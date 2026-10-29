"""Messages that survive st.rerun().

A message shown just before ``st.rerun()`` is wiped when the page redraws, so
nobody sees it. Queue it with ``flash`` instead; ``show_flash`` shows it on the
next run.
"""

import streamlit as st


def flash(message: str, kind: str = "success") -> None:
    st.session_state["_flash"] = (kind, message)


def show_flash() -> None:
    kind, message = st.session_state.pop("_flash", (None, None))
    if message:
        getattr(st, kind)(message)
