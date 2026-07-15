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


DEFAULT_CATEGORY = "Misc."

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
    "Software & Subscriptions",
    DEFAULT_CATEGORY,
]

CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "Food & Dining": ("restaurant", "cafe", "coffee", "food", "餐", "飯", "茶餐", "麥當", "starbucks"),
    "Transport": ("taxi", "uber", "mtr", "octopus", "港鐵", "的士", "油站", "parking", "停車"),
    "Office Supplies": ("stationery", "office", "文具", "打印", "print"),
    "Utilities": ("electric", "water", "gas", "電力", "水費", "煤氣", "clp", "hk electric"),
    "Entertainment": ("cinema", "netflix", "spotify", "game", "電影", "娛樂"),
    "Shopping": ("mall", "百貨", "超市", "wellcome", "parknshop", "supermarket", "department store"),
    "Medical": ("clinic", "hospital", "pharmacy", "診所", "醫", "藥房"),
    "Travel": ("hotel", "airline", "flight", "booking", "酒店", "機票", "旅"),
    "Professional Services": ("consult", "legal", "account", "會計", "法律", "顧問"),
    "Software & Subscriptions": ("notion", "hostinger", "subscription", "saas", "software", "cloud", "github", "openai", "domain"),
}

TOTAL_LABEL_PATTERN = re.compile(
    r"(?:^|\b)(?:total\s+due|amount\s+due|total|grand\s*total|balance\s+due|subtotal\s*total|"
    r"payment\s+amount|應付|合計|总计|合计|總金額|總計|總數|總額|實付|应付)(?:\s*amount)?",
    re.IGNORECASE,
)

AMOUNT_PATTERN = re.compile(
    r"(?:HK\$|US\$|USD|CNY|RMB|JPY|¥|\$)?\s*(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?|\d+\.\d{1,2})",
    re.IGNORECASE,
)

US_STATES = (
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN", "IA", "KS", "KY",
    "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND",
    "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC",
)

US_STATE_NAMES: dict[str, str] = {
    "AL": "Alabama",
    "AK": "Alaska",
    "AZ": "Arizona",
    "AR": "Arkansas",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DE": "Delaware",
    "FL": "Florida",
    "GA": "Georgia",
    "HI": "Hawaii",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "IA": "Iowa",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "ME": "Maine",
    "MD": "Maryland",
    "MA": "Massachusetts",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MS": "Mississippi",
    "MO": "Missouri",
    "MT": "Montana",
    "NE": "Nebraska",
    "NV": "Nevada",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NY": "New York",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VT": "Vermont",
    "VA": "Virginia",
    "WA": "Washington",
    "WV": "West Virginia",
    "WI": "Wisconsin",
    "WY": "Wyoming",
    "DC": "District of Columbia",
}

_US_STATE_FULL_NAMES = sorted(set(US_STATE_NAMES.values()), key=len, reverse=True)
_US_STATE_TOKENS = "|".join(re.escape(name) for name in _US_STATE_FULL_NAMES)
_US_STATE_ABBR = "|".join(US_STATES)

_US_CITY_STATE_PATTERN = re.compile(
    rf"\b[A-Za-z][A-Za-z\s.'-]{{1,40}},\s*(?:{_US_STATE_TOKENS}|{_US_STATE_ABBR})\b",
    re.IGNORECASE,
)
_US_CITY_STATE_PAREN_PATTERN = re.compile(
    rf"\(\s*[A-Za-z][A-Za-z\s.'-]{{1,40}},\s*(?:{_US_STATE_TOKENS}|{_US_STATE_ABBR})\s*\)",
    re.IGNORECASE,
)
_US_STATE_ZIP_PATTERN = re.compile(
    rf"\b(?:{_US_STATE_ABBR})\b\s+\d{{5}}(?:-\d{{4}})?\b",
    re.IGNORECASE,
)


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
    text = _sanitize_text(text)
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
        "Extract accounting fields from this receipt OCR text.\n"
        "Return ONLY one JSON object with keys: payment_date, category, amount, currency.\n\n"
        "Rules:\n"
        "- payment_date must be YYYY-MM-DD.\n"
        "- category: infer the expense category with AI. If unsure, use Misc.\n"
        "- amount: use the final Total Due / 總金額 / 總數 / 總計 / 合計 value on the same row or nearest total line. "
        "For Notion and similar invoices, prefer Total Due over plain Total. "
        "Do not use subtotal, tax-only, or change lines unless no total exists.\n"
        "- currency: infer from merchant address/country, not from a single $ symbol.\n"
        "  US SaaS merchants (Notion, Stripe, OpenAI, GitHub, etc.) bill in USD even if the customer billing address is Hong Kong.\n"
        "  Hong Kong merchant addresses (銅鑼灣, 柯士道, 香港, Kowloon, etc.) => HKD.\n"
        "  Mainland China addresses => CNY.\n"
        "  Japan addresses => JPY.\n"
        "  United States addresses => USD: United States/USA, city + state (San Francisco, California / San Francisco, CA), "
        "state + ZIP (CA 94105), or US street address with Inc./LLC.\n"
        "  Do not hardcode one city; use country/region cues.\n"
        f"- reference context file: {reference_file}\n\n"
        f"OCR:\n{text[:6000]}"
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
            env={**os.environ},
        )
    except (subprocess.TimeoutExpired, OSError):
        return None

    payload = _extract_json(result.stdout) or _extract_json(result.stderr)
    if not payload:
        return None

    return _row_from_payload(payload, reference_file, text)


