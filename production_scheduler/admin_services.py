"""Business logic used by the admin calendar and table pages."""

from __future__ import annotations

import hashlib
import io
from calendar import monthrange
from datetime import date, datetime

import pandas as pd

from production_scheduler.status import normalize_status_key, status_to_colors


def df_to_calendar_events(df: pd.DataFrame) -> list[dict]:
    """Convert order rows to FullCalendar event dictionaries."""
    events: list[dict] = []
    for _, row in df.iterrows():
        wo = str(row.get("WO", "")).strip()
        scheduled_date = row.get("Scheduled Date", pd.NaT)
        if not wo or pd.isna(scheduled_date):
            continue

        customer = str(row.get("Customer Name", "")).strip()
        model = str(row.get("Model Description", "")).strip()
        status = str(row.get("Status", "")).strip()

        title = " | ".join(part for part in [wo, customer] if part)
        if model:
            title += f" — {model}"

        events.append(
            {
                "id": wo,
                "title": title,
                "start": scheduled_date.isoformat(),
                "allDay": True,
                **status_to_colors(status),
                "extendedProps": {
                    "wo": wo,
                    "customer_name": customer,
                    "model_description": model,
                    "status": status,
                },
            }
        )
    return events


def uploaded_file_signature(file) -> str:
    """Create a stable hash for uploaded file de-duplication checks."""
    return hashlib.sha256(file.getvalue()).hexdigest()


def build_excel_bytes(df: pd.DataFrame) -> bytes:
    """Serialize a DataFrame to XLSX with date and price formatting."""
    export_df = df.copy()
    export_df["Scheduled Date"] = pd.to_datetime(export_df["Scheduled Date"], errors="coerce")
    export_df["Completion Date"] = pd.to_datetime(export_df["Completion Date"], errors="coerce")

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        export_df.to_excel(writer, index=False, sheet_name="Order Book")
        ws = writer.sheets["Order Book"]
        col_map = {cell.value: cell.column for cell in ws[1]}

        for date_column in [col_map.get("Scheduled Date"), col_map.get("Completion Date")]:
            if date_column:
                for row_number in range(2, ws.max_row + 1):
                    ws.cell(row=row_number, column=date_column).number_format = "yyyy-mm-dd"

        price_col = col_map.get("Price")
        if price_col:
            for row_number in range(2, ws.max_row + 1):
                ws.cell(row=row_number, column=price_col).number_format = '"$"#,##0.00'

        for col in range(1, ws.max_column + 1):
            max_len = max((len(str(ws.cell(row=r, column=col).value or "")) for r in range(1, ws.max_row + 1)), default=10)
            ws.column_dimensions[ws.cell(row=1, column=col).column_letter].width = min(max(10, max_len + 2), 60)

    return buffer.getvalue()


