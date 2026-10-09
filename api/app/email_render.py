from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .facts import stock_alerts, suggested_actions, sync_health, yesterday_facts

env = Environment(loader=FileSystemLoader(Path(__file__).parent / "templates"),
                  autoescape=select_autoescape(["html"]))


def kc(v: float) -> str:
    return f"{v:,.0f}".replace(",", " ") + " Kč"


def pct(v: float | None) -> str:
    return "—" if v is None else f"{v:+.0f}".replace("-", "−") + " %"


env.filters["kc"], env.filters["pct"] = kc, pct

WEEKDAYS = ["pondělí", "úterý", "středa", "čtvrtek", "pátek", "sobota", "neděle"]


def summary(f: dict) -> str:
    """Placeholder for the LLM summary: deterministic text from computed facts (Phase 1 swaps in an LLM)."""
    trend = "nad" if (f["yoy_pct"] or 0) >= 0 else "pod"
    s = (f"Včera ({WEEKDAYS[f['date'].weekday()]}) jste utržili {kc(f['current']['total']['revenue'])} "
         f"z {f['current']['total']['orders']} objednávek.")
    if f["yoy_pct"] is not None:
        s += f" To je {abs(f['yoy_pct']):.0f} % {trend} stejným dnem loni."
    return s


def build_email(conn, today: date, tenant) -> dict:
    f = yesterday_facts(conn, today)
    st = stock_alerts(conn)
    health = sync_health(conn)
    subject = f"Včera {kc(f['current']['total']['revenue'])} ({pct(f['yoy_pct'])} r/r)"
    if st["sold_out"]:
        subject += f" · {len(st['sold_out'])} velikostí došlo"
    show_unusual = bool(f["anomalies"])
    show_stock = bool(st["broken"] or st["sold_out"] or st["dead_crossing"])
    html = env.get_template("daily.html").render(
        tenant=tenant, f=f, st=st, health=health, subject=subject, summary=summary(f), actions=suggested_actions(f, st),
        show_unusual=show_unusual, show_stock=show_stock)
    return {"subject": subject, "html": html}
