"""Browser tests for the single Schedule page (step 5) and live updates (step 6)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from supabase import create_client

from production_scheduler import order_book
from sample_data import month_day, order
from ui import (
    click,
    drag_event,
    edit_table_date,
    event_day,
    next_month,
    open_app,
    filter_customer,
    pending_text,
    save,
    saved_dates,
    shown_month,
    table_rows,
    wait_for_app,
    working_dates,
)

pytestmark = pytest.mark.e2e


def iso(day: int) -> str:
    return month_day(day).isoformat()


def dates_in_table(page) -> dict[str, str]:
    return {r["WO"]: r["Scheduled Date"][:10] for r in table_rows(page)}


# ---------- step 5: one page, one edit flow ----------

def test_drag_shows_in_table_on_same_page(page, fake_db, admin_url):
    fake_db.reset([order("100", month_day(10)), order("101", month_day(11))])
    open_app(page, admin_url)
    drag_event(page, "100", month_day(12))
    assert dates_in_table(page) == {"100": iso(12), "101": iso(11)}


def test_table_edit_shows_on_calendar_without_changing_month(page, fake_db, admin_url):
    later = (month_day(1) + timedelta(days=40)).replace(day=10)
    fake_db.reset([order("300", later), order("301", month_day(10))])
    open_app(page, admin_url)
    next_month(page)
    title = shown_month(page)

    edit_table_date(page, row=0, value=later + timedelta(days=5))  # newest first: WO 300 is the top row

    assert event_day(page, "300") == (later + timedelta(days=5)).isoformat()
    assert shown_month(page) == title
    assert working_dates(page)["300"] == [(later + timedelta(days=5)).isoformat()]


def test_drag_then_table_edit_then_drag_back_on_same_page(page, fake_db, admin_url):
    fake_db.reset([order("100", month_day(10))])
    open_app(page, admin_url)
    drag_event(page, "100", month_day(12))
    edit_table_date(page, row=0, value=month_day(15))
    assert event_day(page, "100") == iso(15)
    drag_event(page, "100", month_day(12))
    assert dates_in_table(page) == {"100": iso(12)}
    assert event_day(page, "100") == iso(12)


def test_pending_changes_undo_and_discard(page, fake_db, admin_url):
    fake_db.reset([order("100", month_day(10)), order("101", month_day(11))])
    open_app(page, admin_url)
    assert "No unsaved changes" in page.get_by_text("No unsaved changes").first.inner_text()

    drag_event(page, "100", month_day(12))
    drag_event(page, "101", month_day(14))
    assert pending_text(page).startswith("⚠️ 2 unsaved changes")
    page.get_by_text("Show unsaved changes").click()
    assert page.get_by_text(f"Scheduled Date: {iso(10)} → {iso(12)}").first.is_visible()

    click(page, "Undo")
    assert event_day(page, "101") == iso(11)
    assert pending_text(page).startswith("⚠️ 1 unsaved change")

    click(page, "Discard changes")
    assert event_day(page, "100") == iso(10)
    assert page.get_by_text("No unsaved changes").first.is_visible()

    click(page, "Undo")  # discarding can be undone too
    assert event_day(page, "100") == iso(12)
    assert saved_dates(fake_db) == {"100": [iso(10)], "101": [iso(11)]}  # nothing saved meanwhile


def test_password_is_asked_once_per_session(page, fake_db, admin_url):
    fake_db.reset([order("100", month_day(10))])
    open_app(page, admin_url)
    drag_event(page, "100", month_day(12))
    save(page)
    assert page.get_by_label("Password", exact=True).count() == 0

    drag_event(page, "100", month_day(14))
    click(page, "Save schedule")
    assert saved_dates(fake_db) == {"100": [iso(14)]}


def test_clear_filters_and_sort_order(page, fake_db, admin_url):
    fake_db.reset([order("100", month_day(10)), order("101", month_day(11), customer="Beta Industries"),
                   order("102", month_day(12))])
    open_app(page, admin_url)

    filter_customer(page, "Beta")
    assert set(dates_in_table(page)) == {"101"}
    click(page, "Clear All Filters")
    assert set(dates_in_table(page)) == {"100", "101", "102"}

    page.get_by_label("Sort Order").click()
    page.get_by_role("option", name="Ascending (Oldest First)").click()
    wait_for_app(page)
    assert [r["WO"] for r in table_rows(page)] == ["100", "101", "102"]
    edit_table_date(page, row=0, value=month_day(20))  # top row is now the oldest order
    assert working_dates(page)["100"] == [iso(20)]


def test_filters_survive_edits(page, fake_db, admin_url):
    fake_db.reset([order("100", month_day(10)), order("101", month_day(11), customer="Beta Industries")])
    open_app(page, admin_url)
    filter_customer(page, "Beta")
    edit_table_date(page, row=0, value=month_day(20))
    drag_event(page, "100", month_day(5))
    assert dates_in_table(page) == {"101": iso(20)}


def test_table_view_page_edits_the_same_copy(page, fake_db, admin_url):
    fake_db.reset([order("100", month_day(10))])
    open_app(page, admin_url)
    drag_event(page, "100", month_day(12))
    page.get_by_role("link", name="table view").click()
    wait_for_app(page, 800)
    assert pending_text(page).startswith("⚠️ 1 unsaved change")
    assert dates_in_table(page) == {"100": iso(12)}
    edit_table_date(page, row=0, value=month_day(15))
    page.get_by_role("link", name="app", exact=True).click()
    wait_for_app(page, 800)
    assert event_day(page, "100") == iso(15)


# ---------- step 6: other sessions and customers ----------

def save_elsewhere(fake_db, wo: str, new_date) -> None:
    """Save a change the way another admin's session would."""
    client = create_client(fake_db.url, "fake.test.key")
    loaded = order_book.load(client)
    working = loaded.df.copy()
    working.loc[working["WO"] == wo, "Scheduled Date"] = new_date
    order_book.save(client, order_book.diff(loaded.df, working), loaded.version)


