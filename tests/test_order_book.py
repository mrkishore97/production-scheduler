import json
from datetime import date

import pandas as pd
import pytest
from supabase import create_client

from production_scheduler import order_book as ob
from sample_data import order


def frame(*rows):
    """Working-copy rows: (id, WO, customer, scheduled date)."""
    df = pd.DataFrame(rows, columns=["id", "WO", "Customer Name", "Scheduled Date"])
    for c in ["Quote", "PO Number", "Status", "Model Description"]:
        df[c] = ""
    df["Completion Date"] = pd.NaT
    df["Price"] = 100.0
    return df[["id"] + ob.REQUIRED_COLS]


D5, D7, D9, D15 = date(2026, 10, 5), date(2026, 10, 7), date(2026, 10, 9), date(2026, 10, 15)


# ---------- cleaning ----------

def test_upload_maps_column_names_and_types():
    raw = pd.DataFrame({
        "Work Order": ["100", "101", "2"], "Quotation": ["Q1", "", ""], "PO #": ["", "", ""],
        "Status": ["Open", "", ""], "Client": ["Acme", "Beta", ""], "Model": ["Van", "", ""],
        "Ship Date": ["2026-10-05", None, None], "Completed Date": [None, None, None],
        "Amount": ["$1,234.50", None, "2469"],
    })
    df = ob.normalize_upload(raw)
    assert list(df["WO"]) == ["100", "101"]  # the "2 | total" footer row is dropped
    assert df.loc[0, "Scheduled Date"] == D5
    assert df.loc[0, "Price"] == 1234.5
    assert list(df["id"]) == ["new-1", "new-2"]


def test_upload_reports_missing_columns():
    with pytest.raises(ob.MissingColumnsError) as err:
        ob.normalize_upload(pd.DataFrame({"WO": ["1"]}))
    assert "Scheduled Date" in err.value.missing


def test_upload_ignores_an_id_column_in_the_file():
    raw = ob.empty_frame().drop(columns=["id"])
    raw.loc[0] = ["100", "", "", "", "Acme", "", "2026-10-05", None, 1.0]
    raw["id"] = ["999"]
    assert list(ob.normalize_upload(raw)["id"]) == ["new-1"]


def test_frame_from_rows_keeps_id_as_text():
    df, name = ob.frame_from_rows([dict(order("100", D5), id=7)])
    assert list(df["id"]) == ["7"]
    assert df.loc[0, "Scheduled Date"] == D5
    assert name == "test.xlsx"


# ---------- identity ----------

def test_temp_ids_never_reuse_one_in_use():
    df = pd.DataFrame({"id": ["4", None, "new-2", float("nan")]})
    assert list(ob.with_temp_ids(df, taken=["new-5"])["id"]) == ["4", "new-6", "new-2", "new-7"]


def test_filtered_edit_leaves_hidden_orders_alone():
    working = frame(("1", "500", "Acme", D5), ("2", "500", "Beta", D7), ("3", "", "No WO Co", None), ("4", "", "Other", D9))
    shown = working[working["Customer Name"] == "Acme"]
    edited = shown.copy()
    edited["Scheduled Date"] = [D15]
    merged = ob.merge_edits(working, shown["id"], edited)
    assert sorted(merged["id"]) == ["1", "2", "3", "4"]
    assert merged.set_index("id").loc["1", "Scheduled Date"] == D15
    assert merged.set_index("id").loc["2", "Scheduled Date"] == D7


def test_deleting_every_shown_order_deletes_them():
    working = frame(("1", "500", "Acme", D5), ("2", "501", "Beta", D7))
    merged = ob.merge_edits(working, ["1"], working.iloc[0:0])
    assert list(merged["id"]) == ["2"]


def test_rows_added_in_the_table_get_temp_ids():
    working = frame(("1", "500", "Acme", D5))
    edited = pd.concat([working, frame((None, "600", "New Co", D9))], ignore_index=True)
    merged = ob.merge_edits(working, ["1"], edited)
    assert list(merged["id"]) == ["1", "new-1"]


# ---------- comparing ----------

def test_diff_sends_only_changes():
    saved = frame(("1", "100", "Acme", D5), ("2", "101", "Acme", D7), ("3", "102", "Acme", D9))
    working = saved.copy()
    working.loc[0, "Scheduled Date"] = D15             # changed
    working = working[working["id"] != "3"]             # removed
    working = pd.concat([working, frame(("new-1", "103", "Beta", D5))], ignore_index=True)  # added

    changes = ob.diff(saved, working, "file.xlsx")
    assert (changes.added, changes.changed, changes.removed) == (1, 1, 1)
    assert changes.deletes == ["3"]
    update = next(u for u in changes.upserts if u.get("id") == "1")
    assert update["scheduled_date"] == "2026-10-15" and update["uploaded_name"] == "file.xlsx"
    insert = next(u for u in changes.upserts if "id" not in u)
    assert insert["wo"] == "103"


