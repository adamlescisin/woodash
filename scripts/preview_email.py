"""Render the Czech daily email to an HTML file (no sending in Phase 0)."""
import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

from app.config import load_tenant  # noqa: E402
from app.db import connect  # noqa: E402
from app.email_render import build_email  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--tenant", default="elka")
ap.add_argument("--as-of", default=str(date.today()))
ap.add_argument("--out", default="email_preview.html")
a = ap.parse_args()
t = load_tenant(a.tenant)
with connect(t) as conn:
    mail = build_email(conn, date.fromisoformat(a.as_of), t)
Path(a.out).write_text(mail["html"], encoding="utf-8")
print(mail["subject"])
