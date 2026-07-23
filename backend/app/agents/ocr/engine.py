"""
Thin wrapper around PaddleOCR. Only this file imports paddleocr, so
swapping in PaddleOCR-VL (better on handwriting/skew) or a real TrOCR
model later only touches this file.

NOTE ON VERSION: this project's requirements.txt currently pins
paddlepaddle==2.6.2 / paddleocr==2.9.1, which use the OLD result format
([bbox, (text, confidence)] tuples). This code targets the NEW format
(paddleocr>=3.5), which is what was actually tested and confirmed
working against real handwritten lab reports. If you install exactly
what requirements.txt says, this parsing code will break -- bump those
two pins (see the note at the bottom of this file) rather than
reverting this logic.
"""

import logging
from typing import List

import numpy as np
from paddleocr import PaddleOCR

from app.schemas.agent_messages import TextSpan
from app.schemas.common import BoundingBox

log = logging.getLogger(__name__)


class PaddleOCREngine:
    def __init__(self, lang: str = "en"):
        # enable_mkldnn=False works around a known PaddlePaddle 3.3.x bug:
        # NotImplementedError: ConvertPirAttribute2RuntimeAttribute not
        # support [pir::ArrayAttribute<pir::DoubleAttribute>]
        # https://github.com/PaddlePaddle/Paddle/issues/77340
        self._ocr = PaddleOCR(use_angle_cls=True, lang=lang, enable_mkldnn=False)

    def run(self, image: np.ndarray, page: int = 1) -> List[TextSpan]:
        if image is None or image.size == 0:
            log.warning(f"Page {page}: received empty image, skipping OCR call")
            return []

        try:
            results = self._ocr.predict(image)
        except Exception as exc:
            log.error(f"Page {page}: PaddleOCR predict() raised: {exc}", exc_info=True)
            return []

        if not results:
            return []

        spans: List[TextSpan] = []
        for res in results:
            try:
                data = res.json if hasattr(res, "json") else res
                if isinstance(data, dict) and "res" in data:
                    data = data["res"]

                texts = data.get("rec_texts", [])
                scores = data.get("rec_scores", [])
                polys = data.get("rec_polys", data.get("dt_polys", []))
            except Exception as exc:
                log.warning(f"Page {page}: could not parse OCR result block: {exc}")
                continue

            for text, score, poly in zip(texts, scores, polys):
                if not text or not text.strip():
                    continue
                try:
                    bbox = self._poly_to_bbox(poly, page) if poly is not None else None
                except Exception as exc:
                    log.warning(f"Page {page}: bad bounding-box polygon for span "
                                f"'{text[:30]}': {exc}")
                    bbox = None
                spans.append(
                    TextSpan(
                        text=text,
                        confidence=float(score),
                        bounding_box=bbox,
                        page=page,
                        span_type="handwriting" if self._is_handwriting_mode else "text",
                    )
                )
        return spans

    @staticmethod
    def _poly_to_bbox(poly, page: int) -> BoundingBox:
        xs = [float(p[0]) for p in poly]
        ys = [float(p[1]) for p in poly]
        x, y = min(xs), min(ys)
        return BoundingBox(x=x, y=y, width=max(xs) - x, height=max(ys) - y, page=page)

    @property
    def _is_handwriting_mode(self) -> bool:
        # Placeholder hook: PP-OCRv6 has meaningfully better handwriting
        # support than v5 out of the box, but for genuinely hard cursive
        # handwriting (like real prescriptions), PaddleOCR-VL or a real
        # TrOCR model will do better than the standard detection+recognition
        # pipeline used here. This engine currently uses the same pipeline
        # for both typed and handwritten routing -- swap in a second engine
        # instance here once you've benchmarked alternatives on real samples.
        return False


# ---------------------------------------------------------------------------
# TODO for requirements.txt: bump these two lines to match what's tested:
#   paddlepaddle==2.6.2   -> paddlepaddle>=3.5
#   paddleocr==2.9.1      -> paddleocr>=3.5
# ---------------------------------------------------------------------------