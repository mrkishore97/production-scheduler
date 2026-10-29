"""Page pieces shared by the admin pages: save bar, orders table, update banner."""

from datetime import datetime

import pandas as pd
import streamlit as st

from production_scheduler import admin_session, order_book
from production_scheduler.feedback import flash
from production_scheduler.live_updates import format_time, refresh_seconds
from production_scheduler.supabase_io import read_meta

SORT_NEWEST = "Descending (Newest First)"
SORT_OLDEST = "Ascending (Oldest First)"
FILTER_DEFAULTS = {
    "quote": "", "quote_match": "Contains",
    "po": "", "po_match": "Contains",
    "status": "All", "status_match": "Contains",
    "customer": "", "customer_match": "Contains",
    "model": "", "model_match": "Contains",
    "date_type": "None",
    "sort": SORT_NEWEST,
}
DATE_FILTERS = ("exact_date", "month", "year")  # only exist while their date filter is chosen


# ---------------- Save bar ----------------

def save_bar(where: str) -> None:
    """Unsaved-change count and list, with Save schedule, Undo, Discard and Reload."""
    ss = st.session_state
    changes = admin_session.pending()
    count = len(changes)
    with st.container(border=True):
        if count:
            st.markdown(f"**⚠️ {count} unsaved change{'s' if count != 1 else ''}** ({changes.summary()})")
            with st.expander("Show unsaved changes"):
                details = order_book.describe_changes(ss.saved_df, ss.df)
                for item in details[:100]:
                    st.markdown(f"- **WO {item['WO'] or '(none)'}** · {item['Customer'] or '—'}: {item['Change']}")
                if len(details) > 100:
                    st.caption(f"…and {len(details) - 100} more.")
        else:
            st.markdown("✅ **No unsaved changes**")
        saved = format_time(ss.saved_at)
        loaded = f"File: {ss.last_uploaded_name}. " if ss.last_uploaded_name else ""
        st.caption(f"{loaded}Database last saved {saved}." if saved else loaded)

        cols = st.columns([2, 1, 1, 1, 1])
        password = None
        if not ss.unlocked:
            password = cols[0].text_input(
                "Password", type="password", key=f"password_{where}",
                help="Asked once per session; saves after that need only a click.",
            )
        save_clicked = cols[1].button("💾 Save schedule", type="primary", disabled=not count, key=f"save_{where}")
        undo_clicked = cols[2].button("↩️ Undo", disabled=not ss.undo_stack, key=f"undo_{where}")
        discard_clicked = cols[3].button("Discard changes", disabled=not count, key=f"discard_{where}")
        reload_clicked = cols[4].button(
            "🔄 Reload latest", key=f"reload_{where}", help="Unsaved changes on this device are dropped."
        )

        if save_clicked:
            if ss.unlocked or password == st.secrets.get("UPDATE_PASSWORD", "admin123"):
                ss.unlocked = True
                with st.spinner("Saving changes to database..."):
                    admin_session.save()
                st.rerun()  # failed: show the error once, at the top of the page
            else:
                st.error("❌ Incorrect password. Changes not saved.")
        if undo_clicked:
            admin_session.undo()
            st.rerun()
        if discard_clicked:
            admin_session.discard()
            flash("Discarded unsaved changes. **Undo** brings them back.", "info")
            st.rerun()
        if reload_clicked:
            admin_session.reload()
            flash("Reloaded the latest saved schedule.", "info")
            st.rerun()


# ---------------- Update banner ----------------

def newer_version_banner(where: str) -> None:
    """Check every few seconds whether someone else has saved, and say so.

    The page is never reloaded automatically, so unsaved work here is never lost.
    """
    def check():
        try:
            meta = read_meta(admin_session.get_client())
        except Exception:
            return
        if meta.version == st.session_state.data_version:
            return
        when = format_time(meta.saved_at)
        count = len(admin_session.pending())
        message = f"🔔 The schedule was saved by someone else{f' at {when}' if when else ''}."
        if count:
            message += (
                f" You have {count} unsaved change{'s' if count != 1 else ''} here, which can't be saved "
                "over theirs. Download them if you need a copy, then load their changes."
            )
        st.warning(message)
        if st.button("🔄 Load their changes", key=f"banner_reload_{where}"):
            admin_session.reload()
            flash("Reloaded the latest saved schedule.", "info")
            st.rerun()

    st.fragment(check, run_every=refresh_seconds())()


# ---------------- Orders table ----------------

def _clear_filters(where: str) -> None:
    for name, value in FILTER_DEFAULTS.items():
        st.session_state[f"{where}_f_{name}"] = value
    for name in DATE_FILTERS:
        st.session_state.pop(f"{where}_f_{name}", None)


