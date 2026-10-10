"""Read queries behind the Prodej (sales) and Sklad (stock) screens.

Revenue figures also return the same period shifted 364 days back (same weekdays), as the spec asks.
Channel filter: 'all' | 'store' | 'web'. Brand filter: exact brand name or None.
"""
from datetime import date, timedelta

LY_SHIFT = 364


def _flt(channel: str, brand: str | None) -> tuple[str, list]:
    sql, args = "", []
    if channel in ("store", "web"):
        sql += " AND f.channel = %s"
        args.append(channel)
    if brand:
        sql += " AND v.brand = %s"
        args.append(brand)
    return sql, args


def _ly(start: date, end: date) -> tuple[date, date]:
    return start - timedelta(days=LY_SHIFT), end - timedelta(days=LY_SHIFT)


def ranking(conn, start: date, end: date, channel: str, brand: str | None, by: str) -> list[dict]:
    col = {"brand": "v.brand", "category": "v.category"}[by]
    ly_s, ly_e = _ly(start, end)
    flt, args = _flt(channel, brand)
    return conn.execute(
        f"""SELECT {col} AS name,
               COALESCE(SUM(f.net_revenue) FILTER (WHERE f.date BETWEEN %s AND %s), 0) AS revenue,
               COALESCE(SUM(f.net_revenue) FILTER (WHERE f.date BETWEEN %s AND %s), 0) AS revenue_ly,
               COALESCE(SUM(f.qty) FILTER (WHERE f.date BETWEEN %s AND %s), 0) AS units
            FROM fact_order_line f JOIN dim_variant v USING (variant_id)
            WHERE f.date BETWEEN %s AND %s {flt}
            GROUP BY 1
            HAVING COALESCE(SUM(f.net_revenue) FILTER (WHERE f.date BETWEEN %s AND %s), 0) > 0
            ORDER BY revenue DESC LIMIT 15""",
        [start, end, ly_s, ly_e, start, end, ly_s, end, *args, start, end]).fetchall()


def top_products(conn, start: date, end: date, channel: str, brand: str | None) -> list[dict]:
    flt, args = _flt(channel, brand)
    return conn.execute(
        f"""SELECT v.product_id, MIN(v.product_name) AS name, MIN(v.brand) AS brand,
               SUM(f.net_revenue) AS revenue, SUM(f.qty) AS units
            FROM fact_order_line f JOIN dim_variant v USING (variant_id)
            WHERE f.date BETWEEN %s AND %s {flt}
            GROUP BY v.product_id ORDER BY revenue DESC LIMIT 10""", [start, end, *args]).fetchall()


def heatmap(conn, start: date, end: date, brand: str | None) -> list[dict]:
    """Store revenue by ISO weekday (1 = Monday) and hour."""
    flt, args = _flt("store", brand)
    return conn.execute(
        f"""SELECT EXTRACT(ISODOW FROM f.date)::int AS weekday, f.hour,
               SUM(f.net_revenue) AS revenue, COUNT(DISTINCT f.order_id) AS orders
            FROM fact_order_line f JOIN dim_variant v USING (variant_id)
            WHERE f.date BETWEEN %s AND %s {flt} GROUP BY 1, 2 ORDER BY 1, 2""", [start, end, *args]).fetchall()


def basket(conn, start: date, end: date, channel: str, brand: str | None) -> dict:
    ly_s, ly_e = _ly(start, end)
    flt, args = _flt(channel, brand)
    return conn.execute(
        f"""WITH o AS (
              SELECT f.order_id, f.date, SUM(f.net_revenue) AS rev, SUM(f.qty) AS units
              FROM fact_order_line f JOIN dim_variant v USING (variant_id)
              WHERE f.date BETWEEN %s AND %s {flt} GROUP BY f.order_id, f.date)
            SELECT
              COALESCE(AVG(rev) FILTER (WHERE date BETWEEN %s AND %s), 0) AS basket,
              COALESCE(AVG(rev) FILTER (WHERE date BETWEEN %s AND %s), 0) AS basket_ly,
              COALESCE(AVG(units) FILTER (WHERE date BETWEEN %s AND %s), 0) AS units_per_order,
              COUNT(*) FILTER (WHERE date BETWEEN %s AND %s) AS orders,
              COUNT(*) FILTER (WHERE date BETWEEN %s AND %s) AS orders_ly
            FROM o""",
        [ly_s, end, *args, start, end, ly_s, ly_e, start, end, start, end, ly_s, ly_e]).fetchone()


# ---------------------------------------------------------------- stock

