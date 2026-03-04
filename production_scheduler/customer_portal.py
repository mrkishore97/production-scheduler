#production_scheduler/customer_portal.py
import io
from calendar import monthrange
from datetime import date, datetime

import pandas as pd
import streamlit as st
from supabase import Client, create_client

from production_scheduler.config import REQUIRED_COLS, SUPABASE_TABLE
from production_scheduler.status import SOLD_COLORS, normalize_status_key, status_to_colors


@st.cache_resource
def get_supabase() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])


def get_data_version() -> str:
    """Cheap single-row fetch — never cached, runs on every page load."""
    supabase = get_supabase()
    try:
        resp = (
            supabase.table("app_meta")
            .select("value")
            .eq("key", "data_version")
            .execute()
        )
        if resp.data:
            return resp.data[0]["value"]
    except Exception:
        pass
    return "0"


@st.cache_data(ttl=300)
def load_all_data(data_version: str = "0") -> pd.DataFrame:
    supabase = get_supabase()
    response = supabase.table(SUPABASE_TABLE).select("*").execute()
    rows = response.data

    if not rows:
        return pd.DataFrame(columns=REQUIRED_COLS)

    df = pd.DataFrame(rows)
    df = df.rename(columns={
        "wo": "WO", "quote": "Quote", "po_number": "PO Number",
        "status": "Status", "customer_name": "Customer Name",
        "model_description": "Model Description",
        "scheduled_date": "Scheduled Date", "completion_date": "Completion Date", "price": "Price",
    })
    df = df.drop(columns=[c for c in ["uploaded_name", "id"] if c in df.columns], errors="ignore")
    df["Scheduled Date"] = df["Scheduled Date"].apply(parse_date)
    df["Completion Date"] = df["Completion Date"].apply(parse_date)
    df["Price"] = df["Price"].apply(lambda x: float(x) if x is not None else pd.NA)
    for c in ["Quote", "PO Number", "Status", "Customer Name", "Model Description"]:
        df[c] = df[c].fillna("").astype(str)

    present = [c for c in REQUIRED_COLS if c in df.columns]
    return df[present]


def parse_date(x):
    if x is None or str(x).strip() in ("", "None", "NaT"):
        return pd.NaT
    try:
        if pd.isna(x):
            return pd.NaT
    except Exception:
        pass
    dt = pd.to_datetime(x, errors="coerce")
    return pd.NaT if pd.isna(dt) else dt.date()


def is_mine(cust_col_value: str, my_customers: list[str]) -> bool:
    val = cust_col_value.strip().lower()
    return any(val == c.strip().lower() for c in my_customers)


def df_to_calendar_events(df: pd.DataFrame, my_customers: list[str]):
    events = []
    for _, r in df.iterrows():
        wo = str(r.get("WO", "")).strip()
        d = r.get("Scheduled Date", pd.NaT)
        if not wo or pd.isna(d):
            continue

        cust = str(r.get("Customer Name", "")).strip()
        model = str(r.get("Model Description", "")).strip()
        status = str(r.get("Status", "")).strip()

        if is_mine(cust, my_customers):
            title = " | ".join(filter(None, [wo, cust]))
            if model:
                title += f" — {model}"
            events.append({
                "id": wo, "title": title,
                "start": d.isoformat(), "allDay": True,
                **status_to_colors(status),
                "extendedProps": {
                    "wo": wo, "customer_name": cust,
                    "model_description": model, "status": status,
                },
            })
        else:
            events.append({
                "id": f"sold_{wo}",
                "title": "● SOLD",
                "start": d.isoformat(), "allDay": True,
                **SOLD_COLORS,
                "extendedProps": {"sold": True},
            })
    return events


def build_excel_bytes(df: pd.DataFrame) -> bytes:
    out = df.copy()
    out["Scheduled Date"] = pd.to_datetime(out["Scheduled Date"], errors="coerce")
    out["Completion Date"] = pd.to_datetime(out["Completion Date"], errors="coerce")
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        out.to_excel(writer, index=False, sheet_name="My Orders")
        ws = writer.sheets["My Orders"]
        col_map = {cell.value: cell.column for cell in ws[1]}
        dc = col_map.get("Scheduled Date")
        cc = col_map.get("Completion Date")
        pc = col_map.get("Price")
        if dc:
            for r in range(2, ws.max_row + 1):
                ws.cell(row=r, column=dc).number_format = "yyyy-mm-dd"
        if cc:
            for r in range(2, ws.max_row + 1):
                ws.cell(row=r, column=cc).number_format = "yyyy-mm-dd"
        if pc:
            for r in range(2, ws.max_row + 1):
                ws.cell(row=r, column=pc).number_format = '"$"#,##0.00'
        for col in range(1, ws.max_column + 1):
            max_len = max(
                (len(str(ws.cell(row=r, column=col).value or "")) for r in range(1, ws.max_row + 1)),
                default=10,
            )
            ws.column_dimensions[ws.cell(row=1, column=col).column_letter].width = min(max(10, max_len + 2), 60)
    return buf.getvalue()


