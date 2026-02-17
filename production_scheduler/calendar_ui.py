ADMIN_CALENDAR_CUSTOM_CSS = """
    .fc .fc-daygrid-event, .fc .fc-timegrid-event { white-space: normal !important; }
    .fc .fc-event-title, .fc .fc-list-event-title {
        white-space: normal !important; overflow: visible !important; text-overflow: clip !important;
    }
"""

CUSTOMER_CALENDAR_CUSTOM_CSS = """
    .fc .fc-daygrid-event { white-space: normal !important; cursor: default !important; }
    .fc .fc-event-title   { white-space: normal !important; overflow: visible !important;
                            text-overflow: clip !important; }
"""


def build_calendar_options(*, editable: bool, height: int) -> dict:
    return {
        "initialView": "dayGridMonth",
        "firstDay": 1,
        "editable": editable,
        "selectable": editable,
        "height": height,
        "eventDisplay": "block",
        "dayMaxEvents": False,
        "headerToolbar": {
            "left": "today prev,next",
            "center": "title",
            "right": "dayGridMonth,timeGridWeek,timeGridDay,listWeek",
        },
    }



def ontario_holiday_events_2026() -> list[dict]:
    """Ontario (Canada) public holidays for 2026 as all-day calendar events."""
    holidays = [
        ("2026-01-01", "New Year's Day"),
        ("2026-02-16", "Family Day"),
        ("2026-04-03", "Good Friday"),
        ("2026-05-18", "Victoria Day"),
        ("2026-07-01", "Canada Day"),
        ("2026-08-03", "Civic Holiday"),
        ("2026-09-07", "Labour Day"),
        ("2026-10-12", "Thanksgiving"),
        ("2026-12-25", "Christmas Day"),
        ("2026-12-26", "Boxing Day"),
    ]

    return [
        {
            "id": f"holiday_{date_iso}",
            "title": f"🎉 {name}",
            "start": date_iso,
            "allDay": True,
            "editable": False,
            "backgroundColor": "#7c3aed",
            "borderColor": "#6d28d9",
            "textColor": "#ffffff",
            "extendedProps": {"holiday": True, "region": "Ontario, Canada"},
        }
        for date_iso, name in holidays
    ]
