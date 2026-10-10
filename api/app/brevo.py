import os

import httpx


def send_email(tenant, subject: str, html: str, transport: httpx.BaseTransport | None = None) -> bool:
    """Send through Brevo. Returns False (dry run) when no API key, sender or recipients are configured."""
    key = os.environ.get("BREVO_API_KEY")
    sender = tenant.email.get("sender") or {}
    to = [{"email": a} for a in tenant.email.get("recipients", [])]
    if not (key and sender.get("email") and to):
        return False
    r = httpx.Client(transport=transport, timeout=30).post(
        "https://api.brevo.com/v3/smtp/email", headers={"api-key": key},
        json={"sender": sender, "to": to, "subject": subject, "htmlContent": html})
    if r.is_error:
        raise RuntimeError(f"Brevo {r.status_code}: {r.text[:300]}")
    return True
