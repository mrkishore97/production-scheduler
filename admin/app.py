#admin/app.py

import hashlib
import io
import sys
from datetime import datetime, date
from calendar import monthrange
from pathlib import Path

import pandas as pd
import streamlit as st
from streamlit_calendar import calendar

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from production_scheduler import admin_session, order_book
from production_scheduler.calendar_sync import apply_drag, parse_event_change
from production_scheduler.calendar_ui import ADMIN_CALENDAR_CUSTOM_CSS, build_calendar_options
from production_scheduler.feedback import flash
from production_scheduler.status import normalize_status_key, status_to_colors

# ---------------- Config ----------------
st.set_page_config(page_title="Order Book Calendar", layout="wide")


# ---------------- Helpers ----------------

def df_to_calendar_events(df: pd.DataFrame):
    events = []
    for _, r in df.iterrows():
        wo = str(r.get("WO", "")).strip()
        d = r.get("Scheduled Date", pd.NaT)
        if pd.isna(d):
            continue
        cust  = str(r.get("Customer Name", "")).strip()
        model = str(r.get("Model Description", "")).strip()
        status = str(r.get("Status", "")).strip()

        title = " | ".join([p for p in [wo or "No WO", cust] if p])
        if model:
            title += f" — {model}"

        events.append({
            # The row id, not the WO: WOs can repeat or be blank.
            "id": str(r[order_book.ID]), "title": title,
            "start": d.isoformat(), "allDay": True,
            **status_to_colors(status),
            "extendedProps": {"wo": wo, "customer_name": cust,
                              "model_description": model, "status": status},
        })
    return events




def uploaded_file_signature(file) -> str:
    return hashlib.sha256(file.getvalue()).hexdigest()


def build_excel_bytes(df: pd.DataFrame) -> bytes:
    export_df = df.drop(columns=[order_book.ID], errors="ignore")
    export_df["Scheduled Date"] = pd.to_datetime(export_df["Scheduled Date"], errors="coerce")
    export_df["Completion Date"] = pd.to_datetime(export_df["Completion Date"], errors="coerce")
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        export_df.to_excel(writer, index=False, sheet_name="Order Book")
        ws = writer.sheets["Order Book"]
        col_map = {cell.value: cell.column for cell in ws[1]}
        date_col  = col_map.get("Scheduled Date")
        completion_col = col_map.get("Completion Date")
        price_col = col_map.get("Price")
        if date_col:
            for r in range(2, ws.max_row + 1):
                ws.cell(row=r, column=date_col).number_format = "yyyy-mm-dd"
        if completion_col:
            for r in range(2, ws.max_row + 1):
                ws.cell(row=r, column=completion_col).number_format = "yyyy-mm-dd"
        if price_col:
            for r in range(2, ws.max_row + 1):
                ws.cell(row=r, column=price_col).number_format = '"$"#,##0.00'
        for col in range(1, ws.max_column + 1):
            max_len = max(
                (len(str(ws.cell(row=r, column=col).value or "")) for r in range(1, ws.max_row + 1)),
                default=10,
            )
            ws.column_dimensions[ws.cell(row=1, column=col).column_letter].width = min(max(10, max_len + 2), 60)
    return buf.getvalue()


