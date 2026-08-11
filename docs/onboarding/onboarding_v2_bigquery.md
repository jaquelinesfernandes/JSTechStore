# Onboarding — JSTechStore Data Platform v2 (BigQuery + GCS)

**Versão:** 2.0  
**Data:** 2026-08-11  
**Arquitetura:** BigQuery + Google Cloud Storage  
**Para:** Novos membros da equipe de Engenharia de Dados

> **Migrando da v1?** Veja `docs/migração/plano_migracao_bigquery_gcs.md` para o plano completo de transição. Este guia já descreve o estado final — sem DuckDB, sem armazenamento local.

---

## O que é este projeto

A **JSTechStore Brasil** é uma rede varejista omnichannel (15 lojas físicas + e-commerce) que precisa de uma visão unificada de vendas, clientes, estoque, logística e financeiro. Este projeto entrega uma plataforma de dados completa com:

- **Fonte:** Supabase (PostgreSQL) com dados sintéticos gerados por Faker pt_BR
- **Ingestão:** Python → Google Cloud Storage (Bronze)
- **Transformação:** dbt → BigQuery (Silver + Gold)
- **BI:** Power BI com 6 dashboards executivos
- **Orquestração:** GitHub Actions (cron diário 04:00 UTC)

**Nada roda ou fica armazenado localmente.** A única coisa que você precisa na sua máquina são as ferramentas de desenvolvimento (Python, dbt, gcloud CLI). Os dados vivem no GCS e no BigQuery.

---

## Índice

