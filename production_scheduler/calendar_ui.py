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


GRID_VIEWS = ("dayGridMonth", "dayGridWeek", "dayGridDay")


def build_calendar_options(
    *,
    editable: bool,
    height: int,
    initial_date: str | None = None,
    initial_view: str | None = None,
) -> dict:
    """FullCalendar options.

    Orders carry a date, not a time or a length, so events can be moved but not
    stretched, there is no date-range selection, and week/day views are day
    grids (hourly views would turn a dropped order into a timed event).
    ``initial_date``/``initial_view`` only apply when the calendar is first drawn.
    """
    options = {
        "initialView": initial_view if initial_view in GRID_VIEWS else "dayGridMonth",
        "firstDay": 1,
        "editable": editable,
        "eventDurationEditable": False,
        "selectable": False,
        "height": height,
        "eventDisplay": "block",
        "dayMaxEvents": False,
        "headerToolbar": {
            "left": "today prev,next",
            "center": "title",
            "right": "dayGridMonth,dayGridWeek,dayGridDay,listWeek",
        },
    }
    if initial_date:
        options["initialDate"] = initial_date
    return options
