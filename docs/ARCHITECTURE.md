# Production Scheduler Architecture Guide

This document explains how the apps and shared modules work together, and where to make future changes safely.

## 1. High-Level Components

### App entrypoints

- `admin/app.py`
  - Uploads/normalizes order book files
  - Shows editable calendar
  - Persists updates to Supabase
  - Produces downloadable Excel and print HTML

- `admin/pages/table_view.py`
  - Grid-style admin editing and filtering
  - Persists changes to Supabase

- `customer/customer_app.py`
  - Username/password protected customer portal
  - Shows own orders with details, non-owned dates as SOLD

- `customer/customer_specific_app.py`
  - Tokenized customer portal (URL param token)
  - Same visibility model as login portal

### Shared modules (`production_scheduler/`)

- `config.py`
  - Single source of truth for required columns and Supabase table name

- `status.py`
  - Status normalization and color token mapping
  - Prevents drift in status display rules across apps

- `calendar_ui.py`
  - Shared FullCalendar options and CSS presets
  - Main place to update visual consistency across app entrypoints

- `customer_portal.py`
  - Consolidated customer portal logic:
    - Supabase reads
    - Date parsing
    - Event generation (owned vs sold)
    - Excel export
    - Monthly print HTML generation

---

## 2. Data Flow

### Admin write path

1. Admin uploads CSV/XLSX in `admin/app.py`
2. Data is normalized into canonical schema
3. Admin edits via drag-drop calendar and/or table editor
4. Data written back to Supabase (`order_book`)
5. Customer views read updated data on next load/cache refresh

### Customer read path

1. User authenticates (password or token)
2. App loads full order book from Supabase (cached)
3. Event transformer marks rows:
   - owned customer rows => detailed colored event
   - non-owned rows => generic SOLD event
4. UI displays calendar + optional exports/print view

---

## 3. Where to Change What

### Change calendar appearance globally

Edit `production_scheduler/calendar_ui.py`:

- `build_calendar_options(...)` for behavior/layout/toolbars/views
- `ADMIN_CALENDAR_CUSTOM_CSS` for admin-only style tweaks
- `CUSTOMER_CALENDAR_CUSTOM_CSS` for customer app style tweaks

This will affect:

- `admin/app.py`
- `customer/customer_app.py`
- `customer/customer_specific_app.py`

### Change status colors or mapping

Edit `production_scheduler/status.py`:

- `STATUS_COLORS`
- `STATUS_KEYWORDS`
- `normalize_status_key(...)`

### Change shared customer print/export/event logic

Edit `production_scheduler/customer_portal.py`.

### Change admin-only upload/edit behavior

Edit `admin/app.py` and/or `admin/pages/table_view.py`.

---

## 4. Security and Access Model

### Secrets

Stored in `.streamlit/secrets.toml`:

- `SUPABASE_URL`, `SUPABASE_KEY`
- `UPDATE_PASSWORD` (admin save/clear actions)
- `[customers]` credential map (username/password)
- `[tokens]` token map (token -> customer(s))

See `.streamlit/secrets.example.toml` for a template.

### Customer data isolation behavior

Customer portals avoid leaking details for non-owned rows by rendering only a generic SOLD marker.

---

## 5. Performance and Stability Notes

- Customer Supabase reads are cached for 300 seconds.
- Shared modules reduce duplication risk and inconsistent bug fixes.
- Canonical status normalization avoids mismatched color behavior.
- Centralized calendar config prevents style drift across portals.

---

## 6. Suggested Engineering Guardrails (Next Step)

- Add tests for:
  - status normalization (`status.py`)
  - event visibility rules (`customer_portal.py`)
  - calendar option contract (`calendar_ui.py`)
- Add CI pipeline for:
  - `python -m py_compile`
  - optional formatting/linting checks
- Introduce semantic versioned release notes for UI behavior changes.

