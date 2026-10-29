"""Shared pytest fixtures.

Browser tests start the real Streamlit apps against the in-memory fake
Supabase server in ``fake_supabase.py``. Secrets come only from a temporary
file, so a real ``.streamlit/secrets.toml`` on your machine is never read.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

import fake_supabase

REPO = Path(__file__).resolve().parents[1]
PASSWORD = "test-pass"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class FakeSupabase:
    """Handle for the fake database: seed rows, change settings, read results."""

    def __init__(self, url: str) -> None:
        self.url = url

    def _post(self, path: str, payload: dict) -> dict:
        req = urllib.request.Request(
            f"{self.url}/__test__/{path}",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read() or b"{}")

    def reset(self, orders: list[dict] | None = None, **config) -> None:
        version = str(time.time_ns())  # unique, so customer caches never reuse old data
        tables = {"order_book": orders or [], "app_meta": [{"key": "data_version", "value": version}]}
        self._post("reset", {"tables": tables, "config": config})

    def configure(self, **config) -> None:
        self._post("config", config)

    def dump(self) -> dict:
        with urllib.request.urlopen(f"{self.url}/__test__/dump") as resp:
            return json.loads(resp.read())

    def orders(self) -> list[dict]:
        return self.dump()["tables"]["order_book"]

    def reads(self, table: str) -> int:
        return self.dump()["reads"].get(table, 0)


@pytest.fixture(scope="session")
def fake_db():
    server, url = fake_supabase.start()
    db = FakeSupabase(url)
    db.reset()
    yield db
    server.shutdown()


@pytest.fixture(scope="session")
def secrets_file(fake_db, tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("secrets") / "secrets.toml"
    path.write_text(
        f'SUPABASE_URL = "{fake_db.url}"\n'
        'SUPABASE_KEY = "fake.test.key"\n'
        f'UPDATE_PASSWORD = "{PASSWORD}"\n'
        "\n[customers.acme]\n"
        'password = "acme-pass"\n'
        'customer_names = ["Acme Corp"]\n'
        "\n[tokens]\n"
        'acme-token = "Acme Corp"\n'
    )
    return path


def _start_streamlit(script: Path, secrets: Path, workdir: Path):
    port = _free_port()
    env = dict(os.environ, HOME=str(workdir), PYTHONDONTWRITEBYTECODE="1")
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "streamlit", "run", str(script),
            "--server.headless=true",
            f"--server.port={port}",
            "--server.fileWatcherType=none",
            "--browser.gatherUsageStats=false",
            f"--secrets.files={secrets}",
        ],
        cwd=workdir,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 60
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{url}/_stcore/health", timeout=1) as resp:
                if resp.read() == b"ok":
                    return proc, url
        except OSError:
            time.sleep(0.3)
    proc.kill()
    raise RuntimeError(f"Streamlit did not start:\n{proc.stdout.read().decode()}")


@pytest.fixture(scope="session")
def admin_url(secrets_file, tmp_path_factory):
    proc, url = _start_streamlit(REPO / "admin" / "app.py", secrets_file, tmp_path_factory.mktemp("admin"))
    yield url
    proc.terminate()
    proc.wait(timeout=10)


@pytest.fixture(scope="session")
def customer_url(secrets_file, tmp_path_factory):
    proc, url = _start_streamlit(REPO / "customer" / "customer_specific_app.py", secrets_file, tmp_path_factory.mktemp("cust"))
    yield url
    proc.terminate()
    proc.wait(timeout=10)


@pytest.fixture(scope="session")
def browser():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def page(browser):
    context = browser.new_context(viewport={"width": 1400, "height": 1100}, accept_downloads=True)
    pg = context.new_page()
    pg.set_default_timeout(20_000)
    yield pg
    context.close()
