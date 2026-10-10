"""Generate synthetic ELKA-like data (kidswear, store + e-shop) into a tenant database.

Phase 0 only: lets the dashboard and email be built and judged before real exports arrive.
Deterministic (seeded), so screenshots and tests are reproducible.
"""
import argparse
import random
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

from app.calendar_cz import holiday_name, season  # noqa: E402
from app.config import load_tenant  # noqa: E402
from app.db import connect, migrate  # noqa: E402
from app.loaders import ensure_dim_date  # noqa: E402

SIZES = [("50", 1), ("56", 2), ("62", 3), ("68", 4), ("74", 5), ("80", 6), ("86", 7),
         ("92", 8), ("98", 9), ("104", 10), ("110", 11), ("116", 12), ("122", 13),
         ("128", 14), ("134", 15), ("140", 16), ("152", 17), ("164", 18), ("176", 19)]
BRANDS = {"Mayoral": 2.3, "Name It": 2.2, "Tape à l'oeil": 2.4, "Boboli": 2.3, "Lola": 2.2}
CATEGORIES = ["Body", "Kalhoty", "Tričko", "Šaty", "Bunda", "Mikina", "Čepice"]
SOURCES = [("google", "organic"), ("google", "cpc"), ("facebook", "paid"), ("instagram", "social"),
           ("newsletter", "email"), ("(direct)", "(none)")]
WEEKDAY_WEIGHT = [0.8, 0.85, 0.9, 1.0, 1.1, 1.5, 0.6]  # Mon..Sun


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tenant", default="elka")
    ap.add_argument("--end", default=str(date.today() - timedelta(days=1)))
    ap.add_argument("--years", type=int, default=3)
    ap.add_argument("--styles", type=int, default=60)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    end = date.fromisoformat(args.end)
    start = end - timedelta(days=365 * args.years)
    tenant = load_tenant(args.tenant)
    conn = connect(tenant)
    migrate(conn, Path(__file__).resolve().parents[1] / "db" / "migrations")
    conn.execute("TRUNCATE fact_order_line, fact_stock_daily, fact_traffic_daily, fact_ad_spend_daily, "
                 "dim_variant, dim_customer, dim_date, job_run RESTART IDENTITY CASCADE")

    ensure_dim_date(conn, start, end)

    # dim_variant
    variants = []  # (variant_id, product_id, price, brand, popularity, size_idx)
    vid = 1
    with conn.cursor() as cur:
        for pid in range(1, args.styles + 1):
            brand = rng.choice(list(BRANDS))
            cat = rng.choice(CATEGORIES)
            price = round(rng.uniform(249, 1290), -1)
            lo = rng.randint(0, 8)
            sizes = SIZES[lo:lo + rng.randint(5, 8)]
            pop = rng.uniform(0.3, 3.0)
            peak = rng.randint(2, len(sizes) - 2) if len(sizes) > 4 else 1
            for i, (sz, order) in enumerate(sizes):
                weight = pop * max(0.15, 1 - abs(i - peak) * 0.3)
                cur.execute(
                    "INSERT INTO dim_variant VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (vid, f"{brand[:3].upper()}-{pid:03d}-{sz}", pid, f"{cat} {pid}", brand, cat,
                     season(end), sz, order, rng.choice(["modrá", "růžová", "bílá", "šedá"]), price))
                variants.append((vid, pid, price, brand, weight, i))
                vid += 1
    cost_known = {pid: rng.random() < 0.55 for pid in range(1, args.styles + 1)}

    # customers + orders
    customers = []
    order_id = 1
    stock = {v[0]: rng.randint(0, 6) for v in variants}
    weights = [v[4] for v in variants]
    with conn.cursor() as cur:
        d = start
        while d <= end:
            base = 14 * WEEKDAY_WEIGHT[d.weekday()]
            if holiday_name(d):
                base *= 0.3
            if d.month in (11, 12):
                base *= 1.4
            n_orders = max(0, int(rng.gauss(base, base * 0.25)))
            for _ in range(n_orders):
                channel = "store" if rng.random() < 0.62 else "web"
                hour = rng.choices(range(9, 18), weights=[1, 2, 3, 3, 2, 3, 4, 3, 1])[0] if channel == "store" \
                    else rng.choices(range(0, 24), weights=[1] * 7 + [2, 3, 3, 3, 3, 3, 3, 3, 3, 3, 4, 5, 6, 6, 5, 3, 2])[0]
                capture = 0.45 if channel == "store" else 1.0
                cust = None
                if rng.random() < capture:
                    if customers and rng.random() < 0.35:
                        cust = rng.choice(customers)
                    else:
                        cust = len(customers) + 1
                        customers.append(cust)
                        cur.execute("INSERT INTO dim_customer VALUES (%s,%s,%s,%s,%s)",
                                    (cust, d, channel, None, rng.random() < 0.6))
                src, med = rng.choice(SOURCES) if channel == "web" else (None, None)
                for ln in range(1, rng.choice([1, 1, 2, 2, 3]) + 1):
                    v = rng.choices(variants, weights=weights)[0]
                    qty = 1 if rng.random() < 0.85 else 2
                    disc_pct = rng.choice([0, 0, 0, 0.2, 0.3])
                    net = round(v[2] / 1.21 * qty * (1 - disc_pct), 2)
                    cost_src = None
                    unit_cost = None
                    if args.tenant == "elka":
                        ratio = BRANDS[v[3]]
                        unit_cost = round(v[2] / 1.21 / ratio, 2)
                        cost_src = "known" if cost_known[v[1]] else "estimated"
                    cur.execute(
                        "INSERT INTO fact_order_line VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (order_id, ln, d, hour, channel, v[0], qty, net, round(v[2] / 1.21 * qty * disc_pct, 2),
                         unit_cost, cost_src, cust, src, med, None))
                    stock[v[0]] = max(0, stock[v[0]] - qty)
                    if stock[v[0]] == 0 and rng.random() < 0.02:
                        stock[v[0]] = rng.randint(2, 6)  # occasional restock
                order_id += 1
            d += timedelta(days=1)
            if (end - d).days <= 120:  # stock history only for the recent window
                for v in variants:
                    price = v[2]
                    q = stock[v[0]]
                    ratio = BRANDS[v[3]]
                    cur.execute("INSERT INTO fact_stock_daily VALUES (%s,%s,%s,%s,%s)",
                                (v[0], d - timedelta(days=1), q, round(q * price / 1.21 / ratio, 2), round(q * price, 2)))
    chan = [("Organic Search", 60), ("Direct", 40), ("Paid Social", 25), ("Email", 12), ("Organic Social", 18)]
    with conn.cursor() as cur:
        d = start
        while d <= end:
            for name, base in chan:
                sessions = max(0, int(rng.gauss(base, base * 0.3)))
                cur.execute("INSERT INTO fact_traffic_daily VALUES (%s,%s,%s,%s,%s,%s)",
                            (d, name, sessions, int(sessions * 0.8), int(sessions * 0.08), int(sessions * 0.03)))
            d += timedelta(days=1)
    conn.commit()
    print(f"seeded {order_id - 1} orders, {len(customers)} customers, {len(variants)} variants "
          f"for tenant {args.tenant} ({start}..{end})")


if __name__ == "__main__":
    main()
