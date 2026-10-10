"""WooCommerce -> warehouse sync jobs. Raw responses are stored first, then transformed (spec: ingestion rules)."""
from contextlib import contextmanager
from datetime import date, datetime, timezone

from psycopg.types.json import Jsonb

from .config import Tenant
from .loaders import ensure_dim_date
from .transform import attr, cost_of, order_lines


@contextmanager
def run_log(conn, job: str):
    """Every job writes rows read / errors / duration; failures stay visible in dashboard and email."""
    run = conn.execute("INSERT INTO job_run (job) VALUES (%s) RETURNING id", (job,)).fetchone()["id"]
    conn.commit()
    stats = {"rows": 0, "errors": 0, "message": None}
    try:
        yield stats
    except Exception as e:  # noqa: BLE001
        conn.rollback()
        stats["errors"] += 1
        stats["message"] = f"{type(e).__name__}: {e}"[:500]
        raise
    finally:
        conn.execute("UPDATE job_run SET finished_at = now(), rows_read = %s, errors = %s, message = %s WHERE id = %s",
                     (stats["rows"], stats["errors"], stats["message"], run))
        conn.commit()


def _cursor(conn, job: str, default: str) -> str:
    row = conn.execute("SELECT cursor FROM sync_state WHERE job = %s", (job,)).fetchone()
    return row["cursor"].astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") if row else f"{default}T00:00:00"


def _upsert_variant(conn, vid, sku, product_id, name, brand, category, size, colour, price, season="unknown"):
    first = (size or "").split(" ")[0]
    order = int(first) if first.isdigit() else 0
    conn.execute(
        "INSERT INTO dim_variant VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (variant_id) DO UPDATE SET "
        "sku=EXCLUDED.sku, product_id=EXCLUDED.product_id, product_name=EXCLUDED.product_name, brand=EXCLUDED.brand, "
        "category=EXCLUDED.category, size=EXCLUDED.size, size_order=EXCLUDED.size_order, colour=EXCLUDED.colour, "
        "current_price=EXCLUDED.current_price",
        (vid, sku or f"WC-{vid}", product_id, name, brand, category, season, size or "n/a", order, colour, price))


def _set_stock(conn, vid: int, day: date, qty: int | None, price: float, cost: float | None):
    if qty is None:
        return
    q = max(qty, 0)
    conn.execute(
        "INSERT INTO fact_stock_daily VALUES (%s,%s,%s,%s,%s) ON CONFLICT (variant_id, date) DO UPDATE SET "
        "stock_qty=EXCLUDED.stock_qty, stock_value_cost=EXCLUDED.stock_value_cost, stock_value_price=EXCLUDED.stock_value_price",
        (vid, day, q, round(q * cost, 2) if cost else None, round(q * price, 2)))


def _price(item: dict, fallback: float = 0.0) -> float:
    try:
        return float(item.get("price") or item.get("regular_price") or fallback)
    except ValueError:
        return fallback


def _store_item(conn, item: dict, parent: dict | None, tenant: Tenant, today: date) -> int:
    src = parent or item
    brand = next((b["name"] for b in src.get("brands", [])), None) or \
        next((a["options"][0] for a in src.get("attributes", []) if (a.get("name") or "").lower() in ("značka", "brand") and a.get("options")), None) or \
        ("Mayoral" if "mayoral" in src.get("name", "").lower() else "Ostatní")
    cats = [c["name"] for c in src.get("categories", [])]
    vid = item["id"]
    price = _price(item, _price(src))
    _upsert_variant(conn, vid, item.get("sku"), (parent or item)["id"], src["name"], brand, (cats or ["Ostatní"])[0],
                    attr(item, "velikost"), attr(item, "barva"), price)
    keys = tenant.woo.get("cost_meta_keys") or ()
    cost = cost_of(item, keys) or (cost_of(parent, keys) if parent else None)
    if cost:
        conn.execute("INSERT INTO dim_variant_cost VALUES (%s,%s,'known') ON CONFLICT (variant_id) DO UPDATE SET "
                     "unit_cost=EXCLUDED.unit_cost, source='known'", (vid, cost))
    if item.get("manage_stock") or item.get("stock_quantity") is not None:
        _set_stock(conn, vid, today, item.get("stock_quantity"), price, cost)
    return vid


