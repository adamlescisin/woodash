"""Load a WooCommerce order-export JSON (flat plugin export) into a tenant database.

Stopgap for Phase 0 until the REST ingestion exists (Phase 1). Mapping and assumptions:
- Channel: no shipping method -> `store` (POS / counter sale), otherwise `web`.
- Net revenue per line = item_price * qty, minus the order discount allocated pro rata.
  Shipping is excluded. The export shows 0 tax everywhere, so prices are treated as net (tenant `vat_payer: false`).
- SKU 'a-b-c-d' -> style key 'a-b-c', size 'd' (supplier-style-colour-size; to be confirmed).
- Lines without SKU get a stable placeholder SKU from the product name.
- Order Attribution and cost are not in this export -> NULL.
- Personal data: only a one-way hash of the billing e-mail is kept as customer key. Names, addresses
  and phone numbers are never copied (spec: Security and GDPR).
"""
import argparse
import hashlib
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

from app.calendar_cz import season  # noqa: E402
from app.config import load_tenant  # noqa: E402
from app.db import connect, migrate  # noqa: E402
from app.loaders import ensure_dim_date  # noqa: E402

CATEGORIES = ["bunda", "košile", "boxerky", "čepice", "čepička", "kalhoty", "tričko", "šaty", "mikina", "body", "svetr", "sukně"]


def h(s: str) -> int:
    return int(hashlib.sha256(s.encode()).hexdigest()[:12], 16)


def brand_of(name: str) -> str:
    for b in ("Mayoral", "Name It", "Boboli", "Tape"):
        if b.lower() in name.lower():
            return b
    return "Ostatní"


def category_of(name: str) -> str:
    low = name.lower()
    return next((c for c in CATEGORIES if c in low), "Ostatní")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--tenant", default="elka")
    ap.add_argument("--keep", action="store_true", help="do not truncate existing data first")
    a = ap.parse_args()

    orders = json.loads(Path(a.file).read_text())
    tenant = load_tenant(a.tenant)
    conn = connect(tenant)
    migrate(conn, Path(__file__).resolve().parents[1] / "db" / "migrations")
    if not a.keep:
        conn.execute("TRUNCATE fact_order_line, fact_stock_daily, fact_traffic_daily, fact_ad_spend_daily, "
                     "dim_variant, dim_customer, dim_date, job_run RESTART IDENTITY CASCADE")

    dates = [datetime.strptime(o["order_date"], "%Y-%m-%d %H:%M") for o in orders]
    ensure_dim_date(conn, min(dates).date(), max(dates).date())

    variants: dict[str, int] = {}
    customers: dict[str, tuple] = {}
    lines, skipped = [], 0
    for o, dt in zip(orders, dates):
        if o["order_status"] not in ("Dokončeno", "Zpracovává se"):
            skipped += 1
            continue
        channel = "web" if o["shipping_method_title"] else "store"
        email = (o["billing_email"] or "").strip().lower()
        cust = None
        if email:
            cust = h("cust:" + email)
            first = customers.get(cust)
            if not first or dt.date() < first[0]:
                customers[cust] = (dt.date(), channel)
        gross = sum(p["item_price"] * p["qty_minus_refund"] for p in o["products"])
        disc = float(o["cart_discount"] or 0)
        for i, p in enumerate(o["products"], 1):
            qty = p["qty_minus_refund"]
            if qty <= 0:
                continue
            sku = p["sku"] or f"NOSKU-{h(p['name']) % 10**8}"
            if sku not in variants:
                variants[sku] = len(variants) + 1
            share = (p["item_price"] * qty / gross) if gross else 0
            line_disc = round(disc * share, 2)
            lines.append((int(o["order_number"]), i, dt.date(), dt.hour, channel, sku, p["name"], qty,
                          round(p["item_price"] * qty - line_disc, 2), line_disc, cust, float(p["item_price"])))

    with conn.cursor() as cur:
        meta = {}
        for ln in lines:
            meta.setdefault(ln[5], (ln[6], ln[11], ln[2]))
        for sku, vid in variants.items():
            name, price, d0 = meta[sku]
            parts = sku.split("-")
            style = "-".join(parts[:3]) if len(parts) == 4 else sku
            size = parts[3] if len(parts) == 4 else "n/a"
            cur.execute("INSERT INTO dim_variant VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (vid, sku, h(style) % 10**9, name, brand_of(name), category_of(name), season(d0),
                         size, int(size) if size.isdigit() else 0, None, price))
        for cid, (d0, ch) in customers.items():
            cur.execute("INSERT INTO dim_customer VALUES (%s,%s,%s,NULL,FALSE)", (cid, d0, ch))
        for (oid, ln, d, hr, ch, sku, _n, qty, net, disc, cust, _p) in lines:
            cur.execute("INSERT INTO fact_order_line VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NULL,NULL,%s,NULL,NULL,NULL)",
                        (oid, ln, d, hr, ch, variants[sku], qty, net, disc, cust))
    conn.commit()
    by_ch = defaultdict(float)
    for ln in lines:
        by_ch[ln[4]] += ln[8]
    print(f"imported {len(lines)} lines from {len(orders) - skipped} orders ({skipped} skipped), "
          f"{len(variants)} variants, {len(customers)} hashed customers; revenue by channel: "
          + ", ".join(f"{k} {v:,.0f}" for k, v in by_ch.items()))


if __name__ == "__main__":
    main()