def generate_monthly_print_view(df: pd.DataFrame, month: int, year: int) -> str:
    """Generate a printable monthly HTML calendar view."""
    month_name = datetime(year, month, 1).strftime("%B %Y")
    df_month = df[
        (pd.to_datetime(df["Scheduled Date"], errors="coerce").dt.month == month)
        & (pd.to_datetime(df["Scheduled Date"], errors="coerce").dt.year == year)
    ].copy()

    events_by_date: dict[str, list[dict]] = {}
    for _, row in df_month.iterrows():
        scheduled_date = row["Scheduled Date"]
        if pd.isna(scheduled_date):
            continue

        date_key = scheduled_date.isoformat()
        events_by_date.setdefault(date_key, []).append(
            {
                "wo": str(row.get("WO", "")).strip(),
                "customer": str(row.get("Customer Name", "")).strip(),
                "model": str(row.get("Model Description", "")).strip(),
                "status": str(row.get("Status", "")).strip(),
            }
        )

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>{month_name}</title>
        <style>
            @media print {{
                @page {{ 
                    size: letter landscape;
                    margin: 0.4in; 
                }}
                body {{ margin: 0; }}
                .no-print {{ display: none; }}
            }}
            
            * {{
                -webkit-print-color-adjust: exact !important;
                print-color-adjust: exact !important;
                color-adjust: exact !important;
            }}
            
            body {{
                font-family: Arial, sans-serif;
                padding: 10px;
                background: white;
                max-width: 10.2in;
                margin: 0 auto;
            }}
            .header {{ text-align: center; margin-bottom: 10px; }}
            .header h2 {{ margin: 0; font-size: 16px; color: #333; font-weight: 600; }}
            .calendar-table {{ width: 100%; border-collapse: collapse; table-layout: fixed; margin-bottom: 10px; }}
            .calendar-table th {{ background-color: #2563eb; color: white; padding: 6px; text-align: center; border: 1px solid #999; font-size: 11px; width: 14.28%; }}
            .calendar-table td {{ border: 1px solid #999; padding: 5px; vertical-align: top; width: 14.28%; height: 105px; }}
            .date-number {{ font-weight: bold; font-size: 12px; margin-bottom: 4px; color: #333; }}
            .event-item {{ margin-bottom: 5px; padding: 4px; border-radius: 3px; font-size: 9px; line-height: 1.3; }}
            .status-open {{ background-color: #dbeafe; border-left: 3px solid #2563eb; }}
            .status-inprogress {{ background-color: #fed7aa; border-left: 3px solid #d97706; }}
            .status-completed {{ background-color: #dcfce7; border-left: 3px solid #16a34a; }}
            .status-onhold {{ background-color: #e5e7eb; border-left: 3px solid #6b7280; }}
            .status-cancelled {{ background-color: #fee2e2; border-left: 3px solid #dc2626; }}
            .status-default {{ background-color: #ccfbf1; border-left: 3px solid #0f766e; }}
            .event-wo {{ font-weight: bold; color: #000; font-size: 10px; }}
            .event-customer {{ color: #1f2937; font-size: 9.5px; font-weight: 500; }}
            .event-model {{ color: #374151; font-size: 9px; }}
            .legend {{ margin-top: 10px; padding: 10px; background-color: #f9fafb; border: 1px solid #ddd; border-radius: 3px; }}
            .legend-title {{ font-weight: bold; margin-bottom: 8px; font-size: 11px; }}
            .legend-items {{ display: flex; flex-wrap: wrap; gap: 12px; }}
            .legend-item {{ display: flex; align-items: center; gap: 5px; font-size: 10px; }}
            .legend-color {{ width: 16px; height: 16px; border-radius: 2px; }}
        </style>
    </head>
    <body>
        <div class="header"><h2>{month_name}</h2></div>
        <table class="calendar-table"><thead><tr>
            <th>Monday</th><th>Tuesday</th><th>Wednesday</th><th>Thursday</th>
            <th>Friday</th><th>Saturday</th><th>Sunday</th>
        </tr></thead><tbody>
    """

    first_day_weekday = datetime(year, month, 1).weekday()
    num_days = monthrange(year, month)[1]
    current_day = 1
    weeks_needed = ((num_days + first_day_weekday) // 7) + (1 if (num_days + first_day_weekday) % 7 > 0 else 0)

    for week in range(weeks_needed):
        html += "<tr>"
        for day_of_week in range(7):
            if week == 0 and day_of_week < first_day_weekday:
                html += "<td></td>"
            elif current_day > num_days:
                html += "<td></td>"
            else:
                date_str = date(year, month, current_day).isoformat()
                html += f'<td><div class="date-number">{current_day}</div>'
                for event in events_by_date.get(date_str, []):
                    status_class = normalize_status_key(event["status"]).replace(" ", "")
                    html += f'<div class="event-item status-{status_class}">'
                    html += f'<div class="event-wo">WO: {event["wo"]}</div>'
                    if event["customer"]:
                        html += f'<div class="event-customer">{event["customer"]}</div>'
                    if event["model"]:
                        html += f'<div class="event-model">{event["model"]}</div>'
                    html += "</div>"
                html += "</td>"
                current_day += 1
        html += "</tr>"

    html += """
            </tbody></table>
            <div class="legend"><div class="legend-title">Status Legend:</div><div class="legend-items">
                <div class="legend-item"><div class="legend-color" style="background-color: #2563eb;"></div><span>Open</span></div>
                <div class="legend-item"><div class="legend-color" style="background-color: #d97706;"></div><span>In Progress</span></div>
                <div class="legend-item"><div class="legend-color" style="background-color: #16a34a;"></div><span>Completed</span></div>
                <div class="legend-item"><div class="legend-color" style="background-color: #6b7280;"></div><span>On Hold</span></div>
                <div class="legend-item"><div class="legend-color" style="background-color: #dc2626;"></div><span>Cancelled</span></div>
            </div></div>
        <script>/* window.onload = function() {{ window.print(); }} */</script>
    </body></html>
    """
    return html
