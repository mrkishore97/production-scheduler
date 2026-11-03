"""Turning calendar messages (drops, clicks on orders, clicks on days) into changes.

The calendar component hands back its *last* message on every rerun, not just
once, so each message must be applied once and then ignored. Every event
carries the revision it was drawn from (``extendedProps.rev``); a drag is
identified by that revision plus the event's id and its old and new dates. A
repeat of the same message is skipped, while a new drag, even back to a date
used before, comes from a newer revision and is applied. Clicks work the same
way, which is what lets an order be cut and then pasted on a day in any month.
"""

from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

ID = "id"


@dataclass(frozen=True)
class DragChange:
    event_id: str  # the order's row id
    wo: str
    rev: str  # data revision the dragged event was drawn from
    old_start: str
    new_start: str
    new_date: date
    view_type: str | None = None
    view_date: date | None = None  # a day inside the period the calendar was showing

    def signature(self) -> tuple:
        return (self.event_id, self.rev, self.old_start, self.new_start)


def parse_event_change(state) -> DragChange | None:
    """Read an ``eventChange`` message from the calendar component, if there is one."""
    if not state or state.get("callback") != "eventChange":
        return None
    payload = state.get("eventChange") or {}
    new = payload.get("event") or {}
    old = payload.get("oldEvent") or {}
    event_id = str(new.get("id", "")).strip()
    new_dt = pd.to_datetime(new.get("start"), errors="coerce")
    if not event_id or pd.isna(new_dt):
        return None
    view = payload.get("view") or {}
    return DragChange(
        event_id=event_id,
        wo=str((new.get("extendedProps") or {}).get("wo", "")),
        rev=str((old.get("extendedProps") or {}).get("rev", "")),
        old_start=str(old.get("start", "")),
        new_start=str(new.get("start")),
        new_date=new_dt.date(),
        view_type=view.get("type"),
        view_date=_day_in_view(view.get("currentStart"), view.get("currentEnd")),
    )


@dataclass(frozen=True)
class EventClick:
    event_id: str
    rev: str

    def signature(self) -> tuple:
        return ("event", self.event_id, self.rev)


@dataclass(frozen=True)
class DayClick:
    day: date
    raw: str  # exactly as reported, so a repeat of the same message is recognised
    view_type: str | None = None
    view_date: date | None = None

    def signature(self) -> tuple:
        return ("day", self.raw, self.view_type, self.view_date)


def parse_click(state, timezone: str | None = None) -> EventClick | DayClick | None:
    """Read a click on an order (``eventClick``) or on a day (``dateClick``)."""
    if not state:
        return None
    if state.get("callback") == "eventClick":
        event = (state.get("eventClick") or {}).get("event") or {}
        event_id = str(event.get("id", "")).strip()
        if not event_id:
            return None
        return EventClick(event_id, str((event.get("extendedProps") or {}).get("rev", "")))
    if state.get("callback") == "dateClick":
        info = state.get("dateClick") or {}
        day = _clicked_day(info.get("date"), timezone)
        if day is None:
            return None
        view = info.get("view") or {}
        return DayClick(day, str(info.get("date")), view.get("type"),
                        _day_in_view(view.get("currentStart"), view.get("currentEnd")))
    return None


def move_order(df: pd.DataFrame, order_id: str, day: date) -> bool:
    """Set an order's Scheduled Date in place; return True if it changed."""
    mask = df[ID].astype(str) == order_id
    if not mask.any():
        return False
    if df["Scheduled Date"].dtype != object:
        # A column of only blank dates is stored as timestamps, which reject plain dates.
        df["Scheduled Date"] = df["Scheduled Date"].astype(object)
    if (df.loc[mask, "Scheduled Date"] == day).all():
        return False
    df.loc[mask, "Scheduled Date"] = day
    return True


def apply_drag(df: pd.DataFrame, change: DragChange) -> bool:
    """Set the dragged order's Scheduled Date in place; return True if it changed."""
    return move_order(df, change.event_id, change.new_date)


def _clicked_day(value, timezone: str | None) -> date | None:
    # The calendar reports the clicked day as local midnight written in UTC
    # (Nov 5 in India is "2026-11-04T18:30Z"). Convert back to the viewer's
    # time zone; without one, round to the nearest midnight (right for UTC-12..+12).
    ts = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(ts):
        return None
    if timezone:
        try:
            return ts.tz_convert(timezone).date()
        except Exception:
            pass
    return (ts.to_pydatetime() + timedelta(hours=12)).date()


def _day_in_view(start, end) -> date | None:
    # The view reports its range in UTC. A little after its start (a day, or
    # half the range for a one-day view) is inside the shown period whatever
    # the viewer's time zone, and is where the view should reopen.
    s = pd.to_datetime(start, errors="coerce", utc=True)
    e = pd.to_datetime(end, errors="coerce", utc=True)
    if pd.isna(s) or pd.isna(e):
        return None
    s, e = s.to_pydatetime(), e.to_pydatetime()
    return (s + min(timedelta(days=1), (e - s) / 2)).date()
