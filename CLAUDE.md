# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Data Engineering platform for **JSTechStore Brasil** — an omnichannel retail chain (15 physical stores + e-commerce) selling tech products. The project uses synthetic data generated into Supabase (PostgreSQL), ingested into a Medallion architecture (Bronze → Silver → Gold) in local Parquet + DuckDB, and delivers 6 executive Power BI dashboards with Incremental Refresh.

Full requirements: `docs/PRD_JSTechStore_Brasil_DataEngineering.md`

## Architecture

```
Supabase (PostgreSQL) → Bronze (Parquet/local) → Silver (Parquet/local) → Gold (DuckDB) → Power BI
```

- **Data Generation:** `scripts/generate_data.py` (3-year full load) + `scripts/generate_daily.py` (daily incremental)
- **Source:** Supabase (PostgreSQL Cloud) — free tier, ~200–300 MB OLTP
- **Connector:** Python + psycopg2 + SQLAlchemy; incremental control via `updated_at` column
- **Orchestration:** GitHub Actions (cron daily at 01:00 BRT via `.github/workflows/daily_pipeline.yml`)
- **Transformations:** dbt Core (`transformation/dbt_project/` — incremental models for Silver and Gold)
- **Storage Bronze/Silver:** Local Parquet files under `data/bronze/` and `data/silver/`, partitioned by ingest date
- **Gold / DW:** DuckDB (`data/gold/jstechstore.duckdb`) — embedded, zero infrastructure, reads Parquet natively
- **Quality:** dbt tests (`schema.yml` — `not_null`, `unique`, `relationships`, `accepted_values`)
- **BI:** Power BI (Import Mode + Incremental Refresh on `fato_venda`)
- **Version control + CI/CD:** GitHub + GitHub Actions

## Source Schema Mapping (Supabase / PostgreSQL)

| Schema | Domain | Key Tables |
|--------|--------|-----------|
| `vendas` | Sales orders | pedidos, itens_pedido, devolucoes |
| `clientes` | Customer + loyalty | clientes, enderecos, techpoints |
| `produtos` | Product catalog | produtos, categorias, fornecedores, precos |
| `estoque` | Inventory | saldo_estoque, movimentacoes |
| `logistica` | Deliveries | entregas, transportadoras, modalidades |
| `financeiro` | Finance | lancamentos, parcelas, contas_receber |
| `marketing` | Campaigns | campanhas, leads, atribuicao |
| `rh` | Staff | vendedores, metas, comissoes |

## Common Commands

### Data Generation

```bash
# Generate 3 years of historical data into Supabase (run once in Phase 1)
python scripts/generate_data.py --start-date 2023-07-21 --end-date 2026-07-20 --seed 42

# Generate today's incremental data into Supabase (run by GitHub Actions daily)
python scripts/generate_daily.py --date today

# Generate for a specific date (backfill)
python scripts/generate_daily.py --date 2026-07-21
```

### Python / Ingestion

```bash
# Install dependencies
pip install -r requirements.txt

# Run full load (first time — processes all data from Supabase to Bronze Parquet)
python -m ingestion.connectors.postgres.extract --mode full

# Run incremental load (reads updated_at > last watermark)
python -m ingestion.connectors.postgres.extract --mode incremental

# Run ingestion unit tests
pytest tests/ingestion/ -v
```

### dbt

```bash
cd transformation/dbt_project

# Install packages
dbt deps

# First run — full rebuild from Bronze Parquet (processes 3 years)
dbt run --full-refresh

# Daily incremental run (processes only new Parquet files)
dbt run

# Run a specific layer only
dbt run --select bronze
dbt run --select silver
dbt run --select gold

# Run a single model
dbt run --select fato_venda

# Run tests
dbt test

# Test a specific model
dbt test --select dim_cliente

# Generate and serve docs locally
dbt docs generate && dbt docs serve
```

### DuckDB

```bash
# Open DuckDB REPL against Gold database
duckdb data/gold/jstechstore.duckdb

# Quick sanity check from shell
python -c "import duckdb; print(duckdb.connect('data/gold/jstechstore.duckdb').execute('SELECT COUNT(*) FROM fato_venda').fetchone())"
```

### LGPD

```bash
# Execute data subject erasure request (dry-run first)
python quality/lgpd/exclusao_titular.py --cpf_hash <hash> --dry-run
python quality/lgpd/exclusao_titular.py --cpf_hash <hash> --execute
```

### Reconciliation

```bash
# Compare Gold totals vs. Supabase source (tolerance <= 0.1%)
python quality/reconciliation/reconcile_gold_vs_source.py --table fato_venda
```

## Data Layer Conventions

### Bronze
- No transformations — exact copy of each Supabase table as Parquet
- Partitioned by `_ingested_at` date: `data/bronze/<schema>/<table>/year=YYYY/month=MM/day=DD/`
- Metadata columns added on ingest: `_source_schema`, `_source_table`, `_ingested_at`, `_row_count_batch`
- **No PII in plain text** — pseudonymization runs before writing Parquet (see `quality/lgpd/pseudonimizacao.py`)
- Incremental watermark stored in `data/bronze/.watermarks/<schema>__<table>.json`

### Silver
- dbt staging models (`stg_<schema>__<table>.sql`) reading Bronze Parquet, then intermediate (`int_<domain>__<entity>.sql`)
- All Silver models use `materialized='incremental'` with `unique_key` set to natural key
- Deduplication by natural key before writing
- SCD Type 2 for `dim_cliente`, `dim_produto`, `dim_vendedor` — use `valid_from` / `valid_to` / `fl_current`
- Monetary values in BRL 2 decimals, dates in UTC, strings stripped/lowercase

