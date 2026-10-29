"""Synthetic order-book data for tests and manual testing.

Run as a script to write an Excel file you can upload in the admin app:

    python tests/sample_data.py --rows 1500 --out sample_order_book.xlsx
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta

CUSTOMERS = ["Acme Corp", "Beta Industries", "Trans East Trailers Moncton", "Northwind Haulage"]
STATUSES = ["Open", "In Progress", "Completed", "On Hold", "Cancelled"]
MODELS = ["53ft Dry Van", "48ft Flatbed", "Reefer 53", "Lowboy 3-axle"]


def month_day(day: int, ref: date | None = None) -> date:
    """Day ``day`` of the month containing ``ref`` (default: today)."""
    ref = ref or date.today()
    return ref.replace(day=1) + timedelta(days=day - 1)


def order(wo: str, scheduled: date | None, customer: str = "Acme Corp", status: str = "Open", **extra) -> dict:
    """One order_book row in database (snake_case) format."""
    row = {
        "wo": wo,
        "quote": f"Q-{wo}",
        "po_number": f"PO-{wo}",
        "status": status,
        "customer_name": customer,
        "model_description": "53ft Dry Van",
        "scheduled_date": scheduled.isoformat() if scheduled else None,
        "completion_date": None,
        "price": 1000.0,
        "uploaded_name": "test.xlsx",
    }
    row.update(extra)
    return row


def bulk_orders(count: int, start: date | None = None, duplicates: int = 0, blank_wo: int = 0) -> list[dict]:
    """``count`` orders spread over ~6 months, plus optional duplicate-WO and blank-WO rows."""
    start = start or month_day(1)
    rows = []
    for i in range(count):
        rows.append(
            order(
                wo=str(100000 + i),
                scheduled=start + timedelta(days=i % 180),
                customer=CUSTOMERS[i % len(CUSTOMERS)],
                status=STATUSES[i % len(STATUSES)],
                model_description=MODELS[i % len(MODELS)],
                price=1000.0 + i,
            )
        )
    for i in range(duplicates):
        rows.append(order(wo=str(100000 + i), scheduled=start + timedelta(days=(i + 7) % 180), customer="Duplicate Co"))
    for i in range(blank_wo):
        rows.append(order(wo="", scheduled=None, customer=f"No WO Customer {i}"))
    return rows


def to_upload_frame(rows: list[dict]):
    """Convert database rows into the spreadsheet layout the admin upload expects."""
    import pandas as pd

    df = pd.DataFrame(rows).rename(
        columns={
            "wo": "WO", "quote": "Quote", "po_number": "PO Number", "status": "Status",
            "customer_name": "Customer Name", "model_description": "Model Description",
            "scheduled_date": "Scheduled Date", "completion_date": "Completion Date", "price": "Price",
        }
    )
    return df.drop(columns=[c for c in ["uploaded_name", "id"] if c in df.columns])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rows", type=int, default=1500)
    parser.add_argument("--duplicates", type=int, default=5)
    parser.add_argument("--blank-wo", type=int, default=3)
    parser.add_argument("--out", default="sample_order_book.xlsx")
    args = parser.parse_args()
    frame = to_upload_frame(bulk_orders(args.rows, duplicates=args.duplicates, blank_wo=args.blank_wo))
    frame.to_excel(args.out, index=False)
    print(f"Wrote {len(frame)} rows to {args.out}")
