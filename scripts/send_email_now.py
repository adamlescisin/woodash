"""Build today's daily email and send it right now through Brevo, printing the real error if it fails.
Use it to test Brevo settings without waiting for the scheduled time:
    docker compose exec worker python /app/scripts/send_email_now.py elka
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

from app.brevo import send_email  # noqa: E402
from app.config import load_tenant  # noqa: E402
from app.db import connect  # noqa: E402
from app.email_render import build_email  # noqa: E402

t = load_tenant(sys.argv[1] if len(sys.argv) > 1 else "elka")
with connect(t) as conn:
    mail = build_email(conn, date.today(), t)
print("subject:", mail["subject"])
print("sent" if send_email(t, mail["subject"], mail["html"]) else "NOT sent: missing BREVO_API_KEY, sender or recipients")