def sync_catalogue(conn, client, tenant: Tenant, today: date) -> int:
    """Nightly: products, variations, costs and today's stock snapshot."""
    with run_log(conn, "catalogue") as st:
        ensure_dim_date(conn, today, today)
        for prod in client.pages("/products", status="any"):
            conn.execute("INSERT INTO raw_wc_products VALUES (%s, now(), %s) ON CONFLICT (id) DO UPDATE SET "
                         "fetched_at = now(), payload = EXCLUDED.payload", (prod["id"], Jsonb(prod)))
            if prod["type"] == "variable":
                for var in client.pages(f"/products/{prod['id']}/variations"):
                    _store_item(conn, var, prod, tenant, today)
                    st["rows"] += 1
            elif prod.get("sku"):
                _store_item(conn, prod, None, tenant, today)
                st["rows"] += 1
            conn.commit()
        return st["rows"]


def sync_orders(conn, client, tenant: Tenant, today: date) -> int:
    """Every 15 min: orders modified since the cursor, plus a stock refresh for the products they touched."""
    with run_log(conn, "orders") as st:
        cursor = _cursor(conn, "orders", tenant.woo.get("backfill_from", "2023-10-01"))
        newest, touched = None, set()
        for o in client.pages("/orders", modified_after=cursor, dates_are_gmt="true", status="any", orderby="date", order="asc"):
            conn.execute("INSERT INTO raw_wc_orders VALUES (%s, now(), %s) ON CONFLICT (id) DO UPDATE SET "
                         "fetched_at = now(), payload = EXCLUDED.payload", (o["id"], Jsonb(o)))
            refunds = client.get(f"/orders/{o['id']}/refunds") if o.get("refunds") else []
            lines = order_lines(o, tenant.timezone, refunds)
            conn.execute("DELETE FROM fact_order_line WHERE order_id = %s", (o["id"],))
            for ln in lines:
                ensure_dim_date(conn, ln["date"], ln["date"])
                if not conn.execute("SELECT 1 FROM dim_variant WHERE variant_id = %s", (ln["variant_id"],)).fetchone():
                    _upsert_variant(conn, ln["variant_id"], ln["sku"], ln["variant_id"], ln["name"] or "?", "Ostatní",
                                    "Ostatní", None, None, 0)
                cust = ln["customer_id"]
                if cust:
                    conn.execute("INSERT INTO dim_customer VALUES (%s,%s,%s,NULL,FALSE) ON CONFLICT (customer_id) DO UPDATE "
                                 "SET first_order_date = LEAST(dim_customer.first_order_date, EXCLUDED.first_order_date)",
                                 (cust, ln["date"], ln["channel"]))
                c = conn.execute("SELECT unit_cost, source FROM dim_variant_cost WHERE variant_id = %s", (ln["variant_id"],)).fetchone()
                conn.execute(
                    "INSERT INTO fact_order_line VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (ln["order_id"], ln["line_no"], ln["date"], ln["hour"], ln["channel"], ln["variant_id"], ln["qty"],
                     ln["net_revenue"], ln["discount"], c and c["unit_cost"], c and c["source"], cust,
                     ln["source"], ln["medium"], ln["campaign"]))
                touched.add((o_line_product(o, ln), ln["variant_id"]))
            st["rows"] += 1
            newest = max(newest or o["date_modified_gmt"], o["date_modified_gmt"])
            conn.commit()
        for pid, vid in touched:  # keep stock fresh without re-reading the whole catalogue
            path = f"/products/{pid}/variations/{vid}" if pid != vid else f"/products/{vid}"
            try:
                item = client.get(path)
                _set_stock(conn, vid, today, item.get("stock_quantity"), _price(item), None)
            except Exception as e:  # noqa: BLE001  one missing product must not fail the order sync
                st["errors"] += 1
                st["message"] = st["message"] or f"stock refresh failed for {path}: {type(e).__name__}: {e}"[:300]
        if newest:
            conn.execute("INSERT INTO sync_state VALUES ('orders', %s) ON CONFLICT (job) DO UPDATE SET cursor = EXCLUDED.cursor",
                         (datetime.fromisoformat(newest).replace(tzinfo=timezone.utc),))
        conn.commit()
        return st["rows"]


def o_line_product(order: dict, ln: dict) -> int:
    for li in order["line_items"]:
        if (li.get("variation_id") or li["product_id"]) == ln["variant_id"]:
            return li["product_id"]
    return ln["variant_id"]
