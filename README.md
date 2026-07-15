# AccountingAgent

Receipt upload web app and Telegram bot powered by OCR and Hermes Agent.

Upload PDF or image receipts, extract accounting fields, and download CSV or Excel with:

`Payment Date | Category | Amount | Currency | Reference File`

## Quick start (web)

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

## Telegram bot (client intake)

The Telegram bot lets approved clients send receipt photos or PDFs in chat and receive an Excel file back.

### 1. Create a bot

1. Message [@BotFather](https://t.me/BotFather) on Telegram.
2. Run `/newbot` and copy the bot token.

### 2. Find client Telegram user IDs

Each client can message [@userinfobot](https://t.me/userinfobot) to get their numeric user ID.

### 3. Configure environment

```bash
export TELEGRAM_BOT_TOKEN="your-bot-token"
export TELEGRAM_ALLOWED_USER_IDS="123456789,987654321"
```

If `TELEGRAM_ALLOWED_USER_IDS` is empty, all users are rejected.

### 4. Run the bot

```bash
bash scripts/run-telegram.sh
```

Or manually:

```bash
cd web
source .venv/bin/activate
python -m app.telegram_bot
```

### Client workflow

1. Client sends `/start`.
2. Client sends receipt photos or PDF documents.
3. Client sends `/done` to process the batch and receive `.xlsx`.
4. Client sends `/cancel` to discard the current batch.

The web form remains available for bulk uploads and desktop review.

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

## Export formats

| Format | Web | Telegram |
|--------|-----|----------|
| CSV | Yes | No |
| Excel (.xlsx) | Yes | Yes |

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Telegram only | Bot token from BotFather |
| `TELEGRAM_ALLOWED_USER_IDS` | Telegram only | Comma-separated Telegram user IDs allowed to use the bot |
| `HERMES_TIMEOUT_SECONDS` | No | Hermes subprocess timeout (default `90`) |
| `ACCOUNTING_AGENT_FORCE_HEURISTIC` | No | Set to `1` to skip Hermes and use local parsing |

## Deployment notes

- The Telegram bot must run continuously (polling or webhook).
- Host on a VPS, Railway, or Render — not localhost — for client access.
- Receipts contain PII; restrict bot access with the allowlist and clean up old uploads/exports regularly.

## Legacy iOS demo

The original Tesseract iOS demo remains in `TextScanDemo/`.

## CSV / Excel columns

| Column | Description |
|--------|-------------|
| Payment Date | Transaction date (`YYYY-MM-DD`) |
| Category | Expense category |
| Amount | Total amount |
| Currency | Currency code, default HKD |
| Reference File | Uploaded receipt filename |
