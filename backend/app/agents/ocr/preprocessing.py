"""
Image preprocessing for the OCR agent: quality assessment, deskew, contrast.
Ported unchanged from the standalone prototype -- these operate on in-memory
numpy arrays, so they don't care whether the image came from local disk or
(as in this project) was downloaded from MinIO.
"""

import cv2
import numpy as np


def _variance_of_laplacian(gray: np.ndarray) -> float:
    return cv2.Laplacian(gray, cv2.CV_64F).var()


def assess_quality(img: np.ndarray, blur_threshold: float = 100.0,
                    min_brightness: float = 60.0, min_dimension_px: int = 600):
    """Cheap pre-OCR checks. Returns (quality_label: str, blur_score: float)."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape[:2]

    if min(h, w) < min_dimension_px:
        return "too_small", 0.0

    blur_score = _variance_of_laplacian(gray)
    if blur_score < blur_threshold:
        return "blurry", blur_score

    if gray.mean() < min_brightness:
        return "too_dark", blur_score

    return "ok", blur_score


def deskew(img: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.bitwise_not(gray)
    thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]

    coords = np.column_stack(np.where(thresh > 0))
    if coords.size == 0:
        return img

    angle = cv2.minAreaRect(coords)[-1]
    angle = -(90 + angle) if angle < -45 else -angle

    (h, w) = img.shape[:2]
    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, angle, 1.0)
    return cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


def enhance_contrast(img: np.ndarray) -> np.ndarray:
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l = clahe.apply(l)
    merged = cv2.merge((l, a, b))
    return cv2.cvtColor(merged, cv2.COLOR_LAB2BGR)