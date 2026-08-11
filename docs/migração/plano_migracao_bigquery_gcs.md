# Plano de Migração — DuckDB/Local → BigQuery + GCS

**Versão:** 1.0  
**Data:** 2026-08-11  
**Status:** 🟡 Planejamento — aguardando execução  
**Responsável:** Engenharia de Dados

---

## 1. Objetivo

Eliminar toda dependência de armazenamento local da plataforma de dados JSTechStore, migrando:

| Camada | De (atual) | Para |
|--------|-----------|------|
| Bronze | `data/bronze/` — Parquet local | GCS bucket `jstechstore-bronze` |
| Silver | DuckDB local (views internas) | BigQuery dataset `jstechstore_silver` |
| Gold | `data/gold/jstechstore.duckdb` | BigQuery dataset `jstechstore_gold` |
| Compute | dbt-duckdb local / GHA runner | dbt-bigquery no GHA runner |
| Power BI | ODBC → DuckDB local + Gateway | Conector BigQuery nativo (sem ODBC) |

**Motivação principal:** eliminar o arquivo `.duckdb` local de 362 MB e o Parquet Bronze de 165 MB como dependências de máquina física, permitindo que qualquer colaborador rode o pipeline sem estado local.

---

## 2. O que é eliminado

```
REMOVIDO:
  data/gold/jstechstore.duckdb        ← arquivo binário Gold (362 MB)
  data/bronze/                        ← Parquet local (165 MB, 43 arquivos)
  duckdb>=1.1.0                       ← pacote Python
  dbt-duckdb>=1.8.0                   ← adaptador dbt
  scripts/backup_gold.py              ← backup de .duckdb
  scripts/ensure_bronze_parquet.py    ← stubs para tabelas estáticas
  env DUCKDB_PATH                     ← variável de ambiente
  env BRONZE_PATH                     ← variável de ambiente
  env GOLD_BACKUP_DIR                 ← variável de ambiente
  GitHub Actions cache Bronze         ← actions/cache bronze-*
  DuckDB ODBC Driver (Windows)        ← driver local para Power BI
  On-premises Data Gateway            ← gateway para refresh Power BI
```

---

## 3. O que entra na stack

```
ADICIONADO:
  GCS bucket jstechstore-bronze       ← substitui data/bronze/ local
  BigQuery jstechstore_bronze_ext     ← External Tables sobre GCS
  BigQuery jstechstore_silver         ← Silver materializado pelo dbt
  BigQuery jstechstore_gold           ← Gold materializado pelo dbt
  dbt-bigquery>=1.8.0                 ← substitui dbt-duckdb
  google-cloud-bigquery>=3.25.0       ← client Python para BQ
  google-cloud-storage>=2.17.0        ← client Python para GCS
  dbt-external-tables>=0.9.0          ← cria External Tables BQ via dbt
  GCP Service Account                 ← autenticação programática
  GitHub Secret GCP_SA_KEY            ← chave da Service Account
  GHA step: google-github-actions/auth ← substitui variáveis locais
  Power BI conector BigQuery nativo   ← sem ODBC, sem Gateway local
```

---

## 4. Inventário de incompatibilidades DuckDB → BigQuery

A varredura do repositório identificou **409 ocorrências** de sintaxe DuckDB-específica em **41 arquivos SQL**.

### 4.1 Tabela de conversão