1. [Arquitetura em um olhar](#1-arquitetura-em-um-olhar)
2. [Pré-requisitos de ferramentas](#2-pré-requisitos-de-ferramentas)
3. [Contas e acessos necessários](#3-contas-e-acessos-necessários)
4. [Setup do ambiente local](#4-setup-do-ambiente-local)
5. [Configurar variáveis de ambiente](#5-configurar-variáveis-de-ambiente)
6. [Verificar que tudo está funcionando](#6-verificar-que-tudo-está-funcionando)
7. [Primeira execução completa](#7-primeira-execução-completa)
8. [Pipeline diário — o que acontece automaticamente](#8-pipeline-diário--o-que-acontece-automaticamente)
9. [Desenvolvendo com dbt](#9-desenvolvendo-com-dbt)
10. [Qualidade e testes](#10-qualidade-e-testes)
11. [Power BI — conectar ao BigQuery](#11-power-bi--conectar-ao-bigquery)
12. [Referência rápida de comandos](#12-referência-rápida-de-comandos)
13. [Troubleshooting](#13-troubleshooting)
14. [Onde está o quê](#14-onde-está-o-quê)

---

## 1. Arquitetura em um olhar

```
┌─────────────────────────────────────────────────────────────────────┐
│  FONTE: Supabase (PostgreSQL · southamerica-east1)                  │
│  8 schemas · 28 tabelas · ~5,9 M linhas · dados sintéticos         │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ Python psycopg2 · incremental updated_at
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  BRONZE: Google Cloud Storage                                       │
│  gs://jstechstore-bronze/                                           │
│  Parquet · Snappy · particionado por data de ingestão               │
│  Watermarks em gs://jstechstore-bronze/.watermarks/                 │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ BigQuery External Tables
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  SILVER: BigQuery · jstechstore_silver                              │
│  28 stg models + 3 int models · incremental · dedup por chave natural│
└──────────────────────────────┬──────────────────────────────────────┘
                               │ dbt-bigquery
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  GOLD: BigQuery · jstechstore_gold                                  │
│  10 dimensões · 6 fatos · Esquema Estrela                           │
│  SCD Type 2 em dim_cliente, dim_produto, dim_vendedor, dim_loja     │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ Conector BigQuery nativo
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  POWER BI: 6 dashboards executivos                                  │
│  Import Mode · Incremental Refresh em fato_venda                   │
│  Sem ODBC · Sem On-premises Gateway                                 │
└─────────────────────────────────────────────────────────────────────┘
```

**Referências:**
- Arquitetura completa: `docs/arquitetura/arquitetura_v2_bigquery.md`
- Modelagem dimensional (dims + fatos): `docs/PRD_JSTechStore_Brasil_DataEngineering.md` §6

---

## 2. Pré-requisitos de ferramentas

Instale antes de começar:

| Ferramenta | Versão mínima | Como instalar | Verificar |
|-----------|--------------|---------------|-----------|
| Python | 3.12 | [python.org](https://python.org/downloads) | `python --version` |
| Git | 2.40+ | [git-scm.com](https://git-scm.com) | `git --version` |
| gcloud CLI | Mais recente | [cloud.google.com/sdk](https://cloud.google.com/sdk/docs/install) | `gcloud --version` |
| Power BI Desktop | Set/2025+ | [Microsoft Store](https://aka.ms/pbidesktopstore) | (só se trabalhar com dashboards) |

> **Não precisa instalar:** DuckDB, DuckDB ODBC Driver, On-premises Data Gateway — esses são artefatos da arquitetura v1 que não existem mais.

---

## 3. Contas e acessos necessários

Solicite acesso às seguintes plataformas antes de começar:

### 3.1 Supabase (fonte de dados)

**O que é:** banco PostgreSQL cloud com os dados sintéticos da JSTechStore.

**O que você precisa:**
- Connection string no formato `postgresql://postgres:<senha>@<project>.supabase.co:5432/postgres`
- Solicitar ao tech lead ou acessar: Supabase Dashboard → Project → Settings → Database → URI

**Onde vai:** variável `SUPABASE_DB_URL` no seu `.env` local.

### 3.2 Google Cloud Platform (GCP)

**O que é:** onde vivem os dados — GCS (Bronze) e BigQuery (Silver + Gold).

**O que você precisa:**
- Acesso ao projeto GCP `jstechstore-data` (solicitar ao tech lead)
- Ou: permissão de Viewer no BigQuery para consultas de leitura
- Para desenvolvimento completo: role `BigQuery Data Editor` + `Storage Object Admin`

**Autenticação local:**

```bash
# Login com sua conta Google (para uso local/desenvolvimento)
gcloud auth application-default login

# Verificar projeto ativo
gcloud config set project jstechstore-data
gcloud config list
```

**Para rodar o pipeline completo localmente**, você também precisa de uma chave de Service Account (JSON). Solicitar ao tech lead e salvar em local seguro — **nunca commitar**.

### 3.3 GitHub

**O que é:** repositório do projeto + GitHub Actions (orquestração do pipeline diário).

**O que você precisa:**
- Acesso de leitura ao repositório para desenvolvimento
- Acesso de escrita para abrir PRs
- A execução do pipeline é automática via Actions — não precisa de permissão especial para isso

**Secrets configurados no repositório** (apenas tech leads configuram):

| Secret | Descrição |
|--------|-----------|
| `SUPABASE_DB_URL` | Connection string do Supabase |
| `GCP_SA_KEY` | Chave JSON da Service Account (base64) |
| `GCP_PROJECT_ID` | ID do projeto GCP |
| `GCS_BUCKET` | Nome do bucket Bronze (`jstechstore-bronze`) |

### 3.4 Power BI (somente se for trabalhar com dashboards)

**O que é:** ferramenta de BI para os 6 dashboards executivos.

**O que você precisa:**
- Licença Power BI Pro ou Premium Per User (PPU) — solicitar ao gestor
- Conta organizacional (preferencialmente `dados@jstechstore.com.br`)
- **Não é necessário** instalar ODBC Driver nem Data Gateway — a v2 usa o conector BigQuery nativo

---

## 4. Setup do ambiente local

### 4.1 Clonar o repositório

```bash
git clone https://github.com/<org>/jstechstore-data-engineering.git
cd jstechstore-data-engineering
```

### 4.2 Criar e ativar ambiente virtual

```bash
# Windows (PowerShell)
python -m venv .venv
.venv\Scripts\Activate.ps1

# Linux / macOS
python -m venv .venv
source .venv/bin/activate
```

> Após ativar, o prompt deve mostrar `(.venv)` no início. Sempre trabalhe com o venv ativado.

### 4.3 Instalar dependências

```bash
pip install -r requirements.txt
```

Principais pacotes instalados:

| Pacote | Para que serve |
|--------|---------------|
| `psycopg2-binary` | Conector PostgreSQL → Supabase |
| `pandas` + `pyarrow` | Manipulação de DataFrames e Parquet |
| `google-cloud-storage` | Upload/download GCS (Bronze) |
| `google-cloud-bigquery` | Queries e DML no BigQuery (scripts de qualidade) |
| `dbt-core` + `dbt-bigquery` | Transformações SQL (Silver + Gold) |
| `faker[pt_BR]` | Geração de dados sintéticos |
| `ruff` | Linting e formatação Python |
| `pytest` | Testes unitários |

### 4.4 Copiar e preencher o .env

```bash
cp .env.example .env
# Editar .env com seus valores reais
```

> O arquivo `.env` nunca vai para o Git (está no `.gitignore`). Cada pessoa tem o seu próprio.

---

## 5. Configurar variáveis de ambiente

Edite o `.env` com os valores reais. Veja cada variável:

```bash
# ── Supabase ──────────────────────────────────────────────────
# Connection string do PostgreSQL no Supabase
SUPABASE_DB_URL=postgresql://postgres:SUA_SENHA@SEU_PROJECT.supabase.co:5432/postgres

# ── GCP ───────────────────────────────────────────────────────
# ID do projeto GCP (sem aspas)
GCP_PROJECT_ID=jstechstore-data

# Nome do bucket GCS com os dados Bronze
GCS_BUCKET=jstechstore-bronze

# Chave da Service Account — duas opções:
# Opção A: caminho para o arquivo JSON (desenvolvimento local)
GCP_SA_KEY_JSON=/Users/voce/secrets/jstechstore-sa-key.json

# Opção B: conteúdo JSON inline (produção/GitHub Actions — não recomendado para local)
# GCP_SA_KEY_JSON={"type":"service_account","project_id":"jstechstore-data",...}

# ── BigQuery ───────────────────────────────────────────────────
BQ_DATASET_GOLD=jstechstore_gold
BQ_DATASET_SILVER=jstechstore_silver
BQ_DATASET_BRONZE_EXT=jstechstore_bronze_ext
BQ_LOCATION=southamerica-east1

# ── LGPD ──────────────────────────────────────────────────────
# Salt secreto para HMAC em dados sensíveis (se aplicável)
LGPD_HMAC_SALT=gere-uma-string-aleatoria-longa-aqui
```

> **dbt não lê o `.env` automaticamente.** Antes de rodar qualquer comando `dbt`, as variáveis precisam estar no ambiente do shell. Veja como na [seção 9](#9-desenvolvendo-com-dbt).

### Autenticação GCP para desenvolvimento local

Se você usou `gcloud auth application-default login`, não precisa de `GCP_SA_KEY_JSON` para consultas simples no BigQuery. Mas para o `extract.py` e o `dbt run` completo, a Service Account é necessária. Siga o padrão abaixo:

```powershell
# PowerShell — antes de rodar extract.py ou dbt
$env:GOOGLE_APPLICATION_CREDENTIALS = "C:\caminho\para\jstechstore-sa-key.json"
```

```bash
# Linux / macOS
export GOOGLE_APPLICATION_CREDENTIALS="/home/voce/secrets/jstechstore-sa-key.json"
```

---

## 6. Verificar que tudo está funcionando

Execute esta sequência de verificações antes de fazer qualquer coisa:

```bash
# 1. Python e dependências
python --version                    # Python 3.12.x
pip list | grep -E "dbt|google|psycopg"

# 2. Conexão com Supabase
python -c "
import os, psycopg2
from dotenv import load_dotenv
load_dotenv()
conn = psycopg2.connect(os.environ['SUPABASE_DB_URL'])
print('Supabase OK —', conn.server_version)
conn.close()
"

# 3. Conexão com GCS
python -c "
from google.cloud import storage
client = storage.Client()
bucket = client.bucket('jstechstore-bronze')
print('GCS OK — bucket exists:', bucket.exists())
"

# 4. Conexão com BigQuery
python -c "
from google.cloud import bigquery
client = bigquery.Client(project='jstechstore-data')
datasets = [d.dataset_id for d in client.list_datasets()]
print('BigQuery OK — datasets:', datasets)
"

# 5. dbt debug (na pasta do projeto dbt)
cd transformation/dbt_project
dbt debug --profiles-dir .
```

Se alguma verificação falhar, veja a [seção de troubleshooting](#13-troubleshooting).

---

## 7. Primeira execução completa

> **Atenção:** a carga inicial gera ~5,9 M de linhas no Supabase e ~165 MB no GCS. Rodar do zero demora ~30–60 minutos. Em ambientes de desenvolvimento, trabalhe sempre com a carga já existente.

Se o projeto já está inicializado (caso mais comum), pule para o passo 3.

### Passo 1 — Gerar dados históricos no Supabase (apenas na 1ª vez)

```bash
# Gera 3 anos de dados sintéticos (2023-07-21 → 2026-07-20)
python scripts/generate_data.py --start-date 2023-07-21 --end-date 2026-07-20 --seed 42
```

Duração: ~30–45 minutos. Popula ~5,9 M linhas em 28 tabelas.

### Passo 2 — Ingestão Bronze completa para o GCS

```bash
# Extrai tudo do Supabase e envia para gs://jstechstore-bronze/
python -m ingestion.connectors.postgres.extract --mode full
```

Duração: ~10–20 minutos. Gera ~43 arquivos Parquet particionados.

### Passo 3 — Criar External Tables no BigQuery

```bash
cd transformation/dbt_project

# Instalar pacotes dbt
dbt deps

# Criar as 28 External Tables que apontam para o GCS
dbt run-operation stage_external_sources
```

As External Tables são criadas no dataset `jstechstore_bronze_ext`. Elas não copiam dados — apenas registram a localização dos Parquet no GCS como tabelas consultáveis.

### Passo 4 — Primeiro dbt run (full-refresh)

```bash
# Rebuild completo: Silver + Gold a partir do Bronze
dbt seed --select feriados_nacionais
dbt run --full-refresh
```

Duração: ~15–30 minutos (processando 3 anos de histórico). Nas execuções seguintes (incrementais), será ~1–3 minutos.

### Passo 5 — Validar

```bash
# Testes de qualidade (deve retornar 80/80 passando)
dbt test --select gold

# Reconciliação com a fonte
python quality/reconciliation/reconcile_gold_vs_source.py
```

---

## 8. Pipeline diário — o que acontece automaticamente

O GitHub Actions executa o pipeline todo dia às **04:00 UTC (01:00 BRT)**. Você não precisa fazer nada — mas é útil entender o que acontece:

```
04:00 UTC — Cron dispara
│
├── Setup
│   ├── Python 3.12 + pip install -r requirements.txt
│   └── Autenticação GCP (google-github-actions/auth com GCP_SA_KEY)
│
├── Step 1 · Geração de dados do dia
│   └── python scripts/generate_daily.py --date today
│       (insere ~2.000 vendas + entregas + lançamentos no Supabase)
│
├── Step 2 · Ingestão Bronze → GCS
│   └── python -m ingestion.connectors.postgres.extract --mode smart
│       (só extrai registros novos desde o último watermark)
│
├── Step 3 · dbt transformações
│   ├── dbt seed --select feriados_nacionais
│   ├── dbt run-operation stage_external_sources
│   └── dbt run   (incremental — processa apenas dados novos)
│
├── Step 4 · dbt test --select gold
│   (80/80 testes precisam passar para continuar)
│
├── Step 5 · Verificação de frescor
│   └── python quality/monitoring/check_data_freshness.py --tolerance-hours 26
│
├── Step 6 · Reconciliação Gold vs. Supabase
│   └── python quality/reconciliation/reconcile_gold_vs_source.py
│       (6 tabelas fato · tolerância ≤ 0,1%)
│
└── Notificação em caso de falha (GitHub notification)
```

### Checar status do pipeline

Acesse: **GitHub → Repositório → Actions → Daily Pipeline JSTechStore**

Você verá o histórico de execuções com status (✅ / ❌) e duração de cada step.

### Disparar manualmente (workflow_dispatch)

```
GitHub → Actions → Daily Pipeline JSTechStore → Run workflow
  ├── full_refresh: false   → incremental normal
  └── full_refresh: true    → rebuild completo (Gold do zero)
                              (pula generate_daily, usa --mode full na extração)
```

Use `full_refresh=true` quando houver mudança estrutural nos modelos Gold ou após corrigir bugs que afetam dados históricos.

---

## 9. Desenvolvendo com dbt

### Setup obrigatório antes de qualquer comando dbt

```powershell
# PowerShell — setar variáveis no ambiente do shell (dbt não lê .env)
$env:GCP_PROJECT_ID     = "jstechstore-data"
$env:GCS_BUCKET         = "jstechstore-bronze"
$env:GCP_SA_KEY_JSON    = Get-Content "C:\caminho\para\jstechstore-sa-key.json" -Raw
$env:BQ_DATASET_GOLD    = "jstechstore_gold"

# Navegar para a pasta do projeto dbt
Set-Location "Z:\Projetos_Engenharia_Analitycs\JSTechStore\transformation\dbt_project"
```

```bash
# Linux / macOS
export GCP_PROJECT_ID=jstechstore-data
export GCS_BUCKET=jstechstore-bronze
export GCP_SA_KEY_JSON=$(cat /path/to/jstechstore-sa-key.json)
export BQ_DATASET_GOLD=jstechstore_gold

cd transformation/dbt_project
```

### Comandos do dia a dia

```bash
# Instalar/atualizar pacotes dbt
dbt deps

# Sincronizar External Tables (rodar após alterar sources.yml ou novo Parquet no GCS)
dbt run-operation stage_external_sources

# Rodar todos os modelos (incremental)
dbt run

# Rodar uma camada específica
dbt run --select bronze
dbt run --select silver
dbt run --select gold

# Rodar um modelo específico
dbt run --select fato_venda
dbt run --select dim_cliente

# Rodar modelo e todos que dependem dele
dbt run --select fato_venda+

# Rodar modelo e todas as suas dependências
dbt run --select +fato_venda

# Full refresh (rebuild completo — use com moderação)
dbt run --full-refresh
dbt run --full-refresh --select dim_tempo   # só dim_tempo

# Testes
dbt test                        # todos os modelos
dbt test --select gold          # só Gold
dbt test --select fato_venda    # modelo específico

# Compilar sem executar (útil para verificar SQL gerado)
dbt compile --select fato_venda
# SQL gerado fica em: target/compiled/jstechstore/models/gold/facts/fato_venda.sql

# Documentação local
dbt docs generate && dbt docs serve
# Abre browser em http://localhost:8080
```

### Estrutura de modelos dbt

```
transformation/dbt_project/models/
│
├── bronze/                              # Camada 1: staging do GCS
│   ├── sources.yml                      # Declara 28 External Tables no BQ
│   ├── stg_vendas__pedidos.sql          # stg_<schema>__<tabela>.sql
│   ├── stg_vendas__itens_pedido.sql
│   └── ... (28 arquivos)
│
├── silver/                              # Camada 2: regras de negócio
│   ├── int_clientes__unificados.sql     # int_<dominio>__<entidade>.sql
│   ├── int_vendas__pedidos_unificados.sql
│   └── int_produtos__catalogo.sql
│
└── gold/                                # Camada 3: Esquema Estrela
    ├── dimensions/
    │   ├── dim_tempo.sql
    │   ├── dim_cliente.sql
    │   └── ... (10 dimensões)
    └── facts/
        ├── fato_venda.sql
        └── ... (6 fatos)
```

### Como criar um novo modelo

1. Criar o arquivo `.sql` na pasta correta seguindo o padrão de nomenclatura
2. Declarar `{{ config(materialized='incremental', unique_key='...') }}`
3. Adicionar à `schema.yml` com testes `not_null`, `unique`, `relationships`
4. Rodar `dbt run --select novo_modelo` e depois `dbt test --select novo_modelo`

### BigQuery — diferenças importantes vs DuckDB (v1)

| Aspecto | DuckDB (v1) | BigQuery (v2) |
|---------|------------|--------------|
| Casting | `valor::INTEGER` | `CAST(valor AS INT64)` |
| Tipo texto | `VARCHAR` | `STRING` |
| Tipo número | `INTEGER` | `INT64` |
| Tipo booleano | `BOOLEAN` | `BOOL` |
| Intervalo | `INTERVAL '3 days'` | `INTERVAL 3 DAY` |
| Séries de data | `GENERATE_SERIES(d1, d2, INTERVAL '1 day')` | `GENERATE_DATE_ARRAY(d1, d2, INTERVAL 1 DAY)` |
| Formato data | `STRFTIME(date, '%Y%m%d')` | `FORMAT_DATE('%Y%m%d', date)` |
| Dia da semana | `EXTRACT(DOW)` → 0=Dom | `EXTRACT(DAYOFWEEK)` → **1=Dom** |
| Subtração datas | `(d1 - d2)::INTEGER` | `DATE_DIFF(d1, d2, DAY)` |
| MD5 | `MD5(str)` → STRING | `TO_HEX(MD5(str))` (MD5 retorna BYTES no BQ) |
| Sem giro | `post_hook: "ANALYZE {{ this }}"` | Remover (BQ não suporta) |

> Para a lista completa, veja `docs/migração/plano_migracao_bigquery_gcs.md` §4.

---

## 10. Qualidade e testes

### Testes dbt (automáticos no pipeline)

```bash
# Rodar todos os testes
dbt test

# Por camada
dbt test --select gold    # deve retornar 80/80

# Por modelo
dbt test --select fato_venda
dbt test --select dim_cliente
```

Cada modelo Gold tem testes de `not_null`, `unique`, `accepted_values` e `relationships` declarados no `schema.yml`.

### Reconciliação Gold vs. Supabase

Compara totais do BigQuery com a fonte Supabase. Tolerância de desvio: **≤ 0,1%**.

```bash
python quality/reconciliation/reconcile_gold_vs_source.py

# Saída esperada:
# [fato_venda] OK | BQ: 1.234.567 | Supabase: 1.234.589 | desvio: 0.002%
# [fato_estoque] OK | ...
```

### Verificação de frescor

Verifica se os dados do dia anterior já chegaram ao Gold.

```bash
python quality/monitoring/check_data_freshness.py --tolerance-hours 26
```

### Testes unitários Python

```bash
# Na raiz do projeto
pytest tests/ -v

# Módulo específico
pytest tests/ingestion/ -v
```

### LGPD — simulação de exclusão de titular

```bash
# Dry-run (mostra o que seria excluído sem alterar nada)
python quality/lgpd/exclusao_titular.py --cpf_hash <hash> --dry-run

# Executar exclusão
python quality/lgpd/exclusao_titular.py --cpf_hash <hash> --execute
```

---

## 11. Power BI — conectar ao BigQuery

> Nenhuma instalação adicional necessária além do Power BI Desktop. Sem ODBC, sem Gateway.

### Primeira conexão

1. Abrir **Power BI Desktop**
2. Clicar em **Obter Dados** → pesquisar **Google BigQuery** → Conectar
3. Informar:
   - **Project ID:** `jstechstore-data`
   - Autenticação: **Conta Organizacional** → entrar com sua conta Google (que tem acesso ao projeto GCP)
4. No navegador, expandir `jstechstore_gold` e selecionar as tabelas:
   - Todas as `dim_*` (10 tabelas)
   - Todas as `fato_*` (6 tabelas)
5. Clicar em **Carregar**

### Configurar Incremental Refresh em `fato_venda`

Antes de publicar no Service, configure o Incremental Refresh:

1. Na Power Query, criar dois parâmetros M:
   ```m
   // RangeStart — tipo DateTime (obrigatório)
   #"RangeStart" = #datetime(2024, 1, 1, 0, 0, 0)
       meta [IsParameterQuery=true, Type="DateTime", IsParameterQueryRequired=true]

   // RangeEnd — tipo DateTime (obrigatório)
   #"RangeEnd" = #datetime(2026, 12, 31, 23, 59, 59)
       meta [IsParameterQuery=true, Type="DateTime", IsParameterQueryRequired=true]
   ```

2. Na query de `fato_venda`, adicionar filtro por `dt_pedido_data`:
   ```m
   Table.SelectRows(fato_venda_src, each
       [dt_pedido_data] >= RangeStart and [dt_pedido_data] < RangeEnd
   )
   ```

3. Clicar com o botão direito em `fato_venda` → **Atualização Incremental**:
   - Arquivar dados com mais de: **2 anos**
   - Atualizar dados dos últimos: **3 dias**

### Publicar e configurar refresh automático

1. Power BI Desktop → **Publicar** → selecionar workspace
2. No Power BI Service → Dataset → **Configurações** → **Atualização Agendada**
   - Frequência: Diária
   - Horário: **05:30 BRT** (após o pipeline GHA concluir ~05:00)
   - Fuso: `(UTC-03:00) Brasília`
   - Não é necessário configurar gateway

---

## 12. Referência rápida de comandos

### Ingestão

```bash
# Incremental (dia a dia)
python -m ingestion.connectors.postgres.extract --mode smart

# Full load (sem watermark — pega tudo)
python -m ingestion.connectors.postgres.extract --mode full

# Tabela específica
python -m ingestion.connectors.postgres.extract --mode incremental --table vendas.pedidos
```

### GCS

```bash
# Listar arquivos Bronze de uma tabela
gsutil ls gs://jstechstore-bronze/vendas/pedidos/**

# Verificar último watermark de uma tabela
gsutil cat gs://jstechstore-bronze/.watermarks/vendas__pedidos.json

# Tamanho total do bucket
gsutil du -sh gs://jstechstore-bronze/

# Copiar arquivo do GCS para local (para inspeção)
gsutil cp gs://jstechstore-bronze/vendas/pedidos/.../batch_040012.parquet /tmp/
```

### BigQuery

```bash
# Query rápida via bq CLI
bq query --nouse_legacy_sql \
  'SELECT COUNT(*) as total FROM `jstechstore-data.jstechstore_gold.fato_venda`'

# Última data disponível no Gold
bq query --nouse_legacy_sql \
  'SELECT MAX(dt_pedido_data) FROM `jstechstore-data.jstechstore_gold.fato_venda`'

# Time Travel — como estavam os dados 24h atrás
bq query --nouse_legacy_sql \
  'SELECT COUNT(*) FROM `jstechstore-data.jstechstore_gold.fato_venda`
   FOR SYSTEM_TIME AS OF TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)'
```

### dbt (ver também [seção 9](#9-desenvolvendo-com-dbt))

```bash
cd transformation/dbt_project

dbt deps                                    # instalar pacotes
dbt run-operation stage_external_sources    # sincronizar External Tables
dbt run                                     # incremental
dbt run --full-refresh                      # rebuild completo
dbt run --select fato_venda                 # modelo específico
dbt test --select gold                      # testes Gold
dbt compile --select fato_venda             # ver SQL compilado
dbt docs generate && dbt docs serve         # documentação local
```

### Geração de dados

```bash
# Dados do dia (gerado automaticamente pelo GHA)
python scripts/generate_daily.py --date today

# Data específica (backfill)
python scripts/generate_daily.py --date 2026-08-10

# Carga completa 3 anos (roda apenas 1× na inicialização)
python scripts/generate_data.py --start-date 2023-07-21 --end-date 2026-07-20 --seed 42
```

---

## 13. Troubleshooting

### ❌ `dbt debug` falha com "Connection error"

**Causa:** variáveis GCP não estão no ambiente do shell.

**Solução:**
```powershell
# PowerShell — rodar antes de qualquer dbt
$env:GCP_PROJECT_ID  = "jstechstore-data"
$env:GCP_SA_KEY_JSON = Get-Content "C:\caminho\para\key.json" -Raw
```

---

### ❌ `google.auth.exceptions.DefaultCredentialsError`

**Causa:** credenciais GCP não configuradas.

**Solução:**
```bash
# Opção A: Application Default Credentials (uso interativo)
gcloud auth application-default login

# Opção B: Service Account explícita
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/key.json"
```

---

### ❌ `dbt run` falha com `403 Access Denied`

**Causa:** a Service Account não tem permissão no dataset ou bucket.

**Verificar:**
```bash
# Checar permissões da SA no BQ
gcloud projects get-iam-policy jstechstore-data \
  --flatten="bindings[].members" \
  --filter="bindings.members:dbt-runner@"
```

**Solução:** solicitar ao tech lead que adicione as roles `BigQuery Data Editor` e `BigQuery Job User` à Service Account.

---

### ❌ `No such table: jstechstore_bronze_ext.vendas__pedidos`

**Causa:** External Tables não foram criadas ou sincronizadas.

**Solução:**
```bash
cd transformation/dbt_project
dbt run-operation stage_external_sources
```

---

### ❌ `extract.py` não encontra novos registros (0 linhas extraídas)

**Causa A:** watermark está na frente dos dados — o Supabase não tem dados mais novos que o último watermark.

**Verificar:**
```bash
gsutil cat gs://jstechstore-bronze/.watermarks/vendas__pedidos.json
# Comparar com MAX(updated_at) no Supabase:
python -c "
import os, psycopg2; from dotenv import load_dotenv; load_dotenv()
conn = psycopg2.connect(os.environ['SUPABASE_DB_URL'])
cur = conn.cursor()
cur.execute('SELECT MAX(updated_at) FROM vendas.pedidos')
print('MAX updated_at:', cur.fetchone()[0])
conn.close()
"
```

**Causa B:** `generate_daily.py` não rodou hoje.

**Solução:** rodar manualmente: `python scripts/generate_daily.py --date today`

---

### ❌ dbt test falha com `Assertion failed` ou contagem errada

**Causa provável:** incremental com dados desatualizados, ou bug introduzido num modelo.

**Diagnóstico:**
```bash
# Ver detalhes do teste que falhou
dbt test --select nome_do_modelo --store-failures

# Full refresh do modelo problemático
dbt run --full-refresh --select nome_do_modelo
dbt test --select nome_do_modelo
```

---

### ❌ Pipeline GHA falha no Step 3 (dbt run)

**Verificar:**
1. GitHub → Actions → run com falha → expandir o step com ❌
2. Procurar por `DatabaseException` ou `403` no log
3. Se `403`: verificar que o secret `GCP_SA_KEY` está válido e não expirou
4. Se `Table not found`: External Tables precisam ser ressincronizadas (passo `stage_external_sources`)

---

### ❌ Power BI: "Falha ao carregar dados do BigQuery"

**Causa A:** conta Google sem permissão no projeto.

**Solução:** solicitar ao tech lead acesso `BigQuery Data Viewer` no projeto `jstechstore-data`.

**Causa B:** dataset `jstechstore_gold` não existe (pipeline ainda não rodou).

**Solução:** verificar se o pipeline GHA foi executado com sucesso pelo menos uma vez.

---

## 14. Onde está o quê

### Dados

| O que | Onde |
|-------|------|
| Dados fonte (OLTP) | Supabase → PostgreSQL schemas: `vendas`, `clientes`, `produtos`, `estoque`, `logistica`, `financeiro`, `marketing`, `rh` |
| Bronze (Parquet raw) | `gs://jstechstore-bronze/` |
| Watermarks de ingestão | `gs://jstechstore-bronze/.watermarks/` |
| External Tables (BQ) | `jstechstore_bronze_ext.*` |
| Silver (intermediário) | `jstechstore_silver.*` |
| Gold (Esquema Estrela) | `jstechstore_gold.*` |

### Código

| O que | Onde |
|-------|------|
| Geração de dados sintéticos | `scripts/generate_data.py`, `scripts/generate_daily.py` |
| Ingestão Supabase → GCS | `ingestion/connectors/postgres/extract.py` |
| Configuração das tabelas | `ingestion/connectors/postgres/config.py` |
| Modelos dbt Bronze | `transformation/dbt_project/models/bronze/stg_*.sql` |
| External Table sources | `transformation/dbt_project/models/bronze/sources.yml` |
| Modelos dbt Silver | `transformation/dbt_project/models/silver/int_*.sql` |
| Modelos dbt Gold | `transformation/dbt_project/models/gold/` |
| Macros dbt | `transformation/dbt_project/macros/` |
| Testes schema | `transformation/dbt_project/models/**/schema.yml` |
| Pipeline GHA | `.github/workflows/daily_pipeline.yml` |
| CI (testes em PRs) | `.github/workflows/ci_dbt_tests.yml` |
| Reconciliação | `quality/reconciliation/reconcile_gold_vs_source.py` |
| Frescor | `quality/monitoring/check_data_freshness.py` |
| LGPD | `quality/lgpd/exclusao_titular.py` |

### Documentação

| O que | Onde |
|-------|------|
| **Este guia** | `docs/onboarding/onboarding_v2_bigquery.md` |
| PRD completo do projeto | `docs/PRD_JSTechStore_Brasil_DataEngineering.md` |
| Arquitetura v2 detalhada | `docs/arquitetura/arquitetura_v2_bigquery.md` |
| Plano de migração v1→v2 | `docs/migração/plano_migracao_bigquery_gcs.md` |
| Dicionário de métricas Power BI | `docs/dicionario_dados/metricas_powerbi.md` |
| Gabarito de validação Power BI | `docs/dicionario_dados/gabarito_validacao_powerbi.md` |
| LGPD — RIPD | `docs/lgpd/RIPD_JSTechStore.md` |
| Contas e acessos (v1 — referência histórica) | `docs/onboarding/contas_e_acessos.md` |

---

## Checklist de onboarding

```
[ ] Ferramentas instaladas: Python 3.12, Git, gcloud CLI
[ ] Acesso ao repositório GitHub confirmado
[ ] Acesso ao projeto GCP jstechstore-data confirmado
[ ] .env preenchido com SUPABASE_DB_URL, GCP_PROJECT_ID, GCS_BUCKET, GCP_SA_KEY_JSON
[ ] Verificações da seção 6 passando (Supabase OK, GCS OK, BigQuery OK, dbt debug OK)
[ ] Primeiro dbt run incremental executado com sucesso
[ ] dbt test --select gold: 80/80 passando
[ ] Power BI Desktop conectado ao jstechstore_gold (se aplicável)
[ ] Pipeline GHA visto rodando na aba Actions (ao menos 1 execução ✅)
```

---

*Dúvidas? Abrir uma issue no GitHub ou contatar o tech lead via e-mail.*
