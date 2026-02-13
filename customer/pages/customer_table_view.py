# customer/pages/customer_table_view.py

from datetime import datetime

import pandas as pd
import streamlit as st
from pathlib import Path
import sys

st.set_page_config(page_title="My Orders — Table", layout="wide")

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from production_scheduler.customer_portal import get_data_version, load_all_data


def apply_filters(df, filters):
    out = df.copy()

    if filters["quote_text"]:
        if filters["quote_match"] == "Exact":
            out = out[out["Quote"].str.strip() == filters["quote_text"].strip()]
        else:
            out = out[out["Quote"].str.contains(filters["quote_text"], case=False, na=False)]

    if filters["po_text"]:
        if filters["po_match"] == "Exact":
            out = out[out["PO Number"].str.strip() == filters["po_text"].strip()]
        else:
            out = out[out["PO Number"].str.contains(filters["po_text"], case=False, na=False)]

    if filters["status"] and filters["status"] != "All":
        if filters["status_match"] == "Exact":
            out = out[out["Status"].str.strip().str.lower() == filters["status"].lower()]
        else:
            out = out[out["Status"].str.contains(filters["status"], case=False, na=False)]

    # Customer sub-filter — only relevant when user has multiple customers
    if filters["customer"] and filters["customer"] != "All":
        out = out[out["Customer Name"].str.strip() == filters["customer"].strip()]

    if filters["model_text"]:
        if filters["model_match"] == "Exact":
            out = out[out["Model Description"].str.strip() == filters["model_text"].strip()]
        else:
            out = out[out["Model Description"].str.contains(filters["model_text"], case=False, na=False)]

    if filters["date_filter_type"] == "Exact Date" and filters["exact_date"]:
        out = out[out["Scheduled Date"] == filters["exact_date"]]
    elif filters["date_filter_type"] == "Month" and filters["month"] and filters["year"]:
        out = out[
            (pd.to_datetime(out["Scheduled Date"], errors="coerce").dt.month == filters["month"]) &
            (pd.to_datetime(out["Scheduled Date"], errors="coerce").dt.year == filters["year"])
        ]

    return out


# ================================================================
#  SESSION STATE INIT
# ================================================================
for key, default in [
    ("authenticated",       False),
    ("logged_in_customers", []),
    ("token_verified",      False),
    ("token_customers",     []),
    ("customer_display",    ""),
    ("login_username",      None),
    ("df_version",          0),
]:
    if key not in st.session_state:
        st.session_state[key] = default


# ================================================================
#  AUTH GATE
# ================================================================
is_password_auth = bool(st.session_state.authenticated and st.session_state.logged_in_customers)
is_token_auth = bool(st.session_state.get("token_verified") and st.session_state.get("token_customers"))

if not is_password_auth and not is_token_auth:
    st.title("🔒 Access Denied")
    st.warning("You are not logged in or do not have a valid customer token.")
    st.info(
        "👈 Please go back to the **Customer Portal** main page to sign in "
        "or open this page using your secure token link."
    )
    st.stop()


# ================================================================
#  AUTHENTICATED SECTION
# ================================================================
if is_password_auth:
    my_customers: list[str] = st.session_state.logged_in_customers
    customer_display: str = st.session_state.customer_display
else:
    my_customers = st.session_state.token_customers
    customer_display = st.session_state.get("customer_display") or ", ".join(my_customers)

# ---- Sidebar ----
with st.sidebar:
    st.markdown(f"### 👤 {customer_display}")
    if is_password_auth:
        st.caption(f"Signed in as `{st.session_state.login_username}`")
    else:
        st.caption("Accessed via secure token link")
    if len(my_customers) > 1:
        st.caption("**Viewing orders for:**")
        for c in my_customers:
            st.caption(f"• {c}")
    st.divider()
    st.caption("🔒 Read-only — contact admin to make changes.")
    st.divider()
    if st.button("🚪 Log Out", use_container_width=True):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()

