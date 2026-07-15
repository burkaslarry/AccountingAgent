"""Shared receipt batch processing for web and Telegram."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .agent import ReceiptRow, parse_receipt
from .csv_export import rows_to_csv
from .excel_export import rows_to_xlsx_bytes
from .ocr import extract_text, is_supported

BASE_DIR = Path(__file__).resolve().parents[1]
UPLOAD_DIR = BASE_DIR / "uploads"
EXPORT_DIR = BASE_DIR / "exports"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
EXPORT_DIR.mkdir(parents=True, exist_ok=True)

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}


@dataclass
class ProcessResult:
    batch_id: str
    rows: list[ReceiptRow]
    errors: list[dict[str, str]]
    csv_filename: str
    xlsx_filename: str
    batch_dir: Path

    def to_api_dict(self) -> dict:
        return {
            "batch_id": self.batch_id,
            "rows": [row.to_dict() for row in self.rows],
            "errors": self.errors,
            "csv_filename": self.csv_filename,
            "xlsx_filename": self.xlsx_filename,
            "download_url": f"/api/download/{self.csv_filename}",
            "excel_download_url": f"/api/download/{self.xlsx_filename}",
        }


def new_batch_id() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]


def process_receipt_batch(
    files: list[tuple[str, Path]],
    batch_id: str | None = None,
) -> ProcessResult:
    """Process saved receipt files and write CSV + Excel exports."""
    if not files:
        raise ValueError("Upload at least one receipt.")

    resolved_batch_id = batch_id or new_batch_id()
    batch_dir = UPLOAD_DIR / resolved_batch_id

    rows: list[ReceiptRow] = []
    errors: list[dict[str, str]] = []

    for reference_file, saved_path in files:
        if not is_supported(reference_file):
            errors.append({"file": reference_file, "error": "Unsupported file type."})
            continue

        try:
            text = extract_text(saved_path)
            if not text.strip():
                raise ValueError("No readable text found in receipt.")
            image_path = saved_path if saved_path.suffix.lower() in IMAGE_SUFFIXES else None
            row = parse_receipt(text, reference_file, image_path=image_path)
            rows.append(row)
        except Exception as exc:  # noqa: BLE001 - surface per-file failures to callers
            errors.append({"file": reference_file, "error": str(exc)})

    csv_filename = f"receipts-{resolved_batch_id}.csv"
    xlsx_filename = f"receipts-{resolved_batch_id}.xlsx"

    csv_path = EXPORT_DIR / csv_filename
    xlsx_path = EXPORT_DIR / xlsx_filename

    csv_path.write_text(rows_to_csv(rows), encoding="utf-8")
    xlsx_path.write_bytes(rows_to_xlsx_bytes(rows))

    return ProcessResult(
        batch_id=resolved_batch_id,
        rows=rows,
        errors=errors,
        csv_filename=csv_filename,
        xlsx_filename=xlsx_filename,
        batch_dir=batch_dir,
    )
