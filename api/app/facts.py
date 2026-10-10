"""Compute every number shown in the dashboard and email. No LLM ever computes numbers."""
from datetime import date, timedelta

from .anomaly import is_anomaly
from .calendar_cz import same_day_last_year


def _day(conn, d: date) -> dict:
    rows = conn.execute(
        "SELECT channel, net_revenue, orders, units FROM v_daily_sales WHERE date = %s", (d,)
    ).fetchall()
    out = {"total": {"revenue": 0.0, "orders": 0}, "store": {"revenue": 0.0, "orders": 0}, "web": {"revenue": 0.0, "orders": 0}}
    for r in rows:
        rev, n = float(r["net_revenue"]), int(r["orders"])
        out[r["channel"]] = {"revenue": rev, "orders": n}
        out["total"]["revenue"] += rev
        out["total"]["orders"] += n
    for k in out.values():
        k["basket"] = k["revenue"] / k["orders"] if k["orders"] else 0.0
    return out


def _pct(now: float, then: float) -> float | None:
    return None if not then else (now - then) / then * 100


def yesterday_facts(conn, today: date) -> dict:
    y = today - timedelta(days=1)
    cur, ly, lw = _day(conn, y), _day(conn, same_day_last_year(y)), _day(conn, y - timedelta(days=7))
    history = [_day(conn, y - timedelta(days=7 * i))["total"]["revenue"] for i in range(1, 9)]
    anomalies = []
    if is_anomaly(cur["total"]["revenue"], history):
        anomalies.append({"kind": "revenue", "value": cur["total"]["revenue"],
                          "expected": sum(history) / len(history)})
    cov = conn.execute(
        "SELECT COALESCE(SUM(revenue_known_cost)/NULLIF(SUM(net_revenue),0),0) AS c FROM v_daily_sales "
        "WHERE date > %s", (y - timedelta(days=90),)).fetchone()["c"]
    return {
        "date": y, "current": cur, "last_year": ly, "last_week": lw,
        "yoy_pct": _pct(cur["total"]["revenue"], ly["total"]["revenue"]),
        "wow_pct": _pct(cur["total"]["revenue"], lw["total"]["revenue"]),
        "anomalies": anomalies,
        "margin_coverage": float(cov),
    }


def stock_alerts(conn) -> dict:
    broken = conn.execute(
        "SELECT p.product_name, b.top_sizes_at_zero FROM v_broken_size_curve b "
        "JOIN (SELECT DISTINCT product_id, product_name FROM dim_variant) p USING (product_id) "
        "ORDER BY b.top_sizes_at_zero DESC, p.product_name LIMIT 5").fetchall()
    sold_out = conn.execute(
        "WITH d AS (SELECT MAX(date) AS d FROM fact_stock_daily) "
        "SELECT v.sku FROM fact_stock_daily t JOIN fact_stock_daily p ON p.variant_id = t.variant_id AND p.date = t.date - 1 "
        "JOIN dim_variant v ON v.variant_id = t.variant_id, d "
        "WHERE t.date = d.d AND t.stock_qty = 0 AND p.stock_qty > 0 ORDER BY v.sku LIMIT 10").fetchall()
    dead_crossing = conn.execute(
        "SELECT COUNT(*) AS n FROM v_dead_stock WHERE days_since_sale BETWEEN 90 AND 96").fetchone()["n"]
    dead_total = conn.execute("SELECT COUNT(*) AS n FROM v_dead_stock").fetchone()["n"]
    return {"broken": broken, "sold_out": [r["sku"] for r in sold_out],
            "dead_crossing": dead_crossing, "dead_total": dead_total}


def suggested_actions(facts: dict, stock: dict) -> list[str]:
    actions = []
    if stock["broken"]:
        names = ", ".join(r["product_name"] for r in stock["broken"][:3])
        actions.append(f"Zvážit doobjednání velikostí u: {names}.")
    if stock["dead_total"]:
        actions.append(f"Projít {stock['dead_total']} variant bez prodeje 90+ dní a navrhnout slevu.")
    if facts["anomalies"]:
        actions.append("Zkontrolovat, co způsobilo neobvyklý včerejší obrat.")
    if facts["current"]["store"]["orders"] and not actions:
        actions.append("Žádná akutní akce — pokračovat podle plánu.")
    return actions[:3]


def sync_health(conn) -> dict:
    """Last successful run per job and any failed job since, for the dashboard and the email footer."""
    rows = conn.execute(
        "SELECT job, MAX(finished_at) FILTER (WHERE errors = 0) AS last_ok, "
        "COUNT(*) FILTER (WHERE errors > 0 AND finished_at > now() - interval '24 hours') AS failed_24h "
        "FROM job_run WHERE job IN ('orders','catalogue','ga4') GROUP BY job").fetchall()
    return {r["job"]: {"last_ok": r["last_ok"], "failed_24h": r["failed_24h"]} for r in rows}