def generate_monthly_print_view(df: pd.DataFrame, month: int, year: int, my_customers: list[str]) -> str:
    month_label = datetime(year, month, 1).strftime("%B %Y")
    customers_label = ", ".join(my_customers)

    df_month = df[
        (pd.to_datetime(df["Scheduled Date"], errors="coerce").dt.month == month)
        & (pd.to_datetime(df["Scheduled Date"], errors="coerce").dt.year == year)
    ].copy()

    my_events: dict[str, list] = {}
    sold_dates: set[str] = set()

    for _, row in df_month.iterrows():
        d = row["Scheduled Date"]
        if pd.isna(d):
            continue
        dk = d.isoformat()
        cust = str(row.get("Customer Name", "")).strip()
        if is_mine(cust, my_customers):
            my_events.setdefault(dk, []).append({
                "wo": str(row.get("WO", "")).strip(),
                "cust": cust,
                "model": str(row.get("Model Description", "")).strip(),
                "status": str(row.get("Status", "")).strip(),
            })
        else:
            sold_dates.add(dk)

    fdw = datetime(year, month, 1).weekday()
    num_days = monthrange(year, month)[1]
    weeks_need = ((num_days + fdw - 1) // 7) + 1

    html = f"""<!DOCTYPE html>
<html>
<head>
<title>{month_label} — {customers_label}</title>
<style>
@media print {{ @page {{ size: letter landscape; margin: 0.4in; }} body {{ margin:0; }} }}
* {{ -webkit-print-color-adjust:exact !important; print-color-adjust:exact !important; }}
body {{ font-family:Arial,sans-serif; padding:10px; background:white; max-width:10.2in; margin:0 auto; }}
.header {{ text-align:center; margin-bottom:10px; }}
.header h2 {{ margin:0; font-size:16px; color:#1e3a5f; font-weight:700; }}
.header .sub {{ font-size:12px; color:#64748b; margin-top:4px; }}
table {{ width:100%; border-collapse:collapse; table-layout:fixed; }}
th {{ background:#2563eb; color:white; padding:6px; text-align:center;
      border:1px solid #999; font-size:11px; width:14.28%; }}
td {{ border:1px solid #ccc; padding:5px; vertical-align:top; width:14.28%;
      height:110px; background:white; }}
td.sold {{ background:#f8fafc; }}
.dn {{ font-weight:bold; font-size:12px; color:#333; margin-bottom:4px; }}
.ev {{ margin-bottom:4px; padding:4px; border-radius:3px; font-size:9px; line-height:1.3; }}
.s-open       {{ background:#dbeafe; border-left:3px solid #2563eb; }}
.s-inprogress {{ background:#fed7aa; border-left:3px solid #d97706; }}
.s-completed  {{ background:#dcfce7; border-left:3px solid #16a34a; }}
.s-onhold     {{ background:#e5e7eb; border-left:3px solid #6b7280; }}
.s-cancelled  {{ background:#fee2e2; border-left:3px solid #dc2626; }}
.s-default    {{ background:#ccfbf1; border-left:3px solid #0f766e; }}
.wo  {{ font-weight:bold; font-size:10px; color:#000; }}
.cu  {{ font-size:9.5px; color:#1f2937; font-weight:500; }}
.md  {{ font-size:9px; color:#374151; }}
.sold-badge {{ text-align:center; margin-top:8px; padding:5px; background:#cbd5e1;
               color:#475569; border-radius:3px; font-weight:bold; font-size:10px; }}
.legend {{ margin-top:12px; padding:8px 12px; background:#f9fafb;
           border:1px solid #ddd; border-radius:4px; }}
.lt {{ font-weight:bold; font-size:11px; margin-bottom:6px; }}
.li {{ display:inline-flex; align-items:center; gap:5px; font-size:10px; margin-right:12px; }}
.lc {{ width:14px; height:14px; border-radius:2px; display:inline-block; }}
</style>
</head>
<body>
<div class="header">
  <h2>{month_label}</h2>
  <div class="sub">Production Schedule — <strong>{customers_label}</strong></div>
</div>
<table>
<thead><tr>
  <th>Monday</th><th>Tuesday</th><th>Wednesday</th>
  <th>Thursday</th><th>Friday</th><th>Saturday</th><th>Sunday</th>
</tr></thead>
<tbody>"""

    cur = 1
    for week in range(weeks_need):
        html += "<tr>"
        for dow in range(7):
            if week == 0 and dow < fdw:
                html += "<td></td>"
            elif cur > num_days:
                html += "<td></td>"
            else:
                dk = date(year, month, cur).isoformat()
                is_sold = (dk in sold_dates) and (dk not in my_events)
                td_cls = ' class="sold"' if is_sold else ""
                html += f'<td{td_cls}><div class="dn">{cur}</div>'
                if dk in my_events:
                    for ev in my_events[dk]:
                        sk = normalize_status_key(ev["status"]).replace(" ", "")
                        html += f'<div class="ev s-{sk}"><div class="wo">WO: {ev["wo"]}</div>'
                        if ev["cust"]:
                            html += f'<div class="cu">{ev["cust"]}</div>'
                        if ev["model"]:
                            html += f'<div class="md">{ev["model"]}</div>'
                        html += "</div>"
                elif is_sold:
                    html += '<div class="sold-badge">SOLD</div>'
                html += "</td>"
                cur += 1
        html += "</tr>"

    html += """
</tbody></table>
<div class="legend"><div class="lt">Legend:</div>
  <div class="li"><span class="lc" style="background:#2563eb"></span> Open</div>
  <div class="li"><span class="lc" style="background:#d97706"></span> In Progress</div>
  <div class="li"><span class="lc" style="background:#16a34a"></span> Completed</div>
  <div class="li"><span class="lc" style="background:#6b7280"></span> On Hold</div>
  <div class="li"><span class="lc" style="background:#dc2626"></span> Cancelled</div>
  <div class="li"><span class="lc" style="background:#cbd5e1"></span> SOLD — Date Unavailable</div>
</div>
</body></html>"""

    return html
