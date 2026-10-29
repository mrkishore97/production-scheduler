"""Browser tests for the token-based customer portal."""

from __future__ import annotations

import pandas as pd
import pytest

from sample_data import bulk_orders, month_day, order
from ui import calendar, wait_for_app

pytestmark = pytest.mark.e2e


def open_portal(page, url: str) -> None:
    page.goto(f"{url}/?token=acme-token")
    wait_for_app(page)
    calendar(page).locator(".fc-daygrid-body").wait_for()
    wait_for_app(page, 800)


def test_clicking_an_event_does_not_reload_the_page(page, fake_db, customer_url):
    fake_db.reset([order("100", month_day(10)), order("200", month_day(12), customer="Beta Industries")])
    open_portal(page, customer_url)

    # A full page run reads the schedule's version and save time together; the
    # background check for newer saves reads only the version, so it isn't counted.
    full_runs = "app_meta?select=key,value"
    before = fake_db.reads(full_runs)
    calendar(page).locator(".fc-event").first.click()
    calendar(page).locator("td.fc-daygrid-day").nth(20).click()
    wait_for_app(page, 800)
    assert fake_db.reads(full_runs) == before


def test_more_than_1000_orders_are_shown(page, fake_db, customer_url):
    rows = bulk_orders(1500)
    fake_db.reset(rows)
    open_portal(page, customer_url)

    with page.expect_download() as info:
        page.get_by_role("button", name="Download Excel").click()
    mine = pd.read_excel(info.value.path())
    assert len(mine) == sum(1 for r in rows if r["customer_name"] == "Acme Corp")
