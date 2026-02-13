# customer/customer_specific_app.py
# Token-based customer portal — no login required.
# Each customer gets a unique URL: https://yourapp.streamlit.app/?token=abc123xyz
#
# secrets.toml format:
#
# [tokens]
# abc123xyz = "Trans East Trailers Moncton"
# def456uvw = "Trans East Trailers Ontario"
# ghi789rst = "Acme Corp"
#
# Generate tokens with: python -c "import secrets; print(secrets.token_urlsafe(24))"

from datetime import datetime
from pathlib import Path
import sys

import streamlit as st
from streamlit_calendar import calendar

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
from production_scheduler.calendar_ui import CUSTOMER_CALENDAR_CUSTOM_CSS, build_calendar_options
from production_scheduler.customer_portal import (
    build_excel_bytes,
    df_to_calendar_events,
    generate_monthly_print_view,
    load_all_data,
)

# ---------------- Config ----------------
st.set_page_config(page_title="Customer Order Portal", layout="wide")

# ================================================================
#  TOKEN AUTH
# ================================================================

def resolve_token(token: str) -> list[str] | None:
    """
    Looks up a URL token in st.secrets['tokens'].
    Returns a list of customer names, or None if token is invalid.

    secrets.toml supports two formats:

    # Single customer
    abc123 = "Acme Corp"

    # Multiple customers (TOML array)
    def456 = ["Trans East Trailers Moncton", "Trans East Trailers Ontario"]
    """
    try:
        tokens_cfg = st.secrets.get("tokens", {})
    except Exception:
        return None

    value = tokens_cfg.get(token.strip())
    if value is None:
        return None

    if isinstance(value, str):
        return [value]
    return list(value)


