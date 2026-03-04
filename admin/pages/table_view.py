# admin/pages/table_view.py

import re
from datetime import datetime

import pandas as pd
import streamlit as st
from production_scheduler.config import REQUIRED_COLS
from production_scheduler.data.data_io import load_order_book, save_order_book
from production_scheduler.data.data_processing import normalize_order_df
from production_scheduler.services.data_services import apply_filters

st.set_page_config(page_title="Order Book Table", layout="wide")


# ---------------- Session Init ----------------
if "df" not in st.session_state:
    with st.spinner("Loading saved data..."):
        df_loaded, last_name = load_order_book()
    st.session_state.df = df_loaded
    st.session_state.last_uploaded_name = last_name
if "last_uploaded_name" not in st.session_state:
    st.session_state.last_uploaded_name = None
if "df_version" not in st.session_state:
    st.session_state.df_version = 0
if "has_unsaved_changes" not in st.session_state:
    st.session_state.has_unsaved_changes = False


# ---------------- Table Page ----------------
st.title("🧾 Table View")
st.caption("Edit rows here, then click **Apply Changes**. Calendar updates automatically.")

if st.session_state.last_uploaded_name:
    st.info(f"📂 Currently loaded: **{st.session_state.last_uploaded_name}**")
else:
    st.warning("No data loaded. Upload a file from the Calendar page.")

if st.session_state.has_unsaved_changes:
    st.warning("⚠️ You have unsaved changes. Save them below before they're lost.")

# ---------------- Filters ----------------
st.subheader("🔍 Filters (View Only)")
st.caption("Apply filters to view specific data. Filters do not affect editing or saving.")

with st.expander("Filter Options", expanded=False):
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**Quote Number**")
        quote_cols = st.columns([3, 1])
        quote_text = quote_cols[0].text_input("Quote", label_visibility="collapsed", key="filter_quote")
        quote_match = quote_cols[1].selectbox("Match", ["Contains", "Exact"], key="quote_match_type", label_visibility="collapsed")
        
        st.markdown("**PO Number**")
        po_cols = st.columns([3, 1])
        po_text = po_cols[0].text_input("PO Number", label_visibility="collapsed", key="filter_po")
        po_match = po_cols[1].selectbox("Match", ["Contains", "Exact"], key="po_match_type", label_visibility="collapsed")
        
        st.markdown("**Status**")
        status_cols = st.columns([3, 1])
        # Get unique statuses from the dataframe
        unique_statuses = ["All"] + sorted(st.session_state.df["Status"].unique().tolist())
        status = status_cols[0].selectbox("Status", unique_statuses, key="filter_status", label_visibility="collapsed")
        status_match = status_cols[1].selectbox("Match", ["Contains", "Exact"], key="status_match_type", label_visibility="collapsed")
    
    with col2:
        st.markdown("**Customer Name**")
        customer_cols = st.columns([3, 1])
        customer_text = customer_cols[0].text_input("Customer", label_visibility="collapsed", key="filter_customer")
        customer_match = customer_cols[1].selectbox("Match", ["Contains", "Exact"], key="customer_match_type", label_visibility="collapsed")
        
        st.markdown("**Model Description**")
        model_cols = st.columns([3, 1])
        model_text = model_cols[0].text_input("Model", label_visibility="collapsed", key="filter_model")
        model_match = model_cols[1].selectbox("Match", ["Contains", "Exact"], key="model_match_type", label_visibility="collapsed")
        
        st.markdown("**Date Filter**")
        date_filter_type = st.radio("Filter by", ["None", "Exact Date", "Month"], horizontal=True, key="date_filter_type")

        st.markdown("**Sort by Scheduled Date**")
        sort_order = st.selectbox(
            "Sort Order",
            ["Descending (Newest First)", "Ascending (Oldest First)"],
            key="sort_order",
            label_visibility="collapsed",
        )

        exact_date = None
        month = None
        year = None
        
        if date_filter_type == "Exact Date":
            exact_date = st.date_input("Select Date", key="filter_exact_date")
        elif date_filter_type == "Month":
            date_cols = st.columns(2)
            month = date_cols[0].selectbox("Month", range(1, 13), 
                                          format_func=lambda x: datetime(2000, x, 1).strftime("%B"),
                                          key="filter_month")
            year = date_cols[1].number_input("Year", min_value=2020, max_value=2030, 
                                            value=datetime.now().year, key="filter_year")
    
    # Clear filters button
    if st.button("🔄 Clear All Filters"):
        st.rerun()

# Prepare filters dictionary
filters = {
    "quote_text": quote_text,
    "quote_match": quote_match,
    "po_text": po_text,
    "po_match": po_match,
    "status": status,
    "status_match": status_match,
    "customer_text": customer_text,
    "customer_match": customer_match,
    "model_text": model_text,
    "model_match": model_match,
    "date_filter_type": date_filter_type,
    "exact_date": exact_date,
    "month": month,
    "year": year,
    "sort_order": sort_order,
}

# Apply filters for display only
display_df = apply_filters(st.session_state.df, filters)
display_df = display_df.sort_values(by="Scheduled Date", ascending=False, na_position="last")

# Show filtered count
st.caption(f"Showing {len(display_df)} of {len(st.session_state.df)} total rows")

with st.form("table_form"):
    edited = st.data_editor(
        display_df,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Scheduled Date": st.column_config.DateColumn(format="YYYY-MM-DD"),
            "Completion Date": st.column_config.DateColumn(format="YYYY-MM-DD"),
            "Price": st.column_config.NumberColumn(format="$%.2f"),
        },
    )
    apply = st.form_submit_button("✅ Apply Changes")

if apply:
    # When saving, we need to merge the edited filtered data back into the full dataset
    df_new = normalize_df(edited)
    mask = (
        df_new["WO"].str.strip().ne("")
        | df_new["Customer Name"].str.strip().ne("")
        | df_new["Model Description"].str.strip().ne("")
    )
    df_new = df_new.loc[mask]
    
    # Update the full dataframe with changes from the filtered view
    if not df_new.empty:
        # Remove rows that were in the filtered view from the main df
        wo_in_filtered = display_df["WO"].tolist()
        st.session_state.df = st.session_state.df[~st.session_state.df["WO"].isin(wo_in_filtered)]
        
        # Add the edited rows back
        st.session_state.df = pd.concat([st.session_state.df, df_new], ignore_index=True)
    
    st.session_state.df_version += 1
    st.session_state.has_unsaved_changes = True
    st.success("Changes applied. Click 'Update Changes' below to save to database.")
    st.rerun()

# ---------------- Update Changes (Password Protected) ----------------
st.divider()
st.subheader("🔐 Save to Database")

with st.expander("Password Protected Update", expanded=st.session_state.has_unsaved_changes):
    st.write("Enter the password to save your changes to the Supabase database.")
    
    col_a, col_b = st.columns([2, 1])
    with col_a:
        password = st.text_input("Password", type="password", key="table_update_password")
    with col_b:
        update_btn = st.button("✅ Update Changes", type="primary", use_container_width=True)
    
    if update_btn:
        correct_password = st.secrets.get("UPDATE_PASSWORD", "admin123")
        
        if password == correct_password:
            with st.spinner("Saving to database..."):
                save_order_book(st.session_state.df, st.session_state.last_uploaded_name)
            st.session_state.has_unsaved_changes = False
            st.success("✅ Changes saved to database successfully!")
            st.rerun()
        else:
            st.error("❌ Incorrect password. Changes not saved.")
