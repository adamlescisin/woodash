-- Star schema for one tenant database (spec: "Data model").
-- Each tenant has its own database; there is no tenant column.

CREATE TABLE IF NOT EXISTS job_run (
    id          BIGSERIAL PRIMARY KEY,
    job         TEXT NOT NULL,
    started_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    rows_read   INTEGER NOT NULL DEFAULT 0,
    errors      INTEGER NOT NULL DEFAULT 0,
    message     TEXT
);

-- Raw API responses, stored unchanged so any metric can be rebuilt.
CREATE TABLE IF NOT EXISTS raw_wc_orders   (id BIGINT PRIMARY KEY, fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(), payload JSONB NOT NULL);
CREATE TABLE IF NOT EXISTS raw_wc_products (id BIGINT PRIMARY KEY, fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(), payload JSONB NOT NULL);
CREATE TABLE IF NOT EXISTS raw_wc_customers(id BIGINT PRIMARY KEY, fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(), payload JSONB NOT NULL);

CREATE TABLE IF NOT EXISTS dim_date (
    date            DATE PRIMARY KEY,
    weekday         SMALLINT NOT NULL,        -- 1 = Monday .. 7 = Sunday
    week            SMALLINT NOT NULL,
    month           SMALLINT NOT NULL,
    year            SMALLINT NOT NULL,
    season          TEXT NOT NULL,            -- e.g. 2026SS, 2026FW
    is_holiday      BOOLEAN NOT NULL DEFAULT FALSE,
    holiday_name    TEXT,
    same_day_last_year DATE NOT NULL          -- same weekday, 364 days back; holidays map to the same holiday
);

CREATE TABLE IF NOT EXISTS dim_variant (
    variant_id     BIGINT PRIMARY KEY,
    sku            TEXT NOT NULL,
    product_id     BIGINT NOT NULL,
    product_name   TEXT NOT NULL,
    brand          TEXT NOT NULL,
    category       TEXT NOT NULL,
    season         TEXT NOT NULL,
    size           TEXT NOT NULL,
    size_order     SMALLINT NOT NULL,
    colour         TEXT,
    current_price  NUMERIC(12,2) NOT NULL
);

CREATE TABLE IF NOT EXISTS dim_customer (
    customer_id      BIGINT PRIMARY KEY,
    first_order_date DATE,
    first_order_channel TEXT CHECK (first_order_channel IN ('store','web')),
    segment          TEXT,
    consent_marketing BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS fact_order_line (
    order_id     BIGINT NOT NULL,
    line_no      SMALLINT NOT NULL,
    date         DATE NOT NULL REFERENCES dim_date(date),
    hour         SMALLINT NOT NULL CHECK (hour BETWEEN 0 AND 23),
    channel      TEXT NOT NULL CHECK (channel IN ('store','web')),
    variant_id   BIGINT NOT NULL REFERENCES dim_variant(variant_id),
    qty          INTEGER NOT NULL,
    net_revenue  NUMERIC(12,2) NOT NULL,      -- excl. VAT, after discounts and refunds
    discount     NUMERIC(12,2) NOT NULL DEFAULT 0,
    unit_cost    NUMERIC(12,2),
    cost_source  TEXT CHECK (cost_source IN ('known','estimated')),
    customer_id  BIGINT REFERENCES dim_customer(customer_id),
    source       TEXT,                        -- Order Attribution
    medium       TEXT,
    campaign     TEXT,
    PRIMARY KEY (order_id, line_no)
);
CREATE INDEX IF NOT EXISTS ix_fol_date ON fact_order_line(date);
CREATE INDEX IF NOT EXISTS ix_fol_variant ON fact_order_line(variant_id);
CREATE INDEX IF NOT EXISTS ix_fol_customer ON fact_order_line(customer_id);

CREATE TABLE IF NOT EXISTS fact_stock_daily (
    variant_id  BIGINT NOT NULL REFERENCES dim_variant(variant_id),
    date        DATE NOT NULL REFERENCES dim_date(date),
    stock_qty   INTEGER NOT NULL,
    stock_value_cost  NUMERIC(14,2),
    stock_value_price NUMERIC(14,2),
    PRIMARY KEY (variant_id, date)
);

CREATE TABLE IF NOT EXISTS fact_traffic_daily (
    date        DATE NOT NULL REFERENCES dim_date(date),
    channel     TEXT NOT NULL,
    sessions    INTEGER NOT NULL,
    users       INTEGER NOT NULL,
    add_to_carts INTEGER NOT NULL DEFAULT 0,
    checkouts   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (date, channel)
);

CREATE TABLE IF NOT EXISTS fact_ad_spend_daily (
    date     DATE NOT NULL REFERENCES dim_date(date),
    platform TEXT NOT NULL,
    campaign TEXT NOT NULL,
    spend    NUMERIC(12,2) NOT NULL,
    clicks   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (date, platform, campaign)
);
