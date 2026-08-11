# Arquitetura v2 — BigQuery + GCS

**Versão:** 2.0 (target)  
**Data:** 2026-08-11  
**Status:** 🟡 Planejada — ver `docs/migração/plano_migracao_bigquery_gcs.md`  
**Arquitetura atual (v1):** DuckDB + Parquet local — descrita no `CLAUDE.md`

---

## 1. Visão Geral

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  FONTE                                                                      │
│  Supabase (PostgreSQL · southamerica-east1)                                 │
│  28 tabelas · 8 schemas · ~5,9 M linhas                                    │
└────────────────────────┬────────────────────────────────────────────────────┘
                         │ psycopg2 (Python)
                         │ incremental: WHERE updated_at > watermark
                         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  BRONZE — Google Cloud Storage                                              │
│  gs://jstechstore-bronze/                                                   │
│  <schema>/<table>/year=YYYY/month=MM/day=DD/batch_HHMMSS.parquet           │
│  watermarks: gs://jstechstore-bronze/.watermarks/<schema>__<table>.json    │
│  Formato: Parquet · Snappy · ~165 MB total                                 │
└────────────────────────┬────────────────────────────────────────────────────┘
                         │ BigQuery External Tables
                         │ (dbt-external-tables · read_parquet on GCS)
                         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  SILVER — BigQuery dataset: jstechstore_bronze_ext + jstechstore_silver    │
│  External Tables: jstechstore_bronze_ext.vendas__pedidos (×28)             │
│  Staging: stg_<schema>__<table>  (28 modelos · incremental)                │
│  Intermediate: int_<domain>__<entity>  (3 modelos · incremental)           │
└────────────────────────┬────────────────────────────────────────────────────┘
                         │ dbt-bigquery (incremental, unique_key)
                         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  GOLD — BigQuery dataset: jstechstore_gold                                  │
│  10 dimensões: dim_cliente, dim_produto, dim_loja, dim_tempo,              │
│                dim_canal_venda, dim_campanha, dim_vendedor,                 │
│                dim_transportadora, dim_fornecedor, dim_modalidade_entrega  │
│  6 fatos: fato_venda, fato_estoque, fato_entrega,                          │
│           fato_financeiro, fato_cliente_interacao, fato_orcamento          │
└────────────────────────┬────────────────────────────────────────────────────┘
                         │ BigQuery connector (nativo, sem ODBC)
                         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  POWER BI                                                                   │
│  Import Mode + Incremental Refresh em fato_venda                           │
│  6 dashboards executivos · Refresh: 1×/dia                                 │
│  Sem On-premises Data Gateway · Sem DuckDB ODBC Driver                     │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Stack tecnológica

### Antes (v1) vs Depois (v2)

| Componente | v1 (atual) | v2 (target) |
|-----------|-----------|------------|
| Bronze storage | `data/bronze/` — Parquet local | GCS `gs://jstechstore-bronze/` |
| Gold engine | DuckDB `jstechstore.duckdb` | BigQuery dataset `jstechstore_gold` |
| dbt adapter | `dbt-duckdb` | `dbt-bigquery` |
| Watermarks | `data/bronze/.watermarks/*.json` local | `gs://jstechstore-bronze/.watermarks/*.json` |
| Python storage | `pathlib.Path` + `pyarrow.write_parquet` | `google-cloud-storage` + upload em memória |
| Power BI conexão | ODBC → DuckDB local + Gateway | Conector BigQuery nativo |
| GHA state | Cache Bronze (`actions/cache`) | Stateless — lê GCS/BQ direto |
| Backup Gold | `scripts/backup_gold.py` → `.duckdb.gz` | GCS versionado + BQ point-in-time recovery |

### Stack completa v2

```
Linguagem:        Python 3.12
Fonte:            Supabase (PostgreSQL) via psycopg2
Ingestão:         Python custom (extract.py) → GCS
Orquestração:     GitHub Actions (cron 04:00 UTC diário)
Transformação:    dbt Core 1.8+ com adaptador dbt-bigquery
Bronze storage:   Google Cloud Storage (southamerica-east1)
Silver/Gold:      BigQuery (southamerica-east1)
External Tables:  dbt-external-tables 0.9+
BI:               Power BI (Import Mode + Incremental Refresh)
Qualidade:        dbt tests + reconciliação Python (google-cloud-bigquery)
Autenticação:     GCP Service Account via GitHub Secret
```

---

