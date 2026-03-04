from calendar import monthrange
from datetime import date
import io

import pandas as pd

from production_scheduler.status import normalize_status_key, status_to_colors


def is_customer_order(row_customer: str, my_customers: list[str]) -> bool:
    return str(row_customer).strip().lower() in {c.strip().lower() for c in my_customers}


def df_to_calendar_events(df: pd.DataFrame, my_customers: list[str]) -> list[dict]:
    events = []
    for _, row in df.iterrows():
        d = row.get("Scheduled Date", pd.NaT)
        if pd.isna(d):
            continue

        mine = is_customer_order(row.get("Customer Name", ""), my_customers)
        status_raw = str(row.get("Status", ""))
        key = normalize_status_key(status_raw)
        colors = status_to_colors(key)

        if mine:
            title = (
                f"WO {row.get('WO', '')}  |  {row.get('Model Description', '')}\n"
                f"Status: {status_raw or 'Open'}"
            )
            events.append(
                {
                    "title": title,
                    "start": str(d),
                    "allDay": True,
                    "backgroundColor": colors["bg"],
                    "borderColor": colors["border"],
                    "textColor": colors["text"],
                }
            )
        else:
            events.append(
                {
                    "title": "SOLD",
                    "start": str(d),
                    "allDay": True,
                    "backgroundColor": "#E5E7EB",
                    "borderColor": "#9CA3AF",
                    "textColor": "#374151",
                }
            )
    return events


def build_excel_bytes(df: pd.DataFrame) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Orders", index=False)
    return output.getvalue()


def generate_monthly_print_view(df: pd.DataFrame, my_customers: list[str], month: int, year: int) -> str:
    days_in_month = monthrange(year, month)[1]
    first_day = date(year, month, 1)
    start_weekday = (first_day.weekday() + 1) % 7

    by_date: dict[date, list[dict]] = {}
    for _, row in df.iterrows():
        d = row.get("Scheduled Date", pd.NaT)
        if pd.isna(d) or d.month != month or d.year != year:
            continue

        mine = is_customer_order(row.get("Customer Name", ""), my_customers)
        if d not in by_date:
            by_date[d] = []

        if mine:
            by_date[d].append(
                {
                    "label": f"WO {row.get('WO', '')} • {row.get('Model Description', '')}",
                    "class": "mine",
                }
            )
        else:
            by_date[d].append({"label": "SOLD", "class": "sold"})

    cells = []
    for _ in range(start_weekday):
        cells.append('<div class="cell empty"></div>')

    for day in range(1, days_in_month + 1):
        this_date = date(year, month, day)
        entries = by_date.get(this_date, [])
        entry_html = "".join([
            f'<div class="pill {e["class"]}">{e["label"]}</div>' for e in entries
        ])
        cells.append(
            f'<div class="cell"><div class="day">{day}</div><div class="entries">{entry_html}</div></div>'
        )

    month_name = first_day.strftime("%B")
    return f"""
    <html>
    <head>
      <meta charset='utf-8'/>
      <title>{month_name} {year} - Print</title>
      <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; color: #111; }}
        h1 {{ margin: 0 0 8px 0; font-size: 22px; }}
        .legend {{ margin-bottom: 12px; font-size: 12px; }}
        .dot {{ display:inline-block; width:10px; height:10px; border-radius:50%; margin-right:6px; }}
        .mine-dot {{ background:#3B82F6; }} .sold-dot {{ background:#9CA3AF; }}
        .grid {{ display:grid; grid-template-columns: repeat(7, 1fr); gap:6px; }}
        .head {{ font-weight:700; text-align:center; padding:6px 0; border-bottom:1px solid #ccc; }}
        .cell {{ min-height:120px; border:1px solid #ddd; padding:6px; }}
        .cell.empty {{ background:#fafafa; border-style:dashed; }}
        .day {{ font-weight:700; margin-bottom:6px; }}
        .pill {{ font-size:11px; padding:4px 6px; border-radius:999px; margin-bottom:4px; display:inline-block; }}
        .pill.mine {{ background:#DBEAFE; color:#1E40AF; border:1px solid #93C5FD; }}
        .pill.sold {{ background:#E5E7EB; color:#374151; border:1px solid #9CA3AF; }}
        @media print {{ body {{ margin: 8mm; }} }}
      </style>
    </head>
    <body>
      <h1>{month_name} {year} Schedule</h1>
      <div class="legend"><span class="dot mine-dot"></span>Your orders &nbsp;&nbsp; <span class="dot sold-dot"></span>SOLD</div>
      <div class="grid">
        <div class="head">Sun</div><div class="head">Mon</div><div class="head">Tue</div><div class="head">Wed</div><div class="head">Thu</div><div class="head">Fri</div><div class="head">Sat</div>
        {''.join(cells)}
      </div>
      <script>window.onload = () => window.print();</script>
    </body>
    </html>
    """
