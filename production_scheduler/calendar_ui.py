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
