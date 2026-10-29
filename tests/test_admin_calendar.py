"""Browser tests for the admin calendar and its link to the working data.

Each test describes how the app should behave. Tests marked ``xfail`` document
known defects that later steps of the repair plan fix; remove the marker when
the fix lands (``strict=True`` makes the suite fail as a reminder).
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from sample_data import bulk_orders, month_day, order, to_upload_frame
from ui import (
    apply_table,
    calendar,
    drag_event,
    edit_table_date,
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
    fake_db.reset(bulk_orders(1500), has_id=False)
    open_app(page, admin_url)
    save(page)
    assert len(fake_db.orders()) == 1500
    assert page.get_by_text("not saved", exact=False).first.is_visible()


@pytest.mark.xfail(strict=True, reason="Step 3: orders are identified by WO, so duplicates move together")
def test_duplicate_wo_drag_moves_only_that_order(page, fake_db, admin_url):
    fake_db.reset([order("500", month_day(5)), order("500", month_day(7), customer="Beta Industries")])
    open_app(page, admin_url)
    drag_event(page, "500", month_day(20), index=0)
    assert working_dates(page)["500"] == sorted([iso(7), iso(20)])


@pytest.mark.xfail(strict=True, reason="Step 4: saving deletes everything before re-inserting")
def test_failed_save_keeps_existing_data(page, fake_db, admin_url):
    fake_db.reset([order("100", month_day(10)), order("101", month_day(11))])
    open_app(page, admin_url)
    drag_event(page, "100", month_day(12))
    fake_db.configure(fail_insert_after=0)
    save(page)
    assert len(fake_db.orders()) == 2


# ---------- calendar <-> table ----------

def test_table_edit_shows_on_calendar(page, fake_db, admin_url):
    fake_db.reset([order("100", month_day(10))])
    open_app(page, admin_url)

    open_table(page)
    edit_table_date(page, row=0, value=month_day(15))
    apply_table(page)
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
    apply_table(page)
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
    apply_table(page)
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