## 3. Camadas de dados

### Bronze — Google Cloud Storage

**Responsabilidade:** cópia fiel das tabelas Supabase em Parquet, particionada por data de ingestão.

```
gs://jstechstore-bronze/
├── .watermarks/
│   ├── vendas__pedidos.json
│   ├── vendas__itens_pedido.json
│   └── ... (28 arquivos, um por tabela)
├── vendas/
│   ├── pedidos/year=2026/month=08/day=11/batch_040012.parquet
│   ├── itens_pedido/...
│   └── devolucoes/...
├── clientes/
├── produtos/
├── estoque/
├── logistica/
├── financeiro/
├── marketing/
└── rh/
```

**Regras:**
- Parquet com compressão Snappy
- Metadados adicionados: `_source_schema`, `_source_table`, `_ingested_at`, `_row_count_batch`
- Sem PII em plain text — dados sintéticos (Faker pt_BR)
- Watermarks em JSON no GCS: `{"last_updated_at": "2026-08-11T04:00:12+00:00", ...}`
- Retenção: nenhuma expiração automática (volume pequeno; ~165 MB)

**Como funciona:**

```
extract.py --mode smart
│
├── Para cada tabela:
│   ├── Ler watermark de gs://jstechstore-bronze/.watermarks/<key>.json
│   ├── SELECT * FROM supabase WHERE updated_at > watermark
│   ├── Serializar em Parquet (BytesIO, sem disco)
│   ├── Upload para gs://jstechstore-bronze/<schema>/<table>/year=.../...parquet
│   └── Atualizar watermark no GCS (somente após upload bem-sucedido)
│
└── Se --mode full: watermark = EPOCH (extrai tudo)
```

---

### Silver — BigQuery (External Tables + tabelas materializadas)

**Responsabilidade:** limpeza, tipagem, deduplicação e regras de negócio básicas.

#### Subcamada: External Tables (`jstechstore_bronze_ext`)

28 External Tables no BigQuery apontando para os Parquet do GCS. Criadas e mantidas pelo `dbt-external-tables`:

```sql
-- Exemplo: jstechstore_bronze_ext.vendas__pedidos
-- Location: gs://jstechstore-bronze/vendas/pedidos/**/*.parquet
-- Format: PARQUET
-- Partition: Hive-style (year/month/day)
```

O BQ lê os arquivos Parquet do GCS em tempo de query — não há cópia dos dados. Latência adicional vs. tabelas nativas é aceitável para batch diário.

#### Subcamada: Staging (`jstechstore_silver`)

28 modelos `stg_<schema>__<table>` — incrementais com `unique_key`:

- Leem de `jstechstore_bronze_ext.*`
- Aplicam tipagem explícita com `CAST()`
- Deduplicam por chave natural (`ROW_NUMBER() OVER (PARTITION BY key ORDER BY updated_at DESC)`)
- Filtro incremental: `CAST(_ingested_at AS TIMESTAMP) > MAX(_ingested_at) FROM {{ this }}`

#### Subcamada: Intermediária (`jstechstore_silver`)

3 modelos `int_<domain>__<entity>`:

| Modelo | Responsabilidade |
|--------|----------------|
| `int_clientes__unificados` | Dedup por CPF, cálculo RFM, LTV, nível fidelidade |
| `int_vendas__pedidos_unificados` | União pedidos + itens + devoluções; hierarquia de status |
| `int_produtos__catalogo` | União produto + categoria + fornecedor + preço vigente |

---

### Gold — BigQuery (`jstechstore_gold`)

**Responsabilidade:** dimensional warehouse pronto para consumo pelo Power BI.

#### Dimensões (10 tabelas — `materialized='table'`)

| Tabela | Grão | Registros estimados | SCD |
|--------|------|-------------------|-----|
| `dim_cliente` | 1 por cliente | ~10.000 | Type 2 |
| `dim_produto` | 1 por produto | ~500 | Type 2 |
| `dim_loja` | 1 por loja | 15 | Type 2 |
| `dim_tempo` | 1 por dia | ~1.827 (5 anos) | Nenhum |
| `dim_canal_venda` | 1 por canal | ~5 | Nenhum |
| `dim_campanha` | 1 por campanha | ~200 | Type 2 |
| `dim_vendedor` | 1 por vendedor | ~150 | Type 2 |
| `dim_transportadora` | 1 por transportadora | ~10 | Nenhum |
| `dim_fornecedor` | 1 por fornecedor | ~50 | Nenhum |
| `dim_modalidade_entrega` | 1 por modalidade | ~8 | Nenhum |