def generate_monthly_print_view(df: pd.DataFrame, month: int, year: int) -> str:
    """Generate HTML for a printable monthly calendar view."""
    month_name = datetime(year, month, 1).strftime("%B %Y")
    
    # Filter data for the selected month
    df_month = df[
        (pd.to_datetime(df["Scheduled Date"], errors="coerce").dt.month == month) &
        (pd.to_datetime(df["Scheduled Date"], errors="coerce").dt.year == year)
    ].copy()
    
    # Group by date
    events_by_date = {}
    for _, row in df_month.iterrows():
        d = row["Scheduled Date"]
        if pd.isna(d):
            continue
        date_key = d.isoformat()
        if date_key not in events_by_date:
            events_by_date[date_key] = []
        
        wo = str(row.get("WO", "")).strip()
        cust = str(row.get("Customer Name", "")).strip()
        model = str(row.get("Model Description", "")).strip()
        status = str(row.get("Status", "")).strip()
        
        events_by_date[date_key].append({
            "wo": wo,
            "customer": cust,
            "model": model,
            "status": status,
        })
    
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
            
            .header {{
                text-align: center;
                margin-bottom: 10px;
            }}
            
            .header h2 {{
                margin: 0;
                font-size: 16px;
                color: #333;
                font-weight: 600;
            }}
            
            .calendar-table {{
                width: 100%;
                border-collapse: collapse;
                table-layout: fixed;
                margin-bottom: 10px;
            }}
            
            .calendar-table th {{
                background-color: #2563eb;
                color: white;
                padding: 6px;
                text-align: center;
                border: 1px solid #999;
                font-size: 11px;
                width: 14.28%;
            }}
            
            .calendar-table td {{
                border: 1px solid #999;
                padding: 5px;
                vertical-align: top;
                width: 14.28%;
                height: 105px;
            }}
            
            .date-number {{
                font-weight: bold;
                font-size: 12px;
                margin-bottom: 4px;
                color: #333;
            }}
            
            .event-item {{
                margin-bottom: 5px;
                padding: 4px;
                border-radius: 3px;
                font-size: 9px;
                line-height: 1.3;
            }}
            
            .status-open {{ background-color: #dbeafe; border-left: 3px solid #2563eb; }}
            .status-inprogress {{ background-color: #fed7aa; border-left: 3px solid #d97706; }}
            .status-completed {{ background-color: #dcfce7; border-left: 3px solid #16a34a; }}
            .status-onhold {{ background-color: #e5e7eb; border-left: 3px solid #6b7280; }}
            .status-cancelled {{ background-color: #fee2e2; border-left: 3px solid #dc2626; }}
            .status-default {{ background-color: #ccfbf1; border-left: 3px solid #0f766e; }}
            
            .event-wo {{
                font-weight: bold;
                color: #000;
                font-size: 10px;
            }}
            
            .event-customer {{
                color: #1f2937;
                font-size: 9.5px;
                font-weight: 500;
            }}
            
            .event-model {{
                color: #374151;
                font-size: 9px;
            }}
            
            .legend {{
                margin-top: 10px;
                padding: 10px;
                background-color: #f9fafb;
                border: 1px solid #ddd;
                border-radius: 3px;
            }}
            
            .legend-title {{
                font-weight: bold;
                margin-bottom: 8px;
                font-size: 11px;
            }}
            
            .legend-items {{
                display: flex;
                flex-wrap: wrap;
                gap: 12px;
            }}
            
            .legend-item {{
                display: flex;
                align-items: center;
                gap: 5px;
                font-size: 10px;
            }}
            
            .legend-color {{
                width: 16px;
                height: 16px;
                border-radius: 2px;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <h2>{month_name}</h2>
        </div>
        
        <table class="calendar-table">
            <thead>
                <tr>
                    <th>Monday</th>
                    <th>Tuesday</th>
                    <th>Wednesday</th>
                    <th>Thursday</th>
                    <th>Friday</th>
                    <th>Saturday</th>
                    <th>Sunday</th>
                </tr>
            </thead>
            <tbody>
    """
    
    # Get the first day of the month and number of days
    first_day_weekday = datetime(year, month, 1).weekday()
    num_days = monthrange(year, month)[1]
    
    # Build calendar grid
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
                date_obj = date(year, month, current_day)
                date_str = date_obj.isoformat()
                
                html += f'<td><div class="date-number">{current_day}</div>'
                
                if date_str in events_by_date:
                    for event in events_by_date[date_str]:
                        status_class = normalize_status_key(event["status"]).replace(" ", "")
                        html += f'<div class="event-item status-{status_class}">'
                        html += f'<div class="event-wo">WO: {event["wo"]}</div>'
                        if event["customer"]:
                            html += f'<div class="event-customer">{event["customer"]}</div>'
                        if event["model"]:
                            html += f'<div class="event-model">{event["model"]}</div>'
                        html += '</div>'
                
                html += '</td>'
                current_day += 1
        html += "</tr>"
    
    html += """
            </tbody>
        </table>
        
        <div class="legend">
            <div class="legend-title">Status Legend:</div>
            <div class="legend-items">
                <div class="legend-item">
                    <div class="legend-color" style="background-color: #2563eb;"></div>
                    <span>Open</span>
                </div>
                <div class="legend-item">
                    <div class="legend-color" style="background-color: #d97706;"></div>
                    <span>In Progress</span>
                </div>
                <div class="legend-item">
                    <div class="legend-color" style="background-color: #16a34a;"></div>
                    <span>Completed</span>
                </div>
                <div class="legend-item">
                    <div class="legend-color" style="background-color: #6b7280;"></div>
                    <span>On Hold</span>
                </div>
                <div class="legend-item">
                    <div class="legend-color" style="background-color: #dc2626;"></div>
                    <span>Cancelled</span>
                </div>
            </div>
        </div>
        
        <script>
            // Optional: Auto-print on load
            // window.onload = function() { window.print(); }
        </script>
    </body>
    </html>
    """
    
    return html


# ---------------- Session Init ----------------
admin_session.init()
if "show_print_preview" not in st.session_state:
    st.session_state.show_print_preview = False


# ---------------- Calendar drag & drop ----------------
# Apply a drop before anything is drawn, so this run already shows the new
# date everywhere. (Drawing the calendar from the old data first made dropped
# events jump back to their old day for a moment.) The key changes whenever the
# data is changed another way, which starts the drag history afresh.
calendar_key = f"calendar_{st.session_state.df_version}"
drag = parse_event_change(st.session_state.get(calendar_key))
if drag and drag.signature(calendar_key) != st.session_state.last_applied_change:
    st.session_state.last_applied_change = drag.signature(calendar_key)
    if apply_drag(st.session_state.df, drag):
        st.session_state.has_unsaved_changes = True
        st.toast(f"WO {drag.wo or '(none)'} moved to {drag.new_date:%a %b %d, %Y}")
    if drag.view_date:
        st.session_state.calendar_view = {"date": drag.view_date.isoformat(), "view": drag.view_type}


# ---------------- Sidebar ----------------
with st.sidebar:
    st.header("Upload Order Book")
    file = st.file_uploader("Excel (.xlsx) or CSV", type=["xlsx", "csv"])

    if st.session_state.last_uploaded_name:
        st.caption(f"📂 Loaded: **{st.session_state.last_uploaded_name}**")
    else:
        st.caption("No data loaded yet.")

    st.divider()
    
    # Password-protected clear data
    with st.expander("🗑️ Clear All Data"):
        st.warning("This will delete all data from the database. This action cannot be undone.")
        clear_password = st.text_input("Enter password to confirm", type="password", key="clear_password")
        if st.button("Delete All Data", type="secondary"):
            correct_password = st.secrets.get("UPDATE_PASSWORD", "admin123")
            if clear_password == correct_password:
                before = st.session_state.df
                st.session_state.df = order_book.empty_frame()
                st.session_state.last_uploaded_signature = None
                if not admin_session.save(done_message="All data cleared."):
                    st.session_state.df = before
                    st.error(st.session_state.save_error)
            else:
                st.error("❌ Incorrect password. Data not cleared.")

    st.caption("Use Streamlit's left sidebar page selector to open **Table View**.")


# An upload is only a proposal until it is confirmed in the import preview below.
if file is not None:
    try:
        file_signature = uploaded_file_signature(file)
        pending = st.session_state.pending_import or {}
        if file_signature not in (st.session_state.last_uploaded_signature, pending.get("signature")):
            buffer = io.BytesIO(file.getvalue())
            df_raw = pd.read_csv(buffer) if file.name.lower().endswith(".csv") else pd.read_excel(buffer)
            incoming = order_book.normalize_upload(df_raw)
            st.session_state.pending_import = {
                "signature": file_signature,
                "name": file.name,
                "df": incoming,
                "preview": order_book.import_preview(st.session_state.df, incoming),
            }
    except order_book.MissingColumnsError as e:
        st.error("Your file is missing required columns.")
        st.write("**Missing:**", e.missing)
        st.write("**Found columns:**", e.found)
    except Exception as e:
        st.exception(e)


# ---------------- Calendar ----------------
st.title("📅 Production Schedule Calendar")
admin_session.show_status()

pending = st.session_state.pending_import
if pending:
    preview = pending["preview"]
    with st.container(border=True):
        st.subheader(f"📥 Import {pending['name']}?")
        st.write(
            f"The file has **{preview.rows}** orders. Importing **replaces the whole working schedule** "
            "with the file. Nothing is saved to the database until you click **Update Changes**."
        )
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("New WOs", len(preview.new))
        m2.metric("Changed WOs", len(preview.changed))
        m3.metric("Removed WOs", len(preview.missing), help="In the current schedule but not in the file")
        m4.metric("Duplicate WOs in file", len(preview.duplicates))
        if preview.blank_wo:
            st.warning(f"{preview.blank_wo} row(s) in the file have no WO number.")
        with st.expander("Show WO numbers"):
            for label, wos in [("New", preview.new), ("Changed", preview.changed),
                               ("Removed", preview.missing), ("Duplicated", preview.duplicates)]:
                if wos:
                    st.write(f"**{label}:** " + ", ".join(wos))
        c1, c2 = st.columns(2)
        if c1.button("Replace schedule with this file", type="primary"):
            st.session_state.df = pending["df"]
            st.session_state.last_uploaded_name = pending["name"]
            st.session_state.last_uploaded_signature = pending["signature"]
            st.session_state.pending_import = None
            st.session_state.df_version += 1
            st.session_state.has_unsaved_changes = True
            flash(f"Loaded {len(pending['df'])} rows. Click 'Update Changes' below to save to database.")
            st.rerun()
        if c2.button("Cancel import"):
            st.session_state.last_uploaded_signature = pending["signature"]
            st.session_state.pending_import = None
            st.rerun()

events = df_to_calendar_events(st.session_state.df)

# Only drops are reported back. Other calendar messages (clicks, event loads)
# would each re-run the whole page for nothing.
calendar(
    events=events,
    options=build_calendar_options(
        editable=True,
        height=900,
        initial_date=st.session_state.calendar_view.get("date"),
        initial_view=st.session_state.calendar_view.get("view"),
    ),
    custom_css=ADMIN_CALENDAR_CUSTOM_CSS,
    callbacks=["eventChange"],
    key=f"calendar_{st.session_state.df_version}",
)

# ---------------- Update Changes (Password Protected) ----------------
if st.session_state.has_unsaved_changes:
    st.warning("⚠️ You have unsaved changes. Click 'Update Changes' below to save to database.")

with st.expander(
    "🔐 Update Changes (Password Protected)",
    expanded=st.session_state.has_unsaved_changes or bool(st.session_state.save_error),
):
    st.write("Enter the password to save your changes to the Supabase database.")
    
    col_a, col_b = st.columns([2, 1])
    with col_a:
        password = st.text_input("Password", type="password", key="update_password")
    with col_b:
        update_btn = st.button("✅ Update Changes", type="primary", use_container_width=True)
    
    if update_btn:
        correct_password = st.secrets.get("UPDATE_PASSWORD", "admin123")  # Default fallback

        if password == correct_password:
            with st.spinner("Saving changes to database..."):
                saved = admin_session.save()
            if not saved:
                st.error(st.session_state.save_error)
        else:
            st.error("❌ Incorrect password. Changes not saved.")

    admin_session.reload_button(key="reload_calendar")

st.divider()

col1, col2, col3 = st.columns([1, 1, 2])
with col1:
    st.metric("Total orders", int(len(st.session_state.df)))
with col2:
    total_value = st.session_state.df["Price"].dropna().sum() if "Price" in st.session_state.df else 0
    st.metric("Total value", f"${total_value:,.2f}")
with col3:
    st.caption("Drag & drop an event to change Scheduled Date. Edit rows in Table View.")

st.caption("Status colors: 🔵 Open  🟠 In Progress  🟢 Completed  ⚫ On Hold  🔴 Cancelled")

st.subheader("Download updated Excel")
st.download_button(
    "Download XLSX",
    data=build_excel_bytes(st.session_state.df),
    file_name="order_book_updated.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)

st.divider()

# ---------------- Monthly Print View ----------------
st.subheader("🖨️ Print Monthly Schedule")
st.caption("Generate a printable calendar for production distribution")

print_col1, print_col2, print_col3 = st.columns([2, 2, 3])
with print_col1:
    print_month = st.selectbox(
        "Month",
        range(1, 13),
        format_func=lambda x: datetime(2000, x, 1).strftime("%B"),
        key="print_month",
        index=datetime.now().month - 1
    )
with print_col2:
    print_year = st.number_input(
        "Year",
        min_value=2020,
        max_value=2030,
        value=datetime.now().year,
        key="print_year"
    )
with print_col3:
    st.write("")  # Spacer
    generate_btn = st.button("📄 Generate Print View", type="primary")

if generate_btn:
    st.session_state.show_print_preview = True
    st.session_state.print_html = generate_monthly_print_view(st.session_state.df, print_month, print_year)
    st.session_state.print_month_name = datetime(print_year, print_month, 1).strftime("%B_%Y")

if "show_print_preview" in st.session_state and st.session_state.show_print_preview:
    col_dl, col_hide = st.columns([1, 4])
    with col_dl:
        st.download_button(
            label="💾 Download HTML to Print",
            data=st.session_state.print_html,
            file_name=f"production_schedule_{st.session_state.print_month_name}.html",
            mime="text/html",
            help="Download and open in browser, then use Ctrl+P (Cmd+P on Mac) to print"
        )
    with col_hide:
        if st.button("Hide Preview"):
            st.session_state.show_print_preview = False
            st.rerun()
    
    st.info("👁️ Preview below - Download the HTML file and open in your browser to print with proper formatting")
    st.components.v1.html(st.session_state.print_html, height=1000, scrolling=True)
