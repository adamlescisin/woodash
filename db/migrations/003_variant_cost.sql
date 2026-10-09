-- Unit cost per variant with its source (spec: "Purchase costs and margin coverage").
CREATE TABLE IF NOT EXISTS dim_variant_cost (
    variant_id BIGINT PRIMARY KEY REFERENCES dim_variant(variant_id),
    unit_cost  NUMERIC(12,2) NOT NULL,
    source     TEXT NOT NULL CHECK (source IN ('known','estimated'))
);
