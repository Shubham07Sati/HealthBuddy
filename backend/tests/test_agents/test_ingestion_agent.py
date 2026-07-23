"""
Tests for Agent 1: Ingestion & Triage.

These build small synthetic PDFs/images in-memory (no fixture files, no
external services) so the suite runs anywhere with just the repo's
requirements.txt installed -- no Postgres/MinIO/Redis required, since
IngestionAgent.route() is a pure function of (bytes, filename) -> envelope.
"""
import io
from uuid import uuid4

import numpy as np
import pytest
from PIL import Image
from pypdf import PdfWriter

from app.agents.ingestion.agent import IngestionAgent
from app.models.document import DocumentType


@pytest.fixture
def agent() -> IngestionAgent:
    return IngestionAgent()


# ------------------------------------------------------------------ #
# Fixture builders
# ------------------------------------------------------------------ #
def _make_text_pdf(text: str = "Patient presented with elevated glucose levels on routine bloodwork. " * 15) -> bytes:
    """Minimal hand-built single-page PDF with a real, extractable text layer."""
    content = f"BT /F1 14 Tf 50 700 Td ({text}) Tj ET".encode("latin-1")
    objects = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 5 0 R >> >> "
        b"/MediaBox [0 0 612 792] /Contents 4 0 R >>\nendobj\n",
        b"4 0 obj\n<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream\nendobj\n",
        b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
    ]
    pdf = b"%PDF-1.4\n"
    offsets = []
    for obj in objects:
        offsets.append(len(pdf))
        pdf += obj
    xref_offset = len(pdf)
    pdf += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        pdf += f"{off:010d} 00000 n \n".encode()
    pdf += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF".encode()
    return pdf


def _make_image_bytes(
    width: int = 1200,
    height: int = 1600,
    color=(255, 255, 255),
    sharp: bool = True,
    fmt: str = "PNG",
) -> bytes:
    arr = np.full((height, width, 3), color, dtype=np.uint8)
    if sharp:
        # A checkerboard-ish pattern of thin lines gives high Laplacian
        # variance, simulating crisp text edges rather than a flat scan.
        arr[::4, :, :] = 0
        arr[:, ::4, :] = 0
    img = Image.fromarray(arr)
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


def _make_image_pdf(width: int = 1600, height: int = 2000) -> bytes:
    """PDF with an embedded image and NO text layer -- a 'scanned' PDF."""
    img_bytes = _make_image_bytes(width, height, sharp=True)
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PDF")
    return buf.getvalue()


def _make_encrypted_pdf() -> bytes:
    writer = PdfWriter()
    for _ in range(5):  # a single blank page encrypts to well under the 1KB size floor
        writer.add_blank_page(width=612, height=792)
    writer.encrypt(user_password="secret123", owner_password="secret123")
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


# ------------------------------------------------------------------ #
# Happy paths
# ------------------------------------------------------------------ #
class TestTypedPdf:
    def test_typed_pdf_routes_to_ocr_with_high_confidence(self, agent):
        envelope = agent.route(
            document_id=uuid4(), patient_id=uuid4(),
            file_bytes=_make_text_pdf(), filename="lab_report.pdf",
            storage_path="s3://docs/lab_report.pdf",
        )
        assert envelope.document_type == DocumentType.typed_pdf
        assert envelope.routing == "ocr"
        assert envelope.quality_score >= 0.9
        assert envelope.rejection_reason is None
        assert envelope.metadata["detected_mime_type"] == "application/pdf"


class TestScannedPdf:
    def test_image_only_pdf_is_treated_as_scanned(self, agent):
        envelope = agent.route(
            document_id=uuid4(), patient_id=uuid4(),
            file_bytes=_make_image_pdf(), filename="scan.pdf",
            storage_path="s3://docs/scan.pdf",
        )
        assert envelope.document_type == DocumentType.scanned_image
        assert envelope.routing == "ocr"


class TestSharpImage:
    def test_crisp_large_image_routes_to_ocr(self, agent):
        envelope = agent.route(
            document_id=uuid4(), patient_id=uuid4(),
            file_bytes=_make_image_bytes(1200, 1600, sharp=True),
            filename="report.png",
            storage_path="s3://docs/report.png",
        )
        assert envelope.document_type == DocumentType.scanned_image
        assert envelope.routing == "ocr"
        assert "blurry" not in envelope.quality_flags
        assert "low_resolution" not in envelope.quality_flags