| # | DuckDB (atual) | BigQuery (destino) | Onde aparece | Risco |
|---|---------------|-------------------|--------------|-------|
| 1 | `read_parquet('path/**', union_by_name:=true)` | `SELECT * FROM {{ source('bronze_ext', 'tabela') }}` | 28 stg models | Alto |
| 2 | `value::TIMESTAMPTZ` / `::INTEGER` / `::VARCHAR` | `CAST(value AS TIMESTAMP / INT64 / STRING)` | 28 stg + 3 silver + 6 facts | Alto |
| 3 | `DISTINCT ON (col) … ORDER BY` | `ROW_NUMBER() OVER (PARTITION BY col ORDER BY …)` | `int_clientes__unificados` | Alto |
| 4 | `GENERATE_SERIES(d1, d2, INTERVAL '1 day')` | `GENERATE_DATE_ARRAY(d1, d2, INTERVAL 1 DAY)` | `dim_tempo` | Alto |
| 5 | `UNNEST(series)::DATE AS data_full` | `SELECT d FROM UNNEST(GENERATE_DATE_ARRAY(…)) AS d` | `dim_tempo` | Alto |
| 6 | `EXTRACT(DOW FROM date)` → 0=Dom, 6=Sab | `EXTRACT(DAYOFWEEK FROM date)` → **1=Dom, 7=Sab** | `dim_tempo` | **Crítico** — erro silencioso |
| 7 | `STRFTIME(date, '%Y%m%d')` | `FORMAT_DATE('%Y%m%d', date)` | `dim_tempo` | Médio |
| 8 | `EXTRACT(WEEK FROM date)` | `EXTRACT(ISOWEEK FROM date)` | `dim_tempo` | Baixo |
| 9 | `INTERVAL '3 days'` / `INTERVAL '1 day'` | `INTERVAL 3 DAY` / `INTERVAL 1 DAY` | fatos + macros | Médio |
| 10 | `(date1 - date2)::INTEGER` | `DATE_DIFF(date1, date2, DAY)` | `int_clientes__unificados` | Médio |
| 11 | `post_hook: "ANALYZE {{ this }}"` | Remover — BQ não tem `ANALYZE` | 3 silver + 5 facts | Baixo |
| 12 | `MD5(CONCAT_WS('-', …))` → retorna `VARCHAR` | `TO_HEX(MD5(CONCAT(…)))` — BQ MD5 retorna `BYTES` | macros `get_surrogate_key`, `hash_row` | **Crítico** — quebra todos os SKs |
| 13 | `CONCAT_WS('-', a, b, c)` | `CONCAT(a, '-', b, '-', c)` explícito | 2 macros | Médio |
| 14 | `CAST(… AS BOOLEAN)` | `CAST(… AS BOOL)` | stg + dims + facts | Baixo |
| 15 | `NUMERIC(12,2)` em CAST | `NUMERIC` (BQ define precisão no schema) | 28 stg models | Baixo |
| 16 | `'1970-01-01'::TIMESTAMPTZ` literal | `TIMESTAMP '1970-01-01 00:00:00 UTC'` | stg + facts | Baixo |

> ⚠️ **Atenção especial ao item 6 (EXTRACT DOW):** a mudança de 0-based para 1-based inverte a lógica de `fl_fim_de_semana` e `fl_black_friday` em `dim_tempo.sql`. Os valores de Domingo (0→1) e Sábado (6→7) precisam ser atualizados em todas as comparações. Se não corrigido, os dados de calendário ficam errados silenciosamente — sem erro de execução.

> ⚠️ **Atenção especial ao item 12 (MD5 BYTES):** `MD5()` no BigQuery retorna `BYTES`, não `STRING`. Sem `TO_HEX()`, o surrogate key de **todos** os 47 modelos fica com tipo errado, causando falha nos JOINs entre tabelas.

---

## 5. Fases de execução

### Fase 0 — Setup GCP (sem código)

**Duração estimada:** 2 dias  
**Bloqueador:** necessário antes de qualquer outra fase

#### Tarefas

- [ ] Criar projeto GCP `jstechstore-data` (ou aproveitar existente)
- [ ] Ativar APIs: BigQuery API, Cloud Storage API, IAM API
- [ ] Criar GCS bucket `jstechstore-bronze` na região `southamerica-east1`
  ```bash
  gsutil mb -l southamerica-east1 -b on gs://jstechstore-bronze
  ```
- [ ] Criar 3 datasets no BigQuery (mesma região `southamerica-east1`):
  ```
  jstechstore_bronze_ext    ← External Tables que lêem do GCS
  jstechstore_silver        ← Silver materializado
  jstechstore_gold          ← Gold (dims + fatos)
  ```
- [ ] Criar Service Account `dbt-runner@jstechstore-data.iam.gserviceaccount.com`
  - Roles: `BigQuery Data Editor`, `BigQuery Job User`, `Storage Object Admin`
  - Gerar chave JSON e salvar com segurança
- [ ] Adicionar secrets no GitHub Actions:
  ```
  GCP_SA_KEY      ← conteúdo JSON da Service Account (base64)
  GCP_PROJECT_ID  ← ex: jstechstore-data
  GCS_BUCKET      ← jstechstore-bronze
  BQ_DATASET_GOLD ← jstechstore_gold
  ```
- [ ] Adicionar ao `.env.example`:
  ```bash
  GCP_PROJECT_ID=jstechstore-data
  GCS_BUCKET=jstechstore-bronze
  GCP_SA_KEY_JSON=  # path para o JSON ou conteúdo inline
  BQ_DATASET_GOLD=jstechstore_gold
  ```

---

