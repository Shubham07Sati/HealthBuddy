"""
Agent 1: Ingestion & Triage
===========================
Runs synchronously inside the upload request handler (see
api/v1/documents.py) -- deliberately NOT a LangGraph node. Its output
(the routing decision) determines whether a Celery job gets enqueued at
all, so it needs to return a fast, cheap answer before anything is
pushed onto a queue. See the Orchestrator docstring in
agents/orchestrator/pipeline.py for the full reasoning on that split.

Responsibilities (and, importantly, what this agent does NOT do):

1. Verify the upload is a file type/format the rest of the pipeline can
   actually handle (MIME sniffing, not trusting the client-supplied
   Content-Type or file extension).
2. Classify document STRUCTURE: typed_pdf / scanned_image / handwritten.
   This is NOT clinical category (lab_report, discharge_summary, ...).
   Clinical category requires reading the content, which doesn't exist
   yet at ingestion time -- that gets set later by the NER/Reasoning
   agents once OCR text is available. Asking this agent to guess
   "discharge_summary" from raw bytes would be a coin flip dressed up as
   a classification.
3. Score document quality (blur, brightness, resolution, corrupt/
   encrypted files) using real signal -- not a fixed placeholder -- and
   turn that into a routing decision: proceed to OCR, proceed to
   handwriting OCR, or reject outright with a human-readable reason.

Known limitation, intentionally left as a v2 item rather than solved
here: handwritten-vs-printed classification currently relies on a
declared_type hint from the frontend (a checkbox) with a filename
keyword fallback. A dedicated printed-vs-handwritten vision classifier
(e.g. a small ViT/CNN fine-tuned on IAM + medical handwriting samples)
would remove the dependency on the user self-reporting correctly, and
is flagged as a concrete follow-on research contribution rather than
something worth building into this MVP triage step.
"""

import logging
import time
from io import BytesIO
from typing import List, Optional, Tuple
from uuid import UUID

import cv2
import magic
import numpy as np
from pdf2image import convert_from_bytes
from pypdf import PdfReader

from app.models.document import DocumentType
from app.schemas.agent_messages import DocumentEnvelope

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------- #
# Thresholds -- deliberately distinct from ocr/preprocessing.py's
# per-page thresholds. This is a one-shot gatekeeper that runs before
# anything is enqueued; the OCR agent's thresholds gate per-page retries
# *during* OCR itself. Conflating the two would make it hard to reason
# about which layer rejected a document and why.
# ---------------------------------------------------------------------- #
MIN_FILE_SIZE_BYTES = 1_000
MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB
MIN_DIMENSION_PX = 500
BLUR_VARIANCE_THRESHOLD = 80.0
MIN_BRIGHTNESS = 50.0
MAX_BRIGHTNESS = 245.0
MAX_SKEW_DEGREES = 5.0
MIN_TEXT_LAYER_CHARS_PER_PAGE = 40  # avg chars/page to call a PDF "typed"
REJECT_QUALITY_THRESHOLD = 0.5

ACCEPTED_MIME_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/tiff",
    "image/bmp",
    "image/webp",
}

HANDWRITTEN_FILENAME_HINTS = ("handwritten", "handwriting", "note", "script", "scribble")

_REASON_TEXT = {
    "unsupported_mime_type": "File type is not supported.",
    "corrupt_or_too_small": "File is empty, truncated, or too small to be a legible document.",
    "file_too_large": f"File exceeds the {MAX_FILE_SIZE_BYTES // (1024 * 1024)}MB upload limit.",
    "undecodable_image": "Image data could not be decoded -- the file may be corrupt.",
    "corrupt_pdf": "PDF could not be parsed -- the file may be corrupt or not a valid PDF.",
    "encrypted_undecryptable": "PDF is password-protected and could not be opened.",
    "unrenderable_pdf": "PDF pages could not be rendered for quality inspection.",
    "empty_pdf": "PDF contains no pages.",
    "low_resolution": "Image resolution is too low for reliable OCR.",
    "blurry": "Image is too blurry for reliable OCR.",
    "too_dark": "Image is too dark / underexposed.",
    "overexposed": "Image is overexposed / washed out.",
    "skewed": "Page appears significantly rotated.",
}


