"""Browser helpers for driving the Streamlit apps with Playwright."""

from __future__ import annotations

import re
from datetime import date

import pandas as pd

from conftest import PASSWORD


def wait_for_app(page, settle_ms: int = 400) -> None:
    """Wait until Streamlit has finished re-running the script."""
    page.wait_for_timeout(settle_ms)
    page.wait_for_selector("[data-testid='stApp'][data-test-script-state='notRunning']")
    page.wait_for_timeout(200)


def open_app(page, url: str) -> None:
    page.goto(url)
    page.wait_for_selector("[data-testid='stApp'][data-test-connection-state='CONNECTED']")
    wait_for_app(page)
    calendar(page).locator(".fc-daygrid-body").wait_for()


def calendar(page):
    return page.frame_locator("iframe[title='streamlit_calendar.calendar']")


def event(page, wo: str):
    """The calendar event whose title starts with this WO number."""
    return calendar(page).locator(".fc-event", has_text=re.compile(rf"^{re.escape(wo)} \|"))


def day_cell(page, day: date):
    return calendar(page).locator(f"td.fc-daygrid-day[data-date='{day.isoformat()}']")


def drag_event(page, wo: str, target: date, wait: bool = True, index: int = 0) -> None:
    """Drag an event onto another day, moving the mouse the way a person would."""
    page.locator("iframe[title='streamlit_calendar.calendar']").evaluate("el => el.scrollIntoView({block: 'start'})")
    src = event(page, wo).nth(index).bounding_box()
    dst = day_cell(page, target).bounding_box()
    assert src and dst, f"could not find event {wo} or day {target}"
    x0, y0 = src["x"] + src["width"] / 2, src["y"] + src["height"] / 2
    x1, y1 = dst["x"] + dst["width"] / 2, dst["y"] + dst["height"] * 0.6
    page.mouse.move(x0, y0)
    page.mouse.down()
    page.mouse.move(x0 + 8, y0 + 8, steps=4)
    page.mouse.move(x1, y1, steps=12)
    page.mouse.up()
    if wait:
        wait_for_app(page)


def shown_month(page) -> str:
    return calendar(page).locator(".fc-toolbar-title").inner_text()


def next_month(page) -> None:
    calendar(page).locator(".fc-next-button").click()


# Records every on-screen day change of every event, frame by frame, so a test
# can see an event jump back to its old date even if only for a moment.
_RECORDER = """
() => {
  window.__moves = [];
  let last = null;
  const tick = () => {
    const now = {};
    document.querySelectorAll('.fc-event:not(.fc-event-mirror)').forEach(e => {
      const wo = (e.innerText.split(' |')[0] || '').trim();
      const td = e.closest('td[data-date]');
      if (wo && td) now[wo] = td.getAttribute('data-date');
    });
    if (last) for (const wo of Object.keys(now)) if (now[wo] !== last[wo]) window.__moves.push([wo, now[wo]]);
    last = Object.assign(last || {}, now);
    requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}
"""


def _calendar_frame(page):
    return next(f for f in page.frames if "streamlit_calendar" in f.url)


def record_moves(page) -> None:
    _calendar_frame(page).evaluate(_RECORDER)


def moves(page, wo: str) -> list[str]:
    """Days this event has been shown on since recording started (in order)."""
    return [d for w, d in _calendar_frame(page).evaluate("window.__moves") if w == wo]


def upload(page, path, confirm: bool = True) -> None:
    """Upload a spreadsheet; with ``confirm``, accept the import preview."""
    page.locator("[data-testid='stSidebar'] input[type='file']").set_input_files(str(path))
    wait_for_app(page, settle_ms=1000)
    if confirm:
        page.get_by_role("button", name="Replace schedule with this file").click()
        wait_for_app(page, settle_ms=800)


def save(page, password: str = PASSWORD) -> None:
    """Enter the password and click Update Changes on the calendar page."""
    field = page.get_by_label("Password", exact=True)
    if not field.is_visible():
        page.get_by_text("Update Changes (Password Protected)").click()
    field.fill(password)
    page.get_by_role("button", name="Update Changes").click()
    wait_for_app(page, settle_ms=800)


def working_dates(page) -> dict[str, list[str]]:
    """Scheduled dates in the app's working data, read from the Download XLSX button."""
    with page.expect_download() as info:
        page.get_by_role("button", name="Download XLSX").click()
    frame = pd.read_excel(info.value.path(), dtype={"WO": str})
    out: dict[str, list[str]] = {}
    for wo, d in zip(frame["WO"].fillna(""), frame["Scheduled Date"]):
        out.setdefault(str(wo), []).append("" if pd.isna(d) else pd.Timestamp(d).date().isoformat())
    return {k: sorted(v) for k, v in out.items()}


def saved_dates(db) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for row in db.orders():
        out.setdefault(str(row["wo"]), []).append(row["scheduled_date"] or "")
    return {k: sorted(v) for k, v in out.items()}


# ---------- table page ----------
TABLE_COLUMNS = [
    "WO", "Quote", "PO Number", "Status", "Customer Name",
    "Model Description", "Scheduled Date", "Completion Date", "Price",
]


def open_table(page) -> None:
    page.get_by_role("link", name="table view").click()
    wait_for_app(page, 800)
    page.locator("[data-testid='stDataFrame']").first.wait_for()


def open_calendar(page) -> None:
    page.get_by_role("link", name="app", exact=True).click()
    wait_for_app(page, 800)
    calendar(page).locator(".fc-daygrid-body, .fc-list").first.wait_for()


def edit_table_date(page, row: int, value: date, column: str = "Scheduled Date") -> None:
    """Type a new date into a cell of the (canvas-drawn) table, using the keyboard.

    ``row`` counts from the top of the table as currently sorted.
    """
    grid = page.locator("[data-testid='stDataFrame']").first
    grid.scroll_into_view_if_needed()
    box = grid.bounding_box()
    page.mouse.click(box["x"] + 60, box["y"] + 35 + 17)  # first data cell: WO, top row
    for _ in range(TABLE_COLUMNS.index(column)):
        page.keyboard.press("ArrowRight")
    for _ in range(row):
        page.keyboard.press("ArrowDown")
    page.keyboard.press("Enter")
    field = page.locator("input[type='date']").first
    field.fill(value.isoformat())
    field.press("Enter")
    page.wait_for_timeout(300)


def apply_table(page) -> None:
    page.get_by_role("button", name="Apply Changes").click()
    wait_for_app(page, 800)


def event_day(page, wo: str) -> str:
    """The day an event is currently drawn on, as shown on screen."""
    return event(page, wo).first.evaluate("e => e.closest('td[data-date]').getAttribute('data-date')")


def filter_customer(page, text: str) -> None:
    page.get_by_text("Filter Options").click()
    field = page.get_by_label("Customer", exact=True)
    field.fill(text)
    field.press("Enter")
    wait_for_app(page, 800)


def delete_table_row(page, row: int) -> None:
    """Select a table row by its left-hand marker and delete it."""
    grid = page.locator("[data-testid='stDataFrame']").first
    grid.scroll_into_view_if_needed()
    box = grid.bounding_box()
    page.mouse.click(box["x"] + 18, box["y"] + 35 + 17 + 35 * row)
    page.keyboard.press("Delete")
    page.wait_for_timeout(300)


def save_on_table(page, password: str = PASSWORD) -> None:
    field = page.get_by_label("Password", exact=True)
    if not field.is_visible():
        page.get_by_text("Password Protected Update").click()
    field.fill(password)
    page.get_by_role("button", name="Update Changes").click()
    wait_for_app(page, settle_ms=800)
