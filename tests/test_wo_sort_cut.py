"""Browser tests: no repeated WO numbers, sorting by any column, cut and paste, 2-month view."""

from __future__ import annotations

from datetime import timedelta

import pytest

from sample_data import month_day, order
from ui import (
    TABLE_COLUMNS,
    add_table_row,
    calendar,
    click,
    click_day,
    cut_bar,
    cut_order,
    day_cell,
    drag_event,
    edit_table_text,
    event_day,
    filter_customer,
    next_month,
    open_app,
    pending_text,
    save,
    saved_dates,
    set_sort,
    shown_month,
    table_rows,
    wait_for_app,
    working_dates,
)

pytestmark = pytest.mark.e2e


def iso(day: int) -> str:
    return month_day(day).isoformat()


def later_month_day(months: int, day: int):
    first = month_day(1)
    for _ in range(months):
        first = (first + timedelta(days=32)).replace(day=1)
    return first.replace(day=day)


# ---------- no repeated WO numbers ----------

def test_typing_a_used_wo_is_flagged_until_fixed(page, fake_db, admin_url):
    fake_db.reset([order("100", month_day(10)), order("101", month_day(11))])
    open_app(page, admin_url)

    edit_table_text(page, row=0, column="WO", value="100 ")  # newest first: WO 101 is the top row
    page.get_by_text("WO 100 is used by 2 orders", exact=False).first.wait_for(timeout=5000)
    assert page.get_by_role("button", name="Save schedule").is_disabled()
    assert calendar(page).locator(".wo-repeated").count() == 2
    assert {r["Check"] for r in table_rows(page)} == {"⚠ Repeated WO"}

    with_check = TABLE_COLUMNS[:1] + ["Check"] + TABLE_COLUMNS[1:]
    edit_table_text(page, row=0, column="WO", value="102", columns=with_check)
    assert page.get_by_text("is used by", exact=False).count() == 0
    save(page)
    assert saved_dates(fake_db) == {"100": [iso(10)], "102": [iso(11)]}


def test_new_row_with_a_used_wo_is_flagged(page, fake_db, admin_url):
    fake_db.reset([order("100", month_day(10))])
    open_app(page, admin_url)
    add_table_row(page, "100", rows_shown=1)
    page.get_by_text("WO 100 is used by 2 orders", exact=False).first.wait_for(timeout=5000)
    assert page.get_by_role("button", name="Save schedule").is_disabled()


def test_blank_wos_are_allowed(page, fake_db, admin_url):
    fake_db.reset([order("", month_day(10)), order("", month_day(11), customer="Beta Industries")])
    open_app(page, admin_url)
    assert page.get_by_text("is used by", exact=False).count() == 0
    drag_event(page, "No WO", month_day(14))
    save(page)
    assert saved_dates(fake_db) == {"": sorted([iso(11), iso(14)])}


# ---------- sorting ----------

def wos(page) -> list[str]:
    return [r["WO"] for r in table_rows(page)]


def test_sort_by_any_column(page, fake_db, admin_url):
    fake_db.reset([
        order("2164-10", month_day(5), customer="Beta", price=500.0),
        order("2164-02", month_day(9), customer="acme", price=None),
        order("100", month_day(7), customer="Charlie", price=2000.0),
        order("1000", None, customer="", price=10.0),
    ])
    open_app(page, admin_url)

    set_sort(page, "WO", "Ascending")
    assert wos(page) == ["100", "1000", "2164-02", "2164-10"]  # numbers in number order
    set_sort(page, "WO", "Descending")
    assert wos(page) == ["2164-10", "2164-02", "1000", "100"]
    set_sort(page, "Price", "Ascending")
    assert wos(page) == ["1000", "2164-10", "100", "2164-02"]  # blank price last
    set_sort(page, "Customer Name", "Ascending")
    assert wos(page) == ["2164-02", "2164-10", "100", "1000"]  # capitals ignored, blank last
    set_sort(page, "Scheduled Date", "Ascending")
    assert wos(page) == ["2164-10", "100", "2164-02", "1000"]  # blank date last