class IngestionAgent:
    """Agent 1: Ingestion & Triage."""

    def __init__(self):
        pass

    # ------------------------------------------------------------------ #
    # Public entry point
    # ------------------------------------------------------------------ #
    def route(
        self,
        document_id: UUID,
        patient_id: UUID,
        file_bytes: bytes,
        filename: str,
        storage_path: str,
        declared_type: Optional[str] = None,
    ) -> DocumentEnvelope:
        start = time.time()

        size_flags = self._check_size(file_bytes)
        if "corrupt_or_too_small" in size_flags or "file_too_large" in size_flags:
            return self._build_envelope(
                document_id, patient_id, storage_path, filename, declared_type,
                doc_type=DocumentType.unknown, quality_score=0.0,
                flags=size_flags, mime="unknown", start=start,
            )

        mime = self._detect_mime(file_bytes)
        if mime not in ACCEPTED_MIME_TYPES:
            return self._build_envelope(
                document_id, patient_id, storage_path, filename, declared_type,
                doc_type=DocumentType.unknown, quality_score=0.0,
                flags=["unsupported_mime_type"], mime=mime, start=start,
            )

        if mime == "application/pdf":
            doc_type, quality_score, flags = self._triage_pdf(file_bytes, filename, declared_type)
        else:
            doc_type, quality_score, flags = self._triage_image(file_bytes, filename, declared_type)

        return self._build_envelope(
            document_id, patient_id, storage_path, filename, declared_type,
            doc_type=doc_type, quality_score=quality_score,
            flags=size_flags + flags, mime=mime, start=start,
        )

    # ------------------------------------------------------------------ #
    # PDF triage
    # ------------------------------------------------------------------ #
    def _triage_pdf(
        self, file_bytes: bytes, filename: str, declared_type: Optional[str]
    ) -> Tuple[DocumentType, float, List[str]]:
        try:
            reader = PdfReader(BytesIO(file_bytes))
        except Exception as exc:  # pypdf raises several distinct exception types on malformed files
            log.warning(f"Failed to parse PDF '{filename}': {exc}")
            return DocumentType.unknown, 0.0, ["corrupt_pdf"]

        if reader.is_encrypted:
            try:
                # Some PDFs are "encrypted" with an empty owner password
                # purely for permissions (no user password required). The
                # page tree cannot be walked at all until this succeeds --
                # attempting to read .pages first (before checking
                # is_encrypted) raises on pypdf, it doesn't just return
                # empty results.
                if reader.decrypt("") == 0:
                    return DocumentType.unknown, 0.0, ["encrypted_undecryptable"]
            except Exception:
                return DocumentType.unknown, 0.0, ["encrypted_undecryptable"]

        try:
            num_pages = len(reader.pages)
        except Exception as exc:
            log.warning(f"Failed to walk page tree for '{filename}': {exc}")
            return DocumentType.unknown, 0.0, ["corrupt_pdf"]

        if num_pages == 0:
            return DocumentType.unknown, 0.0, ["empty_pdf"]

        sample_pages = reader.pages[: min(3, num_pages)]
        total_chars = sum(len((p.extract_text() or "").strip()) for p in sample_pages)
        avg_chars_per_page = total_chars / len(sample_pages)

        if avg_chars_per_page >= MIN_TEXT_LAYER_CHARS_PER_PAGE:
            # Real, selectable text layer -- render quality barely matters,
            # OCR isn't even doing the heavy lifting here. High confidence.
            return DocumentType.typed_pdf, 0.98, []

        # No usable text layer -> this is effectively a scan wrapped in a
        # PDF container. Render the first page and run image-quality
        # checks so a genuinely poor scan still gets caught before OCR.
        try:
            pages = convert_from_bytes(file_bytes, dpi=150, first_page=1, last_page=1)
        except Exception as exc:  # covers PDFPageCountError, PDFSyntaxError, and poppler binary issues
            log.warning(f"Failed to render PDF page for '{filename}': {exc}")
            return DocumentType.unknown, 0.2, ["unrenderable_pdf"]

        img = cv2.cvtColor(np.array(pages[0]), cv2.COLOR_RGB2BGR)
        quality_score, quality_flags = self._assess_image_quality(img)
        doc_type = DocumentType.handwritten if self._looks_handwritten(filename, declared_type) \
            else DocumentType.scanned_image
        return doc_type, quality_score, quality_flags

    # ------------------------------------------------------------------ #
    # Image triage
    # ------------------------------------------------------------------ #
    def _triage_image(
        self, file_bytes: bytes, filename: str, declared_type: Optional[str]
    ) -> Tuple[DocumentType, float, List[str]]:
        arr = np.frombuffer(file_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            return DocumentType.unknown, 0.0, ["undecodable_image"]

        quality_score, quality_flags = self._assess_image_quality(img)
        doc_type = DocumentType.handwritten if self._looks_handwritten(filename, declared_type) \
            else DocumentType.scanned_image
        return doc_type, quality_score, quality_flags

    # ------------------------------------------------------------------ #
    # Shared image quality scoring
    # ------------------------------------------------------------------ #
    def _assess_image_quality(self, img: np.ndarray) -> Tuple[float, List[str]]:
        """
        Returns a quality score in [0, 1] plus flags explaining any
        deductions. Deliberately independent from ocr/preprocessing.py's
        `assess_quality` (which returns a single categorical label used
        to decide whether OCR should retry with deskew/contrast
        enhancement) -- this one produces a continuous score used for a
        binary accept/reject gate, and needs to combine multiple
        independent defects rather than short-circuit on the first one.
        """
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape[:2]
        flags: List[str] = []
        score = 1.0

        if min(h, w) < MIN_DIMENSION_PX:
            flags.append("low_resolution")
            score -= 0.45

        blur_variance = cv2.Laplacian(gray, cv2.CV_64F).var()
        if blur_variance < BLUR_VARIANCE_THRESHOLD:
            flags.append("blurry")
            # Scale the penalty by how far below threshold it is, rather
            # than a flat deduction -- a near-miss shouldn't cost as much
            # as a completely unusable image.
            severity = min(1.0, (BLUR_VARIANCE_THRESHOLD - blur_variance) / BLUR_VARIANCE_THRESHOLD)
            score -= 0.4 * severity

        brightness = float(gray.mean())
        if brightness < MIN_BRIGHTNESS:
            flags.append("too_dark")
            score -= 0.25
        elif brightness > MAX_BRIGHTNESS:
            flags.append("overexposed")
            score -= 0.15

        skew_angle = self._estimate_skew(gray)
        if abs(skew_angle) > MAX_SKEW_DEGREES:
            flags.append("skewed")
            # Minor penalty only -- the OCR agent's preprocessing step
            # (ocr/preprocessing.deskew) can correct this automatically,
            # so it shouldn't be enough to reject a document on its own.
            score -= 0.1

        return max(0.0, min(1.0, score)), flags

    @staticmethod
    def _estimate_skew(gray: np.ndarray) -> float:
        inverted = cv2.bitwise_not(gray)
        thresh = cv2.threshold(inverted, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
        coords = np.column_stack(np.where(thresh > 0))
        if coords.size == 0:
            return 0.0
        angle = cv2.minAreaRect(coords)[-1]
        return -(90 + angle) if angle < -45 else -angle

    # ------------------------------------------------------------------ #
    # Small helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _detect_mime(file_bytes: bytes) -> str:
        try:
            return magic.from_buffer(file_bytes, mime=True)
        except Exception as exc:
            log.warning(f"MIME detection failed, falling back to octet-stream: {exc}")
            return "application/octet-stream"

    @staticmethod
    def _check_size(file_bytes: bytes) -> List[str]:
        if len(file_bytes) < MIN_FILE_SIZE_BYTES:
            return ["corrupt_or_too_small"]
        if len(file_bytes) > MAX_FILE_SIZE_BYTES:
            return ["file_too_large"]
        return []

    @staticmethod
    def _looks_handwritten(filename: str, declared_type: Optional[str]) -> bool:
        if declared_type and declared_type.lower() == "handwritten":
            return True
        lower_name = filename.lower()
        return any(hint in lower_name for hint in HANDWRITTEN_FILENAME_HINTS)

    @staticmethod
    def _build_rejection_reason(flags: List[str], quality_score: float) -> str:
        messages = [_REASON_TEXT[f] for f in flags if f in _REASON_TEXT]
        if not messages:
            messages.append(
                f"Document quality score ({quality_score:.2f}) fell below the "
                f"acceptable threshold ({REJECT_QUALITY_THRESHOLD})."
            )
        return " ".join(messages)

    def _build_envelope(
        self,
        document_id: UUID,
        patient_id: UUID,
        storage_path: str,
        filename: str,
        declared_type: Optional[str],
        doc_type: DocumentType,
        quality_score: float,
        flags: List[str],
        mime: str,
        start: float,
    ) -> DocumentEnvelope:
        routing = "ocr"
        rejection_reason = None

        if quality_score < REJECT_QUALITY_THRESHOLD or doc_type == DocumentType.unknown:
            routing = "reject"
            rejection_reason = self._build_rejection_reason(flags, quality_score)
        elif doc_type == DocumentType.handwritten:
            routing = "handwriting_ocr"

        envelope = DocumentEnvelope(
            document_id=document_id,
            patient_id=patient_id,
            storage_path=storage_path,
            document_type=doc_type,
            quality_score=round(quality_score, 4),
            quality_flags=flags,
            routing=routing,
            rejection_reason=rejection_reason,
            metadata={
                "original_filename": filename,
                "detected_mime_type": mime,
                "declared_type": declared_type,
                "triage_time_ms": int((time.time() - start) * 1000),
            },
        )
        log.info(
            f"Ingestion triage for {document_id}: type={doc_type.value} "
            f"quality={envelope.quality_score} routing={routing} flags={flags}"
        )
        return envelope
