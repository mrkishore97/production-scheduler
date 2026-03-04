"""Data access and transformation utilities for scheduler datasets."""

from __future__ import annotations

import time
from typing import Callable

import pandas as pd
import streamlit as st
from supabase import Client, create_client

from production_scheduler.config import REQUIRED_COLS, SUPABASE_TABLE

DB_TO_APP_COLUMNS = {
    "wo": "WO",
    "quote": "Quote",
    "po_number": "PO Number",
    "status": "Status",
    "customer_name": "Customer Name",
    "model_description": "Model Description",
    "scheduled_date": "Scheduled Date",
    "completion_date": "Completion Date",
    "price": "Price",
}

APP_TO_DB_COLUMNS = {value: key for key, value in DB_TO_APP_COLUMNS.items()}


@st.cache_resource
def get_supabase() -> Client:
    """Return a cached Supabase client for the current Streamlit process."""
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])


def save_data(
    df: pd.DataFrame,
    last_uploaded_name: str,
    date_parser: Callable[[object], object],
) -> None:
    """Replace all persisted order book rows with the provided DataFrame."""
    supabase = get_supabase()
    supabase.table(SUPABASE_TABLE).delete().neq("wo", "___never___").execute()

    if df.empty:
        supabase.table("app_meta").upsert(
            {"key": "data_version", "value": str(int(time.time()))}
        ).execute()
        return

    rows = []
    for _, row in df.iterrows():
        scheduled_date = date_parser(row.get("Scheduled Date", pd.NaT))
        completion_date = date_parser(row.get("Completion Date", pd.NaT))
        price = row.get("Price", None)
        rows.append(
            {
                "wo": str(row.get("WO", "")).strip(),
                "quote": str(row.get("Quote", "")),
                "po_number": str(row.get("PO Number", "")),
                "status": str(row.get("Status", "")),
                "customer_name": str(row.get("Customer Name", "")),
                "model_description": str(row.get("Model Description", "")),
                "scheduled_date": scheduled_date.isoformat() if not pd.isna(scheduled_date) else None,
                "completion_date": completion_date.isoformat() if not pd.isna(completion_date) else None,
                "price": float(price) if price is not None and not pd.isna(price) else None,
                "uploaded_name": last_uploaded_name or "",
            }
        )

    for idx in range(0, len(rows), 500):
        supabase.table(SUPABASE_TABLE).insert(rows[idx : idx + 500]).execute()

    supabase.table("app_meta").upsert(
        {"key": "data_version", "value": str(int(time.time()))}
    ).execute()


def load_data(date_parser: Callable[[object], object]) -> tuple[pd.DataFrame, str | None]:
    """Load order rows from Supabase and map them to application columns."""
    supabase = get_supabase()
    response = supabase.table(SUPABASE_TABLE).select("*").execute()
    rows = response.data

    if not rows:
        return pd.DataFrame(columns=REQUIRED_COLS), None

    df = pd.DataFrame(rows)
    last_name = df["uploaded_name"].iloc[0] if "uploaded_name" in df.columns else None
    df = df.rename(columns=DB_TO_APP_COLUMNS)
    df = df.drop(columns=[c for c in ["uploaded_name", "id"] if c in df.columns], errors="ignore")

    df["Scheduled Date"] = df["Scheduled Date"].apply(date_parser)
    df["Completion Date"] = df["Completion Date"].apply(date_parser)
    df["Price"] = df["Price"].apply(lambda x: float(x) if x is not None else pd.NA)

    for col in ["Quote", "PO Number", "Status", "Customer Name", "Model Description"]:
        df[col] = df[col].fillna("").astype(str)

    present = [col for col in REQUIRED_COLS if col in df.columns]
    return df[present], last_name