### Fase 1 — Ingestão Bronze → GCS

**Duração estimada:** 3–4 dias  
**Arquivos modificados:** `requirements.txt`, `ingestion/connectors/postgres/extract.py`  
**Arquivos novos:** `scripts/upload_bronze_to_gcs.py`

#### Tarefas

- [ ] **`requirements.txt`** — substituir dependências de armazenamento:
  ```
  REMOVER:  duckdb>=1.1.0
  REMOVER:  dbt-duckdb>=1.8.0

  ADICIONAR: google-cloud-storage>=2.17.0
  ADICIONAR: google-cloud-bigquery>=3.25.0
  ADICIONAR: dbt-bigquery>=1.8.0  (mover aqui ou manter em transformações)
  ```

- [ ] **`extract.py` — função `write_parquet_atomic()`:**  
  Substituir escrita local por upload em memória para GCS:
  ```python
  import io
  from google.cloud import storage

  def write_parquet_to_gcs(df: pd.DataFrame, table: TableConfig, ingested_at: datetime) -> str:
      """Grava DataFrame como Parquet diretamente no GCS. Retorna gs:// URI."""
      client = storage.Client()
      bucket = client.bucket(GCS_BUCKET)

      key = (
          f"{table.schema}/{table.table}/"
          f"year={ingested_at.year}/month={ingested_at.month:02d}/"
          f"day={ingested_at.day:02d}/"
          f"batch_{ingested_at.strftime('%H%M%S')}.parquet"
      )

      df["_source_schema"]   = table.schema
      df["_source_table"]    = table.table
      df["_ingested_at"]     = ingested_at.isoformat()
      df["_row_count_batch"] = len(df)

      buffer = io.BytesIO()
      df.to_parquet(buffer, engine="pyarrow", compression="snappy", index=False)
      buffer.seek(0)

      blob = bucket.blob(key)
      blob.upload_from_file(buffer, content_type="application/octet-stream")
      return f"gs://{GCS_BUCKET}/{key}"
  ```

- [ ] **`extract.py` — watermarks:**  
  Substituir leitura/escrita de arquivo local por GCS JSON:
  ```python
  WATERMARKS_PREFIX = ".watermarks/"

  def read_watermark(table: TableConfig) -> datetime:
      blob = bucket.blob(f"{WATERMARKS_PREFIX}{table.watermark_key}.json")
      if not blob.exists():
          return EPOCH
      data = json.loads(blob.download_as_text(encoding="utf-8"))
      return datetime.fromisoformat(data["last_updated_at"])

  def write_watermark(table: TableConfig, value: datetime) -> None:
      blob = bucket.blob(f"{WATERMARKS_PREFIX}{table.watermark_key}.json")
      blob.upload_from_string(
          json.dumps({"last_updated_at": value.isoformat(), ...}),
          content_type="application/json"
      )
  ```

- [ ] **`extract.py` — função `has_parquet()`:**  
  Substituir verificação de filesystem por listagem GCS:
  ```python
  def has_parquet(table: TableConfig) -> bool:
      prefix = f"{table.schema}/{table.table}/"
      return next(bucket.list_blobs(prefix=prefix, max_results=1), None) is not None
  ```

- [ ] **Criar `scripts/upload_bronze_to_gcs.py`:**  
  Script de migração pontual — faz upload dos 43 arquivos Parquet locais existentes para o bucket GCS, mantendo a estrutura de partições `schema/table/year=.../month=.../day=.../`.
  ```bash
  # Rodar 1× durante a migração
  python scripts/upload_bronze_to_gcs.py --source data/bronze --bucket jstechstore-bronze
  ```

- [ ] **Teste de validação:**
  ```bash
  GOOGLE_APPLICATION_CREDENTIALS=/path/to/key.json \
  python -m ingestion.connectors.postgres.extract --mode incremental --table vendas.pedidos
  
  # Confirmar arquivo no GCS:
  gsutil ls gs://jstechstore-bronze/vendas/pedidos/
  ```

---

### Fase 2 — Bronze: External Tables no BigQuery

**Duração estimada:** 3 dias  
**Arquivos modificados:** 28 `stg_*.sql`, `transformation/dbt_project/profiles.yml`, `transformation/dbt_project/dbt_project.yml`  
**Arquivos novos:** `transformation/dbt_project/packages.yml`, `transformation/dbt_project/models/bronze/sources.yml`

#### Tarefas

- [ ] **`packages.yml` (novo):**
  ```yaml
  packages:
    - package: dbt-labs/dbt_external_tables
      version: [">=0.9.0", "<1.0.0"]
  ```

