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

        try:
            images = self._bytes_to_page_images(file_bytes)
        except Exception as exc:
            log.error(f"Failed to decode document {envelope.document_id} into page "
                      f"images: {exc}")
            return RawExtraction(
                document_id=envelope.document_id,
                spans=[],
                tables=[],
                full_text="",
                avg_confidence=0.0,
                low_confidence_spans=[],
                ocr_engine="paddleocr",
                processing_time_ms=int((time.time() - start) * 1000),
            )

        all_spans: List[TextSpan] = []
        for page_num, img in enumerate(images, start=1):
            try:
                all_spans.extend(self._process_page(img, page_num))
            except Exception as exc:
                # A single unreadable page shouldn't fail the whole
                # document -- log it and keep going with the remaining pages.
                log.error(f"OCR failed on page {page_num} of doc "
                          f"{envelope.document_id}: {exc}", exc_info=True)

        avg_confidence = (
            sum(s.confidence for s in all_spans) / len(all_spans) if all_spans else 0.0
        )
        low_confidence = [
            s for s in all_spans if s.confidence < settings.ocr_confidence_threshold
        ]
        full_text = "\n".join(s.text for s in all_spans)

        if not all_spans:
            log.warning(f"OCR produced no text spans for doc {envelope.document_id} "
                        f"({len(images)} page(s) processed)")

        return RawExtraction(
            document_id=envelope.document_id,
            spans=all_spans,
            tables=[],  # see class docstring
            full_text=full_text,
            avg_confidence=round(avg_confidence, 4),
            low_confidence_spans=low_confidence,
            ocr_engine="paddleocr",
            processing_time_ms=int((time.time() - start) * 1000),
        )

    # ------------------------------------------------------------------ #
    # Internals                                                          #
    # ------------------------------------------------------------------ #
    def _bytes_to_page_images(self, file_bytes: bytes) -> List[np.ndarray]:
        """Convert document bytes to a list of BGR page images.
        Uses PyMuPDF (fitz) for PDFs -- no Poppler dependency required.
        Falls back to OpenCV for raw image files.
        """
        if file_bytes[:4] == b"%PDF":
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            images = []
            for page in doc:
                # Render at 1x zoom for faster OCR (demo optimization)
                mat = fitz.Matrix(1.0, 1.0)
                pix = page.get_pixmap(matrix=mat, alpha=False)
                img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                    pix.height, pix.width, 3
                )
                # fitz returns RGB, OpenCV needs BGR
                images.append(cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR))
            doc.close()
            return images

        arr = np.frombuffer(file_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Could not decode document bytes as image or PDF")
        return [img]

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