def _brand_sql(brand: str | None) -> tuple[str, list]:
    return (" AND v.brand = %s", [brand]) if brand else ("", [])


STYLE_BASE = """
WITH latest AS (SELECT MAX(date) AS d FROM fact_stock_daily),
stock AS (
    SELECT v.product_id, SUM(s.stock_qty) AS stock
    FROM fact_stock_daily s JOIN dim_variant v USING (variant_id) CROSS JOIN latest
    WHERE s.date = latest.d {brand} GROUP BY v.product_id),
sold AS (
    SELECT v.product_id,
           SUM(f.qty) FILTER (WHERE f.date > latest.d - 365) AS units_12m,
           SUM(f.qty) FILTER (WHERE f.date > latest.d - 28) AS units_4w
    FROM fact_order_line f JOIN dim_variant v USING (variant_id) CROSS JOIN latest
    WHERE f.date > latest.d - 365 {brand} GROUP BY v.product_id),
style AS (
    SELECT st.product_id, COALESCE(st.stock, 0) AS stock, COALESCE(so.units_12m, 0) AS units_12m,
           COALESCE(so.units_4w, 0) AS units_4w
    FROM stock st FULL JOIN sold so USING (product_id)),
named AS (
    SELECT product_id, MIN(product_name) AS name, MIN(brand) AS brand, MAX(current_price) AS price
    FROM dim_variant GROUP BY product_id)
SELECT n.product_id, n.name, n.brand, s.stock, s.units_12m, s.units_4w,
       s.units_12m::numeric / NULLIF(s.units_12m + s.stock, 0) AS sell_through,
       CASE WHEN s.units_4w = 0 THEN NULL ELSE s.stock / (s.units_4w / 4.0) END AS weeks_of_cover,
       s.stock * n.price AS stock_value
FROM style s JOIN named n USING (product_id)
"""


def style_lists(conn, brand: str | None) -> dict:
    b, args = _brand_sql(brand)
    base = STYLE_BASE.replace("{brand}", b)
    a = args * 2
    reorder = conn.execute(
        base + " WHERE s.units_4w > 0 AND s.stock > 0 AND s.units_12m >= 2 AND s.stock / (s.units_4w / 4.0) < 8 "
               "ORDER BY s.units_12m DESC, weeks_of_cover ASC LIMIT 15", a).fetchall()
    markdown = conn.execute(
        base + " WHERE s.stock >= 3 AND COALESCE(s.units_12m::numeric / NULLIF(s.units_12m + s.stock, 0), 0) < 0.3 "
               "ORDER BY stock_value DESC LIMIT 15", a).fetchall()
    return {"reorder": reorder, "markdown": markdown}


def broken_curves(conn, brand: str | None) -> list[dict]:
    b, args = _brand_sql(brand)
    return conn.execute(
        f"""SELECT x.product_id, MIN(v.product_name) AS name, MIN(v.brand) AS brand,
               MAX(x.top_sizes_at_zero) AS sizes_at_zero, MAX(x.total_stock) AS stock
            FROM v_broken_size_curve x JOIN dim_variant v USING (product_id)
            WHERE TRUE {b} GROUP BY x.product_id ORDER BY stock DESC LIMIT 20""", args).fetchall()


def dead_stock(conn, brand: str | None) -> dict:
    b, args = _brand_sql(brand)
    buckets = conn.execute(
        f"""SELECT CASE WHEN d.days_since_sale IS NULL OR d.last_sale IS NULL THEN 'nikdy neprodáno'
                        WHEN d.days_since_sale < 180 THEN '90–180 dní'
                        WHEN d.days_since_sale < 365 THEN '180–365 dní' ELSE '365+ dní' END AS bucket,
               COUNT(*) AS variants, SUM(d.stock_qty) AS units, SUM(d.stock_qty * v.current_price) AS value
            FROM v_dead_stock d JOIN dim_variant v USING (variant_id) WHERE TRUE {b} GROUP BY 1
            ORDER BY MIN(COALESCE(d.days_since_sale, 99999))""", args).fetchall()
    top = conn.execute(
        f"""SELECT v.product_id, MIN(v.product_name) AS name, MIN(v.brand) AS brand,
               SUM(d.stock_qty) AS units, SUM(d.stock_qty * v.current_price) AS value,
               MIN(d.days_since_sale) AS days_since_sale
            FROM v_dead_stock d JOIN dim_variant v USING (variant_id) WHERE TRUE {b}
            GROUP BY v.product_id ORDER BY value DESC LIMIT 10""", args).fetchall()
    return {"buckets": buckets, "top": top}