class TestHandwrittenRouting:
    def test_declared_handwritten_routes_to_handwriting_ocr(self, agent):
        envelope = agent.route(
            document_id=uuid4(), patient_id=uuid4(),
            file_bytes=_make_image_bytes(1200, 1600, sharp=True),
            filename="prescription.jpg",
            storage_path="s3://docs/prescription.jpg",
            declared_type="handwritten",
        )
        assert envelope.document_type == DocumentType.handwritten
        assert envelope.routing == "handwriting_ocr"

    def test_filename_hint_routes_to_handwriting_ocr(self, agent):
        envelope = agent.route(
            document_id=uuid4(), patient_id=uuid4(),
            file_bytes=_make_image_bytes(1200, 1600, sharp=True),
            filename="doctor_handwritten_note.jpg",
            storage_path="s3://docs/note.jpg",
        )
        assert envelope.document_type == DocumentType.handwritten
        assert envelope.routing == "handwriting_ocr"


# ------------------------------------------------------------------ #
# Rejections
# ------------------------------------------------------------------ #
class TestRejections:
    def test_tiny_file_is_rejected(self, agent):
        envelope = agent.route(
            document_id=uuid4(), patient_id=uuid4(),
            file_bytes=b"\x00" * 10, filename="broken.pdf",
            storage_path="s3://docs/broken.pdf",
        )
        assert envelope.routing == "reject"
        assert "corrupt_or_too_small" in envelope.quality_flags
        assert envelope.rejection_reason is not None

    def test_unsupported_mime_type_is_rejected(self, agent):
        envelope = agent.route(
            document_id=uuid4(), patient_id=uuid4(),
            file_bytes=b"Just a plain text file, not a medical document at all here. " * 20,
            filename="notes.txt",
            storage_path="s3://docs/notes.txt",
        )
        assert envelope.routing == "reject"
        assert "unsupported_mime_type" in envelope.quality_flags

    def test_corrupt_pdf_is_rejected(self, agent):
        envelope = agent.route(
            document_id=uuid4(), patient_id=uuid4(),
            file_bytes=b"%PDF-1.4\nthis is not actually a valid pdf body at all " * 40,
            filename="corrupt.pdf",
            storage_path="s3://docs/corrupt.pdf",
        )
        assert envelope.routing == "reject"
        assert envelope.document_type == DocumentType.unknown

    def test_encrypted_pdf_without_password_is_rejected(self, agent):
        envelope = agent.route(
            document_id=uuid4(), patient_id=uuid4(),
            file_bytes=_make_encrypted_pdf(), filename="confidential.pdf",
            storage_path="s3://docs/confidential.pdf",
        )
        assert envelope.routing == "reject"
        assert "encrypted_undecryptable" in envelope.quality_flags

    def test_small_blurry_image_is_rejected(self, agent):
        envelope = agent.route(
            document_id=uuid4(), patient_id=uuid4(),
            file_bytes=_make_image_bytes(200, 200, color=(128, 128, 128), sharp=False, fmt="BMP"),
            filename="bad_scan.bmp",
            storage_path="s3://docs/bad_scan.bmp",
        )
        assert envelope.routing == "reject"
        assert "low_resolution" in envelope.quality_flags
        assert "blurry" in envelope.quality_flags
        assert envelope.quality_score < 0.5

    def test_undecodable_image_is_rejected(self, agent):
        envelope = agent.route(
            document_id=uuid4(), patient_id=uuid4(),
            file_bytes=b"\xff\xd8\xff" + b"\x00" * 2000,  # JPEG magic bytes, garbage body
            filename="garbage.jpg",
            storage_path="s3://docs/garbage.jpg",
        )
        assert envelope.routing == "reject"
        assert envelope.document_type == DocumentType.unknown


# ------------------------------------------------------------------ #
# Non-fatal quality flags (flagged but not rejected)
# ------------------------------------------------------------------ #
class TestNonFatalFlags:
    def test_moderately_blurry_large_image_is_flagged_but_still_processed(self, agent):
        envelope = agent.route(
            document_id=uuid4(), patient_id=uuid4(),
            file_bytes=_make_image_bytes(1200, 1600, color=(200, 200, 200), sharp=False),
            filename="slightly_blurry.jpg",
            storage_path="s3://docs/slightly_blurry.jpg",
        )
        assert "blurry" in envelope.quality_flags
        assert envelope.routing == "ocr"  # large enough to survive on resolution alone


# ------------------------------------------------------------------ #
# Envelope shape / metadata
# ------------------------------------------------------------------ #
class TestEnvelopeMetadata:
    def test_envelope_carries_original_filename_and_ids(self, agent):
        doc_id, patient_id = uuid4(), uuid4()
        envelope = agent.route(
            document_id=doc_id, patient_id=patient_id,
            file_bytes=_make_text_pdf(), filename="discharge_summary.pdf",
            storage_path="s3://docs/discharge_summary.pdf",
        )
        assert envelope.document_id == doc_id
        assert envelope.patient_id == patient_id
        assert envelope.metadata["original_filename"] == "discharge_summary.pdf"
        assert "triage_time_ms" in envelope.metadata
