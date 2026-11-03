from datetime import date

import pandas as pd

from production_scheduler.calendar_sync import apply_drag, parse_event_change


def message(event_id="7", old="2026-10-10", new="2026-10-12", view=None, wo="100", rev=3):
    props = {"wo": wo, "rev": rev}
    return {
        "callback": "eventChange",
        "eventChange": {
            "oldEvent": {"id": event_id, "start": old, "allDay": True, "extendedProps": props},
            "event": {"id": event_id, "start": new, "allDay": True, "extendedProps": props},
            "relatedEvents": [],
            "view": view
            or {
                "type": "dayGridMonth",
                "currentStart": "2026-10-01T04:00:00.000Z",
                "currentEnd": "2026-11-01T04:00:00.000Z",
            },
        },
    }


def frame(*rows):
    return pd.DataFrame(rows, columns=["id", "WO", "Scheduled Date"])


def test_ignores_other_messages():
    assert parse_event_change(None) is None
    assert parse_event_change({}) is None
    assert parse_event_change({"callback": "eventClick", "eventClick": {}}) is None


def test_reads_drop():
    drag = parse_event_change(message())
    assert drag.event_id == "7"
    assert drag.wo == "100"
    assert drag.new_date == date(2026, 10, 12)
    assert drag.view_type == "dayGridMonth"
    assert drag.view_date.month == 10


def test_view_date_stays_in_shown_month_for_any_time_zone():
    # Midnight on Oct 1 in UTC+14 is still Sep 30 in UTC.
    view = {"type": "dayGridMonth", "currentStart": "2026-09-30T10:00:00.000Z", "currentEnd": "2026-10-31T10:00:00.000Z"}
    assert parse_event_change(message(view=view)).view_date.month == 10


def test_same_message_has_same_signature_but_new_drag_back_does_not():
    first = parse_event_change(message(old="2026-10-10", new="2026-10-12", rev=3))
    repeat = parse_event_change(message(old="2026-10-10", new="2026-10-12", rev=3))
    assert first.signature() == repeat.signature()
    # After the data changed another way, events are redrawn with a newer
    # revision, so the same move is a new drag.
    again = parse_event_change(message(old="2026-10-10", new="2026-10-12", rev=5))
    assert again.signature() != first.signature()
    # Moving back later has a different old date, so it is a new drag too.
    back = parse_event_change(message(old="2026-10-15", new="2026-10-12", rev=3))
    assert back.signature() != first.signature()


def test_apply_drag_sets_date_once():
    df = frame(("7", "100", date(2026, 10, 10)), ("8", "200", date(2026, 10, 3)))
    drag = parse_event_change(message())
    assert apply_drag(df, drag) is True
    assert df.loc[0, "Scheduled Date"] == date(2026, 10, 12)
    assert df.loc[1, "Scheduled Date"] == date(2026, 10, 3)
    assert apply_drag(df, drag) is False  # already there


def test_apply_drag_fills_missing_date_and_ignores_unknown_order():
    df = frame(("7", "100", pd.NaT))
    assert apply_drag(df, parse_event_change(message())) is True
    assert apply_drag(df, parse_event_change(message(event_id="999"))) is False


def test_duplicate_wo_moves_only_the_dragged_order():
    df = frame(("7", "500", date(2026, 10, 5)), ("8", "500", date(2026, 10, 7)))
    assert apply_drag(df, parse_event_change(message(event_id="7", wo="500", new="2026-10-20"))) is True
    assert list(df["Scheduled Date"]) == [date(2026, 10, 20), date(2026, 10, 7)]


# ---------- clicks (cut and paste) ----------

from production_scheduler.calendar_sync import DayClick, EventClick, move_order, parse_click  # noqa: E402


def test_reads_a_click_on_an_order():
    click = parse_click({"callback": "eventClick", "eventClick": {"event": {"id": "7", "extendedProps": {"rev": "4.2"}}}})
    assert click == EventClick("7", "4.2")
    assert click.signature() != EventClick("7", "4.3").signature()


def test_reads_a_click_on_a_day_in_the_viewers_time_zone():
    # Nov 5 in India (UTC+5:30) is reported as 18:30 UTC on Nov 4.
    state = {"callback": "dateClick", "dateClick": {"date": "2026-11-04T18:30:00.000Z", "allDay": True}}
    assert parse_click(state, "Asia/Kolkata").day == date(2026, 11, 5)
    # Nov 5 in Moncton (UTC-4) is reported as 04:00 UTC on Nov 5.
    state = {"callback": "dateClick", "dateClick": {"date": "2026-11-05T04:00:00.000Z", "allDay": True}}
    assert parse_click(state, "America/Moncton").day == date(2026, 11, 5)
    # Without a time zone, the nearest midnight is used.
    assert parse_click(state, None).day == date(2026, 11, 5)
    assert isinstance(parse_click(state), DayClick)


def test_move_order_only_moves_that_order():
    df = frame(("7", "100", date(2026, 10, 5)), ("8", "101", date(2026, 10, 7)))
    assert move_order(df, "8", date(2027, 1, 12)) is True
    assert list(df["Scheduled Date"]) == [date(2026, 10, 5), date(2027, 1, 12)]
    assert move_order(df, "8", date(2027, 1, 12)) is False
