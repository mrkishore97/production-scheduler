import time

import pandas as pd
import streamlit as st
from supabase import Client, create_client

from production_scheduler.config import REQUIRED_COLS, SUPABASE_TABLE
from production_scheduler.data.data_processing import parse_date_to_date


@st.cache_resource
def get_supabase_client() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])


def get_data_version() -> int:
    supabase = get_supabase_client()
    try:
        response = supabase.table("app_meta").select("value").eq("key", "data_version").single().execute()
        return int(response.data["value"])
    except Exception:
        return 0


def load_order_book() -> tuple[pd.DataFrame, str | None]:
    supabase = get_supabase_client()
    response = supabase.table(SUPABASE_TABLE).select("*").execute()
    rows = response.data

    if not rows:
        return pd.DataFrame(columns=REQUIRED_COLS), None

    df = pd.DataFrame(rows)
    last_name = df["uploaded_name"].iloc[0] if "uploaded_name" in df.columns else None

    df = df.rename(columns={
        "wo": "WO", "quote": "Quote", "po_number": "PO Number",
        "status": "Status", "customer_name": "Customer Name",
        "model_description": "Model Description",
        "scheduled_date": "Scheduled Date", "completion_date": "Completion Date", "price": "Price",
    })
    df = df.drop(columns=[c for c in ["uploaded_name", "id"] if c in df.columns], errors="ignore")

    df["Scheduled Date"] = df["Scheduled Date"].apply(parse_date_to_date)
    df["Completion Date"] = df["Completion Date"].apply(parse_date_to_date)
    df["Price"] = df["Price"].apply(lambda x: float(x) if x is not None else pd.NA)
    for c in ["Quote", "PO Number", "Status", "Customer Name", "Model Description"]:
        df[c] = df[c].fillna("").astype(str)

    present = [c for c in REQUIRED_COLS if c in df.columns]
    return df[present], last_name


def save_order_book(df: pd.DataFrame, last_uploaded_name: str | None) -> None:
    supabase = get_supabase_client()
    supabase.table(SUPABASE_TABLE).delete().neq("wo", "___never___").execute()

    if df.empty:
        supabase.table("app_meta").upsert(
            {"key": "data_version", "value": str(int(time.time()))}
        ).execute()
        return

    rows = []
    for _, r in df.iterrows():
        d = r.get("Scheduled Date", pd.NaT)
        cd = r.get("Completion Date", pd.NaT)
        price = r.get("Price", None)
        rows.append({
            "wo": str(r.get("WO", "")).strip(),
            "quote": str(r.get("Quote", "")),
            "po_number": str(r.get("PO Number", "")),
            "status": str(r.get("Status", "")),
            "customer_name": str(r.get("Customer Name", "")),
            "model_description": str(r.get("Model Description", "")),
            "scheduled_date": d.isoformat() if not pd.isna(d) else None,
            "completion_date": cd.isoformat() if not pd.isna(cd) else None,
            "price": float(price) if price is not None and not pd.isna(price) else None,
            "uploaded_name": last_uploaded_name or "",
        })

    for i in range(0, len(rows), 500):
        supabase.table(SUPABASE_TABLE).insert(rows[i:i + 500]).execute()

    supabase.table("app_meta").upsert(
        {"key": "data_version", "value": str(int(time.time()))}
    ).execute()