def show_invalid_token_screen():
    """Shown when no token or an unrecognised token is in the URL."""
    st.markdown(
        """
        <style>
        [data-testid="stAppViewContainer"] > .main {
            background: linear-gradient(135deg, #1e3a5f 0%, #2563eb 100%);
            min-height: 100vh;
        }
        [data-testid="collapsedControl"] { display: none; }
        section[data-testid="stSidebar"] { display: none; }
        .err-card {
            background: white;
            padding: 2.5rem 3rem;
            border-radius: 18px;
            box-shadow: 0 24px 64px rgba(0,0,0,0.35);
            max-width: 460px;
            text-align: center;
        }
        .err-icon  { font-size: 3rem; margin-bottom: 8px; }
        .err-title { font-size: 1.3rem; font-weight: 700; color: #1e3a5f; margin: 0; }
        .err-sub   { font-size: 0.9rem; color: #64748b; margin-top: 8px; }
        .footer-note { text-align: center; color: rgba(255,255,255,0.55);
                       font-size: 0.78rem; margin-top: 1.5rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )
    _, mid, _ = st.columns([1, 2.2, 1])
    with mid:
        st.markdown(
            """
            <div class="err-card">
              <div class="err-icon">🔒</div>
              <div class="err-title">Access Denied</div>
              <div class="err-sub">
                This link is invalid or has expired.<br><br>
                Please contact your administrator to receive a valid link.
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    st.markdown(
        '<div class="footer-note">Contact your administrator if you need access.</div>',
        unsafe_allow_html=True,
    )


# ================================================================
#  SESSION STATE INIT
# ================================================================
for key, default in [
    ("token_verified",      False),
    ("token_customers",     []),
    ("customer_display",    ""),
    ("df_version",          0),
    ("show_print_preview",  False),
]:
    if key not in st.session_state:
        st.session_state[key] = default


# ================================================================
#  TOKEN GATE
#  Read ?token= from URL on every page load.
#  Once verified, cache result in session state so the page
#  doesn't flicker on reruns.
# ================================================================
params = st.query_params

if not st.session_state.token_verified:
    token = params.get("token", "")
    if not token:
        show_invalid_token_screen()
        st.stop()

    customer_names = resolve_token(token)
    if not customer_names:
        show_invalid_token_screen()
        st.stop()

    # Token is valid — store in session
    st.session_state.token_verified   = True
    st.session_state.token_customers  = customer_names
    st.session_state.customer_display = ", ".join(customer_names)


# ================================================================
#  AUTHENTICATED SECTION
# ================================================================
my_customers: list[str] = st.session_state.token_customers
customer_display: str   = st.session_state.customer_display

df_all = load_all_data()
my_df  = df_all[
    df_all["Customer Name"].str.strip().str.lower().isin(
        [c.strip().lower() for c in my_customers]
    )
].copy()


# ---- Sidebar ----
with st.sidebar:
    st.markdown(f"### 🏭 {customer_display}")
    if len(my_customers) > 1:
        st.caption("**Viewing orders for:**")
        for c in my_customers:
            st.caption(f"• {c}")
    st.divider()
    st.caption("🔒 Read-only — contact admin to make changes.")


# ---- Page title ----
st.title("📅 My Production Schedule")
st.caption(
    f"Showing orders for **{customer_display}**.  "
    "Gray **SOLD** blocks are dates already taken by other customers."
)

# ---- Calendar ----
events = df_to_calendar_events(df_all, my_customers)

calendar(
    events=events,
    options=build_calendar_options(editable=False, height=880),
    custom_css=CUSTOMER_CALENDAR_CUSTOM_CSS,
    key=f"cal_{st.session_state.df_version}",
)

st.divider()

# ---- Stats ----
c1, c2, c3 = st.columns([1, 1, 2])
with c1:
    st.metric("My Orders", int(len(my_df)))
with c2:
    total_val = my_df["Price"].dropna().sum() if not my_df.empty else 0
    st.metric("Total Value", f"${total_val:,.2f}")
with c3:
    st.caption("🟦 Your orders   🔘 SOLD — unavailable dates")

st.caption("Status colours:  🔵 Open  🟠 In Progress  🟢 Completed  ⚫ On Hold  🔴 Cancelled")

# ---- Download ----
safe_name = customer_display.replace(" ", "_").replace(",", "").replace("/", "")
st.subheader("📥 Download My Orders")
st.download_button(
    "⬇️ Download Excel",
    data=build_excel_bytes(my_df),
    file_name=f"my_orders_{safe_name}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)

st.divider()

# ---- Print View ----
st.subheader("🖨️ Print Monthly Schedule")
st.caption("Generates a printable calendar: your orders + sold dates")

pc1, pc2, pc3 = st.columns([2, 2, 3])
with pc1:
    print_month = st.selectbox(
        "Month", range(1, 13),
        format_func=lambda x: datetime(2000, x, 1).strftime("%B"),
        index=datetime.now().month - 1, key="print_month",
    )
with pc2:
    print_year = st.number_input(
        "Year", min_value=2020, max_value=2030,
        value=datetime.now().year, key="print_year",
    )
with pc3:
    st.write("")
    if st.button("📄 Generate Print View", type="primary"):
        st.session_state.show_print_preview = True
        st.session_state.print_html = generate_monthly_print_view(
            df_all, print_month, print_year, my_customers
        )
        st.session_state.print_month_name = datetime(
            print_year, print_month, 1
        ).strftime("%B_%Y")

if st.session_state.show_print_preview:
    dl_col, hide_col = st.columns([1, 4])
    with dl_col:
        st.download_button(
            "💾 Download HTML to Print",
            data=st.session_state.print_html,
            file_name=f"schedule_{safe_name}_{st.session_state.print_month_name}.html",
            mime="text/html",
            help="Open in browser → Ctrl+P / Cmd+P",
        )
    with hide_col:
        if st.button("Hide Preview"):
            st.session_state.show_print_preview = False
            st.rerun()
    st.info("👁️ Preview — download HTML and open in browser for proper printing")
    st.components.v1.html(st.session_state.print_html, height=1000, scrolling=True)
