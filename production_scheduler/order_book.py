"""The order book's data rules: loading, cleaning, comparing and saving orders.

Every order keeps its database row ``id`` (as text) for as long as it is in
the app, so a drag, a table edit or a save always affects exactly that order,
even when WO numbers repeat or are blank. Orders added in the app get a
temporary id ("new-1", "new-2", ...) until they are saved.

WO numbers must not repeat (ignoring capitals and surrounding spaces); blank
WOs are allowed. Repeats are flagged wherever they appear and block saving,
and the database refuses them too (db/save_schedule.sql).

Saving sends only what changed since the orders were loaded, through the
``save_schedule`` database function (db/save_schedule.sql), which applies the
whole save in one transaction and refuses it if someone else saved first.
"""

import math
import re
from dataclasses import dataclass, field
from datetime import date

import pandas as pd
from supabase import Client, PostgrestAPIError

from production_scheduler.config import REQUIRED_COLS, SUPABASE_TABLE
from production_scheduler.supabase_io import fetch_all_rows, read_meta

ID = "id"
TEXT_COLS = ["WO", "Quote", "PO Number", "Status", "Customer Name", "Model Description"]
TO_DB = {
    "WO": "wo", "Quote": "quote", "PO Number": "po_number", "Status": "status",
    "Customer Name": "customer_name", "Model Description": "model_description",
    "Scheduled Date": "scheduled_date", "Completion Date": "completion_date", "Price": "price",
}
FROM_DB = {db: col for col, db in TO_DB.items()}

COLUMN_ALIASES = {
    "wo": "WO", "work order": "WO", "workorder": "WO",
    "quote": "Quote", "quotation": "Quote",
    "po number": "PO Number", "po #": "PO Number", "po#": "PO Number",
    "ponumber": "PO Number", "purchase order": "PO Number",
    "status": "Status",
    "customer": "Customer Name", "customer name": "Customer Name",
    "client": "Customer Name", "client name": "Customer Name",
    "model description": "Model Description", "description": "Model Description",
    "model": "Model Description",
    "scheduled date": "Scheduled Date", "schedule date": "Scheduled Date",
    "scheduled": "Scheduled Date", "ship date": "Scheduled Date",
    "delivery date": "Scheduled Date", "date": "Scheduled Date",
    "completion date": "Completion Date", "completed date": "Completion Date",
    "price": "Price", "amount": "Price", "value": "Price",
}

NEW_ID = re.compile(r"new-(\d+)")
NO_ID_PROBLEM = (
    "The order_book table has no id column, so orders can't be told apart reliably and saving "
    "is turned off. Add an id primary key column to the table in Supabase."
)
CONFLICT_CODE = "PT409"  # raised by save_schedule when the version moved on
MISSING_FUNCTION_CODE = "PGRST202"
UNIQUE_VIOLATION_CODE = "23505"  # the database's own repeated-WO guard


class MissingColumnsError(ValueError):
    def __init__(self, missing: list[str], found: list[str]) -> None:
        super().__init__(f"Missing columns: {missing}")
        self.missing = missing
        self.found = found


class SaveConflict(Exception):
    """Someone else saved after this copy was loaded; nothing was written."""


class SaveSetupMissing(Exception):
    """The save_schedule database function hasn't been created yet."""


class SaveRepeatedWO(Exception):
    """The database refused a WO number another order already has; nothing was written."""


# ---------------- Parsing ----------------

def clean_header(s: str) -> str:
    return re.sub(r"\s+", " ", str(s).strip()).lower()


def parse_date(x):
    if x is None or str(x).strip() in ("", "None", "NaT"):
        return pd.NaT
    try:
        if pd.isna(x):
            return pd.NaT
    except Exception:
        pass
    dt = pd.to_datetime(x, errors="coerce")
    return pd.NaT if pd.isna(dt) else dt.date()


