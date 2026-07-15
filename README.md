# AccountingAgent

Receipt upload web app powered by OCR and Hermes Agent.

Upload PDF or image receipts, extract accounting fields, and download a CSV with:

`Payment Date | Category | Amount | Currency (HKD) | Reference File`

## Quick start

```bash
cd web
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
bash ../scripts/hermes/install-skill.sh
uvicorn app.main:app --host 127.0.0.1 --port 8080 --reload
```

Open: http://127.0.0.1:8080

Or run:

```bash
bash scripts/run-web.sh
```

## Hermes Agent

Install the receipt skill:

```bash
bash scripts/hermes/install-skill.sh
```

Configure an LLM provider for Hermes:

```bash
hermes setup
hermes doctor
```

If Hermes is unavailable or no provider is configured, the app falls back to local OCR + heuristic parsing.

## Supported files

- Images: JPG, PNG, WEBP, GIF, BMP, TIFF
- Documents: PDF

## Legacy iOS demo

The original Tesseract iOS demo remains in `TextScanDemo/`.

## CSV columns

| Column | Description |
|--------|-------------|
| Payment Date | Transaction date (`YYYY-MM-DD`) |
| Category | Expense category |
| Amount | Total amount |
| Currency (HKD) | Currency code, default HKD |
| Reference File | Uploaded receipt filename |
