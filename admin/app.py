"""Admin calendar page for production scheduling."""

import io
from datetime import datetime
from pathlib import Path
import sys

import pandas as pd
import streamlit as st
from streamlit_calendar import calendar


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from production_scheduler.admin_services import (
    build_excel_bytes,
    df_to_calendar_events,
    generate_monthly_print_view,
    uploaded_file_signature,
)
from production_scheduler.calendar_ui import ADMIN_CALENDAR_CUSTOM_CSS, build_calendar_options
from production_scheduler.config import REQUIRED_COLS
from production_scheduler.data_io import load_data, save_data
from production_scheduler.data_processing import normalize_df, parse_date_to_date

st.set_page_config(page_title="Order Book Calendar", layout="wide")


def initialize_session_state() -> None:
    """Initialize admin state values the page relies on."""
    if "df" not in st.session_state:
        with st.spinner("Loading saved data..."):
            df_loaded, last_name = load_data(parse_date_to_date)
        st.session_state.df = df_loaded
        st.session_state.last_uploaded_name = last_name

    defaults = {
        "last_uploaded_name": None,
        "df_version": 0,
        "last_applied_change": None,
        "has_unsaved_changes": False,
        "show_print_preview": False,
        "last_uploaded_signature": None,
    }
    for key, default in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default


def render_sidebar() -> None:
    """Render upload and data management controls."""
    with st.sidebar:
        st.header("Upload Order Book")
        uploaded_file = st.file_uploader("Excel (.xlsx) or CSV", type=["xlsx", "csv"])

        if st.session_state.last_uploaded_name:
            st.caption(f"📂 Loaded: **{st.session_state.last_uploaded_name}**")
        else:
            st.caption("No data loaded yet.")

        st.divider()
        with st.expander("🗑️ Clear All Data"):
            st.warning("This will delete all data from the database. This action cannot be undone.")
            clear_password = st.text_input("Enter password to confirm", type="password", key="clear_password")
            if st.button("Delete All Data", type="secondary"):
                if clear_password == st.secrets.get("UPDATE_PASSWORD", "admin123"):
                    empty_df = pd.DataFrame(columns=REQUIRED_COLS)
                    st.session_state.df = empty_df
                    st.session_state.last_uploaded_name = None
                    st.session_state.df_version += 1
                    st.session_state.has_unsaved_changes = False
                    st.session_state.last_uploaded_signature = None
                    save_data(empty_df, "", parse_date_to_date)
                    st.success("All data cleared.")
                    st.rerun()
                else:
                    st.error("❌ Incorrect password. Data not cleared.")

        st.caption("Use Streamlit's left sidebar page selector to open **Table View**.")

    if uploaded_file is not None:
        load_uploaded_file(uploaded_file)


def load_uploaded_file(uploaded_file) -> None:
    """Process uploaded spreadsheet and stage edits in session state."""
    try:
        file_signature = uploaded_file_signature(uploaded_file)
        if file_signature == st.session_state.last_uploaded_signature:
            return

        file_bytes = uploaded_file.getvalue()
        buffer = io.BytesIO(file_bytes)
        raw_df = pd.read_csv(buffer) if uploaded_file.name.lower().endswith(".csv") else pd.read_excel(buffer)
        st.session_state.df = normalize_df(raw_df)
        st.session_state.df_version += 1
        st.session_state.last_uploaded_name = uploaded_file.name
        st.session_state.last_uploaded_signature = file_signature
        st.session_state.has_unsaved_changes = True
        st.success(f"Loaded {len(st.session_state.df)} rows. Click 'Update Changes' below to save to database.")
    except KeyError as error:
        missing = str(error)
        st.error("Your file is missing required columns.")
        st.write(missing)
    except Exception as error:
        st.exception(error)


