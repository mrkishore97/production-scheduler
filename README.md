# Production Scheduler

A modular Streamlit-based production scheduling system with:

- **Admin app** for uploading/editing schedule data and drag-drop calendar updates.
- **Customer login app** for authenticated customer schedule visibility.
- **Token-based customer app** for secure no-login customer links.

All apps share a single Supabase data source and a common set of reusable modules under `production_scheduler/`.

---

## Repository Structure

```text
admin/
  app.py                         # Admin calendar app (editable)
  pages/table_view.py            # Admin tabular editor
customer/
  customer_app.py                # Username/password customer portal
  customer_specific_app.py       # Tokenized customer portal
  pages/customer_table_view.py   # Customer table page
production_scheduler/
  config.py                      # Shared constants (columns/table name)
  status.py                      # Shared status normalization + colors
  calendar_ui.py                 # Shared calendar options + CSS presets
  customer_portal.py             # Shared customer portal data/event/export logic
docs/
  ARCHITECTURE.md                # Detailed architecture and data flow
.streamlit/
  secrets.example.toml           # Example secrets template
```

---

## Key Design Goal

The codebase is organized so that shared behavior is centralized and easy to evolve.

### Calendar changes in one place
If you want to change the calendar behavior/look across:

- `admin/app.py`
- `customer/customer_app.py`
- `customer/customer_specific_app.py`

you should primarily update:

- `production_scheduler/calendar_ui.py`

This module contains:

- `build_calendar_options(...)` (view controls, toolbar, interaction defaults)
- shared CSS blocks (`ADMIN_CALENDAR_CUSTOM_CSS`, `CUSTOMER_CALENDAR_CUSTOM_CSS`)

---

## Getting Started

### 1) Install dependencies

```bash
pip install -r requirements.txt
```

### 2) Configure secrets

Copy the example file and fill in real values:

```bash
cp .streamlit/secrets.example.toml .streamlit/secrets.toml
```

### 3) Run apps

### Admin app
```bash
streamlit run admin/app.py
```

### Customer login app
```bash
streamlit run customer/customer_app.py
```

### Customer token app
```bash
streamlit run customer/customer_specific_app.py
```

---

## Data Model (Supabase table: `order_book`)

Expected canonical fields used across apps:

- `wo`
- `quote`
- `po_number`
- `status`
- `customer_name`
- `model_description`
- `scheduled_date`
- `price`
- `uploaded_name`

---

## Authentication Modes

### 1) Username/password (customer app)
- Configured under `[customers.<username>]`
- Supports both single and multi-customer access (`customer_name` or `customer_names`)

### 2) URL token (customer_specific_app)
- Configured under `[tokens]`
- Each token maps to one or more customer names

---

## Operational Notes

- Admin edits are saved to Supabase and reflected in customer views.
- Customer portals are intentionally read-only.
- Status color rendering is normalized through `production_scheduler/status.py`.
- Customer apps cache Supabase reads (`@st.cache_data(ttl=300)`) to reduce load.

---

## Recommended Next Improvements

- Add unit tests for status normalization and event generation.
- Add CI checks (formatting/linting/py_compile).
- Add role-based controls for admin/table actions.
- Add migration scripts for schema changes.

For full deep-dive architecture and extension guidance, see:

- `docs/ARCHITECTURE.md`
