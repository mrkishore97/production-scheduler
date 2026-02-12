# customer_app.py

from datetime import datetime

import streamlit as st
from streamlit_calendar import calendar
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
#  AUTH
#  Credentials live in .streamlit/secrets.toml under [customers]
#
#  Example secrets.toml layout:
#
#  [customers.user1]
#  password       = "hunter2"
#  customer_names = ["Acme Corp", "Beta Industries"]
#
#  [customers.user2]
#  password       = "letmein"
#  customer_names = ["Beta Industries"]
#
#  customer_names values MUST match exactly how names appear
#  in the Customer Name column of your order book.
# ================================================================

def verify_login(username: str, password: str) -> list[str] | None:
    """
    Checks credentials against st.secrets['customers'].
    Returns a list of customer names the user can see, or None if invalid.
    Supports both legacy single `customer_name` and new `customer_names` list.
    """
    try:
        customers_cfg = st.secrets.get("customers", {})
    except Exception:
        customers_cfg = {}

    entry = customers_cfg.get(username.strip())
    if not entry or entry.get("password") != password:
        return None

    # New list format
    if "customer_names" in entry:
        names = entry["customer_names"]
        return [names] if isinstance(names, str) else list(names)

    # Legacy single customer_name (backwards compatible)
    if "customer_name" in entry:
        return [entry["customer_name"]]

    return None


def show_login_screen():
    """Renders a centered login card. Stops execution until successful login."""

    st.markdown(
        """
        <style>
        [data-testid="stAppViewContainer"] > .main {
            background: linear-gradient(135deg, #1e3a5f 0%, #2563eb 100%);
            min-height: 100vh;
        }
        [data-testid="collapsedControl"] { display: none; }
        section[data-testid="stSidebar"] { display: none; }
        .login-card {
            background: white;
            padding: 2.5rem 3rem 2rem 3rem;
            border-radius: 18px;
            box-shadow: 0 24px 64px rgba(0,0,0,0.35);
            width: 100%;
            max-width: 420px;
        }
        .login-icon  { text-align: center; font-size: 3rem; margin-bottom: 4px; }
        .login-title { text-align: center; font-size: 1.45rem; font-weight: 700;
                       color: #1e3a5f; margin: 0; }
        .login-sub   { text-align: center; font-size: 0.85rem; color: #64748b;
                       margin: 6px 0 1.8rem 0; }
        .footer-note { text-align: center; color: rgba(255,255,255,0.55);
                       font-size: 0.78rem; margin-top: 1.5rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    _, mid, _ = st.columns([1, 2.2, 1])
    with mid:
        st.markdown('<div class="login-card">', unsafe_allow_html=True)
        st.markdown('<div class="login-icon">🏭</div>', unsafe_allow_html=True)
        st.markdown('<div class="login-title">Customer Portal</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="login-sub">Sign in to view your production schedule</div>',
            unsafe_allow_html=True,
        )

        username = st.text_input("Username", placeholder="Enter your username", key="li_user")
        password = st.text_input("Password", placeholder="Enter your password",
                                 type="password", key="li_pass")

        if st.button("Sign In →", type="primary", use_container_width=True):
            if not username.strip() or not password:
                st.error("Please enter both username and password.")
            else:
                customer_names = verify_login(username, password)
                if customer_names:
                    st.session_state.authenticated       = True
                    st.session_state.logged_in_customers = customer_names
                    st.session_state.login_username      = username.strip()
                    st.session_state.customer_display    = ", ".join(customer_names)
                    st.rerun()
                else:
                    st.error("❌ Incorrect username or password.")

        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown(
        '<div class="footer-note">Contact your administrator if you need access.</div>',
        unsafe_allow_html=True,
    )


# ================================================================
#  SESSION STATE INIT
# ================================================================
for key, default in [
    ("authenticated",       False),
    ("logged_in_customers", []),
    ("customer_display",    ""),
    ("login_username",      None),
    ("df_version",          0),
    ("show_print_preview",  False),
]:
    if key not in st.session_state:
        st.session_state[key] = default


# ================================================================
#  AUTH GATE
# ================================================================
if not st.session_state.authenticated:
    show_login_screen()
    st.stop()

# ================================================================
#  AUTHENTICATED SECTION
# ================================================================
my_customers: list[str] = st.session_state.logged_in_customers
customer_display: str   = st.session_state.customer_display

df_all = load_all_data()
my_df  = df_all[
    df_all["Customer Name"].str.strip().str.lower().isin(
        [c.strip().lower() for c in my_customers]
    )
].copy()


# ---- Sidebar ----
with st.sidebar:
    st.markdown(f"### 👤 {customer_display}")
    st.caption(f"Signed in as `{st.session_state.login_username}`")
    if len(my_customers) > 1:
        st.caption("**Viewing orders for:**")
        for c in my_customers:
            st.caption(f"• {c}")
    st.divider()
    st.caption("📖 Use the page selector to open **Table View**.")
    st.caption("🔒 Read-only — contact admin to make changes.")
    st.divider()
    if st.button("🚪 Log Out", use_container_width=True):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()


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
