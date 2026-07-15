"""AccountingAgent web API."""

from __future__ import annotations

import shutil
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from .agent import ReceiptRow, parse_receipt
from .csv_export import rows_to_csv
from .ocr import extract_text, is_supported

BASE_DIR = Path(__file__).resolve().parents[1]
STATIC_DIR = BASE_DIR / "static"
UPLOAD_DIR = BASE_DIR / "uploads"
EXPORT_DIR = BASE_DIR / "exports"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
EXPORT_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="AccountingAgent", version="1.0.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse((STATIC_DIR / "index.html").read_text(encoding="utf-8"))


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "AccountingAgent"}


@app.post("/api/process")
async def process_receipts(files: list[UploadFile] = File(...)) -> dict:
    if not files:
        raise HTTPException(status_code=400, detail="Upload at least one receipt.")

    batch_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
    batch_dir = UPLOAD_DIR / batch_id
    batch_dir.mkdir(parents=True, exist_ok=True)

    rows: list[ReceiptRow] = []
    errors: list[dict[str, str]] = []

    for upload in files:
        filename = upload.filename or "receipt"
        if not is_supported(filename):
            errors.append({"file": filename, "error": "Unsupported file type."})
            continue

        safe_name = Path(filename).name
        saved_path = batch_dir / safe_name
        with saved_path.open("wb") as handle:
            shutil.copyfileobj(upload.file, handle)

        try:
            text = extract_text(saved_path)
            if not text.strip():
                raise ValueError("No readable text found in receipt.")
            image_path = saved_path if saved_path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"} else None
            row = parse_receipt(text, safe_name, image_path=image_path)
            rows.append(row)
        except Exception as exc:  # noqa: BLE001 - surface per-file failures to UI
            errors.append({"file": safe_name, "error": str(exc)})

    csv_content = rows_to_csv(rows)
    export_name = f"receipts-{batch_id}.csv"
    export_path = EXPORT_DIR / export_name
    export_path.write_text(csv_content, encoding="utf-8")

    return {
        "batch_id": batch_id,
        "rows": [row.to_dict() for row in rows],
        "errors": errors,
        "csv_filename": export_name,
        "download_url": f"/api/download/{export_name}",
    }


@app.get("/api/download/{filename}")
def download_csv(filename: str) -> FileResponse:
    safe_name = Path(filename).name
    export_path = EXPORT_DIR / safe_name
    if not export_path.exists():
        raise HTTPException(status_code=404, detail="CSV not found.")
    return FileResponse(
        export_path,
        media_type="text/csv",
        filename=safe_name,
    )
