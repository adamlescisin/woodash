-- One view per metric (spec: "Metric definitions"); dashboard and email both read these.

-- Net revenue, orders, units, gross margin per day and channel.
CREATE OR REPLACE VIEW v_daily_sales AS
SELECT
    date,
    channel,
    SUM(net_revenue)                       AS net_revenue,
    COUNT(DISTINCT order_id)               AS orders,
    SUM(qty)                               AS units,
    SUM(net_revenue) FILTER (WHERE cost_source IS NOT NULL)                       AS revenue_with_cost,
    SUM(net_revenue - qty * unit_cost) FILTER (WHERE cost_source IS NOT NULL)      AS gross_margin,
    SUM(net_revenue) FILTER (WHERE cost_source = 'known')                          AS revenue_known_cost
FROM fact_order_line
GROUP BY date, channel;

-- Share of revenue resting on known costs.
CREATE OR REPLACE VIEW v_margin_coverage AS
SELECT
    date,
    COALESCE(SUM(revenue_known_cost) / NULLIF(SUM(net_revenue), 0), 0) AS margin_coverage
FROM v_daily_sales
GROUP BY date;

-- Weeks of cover: stock / average weekly units over the last 4 weeks (as of latest stock date).
CREATE OR REPLACE VIEW v_weeks_of_cover AS
WITH latest AS (SELECT MAX(date) AS d FROM fact_stock_daily),
sold AS (
    SELECT variant_id, SUM(qty)::numeric / 4 AS weekly_units
    FROM fact_order_line CROSS JOIN latest
    WHERE date > latest.d - 28 AND date <= latest.d
    GROUP BY variant_id
)
SELECT s.variant_id, s.stock_qty,
       COALESCE(sold.weekly_units, 0) AS weekly_units,
       CASE WHEN COALESCE(sold.weekly_units, 0) = 0 THEN NULL
            ELSE s.stock_qty / sold.weekly_units END AS weeks_of_cover
FROM fact_stock_daily s
CROSS JOIN latest
LEFT JOIN sold ON sold.variant_id = s.variant_id
WHERE s.date = latest.d;

-- Dead stock: variants with stock and no sale in 90+ days.
CREATE OR REPLACE VIEW v_dead_stock AS
WITH latest AS (SELECT MAX(date) AS d FROM fact_stock_daily),
last_sale AS (SELECT variant_id, MAX(date) AS last_sale FROM fact_order_line GROUP BY variant_id)
SELECT s.variant_id, s.stock_qty, l.last_sale,
       (latest.d - COALESCE(l.last_sale, DATE '1970-01-01')) AS days_since_sale
FROM fact_stock_daily s
JOIN latest ON s.date = latest.d
LEFT JOIN last_sale l USING (variant_id)
WHERE s.stock_qty > 0
  AND (l.last_sale IS NULL OR latest.d - l.last_sale >= 90);

-- Broken size curve: style with stock where >= 2 of its 3 best-selling sizes are at zero.
CREATE OR REPLACE VIEW v_broken_size_curve AS
WITH latest AS (SELECT MAX(date) AS d FROM fact_stock_daily),
size_sales AS (
    SELECT v.product_id, v.variant_id, COALESCE(SUM(f.qty), 0) AS units
    FROM dim_variant v LEFT JOIN fact_order_line f USING (variant_id)
    GROUP BY v.product_id, v.variant_id
),
ranked AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY product_id ORDER BY units DESC, variant_id) AS rk
    FROM size_sales WHERE units > 0
),
top3 AS (
    SELECT r.product_id, r.variant_id, COALESCE(s.stock_qty, 0) AS stock_qty
    FROM ranked r
    CROSS JOIN latest
    LEFT JOIN fact_stock_daily s ON s.variant_id = r.variant_id AND s.date = latest.d
    WHERE r.rk <= 3
),
style_stock AS (
    SELECT v.product_id, SUM(s.stock_qty) AS total_stock
    FROM fact_stock_daily s JOIN dim_variant v USING (variant_id)
    CROSS JOIN latest
    WHERE s.date = latest.d GROUP BY v.product_id
)
SELECT t.product_id,
       COUNT(*) FILTER (WHERE t.stock_qty = 0) AS top_sizes_at_zero,
       ss.total_stock
FROM top3 t JOIN style_stock ss USING (product_id)
GROUP BY t.product_id, ss.total_stock
HAVING COUNT(*) FILTER (WHERE t.stock_qty = 0) >= 2 AND ss.total_stock > 0;

-- Store customer capture rate per day.
CREATE OR REPLACE VIEW v_capture_rate AS
SELECT date,
       COUNT(DISTINCT order_id) FILTER (WHERE customer_id IS NOT NULL)::numeric
         / NULLIF(COUNT(DISTINCT order_id), 0) AS capture_rate
FROM fact_order_line WHERE channel = 'store'
GROUP BY date;