#### Fatos (6 tabelas — `materialized='incremental'`)

| Tabela | Grão | Volume estimado |
|--------|------|----------------|
| `fato_venda` | Item × pedido | ~300.000 linhas/mês |
| `fato_estoque` | Produto × loja × dia | ~450 linhas/dia |
| `fato_entrega` | 1 por entrega | ~15.000 linhas/mês |
| `fato_financeiro` | 1 por lançamento | ~20.000 linhas/mês |
| `fato_cliente_interacao` | 1 por interação | ~50.000 linhas/mês |
| `fato_orcamento` | 1 por linha de orçamento | ~5.000 linhas/mês |

**Convenções:**
- Surrogate keys: `sk_*` — `TO_HEX(MD5(CONCAT(...)))` — 32 chars hex
- Chaves naturais: `*_nk`; chaves degeneradas: `*_dg`
- SCD Type 2: `valid_from`, `valid_to`, `fl_current`, `hash_row`
- Preços históricos na fato, não na dim_produto
- Filtro incremental por `sk_tempo` (date-based window)

---

## 4. Pipeline de orquestração (GitHub Actions)

### Diagrama do pipeline diário

```
GitHub Actions · Cron 04:00 UTC (01:00 BRT)
│
├── Setup
│   ├── Checkout repositório
│   ├── Setup Python 3.12
│   ├── pip install -r requirements.txt
│   └── Autenticar no GCP (google-github-actions/auth)
│
├── Step 1 · Geração de dados sintéticos
│   └── python scripts/generate_daily.py --date today
│       [pulado se full_refresh=true]
│
├── Step 2 · Ingestão Bronze → GCS
│   ├── python -m ingestion.connectors.postgres.extract --mode smart
│   │   (ou --mode full se full_refresh=true)
│   └── Diagnóstico: gsutil ls gs://jstechstore-bronze/ | wc -l
│
├── Step 3 · dbt transformações
│   ├── dbt deps
│   ├── dbt seed --select feriados_nacionais
│   ├── dbt run-operation stage_external_sources   ← sincroniza External Tables
│   └── dbt run [--full-refresh]
│
├── Step 4 · Qualidade Gold
│   └── dbt test --select gold
│
├── Step 5 · Frescor Bronze + Gold
│   └── python quality/monitoring/check_data_freshness.py --tolerance-hours 26
│
├── Step 6 · Reconciliação Gold vs. Supabase
│   └── python quality/reconciliation/reconcile_gold_vs_source.py
│       [query via bigquery.Client]
│
└── Notificação em caso de falha
    └── echo ::error:: + link para o run
```

### Variáveis de ambiente no GHA

```yaml
env:
  SUPABASE_DB_URL:  ${{ secrets.SUPABASE_DB_URL }}
  GCP_PROJECT_ID:   ${{ secrets.GCP_PROJECT_ID }}
  GCS_BUCKET:       ${{ secrets.GCS_BUCKET }}
  GCP_SA_KEY_JSON:  ${{ secrets.GCP_SA_KEY }}
  BQ_DATASET_GOLD:  jstechstore_gold
```

### GitHub Secrets necessários

| Secret | Descrição |
|--------|-----------|
| `SUPABASE_DB_URL` | Connection string PostgreSQL do Supabase |
| `GCP_SA_KEY` | JSON da Service Account GCP (base64 ou inline) |
| `GCP_PROJECT_ID` | ID do projeto GCP (ex: `jstechstore-data`) |
| `GCS_BUCKET` | Nome do bucket GCS Bronze (ex: `jstechstore-bronze`) |

---

## 5. Power BI — sem Gateway

### Antes (v1)

```
Power BI Desktop → ODBC DSN "JSTechStoreGold" → DuckDB ODBC Driver
→ data/gold/jstechstore.duckdb (local) → On-premises Gateway → Power BI Service
```

**Dependências:** máquina local ligada 24/7, driver ODBC instalado, Gateway rodando como serviço Windows.

### Depois (v2)

```
Power BI Desktop → Conector BigQuery (nativo) → jstechstore_gold (BQ) → Power BI Service
```

**Sem dependências locais.** O conector BigQuery nativo do Power BI usa autenticação OAuth com a conta Microsoft/Google. Não requer ODBC, não requer Gateway.

