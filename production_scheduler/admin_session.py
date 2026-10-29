"""The admin pages' shared working copy of the order book.

Both admin pages (calendar and table) edit the same copy, kept in
st.session_state:

- ``df``: the working copy that drags, table edits and imports change
- ``saved_df``: the orders as last loaded or saved; a save sends only the differences
- ``data_version``: the database version ``saved_df`` came from
- ``load_problem`` / ``save_error``: messages that stay on screen until resolved
"""

import streamlit as st
from supabase import Client, create_client

from production_scheduler import order_book
from production_scheduler.feedback import flash, show_flash

CONFLICT_MESSAGE = (
    "❌ Changes not saved: someone else saved the schedule after you loaded it, and saving now "
    "would overwrite their work. Your changes are still here. Download them if you need a copy, "
    "then click **Reload latest from database** and make them again."
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
    if "df" not in st.session_state:
        with st.spinner("Loading saved data..."):
            _load()
    defaults = {
        "df_version": 0,
        "has_unsaved_changes": False,
        "last_applied_change": None,
        "save_error": None,
        "calendar_view": {},
        "pending_import": None,
        "last_uploaded_signature": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _load() -> None:
    loaded = order_book.load(get_client())
    st.session_state.df = loaded.df
    st.session_state.saved_df = loaded.df.copy()
    st.session_state.data_version = loaded.version
    st.session_state.last_uploaded_name = loaded.uploaded_name
    st.session_state.load_problem = loaded.problem
    st.session_state.save_error = None
    st.session_state.has_unsaved_changes = False


def reload() -> None:
    """Replace the working copy with the latest saved orders (unsaved changes are dropped)."""
    _load()
    st.session_state.df_version += 1  # new calendar key: starts a fresh drag history


def save(done_message: str | None = None) -> bool:
    """Save the working copy.

    On success the latest orders are reloaded and the page re-runs. On failure
    the working copy is left as it is, ``save_error`` explains what happened,
    and False is returned.
    """
    if st.session_state.load_problem:
        st.session_state.save_error = f"❌ Changes not saved. {st.session_state.load_problem}"
        return False
    changes = order_book.diff(st.session_state.saved_df, st.session_state.df, st.session_state.last_uploaded_name)
    if not changes:
        st.session_state.has_unsaved_changes = False
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
            f"❌ Saving failed ({err}). Nothing was changed in the database. "
            "Your changes are still here; click **Update Changes** to try again."
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


def reload_button(key: str) -> None:
    if st.button("🔄 Reload latest from database", key=key, help="Unsaved changes on this device are dropped."):
        reload()
        flash("Reloaded the latest saved schedule.", "info")
        st.rerun()
