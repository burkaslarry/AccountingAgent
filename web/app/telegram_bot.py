"""Telegram bot for client receipt intake."""

from __future__ import annotations

import logging
import os
import shutil
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from .ocr import is_supported
from .processor import EXPORT_DIR, process_receipt_batch

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[1]
TELEGRAM_SESSION_DIR = BASE_DIR / "uploads" / "telegram"

load_dotenv(BASE_DIR / ".env")

WELCOME_MESSAGE = (
    "Send receipt photos or PDF files here.\n"
    "When you are done, send /done to receive an Excel file.\n"
    "Use /cancel to discard the current batch."
)

ACCESS_DENIED_MESSAGE = (
    "This bot is restricted to approved users.\n"
    "Send /id to see your Telegram user ID, then ask your accountant to add it to the allowlist."
)


def access_denied_message(user_id: int | None) -> str:
    if user_id is None:
        return ACCESS_DENIED_MESSAGE
    return (
        f"{ACCESS_DENIED_MESSAGE}\n\n"
        f"Your user ID: `{user_id}`\n"
        f"Add to TELEGRAM_ALLOWED_USER_IDS in web/.env and restart the bot."
    )


@dataclass
class ChatSession:
    files: list[tuple[str, Path]] = field(default_factory=list)


_sessions: dict[int, ChatSession] = defaultdict(ChatSession)


def allowed_user_ids() -> set[int]:
    raw = os.getenv("TELEGRAM_ALLOWED_USER_IDS", "")
    return {int(value.strip()) for value in raw.split(",") if value.strip().isdigit()}


def allowed_usernames() -> set[str]:
    raw = os.getenv("TELEGRAM_ALLOWED_USER_IDS", "")
    return {
        value.strip().lstrip("@").lower()
        for value in raw.split(",")
        if value.strip() and not value.strip().isdigit()
    }


def is_allowed(user_id: int | None, username: str | None = None) -> bool:
    allowed_ids = allowed_user_ids()
    allowed_names = allowed_usernames()
    if not allowed_ids and not allowed_names:
        return False
    if user_id is not None and user_id in allowed_ids:
        return True
    if username and username.lower().lstrip("@") in allowed_names:
        return True
    return False


def session_dir(chat_id: int) -> Path:
    path = TELEGRAM_SESSION_DIR / str(chat_id) / "pending"
    path.mkdir(parents=True, exist_ok=True)
    return path


def clear_session(chat_id: int) -> None:
    pending_dir = TELEGRAM_SESSION_DIR / str(chat_id) / "pending"
    if pending_dir.exists():
        shutil.rmtree(pending_dir, ignore_errors=True)
    _sessions.pop(chat_id, None)


async def require_allowed(update: Update) -> bool:
    user = update.effective_user
    if is_allowed(user.id if user else None, user.username if user else None):
        return True
    user_id = user.id if user else None
    logger.info("Access denied for Telegram user id %s", user_id)
    if update.message:
        await update.message.reply_text(
            access_denied_message(user_id),
            parse_mode="Markdown",
        )
    return False


async def id_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not update.message or not user:
        return
    allowed = allowed_user_ids()
    status = "approved" if is_allowed(user.id, user.username) else "not on allowlist yet"
    await update.message.reply_text(
        f"Your Telegram user ID: `{user.id}`\n"
        f"Status: {status}\n\n"
        f"Add this to web/.env:\n"
        f"`TELEGRAM_ALLOWED_USER_IDS={user.id}`\n\n"
        f"Then restart the bot.",
        parse_mode="Markdown",
    )


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await require_allowed(update):
        return
    clear_session(update.effective_chat.id)
    await update.message.reply_text(WELCOME_MESSAGE)


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await require_allowed(update):
        return
    clear_session(update.effective_chat.id)
    await update.message.reply_text("Current batch cleared. Send new receipts when ready.")


async def done_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await require_allowed(update):
        return

    chat_id = update.effective_chat.id
    session = _sessions[chat_id]
    if not session.files:
        await update.message.reply_text("No receipts waiting. Send photos or PDFs first.")
        return

    await update.message.reply_text(f"Processing {len(session.files)} receipt(s)...")

    try:
        result = process_receipt_batch(session.files)
    except Exception as exc:  # noqa: BLE001 - report processing failures to user
        logger.exception("Telegram batch processing failed for chat %s", chat_id)
        await update.message.reply_text(f"Processing failed: {exc}")
        return
    finally:
        clear_session(chat_id)

    summary_lines = [
        f"Processed {len(result.rows)} receipt(s).",
    ]
    if result.errors:
        summary_lines.append(f"{len(result.errors)} file(s) had errors:")
        summary_lines.extend(f"- {item['file']}: {item['error']}" for item in result.errors)

    await update.message.reply_text("\n".join(summary_lines))

    xlsx_path = EXPORT_DIR / result.xlsx_filename
    await update.message.reply_document(
        document=str(xlsx_path),
        filename=result.xlsx_filename,
        caption="Receipt export (.xlsx)",
    )


async def handle_receipt_file(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    filename: str,
    telegram_file,
) -> None:
    if not await require_allowed(update):
        return

    if not is_supported(filename):
        await update.message.reply_text(
            f"Unsupported file type: {filename}\nAccepted: PDF, JPG, PNG, WEBP, GIF, BMP, TIFF."
        )
        return

    chat_id = update.effective_chat.id
    pending_dir = session_dir(chat_id)
    safe_name = Path(filename).name
    destination = pending_dir / safe_name

    if destination.exists():
        stem = destination.stem
        suffix = destination.suffix
        counter = 2
        while destination.exists():
            destination = pending_dir / f"{stem}-{counter}{suffix}"
            counter += 1
        safe_name = destination.name

    await telegram_file.download_to_drive(custom_path=destination)

    session = _sessions[chat_id]
    session.files.append((safe_name, destination))

    await update.message.reply_text(
        f"Saved {safe_name}. Total waiting: {len(session.files)}. Send /done when finished."
    )


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.photo:
        return

    photo = update.message.photo[-1]
    filename = f"receipt-{photo.file_unique_id}.jpg"
    telegram_file = await context.bot.get_file(photo.file_id)
    await handle_receipt_file(
        update,
        context,
        filename=filename,
        telegram_file=telegram_file,
    )


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.document:
        return

    document = update.message.document
    filename = document.file_name or f"receipt-{document.file_unique_id}.pdf"
    telegram_file = await context.bot.get_file(document.file_id)
    await handle_receipt_file(
        update,
        context,
        filename=filename,
        telegram_file=telegram_file,
    )


def build_application() -> Application:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set.")

    application = Application.builder().token(token).build()
    application.add_handler(CommandHandler("id", id_command))
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("done", done_command))
    application.add_handler(CommandHandler("cancel", cancel_command))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    return application


def run_telegram_bot() -> None:
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        level=logging.INFO,
    )

    allowed_ids = allowed_user_ids()
    allowed_names = allowed_usernames()
    if not allowed_ids and not allowed_names:
        logger.warning(
            "TELEGRAM_ALLOWED_USER_IDS is empty; all users will be rejected until configured."
        )
    else:
        logger.info(
            "Telegram allowlist enabled for %s user id(s) and %s username(s).",
            len(allowed_ids),
            len(allowed_names),
        )

    application = build_application()
    logger.info("Starting Telegram bot polling.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    run_telegram_bot()