- [ ] **`profiles.yml` — reescrever completamente:**
  ```yaml
  jstechstore:
    target: dev
    outputs:
      dev:
        type: bigquery
        method: service-account-json
        project: "{{ env_var('GCP_PROJECT_ID') }}"
        dataset: jstechstore_gold
        location: southamerica-east1
        keyfile_json: "{{ env_var('GCP_SA_KEY_JSON') }}"
        threads: 4
        timeout_seconds: 300
        priority: interactive

      prod:
        type: bigquery
        method: service-account-json
        project: "{{ env_var('GCP_PROJECT_ID') }}"
        dataset: jstechstore_gold
        location: southamerica-east1
        keyfile_json: "{{ env_var('GCP_SA_KEY_JSON') }}"
        threads: 8
        timeout_seconds: 600
        priority: batch
  ```

- [ ] **`dbt_project.yml` — remover `bronze_path`, adicionar vars GCP:**
  ```yaml
  vars:
    gcs_bucket:        "{{ env_var('GCS_BUCKET', 'jstechstore-bronze') }}"
    gcp_project_id:    "{{ env_var('GCP_PROJECT_ID') }}"
    bq_bronze_dataset: jstechstore_bronze_ext
    start_date:        '2023-07-21'
    end_date:          '2026-07-20'
    dim_inicio:        '2023-01-01'
    dim_fim:           '2027-12-31'
  ```

- [ ] **`models/bronze/sources.yml` (novo)** — definir 28 External Tables:
  ```yaml
  sources:
    - name: bronze_ext
      schema: jstechstore_bronze_ext
      tables:
        - name: vendas__pedidos
          external:
            location: "gs://jstechstore-bronze/vendas/pedidos/**/*.parquet"
            options:
              format: PARQUET
              hive_partition_uri_prefix: "gs://jstechstore-bronze/vendas/pedidos"
        - name: vendas__itens_pedido
          external:
            location: "gs://jstechstore-bronze/vendas/itens_pedido/**/*.parquet"
        # ... repetir para todas as 28 tabelas
  ```

- [ ] **28 stg models — padrão de reescrita:**

  ```sql
  -- ANTES (DuckDB)
  {{ config(unique_key='id_pedido') }}
  WITH source AS (
      SELECT *
      FROM read_parquet('{{ var("bronze_path") }}/vendas/pedidos/**/*.parquet', union_by_name := true)
      {% if is_incremental() %}
      WHERE _ingested_at::TIMESTAMPTZ > (
          SELECT COALESCE(MAX(_ingested_at::TIMESTAMPTZ), '1970-01-01'::TIMESTAMPTZ)
          FROM {{ this }}
      )
      {% endif %}
  )

  -- DEPOIS (BigQuery)
  {{ config(unique_key='id_pedido') }}
  WITH source AS (
      SELECT *
      FROM {{ source('bronze_ext', 'vendas__pedidos') }}
      {% if is_incremental() %}
      WHERE CAST(_ingested_at AS TIMESTAMP) > (
          SELECT COALESCE(MAX(CAST(_ingested_at AS TIMESTAMP)), TIMESTAMP '1970-01-01 00:00:00 UTC')
          FROM {{ this }}
      )
      {% endif %}
  )
  ```

- [ ] **Conversão de tipos em todos os SELECTs dos stg models:**
  ```
  ::INTEGER      →  CAST(col AS INT64)
  ::VARCHAR      →  CAST(col AS STRING)
  ::TIMESTAMPTZ  →  CAST(col AS TIMESTAMP)
  ::BOOLEAN      →  CAST(col AS BOOL)
  ::NUMERIC      →  CAST(col AS NUMERIC)
  ::DATE         →  CAST(col AS DATE)
  NUMERIC(12,2)  →  NUMERIC
  BOOLEAN        →  BOOL
  ```

- [ ] **Criar External Tables no BQ:**
  ```bash
  cd transformation/dbt_project
  dbt deps
  dbt run-operation stage_external_sources
  ```

- [ ] **Testar camada Bronze:**
  ```bash
  dbt run --select bronze
  dbt test --select bronze
  ```

---

### Fase 3 — Macros

**Duração estimada:** 1 dia  
**Arquivos modificados:** `macros/get_surrogate_key.sql`, `macros/scd2_merge.sql`

#### Tarefas

