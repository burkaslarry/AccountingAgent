"""Extract text from receipt images and PDFs."""

from __future__ import annotations

from pathlib import Path

import pdfplumber
import pytesseract
from PIL import Image
from pypdf import PdfReader


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tiff", ".tif"}
PDF_SUFFIXES = {".pdf"}


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in IMAGE_SUFFIXES:
        return _sanitize_text(_extract_image_text(path))
    if suffix in PDF_SUFFIXES:
        return _sanitize_text(_extract_pdf_text(path))
    raise ValueError(f"Unsupported file type: {suffix}")


def _sanitize_text(text: str) -> str:
    return text.replace("\x00", "")


def _extract_image_text(path: Path) -> str:
    with Image.open(path) as image:
        rgb = image.convert("RGB")
        return pytesseract.image_to_string(rgb).strip()


def _extract_pdf_text(path: Path) -> str:
    try:
        return _extract_pdf_text_with_pdfplumber(path)
    except Exception:
        return _extract_pdf_text_with_pypdf(path)


def _extract_pdf_text_with_pdfplumber(path: Path) -> str:
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


def _extract_pdf_text_with_pypdf(path: Path) -> str:
    reader = PdfReader(str(path), strict=False)
    chunks: list[str] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        if text.strip():
            chunks.append(text.strip())
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
