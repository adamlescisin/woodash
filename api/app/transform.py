"""Pure transforms from WooCommerce REST payloads to warehouse rows."""
import hashlib
from datetime import datetime
from zoneinfo import ZoneInfo

COUNTED_STATUSES = {"completed", "processing"}
DEFAULT_COST_KEYS = ("_cogs_total_value", "_wc_cog_cost", "_cost", "cost_of_goods", "_purchase_price")


def h(s: str) -> int:
    return int(hashlib.sha256(s.encode()).hexdigest()[:12], 16)


def customer_key(order: dict) -> int | None:
    """One-way hash of the billing e-mail (same key as the file importer); never stores personal data."""
    email = ((order.get("billing") or {}).get("email") or "").strip().lower()
    if email:
        return h("cust:" + email)
    cid = order.get("customer_id") or 0
    return cid if cid > 0 else None


POS_META_KEYS = ("wc_pos_order_type", "wc_pos_register_id", "wc_pos_id_register")


def channel_of(order: dict) -> str:
    """Store = created by a POS. Covers WooCommerce Point of Sale (Actuality Extensions), which marks orders
    with `created_via` (pos / point-of-sale) and `wc_pos_*` meta; the exact value is verified on the first real sync."""
    via = (order.get("created_via") or "").lower()
    if "pos" in via or "point-of-sale" in via or "point_of_sale" in via:
        return "store"
    meta = {m.get("key"): m.get("value") for m in order.get("meta_data", [])}
    if any(meta.get(k) not in (None, "", 0, "0") for k in POS_META_KEYS):
        return "store"
    return "web"


def attribution(order: dict) -> tuple[str | None, str | None, str | None]:
    meta = {m.get("key"): m.get("value") for m in order.get("meta_data", [])}
    g = lambda k: meta.get(f"_wc_order_attribution_{k}") or None  # noqa: E731
    return g("utm_source"), g("utm_medium"), g("utm_campaign")


def local_dt(order: dict, tz: str) -> datetime:
    gmt = order.get("date_created_gmt") or order["date_created"]
    return datetime.fromisoformat(gmt).replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo(tz))


def order_lines(order: dict, tz: str, refunds: list[dict] | None = None) -> list[dict]:
    """Lines for one order; [] when the status does not count (cancelled, failed, pending, ...)."""
    if order.get("status") not in COUNTED_STATUSES:
        return []
    refunded: dict[int, tuple[int, float]] = {}  # order line id -> (qty, amount) refunded
    for rf in refunds or []:
        for li in rf.get("line_items", []):
            ref_id = next((int(m["value"]) for m in li.get("meta_data", []) if m.get("key") == "_refunded_item_id"), None)
            if ref_id is not None:
                q, a = refunded.get(ref_id, (0, 0.0))
                refunded[ref_id] = (q + abs(int(li.get("quantity", 0))), a + abs(float(li.get("total", 0))))
    dt = local_dt(order, tz)
    src, med, camp = attribution(order)
    out = []
    for n, li in enumerate(order.get("line_items", []), 1):
        rq, ra = refunded.get(li["id"], (0, 0.0))
        qty = li["quantity"] - rq
        if qty <= 0:
            continue
        subtotal, total = float(li.get("subtotal", 0)), float(li.get("total", 0))
        out.append({
            "order_id": order["id"], "line_no": n, "date": dt.date(), "hour": dt.hour,
            "channel": channel_of(order), "variant_id": li.get("variation_id") or li["product_id"],
            "qty": qty, "net_revenue": round(total - ra, 2), "discount": round(subtotal - total, 2),
            "customer_id": customer_key(order), "source": src, "medium": med, "campaign": camp,
            "sku": li.get("sku") or None, "name": li.get("name"),
        })
    return out


def cost_of(item: dict, keys=DEFAULT_COST_KEYS) -> float | None:
    """Unit cost from WooCommerce COGS (REST `cost_of_goods_sold.total_value`) or the first configured meta key."""
    try:
        v = float((item.get("cost_of_goods_sold") or {}).get("total_value") or 0)
        if v > 0:
            return v
    except (TypeError, ValueError):
        pass
    meta = {m.get("key"): m.get("value") for m in item.get("meta_data", [])}
    for k in keys:
        try:
            v = float(str(meta.get(k, "")).replace(",", "."))
        except ValueError:
            continue
        if v > 0:
            return v
    return None


def attr(item: dict, name: str) -> str | None:
    for a in item.get("attributes", []):
        if (a.get("name") or "").lower() == name:
            return a.get("option") or (a.get("options") or [None])[0]
    return None
