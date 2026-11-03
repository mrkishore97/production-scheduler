from datetime import date

import pandas as pd

from production_scheduler.admin_ui import sort_orders


def frame():
    return pd.DataFrame({
        "id": ["1", "2", "3", "4", "5"],
        "WO": ["2164-10", "2164-02", "100", "1000", ""],
        "Customer Name": ["Beta", "acme", "Charlie", "", "Acme"],
        "Scheduled Date": [date(2026, 11, 5), date(2026, 11, 9), date(2026, 11, 7), None, date(2026, 11, 7)],
        "Price": [500.0, None, 2000.0, 10.0, 1.0],
    })


def wos(df):
    return list(df["WO"])


def test_wo_sorts_numbers_by_value_and_blank_last():
    assert wos(sort_orders(frame(), "WO")) == ["100", "1000", "2164-02", "2164-10", ""]
    assert wos(sort_orders(frame(), "WO", descending=True)) == ["2164-10", "2164-02", "1000", "100", ""]


def test_price_and_dates_sort_by_value_with_blanks_last():
    assert wos(sort_orders(frame(), "Price")) == ["", "1000", "2164-10", "100", "2164-02"]
    assert wos(sort_orders(frame(), "Scheduled Date", descending=True)) == ["2164-02", "100", "", "2164-10", "1000"]


def test_text_ignores_capitals_and_ties_go_by_date_then_wo():
    assert wos(sort_orders(frame(), "Customer Name")) == ["", "2164-02", "2164-10", "100", "1000"]
