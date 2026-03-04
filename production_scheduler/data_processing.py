"""Data normalization and filtering helpers shared by Streamlit pages."""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

from production_scheduler.config import REQUIRED_COLS

COLUMN_ALIASES = {
    "wo": "WO",
    "work order": "WO",
    "workorder": "WO",
    "quote": "Quote",
    "quotation": "Quote",
    "po number": "PO Number",
    "po #": "PO Number",
    "po#": "PO Number",
    "ponumber": "PO Number",
    "purchase order": "PO Number",
    "status": "Status",
    "customer": "Customer Name",
    "customer name": "Customer Name",
    "client": "Customer Name",
    "client name": "Customer Name",
    "model description": "Model Description",
    "description": "Model Description",
    "model": "Model Description",
    "scheduled date": "Scheduled Date",
    "schedule date": "Scheduled Date",
    "scheduled": "Scheduled Date",
    "ship date": "Scheduled Date",
    "delivery date": "Scheduled Date",
    "date": "Scheduled Date",
    "completion date": "Completion Date",
    "completed date": "Completion Date",
    "price": "Price",
    "amount": "Price",
    "value": "Price",
}

TEXT_COLS = ["WO", "Quote", "PO Number", "Status", "Customer Name", "Model Description"]


def clean_header(value: str) -> str:
    """Normalize incoming column names for alias matching."""
    return re.sub(r"\s+", " ", str(value).strip()).lower()


def parse_date_to_date(value: Any):
    """Convert arbitrary date-like values into ``date`` or ``pd.NaT``."""
    if value is None or str(value).strip() in ("", "None", "NaT"):
        return pd.NaT
    try:
        if pd.isna(value):
            return pd.NaT
    except Exception:
        pass
    dt = pd.to_datetime(value, errors="coerce")
    return pd.NaT if pd.isna(dt) else dt.date()


def parse_price_to_float(value: Any):
    """Parse currency-like inputs into float or ``pd.NA``."""
    if value is None or str(value).strip() == "":
        return pd.NA
    try:
        if pd.isna(value):
            return pd.NA
    except Exception:
        pass

    normalized = re.sub(r"[^0-9.\-]", "", str(value).replace("$", "").replace(",", ""))
    try:
        return float(normalized)
    except Exception:
        return pd.NA


def standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Rename DataFrame columns using known aliases."""
    renamed = df.rename(columns={c: COLUMN_ALIASES.get(clean_header(c), str(c).strip()) for c in df.columns})
    renamed.columns = [str(col).strip() for col in renamed.columns]
    return renamed


def normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize uploaded or edited data to the required schema and datatypes."""
    normalized = standardize_columns(df).copy()
    missing = [col for col in REQUIRED_COLS if col not in normalized.columns]
    if missing:
        raise KeyError(f"Missing columns: {missing}")

    ordered = REQUIRED_COLS + [col for col in normalized.columns if col not in REQUIRED_COLS]
    normalized = normalized[ordered].copy()
    normalized = normalized.dropna(how="all", subset=REQUIRED_COLS)

    for col in TEXT_COLS:
        normalized[col] = normalized[col].where(normalized[col].notna(), "").astype(str).str.strip()
        normalized[col] = normalized[col].replace({"nan": "", "NaN": "", "None": "", "<NA>": ""})

    normalized["Scheduled Date"] = normalized["Scheduled Date"].apply(parse_date_to_date)
    normalized["Completion Date"] = normalized["Completion Date"].apply(parse_date_to_date)
    normalized["Price"] = normalized["Price"].apply(parse_price_to_float)

    summary_like = (
        normalized["WO"].str.fullmatch(r"\d+")
        & normalized["Quote"].eq("")
        & normalized["PO Number"].eq("")
        & normalized["Status"].eq("")
        & normalized["Customer Name"].eq("")
        & normalized["Model Description"].eq("")
        & normalized["Scheduled Date"].isna()
        & normalized["Completion Date"].isna()
        & normalized["Price"].notna()
    )

    blank_text = normalized[TEXT_COLS].eq("").all(axis=1)
    normalized = normalized[
        ~(summary_like | (blank_text & normalized["Scheduled Date"].isna() & normalized["Completion Date"].isna() & normalized["Price"].isna()))
    ]
    return normalized


def apply_filters(df: pd.DataFrame, filters: dict[str, Any]) -> pd.DataFrame:
    """Apply table-view filters to a DataFrame without mutating the source."""
    filtered_df = df.copy()

    filter_map = [
        ("Quote", "quote_text", "quote_match"),
        ("PO Number", "po_text", "po_match"),
        ("Status", "status", "status_match"),
        ("Customer Name", "customer_text", "customer_match"),
        ("Model Description", "model_text", "model_match"),
    ]

    for column, value_key, mode_key in filter_map:
        raw_value = filters.get(value_key)
        if not raw_value or (column == "Status" and raw_value == "All"):
            continue
        if filters.get(mode_key) == "Exact":
            filtered_df = filtered_df[filtered_df[column].str.strip() == str(raw_value).strip()]
        else:
            filtered_df = filtered_df[filtered_df[column].str.contains(str(raw_value), case=False, na=False)]

    if filters.get("date_filter_type") == "Exact Date" and filters.get("exact_date"):
        filtered_df = filtered_df[filtered_df["Scheduled Date"] == filters["exact_date"]]
    elif filters.get("date_filter_type") == "Month" and filters.get("month") and filters.get("year"):
        as_dt = pd.to_datetime(filtered_df["Scheduled Date"], errors="coerce")
        filtered_df = filtered_df[(as_dt.dt.month == filters["month"]) & (as_dt.dt.year == filters["year"])]

    return filtered_df
