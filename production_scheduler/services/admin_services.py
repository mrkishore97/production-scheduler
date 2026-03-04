import hashlib

import pandas as pd

from production_scheduler.services.customer_services import build_excel_bytes, generate_monthly_print_view
from production_scheduler.status import normalize_status_key, status_to_colors


def df_to_calendar_events(df: pd.DataFrame) -> list[dict]:
    events = []
    for _, row in df.iterrows():
        d = row.get("Scheduled Date", pd.NaT)
        if pd.isna(d):
            continue
        status_raw = str(row.get("Status", ""))
        key = normalize_status_key(status_raw)
        colors = status_to_colors(key)

        title = (
            f"WO {row.get('WO', '')} | {row.get('Customer Name', '')}\n"
            f"{row.get('Model Description', '')}"
        )
        events.append(
            {
                "id": str(row.name),
                "title": title,
                "start": str(d),
                "allDay": True,
                "backgroundColor": colors["bg"],
                "borderColor": colors["border"],
                "textColor": colors["text"],
                "extendedProps": {"status": status_raw},
            }
        )
    return events


def uploaded_file_signature(uploaded_file) -> str:
    if uploaded_file is None:
        return ""
    return hashlib.sha256(uploaded_file.getvalue()).hexdigest()