def parse_price(x):
    if x is None or str(x).strip() == "":
        return pd.NA
    try:
        if pd.isna(x):
            return pd.NA
    except Exception:
        pass
    s = re.sub(r"[^0-9.\-]", "", str(x).replace("$", "").replace(",", ""))
    try:
        return float(s)
    except Exception:
        return pd.NA


def _cell_text(value) -> str:
    """A spreadsheet cell as text. A number column with a blank cell is read as
    decimals, so WO 100 arrives as 100.0; whole numbers lose the ".0"."""
    try:
        if value is None or pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df = df.rename(columns={c: COLUMN_ALIASES.get(clean_header(c), str(c).strip()) for c in df.columns})
    df.columns = [str(c).strip() for c in df.columns]
    return df


def clean_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Give order columns their proper types and drop blank and spreadsheet-footer rows.

    Other columns (such as ``id``) pass through unchanged.
    """
    df = df.dropna(how="all", subset=REQUIRED_COLS).copy()

    for c in TEXT_COLS:
        df[c] = df[c].map(_cell_text)
        df[c] = df[c].replace({"nan": "", "NaN": "", "None": "", "<NA>": ""})

    df["Scheduled Date"] = df["Scheduled Date"].apply(parse_date).astype(object)
    df["Completion Date"] = df["Completion Date"].apply(parse_date).astype(object)
    df["Price"] = df["Price"].apply(parse_price)

    # Drop Excel summary rows (e.g., WO count + total price footer).
    summary_like = (
        df["WO"].str.fullmatch(r"\d+")
        & df["Quote"].eq("")
        & df["PO Number"].eq("")
        & df["Status"].eq("")
        & df["Customer Name"].eq("")
        & df["Model Description"].eq("")
        & df["Scheduled Date"].isna()
        & df["Completion Date"].isna()
        & df["Price"].notna()
    )
    df = df[~summary_like]

    # Remove empty-looking rows that became blanks after cleanup.
    blank_text = df[TEXT_COLS].eq("").all(axis=1)
    return df[~(blank_text & df["Scheduled Date"].isna() & df["Completion Date"].isna() & df["Price"].isna())]


def normalize_upload(df: pd.DataFrame) -> pd.DataFrame:
    """Clean an uploaded spreadsheet. Every row becomes a new order (temporary id)."""
    df = standardize_columns(df)
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        raise MissingColumnsError(missing, list(df.columns))
    df = df.drop(columns=[ID], errors="ignore")
    ordered = REQUIRED_COLS + [c for c in df.columns if c not in REQUIRED_COLS]
    return with_temp_ids(clean_rows(df[ordered]).reset_index(drop=True))


# ---------------- Identity ----------------

def empty_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=[ID] + REQUIRED_COLS)


def is_new_id(value) -> bool:
    return NEW_ID.fullmatch(str(value)) is not None


def with_temp_ids(df: pd.DataFrame, taken=()) -> pd.DataFrame:
    """Give every row without an id a temporary one, unused in ``df`` and ``taken``."""
    df = df.copy()
    ids = df[ID] if ID in df.columns else pd.Series(None, index=df.index, dtype=object)
    missing = ids.isna() | ids.astype(str).str.strip().isin(["", "None", "nan", "<NA>"])
    used = [int(m.group(1)) for v in [*taken, *ids[~missing]] if (m := NEW_ID.fullmatch(str(v)))]
    start = max(used, default=0) + 1
    ids = ids.astype(object)
    ids[missing] = [f"new-{n}" for n in range(start, start + int(missing.sum()))]
    df[ID] = ids.astype(str)
    return df


def merge_edits(working: pd.DataFrame, shown_ids, edited: pd.DataFrame) -> pd.DataFrame:
    """Put a table edit back into the working copy.

    ``shown_ids`` are the orders the table showed (after filtering). Those are
    replaced by ``edited``: a shown order missing from ``edited`` was deleted,
    and an edited row without an id was added. Orders the filter hid are kept
    exactly as they were.
    """
    edited = with_temp_ids(edited, taken=working[ID])
    kept = working[~working[ID].isin(set(shown_ids))]
    return pd.concat([kept, edited], ignore_index=True)


def apply_table_delta(shown: pd.DataFrame, delta: dict) -> pd.DataFrame:
    """Apply the edits ``st.data_editor`` reports in session state to the rows it was shown.

    ``delta`` is {"edited_rows": {position: {column: value}}, "added_rows": [...],
    "deleted_rows": [position, ...]}; positions refer to ``shown``'s rows. Reading
    this before the page is drawn lets an edit reach every view in the same run.
    """
    df = shown.reset_index(drop=True).copy()
    for col in ("Scheduled Date", "Completion Date"):
        df[col] = df[col].astype(object)
    for pos, values in (delta.get("edited_rows") or {}).items():
        for col, value in values.items():
            df.at[int(pos), col] = value
    deleted = {int(p) for p in delta.get("deleted_rows") or []}
    df = df[~df.index.isin(deleted)]
    added = [row for row in delta.get("added_rows") or []]
    if added:
        df = pd.concat([df, pd.DataFrame(added, columns=df.columns)], ignore_index=True)
    return df


# ---------------- WO numbers ----------------

def wo_key(value) -> str:
    """How WO numbers are compared: capitals and surrounding spaces don't matter."""
    return _text(value).strip().lower()