- [ ] **`get_surrogate_key.sql` — MD5 retorna BYTES no BQ:**
  ```sql
  -- ANTES (DuckDB)
  MD5(
      CONCAT_WS(
          '-',
          {% for field in fields %}
              COALESCE(CAST({{ field }} AS VARCHAR), 'NULL')
              {%- if not loop.last %}, {% endif %}
          {% endfor %}
      )
  )

  -- DEPOIS (BigQuery)
  TO_HEX(MD5(
      CONCAT(
          {% for field in fields %}
              COALESCE(CAST({{ field }} AS STRING), 'NULL')
              {%- if not loop.last %}, '-', {% endif %}
          {% endfor %}
      )
  ))
  ```

- [ ] **`scd2_merge.sql` — macro `hash_row`:**
  ```sql
  -- ANTES
  MD5(CONCAT_WS('|', {% for field in fields %} COALESCE(CAST({{ field }} AS VARCHAR), '') {%- if not loop.last %}, {% endif %} {% endfor %}))

  -- DEPOIS
  TO_HEX(MD5(CONCAT({% for field in fields %} COALESCE(CAST({{ field }} AS STRING), '') {%- if not loop.last %}, '|', {% endif %} {% endfor %})))
  ```

- [ ] **`scd2_merge.sql` — macro `scd2_close_expired`:**
  ```sql
  -- ANTES
  valid_to = CURRENT_DATE - INTERVAL '1 day'

  -- DEPOIS
  valid_to = DATE_SUB(CURRENT_DATE, INTERVAL 1 DAY)
  ```

- [ ] **`rfm_score.sql`:** sem alterações — usa apenas `CASE/WHEN` com comparações numéricas.

---

### Fase 4 — Silver (3 modelos intermediários)

**Duração estimada:** 2–3 dias  
**Arquivos modificados:** `int_clientes__unificados.sql`, `int_vendas__pedidos_unificados.sql`, `int_produtos__catalogo.sql`

#### Tarefas

- [ ] **`int_clientes__unificados.sql` — 3 pontos críticos:**

  **1. `DISTINCT ON` → `ROW_NUMBER()`:**
  ```sql
  -- ANTES (DuckDB/PostgreSQL)
  SELECT DISTINCT ON (id_cliente) id_cliente, cep, cidade, uf
  FROM {{ ref('stg_clientes__enderecos') }}
  WHERE tipo = 'principal'
  ORDER BY id_cliente, updated_at DESC

  -- DEPOIS (BigQuery)
  WITH ranked AS (
      SELECT *, ROW_NUMBER() OVER (PARTITION BY id_cliente ORDER BY updated_at DESC) AS rn
      FROM {{ ref('stg_clientes__enderecos') }}
      WHERE tipo = 'principal'
  )
  SELECT id_cliente, cep, cidade, uf FROM ranked WHERE rn = 1
  ```

  **2. Subtração de datas → `DATE_DIFF()`:**
  ```sql
  -- ANTES
  (DATE '{{ var("end_date") }}' - pc.ultima_compra)::INTEGER

  -- DEPOIS
  DATE_DIFF(DATE '{{ var("end_date") }}', pc.ultima_compra, DAY)
  ```

  **3. Literal de timestamp:**
  ```sql
  -- ANTES
  COALESCE(MAX(_ingested_at), '1970-01-01'::TIMESTAMPTZ)

  -- DEPOIS
  COALESCE(MAX(_ingested_at), TIMESTAMP '1970-01-01 00:00:00 UTC')
  ```

- [ ] **`int_vendas__pedidos_unificados.sql`:**
  - Remover `post_hook: "ANALYZE {{ this }}"`
  - Corrigir `::TIMESTAMPTZ` e castings

- [ ] **`int_produtos__catalogo.sql`:**
  - Corrigir castings e tipos

- [ ] **Testar Silver:**
  ```bash
  dbt run --select silver
  dbt test --select silver
  ```

---

### Fase 5 — Gold (10 dimensões + 6 fatos)

**Duração estimada:** 5–7 dias  
**Arquivos modificados:** todos os 16 modelos Gold

#### 5.1 `dim_tempo.sql` — maior reescrita

```sql
-- ANTES (DuckDB) — SPINE
WITH spine AS (
    SELECT UNNEST(
        GENERATE_SERIES(
            DATE '{{ var("dim_inicio") }}',
            DATE '{{ var("dim_fim") }}',
            INTERVAL '1 day'
        )
    )::DATE AS data_full
)

-- DEPOIS (BigQuery) — SPINE
WITH spine AS (
    SELECT d AS data_full
    FROM UNNEST(
        GENERATE_DATE_ARRAY(
            DATE '{{ var("dim_inicio") }}',
            DATE '{{ var("dim_fim") }}',
            INTERVAL 1 DAY
        )
    ) AS d
)
```

