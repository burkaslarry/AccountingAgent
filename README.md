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

Bot: [@acctxp_bot](https://t.me/acctxp_bot) (replace with your own if you create a new bot)

### 1. Create a bot

1. Message [@BotFather](https://t.me/BotFather) on Telegram.
2. Run `/newbot` and copy the bot token.

### 2. Configure environment

Copy the example env file and edit it:

```bash
cp web/.env.example web/.env
```

```bash
TELEGRAM_BOT_TOKEN=your-bot-token-from-botfather
TELEGRAM_ALLOWED_USER_IDS=123456789,xx275usagi
```

Allowlist accepts **numeric user IDs** and/or **Telegram usernames** (without `@`).

Clients can send `/id` to the bot to see their numeric ID, or message [@userinfobot](https://t.me/userinfobot).

If `TELEGRAM_ALLOWED_USER_IDS` is empty, all users are rejected.

### 3. Run the bot

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
| `TELEGRAM_ALLOWED_USER_IDS` | Telegram only | Comma-separated Telegram user IDs and/or usernames |
| `HERMES_TIMEOUT_SECONDS` | No | Hermes subprocess timeout (default `90`) |
| `ACCOUNTING_AGENT_FORCE_HEURISTIC` | No | Set to `1` to skip Hermes and use local parsing |

## Deployment (3–5 concurrent users)

For **3–5 CCU** (clients uploading receipts at the same time), you do not need a large server. You do need:

- **Always-on process** for the Telegram bot (polling or webhook)
- **Tesseract OCR** installed on the host (`tesseract` system package)
- **~512 MB–1 GB RAM** and 1 vCPU is usually enough
- **HTTPS** if you expose the web UI publicly
- **Allowlist** on the bot — receipts contain PII

### Recommended cheap platforms

| Platform | Est. cost | Best for | Notes |
|----------|-----------|----------|-------|
| [Hetzner Cloud](https://www.hetzner.com/cloud) CX22 | ~€4–5/mo | **Best value** | Small VPS; install Tesseract + run web + bot with systemd. Most predictable for OCR. |
| [DigitalOcean](https://www.digitalocean.com/) Basic Droplet | ~$6/mo | Simple VPS | Same as Hetzner; good docs, 1 GB RAM tier. |
| [Oracle Cloud](https://www.oracle.com/cloud/free/) Always Free | $0 | Tight budget | Free ARM VM (up to 4 OCPU / 24 GB). More setup, but fine for 3–5 CCU. |
| [Fly.io](https://fly.io/) | ~$5–7/mo | Container deploy | Deploy with Docker; scale-to-zero **not** suitable for Telegram polling. |
| [Railway](https://railway.app/) | ~$5/mo hobby | Fastest PaaS setup | Use a Dockerfile with Tesseract; run web and bot as two services. |

**Not recommended for the Telegram bot:** Render/Railway **free tiers that sleep** — the bot must stay awake to receive messages.

### Suggested architecture (3–5 CCU)

```text
                    ┌─────────────────────┐
  Clients (web) ──► │  FastAPI :8080      │
                    │  (uvicorn)          │
                    └──────────┬──────────┘
                               │
  Clients (TG) ───► ┌──────────▼──────────┐
                    │  telegram_bot.py    │──► shared processor + OCR
                    │  (always-on)        │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │  uploads/ exports/  │
                    └─────────────────────┘
```

**Simplest path:** one **Hetzner or DigitalOcean VPS** ($4–6/mo):

```bash
# On Ubuntu VPS
sudo apt update && sudo apt install -y python3-venv tesseract-ocr git
git clone https://github.com/burkaslarry/AccountingAgent.git
cd AccountingAgent/web
cp .env.example .env   # add TELEGRAM_BOT_TOKEN and allowlist
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Web (optional, behind nginx + HTTPS)
uvicorn app.main:app --host 0.0.0.0 --port 8080

# Telegram bot (required for @acctxp_bot)
python -m app.telegram_bot
```

Use **systemd** or **supervisor** to keep both processes running after reboot.

### Production checklist

- [ ] Copy `web/.env.example` → `web/.env` on the server (never commit `.env`)
- [ ] Set `TELEGRAM_ALLOWED_USER_IDS` to real client IDs/usernames
- [ ] Install `tesseract-ocr` on the host
- [ ] Run Telegram bot as an always-on service
- [ ] Put nginx/Caddy in front of the web app for HTTPS (optional)
- [ ] Schedule cleanup of `web/uploads/` and `web/exports/` (PII retention)
- [ ] Revoke and rotate the bot token if it was ever shared publicly

## CSV / Excel columns

| Column | Description |
|--------|-------------|
| Payment Date | Transaction date (`YYYY-MM-DD`) |
| Category | Expense category |
| Amount | Total amount |
| Currency | Currency code (inferred from address; e.g. USD, HKD) |
| Reference File | Uploaded receipt filename |
