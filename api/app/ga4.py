"""GA4 Data API -> fact_traffic_daily (sessions, users, add-to-carts, checkouts per channel per day).

GA4 is used for traffic and funnel only; consent mode hides part of the sessions, so WooCommerce stays
the source of truth for orders (spec: Data sources). Recent days are re-read every night because GA revises them.
"""
import os
from datetime import date, timedelta

import httpx

from .config import Tenant
from .ingest import run_log
from .loaders import ensure_dim_date

SCOPE = "https://www.googleapis.com/auth/analytics.readonly"
METRICS = ["sessions", "totalUsers", "addToCarts", "checkouts"]
RESYNC_DAYS = 14
CHUNK_DAYS = 90


def service_account_token(path: str) -> str:
    from google.auth.transport.requests import Request
    from google.oauth2 import service_account

    creds = service_account.Credentials.from_service_account_file(path, scopes=[SCOPE])
    creds.refresh(Request())
    return creds.token


def fetch_rows(property_id: str, token: str, start: date, end: date,
               transport: httpx.BaseTransport | None = None) -> list[dict]:
    """All (date, channel, metrics) rows for the range, following pagination."""
    http = httpx.Client(transport=transport, timeout=60, headers={"Authorization": f"Bearer {token}"})
    url = f"https://analyticsdata.googleapis.com/v1beta/properties/{property_id}:runReport"
    out, offset = [], 0
    while True:
        r = http.post(url, json={
            "dateRanges": [{"startDate": start.isoformat(), "endDate": end.isoformat()}],
            "dimensions": [{"name": "date"}, {"name": "sessionDefaultChannelGroup"}],
            "metrics": [{"name": m} for m in METRICS],
            "limit": 10000, "offset": offset,
        })
        if r.is_error:
            raise RuntimeError(f"GA4 {r.status_code}: {r.text[:300]}")
        body = r.json()
        for row in body.get("rows", []):
            d, ch = (v["value"] for v in row["dimensionValues"])
            m = [int(float(v["value"])) for v in row["metricValues"]]
            out.append({"date": date(int(d[:4]), int(d[4:6]), int(d[6:])), "channel": ch, **dict(zip(METRICS, m))})
        offset += 10000
        if offset >= int(body.get("rowCount", 0)):
            return out


def sync_ga4(conn, tenant: Tenant, today: date, token: str | None = None,
             transport: httpx.BaseTransport | None = None) -> int:
    cfg = tenant.ga4
    with run_log(conn, "ga4") as st:
        token = token or service_account_token(os.environ[cfg["credentials_env"]])
        last = conn.execute("SELECT MAX(date) AS d FROM fact_traffic_daily").fetchone()["d"]
        start = (last - timedelta(days=RESYNC_DAYS)) if last else date.fromisoformat(cfg.get("backfill_from", "2023-10-01"))
        end = today - timedelta(days=1)
        while start <= end:
            chunk_end = min(start + timedelta(days=CHUNK_DAYS - 1), end)
            rows = fetch_rows(cfg["property_id"], token, start, chunk_end, transport)
            if rows:
                ensure_dim_date(conn, min(r["date"] for r in rows), max(r["date"] for r in rows))
            for r in rows:
                conn.execute(
                    "INSERT INTO fact_traffic_daily VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (date, channel) DO UPDATE SET "
                    "sessions=EXCLUDED.sessions, users=EXCLUDED.users, add_to_carts=EXCLUDED.add_to_carts, checkouts=EXCLUDED.checkouts",
                    (r["date"], r["channel"], r["sessions"], r["totalUsers"], r["addToCarts"], r["checkouts"]))
            conn.commit()
            st["rows"] += len(rows)
            start = chunk_end + timedelta(days=1)
        return st["rows"]
