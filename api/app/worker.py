"""Scheduler: orders every 15 min, catalogue nightly at 02:00, daily email at the tenant's send time."""
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .brevo import send_email
from .config import load_tenant, woo_client
from .db import connect, migrate
from .email_render import build_email
from .ga4 import sync_ga4
from .ingest import refresh_line_costs, run_log, sync_catalogue, sync_orders

log = logging.getLogger("worker")


def tick(tenant, conn, client, now: datetime) -> None:
    """One scheduler pass; `now` is tenant-local. Idempotent per minute via job_run lookups."""
    hhmm = now.strftime("%H:%M")
    last = lambda job: conn.execute(  # noqa: E731
        "SELECT MAX(started_at) AS t FROM job_run WHERE job = %s", (job,)).fetchone()["t"]

    t = last("orders")
    if t is None or (now - t.astimezone(now.tzinfo)).total_seconds() >= 900:
        _safe(sync_orders, conn, client, tenant, now.date())
    if hhmm >= "02:00" and (last("catalogue") is None or last("catalogue").astimezone(now.tzinfo).date() != now.date()):
        _safe(sync_catalogue, conn, client, tenant, now.date())
    if tenant.ga4 and hhmm >= "03:00" and (last("ga4") is None or last("ga4").astimezone(now.tzinfo).date() != now.date()):
        _safe(lambda c, _cl, t, today: sync_ga4(c, t, today), conn, client, tenant, now.date())
    if hhmm >= tenant.email.get("send_time", "06:30") and (last("email") is None or last("email").astimezone(now.tzinfo).date() != now.date()):
        with run_log(conn, "email") as st:
            mail = build_email(conn, now.date(), tenant)
            sent = send_email(tenant, mail["subject"], mail["html"])
            st["message"] = "sent" if sent else "dry run (no BREVO_API_KEY / sender / recipients)"


def _safe(fn, conn, client, tenant, today):
    try:
        fn(conn, client, tenant, today)
    except Exception:  # noqa: BLE001  logged in job_run; the loop keeps going
        log.exception("%s failed", getattr(fn, "__name__", "job"))


def main(tenant_id: str) -> None:
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)  # one line per API request drowns real errors
    tenant = load_tenant(tenant_id)
    client = woo_client(tenant)
    tz = ZoneInfo(tenant.timezone)
    mig = Path(os.environ.get("MIGRATIONS_DIR", Path(__file__).resolve().parents[2] / "db" / "migrations"))
    with connect(tenant) as conn:
        migrate(conn, mig)  # schema is applied on every start; migrations are idempotent
        refresh_line_costs(conn, tenant)  # backfill cost / estimated margin on lines synced before this setting existed
    while True:
        with connect(tenant) as conn:
            tick(tenant, conn, client, datetime.now(tz))
        time.sleep(60)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "elka")