def _filter_controls(where: str) -> dict:
    def k(name):
        return f"{where}_f_{name}"

    for name, value in FILTER_DEFAULTS.items():
        st.session_state.setdefault(k(name), value)
    statuses = ["All"] + sorted(s for s in st.session_state.df["Status"].unique().tolist() if s)
    if st.session_state[k("status")] not in statuses:
        st.session_state[k("status")] = "All"
    match = ["Contains", "Exact"]

    with st.expander("🔍 Filter Options", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Quote Number**")
            c = st.columns([3, 1])
            c[0].text_input("Quote", label_visibility="collapsed", key=k("quote"))
            c[1].selectbox("Match", match, key=k("quote_match"), label_visibility="collapsed")

            st.markdown("**PO Number**")
            c = st.columns([3, 1])
            c[0].text_input("PO Number", label_visibility="collapsed", key=k("po"))
            c[1].selectbox("Match", match, key=k("po_match"), label_visibility="collapsed")

            st.markdown("**Status**")
            c = st.columns([3, 1])
            c[0].selectbox("Status", statuses, key=k("status"), label_visibility="collapsed")
            c[1].selectbox("Match", match, key=k("status_match"), label_visibility="collapsed")

        with col2:
            st.markdown("**Customer Name**")
            c = st.columns([3, 1])
            c[0].text_input("Customer", label_visibility="collapsed", key=k("customer"))
            c[1].selectbox("Match", match, key=k("customer_match"), label_visibility="collapsed")

            st.markdown("**Model Description**")
            c = st.columns([3, 1])
            c[0].text_input("Model", label_visibility="collapsed", key=k("model"))
            c[1].selectbox("Match", match, key=k("model_match"), label_visibility="collapsed")

            st.markdown("**Date Filter**")
            st.radio("Filter by", ["None", "Exact Date", "Month"], horizontal=True, key=k("date_type"))

            st.markdown("**Sort by Scheduled Date**")
            st.selectbox("Sort Order", [SORT_NEWEST, SORT_OLDEST], key=k("sort"), label_visibility="collapsed")

            date_type = st.session_state[k("date_type")]
            if date_type == "Exact Date":
                st.date_input("Select Date", key=k("exact_date"))
            elif date_type == "Month":
                c = st.columns(2)
                c[0].selectbox("Month", range(1, 13), format_func=lambda x: datetime(2000, x, 1).strftime("%B"),
                               index=datetime.now().month - 1, key=k("month"))
                c[1].number_input("Year", min_value=2020, max_value=2030, value=datetime.now().year, key=k("year"))

        st.button("🔄 Clear All Filters", on_click=_clear_filters, args=(where,), key=k("clear"))

    return {name: st.session_state.get(k(name)) for name in [*FILTER_DEFAULTS, *DATE_FILTERS]}


def apply_filters(df: pd.DataFrame, f: dict) -> pd.DataFrame:
    """Filter and sort orders for display. Filters never change what is saved."""
    def text_filter(frame, col, text, how):
        if not text:
            return frame
        if how == "Exact":
            return frame[frame[col].str.strip() == text.strip()]
        return frame[frame[col].str.contains(text, case=False, na=False, regex=False)]

    out = df
    out = text_filter(out, "Quote", f["quote"], f["quote_match"])
    out = text_filter(out, "PO Number", f["po"], f["po_match"])
    if f["status"] and f["status"] != "All":
        if f["status_match"] == "Exact":
            out = out[out["Status"].str.strip().str.lower() == f["status"].lower()]
        else:
            out = out[out["Status"].str.contains(f["status"], case=False, na=False, regex=False)]
    out = text_filter(out, "Customer Name", f["customer"], f["customer_match"])
    out = text_filter(out, "Model Description", f["model"], f["model_match"])

    dates = pd.to_datetime(out["Scheduled Date"], errors="coerce")
    if f["date_type"] == "Exact Date" and f.get("exact_date"):
        out = out[dates.dt.date == f["exact_date"]]
    elif f["date_type"] == "Month" and f.get("month") and f.get("year"):
        out = out[(dates.dt.month == f["month"]) & (dates.dt.year == f["year"])]

    newest_first = f["sort"] != SORT_OLDEST
    order = pd.to_datetime(out["Scheduled Date"], errors="coerce")
    return out.assign(_order=order).sort_values(
        ["_order", "WO"], ascending=[not newest_first, True], na_position="last", kind="stable"
    ).drop(columns="_order")


def orders_table(where: str) -> None:
    """Filters plus an editable table. An edit counts as soon as the cell is
    committed (Enter or leaving the cell); no separate Apply step."""
    ss = st.session_state
    filters = _filter_controls(where)
    signature = tuple(sorted(filters.items()))
    snap = admin_session.table_snapshot(where)
    if snap is None or snap["rev"] != ss.data_rev or snap["filters"] != signature:
        shown = apply_filters(ss.df, filters).reset_index(drop=True)
        snap = admin_session.reset_table(where, shown, signature)

    st.caption(
        f"Showing {len(snap['shown'])} of {len(ss.df)} orders. Edits apply straight away (press Enter or "
        "leave the cell); select rows on the left and press Delete to remove them."
    )
    with st.container(key=f"orders_table_{where}"):
        st.data_editor(
            snap["shown"],
            key=snap["key"],
            num_rows="dynamic",
            hide_index=True,
            column_config={
                order_book.ID: None,  # hidden, but kept: it says which order each row is
                "Scheduled Date": st.column_config.DateColumn(format="YYYY-MM-DD"),
                "Completion Date": st.column_config.DateColumn(format="YYYY-MM-DD"),
                "Price": st.column_config.NumberColumn(format="$%.2f"),
            },
        )
