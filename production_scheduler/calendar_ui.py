ADMIN_CALENDAR_CUSTOM_CSS = """
    .fc .fc-daygrid-event, .fc .fc-timegrid-event { white-space: normal !important; }
    .fc .fc-event-title, .fc .fc-list-event-title {
        white-space: normal !important; overflow: visible !important; text-overflow: clip !important;
    }
    .fc .cut-order { opacity: 0.55; outline: 3px dashed #facc15; outline-offset: -3px; }
    .fc .wo-repeated { box-shadow: inset 0 0 0 3px #ef4444; }
"""

# Added while an order is cut: every day shows it can take the paste.
PASTE_TARGET_CSS = """
    .fc .fc-daygrid-day { cursor: copy; }
    .fc .fc-daygrid-day:hover { background: rgba(250, 204, 21, 0.12); }
"""

CUSTOMER_CALENDAR_CUSTOM_CSS = """
    .fc .fc-daygrid-event { white-space: normal !important; cursor: default !important; }
    .fc .fc-event-title   { white-space: normal !important; overflow: visible !important;
                            text-overflow: clip !important; }
"""


GRID_VIEWS = ("dayGridMonth", "dayGridTwoMonth", "dayGridWeek", "dayGridDay")

# Two months as one continuous grid, so an order can be dragged straight across
# the end of a month. The arrows move it one month at a time.
TWO_MONTH_VIEW = {"type": "dayGrid", "duration": {"months": 2}, "dateIncrement": {"months": 1}, "buttonText": "2 months"}


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
            "right": "dayGridMonth,dayGridTwoMonth,dayGridWeek,dayGridDay,listWeek",
        },
        "views": {"dayGridTwoMonth": TWO_MONTH_VIEW},
    }
    if initial_date:
        options["initialDate"] = initial_date
    return options
