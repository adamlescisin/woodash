CREATE TABLE IF NOT EXISTS sync_state (
    job    TEXT PRIMARY KEY,
    cursor TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_fol_order ON fact_order_line(order_id);
