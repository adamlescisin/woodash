from datetime import date, timedelta

from fastapi import FastAPI, HTTPException

from .config import load_tenant
from .db import connect
from .facts import stock_alerts, yesterday_facts

app = FastAPI(title="woodash")


def _conn(tenant_id: str):
    try:
        return load_tenant(tenant_id), None
    except KeyError:
        raise HTTPException(404, "unknown tenant")


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/api/{tenant_id}/overview")
def overview(tenant_id: str, as_of: date | None = None):
    tenant, _ = _conn(tenant_id)
    today = as_of or date.today()
    with connect(tenant) as conn:
        f = yesterday_facts(conn, today)
        trend = conn.execute(
            "SELECT date, SUM(net_revenue) AS revenue FROM v_daily_sales WHERE date > %s AND date <= %s "
            "GROUP BY date ORDER BY date", (today - timedelta(days=31), today - timedelta(days=1))).fetchall()
        st = stock_alerts(conn)
    return {
        "tenant": tenant.name, "features": tenant.features, "facts": f,
        "trend": [{"date": r["date"], "revenue": float(r["revenue"])} for r in trend],
        "alerts": {"broken_size_curves": [r["product_name"] for r in st["broken"]],
                   "sold_out": st["sold_out"], "dead_stock": st["dead_total"]},
    }


def _period(days: int, as_of: date | None) -> tuple[date, date]:
    end = (as_of or date.today()) - timedelta(days=1)
    return end - timedelta(days=days - 1), end


def _num(rows):
    """Decimal -> float for JSON."""
    from decimal import Decimal
    if isinstance(rows, list):
        return [_num(r) for r in rows]
    if isinstance(rows, dict):
        return {k: _num(v) for k, v in rows.items()}
    return float(rows) if isinstance(rows, Decimal) else rows


@app.get("/api/{tenant_id}/sales")
def sales(tenant_id: str, days: int = 30, channel: str = "all", brand: str | None = None, as_of: date | None = None):
    from . import queries as q
    tenant, _ = _conn(tenant_id)
    start, end = _period(max(1, min(days, 365)), as_of)
    with connect(tenant) as conn:
        return _num({
            "period": {"start": start, "end": end}, "channel": channel, "brand": brand,
            "brands": q.ranking(conn, start, end, channel, brand, "brand"),
            "categories": q.ranking(conn, start, end, channel, brand, "category"),
            "top_products": q.top_products(conn, start, end, channel, brand),
            "heatmap": q.heatmap(conn, start, end, brand) if tenant.has("pos") else [],
            "basket": q.basket(conn, start, end, channel, brand),
        })


@app.get("/api/{tenant_id}/stock")
def stock(tenant_id: str, brand: str | None = None):
    from . import queries as q
    tenant, _ = _conn(tenant_id)
    with connect(tenant) as conn:
        return _num({"styles": q.style_lists(conn, brand), "broken_curves": q.broken_curves(conn, brand),
                     "dead_stock": q.dead_stock(conn, brand)})


@app.get("/api/{tenant_id}/stock/{product_id}")
def stock_style(tenant_id: str, product_id: int):
    from . import queries as q
    tenant, _ = _conn(tenant_id)
    with connect(tenant) as conn:
        return _num({"product_id": product_id, "sizes": q.size_grid(conn, product_id)})


@app.get("/api/{tenant_id}/brands")
def brands(tenant_id: str):
    tenant, _ = _conn(tenant_id)
    with connect(tenant) as conn:
        rows = conn.execute("SELECT brand FROM dim_variant GROUP BY brand ORDER BY COUNT(*) DESC").fetchall()
    return [r["brand"] for r in rows]
