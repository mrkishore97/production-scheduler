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
  order_book.py                  # Loading, cleaning, comparing and saving orders
  admin_session.py               # The admin pages' shared working copy (load/save/reload)
  calendar_sync.py               # Applies calendar drag-and-drop to the working data
  supabase_io.py                 # Reads whole tables page by page
  feedback.py                    # Messages that survive a page re-run
  customer_portal.py             # Shared customer portal data/event/export logic
db/
  save_schedule.sql              # One-time database setup for safe saving
tests/                           # Unit, database and browser tests (see "Running the tests")
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

### 3) Set up safe saving in the database (once)

In Supabase, open **SQL Editor → New query**, paste the whole of
[`db/save_schedule.sql`](db/save_schedule.sql) and click **Run**. Running it
again later is harmless.

It creates the `save_schedule` function the admin pages save through. Each save
then writes only the orders that changed, all in one transaction, and is
refused if someone else saved after you loaded the schedule. Until it has been
run, the admin pages show a message instead of saving.

### 4) Run apps

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

- `id` (primary key; identifies each order in the app and when saving)
- `wo`
- `quote`
- `po_number`
- `status`
- `customer_name`
- `model_description`
- `scheduled_date`
- `completion_date`
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
- Saving sends only the changed orders through `save_schedule`; if another admin saved first,
  the save is refused and nothing is written. Use **Reload latest from database** to continue.
- Uploading a spreadsheet shows a preview (new, changed, removed and duplicate WOs) before it
  replaces the working schedule; nothing is saved until **Update Changes**.
- Customer portals are intentionally read-only.
- Status color rendering is normalized through `production_scheduler/status.py`.
- Customer apps cache Supabase reads (`@st.cache_data(ttl=300)`) to reduce load.

---

## Running the tests

The tests start the real apps against an in-memory stand-in for Supabase
(`tests/fake_supabase.py`) and drive them in a headless Chromium browser. They
never read your `.streamlit/secrets.toml` or touch your real database.

```bash
pip install -r requirements-dev.txt
```

```bash
playwright install chromium
```

```bash
pytest
```

The database tests in `tests/test_save_schedule_sql.py` check `db/save_schedule.sql`
against a real Postgres. They are skipped unless `TEST_DATABASE_URL` points at a
throwaway database (each test drops and recreates the tables):

```bash
TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:5432/postgres pytest tests/test_save_schedule_sql.py
```

To run only the fast tests that don't need a browser:

```bash
pytest -m "not e2e"
```

To make a test spreadsheet for manual testing (duplicate WOs, blank WOs and
more than 1,000 rows included):

```bash
python tests/sample_data.py --rows 1500 --out sample_order_book.xlsx
```

---

## Recommended Next Improvements

- Add unit tests for status normalization and event generation.
- Add CI checks (formatting/linting/py_compile).
- Add role-based controls for admin/table actions.
- Add migration scripts for schema changes.

For full deep-dive architecture and extension guidance, see:

- `docs/ARCHITECTURE.md`