### Setup Power BI v2

1. Power BI Desktop → **Obter Dados** → **Google BigQuery**
2. Autenticar com conta Google que tem acesso ao projeto GCP
3. Selecionar projeto `jstechstore-data` → dataset `jstechstore_gold`
4. Importar todas as `dim_*` e `fato_*`
5. Configurar Incremental Refresh em `fato_venda`:
   - Parâmetros M: `RangeStart` e `RangeEnd` (tipo `DateTime`)
   - Arquivar: dados com mais de 2 anos
   - Refresh window: últimos 3 dias
6. Publicar no Power BI Service → **não é necessário configurar Gateway**
7. Agendar refresh: 05:30 BRT (após pipeline GHA concluir ~05:00)

### Limites Power BI v2

| Métrica | Antes (v1) | Depois (v2) |
|---------|-----------|------------|
| Limite dataset | 1 GB (Pro) | 1 GB (Pro) — mas BQ serve só o necessário |
| Refresh/dia | 8× (Pro) | 8× (Pro) |
| Gateway necessário | Sim | **Não** |
| ODBC Driver necessário | Sim | **Não** |
| Máquina local ligada | Sim (Gateway) | **Não** |

---

## 6. Estratégia de backup e recuperação (v2)

Na arquitetura v2, a estratégia de backup muda fundamentalmente:

### Bronze — GCS

- GCS tem **replicação geográfica automática** no tier padrão
- Nenhum backup adicional necessário para Bronze — os arquivos Parquet são a fonte de verdade
- Se necessário, ativar **Object Versioning** no bucket para proteger contra deleção acidental:
  ```bash
  gsutil versioning set on gs://jstechstore-bronze
  ```

### Gold — BigQuery

BigQuery oferece **Time Travel** nativo: qualquer tabela pode ser consultada em qualquer ponto dos últimos 7 dias:

```sql
-- Consultar fato_venda como estava 24h atrás
SELECT * FROM `jstechstore_gold.fato_venda`
FOR SYSTEM_TIME AS OF TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
```

**Restaurar uma tabela para um ponto no tempo:**
```bash
bq cp \
  "jstechstore_gold.fato_venda@-86400000" \
  "jstechstore_gold.fato_venda_restaurada"
```

### Reconstrução completa (equivalente ao Cenário C da v1)

Se o Gold precisar ser reconstruído do zero:

```bash
# 1. Ingestão full do Bronze no GCS (já existente — só roda se necessário)
python -m ingestion.connectors.postgres.extract --mode full

# 2. Rebuild Gold via dbt
cd transformation/dbt_project
dbt run --full-refresh

# 3. Validar
dbt test --select gold
```

O Bronze em GCS elimina a dependência de ter Parquet local — qualquer máquina com credenciais GCP consegue reconstruir.

---

## 7. Segurança e credenciais

### Diagrama de credenciais

```
┌──────────────────────────────────────────────────┐
│  GitHub Secrets (encryptados)                    │
│  ├── SUPABASE_DB_URL  → extract.py               │
│  ├── GCP_SA_KEY       → google-github-actions    │
│  ├── GCP_PROJECT_ID   → profiles.yml + scripts   │
│  └── GCS_BUCKET       → extract.py               │
└──────────────────────────────────────────────────┘
                    │ injetado em runtime
                    ▼
┌──────────────────────────────────────────────────┐
│  Service Account dbt-runner@...                  │
│  Roles:                                          │
│  ├── BigQuery Data Editor                        │
│  ├── BigQuery Job User                           │
│  └── Storage Object Admin                        │
└──────────────────────────────────────────────────┘
```

### Princípio de menor privilégio

| Acesso | Service Account | Power BI |
|--------|----------------|---------|
| Leitura GCS Bronze | ✅ (`Storage Object Admin`) | ❌ (não precisa) |
| Escrita GCS Bronze | ✅ | ❌ |
| Leitura BQ Gold | ✅ | ✅ (via OAuth Google) |
| Escrita BQ Gold | ✅ (dbt materializa) | ❌ |
| Leitura Supabase | ✅ (via `extract.py`) | ❌ |

### O que nunca commitar

```
.env                          ← todas as credenciais ficam aqui localmente
key.json                      ← chave da Service Account GCP
```

---

## 8. Comandos comuns (v2)

### Ingestão

