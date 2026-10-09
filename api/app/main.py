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
