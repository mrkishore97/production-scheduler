# Production Scheduler Architecture Guide

## App entry points

Run each Streamlit app independently from the repository root:

- `streamlit run admin/app.py`
- `streamlit run customer/customer_app.py`
- `streamlit run customer/customer_specific_app.py`

## Current modular layout

```text
admin/
  app.py
  pages/table_view.py

customer/
  customer_app.py
  customer_specific_app.py
  pages/customer_table_view.py

production_scheduler/
  __init__.py
  config.py
  status.py
  calendar_ui.py                 # compatibility re-export
  customer_portal.py             # compatibility facade for customer apps

  services/
    admin_services.py
    customer_services.py
    data_services.py

  ui/
    calendar_ui.py

  data/
    data_io.py
    data_processing.py
```

## Responsibilities

- **UI-only app files** (`admin/*.py`, `customer/*.py`): Streamlit widgets, page layout, user interaction.
- **`production_scheduler.data.data_io`**: Supabase reads/writes and data version management.
- **`production_scheduler.data.data_processing`**: column standardization, date/price parsing, order normalization.
- **`production_scheduler.services.customer_services`**: customer event generation, export and print helpers.
- **`production_scheduler.services.admin_services`**: admin calendar event generation and upload signature utilities.
- **`production_scheduler.services.data_services`**: shared filter logic used by table views.
- **`production_scheduler.status`**: canonical status mapping and color tokens.
- **`production_scheduler.ui.calendar_ui`**: shared calendar options and CSS presets.

## Import contract

All app entry points should import shared logic using package imports:

```python
from production_scheduler.module import function
```

Examples used in the project:

- `from production_scheduler.ui.calendar_ui import build_calendar_options`
- `from production_scheduler.data.data_io import load_order_book, save_order_book`
- `from production_scheduler.services.customer_services import df_to_calendar_events`

This avoids local `sys.path` manipulation and prevents `ModuleNotFoundError` when running from the project root.