def test_no_changes_means_nothing_to_send():
    saved = frame(("1", "100", "Acme", D5), ("2", "", "Acme", None))
    assert not ob.diff(saved, saved.copy(), "other-name.xlsx")


def test_import_preview_counts():
    current = frame(("1", "100", "Acme", D5), ("2", "101", "Acme", D7))
    incoming = frame(("new-1", "100", "Acme", D15), ("new-2", "102", "Beta", D5), ("new-3", "103", "Beta", D5),
                     ("new-4", "103", "Beta", D7), ("new-5", "", "Beta", D9))
    p = ob.import_preview(current, incoming)
    assert (p.new, p.changed, p.missing, p.duplicates, p.blank_wo, p.rows) == (
        ["102", "103"], ["100"], ["101"], ["103"], 1, 5)


# ---------- saving (against the fake database) ----------

@pytest.fixture
def client(fake_db):
    return create_client(fake_db.url, "fake.test.key")


def test_load_then_save_round_trip(fake_db, client):
    fake_db.reset([order("100", D5), order("100", D7)])
    loaded = ob.load(client)
    working = loaded.df.copy()
    working.loc[0, "Scheduled Date"] = D15
    new_version = ob.save(client, ob.diff(loaded.df, working), loaded.version)

    assert int(new_version) == int(loaded.version) + 1
    assert sorted(r["scheduled_date"] for r in fake_db.orders()) == ["2026-10-07", "2026-10-15"]


def test_save_refused_when_someone_saved_first(fake_db, client):
    fake_db.reset([order("100", D5)])
    loaded = ob.load(client)
    working = loaded.df.copy()
    working.loc[0, "Scheduled Date"] = D15
    ob.save(client, ob.diff(loaded.df, working), loaded.version)
    with pytest.raises(ob.SaveConflict):
        ob.save(client, ob.diff(loaded.df, working), loaded.version)


def test_save_without_database_function(fake_db, client):
    fake_db.reset([order("100", D5)], has_save_function=False)
    loaded = ob.load(client)
    with pytest.raises(ob.SaveSetupMissing):
        ob.save(client, ob.diff(loaded.df, loaded.df.iloc[0:0]), loaded.version)
    assert len(fake_db.orders()) == 1


# ---------- table edits as reported by st.data_editor ----------

def test_apply_table_delta_edits_adds_and_deletes():
    shown = frame(("1", "100", "Acme", D5), ("2", "101", "Beta", D7))
    delta = {
        "edited_rows": {1: {"Scheduled Date": "2026-10-15", "Customer Name": "Beta Ltd"}},
        "added_rows": [{"WO": "102", "Scheduled Date": "2026-10-09"}],
        "deleted_rows": [0],
    }
    out = ob.clean_rows(ob.apply_table_delta(shown, delta))
    assert list(out["WO"]) == ["101", "102"]
    assert list(out["Scheduled Date"]) == [D15, D9]
    assert out.iloc[0]["Customer Name"] == "Beta Ltd"
    assert out.iloc[0]["id"] == "2" and pd.isna(out.iloc[1]["id"])


def test_apply_table_delta_accepts_string_positions():
    shown = frame(("1", "100", "Acme", D5))
    out = ob.apply_table_delta(shown, {"edited_rows": {"0": {"WO": "200"}}, "added_rows": [], "deleted_rows": []})
    assert list(out["WO"]) == ["200"]


def test_same_orders_counts_unsaved_new_rows_as_equal():
    a = frame(("1", "100", "Acme", D5), ("new-1", "101", "Beta", D7))
    assert ob.same_orders(a, a.copy())
    b = a.copy()
    b.loc[1, "Scheduled Date"] = D9
    assert not ob.same_orders(a, b)
    assert not ob.same_orders(a, a.iloc[:1])


def test_describe_changes():
    saved = frame(("1", "100", "Acme", D5), ("2", "101", "Beta", D7))
    working = frame(("1", "100", "Acme", D15), ("new-1", "102", "Gamma", D9))
    described = {d["WO"]: d["Change"] for d in ob.describe_changes(saved, working)}
    assert described == {
        "100": "Scheduled Date: 2026-10-05 → 2026-10-15",
        "102": "Added (scheduled 2026-10-09)",
        "101": "Removed",
    }


def test_blank_prices_and_dates_are_sent_as_nulls():
    working = frame(("new-1", "100", "Acme", None), ("new-2", "101", "Acme", D5))
    working["Price"] = [float("nan"), 2.5]
    changes = ob.diff(ob.empty_frame(), working)
    json.dumps(changes.upserts, allow_nan=False)  # raises on NaN
    assert [(u["price"], u["scheduled_date"]) for u in changes.upserts] == [(None, None), (2.5, "2026-10-05")]


def test_save_never_sends_nan(fake_db, client):
    fake_db.reset([])
    loaded = ob.load(client)
    changes = ob.Changes(upserts=[dict(ob.to_record(frame(("new-1", "100", "Acme", D5)).iloc[0]), price=float("nan"))], added=1)
    ob.save(client, changes, loaded.version)
    assert fake_db.orders()[0]["price"] is None