# ---- Load & filter to this user's customers ----
_version = get_data_version()
df_all = load_all_data(data_version=_version)
my_df  = df_all[
    df_all["Customer Name"].str.strip().str.lower().isin(
        [c.strip().lower() for c in my_customers]
    )
].copy()

st.title(f"🧾 My Orders — {customer_display}")
st.caption("Read-only view of your orders. Contact your admin for any changes.")

if my_df.empty:
    st.warning(f"No orders found for **{customer_display}**.")
    st.stop()

# ---- Filters ----
st.subheader("🔍 Filters")

with st.expander("Filter Options", expanded=False):
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Quote Number**")
        q_cols = st.columns([3, 1])
        quote_text  = q_cols[0].text_input("Quote", label_visibility="collapsed", key="f_quote")
        quote_match = q_cols[1].selectbox("", ["Contains", "Exact"], key="f_quote_m",
                                          label_visibility="collapsed")

        st.markdown("**PO Number**")
        p_cols = st.columns([3, 1])
        po_text  = p_cols[0].text_input("PO", label_visibility="collapsed", key="f_po")
        po_match = p_cols[1].selectbox("", ["Contains", "Exact"], key="f_po_m",
                                       label_visibility="collapsed")

        st.markdown("**Status**")
        s_cols = st.columns([3, 1])
        unique_statuses = ["All"] + sorted([s for s in my_df["Status"].unique() if s])
        status       = s_cols[0].selectbox("Status", unique_statuses, key="f_status",
                                           label_visibility="collapsed")
        status_match = s_cols[1].selectbox("", ["Contains", "Exact"], key="f_status_m",
                                           label_visibility="collapsed")

    with col2:
        # Customer sub-filter — only shown when user has access to multiple customers
        if len(my_customers) > 1:
            st.markdown("**Customer**")
            customer_options  = ["All"] + sorted(my_customers)
            selected_customer = st.selectbox("Customer", customer_options, key="f_customer",
                                             label_visibility="collapsed")
        else:
            selected_customer = "All"

        st.markdown("**Model Description**")
        m_cols = st.columns([3, 1])
        model_text  = m_cols[0].text_input("Model", label_visibility="collapsed", key="f_model")
        model_match = m_cols[1].selectbox("", ["Contains", "Exact"], key="f_model_m",
                                          label_visibility="collapsed")

        st.markdown("**Date Filter**")
        date_filter_type = st.radio(
            "Filter by", ["None", "Exact Date", "Month"],
            horizontal=True, key="f_date_type",
        )

        exact_date = month = year = None
        if date_filter_type == "Exact Date":
            exact_date = st.date_input("Select Date", key="f_exact_date")
        elif date_filter_type == "Month":
            dc = st.columns(2)
            month = dc[0].selectbox(
                "Month", range(1, 13),
                format_func=lambda x: datetime(2000, x, 1).strftime("%B"),
                key="f_month",
            )
            year = dc[1].number_input(
                "Year", min_value=2020, max_value=2030,
                value=datetime.now().year, key="f_year",
            )

    if st.button("🔄 Clear Filters"):
        st.rerun()

filters = {
    "quote_text":       quote_text,
    "quote_match":      quote_match,
    "po_text":          po_text,
    "po_match":         po_match,
    "status":           status,
    "status_match":     status_match,
    "customer":         selected_customer,
    "model_text":       model_text,
    "model_match":      model_match,
    "date_filter_type": date_filter_type,
    "exact_date":       exact_date,
    "month":            month,
    "year":             year,
}

display_df = apply_filters(my_df, filters)
st.caption(f"Showing **{len(display_df)}** of **{len(my_df)}** orders")

# ---- Read-only table ----
st.dataframe(
    display_df,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Scheduled Date": st.column_config.DateColumn(format="YYYY-MM-DD"),
        "Price":          st.column_config.NumberColumn(format="$%.2f"),
    },
)

st.divider()

pending_orders_count = (my_df["Status"].str.strip().str.lower() != "completed").sum()
st.metric("Pending orders", int(pending_orders_count))

st.divider()
st.caption("💡 Need to make changes to an order? Please contact your administrator.")