### Gold (DuckDB)
- **10 conformed dimensions:** `dim_cliente`, `dim_produto`, `dim_loja`, `dim_tempo`, `dim_canal_venda`, `dim_campanha`, `dim_vendedor`, `dim_transportadora`, `dim_fornecedor`, `dim_modalidade_entrega`
- **5 fact tables:** `fato_venda`, `fato_estoque`, `fato_entrega`, `fato_financeiro`, `fato_cliente_interacao`
- All fact tables use `materialized='incremental'` with date-based predicates
- Surrogate keys: `sk_*`; natural/degenerate keys: `*_nk` and `*_dg`
- Prices stored in fact, **not** in `dim_produto` — historical price is captured at transaction time
- `segmento_rfm` and `nivel_fidelidade` updated monthly via dbt, tracked with SCD2 in `dim_cliente`
- Dataset size target: keep Gold ≤ 900 MB for Power BI headroom

## dbt Model Naming

```
bronze/  →  stg_<schema>__<table>.sql       (e.g. stg_vendas__pedidos)
silver/  →  int_<domain>__<entity>.sql      (e.g. int_vendas__pedidos_unificados)
gold/dimensions/  →  dim_<entity>.sql
gold/facts/       →  fato_<entity>.sql
```

## Key Business Rules (implemented in Silver)

- **Unique customer:** same `cpf_hash` in POS records and e-commerce = same `dim_cliente` record
- **Order status hierarchy:** Cancelled > Returned > Delivered (most severe wins for order-level status)
- **OTD flag:** `fl_sla_atendido = TRUE` when `data_efetiva <= data_promessa`
- **Historical LTV:** sum of `fato_venda.valor_liquido_item` per `cpf_hash` (not predictive)
- **Gross margin at item level:** `valor_liquido_item - (qtd_vendida × custo_unitario)`
- **Discount rate:** `desconto_valor / (desconto_valor + valor_liquido_item)` — never stored as negative revenue
- **RFM scoring:** recency buckets and quintile logic defined in `macros/rfm_score.sql`

## Incremental Strategy Summary

| Layer | Strategy | Key |
|-------|----------|-----|
| Supabase → Bronze | Python: `WHERE updated_at > watermark` | `updated_at` column |
| Bronze → Silver (dbt) | `materialized='incremental'`, `unique_key=natural_key` | Natural key per table |
| Silver → Gold (dbt) | `materialized='incremental'`, filter on `sk_tempo` | Date-based window |
| Gold → Power BI | Power BI Incremental Refresh on `fato_venda` | `RangeStart`/`RangeEnd` |

## GitHub Actions Workflows

### `.github/workflows/daily_pipeline.yml`
Runs at 04:00 UTC (01:00 BRT) daily:
1. `python scripts/generate_daily.py --date today`
2. `python -m ingestion.connectors.postgres.extract --mode incremental`
3. `dbt run` (incremental)
4. `dbt test --select gold`
5. Notify on failure (GitHub notification)

### `.github/workflows/ci_dbt_tests.yml`
Runs on Pull Requests to `main`:
1. `dbt compile`
2. `dbt test`

## Environment Variables

Copy `.env.example` to `.env`. Never commit `.env`.

Key variables:
- `SUPABASE_DB_URL` — PostgreSQL connection string: `postgresql://postgres:<pw>@<project>.supabase.co:5432/postgres`
- `DUCKDB_PATH` — path to the Gold `.duckdb` file (default: `data/gold/jstechstore.duckdb`)
- `BRONZE_PATH` — local path for Bronze Parquet (default: `data/bronze`)
- `SILVER_PATH` — local path for Silver Parquet (default: `data/silver`)
- `LGPD_HMAC_SALT` — secret salt for HMAC-SHA256 pseudonymization (never commit)

## Testing Strategy

- **Unit tests** (`tests/`): Python connector logic with mocked Supabase responses; LGPD pseudonymization correctness; data generator output shape
- **dbt schema tests**: `not_null`, `unique`, `accepted_values`, `relationships` in every `schema.yml` — run in CI on every PR
- **Reconciliation scripts** (`quality/reconciliation/`): compare Gold totals to Supabase source (tolerance ≤ 0.1%)
- **LGPD erasure test**: dry-run mode validates records found and tables targeted without modifying data

## Power BI Constraints and Incremental Refresh

- Import Mode only (no DirectQuery to DuckDB)
- Dataset size limit: **1 GB** — keep Gold ≤ 900 MB
- Max refresh: **8×/day** per dataset
- **Incremental Refresh on `fato_venda`:**
  - Archive data older than 2 years (not reloaded)
  - Refresh window: last 3 days (safety buffer for reprocessing)
  - Required M parameters: `RangeStart` (DateTime) and `RangeEnd` (DateTime)
  - Result: daily refresh processes ~15 MB instead of full 700 MB
- Dimension tables: full refresh each run (small volume, stable)
- Upgrade path if needed: **Power BI Premium Per User (PPU)** — lifts the 1 GB cap

## Project Phases

| Phase | Scope | Target |
|-------|-------|--------|
| 1 | Supabase setup + data generation (3 years) + Bronze ingestion (incremental) + GitHub Actions | Month 1–2 |
| 2 | Silver + Gold DW + dbt incremental (10 dims, 5 facts) + LGPD scripts | Month 3–4 |
| 3 | 6 Power BI dashboards with Incremental Refresh (validated by business owners) | Month 5–6 |
| 4 | Predictive models + self-service BI + Gold size optimization | Month 7–9 |
