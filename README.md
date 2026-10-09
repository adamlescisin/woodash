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

## Loading real exports (Phase 0)
    python scripts/import_wc_products.py products.csv --as-of YYYY-MM-DD   # catalogue, stock snapshot, known costs
    python scripts/import_wc_export.py orders.json                          # orders (products first)
Exports contain personal data: keep them outside the repo (`data/` is git-ignored).

## Run on the Mac Mini (Docker)
    git clone -b claude/nifty-ride-z3zpd6 https://github.com/adamlescisin/woodash.git && cd woodash
    cp .env.example .env     # edit: POSTGRES_PASSWORD (same password inside ELKA_DATABASE_URL), WC keys, BREVO_API_KEY
    docker compose up -d --build
    docker compose logs -f worker
Dashboard: http://localhost:3000 (API on :8000), both bound to localhost only. The `elka` database and schema are created automatically.

## Live ingestion (Phase 1)
`python -m app.worker elka` (the `worker` service) syncs orders every 15 min (cursor `modified_after`, raw JSON kept in `raw_wc_*`),
the catalogue + stock snapshot nightly at 02:00, and sends the daily email at the tenant's `send_time`
(dry run until `BREVO_API_KEY` and `email.sender` are set). Requires the `*_WC_URL/KEY/SECRET` env vars (read-only keys).
Integration test: `TEST_DATABASE_URL=postgresql://... pytest api`.

## Status
Phase 0 (prototype): schema, metric views, synthetic data, Přehled, email preview. Next: Phase 1 (Woo + POS ingestion, Prodej, Sklad, live email via Brevo).
