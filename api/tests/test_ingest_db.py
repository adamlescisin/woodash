"""Integration test against a real Postgres: set TEST_DATABASE_URL to an empty database to run it."""
import json
import os
from datetime import date
from pathlib import Path

import httpx
import psycopg
import pytest
from psycopg.rows import dict_row

from app.config import Tenant
from app.ingest import sync_catalogue, sync_orders
from app.woo import WooClient

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL not set")

TENANT = Tenant(id="t", name="T", currency="CZK", timezone="Europe/Prague", database_url_env="X",
                woo={"cost_meta_keys": ["_cost"], "backfill_from": "2025-01-01"}, margin={"default": 0.20, "brands": {}})

PRODUCTS = [{"id": 10, "type": "variable", "name": "Kalhoty Mayoral", "sku": "P", "categories": [{"name": "Kalhoty"}],
             "meta_data": [{"key": "_cost", "value": "200"}], "attributes": []},
            {"id": 20, "type": "simple", "name": "Čepice", "sku": "S-1", "price": "300", "categories": [], "meta_data": [], "attributes": []},
            {"id": 30, "type": "simple", "name": "Ponožky", "sku": "S-2", "price": "100", "categories": [],
             "meta_data": [{"key": "_cost", "value": "999"}], "attributes": []}]
VARIATIONS = [{"id": 11, "sku": "A-1", "price": "500", "manage_stock": True, "stock_quantity": 3, "meta_data": [],
               "attributes": [{"name": "velikost", "option": "68 (4-6 měs.)"}, {"name": "barva", "option": "modrá"}]}]
ORDERS = [{"id": 101, "status": "completed", "created_via": "checkout", "customer_id": 0, "refunds": [],
           "date_created_gmt": "2026-10-09T10:00:00", "date_modified_gmt": "2026-10-09T10:05:00",
           "billing": {"email": "a@b.cz"}, "meta_data": [],
           "line_items": [{"id": 1, "product_id": 10, "variation_id": 11, "quantity": 2, "subtotal": "1000", "total": "900", "sku": "A-1"},
                          {"id": 2, "product_id": 20, "variation_id": 0, "quantity": 1, "subtotal": "300", "total": "300", "sku": "S-1"},
                          {"id": 3, "product_id": 30, "variation_id": 0, "quantity": 2, "subtotal": "200", "total": "200", "sku": "S-2"}]}]


def handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path.endswith("/products") and "page=1" in str(request.url):
        return httpx.Response(200, json=PRODUCTS)
    if path.endswith("/products/10/variations"):
        return httpx.Response(200, json=VARIATIONS)
    if path.endswith("/products/10/variations/11"):
        return httpx.Response(200, json={**VARIATIONS[0], "stock_quantity": 1})
    if path.endswith("/products/20") or path.endswith("/products/30"):
        return httpx.Response(200, json=next(p for p in PRODUCTS if path.endswith(f"/{p['id']}")))
    if path.endswith("/orders"):
        return httpx.Response(200, json=ORDERS)
    return httpx.Response(404)


@pytest.fixture
def conn():
    c = psycopg.connect(URL, row_factory=dict_row)
    c.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public")
    for p in sorted((Path(__file__).resolve().parents[2] / "db" / "migrations").glob("*.sql")):
        c.execute(p.read_text())
    c.commit()
    yield c
    c.close()


def test_catalogue_then_orders_roundtrip(conn):
    client = WooClient("https://shop.test", "k", "s", transport=httpx.MockTransport(handler))
    today = date(2026, 10, 10)
    sync_catalogue(conn, client, TENANT, today)
    v = conn.execute("SELECT size, size_order, colour, brand FROM dim_variant WHERE variant_id = 11").fetchone()
    assert (v["size"], v["size_order"], v["colour"], v["brand"]) == ("68 (4-6 měs.)", 68, "modrá", "Mayoral")
    assert conn.execute("SELECT unit_cost FROM dim_variant_cost WHERE variant_id = 11").fetchone()["unit_cost"] == 200

    assert sync_orders(conn, client, TENANT, today) == 1
    lines = {r["variant_id"]: r for r in conn.execute("SELECT * FROM fact_order_line").fetchall()}
    line = lines[11]
    assert line["net_revenue"] == 900 and line["cost_source"] == "known" and line["channel"] == "web"
    # no cost -> estimated at the default 20 % margin; an implausible cost (>= price) is ignored the same way
    assert (lines[20]["cost_source"], lines[20]["unit_cost"]) == ("estimated", 240)
    assert (lines[30]["cost_source"], lines[30]["unit_cost"]) == ("estimated", 80)
    assert conn.execute("SELECT count(*) AS n FROM dim_variant_cost").fetchone()["n"] == 1
    assert "implausible" in conn.execute("SELECT message FROM job_run WHERE job = 'catalogue'").fetchone()["message"]
    assert conn.execute("SELECT stock_qty FROM fact_stock_daily WHERE date = %s", (today,)).fetchone()["stock_qty"] == 1
    cursor = conn.execute("SELECT cursor FROM sync_state WHERE job = 'orders'").fetchone()["cursor"]
    assert cursor.isoformat().startswith("2026-10-09T10:05")

    sync_orders(conn, client, TENANT, today)  # idempotent: same order again does not duplicate lines
    assert conn.execute("SELECT count(*) AS n FROM fact_order_line").fetchone()["n"] == 3
    assert conn.execute("SELECT count(*) AS n FROM job_run WHERE errors = 0").fetchone()["n"] == 3


def test_screen_queries_run_on_synced_data(conn):
    from app import queries as q
    client = WooClient("https://shop.test", "k", "s", transport=httpx.MockTransport(handler))
    today = date(2026, 10, 10)
    sync_catalogue(conn, client, TENANT, today)
    sync_orders(conn, client, TENANT, today)
    start, end = date(2026, 9, 10), date(2026, 10, 9)
    brands = q.ranking(conn, start, end, "all", None, "brand")
    assert brands[0]["name"] == "Mayoral" and brands[0]["revenue"] == 900
    assert q.basket(conn, start, end, "web", None)["orders"] == 1
    assert q.top_products(conn, start, end, "all", "Mayoral")[0]["units"] == 2
    assert q.heatmap(conn, start, end, None) == []  # no store orders
    assert set(q.style_lists(conn, None)) == {"reorder", "markdown"}
    assert q.broken_curves(conn, None) == [] and q.dead_stock(conn, None)["top"] == []
    assert q.size_grid(conn, 10)[0]["size"] == "68 (4-6 měs.)"


def test_refresh_line_costs_applies_brand_override_and_known_cost(conn):
    from app.ingest import refresh_line_costs
    client = WooClient("https://shop.test", "k", "s", transport=httpx.MockTransport(handler))
    today = date(2026, 10, 10)
    sync_catalogue(conn, client, TENANT, today)
    sync_orders(conn, client, TENANT, today)
    t2 = Tenant(**{**TENANT.__dict__, "margin": {"default": 0.20, "brands": {"Ostatní": 0.5}}})
    refresh_line_costs(conn, t2)
    rows = {r["variant_id"]: r for r in conn.execute("SELECT * FROM fact_order_line").fetchall()}
    assert rows[20]["unit_cost"] == 150 and rows[20]["cost_source"] == "estimated"   # brand override: 50 %
    assert rows[11]["cost_source"] == "known" and rows[11]["unit_cost"] == 200
