"""Reading whole tables from Supabase safely."""

from typing import NamedTuple

from supabase import Client, PostgrestAPIError

PAGE_SIZE = 1000
UNDEFINED_COLUMN = "42703"  # Postgres error code


class Fetched(NamedTuple):
    rows: list[dict]
    total: int | None  # row count reported by the database

    @property
    def complete(self) -> bool:
        return self.total is not None and len(self.rows) == self.total

    def problem(self) -> str | None:
        """A message for the person when not every row was read, else None."""
        if self.complete:
            return None
        total = "an unknown number of" if self.total is None else f"{self.total}"
        return (
            f"Only {len(self.rows)} of {total} orders could be read from the database. "
            "Saving now would delete the rest, so saving is turned off. Reload the page to try again."
        )


class Meta(NamedTuple):
    version: str  # app_meta "data_version"; "0" if there is none yet
    saved_at: str | None  # app_meta "data_saved_at", written by save_schedule


def read_version(client: Client) -> str:
    """The schedule's saved version (app_meta "data_version"); "0" if there is none yet."""
    resp = client.table("app_meta").select("value").eq("key", "data_version").execute()
    return str(resp.data[0]["value"]) if resp.data else "0"


def read_meta(client: Client) -> Meta:
    resp = client.table("app_meta").select("key,value").in_("key", ["data_version", "data_saved_at"]).execute()
    values = {row["key"]: row["value"] for row in resp.data or []}
    return Meta(str(values.get("data_version", "0")), values.get("data_saved_at"))


def fetch_all_rows(client: Client, table: str, page_size: int = PAGE_SIZE) -> Fetched:
    """Read every row of ``table``.

    Supabase returns at most "Max rows" rows per request (1000 by default), so a
    single ``select("*")`` silently drops the rest. Read page by page instead,
    ordered by ``id`` so pages never overlap or skip rows. ``Fetched.complete``
    says whether the rows read match the table's row count.
    """
    rows: list[dict] = []
    try:
        while True:
            resp = (
                client.table(table)
                .select("*", count="exact")
                .order("id")
                .range(len(rows), len(rows) + page_size - 1)
                .execute()
            )
            batch = resp.data or []
            rows.extend(batch)
            if not batch or resp.count is None or len(rows) >= resp.count:
                return Fetched(rows, resp.count)
    except PostgrestAPIError as err:
        if err.code != UNDEFINED_COLUMN:
            raise
    # No "id" column to page by: only a single request can be trusted, and
    # Fetched.complete reports whether it held every row.
    resp = client.table(table).select("*", count="exact").execute()
    return Fetched(resp.data or [], resp.count)
