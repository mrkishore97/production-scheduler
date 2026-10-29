import pytest
from supabase import create_client

from production_scheduler.supabase_io import fetch_all_rows
from sample_data import bulk_orders


@pytest.fixture
def client(fake_db):
    return create_client(fake_db.url, "fake.test.key")


def test_reads_past_the_row_cap(fake_db, client):
    fake_db.reset(bulk_orders(2500), max_rows=1000)
    fetched = fetch_all_rows(client, "order_book")
    assert fetched.complete
    assert len(fetched.rows) == 2500
    assert len({r["id"] for r in fetched.rows}) == 2500  # no row twice


def test_server_cap_smaller_than_page_size(fake_db, client):
    fake_db.reset(bulk_orders(1200), max_rows=250)
    fetched = fetch_all_rows(client, "order_book")
    assert fetched.complete and len(fetched.rows) == 1200


def test_empty_table(fake_db, client):
    fake_db.reset([])
    fetched = fetch_all_rows(client, "order_book")
    assert fetched.complete and fetched.rows == []
    assert fetched.problem() is None


def test_without_id_column_small_table_is_complete(fake_db, client):
    fake_db.reset(bulk_orders(300), has_id=False)
    assert fetch_all_rows(client, "order_book").complete


def test_without_id_column_large_table_is_reported_incomplete(fake_db, client):
    fake_db.reset(bulk_orders(1500), has_id=False)
    fetched = fetch_all_rows(client, "order_book")
    assert not fetched.complete
    assert "1000 of 1500" in fetched.problem()