```bash
# Full load — extrai tudo do Supabase para GCS
python -m ingestion.connectors.postgres.extract --mode full

# Incremental — extrai apenas registros novos/alterados
python -m ingestion.connectors.postgres.extract --mode smart

# Tabela específica
python -m ingestion.connectors.postgres.extract --mode incremental --table vendas.pedidos

# Verificar o que está no GCS
gsutil ls -l gs://jstechstore-bronze/vendas/pedidos/
```

### dbt

```bash
cd transformation/dbt_project

# Instalar pacotes
dbt deps

# Criar/sincronizar External Tables no BigQuery
dbt run-operation stage_external_sources

# Full rebuild (primeira vez ou após full_refresh)
dbt run --full-refresh

# Run incremental diário
dbt run

# Camada específica
dbt run --select bronze
dbt run --select silver
dbt run --select gold

# Modelo específico
dbt run --select fato_venda

# Testes
dbt test --select gold
```

### BigQuery (consultas de sanidade)

```bash
# Contar linhas em fato_venda
bq query --nouse_legacy_sql \
  'SELECT COUNT(*) as total FROM `jstechstore_gold.fato_venda`'

# Verificar última data de carga
bq query --nouse_legacy_sql \
  'SELECT MAX(dt_pedido_data) as ultima_data FROM `jstechstore_gold.fato_venda`'

# Time Travel — estado de 24h atrás
bq query --nouse_legacy_sql \
  'SELECT COUNT(*) FROM `jstechstore_gold.fato_venda`
   FOR SYSTEM_TIME AS OF TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)'
```

### GCS

```bash
# Listar arquivos Bronze de uma tabela
gsutil ls gs://jstechstore-bronze/vendas/pedidos/**

# Verificar watermarks
gsutil cat gs://jstechstore-bronze/.watermarks/vendas__pedidos.json

# Upload pontual (migração inicial)
python scripts/upload_bronze_to_gcs.py --source data/bronze --bucket jstechstore-bronze

# Tamanho total do bucket
gsutil du -sh gs://jstechstore-bronze/
```

---

## 9. Variáveis de ambiente (v2)

Copiar `.env.example` → `.env`. Nunca commitar `.env`.

```bash
# ── Supabase (fonte OLTP) ─────────────────────────────────
SUPABASE_DB_URL=postgresql://postgres:<pw>@<project>.supabase.co:5432/postgres

# ── GCP / Google Cloud ────────────────────────────────────
GCP_PROJECT_ID=jstechstore-data
GCS_BUCKET=jstechstore-bronze
GCP_SA_KEY_JSON=/path/para/service_account.json  # ou conteúdo inline JSON

# ── BigQuery ──────────────────────────────────────────────
BQ_DATASET_GOLD=jstechstore_gold
BQ_DATASET_SILVER=jstechstore_silver
BQ_DATASET_BRONZE_EXT=jstechstore_bronze_ext
BQ_LOCATION=southamerica-east1

# ── dbt ───────────────────────────────────────────────────
# dbt lê GCP_PROJECT_ID e GCP_SA_KEY_JSON diretamente via profiles.yml

# ── LGPD ──────────────────────────────────────────────────
LGPD_HMAC_SALT=<secret-salt>  # nunca commitar
```

> **Nota:** variáveis `DUCKDB_PATH`, `BRONZE_PATH`, `SILVER_PATH` e `GOLD_BACKUP_DIR` são eliminadas na v2.

---

## 10. Comparação v1 vs v2

| Aspecto | v1 (DuckDB local) | v2 (BigQuery + GCS) |
|---------|-----------------|-------------------|
| Bronze storage | Disco local (165 MB) | GCS (replicated) |
| Gold storage | Arquivo .duckdb (362 MB) | BigQuery dataset |
| Dependency local | Sim — disco com dados | Não — stateless |
| Power BI Gateway | Necessário | **Não necessário** |
| Power BI ODBC | Necessário | **Não necessário** |
| Máquina ligada | Sim (Gateway) | **Não** |
| Backup manual | Sim (backup_gold.py) | BQ Time Travel nativo |
| Multi-colaborador | Difícil (arquivo local) | **Qualquer máquina** |
| Custo | $0 (tudo local) | $0 (free tier BQ+GCS) |
| Escalabilidade | Limitada (1 GB PBI) | Alta (BQ serverless) |
| Latência dbt run | Baixa (DuckDB local) | Maior (BQ network) |
| SQL compat. | DuckDB/PostgreSQL | BigQuery Standard SQL |
