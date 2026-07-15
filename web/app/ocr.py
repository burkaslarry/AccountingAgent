"""Extract text from receipt images and PDFs."""

from __future__ import annotations

import io
from pathlib import Path

import pdfplumber
import pytesseract
from PIL import Image


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tiff", ".tif"}
PDF_SUFFIXES = {".pdf"}


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in IMAGE_SUFFIXES:
        return _extract_image_text(path)
    if suffix in PDF_SUFFIXES:
        return _extract_pdf_text(path)
    raise ValueError(f"Unsupported file type: {suffix}")


def _extract_image_text(path: Path) -> str:
    with Image.open(path) as image:
        rgb = image.convert("RGB")
        return pytesseract.image_to_string(rgb).strip()


def _extract_pdf_text(path: Path) -> str:
    chunks: list[str] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if text.strip():
                chunks.append(text.strip())
            else:
                image_text = _extract_pdf_page_image_text(page)
                if image_text:
                    chunks.append(image_text)
    return "\n\n".join(chunks).strip()


def _extract_pdf_page_image_text(page) -> str:
    if not page.images:
        return ""
    try:
        rendered = page.to_image(resolution=200).original
        return pytesseract.image_to_string(rendered).strip()
    except Exception:
        return ""


def is_supported(filename: str) -> bool:
    suffix = Path(filename).suffix.lower()
    return suffix in IMAGE_SUFFIXES or suffix in PDF_SUFFIXES