def test_last_saved_time_is_shown(page, fake_db, admin_url):
    fake_db.reset([order("100", month_day(10))])
    open_app(page, admin_url)
    drag_event(page, "100", month_day(12))
    save(page)
    assert page.get_by_text("Database last saved").first.is_visible()


def test_banner_when_someone_else_saves_keeps_unsaved_work(page, fake_db, admin_url):
    fake_db.reset([order("100", month_day(10)), order("101", month_day(11))])
    open_app(page, admin_url)
    drag_event(page, "101", month_day(14))  # unsaved work here

    save_elsewhere(fake_db, "100", month_day(12))
    banner = page.get_by_text("saved by someone else")
    banner.first.wait_for(timeout=10_000)  # appears without any click (checks every 2 s in tests)
    assert "1 unsaved change" in banner.first.inner_text()
    assert working_dates(page) == {"100": [iso(10)], "101": [iso(14)]}  # nothing replaced

    click(page, "Load their changes")
    assert working_dates(page) == {"100": [iso(12)], "101": [iso(11)]}
    assert page.get_by_text("saved by someone else").count() == 0


def test_customer_page_updates_after_a_save(page, fake_db, customer_url):
    fake_db.reset([order("100", month_day(10))])
    page.goto(f"{customer_url}/?token=acme-token")
    wait_for_app(page, 800)
    event = page.frame_locator("iframe[title='streamlit_calendar.calendar']").locator(".fc-event", has_text="100 |")
    assert event.evaluate("e => e.closest('td[data-date]').getAttribute('data-date')") == iso(10)

    save_elsewhere(fake_db, "100", month_day(12))
    page.wait_for_function(
        """() => {
            const f = document.querySelector("iframe[title='streamlit_calendar.calendar']");
            const e = f && [...f.contentDocument.querySelectorAll('.fc-event')].find(x => x.innerText.startsWith('100 |'));
            return e && e.closest('td[data-date]').getAttribute('data-date') === '%s';
        }""" % iso(12),
        timeout=15_000,
    )
    assert page.get_by_text("Schedule last updated").first.is_visible()