def test_sort_stays_through_drags_and_filters(page, fake_db, admin_url):
    fake_db.reset([order("300", month_day(5)), order("100", month_day(9)), order("200", month_day(7)),
                   order("400", month_day(6), customer="Beta Industries")])
    open_app(page, admin_url)
    set_sort(page, "WO", "Ascending")
    drag_event(page, "300", month_day(20))
    assert wos(page) == ["100", "200", "300", "400"]
    filter_customer(page, "Acme")
    assert wos(page) == ["100", "200", "300"]


# ---------- cut and paste ----------

def test_cut_and_paste_into_another_month(page, fake_db, admin_url):
    fake_db.reset([order("100", month_day(10)), order("101", month_day(11))])
    open_app(page, admin_url)

    cut_order(page, "100")
    assert cut_bar(page).is_visible()
    assert calendar(page).locator(".cut-order").count() == 1

    next_month(page)
    next_month(page)
    target = later_month_day(2, 12)
    title = shown_month(page)
    click_day(page, target)

    assert working_dates(page) == {"100": [target.isoformat()], "101": [iso(11)]}
    assert cut_bar(page).count() == 0
    assert shown_month(page) == title
    assert event_day(page, "100") == target.isoformat()
    assert pending_text(page).startswith("⚠️ 1 unsaved change")

    click(page, "Undo")
    assert working_dates(page)["100"] == [iso(10)]


def test_cut_can_be_cancelled_and_redone(page, fake_db, admin_url):
    fake_db.reset([order("100", month_day(10))])
    open_app(page, admin_url)

    cut_order(page, "100")
    cut_order(page, "100")  # clicking the cut order again puts it back
    assert cut_bar(page).count() == 0

    cut_order(page, "100")
    click(page, "Cancel cut")
    assert cut_bar(page).count() == 0
    click_day(page, month_day(20))  # nothing is cut, so nothing moves
    assert working_dates(page) == {"100": [iso(10)]}

    cut_order(page, "100")  # the same click as before still cuts it
    assert cut_bar(page).is_visible()
    click_day(page, month_day(20))
    assert working_dates(page) == {"100": [iso(20)]}


def test_paste_with_the_date_box(page, fake_db, admin_url):
    fake_db.reset([order("100", month_day(10))])
    open_app(page, admin_url)
    cut_order(page, "100")
    target = later_month_day(3, 4)
    field = cut_bar(page).locator("input").first
    field.fill(target.isoformat())
    field.press("Enter")
    wait_for_app(page)
    click(page, "Paste")
    assert working_dates(page) == {"100": [target.isoformat()]}
    save(page)
    assert saved_dates(fake_db) == {"100": [target.isoformat()]}


def test_two_orders_pasted_on_the_same_day(page, fake_db, admin_url):
    fake_db.reset([order("100", month_day(10)), order("101", month_day(11))])
    open_app(page, admin_url)
    cut_order(page, "100")
    click_day(page, month_day(20))
    cut_order(page, "101")
    click_day(page, month_day(20))
    assert working_dates(page) == {"100": [iso(20)], "101": [iso(20)]}


# ---------- 2-month view ----------

def test_two_month_view_lets_you_drag_across_the_month_end(page, fake_db, admin_url):
    last = later_month_day(1, 1) - timedelta(days=1)  # last day of this month
    fake_db.reset([order("100", last - timedelta(days=1))])
    open_app(page, admin_url)
    calendar(page).get_by_role("button", name="2 months").click()
    wait_for_app(page, 500)
    assert "–" in shown_month(page)
    assert day_cell(page, last + timedelta(days=3)).count() == 1
    drag_event(page, "100", last + timedelta(days=3))
    assert working_dates(page) == {"100": [(last + timedelta(days=3)).isoformat()]}