@dataclass
class RepeatedWO:
    wo: str         # as first typed
    ids: list[str]  # the orders that share it


def repeated_wos(df: pd.DataFrame) -> list[RepeatedWO]:
    """WO numbers used by more than one order. Blank WOs are allowed and never count."""
    keys = [wo_key(v) for v in df["WO"].tolist()]
    seen: dict[str, RepeatedWO] = {}
    for key, wo, rid in zip(keys, df["WO"].tolist(), df[ID].astype(str).tolist()):
        if key:
            seen.setdefault(key, RepeatedWO(_text(wo).strip(), [])).ids.append(rid)
    return [r for r in seen.values() if len(r.ids) > 1]


def repeated_wo_messages(df: pd.DataFrame) -> list[str]:
    """One line per repeated WO, naming the orders that share it."""
    repeats = repeated_wos(df)
    if not repeats:
        return []
    by_id = {str(r[ID]): r for _, r in df.iterrows()}
    lines = []
    for rep in repeats:
        orders = [
            f"{_text(by_id[i].get('Customer Name')).strip() or 'no customer'} "
            f"({_iso(by_id[i].get('Scheduled Date')) or 'no date'})"
            for i in rep.ids
        ]
        lines.append(f"WO {rep.wo} is used by {len(rep.ids)} orders: " + "; ".join(orders))
    return lines


# ---------------- Loading ----------------

@dataclass
class Loaded:
    df: pd.DataFrame
    uploaded_name: str | None
    version: str
    problem: str | None  # set when not every row could be read
    saved_at: str | None = None  # when the schedule was last saved (database time)


def frame_from_rows(rows: list[dict]) -> tuple[pd.DataFrame, str | None]:
    """Database rows -> (orders with an ``id`` column, name of the last uploaded file)."""
    if not rows:
        return empty_frame(), None
    df = pd.DataFrame(rows)
    last_name = df["uploaded_name"].iloc[0] if "uploaded_name" in df.columns else None
    df = df.rename(columns=FROM_DB)
    if ID not in df.columns:  # load() turns saving off in this case
        df[ID] = [f"row-{n}" for n in range(1, len(df) + 1)]
    df[ID] = df[ID].astype(str)
    df["Scheduled Date"] = df["Scheduled Date"].apply(parse_date).astype(object)
    df["Completion Date"] = df["Completion Date"].apply(parse_date).astype(object)
    df["Price"] = df["Price"].apply(lambda x: float(x) if x is not None else pd.NA)
    for c in TEXT_COLS:
        df[c] = df[c].fillna("").astype(str)
    return df[[ID] + [c for c in REQUIRED_COLS if c in df.columns]], last_name


