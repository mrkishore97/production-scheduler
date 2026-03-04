import re

import pandas as pd

from production_scheduler.config import REQUIRED_COLS

COLUMN_ALIASES = {
    "wo": "WO", "work order": "WO", "workorder": "WO",
    "quote": "Quote", "quotation": "Quote",
    "po number": "PO Number", "po #": "PO Number", "po#": "PO Number",
    "ponumber": "PO Number", "purchase order": "PO Number",
    "status": "Status",
    "customer": "Customer Name", "customer name": "Customer Name",
    "client": "Customer Name", "client name": "Customer Name",
    "model description": "Model Description", "description": "Model Description",
    "model": "Model Description",
    "scheduled date": "Scheduled Date", "schedule date": "Scheduled Date",
    "scheduled": "Scheduled Date", "ship date": "Scheduled Date",
    "delivery date": "Scheduled Date", "date": "Scheduled Date",
    "completion date": "Completion Date", "completed date": "Completion Date",
    "price": "Price", "amount": "Price", "value": "Price",
}


def clean_header(value: str) -> str:
    return re.sub(r"\s+", " ", str(value).strip()).lower()


def parse_date_to_date(value):
    if value is None or str(value).strip() in ("", "None", "NaT"):
        return pd.NaT
    try:
        if pd.isna(value):
            return pd.NaT
    except Exception:
        pass
    dt = pd.to_datetime(value, errors="coerce")
    return pd.NaT if pd.isna(dt) else dt.date()


def parse_price_to_float(value):
    if value is None or str(value).strip() == "":
        return pd.NA
    try:
        if pd.isna(value):
            return pd.NA
    except Exception:
        pass
    sanitized = re.sub(r"[^0-9.\-]", "", str(value).replace("$", "").replace(",", ""))
    try:
        return float(sanitized)
    except Exception:
        return pd.NA


def standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
    standardized = df.copy()
    standardized = standardized.rename(
        columns={c: COLUMN_ALIASES.get(clean_header(c), str(c).strip()) for c in standardized.columns}
    )
    return standardized


def normalize_order_df(df: pd.DataFrame) -> pd.DataFrame:
    normalized = df.copy()
    for col in REQUIRED_COLS:
        if col not in normalized.columns:
            normalized[col] = pd.NA
    normalized = normalized[REQUIRED_COLS]

    text_cols = ["WO", "Quote", "PO Number", "Status", "Customer Name", "Model Description"]
    for col in text_cols:
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

    blank_text = normalized[
        ["WO", "Quote", "PO Number", "Status", "Customer Name", "Model Description"]
    ].eq("").all(axis=1)

    normalized = normalized[
        ~(summary_like | (blank_text & normalized["Scheduled Date"].isna() & normalized["Completion Date"].isna() & normalized["Price"].isna()))
    ]

    return normalized
