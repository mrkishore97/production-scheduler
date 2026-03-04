"""Backwards-compatible customer portal API."""

from production_scheduler.data.data_io import get_data_version, load_order_book
from production_scheduler.services.customer_services import (
    build_excel_bytes,
    df_to_calendar_events,
    generate_monthly_print_view,
)


def load_all_data(*, data_version: int):
    del data_version
    df, _ = load_order_book()
    return df


__all__ = [
    "build_excel_bytes",
    "df_to_calendar_events",
    "generate_monthly_print_view",
    "get_data_version",
    "load_all_data",
]
