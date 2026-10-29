"""The admin pages' shared working copy of the order book.

Both admin pages edit the same copy, kept in st.session_state:

- ``df``: the working copy that drags, table edits and imports change
- ``saved_df``: the orders as last loaded or saved; a save sends only the differences
- ``data_version`` / ``saved_at``: the database version ``saved_df`` came from, and when it was saved
- ``load_problem`` / ``save_error``: messages that stay on screen until resolved
- ``undo_stack``: earlier working copies, newest last

Every edit goes through ``change()``, which counts it in ``data_rev``. Views
use the count to know when to redraw, and calendar events carry it so a drag
message is only ever applied once (see calendar_sync).
"""

import pandas as pd
import streamlit as st
from supabase import Client, create_client

from production_scheduler import order_book
from production_scheduler.feedback import flash, show_flash

UNDO_LIMIT = 20

CONFLICT_MESSAGE = (
    "❌ Changes not saved: someone else saved the schedule after you loaded it, and saving now "
    "would overwrite their work. Your changes are still here. Download them if you need a copy, "
    "then click **Reload latest** and make them again."
)
SETUP_MESSAGE = (
    "❌ Changes not saved: the database needs a one-time setup for safe saving. Run "
    "`db/save_schedule.sql` in the Supabase SQL Editor (see README). Your changes are still here."
)


@st.cache_resource
def get_client() -> Client:
    """Cached Supabase client — created once per app lifetime."""
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])


def init() -> None:
    """Load the order book on a session's first run and set defaults."""
    defaults = {
        "data_rev": 0,
        "undo_stack": [],
        "last_applied_change": None,
        "save_error": None,
        "calendar_view": {},
        "pending_import": None,
        "last_uploaded_signature": None,
        "unlocked": False,
        "saved_at": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value
    if "df" not in st.session_state:
        with st.spinner("Loading saved data..."):
            _load()


def _load() -> None:
    loaded = order_book.load(get_client())
    st.session_state.df = loaded.df
    st.session_state.saved_df = loaded.df.copy()
    st.session_state.data_version = loaded.version
    st.session_state.saved_at = loaded.saved_at
    st.session_state.last_uploaded_name = loaded.uploaded_name
    st.session_state.load_problem = loaded.problem
    st.session_state.save_error = None


def reload() -> None:
    """Replace the working copy with the latest saved orders (unsaved changes are dropped)."""
    _load()
    st.session_state.undo_stack = []
    st.session_state.data_rev += 1


# ---------------- Editing ----------------

def change(new_df: pd.DataFrame) -> None:
    """Make ``new_df`` the working copy, remembering the old one for Undo."""
    stack = st.session_state.undo_stack
    stack.append(st.session_state.df)
    del stack[:-UNDO_LIMIT]
    st.session_state.df = new_df
    st.session_state.data_rev += 1


def undo() -> None:
    if st.session_state.undo_stack:
        st.session_state.df = st.session_state.undo_stack.pop()
        st.session_state.data_rev += 1


def discard() -> None:
    """Go back to the saved schedule (can itself be undone)."""
    change(st.session_state.saved_df.copy())


def pending() -> order_book.Changes:
    """Unsaved changes in the working copy."""
    return order_book.diff(st.session_state.saved_df, st.session_state.df, st.session_state.last_uploaded_name)


# ---------------- Table edits ----------------
# The table editor reports its edits relative to the rows it was given, so
# those rows ("shown") and the working copy they came from ("base") are kept
# until something else changes the data or the filters change.

def table_snapshot(where: str) -> dict | None:
    return st.session_state.get(f"table_snapshot_{where}")


def reset_table(where: str, shown: pd.DataFrame, filters) -> dict:
    """Give the table fresh rows (and a new editor key, so old edits can't be re-applied)."""
    old = table_snapshot(where)
    snap = {
        "key": f"table_{where}_{(old['n'] + 1) if old else 0}",
        "n": (old["n"] + 1) if old else 0,
        "base": st.session_state.df,
        "shown": shown,
        "filters": filters,
        "rev": st.session_state.data_rev,
    }
    st.session_state[f"table_snapshot_{where}"] = snap
    return snap


def fold_table_edits(where: str) -> None:
    """Apply the table's edits to the working copy. Run before anything is drawn."""
    snap = table_snapshot(where)
    delta = st.session_state.get(snap["key"]) if snap else None
    if not delta or not any(delta.get(k) for k in ("edited_rows", "added_rows", "deleted_rows")):
        return
    if snap["rev"] != st.session_state.data_rev:
        return  # the data changed some other way since; the table is about to be redrawn
    edited = order_book.clean_rows(order_book.apply_table_delta(snap["shown"], delta))
    # A row needs at least a WO, customer or model to count as an order.
    meaningful = edited[["WO", "Customer Name", "Model Description"]].ne("").any(axis=1)
    new_df = order_book.merge_edits(snap["base"], snap["shown"][order_book.ID], edited[meaningful])
    if not order_book.same_orders(st.session_state.df, new_df):
        change(new_df)
        snap["rev"] = st.session_state.data_rev  # its own edit: keep the table as it is


# ---------------- Saving ----------------

def save(done_message: str | None = None) -> bool:
    """Save the working copy.

    On success the latest orders are reloaded and the page re-runs. On failure
    the working copy is left as it is, ``save_error`` explains what happened,
    and False is returned.
    """
    if st.session_state.load_problem:
        st.session_state.save_error = f"❌ Changes not saved. {st.session_state.load_problem}"
        return False
    changes = pending()
    if not changes:
        st.session_state.save_error = None
        flash("Nothing to save: the database already matches.", "info")
        st.rerun()
    try:
        order_book.save(get_client(), changes, st.session_state.data_version)
    except order_book.SaveConflict:
        st.session_state.save_error = CONFLICT_MESSAGE
        return False
    except order_book.SaveSetupMissing:
        st.session_state.save_error = SETUP_MESSAGE
        return False
    except Exception as err:
        st.session_state.save_error = (
            f"❌ Saving failed ({getattr(err, 'message', None) or err}). Nothing was changed in the database. "
            "Your changes are still here; click **Save schedule** to try again."
        )
        return False
    reload()
    flash(done_message or f"✅ Changes saved to database successfully! ({changes.summary()})")
    st.rerun()


def show_status() -> None:
    """Messages that belong at the top of every admin page."""
    show_flash()
    if st.session_state.load_problem:
        st.error(st.session_state.load_problem)
    if st.session_state.save_error:
        st.error(st.session_state.save_error)