```sql
-- STRFTIME → FORMAT_DATE
STRFTIME(data_full, '%Y%m%d')         →  FORMAT_DATE('%Y%m%d', data_full)
STRFTIME(data_full, '%Y-%m')          →  FORMAT_DATE('%Y-%m', data_full)
STRFTIME(data_full, '%Y-Q')           →  FORMAT_DATE('%Y-Q', data_full)  -- verificar suporte

-- EXTRACT DOW — MUDANÇA DE SEMÂNTICA (crítico!)
-- DuckDB: 0=Dom, 1=Seg, 2=Ter, 3=Qua, 4=Qui, 5=Sex, 6=Sab
-- BigQuery: 1=Dom, 2=Seg, 3=Ter, 4=Qua, 5=Qui, 6=Sex, 7=Sab

EXTRACT(DOW FROM data_full)           →  EXTRACT(DAYOFWEEK FROM data_full)
-- fl_fim_de_semana: IN (0, 6)        →  IN (1, 7)
-- nome_dia_semana CASE 0='Domingo'   →  CASE 1='Domingo'
-- fl_black_friday WHEN DOW = 5       →  WHEN DAYOFWEEK = 6  (Sexta = 5 no DuckDB, 6 no BQ)

-- EXTRACT WEEK → ISOWEEK
EXTRACT(WEEK FROM data_full)          →  EXTRACT(ISOWEEK FROM data_full)

-- INTERVAL
INTERVAL '7 days'                     →  INTERVAL 7 DAY
```

#### 5.2 Outras 9 dimensões

Para cada `dim_*.sql`:
- [ ] Aplicar conversões padrão `::TYPE` → `CAST(... AS TYPE)`
- [ ] `VARCHAR` → `STRING`, `INTEGER` → `INT64`, `BOOLEAN` → `BOOL`
- [ ] `DATE '9999-12-31'` e `CURRENT_DATE` são compatíveis com BQ (sem mudança)
- [ ] Verificar se há macros `scd2_close_expired` em pre_hooks — ajustar INTERVAL (já coberto na Fase 3)

#### 5.3 6 fatos — alterações padrão

```sql
-- Remover em todos os fatos:
post_hook: "ANALYZE {{ this }}"

-- INTERVAL em fato_venda:
MAX(dt_pedido_data) - INTERVAL '3 days'  →  DATE_SUB(MAX(dt_pedido_data), INTERVAL 3 DAY)

-- Literal de timestamp:
'1970-01-01'::TIMESTAMPTZ  →  TIMESTAMP '1970-01-01 00:00:00 UTC'
```

#### 5.4 Seeds

- [ ] Atualizar `schema.yml` para seeds: `column_types` com tipos BQ:
  ```yaml
  seeds:
    jstechstore:
      feriados_nacionais:
        +column_types:
          data: DATE
          nome_feriado: STRING
          tipo: STRING
  ```

- [ ] **Testar Gold:**
  ```bash
  dbt seed --select feriados_nacionais
  dbt run --full-refresh --select gold
  dbt test --select gold
  ```

---

### Fase 6 — GitHub Actions Pipeline

**Duração estimada:** 2–3 dias  
**Arquivos modificados:** `daily_pipeline.yml`, `quality/reconciliation/reconcile_gold_vs_source.py`, `quality/monitoring/check_data_freshness.py`

#### Tarefas

- [ ] **Remover do workflow:**
  - Steps de cache Bronze (`actions/cache` com chaves `bronze-*`, `watermarks-*`)
  - Step `mkdir -p data/bronze data/bronze/.watermarks`
  - Step `ensure_bronze_parquet.py`
  - Step `backup_gold.py`
  - Step de upload do artifact `.duckdb.gz`
  - Env vars `DUCKDB_PATH`, `BRONZE_PATH`, `SILVER_PATH`, `GOLD_BACKUP_DIR`

- [ ] **Adicionar autenticação GCP:**
  ```yaml
  - name: Autenticar no GCP
    uses: google-github-actions/auth@v2
    with:
      credentials_json: ${{ secrets.GCP_SA_KEY }}

  - name: Setup gcloud CLI
    uses: google-github-actions/setup-gcloud@v2
  ```