def render_calendar() -> None:
    st.title("📅 Production Schedule Calendar")
    cal_state = calendar(
        events=df_to_calendar_events(st.session_state.df),
        options=build_calendar_options(editable=True, height=900),
        custom_css=ADMIN_CALENDAR_CUSTOM_CSS,
        key=f"calendar_{st.session_state.df_version}",
    )

    if cal_state and cal_state.get("callback") == "eventChange":
        ev = (cal_state.get("eventChange") or {}).get("event") or {}
        wo = str(ev.get("id", "")).strip()
        new_dt = pd.to_datetime(ev.get("start"), errors="coerce")
        if wo and not pd.isna(new_dt):
            new_date = new_dt.date()
            sig = f"{wo}|{new_date.isoformat()}"
            if st.session_state.last_applied_change != sig:
                mask = st.session_state.df["WO"].astype(str).str.strip() == wo
                if mask.any():
                    old_val = st.session_state.df.loc[mask, "Scheduled Date"].iloc[0]
                    if pd.isna(old_val) or old_val != new_date:
                        st.session_state.df.loc[mask, "Scheduled Date"] = new_date
                        st.session_state.has_unsaved_changes = True
                st.session_state.last_applied_change = sig


def render_update_controls() -> None:
    if st.session_state.has_unsaved_changes:
        st.warning("⚠️ You have unsaved changes. Click 'Update Changes' below to save to database.")

    with st.expander("🔐 Update Changes (Password Protected)", expanded=st.session_state.has_unsaved_changes):
        st.write("Enter the password to save your changes to the Supabase database.")
        col_a, col_b = st.columns([2, 1])
        with col_a:
            password = st.text_input("Password", type="password", key="update_password")
        with col_b:
            update_btn = st.button("✅ Update Changes", type="primary", use_container_width=True)

        if update_btn:
            if password == st.secrets.get("UPDATE_PASSWORD", "admin123"):
                with st.spinner("Saving changes to database..."):
                    save_data(st.session_state.df, st.session_state.last_uploaded_name, parse_date_to_date)
                st.session_state.has_unsaved_changes = False
                st.session_state.df_version += 1
                st.success("✅ Changes saved to database successfully!")
                st.rerun()
            else:
                st.error("❌ Incorrect password. Changes not saved.")


def render_metrics_and_download() -> None:
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


def render_print_section() -> None:
    st.divider()
    st.subheader("🖨️ Print Monthly Schedule")
    st.caption("Generate a printable calendar for production distribution")

    col_month, col_year, col_action = st.columns([2, 2, 3])
    with col_month:
        print_month = st.selectbox(
            "Month",
            range(1, 13),
            format_func=lambda x: datetime(2000, x, 1).strftime("%B"),
            key="print_month",
            index=datetime.now().month - 1,
        )
    with col_year:
        print_year = st.number_input("Year", min_value=2020, max_value=2030, value=datetime.now().year, key="print_year")
    with col_action:
        st.write("")
        generate_btn = st.button("📄 Generate Print View", type="primary")

    if generate_btn:
        st.session_state.show_print_preview = True
        st.session_state.print_html = generate_monthly_print_view(st.session_state.df, print_month, print_year)
        st.session_state.print_month_name = datetime(print_year, print_month, 1).strftime("%B_%Y")

    if st.session_state.show_print_preview:
        col_dl, col_hide = st.columns([1, 4])
        with col_dl:
            st.download_button(
                label="💾 Download HTML to Print",
                data=st.session_state.print_html,
                file_name=f"production_schedule_{st.session_state.print_month_name}.html",
                mime="text/html",
                help="Download and open in browser, then use Ctrl+P (Cmd+P on Mac) to print",
            )
        with col_hide:
            if st.button("Hide Preview"):
                st.session_state.show_print_preview = False
                st.rerun()
        st.info("👁️ Preview below - Download the HTML file and open in your browser to print with proper formatting")
        st.components.v1.html(st.session_state.print_html, height=1000, scrolling=True)


initialize_session_state()
render_sidebar()
render_calendar()
render_update_controls()
render_metrics_and_download()
render_print_section()