def size_grid(conn, product_id: int) -> list[dict]:
    return conn.execute(
        """WITH latest AS (SELECT MAX(date) AS d FROM fact_stock_daily)
           SELECT v.variant_id, v.sku, v.size, v.size_order, v.colour, COALESCE(s.stock_qty, 0) AS stock,
                  COALESCE(SUM(f.qty) FILTER (WHERE f.date > latest.d - 90), 0) AS units_90d,
                  COALESCE(SUM(f.qty), 0) AS units_total
           FROM dim_variant v CROSS JOIN latest
           LEFT JOIN fact_stock_daily s ON s.variant_id = v.variant_id AND s.date = latest.d
           LEFT JOIN fact_order_line f ON f.variant_id = v.variant_id
           WHERE v.product_id = %s GROUP BY v.variant_id, v.sku, v.size, v.size_order, v.colour, s.stock_qty
           ORDER BY v.size_order, v.colour""", (product_id,)).fetchall()


# ------------------------------------------------------------- channels

def order_sources(conn, start: date, end: date) -> dict:
    """E-shop revenue / orders / new customers by Order Attribution source and medium, plus attribution coverage."""
    ly_s, ly_e = _ly(start, end)
    rows = conn.execute(
        """SELECT COALESCE(f.source, '(neuvedeno)') AS source, COALESCE(f.medium, '') AS medium,
               COALESCE(SUM(f.net_revenue) FILTER (WHERE f.date BETWEEN %s AND %s), 0) AS revenue,
               COALESCE(SUM(f.net_revenue) FILTER (WHERE f.date BETWEEN %s AND %s), 0) AS revenue_ly,
               COUNT(DISTINCT f.order_id) FILTER (WHERE f.date BETWEEN %s AND %s) AS orders,
               COUNT(DISTINCT f.customer_id) FILTER (WHERE f.date BETWEEN %s AND %s
                     AND c.first_order_date BETWEEN %s AND %s) AS new_customers
           FROM fact_order_line f LEFT JOIN dim_customer c USING (customer_id)
           WHERE f.channel = 'web' AND f.date BETWEEN %s AND %s
           GROUP BY 1, 2
           HAVING COALESCE(SUM(f.net_revenue) FILTER (WHERE f.date BETWEEN %s AND %s), 0) > 0
           ORDER BY revenue DESC LIMIT 20""",
        [start, end, ly_s, ly_e, start, end, start, end, start, end, ly_s, end, start, end]).fetchall()
    total = sum(r["revenue"] for r in rows)
    known = sum(r["revenue"] for r in rows if r["source"] != "(neuvedeno)")
    return {"rows": rows, "attribution_coverage": (known / total) if total else None}


def traffic(conn, start: date, end: date) -> dict:
    """GA4 sessions and funnel by default channel group, with the e-shop order conversion rate overall."""
    ly_s, ly_e = _ly(start, end)
    rows = conn.execute(
        """SELECT channel,
               COALESCE(SUM(sessions) FILTER (WHERE date BETWEEN %s AND %s), 0) AS sessions,
               COALESCE(SUM(sessions) FILTER (WHERE date BETWEEN %s AND %s), 0) AS sessions_ly,
               COALESCE(SUM(users) FILTER (WHERE date BETWEEN %s AND %s), 0) AS users,
               COALESCE(SUM(add_to_carts) FILTER (WHERE date BETWEEN %s AND %s), 0) AS add_to_carts,
               COALESCE(SUM(checkouts) FILTER (WHERE date BETWEEN %s AND %s), 0) AS checkouts
           FROM fact_traffic_daily WHERE date BETWEEN %s AND %s
           GROUP BY channel HAVING SUM(sessions) FILTER (WHERE date BETWEEN %s AND %s) > 0
           ORDER BY sessions DESC""",
        [start, end, ly_s, ly_e, start, end, start, end, start, end, ly_s, end, start, end]).fetchall()
    orders = conn.execute(
        "SELECT COUNT(DISTINCT order_id) AS n FROM fact_order_line WHERE channel = 'web' AND date BETWEEN %s AND %s",
        (start, end)).fetchone()["n"]
    sessions = sum(r["sessions"] for r in rows)
    last = conn.execute("SELECT MAX(date) AS d, MIN(date) AS first FROM fact_traffic_daily").fetchone()
    return {"rows": rows, "web_orders": orders, "sessions": sessions,
            "conversion_rate": (orders / sessions) if sessions else None,
            "data_from": last["first"], "data_to": last["d"]}
