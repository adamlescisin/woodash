"""Load a WooCommerce product-export CSV (Czech headers) into dim_variant + a stock snapshot + known costs.

- Variants = `variation` rows plus `simple` rows that have a SKU. Variable parents give name/brand/category.
- variant_id = WooCommerce post ID, so the REST ingestion in Phase 1 lines up with it.
- Size from attribute `velikost` (e.g. "68 (4-6 měs.)"), colour from `barva`.
- Stock snapshot is stored as one fact_stock_daily day (--as-of); history builds up from the nightly job.
- `Nákupní cena` (purchase cost), where present on a parent or variant, becomes a `known` cost.
- Season is not in the export -> 'unknown' until products are tagged.
"""
import argparse
import csv
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

from app.config import load_tenant  # noqa: E402
from app.db import connect, migrate  # noqa: E402
from app.loaders import ensure_dim_date  # noqa: E402

PROMO_CATEGORIES = ("akce", "sleva", "výprodej")


def num(s: str) -> float | None:
    s = (s or "").strip().replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def category_of(raw: str) -> str:
    leaves = [c.strip().split(">")[-1].strip() for c in (raw or "").split(",") if c.strip()]
    plain = [c for c in leaves if not any(p in c.lower() for p in PROMO_CATEGORIES)]
    return (plain or leaves or ["Ostatní"])[0]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--tenant", default="elka")
    ap.add_argument("--as-of", default=str(date.today()))
    a = ap.parse_args()
    as_of = date.fromisoformat(a.as_of)

    rows = list(csv.DictReader(open(a.file, encoding="utf-8-sig")))
    parents = {}
    for r in rows:
        if r["Typ"] == "variable" and r["SKU"]:
            parents.setdefault(r["SKU"], r)

    tenant = load_tenant(a.tenant)
    conn = connect(tenant)
    migrate(conn, Path(__file__).resolve().parents[1] / "db" / "migrations")
    ensure_dim_date(conn, as_of, as_of)
    conn.execute("TRUNCATE fact_stock_daily, dim_variant_cost")

    seen_skus, n_var, n_stock, n_cost, n_dup = set(), 0, 0, 0, 0
    with conn.cursor() as cur:
        for r in rows:
            if r["Typ"] not in ("variation", "simple") or not r["SKU"]:
                continue
            if r["SKU"] in seen_skus:  # 39 duplicate SKUs in the export: keep the first
                n_dup += 1
                continue
            seen_skus.add(r["SKU"])
            p = parents.get(r["Nadřazené"]) if r["Typ"] == "variation" else None
            src = p or r
            vid = int(r["ID"])
            price = num(r["Akční cena"]) or num(r["Běžná cena"]) or num((p or {}).get("Běžná cena", "")) or 0
            size = (r["Hodnota(y) 1 vlastnosti"] if r["Název 1 vlastnosti"] == "velikost" else
                    r["Hodnota(y) 2 vlastnosti"] if r["Název 2 vlastnosti"] == "velikost" else "") or "n/a"
            colour = (r["Hodnota(y) 1 vlastnosti"] if r["Název 1 vlastnosti"] == "barva" else
                      r["Hodnota(y) 2 vlastnosti"] if r["Název 2 vlastnosti"] == "barva" else None)
            m = re.match(r"\d+", size)
            brand = src["Značky"] or ("Mayoral" if "mayoral" in src["Jméno"].lower() else "Ostatní")
            product_id = int(p["ID"]) if p else vid
            cur.execute(
                "INSERT INTO dim_variant VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT (variant_id) DO UPDATE SET sku=EXCLUDED.sku, product_id=EXCLUDED.product_id, "
                "product_name=EXCLUDED.product_name, brand=EXCLUDED.brand, category=EXCLUDED.category, "
                "size=EXCLUDED.size, size_order=EXCLUDED.size_order, colour=EXCLUDED.colour, current_price=EXCLUDED.current_price",
                (vid, r["SKU"], product_id, src["Jméno"], brand.replace("&amp;", "&"), category_of(src["Kategorie"]),
                 "unknown", size, int(m.group()) if m else 0, colour, price))
            n_var += 1
            cost = num(r["Nákupní cena"]) or num((p or {}).get("Nákupní cena", ""))
            if cost:
                cur.execute("INSERT INTO dim_variant_cost VALUES (%s,%s,'known')", (vid, cost))
                n_cost += 1
            qty = num(r["Sklad"])
            if qty is not None:
                q = max(int(qty), 0)
                cur.execute("INSERT INTO fact_stock_daily VALUES (%s,%s,%s,%s,%s)",
                            (vid, as_of, q, round(q * cost, 2) if cost else None, round(q * price, 2)))
                n_stock += 1
    conn.commit()
    print(f"loaded {n_var} variants ({n_dup} duplicate SKUs skipped), {n_stock} stock rows, {n_cost} known costs")


if __name__ == "__main__":
    main()
