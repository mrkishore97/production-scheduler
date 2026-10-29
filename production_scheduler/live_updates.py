"""Keeping open pages in step with saves made elsewhere."""

from collections.abc import Callable

import pandas as pd
import streamlit as st

DEFAULT_REFRESH_SECONDS = 30


def refresh_seconds() -> int:
    """How often open pages check for a newer saved schedule (secret REFRESH_SECONDS)."""
    try:
        return max(1, int(st.secrets.get("REFRESH_SECONDS", DEFAULT_REFRESH_SECONDS)))
    except Exception:
        return DEFAULT_REFRESH_SECONDS


def format_time(value) -> str | None:
    """A database timestamp in the viewer's time zone, e.g. "Oct 29, 2026 14:05"."""
    if not value:
        return None
    try:
        ts = pd.Timestamp(value)
    except (TypeError, ValueError):
        return None
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    tz = st.context.timezone
    try:
        return ts.tz_convert(tz).strftime("%b %d, %Y %H:%M")
    except Exception:
        return ts.tz_convert("UTC").strftime("%b %d, %Y %H:%M UTC")


def watch_for_updates(current_version: Callable[[], str], shown_version: str) -> None:
    """Re-run the page once the saved schedule is newer than the one shown.

    For read-only pages, where redrawing can't lose anyone's work.
    """
    def check():
        if current_version() != shown_version:
            st.rerun()

    st.fragment(check, run_every=refresh_seconds())()