- [ ] **Adicionar env vars GCP:**
  ```yaml
  env:
    GCP_PROJECT_ID:  ${{ secrets.GCP_PROJECT_ID }}
    GCS_BUCKET:      ${{ secrets.GCS_BUCKET }}
    GCP_SA_KEY_JSON: ${{ secrets.GCP_SA_KEY }}
    BQ_DATASET_GOLD: jstechstore_gold
  ```

- [ ] **Adicionar step de External Tables antes do dbt run:**
  ```yaml
  - name: "2b · Sincronizar External Tables BQ"
    run: |
      dbt run-operation stage_external_sources \
        --project-dir transformation/dbt_project \
        --profiles-dir transformation/dbt_project
  ```

- [ ] **`reconcile_gold_vs_source.py` — substituir DuckDB por BQ:**
  ```python
  # ANTES
  import duckdb
  con = duckdb.connect(os.environ["DUCKDB_PATH"], read_only=True)
  result = con.execute("SELECT COUNT(*) FROM fato_venda").fetchone()

  # DEPOIS
  from google.cloud import bigquery
  client = bigquery.Client(project=os.environ["GCP_PROJECT_ID"])
  query = "SELECT COUNT(*) FROM `jstechstore_gold.fato_venda`"
  result = client.query(query).result()
  ```

- [ ] **`check_data_freshness.py` — substituir DuckDB por BQ:**
  - Mesma substituição: `duckdb.connect()` → `bigquery.Client()`
  - Queries de freshness apontam para `jstechstore_gold.fato_venda`

---

### Fase 7 — Validação Final + Power BI

**Duração estimada:** 2 dias

#### Tarefas

- [ ] Disparar `workflow_dispatch` com `full_refresh=true` no GitHub Actions
- [ ] Confirmar todos os steps passando no GHA (sem cache local, 100% cloud)
- [ ] Validar: `dbt test --select gold` → meta 80/80 testes
- [ ] Validar reconciliação: 8/8 checks ≤ 0,1% de desvio vs. Supabase
- [ ] **Power BI — conectar via conector BigQuery nativo:**
  1. Power BI Desktop → Obter Dados → Google BigQuery
  2. Informar Project ID: `jstechstore-data`
  3. Selecionar dataset: `jstechstore_gold`
  4. Importar todas as `dim_*` e `fato_*`
  5. Configurar Incremental Refresh em `fato_venda` (parâmetros `RangeStart`/`RangeEnd` — mesmo comportamento de antes)
  6. Publicar no Power BI Service → não é necessário configurar Gateway

---

## 6. Inventário completo de arquivos

### Modificados

| Arquivo | Fase | Tipo de mudança |
|---------|------|----------------|
| `requirements.txt` | 1 | Remover duckdb/dbt-duckdb; adicionar google-cloud-* |
| `ingestion/connectors/postgres/extract.py` | 1 | Escrita local → GCS upload |
| `transformation/dbt_project/profiles.yml` | 2 | Reescrita completa (duckdb → bigquery) |
| `transformation/dbt_project/dbt_project.yml` | 2 | Remover bronze_path; adicionar vars GCP |
| `transformation/dbt_project/macros/get_surrogate_key.sql` | 3 | MD5+CONCAT_WS → TO_HEX+CONCAT |
| `transformation/dbt_project/macros/scd2_merge.sql` | 3 | MD5+CONCAT_WS → TO_HEX+CONCAT; INTERVAL fix |
| `models/bronze/stg_*.sql` (×28) | 2 | read_parquet → source; casting; tipos |
| `models/silver/int_clientes__unificados.sql` | 4 | DISTINCT ON, DATE_DIFF, timestamp literal |
| `models/silver/int_vendas__pedidos_unificados.sql` | 4 | ANALYZE removal; castings |
| `models/silver/int_produtos__catalogo.sql` | 4 | Castings; tipos |
| `models/gold/dimensions/dim_tempo.sql` | 5 | Reescrita quase completa |
| `models/gold/dimensions/dim_*.sql` (×9) | 5 | Castings; tipos |
| `models/gold/facts/fato_*.sql` (×6) | 5 | ANALYZE removal; INTERVAL; timestamp |
| `.github/workflows/daily_pipeline.yml` | 6 | Remover cache; adicionar GCP auth |
| `quality/reconciliation/reconcile_gold_vs_source.py` | 6 | DuckDB → BigQuery client |
| `quality/monitoring/check_data_freshness.py` | 6 | DuckDB → BigQuery client |

### Criados

