import pandas as pd


def apply_filters(df: pd.DataFrame, filters: dict) -> pd.DataFrame:
    filtered_df = df.copy()

    if filters.get("quote_text"):
        if filters.get("quote_match") == "Exact":
            filtered_df = filtered_df[filtered_df["Quote"].str.strip() == filters["quote_text"].strip()]
        else:
            filtered_df = filtered_df[filtered_df["Quote"].str.contains(filters["quote_text"], case=False, na=False)]

    if filters.get("po_text"):
        if filters.get("po_match") == "Exact":
            filtered_df = filtered_df[filtered_df["PO Number"].str.strip() == filters["po_text"].strip()]
        else:
            filtered_df = filtered_df[filtered_df["PO Number"].str.contains(filters["po_text"], case=False, na=False)]

    if filters.get("status") and filters["status"] != "All":
        if filters.get("status_match") == "Exact":
            filtered_df = filtered_df[filtered_df["Status"].str.strip().str.lower() == filters["status"].lower()]
        else:
            filtered_df = filtered_df[filtered_df["Status"].str.contains(filters["status"], case=False, na=False)]

    customer_filter = filters.get("customer") or filters.get("customer_text")
    customer_match = filters.get("customer_match", "Contains")
    if customer_filter:
        if customer_match == "Exact":
            filtered_df = filtered_df[filtered_df["Customer Name"].str.strip() == customer_filter.strip()]
        else:
            filtered_df = filtered_df[filtered_df["Customer Name"].str.contains(customer_filter, case=False, na=False)]

    if filters.get("model_text"):
        if filters.get("model_match") == "Exact":
            filtered_df = filtered_df[filtered_df["Model Description"].str.strip() == filters["model_text"].strip()]
        else:
            filtered_df = filtered_df[filtered_df["Model Description"].str.contains(filters["model_text"], case=False, na=False)]

    if filters.get("date_filter_type") == "Exact Date" and filters.get("exact_date"):
        filtered_df = filtered_df[filtered_df["Scheduled Date"] == filters["exact_date"]]
    elif filters.get("date_filter_type") == "Month" and filters.get("month") and filters.get("year"):
        filtered_df = filtered_df[
            (pd.to_datetime(filtered_df["Scheduled Date"], errors="coerce").dt.month == filters["month"])
            & (pd.to_datetime(filtered_df["Scheduled Date"], errors="coerce").dt.year == filters["year"])
        ]

    return filtered_df
