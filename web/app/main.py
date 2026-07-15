"""AccountingAgent web API."""

from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from .ocr import is_supported
from .processor import EXPORT_DIR, UPLOAD_DIR, new_batch_id, process_receipt_batch

BASE_DIR = Path(__file__).resolve().parents[1]
STATIC_DIR = BASE_DIR / "static"

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

    batch_id = new_batch_id()
    batch_dir = UPLOAD_DIR / batch_id
    batch_dir.mkdir(parents=True, exist_ok=True)

    saved_files: list[tuple[str, Path]] = []
    pre_errors: list[dict[str, str]] = []

    for upload in files:
        filename = upload.filename or "receipt"
        if not is_supported(filename):
            pre_errors.append({"file": filename, "error": "Unsupported file type."})
            continue

        safe_name = Path(filename).name
        saved_path = batch_dir / safe_name
        with saved_path.open("wb") as handle:
            shutil.copyfileobj(upload.file, handle)
        saved_files.append((safe_name, saved_path))

    if not saved_files and pre_errors:
        raise HTTPException(status_code=400, detail="No supported receipt files were uploaded.")

    result = process_receipt_batch(saved_files, batch_id=batch_id)
    result.errors = pre_errors + result.errors
    return result.to_api_dict()


@app.get("/api/download/{filename}")
def download_export(filename: str) -> FileResponse:
    safe_name = Path(filename).name
    export_path = EXPORT_DIR / safe_name
    if not export_path.exists():
        raise HTTPException(status_code=404, detail="Export file not found.")

    if safe_name.endswith(".xlsx"):
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        media_type = "text/csv"

    return FileResponse(
        export_path,
        media_type=media_type,
        filename=safe_name,
    )
