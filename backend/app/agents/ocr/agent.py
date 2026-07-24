import logging
import time
from typing import List, Tuple
from uuid import UUID

import cv2
import fitz  # PyMuPDF -- no Poppler dependency
import numpy as np

from app.core.config import get_settings
from app.schemas.agent_messages import DocumentEnvelope, RawExtraction, TextSpan
from app.services.storage import storage_service

from .engine import PaddleOCREngine
from . import preprocessing as prep

log = logging.getLogger(__name__)
settings = get_settings()


class OCRAgent:
    """
    Agent 2: OCR & Layout Extraction
    Extracts text from typed and handwritten documents. Owns the decision
    of how to preprocess and whether the result is trustworthy, not just
    the transformation itself.

    Table structure extraction (DetectedTable) is NOT implemented yet --
    that needs PP-StructureV3 or an equivalent layout model, which is a
    separate, non-trivial piece of work. `tables` is always [] for now;
    downstream agents should not assume table data is present.
    """

    def __init__(self):
        self._engine = PaddleOCREngine(lang="en")

    # ------------------------------------------------------------------ #
    # Public entry point, called by the orchestrator                     #
    # ------------------------------------------------------------------ #
    async def extract(self, envelope: DocumentEnvelope) -> RawExtraction:
        start = time.time()
        log.info(f"Starting OCR for doc {envelope.document_id} via route {envelope.routing}")

        try:
            file_bytes = await storage_service.download_document(envelope.storage_path)
        except Exception as exc:
            log.error(f"Failed to download document {envelope.document_id} from "
                      f"'{envelope.storage_path}': {exc}")
            raise

        all_spans: List[TextSpan] = []
        is_pdf = file_bytes[:4] == b"%PDF"

        if is_pdf:
            try:
                doc = fitz.open(stream=file_bytes, filetype="pdf")
                for page_num, page in enumerate(doc, start=1):
                    words = page.get_text("words")
                    if words and len(words) > 10:
                        # Machine readable text found, bypass OCR for this page.
                        # Preserve table layouts by grouping words by vertical Y-center.
                        words.sort(key=lambda w: (round((w[1] + w[3]) / 2 / 5) * 5, (w[0] + w[2]) / 2))
                        
                        lines = []
                        current_y_bucket = None
                        current_line_words = []
                        
                        for w in words:
                            y_center = (w[1] + w[3]) / 2
                            y_bucket = round(y_center / 5) * 5
                            
                            if current_y_bucket is None:
                                current_y_bucket = y_bucket
                            
                            if abs(y_bucket - current_y_bucket) <= 2:
                                current_line_words.append(w[4])
                            else:
                                lines.append(" ".join(current_line_words))
                                current_line_words = [w[4]]
                                current_y_bucket = y_bucket
                                
                        if current_line_words:
                            lines.append(" ".join(current_line_words))
                            
                        full_page_text = "\n".join(lines)
                        all_spans.append(
                            TextSpan(
                                text=full_page_text,
                                confidence=1.0,
                                bounding_box=None,
                                page=page_num,
                                span_type="text"
                            )
                        )
                        log.info(f"Page {page_num}: Bypassed OCR, used layout-preserved native text.")
                    else:
                        # Fallback to OCR for this page
                        mat = fitz.Matrix(1.0, 1.0)
                        pix = page.get_pixmap(matrix=mat, alpha=False)
                        img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
                        img = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
                        try:
                            all_spans.extend(self._process_page(img, page_num))
                        except Exception as exc:
                            log.error(f"OCR failed on page {page_num} of doc {envelope.document_id}: {exc}", exc_info=True)
                doc.close()
            except Exception as exc:
                log.error(f"Failed to process PDF {envelope.document_id}: {exc}", exc_info=True)
        else:
            try:
                arr = np.frombuffer(file_bytes, dtype=np.uint8)
                img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if img is None:
                    raise ValueError("Could not decode document bytes as image")
                all_spans.extend(self._process_page(img, 1))
            except Exception as exc:
                log.error(f"Failed to decode or OCR image {envelope.document_id}: {exc}", exc_info=True)

        avg_confidence = (
            sum(s.confidence for s in all_spans) / len(all_spans) if all_spans else 0.0
        )
        low_confidence = [
            s for s in all_spans if s.confidence < settings.ocr_confidence_threshold
        ]
        full_text = "\n".join(s.text for s in all_spans)

        if not all_spans:
            log.warning(f"OCR produced no text spans for doc {envelope.document_id}")

        return RawExtraction(
            document_id=envelope.document_id,
            spans=all_spans,
            tables=[],  # see class docstring
            full_text=full_text,
            avg_confidence=round(avg_confidence, 4),
            low_confidence_spans=low_confidence,
            ocr_engine="paddleocr+pymupdf",
            processing_time_ms=int((time.time() - start) * 1000),
        )

    def _process_page(self, img: np.ndarray, page: int) -> List[TextSpan]:
        quality, _ = prep.assess_quality(img)

        working_img = img
        spans: List[TextSpan] = []
        applied_steps: List[str] = []

        for attempt in range(1):  # initial try only (demo optimization)
            if attempt == 1:
                working_img = prep.deskew(working_img)
                applied_steps.append("deskew")
            elif attempt == 2 and quality == "blurry":
                working_img = prep.enhance_contrast(working_img)
                applied_steps.append("contrast_enhancement")

            try:
                spans = self._engine.run(working_img, page=page)
            except Exception as exc:
                log.error(f"Page {page}: OCR engine raised on attempt {attempt} "
                          f"(steps so far: {applied_steps}): {exc}")
                spans = []
                continue

            mean_conf = sum(s.confidence for s in spans) / len(spans) if spans else 0.0

            if mean_conf >= settings.ocr_confidence_threshold:
                break

        if quality != "ok":
            log.warning(f"Page {page}: image quality flagged as '{quality}' "
                        f"(preprocessing applied: {applied_steps})")

        return spans