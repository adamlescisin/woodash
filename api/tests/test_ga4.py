import json
import os
from datetime import date

import httpx
import psycopg
import pytest
from psycopg.rows import dict_row

from app.config import Tenant
from app.ga4 import fetch_rows, sync_ga4

URL = os.environ.get("TEST_DATABASE_URL")


def report(rows, total=None):
    def mk(d, ch, vals):
        return {"dimensionValues": [{"value": d}, {"value": ch}], "metricValues": [{"value": str(v)} for v in vals]}
    return {"rows": [mk(*r) for r in rows], "rowCount": total if total is not None else len(rows)}


def test_fetch_rows_parses_and_pages():
    calls = []

    def handler(req: httpx.Request):
        body = json.loads(req.content)
        calls.append(body["offset"])
        assert req.headers["authorization"] == "Bearer tok" and "465019231:runReport" in str(req.url)
        if body["offset"] == 0:
            return httpx.Response(200, json=report([("20261009", "Direct", (10, 8, 2, 1))], total=10001))
        return httpx.Response(200, json=report([("20261009", "Organic Search", (5, 4, 0, 0))], total=10001))

    rows = fetch_rows("465019231", "tok", date(2026, 10, 9), date(2026, 10, 9), httpx.MockTransport(handler))
    assert calls == [0, 10000]
    assert rows[0] == {"date": date(2026, 10, 9), "channel": "Direct", "sessions": 10, "totalUsers": 8, "addToCarts": 2, "checkouts": 1}
    assert len(rows) == 2


def test_api_error_is_reported():
    t = httpx.MockTransport(lambda r: httpx.Response(403, text="PERMISSION_DENIED"))
    with pytest.raises(RuntimeError, match="GA4 403"):
        fetch_rows("1", "tok", date(2026, 10, 1), date(2026, 10, 2), t)


@pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL not set")
def test_sync_upserts_and_resyncs_recent_days():
    from pathlib import Path
    c = psycopg.connect(URL, row_factory=dict_row)
    c.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public")
    for p in sorted((Path(__file__).resolve().parents[2] / "db" / "migrations").glob("*.sql")):
        c.execute(p.read_text())
    c.commit()
    tenant = Tenant(id="t", name="T", currency="CZK", timezone="Europe/Prague", database_url_env="X",
                    ga4={"property_id": "1", "backfill_from": "2026-10-01"})
    seen = []

    def handler(req):
        b = json.loads(req.content)
        seen.append(b["dateRanges"][0])
        return httpx.Response(200, json=report([("20261008", "Direct", (10, 8, 2, 1))]))

    assert sync_ga4(c, tenant, date(2026, 10, 10), token="tok", transport=httpx.MockTransport(handler)) == 1
    assert seen[0] == {"startDate": "2026-10-01", "endDate": "2026-10-09"}
    # second run re-reads the last 14 days from the newest stored date; values are upserted, not duplicated
    handler2 = lambda req: httpx.Response(200, json=report([("20261008", "Direct", (12, 9, 3, 1))]))  # noqa: E731
    sync_ga4(c, tenant, date(2026, 10, 11), token="tok", transport=httpx.MockTransport(handler2))
    rows = c.execute("SELECT sessions, add_to_carts FROM fact_traffic_daily").fetchall()
    assert rows == [{"sessions": 12, "add_to_carts": 3}]
    assert c.execute("SELECT count(*) AS n FROM job_run WHERE job = 'ga4' AND errors = 0").fetchone()["n"] == 2
