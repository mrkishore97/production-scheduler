# admin/pages/table_view.py
# A full-page version of the Schedule page's orders table, for longer editing
# sessions. It edits the same working copy, so both pages always agree.

import sys
from pathlib import Path

import streamlit as st

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from production_scheduler import admin_session, admin_ui

st.set_page_config(page_title="Order Book Table", layout="wide")


# ---------------- Session Init ----------------
admin_session.init()
admin_session.fold_table_edits("table")


# ---------------- Table Page ----------------
st.title("🧾 Table View")
st.caption("The same orders as the Schedule page; edits here show up there straight away.")
admin_session.show_status()
admin_ui.newer_version_banner("table")
admin_ui.save_bar("table")
admin_ui.orders_table("table")