| Arquivo | Fase | Descrição |
|---------|------|-----------|
| `transformation/dbt_project/packages.yml` | 2 | Declarar dbt-external-tables |
| `transformation/dbt_project/models/bronze/sources.yml` | 2 | 28 External Table sources |
| `scripts/upload_bronze_to_gcs.py` | 1 | Migração pontual Bronze local → GCS |

### Removidos

| Arquivo | Motivo |
|---------|--------|
| `scripts/backup_gold.py` | DuckDB não existe mais |
| `scripts/ensure_bronze_parquet.py` | Stubs locais não são mais necessários |
| `data/bronze/**/stub_empty.parquet` (×15) | Stubs do workaround dos PRs #23/#24 |
| `data/gold/jstechstore.duckdb` | Substituído pelo BigQuery |

---

## 7. Documentação a atualizar após a migração

| Documento | Mudança necessária |
|-----------|-------------------|
| `docs/arquitetura/estrategia_backup_gold.md` | Estratégia de backup muda: sem .duckdb, backup é o próprio GCS+BQ |
| `docs/arquitetura/powerbi_gateway_setup.md` | Gateway e ODBC eliminados; substituir por setup do conector BQ nativo |
| `docs/onboarding/contas_e_acessos.md` | Adicionar GCP; remover DuckDB ODBC Driver e Gateway |
| `CLAUDE.md` | Atualizar arquitetura, comandos dbt, env vars |

---

## 8. Riscos e mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|-------|--------------|---------|-----------|
| `EXTRACT(DAYOFWEEK)` com semântica diferente | Alta | Alto — dados de calendário errados | Validar `dim_tempo` com query que compara dia da semana de datas conhecidas (ex: 2026-01-01 = Quinta-feira) |
| `MD5()` retornando BYTES quebra todos os JOINs | Alta | Crítico | Testar `get_surrogate_key` isoladamente antes dos modelos Gold |
| `dbt run --full-refresh` no BQ é mais lento que DuckDB | Média | Médio — timeout no GHA | Aumentar `timeout_seconds` no profile prod para 600+ |
| BQ `southamerica-east1` indisponível durante migração | Baixa | Alto | Dados em GCS + BQ são replicados internamente pelo Google |
| Custo BQ ultrapassar free tier | Baixa | Baixo | Volume atual (527 MB) é pequeno; free tier BQ = 10 GB armazenamento + 1 TB queries/mês |
| External Tables têm latência maior que tabelas nativas | Alta | Baixo | Aceitável para batch diário; se latência for problema, usar `bq load` para materializar Bronze |

---

## 9. Estimativa de tempo por fase

| Fase | Descrição | Estimativa |
|------|-----------|-----------|
| 0 | Setup GCP | 2 dias |
| 1 | Ingestão Bronze → GCS | 3–4 dias |
| 2 | Bronze External Tables | 3 dias |
| 3 | Macros | 1 dia |
| 4 | Silver | 2–3 dias |
| 5 | Gold (dim_tempo + resto) | 5–7 dias |
| 6 | GitHub Actions + Quality | 2–3 dias |
| 7 | Validação Final + Power BI | 2 dias |
| **Total** | | **20–25 dias úteis** |

> Estimativa baseada em dedicação part-time (~4h/dia). Full-time reduziria para ~10–12 dias.

---

## 10. Checklist de conclusão

```
[ ] Fase 0: GCP configurado — bucket, datasets, Service Account, Secrets GitHub
[ ] Fase 1: extract.py grava no GCS; watermarks no GCS; upload_bronze_to_gcs.py executado
[ ] Fase 2: 28 stg models usando source(); External Tables no BQ; dbt test bronze ✅
[ ] Fase 3: MD5 → TO_HEX(MD5()); CONCAT_WS → CONCAT; INTERVAL corrigido
[ ] Fase 4: DISTINCT ON removido; DATE_DIFF; ANALYZE removido; dbt test silver ✅
[ ] Fase 5: dim_tempo reescrito e validado; 16 modelos gold corrigidos; dbt test gold ✅
[ ] Fase 6: GHA pipeline sem cache local; GCP auth; scripts quality adaptados
[ ] Fase 7: pipeline completo via GHA ✅; 80/80 testes ✅; 8/8 reconciliação ✅; Power BI conectado ✅
[ ] Docs: CLAUDE.md, contas_e_acessos.md, powerbi_gateway_setup.md atualizados
[ ] data/bronze/ local removido do .gitignore e do repositório
[ ] .env.example atualizado com vars GCP
```
