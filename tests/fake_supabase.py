"""In-memory stand-in for the parts of Supabase's REST API (PostgREST) the apps use.

Tests point SUPABASE_URL at this server so they never touch a real database.
It mimics the behaviour that matters for these tests:

- a per-request row cap (Supabase's "Max rows" setting, 1000 by default)
- ``offset``/``limit`` paging, ``order=``, ``Prefer: count=exact``
- ``eq`` / ``neq`` filters, insert, upsert, update and delete
- the ``save_schedule`` function from db/save_schedule.sql: version check,
  all-or-nothing writes, version bump
- failure injection: a save can be made to fail, or the function to be missing

Test-only control endpoints live under ``/__test__/``.
"""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qsl, urlparse

PRIMARY_KEYS = {"order_book": "id", "app_meta": "key"}


class FakeDatabase:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.reset()

    def reset(self, tables: dict | None = None, **config) -> None:
        with self.lock:
            self.tables: dict[str, list[dict]] = {"order_book": [], "app_meta": []}
            self.next_id = 1
            self.config = {
                "max_rows": 1000,
                "has_id": True,
                "has_save_function": True,  # False: as if db/save_schedule.sql was never run
                "fail_save": False,  # True: save_schedule fails without writing anything
                "latency": 0.0,
            }
            self.config.update(config)
            self.saves = 0
            self.reads: dict[str, int] = {}
            for name, rows in (tables or {}).items():
                self.tables[name] = []
                for row in rows:
                    self._add(name, dict(row))

    def _add(self, table: str, row: dict) -> dict:
        if table == "order_book":
            if self.config["has_id"]:
                if row.get("id") is None:
                    row["id"] = self.next_id
                self.next_id = max(self.next_id, int(row["id"])) + 1
            else:
                row.pop("id", None)
        self.tables.setdefault(table, []).append(row)
        return row


DB = FakeDatabase()


def _matches(row: dict, filters: list[tuple[str, str, str]]) -> bool:
    for column, op, value in filters:
        actual = row.get(column)
        actual_s = "" if actual is None else str(actual)
        if op == "eq" and actual_s != value:
            return False
        if op == "neq" and actual_s == value:
            return False
        if op == "is" and value == "null" and actual is not None:
            return False
        if op == "in":
            options = [v.strip().strip('"') for v in value.strip("()").split(",")]
            if actual_s not in options:
                return False
    return True


