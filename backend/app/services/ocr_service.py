from __future__ import annotations

import io
import re
from dataclasses import dataclass

import cv2
import numpy as np
import pytesseract
from fastapi import UploadFile
from PIL import Image
from rapidfuzz import fuzz

from app.core.config import Settings


DOSAGE_PATTERN = re.compile(r"\b\d+(\.\d+)?\s?(mg|mcg|g|ml|iu|%)\b", re.IGNORECASE)
NOISE_PATTERN = re.compile(r"[^a-zA-Z0-9\s\-+/]")
FORM_WORDS = {
    "tablet",
    "tablets",
    "capsule",
    "capsules",
    "syrup",
    "injection",
    "cream",
    "ointment",
    "drops",
    "solution",
    "suspension",
    "gel",
    "spray",
    "patch",
}


@dataclass
class OCRResult:
    raw_text: str
    cleaned_text: str
    candidates: list[str]


class OCRService:
    def __init__(self, settings: Settings) -> None:
        if settings.tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd

    async def extract_medicine_candidates(self, upload: UploadFile) -> OCRResult:
        contents = await upload.read()
        if not contents:
            return OCRResult(raw_text="", cleaned_text="", candidates=[])

        image = Image.open(io.BytesIO(contents)).convert("RGB")
        processed = self._preprocess_image(image)
        raw_text = pytesseract.image_to_string(processed, config="--oem 3 --psm 6")
        cleaned = self.clean_text(raw_text)
        candidates = self.extract_candidates(cleaned)
        return OCRResult(raw_text=raw_text, cleaned_text=cleaned, candidates=candidates)

    def _preprocess_image(self, image: Image.Image) -> np.ndarray:
        cv_image = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(cv_image, cv2.COLOR_BGR2GRAY)
        scale = max(1.0, 1400 / max(gray.shape[:2]))
        if scale > 1:
            gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        gray = cv2.bilateralFilter(gray, 9, 75, 75)
        return cv2.adaptiveThreshold(
            gray,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            31,
            11,
        )

    @staticmethod
    def clean_text(text: str) -> str:
        lines: list[str] = []
        for line in text.splitlines():
            normalized = NOISE_PATTERN.sub(" ", line)
            normalized = re.sub(r"\s+", " ", normalized).strip()
            if normalized:
                lines.append(normalized)
        return "\n".join(lines)

    @staticmethod
    def extract_candidates(cleaned_text: str) -> list[str]:
        scored: list[tuple[float, str]] = []
        seen: set[str] = set()

        for line in cleaned_text.splitlines():
            candidate = DOSAGE_PATTERN.sub(" ", line)
            candidate = re.sub(r"\b(rx|usp|ip|bp|net|qty|batch|mfg|exp|mrp)\b", " ", candidate, flags=re.I)
            candidate = re.sub(r"\s+", " ", candidate).strip(" -+/")
            if len(candidate) < 3 or candidate.lower() in seen:
                continue

            words = candidate.split()
            alpha_ratio = sum(ch.isalpha() for ch in candidate) / max(len(candidate), 1)
            form_similarity = max((fuzz.partial_ratio(word.lower(), form) for word in words for form in FORM_WORDS), default=0)
            score = alpha_ratio * 60 + min(len(words), 5) * 6 + form_similarity * 0.15

            if any(word.lower() in FORM_WORDS for word in words):
                score -= 4
            if len(candidate) > 60:
                score -= 20

            seen.add(candidate.lower())
            scored.append((score, candidate))

        scored.sort(reverse=True, key=lambda item: item[0])
        return [candidate for _, candidate in scored[:5]]