def load(client: Client) -> Loaded:
    # Read the version first: if a save lands in between, the rows are newer
    # than the version, and the next save is refused rather than overwriting.
    meta = read_meta(client)
    fetched = fetch_all_rows(client, SUPABASE_TABLE)
    df, last_name = frame_from_rows(fetched.rows)
    problem = NO_ID_PROBLEM if fetched.rows and ID not in fetched.rows[0] else fetched.problem()
    return Loaded(df, last_name, meta.version, problem, meta.saved_at)


# ---------------- Comparing ----------------

def _text(value) -> str:
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value)


def _iso(value) -> str | None:
    try:
        if value is None or pd.isna(value):  # pd.NaT counts as a date, so test this first
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    parsed = parse_date(value)
    return None if pd.isna(parsed) else parsed.isoformat()


def _number(value) -> float | None:
    try:
        return None if pd.isna(value) else float(value)
    except (TypeError, ValueError):
        return None


def to_record(row) -> dict:
    """One order in database form (without id or uploaded_name)."""
    return {
        "wo": _text(row.get("WO")).strip(),
        "quote": _text(row.get("Quote")),
        "po_number": _text(row.get("PO Number")),
        "status": _text(row.get("Status")),
        "customer_name": _text(row.get("Customer Name")),
        "model_description": _text(row.get("Model Description")),
        "scheduled_date": _iso(row.get("Scheduled Date")),
        "completion_date": _iso(row.get("Completion Date")),
        "price": _number(row.get("Price")),
    }


def _records(df: pd.DataFrame) -> pd.DataFrame:
    """``to_record`` for a whole frame, indexed by id (column by column, for speed)."""
    convert = {"Scheduled Date": _iso, "Completion Date": _iso, "Price": _number}
    out = {}
    for col, db in TO_DB.items():
        fn = convert.get(col, _text)
        # A plain list keeps None as None; Series.map would turn a blank price into NaN.
        values = [fn(v) for v in df[col].tolist()] if col in df.columns else [None] * len(df)
        out[db] = pd.Series(values, dtype=object)
    out["wo"] = out["wo"].map(lambda v: (v or "").strip())
    return pd.DataFrame(out).set_axis(df[ID].astype(str).tolist())


def _differs(a: pd.DataFrame, b: pd.DataFrame) -> pd.Series:
    """Per row: does any field differ? (None equals None.)"""
    return ~((a == b) | (a.isna() & b.isna())).all(axis=1)


def same_orders(a: pd.DataFrame, b: pd.DataFrame) -> bool:
    """Do ``a`` and ``b`` hold exactly the same orders (same ids, same details)?"""
    ra, rb = _records(a), _records(b)
    if set(ra.index) != set(rb.index) or len(ra) != len(rb):
        return False
    return not _differs(rb, ra.loc[rb.index]).any()


@dataclass
class Changes:
    upserts: list[dict] = field(default_factory=list)  # with "id": update; without: insert
    deletes: list[str] = field(default_factory=list)
    added: int = 0
    changed: int = 0
    removed: int = 0

    def __bool__(self) -> bool:
        return bool(self.upserts or self.deletes)

    def __len__(self) -> int:
        return self.added + self.changed + self.removed

    def summary(self) -> str:
        return f"{self.added} added, {self.changed} changed, {self.removed} removed"


def _split(saved: pd.DataFrame, working: pd.DataFrame):
    old, new = _records(saved), _records(working)
    is_added = new.index.map(is_new_id).to_numpy(dtype=bool) | ~new.index.isin(old.index)
    kept = new[~is_added]
    before = old.loc[kept.index]
    changed = _differs(kept, before)
    removed = old[~old.index.isin(new.index)]
    return old, new[is_added], kept[changed.to_numpy()], removed


