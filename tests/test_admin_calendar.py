"""Browser tests for the admin calendar and its link to the working data.

Each test describes how the app should behave. Tests marked ``xfail`` document
known defects that later steps of the repair plan fix; remove the marker when
the fix lands (``strict=True`` makes the suite fail as a reminder).
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from conftest import PASSWORD
from sample_data import bulk_orders, month_day, order, to_upload_frame
from ui import (
    calendar,
    delete_table_row,
    drag_event,
    edit_table_date,
    filter_customer,
    event_day,
    moves,
    next_month,
    open_app,
    open_calendar,
    open_table,
    record_moves,
    save,
    saved_dates,
    shown_month,
    upload,
    wait_for_app,
    working_dates,
)

pytestmark = pytest.mark.e2e


def iso(day: int) -> str:
    return month_day(day).isoformat()


def test_drags_update_working_data(page, fake_db, admin_url):
    fake_db.reset([order(str(900 + i), month_day(5 + i)) for i in range(4)])
    open_app(page, admin_url)

    for wo, day in [("900", 12), ("901", 14), ("902", 16), ("903", 18), ("900", 20), ("901", 5)]:
        drag_event(page, wo, month_day(day))

    got = working_dates(page)
    assert got["900"] == [iso(20)]
    assert got["901"] == [iso(5)]
    assert got["902"] == [iso(16)]
    assert got["903"] == [iso(18)]


def test_dropped_event_never_jumps_back(page, fake_db, admin_url):
    """After a drop, the event must stay on the new day; it must not flicker back."""
    fake_db.reset([order(str(900 + i), month_day(5 + i)) for i in range(4)])
    open_app(page, admin_url)
    record_moves(page)

    plan = {"900": 12, "901": 14, "902": 16, "903": 18}
    for wo, day in plan.items():
        drag_event(page, wo, month_day(day))
        wait_for_app(page, 800)

    for wo, day in plan.items():
        assert moves(page, wo) == [iso(day)], f"WO {wo} was shown on {moves(page, wo)}"


def test_rapid_drags_all_register(page, fake_db, admin_url):
    fake_db.reset([order(str(900 + i), month_day(5 + i)) for i in range(6)])
    open_app(page, admin_url)

    plan = {str(900 + i): 12 + 2 * i for i in range(6)}
    for wo, day in plan.items():
        drag_event(page, wo, month_day(day), wait=False)
    wait_for_app(page, 1500)

    got = working_dates(page)
    assert {wo: got[wo] for wo in plan} == {wo: [iso(day)] for wo, day in plan.items()}


def test_repeat_move_is_not_ignored(page, fake_db, admin_url, tmp_path):
    """Drag to the 12th, change to the 15th another way, drag back to the 12th."""
    fake_db.reset([order("100", month_day(10))])
    open_app(page, admin_url)

    drag_event(page, "100", month_day(12))
    assert working_dates(page)["100"] == [iso(12)]

    sheet = tmp_path / "changed.xlsx"
    to_upload_frame([order("100", month_day(15))]).to_excel(sheet, index=False)
    upload(page, sheet)
    assert working_dates(page)["100"] == [iso(15)]

    drag_event(page, "100", month_day(12))
    assert working_dates(page)["100"] == [iso(12)]


def test_month_stays_after_save(page, fake_db, admin_url):
    later = (month_day(1) + timedelta(days=40)).replace(day=10)
    fake_db.reset([order("300", later), order("301", month_day(10))])
    open_app(page, admin_url)

    next_month(page)
    title = shown_month(page)
    drag_event(page, "300", later + timedelta(days=2))
    save(page)

    assert shown_month(page) == title
    assert saved_dates(fake_db)["300"] == [(later + timedelta(days=2)).isoformat()]


def test_save_confirmation_is_visible(page, fake_db, admin_url):
    fake_db.reset([order("100", month_day(10))])
    open_app(page, admin_url)
    drag_event(page, "100", month_day(12))
    save(page)
    assert page.get_by_text("Changes saved", exact=False).first.is_visible()
    assert saved_dates(fake_db)["100"] == [iso(12)]


def test_resizing_and_hourly_views_are_off(page, fake_db, admin_url):
    fake_db.reset([order("100", month_day(10))])
    open_app(page, admin_url)
    assert calendar(page).locator(".fc-event-resizer").count() == 0

    calendar(page).get_by_role("button", name="week").click()
    page.wait_for_timeout(300)
    assert calendar(page).locator(".fc-timegrid").count() == 0
    assert calendar(page).locator(".fc-daygrid").count() == 1


def test_more_than_1000_orders_load_completely(page, fake_db, admin_url):
    fake_db.reset(bulk_orders(1500))
    open_app(page, admin_url)
    got = working_dates(page)
    assert sum(len(v) for v in got.values()) == 1500


def test_save_refused_when_load_was_incomplete(page, fake_db, admin_url):
    """Without a way to page reliably, a partial load must never be saved over the full table."""
    next_year = month_day(1).replace(year=month_day(1).year + 1)
    fake_db.reset([order("900", month_day(10))] + bulk_orders(1500, start=next_year), has_id=False)
    open_app(page, admin_url)
    drag_event(page, "900", month_day(20))
    save(page)
    assert len(fake_db.orders()) == 1501
    assert page.get_by_text("not saved", exact=False).first.is_visible()


def test_duplicate_wo_drag_moves_only_that_order(page, fake_db, admin_url):
    fake_db.reset([order("500", month_day(5)), order("500", month_day(7), customer="Beta Industries")])
    open_app(page, admin_url)
    drag_event(page, "500", month_day(20), index=0)
    assert working_dates(page)["500"] == sorted([iso(7), iso(20)])


def test_failed_save_keeps_everything_and_can_be_retried(page, fake_db, admin_url):
    fake_db.reset([order("100", month_day(10)), order("101", month_day(11))])
    open_app(page, admin_url)
    drag_event(page, "100", month_day(12))

    fake_db.configure(fail_save=True)
    save(page)
    assert saved_dates(fake_db) == {"100": [iso(10)], "101": [iso(11)]}  # database untouched
    assert page.get_by_text("Saving failed", exact=False).first.is_visible()
    assert working_dates(page)["100"] == [iso(12)]  # the change is still pending

    fake_db.configure(fail_save=False)
    save(page)
    assert saved_dates(fake_db) == {"100": [iso(12)], "101": [iso(11)]}
    assert page.get_by_text("Changes saved", exact=False).first.is_visible()


def test_save_needs_database_setup(page, fake_db, admin_url):
    fake_db.reset([order("100", month_day(10))], has_save_function=False)
    open_app(page, admin_url)
    drag_event(page, "100", month_day(12))
    save(page)
    assert page.get_by_text("save_schedule.sql", exact=False).first.is_visible()
    assert saved_dates(fake_db) == {"100": [iso(10)]}


def test_two_people_cannot_overwrite_each_other(page, fake_db, admin_url, browser):
    fake_db.reset([order("100", month_day(10)), order("101", month_day(11))])
    other = browser.new_context(viewport={"width": 1400, "height": 1100}, accept_downloads=True).new_page()
    open_app(page, admin_url)
    open_app(other, admin_url)

    drag_event(page, "100", month_day(12))
    save(page)
    drag_event(other, "101", month_day(14))
    save(other)

    assert saved_dates(fake_db) == {"100": [iso(12)], "101": [iso(11)]}
    assert other.get_by_text("someone else saved", exact=False).first.is_visible()

    other.get_by_role("button", name="Reload latest").click()
    wait_for_app(other, 800)
    assert working_dates(other) == {"100": [iso(12)], "101": [iso(11)]}
    drag_event(other, "101", month_day(14))
    save(other)
    assert saved_dates(fake_db) == {"100": [iso(12)], "101": [iso(14)]}
    other.context.close()


def test_import_preview_then_replace(page, fake_db, admin_url, tmp_path):
    fake_db.reset([order("100", month_day(10)), order("101", month_day(11))])
    open_app(page, admin_url)

    sheet = tmp_path / "new.xlsx"
    to_upload_frame([order("100", month_day(15)), order("102", month_day(5)),
                     order("103", month_day(6)), order("103", month_day(7))]).to_excel(sheet, index=False)
    upload(page, sheet, confirm=False)

    def metric(label):
        return page.locator("[data-testid='stMetric']", has_text=label).locator("[data-testid='stMetricValue']").inner_text()

    assert (metric("New WOs"), metric("Changed WOs"), metric("Removed WOs"), metric("Duplicate WOs")) == ("2", "1", "1", "1")
    assert working_dates(page) == {"100": [iso(10)], "101": [iso(11)]}  # nothing replaced yet

    page.get_by_role("button", name="Replace schedule with this file").click()
    wait_for_app(page, 800)
    save(page)
    assert saved_dates(fake_db) == {"100": [iso(15)], "102": [iso(5)], "103": [iso(6), iso(7)]}


def test_import_with_blank_prices_and_dates_saves(page, fake_db, admin_url, tmp_path):
    """Real order books have orders without a price or a date yet."""
    fake_db.reset([order("100", month_day(10))])
    open_app(page, admin_url)
    sheet = tmp_path / "blanks.xlsx"
    to_upload_frame([order("200", month_day(5), price=None), order("201", None, price=None),
                     order("202", month_day(6), price=1500.0)]).to_excel(sheet, index=False)
    upload(page, sheet)
    save(page)

    assert page.get_by_text("Saving failed", exact=False).count() == 0
    saved = {r["wo"]: (r["scheduled_date"], r["price"]) for r in fake_db.orders()}
    assert saved == {"200": (iso(5), None), "201": (None, None), "202": (iso(6), 1500.0)}


def test_cancelled_import_changes_nothing(page, fake_db, admin_url, tmp_path):
    fake_db.reset([order("100", month_day(10))])
    open_app(page, admin_url)
    sheet = tmp_path / "new.xlsx"
    to_upload_frame([order("200", month_day(5))]).to_excel(sheet, index=False)
    upload(page, sheet, confirm=False)
    page.get_by_role("button", name="Cancel import").click()
    wait_for_app(page, 800)
    assert working_dates(page) == {"100": [iso(10)]}
    assert page.get_by_role("button", name="Replace schedule with this file").count() == 0


def test_clear_all_data(page, fake_db, admin_url):
    fake_db.reset([order("100", month_day(10)), order("101", month_day(11))])
    open_app(page, admin_url)
    page.get_by_text("Clear All Data").click()
    page.get_by_label("Enter password to confirm").fill(PASSWORD)
    page.get_by_role("button", name="Delete All Data").click()
    wait_for_app(page, 800)
    assert fake_db.orders() == []
    assert page.get_by_text("All data cleared").first.is_visible()


# ---------- calendar <-> table ----------

def test_table_edit_shows_on_calendar(page, fake_db, admin_url):
    fake_db.reset([order("100", month_day(10))])
    open_app(page, admin_url)

    open_table(page)
    edit_table_date(page, row=0, value=month_day(15))
    open_calendar(page)

    assert event_day(page, "100") == iso(15)
    assert working_dates(page)["100"] == [iso(15)]


def test_drag_table_edit_drag_back(page, fake_db, admin_url):
    """The reported sequence: drag to the 12th, set the 15th in the table, drag back to the 12th."""
    fake_db.reset([order("100", month_day(10))])
    open_app(page, admin_url)

    drag_event(page, "100", month_day(12))
    open_table(page)
    edit_table_date(page, row=0, value=month_day(15))
    open_calendar(page)
    assert event_day(page, "100") == iso(15)

    drag_event(page, "100", month_day(12))
    assert working_dates(page)["100"] == [iso(12)]
    assert event_day(page, "100") == iso(12)


def test_table_edit_survives_later_drags(page, fake_db, admin_url):
    """An earlier drag must never be re-applied over a newer table edit."""
    fake_db.reset([order("100", month_day(10)), order("101", month_day(3))])
    open_app(page, admin_url)

    drag_event(page, "100", month_day(12))
    open_table(page)
    edit_table_date(page, row=0, value=month_day(15))  # sorted newest first: WO 100 is the top row
    open_calendar(page)

    drag_event(page, "101", month_day(20))
    drag_event(page, "101", month_day(21))
    got = working_dates(page)
    assert got["100"] == [iso(15)]
    assert got["101"] == [iso(21)]
    assert event_day(page, "100") == iso(15)


def test_month_stays_after_visiting_table(page, fake_db, admin_url):
    later = (month_day(1) + timedelta(days=40)).replace(day=10)
    fake_db.reset([order("300", later), order("301", month_day(10))])
    open_app(page, admin_url)

    next_month(page)
    title = shown_month(page)
    drag_event(page, "300", later + timedelta(days=2))
    open_table(page)
    open_calendar(page)

    assert shown_month(page) == title


def test_filtered_table_edit_leaves_hidden_orders_alone(page, fake_db, admin_url):
    fake_db.reset([
        order("500", month_day(5)),
        order("500", month_day(7), customer="Beta Industries"),
        order("", None, customer="No WO Co"),
        order("", month_day(9), customer="Other Co"),
    ])
    open_app(page, admin_url)
    open_table(page)
    filter_customer(page, "Acme")
    edit_table_date(page, row=0, value=month_day(15))
    save(page)

    assert saved_dates(fake_db) == {"500": [iso(7), iso(15)], "": ["", iso(9)]}


def test_deleting_every_shown_row_deletes_them(page, fake_db, admin_url):
    fake_db.reset([order("500", month_day(5)), order("500", month_day(7), customer="Beta Industries")])
    open_app(page, admin_url)
    open_table(page)
    filter_customer(page, "Acme")
    delete_table_row(page, row=0)
    save(page)

    rows = fake_db.orders()
    assert [(r["wo"], r["customer_name"]) for r in rows] == [("500", "Beta Industries")]
