# woodash

Self-hosted e-commerce dashboard and Czech daily email for WooCommerce shops (ELKA Fashion first, slovem.eu second tenant). Built from the *E-commerce Dashboard — Specification*.

## Layout
- `db/migrations/` — star schema and one SQL view per metric
- `tenants/*.yml` — per-tenant config and feature flags
- `api/` — FastAPI (facts, email rendering); `api/app/facts.py` computes every number
- `web/` — Next.js dashboard (Přehled so far)
- `scripts/` — `seed_synthetic.py` (Phase 0 demo data), `preview_email.py`

## Phase 0 quick start
    cp .env.example .env            # set POSTGRES_PASSWORD
    docker compose up -d postgres
    createdb elka                   # or via psql in the container
    export ELKA_DATABASE_URL=postgresql://woodash:...@localhost:5432/elka
    pip install -e "api[dev]"
    python scripts/seed_synthetic.py
    python scripts/preview_email.py --out email_preview.html
    pytest api

## Status
Phase 0 (prototype): schema, metric views, synthetic data, Přehled, email preview. Next: Phase 1 (Woo + POS ingestion, Prodej, Sklad, live email via Brevo).
