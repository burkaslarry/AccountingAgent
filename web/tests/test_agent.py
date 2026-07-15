import os
import unittest

os.environ["ACCOUNTING_AGENT_FORCE_HEURISTIC"] = "1"

from app.agent import _find_date, _find_total_amount, _normalize_ocr_year, _row_from_payload, _sanitize_text, parse_receipt


class AgentParsingTests(unittest.TestCase):
    def test_ocr_year_normalization(self) -> None:
        self.assertEqual(_normalize_ocr_year(9026), 2026)
        self.assertEqual(_normalize_ocr_year(2026), 2026)

    def test_date_from_slash_format_with_ocr_year(self) -> None:
        text = "Shop receipt\n2026/06/06\n總金額 48.0"
        self.assertEqual(_find_date(text.replace("2026", "9026")), "2026-06-06")

    def test_img_1951_style_receipt(self) -> None:
        text = """
        銅鑼灣某店
        2026/06/06
        電話: 911-2345
        小計 45.0
        總金額 48.0
        """
        row = parse_receipt(text, "IMG_1951.png")
        self.assertEqual(row.payment_date, "2026-06-06")
        self.assertEqual(row.amount, "48.00")
        self.assertEqual(row.currency, "HKD")

    def test_notion_total_due_over_total(self) -> None:
        text = """
        Notion Labs, Inc.
        685 Market St, San Francisco, CA 94105 United States
        Invoice Date # Feb 1, 2026
        Subtotal $20.00
        Tax $4.00
        Total $24.00
        Total Due $48.00
        """
        row = parse_receipt(text, "notion-invoice.pdf")
        self.assertEqual(row.amount, "48.00")
        self.assertEqual(row.currency, "USD")

    def test_r7394120_style_receipt(self) -> None:
        text = """
        香港某商戶
        發票編號 R7394120
        日期 2026-03-10
        項目 100.0
        服務費 10.0
        總金額 110.0
        """
        row = parse_receipt(text, "R7394120.pdf")
        self.assertEqual(row.amount, "110.00")
        self.assertEqual(row.currency, "HKD")

    def test_sanitize_null_bytes(self) -> None:
        dirty = "Total Due\x00 $24.00\x00"
        self.assertEqual(_sanitize_text(dirty), "Total Due $24.00")
        row = parse_receipt(dirty, "Receipt-2935-8320.pdf")
        self.assertEqual(row.amount, "24.00")

    def test_find_total_amount_prefers_total_due(self) -> None:
        text = "Total $24.00\nTotal Due $48.00"
        self.assertEqual(_find_total_amount(text), 48.0)

    def test_notion_hermes_hkd_overridden_by_us_address(self) -> None:
        text = """
        Notion Labs, Inc.
        685 Market St, San Francisco, CA 94105 United States
        Total Due $24.00
        """
        payload = {
            "payment_date": "2026-11-05",
            "category": "Professional Services",
            "amount": "24.00",
            "currency": "HKD",
        }
        row = _row_from_payload(payload, "Notion Invoice May 11, 2026.pdf", text)
        self.assertEqual(row.currency, "USD")

    def test_notion_filename_hint_when_ocr_sparse(self) -> None:
        text = "Total Due $24.00"
        row = parse_receipt(text, "Notion Invoice June 11, 2026.pdf")
        self.assertEqual(row.currency, "USD")

    def test_notion_merchant_name_without_address(self) -> None:
        text = """
        Notion Labs, Inc.
        Total Due $24.00
        Invoice Date May 11, 2026
        """
        row = parse_receipt(text, "invoice.pdf")
        self.assertEqual(row.currency, "USD")

    def test_notion_hk_billing_address_still_usd(self) -> None:
        text = """
        Notion Labs, Inc.
        685 Market St, San Francisco, CA 94105 United States
        Bill to:
        香港九龍某地址
        Total Due $24.00
        """
        row = parse_receipt(text, "Notion Invoice May 11, 2026.pdf")
        self.assertEqual(row.currency, "USD")

    def test_notion_hermes_hkd_overridden_by_filename_with_hk_billing(self) -> None:
        text = """
        Notion Labs, Inc.
        香港
        Total Due $24.00
        """
        payload = {
            "payment_date": "2026-11-05",
            "category": "Professional Services",
            "amount": "24.00",
            "currency": "HKD",
        }
        row = _row_from_payload(payload, "Notion Invoice May 11, 2026.pdf", text)
        self.assertEqual(row.currency, "USD")

    def test_stripe_receipt_defaults_to_usd(self) -> None:
        text = """
        Stripe
        Receipt from Notion Labs, Inc.
        Amount paid $24.00
        """
        row = parse_receipt(text, "Receipt-2935-8320.pdf")
        self.assertEqual(row.currency, "USD")

    def test_us_city_full_state_name(self) -> None:
        text = """
        Acme Corp
        123 Main Street
        San Francisco, California
        Total Due $99.00
        """
        row = parse_receipt(text, "invoice.pdf")
        self.assertEqual(row.currency, "USD")

    def test_us_city_state_abbreviation(self) -> None:
        text = """
        Vendor LLC
        Austin, TX
        Total $45.00
        """
        row = parse_receipt(text, "receipt.pdf")
        self.assertEqual(row.currency, "USD")

    def test_us_city_state_in_parentheses(self) -> None:
        text = """
        Payment receipt
        Office (New York, New York)
        Total Due $12.00
        """
        row = parse_receipt(text, "receipt.pdf")
        self.assertEqual(row.currency, "USD")

    def test_us_city_state_overrides_hermes_hkd(self) -> None:
        text = """
        Some Vendor Inc.
        Seattle, Washington
        Total Due $30.00
        """
        payload = {
            "payment_date": "2026-07-01",
            "category": "Misc.",
            "amount": "30.00",
            "currency": "HKD",
        }
        row = _row_from_payload(payload, "vendor-invoice.pdf", text)
        self.assertEqual(row.currency, "USD")


if __name__ == "__main__":
    unittest.main()
