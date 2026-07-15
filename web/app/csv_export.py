"""CSV export helpers."""

from __future__ import annotations

import csv
import io
from typing import Iterable

from .agent import ReceiptRow

CSV_HEADERS = [
    "Payment Date",
    "Category",
    "Amount",
    "Currency (HKD)",
    "Reference File",
]


def rows_to_csv(rows: Iterable[ReceiptRow]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(CSV_HEADERS)
    for row in rows:
        writer.writerow(
            [
                row.payment_date,
                row.category,
                row.amount,
                row.currency,
                row.reference_file,
            ]
        )
    return buffer.getvalue()