def _parse_heuristic(text: str, reference_file: str) -> ReceiptRow:
    payment_date = _find_date(text) or datetime.now().strftime("%Y-%m-%d")
    amount = _find_total_amount(text)
    currency = _infer_currency(text, reference_file)
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


def _row_from_payload(payload: dict, reference_file: str, source_text: str = "") -> ReceiptRow | None:
    amount_value = payload.get("amount")
    try:
        amount = float(str(amount_value).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        amount = _find_total_amount(source_text) or 0.0

    heuristic_amount = _find_total_amount(source_text)
    if heuristic_amount is not None and _has_priority_total_label(source_text):
        amount = heuristic_amount

    category = str(payload.get("category") or DEFAULT_CATEGORY).strip()
    if category.lower() in {"other", "others", "misc", "miscellaneous"}:
        category = DEFAULT_CATEGORY
    elif category not in CATEGORIES:
        category = DEFAULT_CATEGORY

    payment_date = str(payload.get("payment_date") or "").strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", payment_date):
        year, month, day = payment_date.split("-")
        fixed_year = _normalize_ocr_year(int(year))
        if fixed_year != int(year):
            payment_date = f"{fixed_year:04d}-{month}-{day}"
    else:
        payment_date = _find_date(source_text) or datetime.now().strftime("%Y-%m-%d")

    currency = _resolve_currency(str(payload.get("currency") or ""), source_text, reference_file)

    return ReceiptRow(
        payment_date=payment_date,
        category=category,
        amount=f"{amount:.2f}",
        currency=currency,
        reference_file=reference_file,
    )


def _find_date(text: str) -> str | None:
    prioritized_patterns = [
        (
            r"Invoice Issued\s*#\s*(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{1,2})\s*,?\s*(\d{4})",
            "mdy",
        ),
        (
            r"Invoice Date\s*#\s*(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{1,2})\s*,?\s*(\d{4})",
            "mdy",
        ),
        (
            r"Invoice Issued\s*#?\s*(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s*,?\s*(\d{4})",
            "dmy",
        ),
        (
            r"Invoice Date\s*#?\s*(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s*,?\s*(\d{4})",
            "dmy",
        ),
    ]
    for pattern, mode in prioritized_patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        if mode == "mdy":
            month, day, year = match.groups()
        else:
            day, month, year = match.groups()
        try:
            return datetime(_normalize_ocr_year(int(year)), _month_to_number(str(month)), int(day)).strftime("%Y-%m-%d")
        except ValueError:
            continue

    patterns = [
        r"\b(\d{4})[/-](\d{1,2})[/-](\d{1,2})\b",
        r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b",
        r"\b(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s*,?\s*(\d{4})\b",
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
            if not str(month).isdigit():
                month = _month_to_number(str(month))
        else:
            continue
        try:
            return datetime(_normalize_ocr_year(int(year)), int(month), int(day)).strftime("%Y-%m-%d")
        except ValueError:
            continue

    slash_date = re.search(r"\b(\d{4})\s*/\s*(\d{1,2})\s*/\s*(\d{1,2})\b", text)
    if slash_date:
        year, month, day = slash_date.groups()
        try:
            return datetime(_normalize_ocr_year(int(year)), int(month), int(day)).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return None


def _normalize_ocr_year(year: int) -> int:
    if 2000 <= year <= 2100:
        return year
    if year > 2100:
        leading_two = int("2" + str(year)[1:])
        if 2000 <= leading_two <= 2100:
            return leading_two
        shifted = year - 7000
        if 2000 <= shifted <= 2100:
            return shifted
    return year


def _sanitize_text(text: str) -> str:
    return text.replace("\x00", "")


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


def _has_priority_total_label(text: str) -> bool:
    return bool(
        re.search(r"總金額|total\s+due|amount\s+due", text, re.IGNORECASE)
    )


def _find_total_amount(text: str) -> float | None:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    best_score = -1
    best_amount: float | None = None

    for line in lines:
        score = _score_total_line(line)
        if score is None:
            continue
        amounts = _primary_amounts_on_total_line(line)
        if not amounts:
            continue
        amount = amounts[0]
        if amount <= 0 and score < 85:
            continue
        if score > best_score or (score == best_score and (best_amount is None or amount > best_amount)):
            best_score = score
            best_amount = amount

    if best_amount is not None:
        return best_amount

    fallback: list[float] = []
    for line in lines:
        if re.search(r"tax|vat|gst|小計|subtotal|change|找贖|找零|amount due", line, re.IGNORECASE):
            continue
        fallback.extend(_primary_amounts_on_total_line(line))
    return max(fallback) if fallback else None


def _score_total_line(line: str) -> int | None:
    lowered = line.lower()
    if re.search(r"總金額", line):
        return 100

    if re.search(r"\btotal\s+due\b", lowered):
        amounts = _primary_amounts_on_total_line(line)
        if amounts and max(amounts) <= 0:
            return None
        return 98

    if re.search(r"\bamount due\b", lowered):
        amounts = _primary_amounts_on_total_line(line)
        if amounts and max(amounts) <= 0:
            return None
        return 95

    if re.search(r"\binvoice amount\b", lowered):
        return 100

    if re.match(r"^total\s+\$", line, re.IGNORECASE):
        return 85

    if re.match(r"^total\b", line, re.IGNORECASE) and "excl" not in lowered and "due" not in lowered:
        return 70

    if re.search(r"\btotal excl\b", lowered):
        return 60

    if TOTAL_LABEL_PATTERN.search(line):
        return 40

    return None


def _primary_amounts_on_total_line(line: str) -> list[float]:
    without_fx = re.sub(r"\([A-Z]{3}\s+[\d,.]+\)", "", line, flags=re.IGNORECASE)
    dollar_amounts = re.findall(
        r"\$\s*(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})|\d+\.\d{1,2})",
        without_fx,
        flags=re.IGNORECASE,
    )
    if dollar_amounts:
        return [float(value.replace(",", "")) for value in dollar_amounts]

    values = _amounts_on_line(without_fx)
    if values:
        return values
    return []


def _amounts_on_line(line: str) -> list[float]:
    values: list[float] = []
    for match in AMOUNT_PATTERN.finditer(line):
        try:
            values.append(float(match.group(1).replace(",", "")))
        except ValueError:
            continue
    return values


def _resolve_currency(payload_currency: str, source_text: str, reference_file: str) -> str:
    inferred = _infer_currency(source_text, reference_file)
    override = _strong_currency_signal(source_text, reference_file)
    if override:
        return override

    if _has_regional_address_cue(source_text, reference_file):
        return inferred

    normalized = payload_currency.strip().upper()
    if normalized in {"HKD", "USD", "CNY", "JPY", "EUR", "GBP", "SGD", "TWD"}:
        return normalized
    return inferred


def _has_regional_address_cue(text: str, reference_file: str = "") -> bool:
    if _explicit_currency_code(text):
        return True
    if _looks_like_hong_kong(text):
        return True
    if _looks_like_united_states(text):
        return True
    if _looks_like_us_merchant(text):
        return True
    if _looks_like_china(text):
        return True
    if _looks_like_japan(text):
        return True
    if re.search(r"\bSG\b|Singapore|新加坡", text, re.IGNORECASE):
        return True
    if re.search(r"\bTW\b|Taiwan|台灣|臺灣", text, re.IGNORECASE):
        return True
    if re.search(r"\bUK\b|United Kingdom|London\s+[A-Z]{1,2}\d", text, re.IGNORECASE):
        return True
    if re.search(r"\bEUR\b|Germany|France|Italy|Spain|Netherlands", text, re.IGNORECASE):
        return True
    return _infer_currency_from_filename(reference_file) is not None


def _infer_currency(text: str, reference_file: str = "") -> str:
    return _infer_currency_from_address(text, reference_file)


def _strong_currency_signal(text: str, reference_file: str = "") -> str | None:
    explicit = _explicit_currency_code(text)
    if explicit:
        return explicit

    filename_currency = _infer_currency_from_filename(reference_file)
    if filename_currency:
        return filename_currency

    if _looks_like_us_merchant(text):
        return "USD"

    return None


def _infer_currency_from_address(text: str, reference_file: str = "") -> str:
    strong = _strong_currency_signal(text, reference_file)
    if strong:
        return strong

    if _looks_like_united_states(text):
        return "USD"
    if _looks_like_japan(text):
        return "JPY"
    if _looks_like_china(text):
        return "CNY"
    if re.search(r"\bSG\b|Singapore|新加坡", text, re.IGNORECASE):
        return "SGD"
    if re.search(r"\bTW\b|Taiwan|台灣|臺灣", text, re.IGNORECASE):
        return "TWD"
    if re.search(r"\bUK\b|United Kingdom|London\s+[A-Z]{1,2}\d", text, re.IGNORECASE):
        return "GBP"
    if re.search(r"\bEUR\b|Germany|France|Italy|Spain|Netherlands", text, re.IGNORECASE):
        return "EUR"
    if _looks_like_hong_kong(text):
        return "HKD"

    return "HKD"


def _infer_currency_from_filename(reference_file: str) -> str | None:
    lowered = reference_file.lower()
    us_saas_filename_hints = (
        "notion",
        "openai",
        "github",
        "hostinger",
        "stripe",
        "adobe",
        "dropbox",
        "slack",
        "zoom",
    )
    if any(hint in lowered for hint in us_saas_filename_hints):
        return "USD"
    return None


US_MERCHANT_KEYWORDS = (
    "notion labs",
    "notion.so",
    "openai",
    "github",
    "stripe",
    "hostinger",
    "adobe",
    "dropbox",
    "slack",
    "zoom",
    "anthropic",
    "cursor",
    "vercel",
    "cloudflare",
)


def _looks_like_us_merchant(text: str) -> bool:
    lowered = text.lower()
    if any(keyword in lowered for keyword in US_MERCHANT_KEYWORDS):
        return True
    if "notion" in lowered and re.search(r"\binc\.?\b", lowered, re.IGNORECASE):
        return True
    return False


def _explicit_currency_code(text: str) -> str | None:
    invoice_amount = re.search(
        r"Invoice Amount\s*#?\s*\$?[\d,.]+\s*\((USD|HKD|SGD|CNY|JPY|EUR|GBP|TWD)\)",
        text,
        re.IGNORECASE,
    )
    if invoice_amount:
        return invoice_amount.group(1).upper()

    checks = [
        (r"\bHKD\b|HK\$", "HKD"),
        (r"\bUSD\b|US\$", "USD"),
        (r"\bCNY\b|\bRMB\b|人民币|人民幣", "CNY"),
        (r"\bJPY\b|円|￥", "JPY"),
        (r"\bEUR\b|€", "EUR"),
        (r"\bGBP\b|£", "GBP"),
        (r"\bSGD\b", "SGD"),
        (r"\bTWD\b|NT\$", "TWD"),
    ]
    for pattern, code in checks:
        if re.search(pattern, text, re.IGNORECASE):
            return code
    return None


def _looks_like_hong_kong(text: str) -> bool:
    patterns = (
        r"香港",
        r"Hong Kong",
        r"\bHK\b",
        r"九龍",
        r"新界",
        r"銅鑼灣",
        r"尖沙咀",
        r"中環",
        r"旺角",
        r"灣仔",
        r"柯士道",
        r"彌敦道",
        r"軒尼詩道",
        r"號\s*[\(（]?\d+[\)）]?",
        r"Room\s+[A-Z0-9-]+.*Hong Kong",
    )
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def _looks_like_united_states(text: str) -> bool:
    if re.search(r"United States|\bUSA\b|\bU\.S\.A\b|\bU\.S\b", text, re.IGNORECASE):
        return True
    if _US_CITY_STATE_PATTERN.search(text):
        return True
    if _US_CITY_STATE_PAREN_PATTERN.search(text):
        return True
    if _US_STATE_ZIP_PATTERN.search(text):
        return True
    if re.search(
        rf"\b(?:{_US_STATE_ABBR})\b(?:\s+\d{{5}}(?:-\d{{4}})?)?\b",
        text,
        re.IGNORECASE,
    ) and re.search(r"\b(?:Inc\.|LLC|Corp\.|Corporation)\b", text, re.IGNORECASE):
        return True
    if re.search(
        r"\b(?:Inc\.|LLC|Corp\.|Corporation|Company)\b",
        text,
        re.IGNORECASE,
    ) and re.search(r"\b\d+\s+[A-Za-z0-9.\s]+(?:St|Street|Ave|Avenue|Road|Rd|Blvd|Drive|Dr)\b", text):
        return True
    return False


def _looks_like_china(text: str) -> bool:
    patterns = (
        r"中国",
        r"中國",
        r"人民币",
        r"人民幣",
        r"北京市",
        r"上海市",
        r"深圳市",
        r"广州市",
        r"广东省",
        r"浙江省",
    )
    return any(re.search(pattern, text) for pattern in patterns)


def _looks_like_japan(text: str) -> bool:
    patterns = (
        r"日本",
        r"東京都",
        r"大阪府",
        r"京都府",
        r"円",
        r"消費税",
    )
    return any(re.search(pattern, text) for pattern in patterns)


def _guess_category(text: str) -> str:
    lowered = text.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            return category
    return DEFAULT_CATEGORY
