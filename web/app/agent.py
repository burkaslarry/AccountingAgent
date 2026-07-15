"""Hermes Agent + heuristic receipt parsing."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path


CATEGORIES = [
    "Food & Dining",
    "Transport",
    "Office Supplies",
    "Utilities",
    "Entertainment",
    "Shopping",
    "Medical",
    "Travel",
    "Professional Services",
    "Other",
]

CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "Food & Dining": ("restaurant", "cafe", "coffee", "food", "餐", "飯", "茶餐", "麥當", "starbucks"),
    "Transport": ("taxi", "uber", "mtr", "octopus", "港鐵", "的士", "油站", "parking", "停車"),
    "Office Supplies": ("stationery", "office", "文具", "打印", "print"),
    "Utilities": ("electric", "water", "gas", "電力", "水費", "煤氣", "clp", "hk electric"),
    "Entertainment": ("cinema", "netflix", "spotify", "game", "電影", "娛樂"),
    "Shopping": ("market", "mall", "store", "shop", "百貨", "超市", "wellcome", "parknshop"),
    "Medical": ("clinic", "hospital", "pharmacy", "診所", "醫", "藥房"),
    "Travel": ("hotel", "airline", "flight", "booking", "酒店", "機票", "旅"),
    "Professional Services": ("consult", "legal", "account", "會計", "法律", "顧問"),
}


@dataclass
class ReceiptRow:
    payment_date: str
    category: str
    amount: str
    currency: str
    reference_file: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def parse_receipt(text: str, reference_file: str, image_path: Path | None = None) -> ReceiptRow:
    hermes_row = _parse_with_hermes(text, reference_file, image_path)
    if hermes_row:
        return hermes_row
    return _parse_heuristic(text, reference_file)


def _parse_with_hermes(
    text: str,
    reference_file: str,
    image_path: Path | None,
) -> ReceiptRow | None:
    if shutil.which("hermes") is None:
        return None
    if os.getenv("ACCOUNTING_AGENT_FORCE_HEURISTIC", "").lower() in {"1", "true", "yes"}:
        return None

    prompt = (
        "Extract accounting fields from this receipt OCR text. "
        "Return ONLY one JSON object with keys: payment_date (YYYY-MM-DD), "
        "category (one of: "
        + ", ".join(CATEGORIES)
        + "), amount (number only), currency (default HKD). "
        f"Reference file is {reference_file}.\n\nOCR:\n{text[:6000]}"
    )

    command = [
        "hermes",
        "chat",
        "-q",
        prompt,
        "-Q",
        "-s",
        "receipt-extractor",
        "--source",
        "tool",
        "--max-turns",
        "3",
    ]
    if image_path and image_path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}:
        command.extend(["--image", str(image_path)])

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=int(os.getenv("HERMES_TIMEOUT_SECONDS", "90")),
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None

    payload = _extract_json(result.stdout) or _extract_json(result.stderr)
    if not payload:
        return None

    return _row_from_payload(payload, reference_file)


def _parse_heuristic(text: str, reference_file: str) -> ReceiptRow:
    payment_date = _find_date(text) or datetime.now().strftime("%Y-%m-%d")
    amount, currency = _find_amount_and_currency(text)
    category = _guess_category(text)
    return ReceiptRow(
        payment_date=payment_date,
        category=category,
        amount=f"{amount:.2f}" if amount is not None else "0.00",
        currency=currency,
        reference_file=reference_file,
    )


def _extract_json(raw: str) -> dict | None:
    if not raw:
        return None
    match = re.search(r"\{[\s\S]*\}", raw)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _row_from_payload(payload: dict, reference_file: str) -> ReceiptRow | None:
    amount_value = payload.get("amount")
    try:
        amount = float(str(amount_value).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        amount = 0.0

    category = str(payload.get("category") or "Other").strip()
    if category not in CATEGORIES:
        category = "Other"

    payment_date = str(payload.get("payment_date") or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", payment_date):
        payment_date = datetime.now().strftime("%Y-%m-%d")

    currency = str(payload.get("currency") or "HKD").strip().upper() or "HKD"

    return ReceiptRow(
        payment_date=payment_date,
        category=category,
        amount=f"{amount:.2f}",
        currency=currency,
        reference_file=reference_file,
    )


def _find_date(text: str) -> str | None:
    patterns = [
        r"\b(\d{4})[/-](\d{1,2})[/-](\d{1,2})\b",
        r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b",
        r"\b(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{4})\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        groups = match.groups()
        if len(groups) == 3 and groups[0].isdigit() and len(groups[0]) == 4:
            year, month, day = groups
        elif len(groups) == 3 and groups[2].isdigit():
            day, month, year = groups
            if not month.isdigit():
                month = _month_to_number(month)
        else:
            continue
        try:
            return datetime(int(year), int(month), int(day)).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _month_to_number(name: str) -> int:
    lookup = {
        "jan": 1,
        "feb": 2,
        "mar": 3,
        "apr": 4,
        "may": 5,
        "jun": 6,
        "jul": 7,
        "aug": 8,
        "sep": 9,
        "oct": 10,
        "nov": 11,
        "dec": 12,
    }
    return lookup[name[:3].lower()]


def _find_amount_and_currency(text: str) -> tuple[float | None, str]:
    currency = "HKD"
    if re.search(r"\bUSD\b|\bUS\$", text, flags=re.IGNORECASE):
        currency = "USD"
    elif re.search(r"\bCNY\b|\bRMB\b|¥", text, flags=re.IGNORECASE):
        currency = "CNY"

    candidates: list[float] = []
    for match in re.finditer(
        r"(?:HK\$|HKD|\$|USD|Total|TOTAL|Amount|AMOUNT|合計|總計|應付)[^\d]{0,12}(\d{1,3}(?:,\d{3})*(?:\.\d{2})?|\d+\.\d{2})",
        text,
        flags=re.IGNORECASE,
    ):
        try:
            candidates.append(float(match.group(1).replace(",", "")))
        except ValueError:
            continue

    if not candidates:
        for match in re.finditer(r"\b(\d{1,3}(?:,\d{3})*\.\d{2})\b", text):
            try:
                candidates.append(float(match.group(1).replace(",", "")))
            except ValueError:
                continue

    if not candidates:
        return None, currency
    return max(candidates), currency


def _guess_category(text: str) -> str:
    lowered = text.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            return category
    return "Other"