def diff(saved: pd.DataFrame, working: pd.DataFrame, uploaded_name: str | None = None) -> Changes:
    """What has to be written so the database matches ``working``."""
    _, added, changed, removed = _split(saved, working)
    name = uploaded_name or ""
    return Changes(
        upserts=[{**rec, "uploaded_name": name} for rec in added.to_dict("records")]
        + [{**rec, "uploaded_name": name, ID: rid} for rid, rec in changed.to_dict("index").items()],
        deletes=removed.index.tolist(),
        added=len(added),
        changed=len(changed),
        removed=len(removed),
    )


def describe_changes(saved: pd.DataFrame, working: pd.DataFrame) -> list[dict]:
    """Unsaved changes in words, one entry per order: {"WO", "Customer", "Change"}."""
    old, added, changed, removed = _split(saved, working)

    def show(v):
        return "—" if v is None or v == "" else str(v)

    out = []
    for rid, rec in changed.iterrows():
        was = old.loc[rid]
        fields = [f"{FROM_DB[c]}: {show(was[c])} → {show(rec[c])}" for c in rec.index
                  if not (rec[c] == was[c] or (pd.isna(rec[c]) and pd.isna(was[c])))]
        out.append({"WO": rec["wo"], "Customer": rec["customer_name"], "Change": "; ".join(fields)})
    for _, rec in added.iterrows():
        out.append({"WO": rec["wo"], "Customer": rec["customer_name"],
                    "Change": f"Added (scheduled {show(rec['scheduled_date'])})"})
    for _, rec in removed.iterrows():
        out.append({"WO": rec["wo"], "Customer": rec["customer_name"], "Change": "Removed"})
    return out


# ---------------- Saving ----------------

def _json_value(value):
    """JSON has no NaN or infinity; send a blank (null) instead."""
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def save(client: Client, changes: Changes, expected_version: str) -> str:
    """Write ``changes`` in one transaction; return the new version.

    Raises SaveConflict if the database version is no longer
    ``expected_version``, SaveSetupMissing if db/save_schedule.sql hasn't
    been run, and SaveRepeatedWO if the database refuses a repeated WO.
    Nothing is written in any of these cases.
    """
    upserts = [{k: _json_value(v) for k, v in row.items()} for row in changes.upserts]
    try:
        resp = client.rpc(
            "save_schedule",
            {"expected_version": expected_version, "upserts": upserts, "deletes": changes.deletes},
        ).execute()
    except PostgrestAPIError as err:
        if err.code == CONFLICT_CODE:
            raise SaveConflict(err.details or err.message) from err
        if err.code == MISSING_FUNCTION_CODE:
            raise SaveSetupMissing(err.message) from err
        if err.code == UNIQUE_VIOLATION_CODE:
            raise SaveRepeatedWO(err.details or err.message) from err
        raise
    return str(resp.data)


# ---------------- Importing ----------------

@dataclass
class ImportPreview:
    rows: int
    new: list[str]         # WOs in the file but not in the schedule
    changed: list[str]     # WOs in both, with different details
    missing: list[str]     # WOs in the schedule but not in the file (they will be removed)
    duplicates: list[str]  # WOs that appear more than once in the file
    blank_wo: int          # file rows without a WO


def import_preview(current: pd.DataFrame, incoming: pd.DataFrame) -> ImportPreview:
    def by_wo(df):
        groups: dict[str, list[dict]] = {}
        shown: dict[str, str] = {}
        for _, r in df.iterrows():
            key = wo_key(r.get("WO"))
            if key:
                groups.setdefault(key, []).append(to_record(r))
                shown.setdefault(key, _text(r.get("WO")).strip())
        return groups, shown

    (now, names), (then, old_names) = by_wo(incoming), by_wo(current)
    names = {**old_names, **names}
    return ImportPreview(
        rows=len(incoming),
        new=sorted(names[k] for k in now if k not in then),
        changed=sorted(names[k] for k in now if k in then and len(now[k]) == len(then[k]) == 1 and now[k] != then[k]),
        missing=sorted(names[k] for k in then if k not in now),
        duplicates=sorted(names[k] for k, recs in now.items() if len(recs) > 1),
        blank_wo=int((incoming["WO"].astype(str).str.strip() == "").sum()),
    )