def _sort_key(value):
    # None sorts last, numbers before strings, like a typical SQL ordering.
    if value is None:
        return (2, "")
    if isinstance(value, (int, float)):
        return (0, value)
    return (1, str(value))


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args) -> None:  # keep test output quiet
        pass

    # ---------- helpers ----------
    def _send(self, status: int, payload=None, headers: dict | None = None) -> None:
        body = b"" if payload is None else json.dumps(payload, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _error(self, status: int, message: str, code: str = "PGRST000") -> None:
        self._send(status, {"code": code, "message": message, "details": None, "hint": None})

    def _body(self):
        return json.loads(self._raw) if self._raw else None

    def _parse(self):
        # Always consume the request body, or it corrupts the next request on a kept-alive connection.
        length = int(self.headers.get("Content-Length") or 0)
        self._raw = self.rfile.read(length) if length else b""
        parsed = urlparse(self.path)
        parts = parsed.path.strip("/").split("/")
        params = parse_qsl(parsed.query, keep_blank_values=True)
        return parts, params

    def _filters(self, params):
        reserved = {"select", "order", "offset", "limit", "on_conflict", "columns"}
        out = []
        for key, value in params:
            if key in reserved or "." not in value:
                continue
            op, _, operand = value.partition(".")
            out.append((key, op, operand))
        return out

    def _prefer(self) -> str:
        return self.headers.get("Prefer", "") or ""

    def _latency(self) -> None:
        if DB.config["latency"]:
            time.sleep(DB.config["latency"])

    # ---------- test control ----------
    def _control(self, action: str) -> None:
        if action == "reset" and self.command == "POST":
            body = self._body() or {}
            DB.reset(body.get("tables"), **body.get("config", {}))
            return self._send(200, {"ok": True})
        if action == "config" and self.command == "POST":
            with DB.lock:
                DB.config.update(self._body() or {})
            return self._send(200, DB.config)
        if action == "dump":
            with DB.lock:
                return self._send(200, {"tables": DB.tables, "saves": DB.saves, "reads": DB.reads})
        return self._error(404, "unknown control action")

    # ---------- REST ----------
    def _table(self, parts):
        if len(parts) >= 3 and parts[0] == "rest" and parts[1] == "v1":
            return parts[2]
        return None

    def do_GET(self) -> None:
        parts, params = self._parse()
        if parts and parts[0] == "__test__":
            return self._control(parts[1] if len(parts) > 1 else "")
        table = self._table(parts)
        if table is None:
            return self._error(404, "not found")
        self._latency()
        p = dict(params)
        with DB.lock:
            for name in (table, f"{table}?select={p.get('select', '*')}"):  # per table, and per query shape
                DB.reads[name] = DB.reads.get(name, 0) + 1
            rows = [dict(r) for r in DB.tables.get(table, []) if _matches(r, self._filters(params))]
            order = p.get("order")
            if order:
                for spec in reversed(order.split(",")):
                    bits = spec.split(".")
                    column = bits[0]
                    if table == "order_book" and column == "id" and not DB.config["has_id"]:
                        return self._error(400, f"column {table}.id does not exist", "42703")
                    rows.sort(key=lambda r: _sort_key(r.get(column)), reverse="desc" in bits[1:])
            total = len(rows)
            offset = int(p.get("offset", 0))
            limit = int(p["limit"]) if "limit" in p else total
            limit = min(limit, DB.config["max_rows"])
            page = rows[offset : offset + limit]
        select = p.get("select", "*")
        if select != "*":
            cols = [c.strip() for c in select.split(",")]
            page = [{c: r.get(c) for c in cols} for r in page]
        end = offset + len(page) - 1
        total_s = str(total) if "count=" in self._prefer() else "*"
        content_range = f"{offset}-{end}/{total_s}" if page else f"*/{total_s}"
        status = 206 if (total_s != "*" and len(page) < total) else 200
        self._send(status, page, {"Content-Range": content_range})

    do_HEAD = do_GET

    def do_POST(self) -> None:
        parts, params = self._parse()
        if parts and parts[0] == "__test__":
            return self._control(parts[1] if len(parts) > 1 else "")
        if parts[:3] == ["rest", "v1", "rpc"] and len(parts) == 4:
            return self._rpc(parts[3], self._body() or {})
        table = self._table(parts)
        if table is None:
            return self._error(404, "not found")
        self._latency()
        body = self._body()
        rows = body if isinstance(body, list) else [body]
        upsert = "resolution=merge-duplicates" in self._prefer()
        with DB.lock:
            out = []
            pk = PRIMARY_KEYS.get(table)
            for row in rows:
                row = dict(row)
                existing = None
                if upsert and pk and row.get(pk) is not None:
                    existing = next((r for r in DB.tables.setdefault(table, []) if r.get(pk) == row[pk]), None)
                if existing is not None:
                    existing.update(row)
                    out.append(dict(existing))
                else:
                    out.append(dict(DB._add(table, row)))
        self._send(201, out if "return=representation" in self._prefer() else None)

    def _rpc(self, name: str, args: dict) -> None:
        """Same rules as db/save_schedule.sql (tested against Postgres in test_save_schedule_sql.py)."""
        if name != "save_schedule" or not DB.config["has_save_function"]:
            return self._error(404, f"Could not find the function public.{name}", "PGRST202")
        self._latency()
        with DB.lock:
            meta = next((r for r in DB.tables["app_meta"] if r.get("key") == "data_version"), None)
            current = str(meta["value"]) if meta else "0"
            if current != str(args.get("expected_version") or "0"):
                return self._error(409, "schedule_conflict", "PT409")
            if DB.config["fail_save"]:
                return self._error(500, "simulated failure: save rejected")
            deletes = {str(i) for i in args.get("deletes") or []}
            rows = [r for r in DB.tables["order_book"] if str(r.get("id")) not in deletes]
            DB.tables["order_book"] = rows
            for change in args.get("upserts") or []:
                values = {k: v for k, v in change.items() if k != "id"}
                if change.get("id") is None:
                    DB._add("order_book", values)
                else:
                    target = next((r for r in rows if str(r.get("id")) == str(change["id"])), None)
                    if target is not None:
                        target.update(values)
            version = str((int(current) if current.isdigit() else 0) + 1)
            if meta is None:
                DB.tables["app_meta"].append({"key": "data_version", "value": version})
            else:
                meta["value"] = version
            saved_at = datetime.now(timezone.utc).isoformat(sep=" ")
            stamp = next((r for r in DB.tables["app_meta"] if r.get("key") == "data_saved_at"), None)
            if stamp is None:
                DB.tables["app_meta"].append({"key": "data_saved_at", "value": saved_at})
            else:
                stamp["value"] = saved_at
            DB.saves += 1
        self._send(200, version)

    def do_PATCH(self) -> None:
        parts, params = self._parse()
        table = self._table(parts)
        if table is None:
            return self._error(404, "not found")
        self._latency()
        changes = self._body() or {}
        with DB.lock:
            out = []
            for row in DB.tables.get(table, []):
                if _matches(row, self._filters(params)):
                    row.update(changes)
                    out.append(dict(row))
        self._send(200, out)

    def do_DELETE(self) -> None:
        parts, params = self._parse()
        table = self._table(parts)
        if table is None:
            return self._error(404, "not found")
        self._latency()
        with DB.lock:
            keep, gone = [], []
            for row in DB.tables.get(table, []):
                (gone if _matches(row, self._filters(params)) else keep).append(row)
            DB.tables[table] = keep
        self._send(200, gone if "return=representation" in self._prefer() else None)


def start(port: int = 0) -> tuple[ThreadingHTTPServer, str]:
    """Start the fake server in a background thread; return (server, base_url)."""
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"
