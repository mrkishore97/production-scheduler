"""Turning calendar drag-and-drop messages into changes to the working data.

The calendar component hands back its *last* message on every rerun, not just
once, so each drag must be applied once and then ignored. Every event carries
the data revision it was drawn from (``extendedProps.rev``); a drag is
identified by that revision plus the event's id and its old and new dates. A
repeat of the same message is skipped, while a new drag, even back to a date
used before, comes from a newer revision and is applied.
"""

from dataclasses import dataclass
from datetime import date

import pandas as pd


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
        view_date=_middle_day(view.get("currentStart"), view.get("currentEnd")),
    )


def apply_drag(df: pd.DataFrame, change: DragChange) -> bool:
    """Set the dragged order's Scheduled Date in place; return True if it changed."""
    mask = df["id"].astype(str) == change.event_id
    if not mask.any():
        return False
    if df["Scheduled Date"].dtype != object:
        # A column of only blank dates is stored as timestamps, which reject plain dates.
        df["Scheduled Date"] = df["Scheduled Date"].astype(object)
    if (df.loc[mask, "Scheduled Date"] == change.new_date).all():
        return False
    df.loc[mask, "Scheduled Date"] = change.new_date
    return True


def _middle_day(start, end) -> date | None:
    # The view reports its range in UTC; the middle of the range is inside the
    # shown month/week whatever the viewer's time zone.
    s = pd.to_datetime(start, errors="coerce", utc=True)
    e = pd.to_datetime(end, errors="coerce", utc=True)
    if pd.isna(s) or pd.isna(e):
        return None
    return (s + (e - s) / 2).date()
