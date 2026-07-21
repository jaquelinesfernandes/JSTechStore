# PRD — Projeto de Engenharia de Dados: JSTechStore Brasil

**Versão:** 3.0  
**Data:** 2026-07-21  
**Status:** Aprovado  
**Responsável:** Equipe de Engenharia de Dados

| Versão | Data | Mudança |
|--------|------|---------|
| 1.0 | 2026-07-20 | Versão inicial |
| 2.0 | 2026-07-20 | Fonte unificada em SQL Server Cloud; stack definida (DuckDB, OpenMetadata, Power BI Pro); volumetria; LGPD mínima; modelagem dimensional revisada |
| 3.0 | 2026-07-21 | **Simplificação de stack:** fonte migrada para Supabase (PostgreSQL); orquestração via GitHub Actions; armazenamento Bronze/Silver em Parquet local; remoção de Airflow, OpenMetadata e Great Expectations; adição de geração de dados sintéticos (3 anos histórico + incremental diário); Power BI com Incremental Refresh |

---

## 1. Sumário Executivo

A JSTechStore Brasil, rede varejista omnichannel com 15 lojas físicas, e-commerce próprio, centro de distribuição e programa de fidelidade, necessita de uma plataforma centralizada de dados para apoiar a tomada de decisão nas áreas Comercial, Clientes, Produtos, Logística, Financeiro e Marketing.

Este projeto entrega uma **plataforma de dados moderna e simplificada** com arquitetura Medallion (Bronze → Silver → Gold), modelagem dimensional (Esquema Estrela) e dashboards executivos no Power BI Pro. A fonte de dados é um banco **Supabase (PostgreSQL)** populado com dados sintéticos gerados por script Python, simulando 3 anos de operação real.

### Objetivos de Negócio

| # | Objetivo | KPI de Sucesso |
|---|----------|----------------|
| 1 | Unificar visão de vendas físicas e online | Dashboard Comercial disponível diariamente com D-1 |
| 2 | Entender comportamento e rentabilidade de clientes | Segmentação RFM operacional com cohort analysis |
| 3 | Otimizar estoque e giro de produtos | Redução de 15% em ruptura de estoque |
| 4 | Monitorar SLAs de entrega e logística | OTD e Ship from Store visíveis no dashboard de logística |
| 5 | Controlar margem e receita por canal | P&L por canal com < 24h de defasagem |
| 6 | Medir eficácia de campanhas de marketing | ROI de campanha por segmento com atribuição definida |

---

## 2. Contexto do Negócio

### 2.1 Perfil da Empresa

**JSTechStore Brasil** é uma rede varejista especializada em tecnologia com operação omnichannel:

- **Produtos:** Informática (notebooks, desktops, componentes), Smartphones & Tablets, Games (consoles, jogos, acessórios), TVs & Áudio, Periféricos (teclados, mouses, headsets, webcams)
- **Canais de venda:** 15 Lojas Físicas (regiões: Sul, Sudeste, Centro-Oeste) + E-commerce (site próprio + marketplaces: Mercado Livre, Amazon, Shopee)
- **Infraestrutura:** 1 Centro de Distribuição (CD) central + modalidade Ship from Store (SFS)
- **Programa de Fidelidade:** TechPoints — acúmulo e resgate de pontos por compra, níveis Bronze/Silver/Gold/Platinum

### 2.2 Fonte de Dados

Toda a operação da JSTechStore Brasil é consolidada em **um único banco de dados Supabase (PostgreSQL)** — cloud-hosted, gratuito para o volume deste projeto. O banco é populado com dados sintéticos gerados por script Python que simula 3 anos de operação real.

| Schema / Módulo | Dados Principais |
|-----------------|-----------------|
| `vendas` | Pedidos, itens de pedido, devoluções, trocas |
| `clientes` | Cadastro, endereços, programa de fidelidade (TechPoints) |
| `produtos` | Cadastro de SKUs, categorias, preços, fornecedores |
| `estoque` | Saldo por loja/CD, movimentações, reservas |
| `logistica` | Entregas, transportadoras, modalidades, rastreamento |
| `financeiro` | Lançamentos, parcelamentos, contas a receber, DRE, orçamentos mensais por canal/loja |
| `marketing` | Campanhas, leads, atribuição de canal |
| `rh` | Vendedores, metas, comissões |
| `web_analytics` | Sessões de usuário (visitas, origem, duração), eventos de carrinho (add, abandon, checkout) — fonte de `fato_cliente_interacao` |

> **Premissa confirmada:** acesso via string de conexão PostgreSQL ao Supabase Cloud. Controle incremental por coluna `updated_at` em todas as tabelas transacionais (índice criado pelo script de setup).

### 2.3 Problemas Simulados (contexto do projeto)

- Relatórios manuais em Excel com dados defasados (D-3 a D-7)
- Silos de informação entre áreas comercial, logística e financeiro
- Sem visão unificada do cliente entre loja física e e-commerce
- Sem métricas consolidadas de margem por canal, produto e campanha
- Tomada de decisão baseada em intuição, não em dados

### 2.4 Volumetria Estimada

| Métrica | Valor | Observação |
|---------|-------|-----------|
| Transações de venda/dia | 2.000 | Físico + online combinados |
| Pedidos/mês | 60.000 | Média anual |
| Itens por pedido (média) | 3,2 | Mix de categorias |
| Histórico inicial gerado | 3 anos | Script `generate_data.py` — carga full na Fase 1 |
| Geração incremental | ~2.000 vendas/dia | Script `generate_daily.py` — roda via GitHub Actions |
| Crescimento anual esperado | 15% | Expansão de lojas + e-commerce |
| Volume Supabase (PostgreSQL) | ~1–2 GB | Banco transacional simulado |
| Volume Bronze (3 anos, Parquet) | ~2 GB | Parquet particionado por data de ingestão |
| Volume Silver (Parquet) | ~1,2 GB | Parquet limpo e conformado |
| Volume Gold (DuckDB) | ~700 MB | Esquema Estrela no DuckDB |

**Projeção de crescimento do Gold layer:**

| Ano | Volume Estimado Gold | Adequação ao Power BI (limite 1 GB dataset) |
|-----|---------------------|------------------------------------------------|
| Ano 0 (base) | 700 MB | OK |
| Ano 1 (+15%) | ~805 MB | OK |
| Ano 2 (+15%) | ~926 MB | OK — margem estreita |
| Ano 3 (+15%) | ~1,06 GB | Revisar agregações Gold ou ativar Incremental Refresh no PBI |

> **Ação preventiva no Ano 2:** revisar agregações na camada Gold para manter dataset abaixo de 900 MB. O Power BI Incremental Refresh na `fato_venda` mitiga o problema ao carregar apenas dados novos.

---

## 3. Escopo do Projeto

### 3.1 Dentro do Escopo

- Geração de dados sintéticos no Supabase PostgreSQL (histórico 3 anos + incremental diário)
- Ingestão incremental Bronze a partir do Supabase (Python + psycopg2 + SQLAlchemy)
- Construção do Data Warehouse com arquitetura Medallion (3 camadas) em Parquet + DuckDB
- Modelagem dimensional com Esquema Estrela — 10 dimensões + 6 tabelas fato (dbt)
- 6 dashboards executivos no Power BI (1 por área) com Incremental Refresh
- Requisitos mínimos de LGPD (pseudonimização, exclusão, registro de atividades)
- Orquestração via GitHub Actions (cron diário para geração de dados + pipeline)
- Documentação técnica e de negócio

### 3.2 Fora do Escopo (versão atual)

- Machine Learning / Modelos preditivos (planejado para Fase 4)
- Integração com APIs externas reais (redes sociais, marketplaces)
- Data streaming em tempo real (latência < 5 min)
- Catálogo de dados (OpenMetadata removido da stack)
- Great Expectations (substituído por testes dbt)
- Apache Airflow (substituído por GitHub Actions)
- Self-service BI para usuários finais (planejado para Fase 4)

---

## 4. Arquitetura Técnica

### 4.1 Visão Geral — Arquitetura Simplificada Medallion

```
┌──────────────────────────────────────────────────────────────────────┐
│         GERAÇÃO DE DADOS SINTÉTICOS                                  │
│  scripts/generate_data.py     — carga inicial 3 anos (full)         │
│  scripts/generate_daily.py    — geração diária incremental           │
└──────────────────────────┬───────────────────────────────────────────┘
                           │ INSERT / UPDATE
                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│         FONTE — SUPABASE (PostgreSQL Cloud)                          │
│  vendas │ clientes │ produtos │ estoque │ logistica │ financeiro     │
│                   marketing │ rh                                     │
│                    Volume: ~1–2 GB                                   │
└──────────────────────────┬───────────────────────────────────────────┘
                           │ Ingestão Incremental
                           │ Python + psycopg2 / SQLAlchemy
                           │ Controle por coluna updated_at
                           │ Orquestrado por GitHub Actions (cron)
                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│         CAMADA BRONZE — Parquet Local (~2 GB)                        │
│  data/bronze/<schema>/<tabela>/year=YYYY/month=MM/day=DD/           │
│  Formato: Parquet · Particionado por data de ingestão               │
│  Sem transformação · Retenção: 3 anos                               │
│  Metadados: _source_schema, _source_table, _ingested_at             │
│  PII pseudonimizado antes da escrita                                 │
└──────────────────────────┬───────────────────────────────────────────┘
                           │ dbt (staging, limpeza, SCD2)
                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│         CAMADA SILVER — Parquet Local (~1,2 GB)                     │
│  data/silver/<dominio>/<entidade>/                                   │
│  Formato: Parquet · Deduplicado · Chaves harmonizadas               │
│  SCD Type 2 para dim_cliente, dim_produto, dim_vendedor             │
│  Regras de negócio aplicadas                                        │
└──────────────────────────┬───────────────────────────────────────────┘
                           │ dbt (modelagem dimensional, incremental)
                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│         CAMADA GOLD — DuckDB (~700 MB)                               │
│  data/gold/jstechstore.duckdb                                        │
│  Esquema Estrela: 10 dimensões + 6 fatos                            │
│  Métricas pré-calculadas · Otimizado para Power BI Import Mode      │
└──────────────────────────┬───────────────────────────────────────────┘
                           │ Import Mode + Incremental Refresh
                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│         POWER BI — 6 DASHBOARDS EXECUTIVOS                          │
│  Comercial │ Clientes │ Produtos │ Logística │ Financeiro │ Mktg    │
│  Incremental Refresh em fato_venda · Refresh: até 8×/dia            │
└──────────────────────────────────────────────────────────────────────┘

Suporte horizontal:
  ┌─────────────────────┐   ┌────────────────────────┐
  │   GitHub Actions    │   │   dbt Tests            │
  │   Orquestração cron │   │   Qualidade de Dados   │
  │   CI/CD pipelines   │   │   (not_null, unique,   │
  └─────────────────────┘   │    relationships)      │
                            └────────────────────────┘
```

### 4.2 Stack Tecnológico

| Camada | Tecnologia | Justificativa |
|--------|-----------|---------------|
| Geração de dados | Python + Faker + SQLAlchemy | Simula OLTP real com distribuições realistas |
| Fonte de dados | Supabase (PostgreSQL Cloud) | Gratuito, fácil setup, pgAdmin incluído, REST API |
| Ingestão | Python + psycopg2 + SQLAlchemy | Conector nativo PostgreSQL; incremental por `updated_at` |
| Orquestração | GitHub Actions (cron YAML) | Zero infraestrutura extra; versionado no repositório |
| Transformação | dbt Core | SQL-first; modelos incrementais; testes de schema integrados |
| Armazenamento Bronze/Silver | Parquet local (`data/`) | Sem dependência de cloud storage; leitura nativa pelo dbt+DuckDB |
| Formato de arquivo | Parquet | Compressão eficiente; leitura colunar; suporte nativo no DuckDB |
| DW Serving (Gold) | DuckDB | Zero infra; leitura nativa de Parquet; OLAP embarcado; ideal até ~5 GB |
| Qualidade de Dados | dbt tests (`schema.yml`) | `not_null`, `unique`, `accepted_values`, `relationships` em cada modelo |
| BI | Power BI | Dashboards executivos; Import Mode + Incremental Refresh |
| Conexão PBI → DuckDB | DuckDB ODBC Driver + On-premises Data Gateway | ODBC 64-bit com DSN "JSTechStoreGold"; Gateway roda como serviço Windows — ver `docs/arquitetura/powerbi_gateway_setup.md` |
| Calendário de feriados | dbt seed (`seeds/feriados_nacionais.csv`) | Feriados nacionais 2023–2027 (fixos + móveis calculados pela Páscoa); popula `fl_feriado_nacional` na `dim_tempo` |
| Versionamento | Git + GitHub | Código e modelos dbt versionados; CI/CD com GitHub Actions |

**Tecnologias removidas em relação à v2.0 (simplificação):**

| Removido | Substituído por |
|----------|----------------|
| SQL Server (Azure SQL / RDS) | Supabase (PostgreSQL) |
| Apache Airflow | GitHub Actions (cron YAML) |
| Azure Blob Storage / AWS S3 | Parquet em disco local (`data/`) |
| OpenMetadata | — (removido; docs dbt suprem necessidade básica) |
| Great Expectations | dbt tests (`schema.yml`) |
| Docker Compose (Airflow + OpenMetadata) | Não necessário (apenas dbt + Python) |

### 4.3 Geração de Dados Sintéticos

O projeto não parte de um sistema legado real — os dados são gerados por scripts Python que simulam 3 anos de operação da JSTechStore Brasil com distribuições realistas.

#### Script de Carga Inicial: `scripts/generate_data.py`

Gera e insere em lote no Supabase:
- **3 anos de histórico** (1.096 dias, de `hoje - 3 anos` até `ontem`)
- ~2.000 pedidos/dia × 3,2 itens/pedido → ~2,1 milhões de itens de pedido
- Cadastros mestres (produtos, clientes, lojas, fornecedores, campanhas, vendedores)
- Distribuições realistas: sazonalidade (Black Friday, Natal, volta às aulas), mix de canal, variação de ticket médio por categoria

```bash
# Executar carga inicial (roda uma vez na Fase 1)
python scripts/generate_data.py --start-date 2023-07-21 --end-date 2026-07-20 --seed 42
```

#### Script Incremental Diário: `scripts/generate_daily.py`

Gera e insere apenas os registros do **dia atual**:
- ~2.000 novos pedidos com itens, entregas e lançamentos financeiros
- Atualiza `updated_at` nos registros modificados (devoluções, status de entrega)
- Executado diariamente pelo GitHub Actions às 01:00 BRT

```bash
# Executar geração do dia (rodado pelo GitHub Actions)
python scripts/generate_daily.py --date today
```

### 4.4 Estratégia de Ingestão Incremental (Bronze)

O conector Python extrai apenas registros **novos ou alterados** desde a última execução bem-sucedida:

```python
# Lógica de watermark por tabela
SELECT * FROM <schema>.<tabela>
WHERE updated_at > :last_watermark
ORDER BY updated_at ASC
```

- Watermark salvo em `data/bronze/.watermarks/<schema>__<tabela>.json`
- Na primeira execução (após `generate_data.py`): full load de 3 anos
- Nas execuções seguintes: apenas delta do dia
- Parquet escrito com `append` na partição do dia corrente

### 4.5 Estratégia de Transformação Incremental (dbt)

Modelos dbt configurados como `incremental` nas camadas Silver e Gold:

```sql
-- Exemplo: fato_venda (Gold) — modelo incremental
{{ config(
    materialized='incremental',
    unique_key='nr_item_pedido_dg',
    on_schema_change='sync_all_columns'
) }}

SELECT ...
FROM {{ ref('int_vendas__itens_unificados') }}
{% if is_incremental() %}
WHERE sk_tempo >= (SELECT MAX(sk_tempo) - 1 FROM {{ this }})
{% endif %}
```

- Primeira execução (`dbt run --full-refresh`): processa 3 anos de histórico
- Execuções subsequentes: processa apenas novos Parquet da Bronze do dia

### 4.6 Power BI — Incremental Refresh

Para suportar crescimento do dataset sem ultrapassar o limite de 1 GB:

- **Política de Incremental Refresh** configurada na `fato_venda`:
  - Arquivar: dados com mais de 2 anos (não recarregados)
  - Atualizar: últimos 3 dias (janela de segurança para reprocessamento)
- **Parâmetros obrigatórios:** `RangeStart` (DateTime) e `RangeEnd` (DateTime) na query M
- **Resultado:** Power BI carrega apenas o delta diário, não o dataset completo
- **Tabelas de dimensão:** refresh completo (volume pequeno, estável)

```
fato_venda:
  Arquivamento:  > 2 anos  → armazenado, não recarregado
  Atualização:   últimos 3 dias → recarregado a cada refresh
  Refresh diário: ~15 MB (vs. 700 MB full load)
```

---

## 5. LGPD — Requisitos Mínimos

### 5.1 Pseudonimização na Geração de Dados

Como os dados são sintéticos, o módulo de pseudonimização aplica HMAC-SHA256 **nos dados gerados antes de inserir no Supabase** e **antes de escrever no Bronze**. Nenhum dado pessoal direto (CPF, e-mail, telefone) persiste no DW.

| Campo Original | Tratamento | Campo no DW |
|---------------|-----------|-------------|
| CPF (sintético) | HMAC-SHA256 com salt | `cpf_hash` |
| E-mail (sintético) | HMAC-SHA256 com salt | `email_hash` |
| Telefone (sintético) | HMAC-SHA256 com salt | `telefone_hash` |
| Nome completo | Apenas `primeiro_nome` | `primeiro_nome` |
| Endereço completo | Apenas CEP + cidade + UF | `cep`, `cidade`, `uf` |

### 5.2 Direito à Exclusão (Art. 18, LGPD)

Script parametrizado `quality/lgpd/exclusao_titular.py`:
1. Identifica registros pelo `cpf_hash`
2. Substitui campos PII por `'[REMOVIDO]'` nas camadas Silver e Gold (DuckDB)
3. Preserva fatos agregados (valores, quantidades) sem identificação pessoal
4. Registra execução em `quality/lgpd/logs/` com timestamp e tabelas afetadas

### 5.3 Registro de Atividades (RIPD)

Documento em `docs/lgpd/RIPD_JSTechStore.md`:

| Campo | Conteúdo |
|-------|---------|
| Finalidade | Analytics e dashboards executivos internos (dados sintéticos) |
| Base legal | Legítimo interesse (Art. 7º, IX) |
| Prazo de retenção | Bronze: 3 anos; Silver/Gold: enquanto necessário |
| Compartilhamento | Apenas internamente (Power BI para equipes internas) |

---

## 6. Modelagem Dimensional — Esquema Estrela

### 6.1 Visão Geral do Esquema

```
                        ┌─────────────────┐
                        │   dim_vendedor  │
                        └────────┬────────┘
                                 │
  ┌──────────────┐    ┌──────────┴──────────────────────────────────────────┐
  │  dim_cliente │    │                   fato_venda                        │
  └──────┬───────┘    │  (grain: 1 linha por item de pedido)                │
         │            │                                                      │
  ┌──────┴───────┐    │  sk_tempo (FK)       sk_produto (FK)                │
  │  dim_tempo   ├────┤  sk_cliente (FK)     sk_loja (FK)                   │
  └──────────────┘    │  sk_canal_venda (FK) sk_campanha (FK)               │
                      │  sk_vendedor (FK)    nr_pedido_dg                   │
  ┌──────────────┐    │  nr_item_pedido_dg   qtd_vendida                    │
  │  dim_produto ├────┤  preco_unitario_bruto  desconto_valor               │
  └──────────────┘    │  valor_bruto_item    valor_liquido_item             │
                      │  custo_unitario      margem_bruta_item              │
  ┌──────────────┐    │  fl_troca_devolucao  ponto_fidelidade_pedido       │
  │  dim_loja    ├────┤                                                      │
  └──────────────┘    └─────────────────────────────────────────────────────┘
                                 │
  ┌──────────────────┐  ┌────────┴────────┐  ┌────────────────────────────┐
  │ dim_canal_venda  │  │  dim_campanha   │  │  dim_modalidade_entrega    │
  └──────────────────┘  └─────────────────┘  └────────────────────────────┘
```

### 6.2 Dimensões

#### dim_cliente
| Campo | Tipo | Descrição |
|-------|------|-----------|
| sk_cliente | INT (PK) | Surrogate key |
| id_cliente_nk | VARCHAR | Chave natural do OLTP |
| cpf_hash | VARCHAR | HMAC-SHA256 do CPF |
| email_hash | VARCHAR | HMAC-SHA256 do e-mail |
| telefone_hash | VARCHAR | HMAC-SHA256 do telefone |
| primeiro_nome | VARCHAR | Primeiro nome apenas |
| cep | VARCHAR | CEP de entrega principal |
| cidade | VARCHAR | Cidade |
| uf | CHAR(2) | Estado |
| data_cadastro | DATE | Primeira interação registrada |
| canal_origem | VARCHAR | Canal de primeiro contato |
| nivel_fidelidade | VARCHAR | Nível TechPoints: Bronze/Silver/Gold/Platinum |
| ativo | BOOLEAN | Comprou nos últimos 180 dias |
| valid_from | DATE | SCD Type 2: início de vigência |
| valid_to | DATE | SCD Type 2: fim de vigência (9999-12-31 se atual) |
| fl_current | BOOLEAN | SCD Type 2: registro atual |

> `segmento_rfm` e `nivel_fidelidade` são calculados mensalmente via dbt e atualizados via SCD2.

#### dim_produto
| Campo | Tipo | Descrição |
|-------|------|-----------|
| sk_produto | INT (PK) | Surrogate key |
| id_produto_nk | VARCHAR | Chave natural / SKU interno |
| sku | VARCHAR | Código de produto |
| nome | VARCHAR | Nome comercial |
| categoria | VARCHAR | Categoria nível 1 (ex: Smartphones) |
| subcategoria | VARCHAR | Categoria nível 2 |
| marca | VARCHAR | Fabricante |
| sk_fornecedor | INT (FK) | Fornecedor principal |
| peso_kg | DECIMAL | Para cálculo de frete |
| ativo | BOOLEAN | Produto em catálogo ativo |
| valid_from | DATE | SCD Type 2 |
| valid_to | DATE | SCD Type 2 |
| fl_current | BOOLEAN | SCD Type 2 |

> Preços **não ficam na dimensão** — pertencem à tabela fato (`custo_unitario`, `preco_unitario_bruto`) para preservar preço histórico da transação.

#### dim_loja
| Campo | Tipo | Descrição |
|-------|------|-----------|
| sk_loja | INT (PK) | Surrogate key |
| id_loja_nk | VARCHAR | Código interno da loja |
| nome_loja | VARCHAR | Nome da unidade |
| tipo_loja | VARCHAR | física, CD, e-commerce |
| regiao | VARCHAR | Sul, Sudeste, Centro-Oeste |
| cidade | VARCHAR | Cidade |
| uf | CHAR(2) | Estado |
| gerente | VARCHAR | Nome do gerente responsável |
| capacidade_m2 | INT | Área da loja |
| dt_abertura | DATE | Data de inauguração |
| ativo | BOOLEAN | Loja em operação |
| valid_from | DATE | SCD Type 2: início de vigência |
| valid_to | DATE | SCD Type 2: fim de vigência (9999-12-31 se atual) |
| fl_current | BOOLEAN | SCD Type 2: registro atual |

> SCD Type 2 aplicado nos atributos `gerente`, `capacidade_m2` e `ativo` — mudança de gerente ou reforma gera nova versão do registro sem perder a histórico de atribuição.

#### dim_tempo
| Campo | Tipo | Descrição |
|-------|------|-----------|
| sk_tempo | INT (PK) | Formato YYYYMMDD |
| data | DATE | Data completa |
| ano | INT | Ano |
| semestre | INT | 1 ou 2 |
| trimestre | INT | 1–4 |
| mes | INT | 1–12 |
| nome_mes | VARCHAR | Janeiro, Fevereiro... |
| semana_ano | INT | Semana ISO |
| dia_semana | INT | 1 (seg) a 7 (dom) |
| nome_dia_semana | VARCHAR | Segunda, Terça... |
| fl_dia_util | BOOLEAN | Dia útil comercial |
| fl_feriado_nacional | BOOLEAN | Feriado nacional |
| fl_black_friday | BOOLEAN | Semana de Black Friday |

#### dim_canal_venda
| Campo | Tipo | Descrição |
|-------|------|-----------|
| sk_canal | INT (PK) | Surrogate key |
| id_canal_nk | VARCHAR | Código do canal |
| canal | VARCHAR | loja_fisica, site_proprio, marketplace_ml, marketplace_amazon, marketplace_shopee |
| tipo | VARCHAR | físico, online |
| descricao | VARCHAR | Descrição completa |

#### dim_campanha
| Campo | Tipo | Descrição |
|-------|------|-----------|
| sk_campanha | INT (PK) | Surrogate key |
| id_campanha_nk | VARCHAR | Código interno da campanha |
| nome_campanha | VARCHAR | Nome da campanha |
| tipo_campanha | VARCHAR | email, paid_search, display, influencer, push, cupom |
| canal_mkt | VARCHAR | Canal de veiculação |
| data_inicio | DATE | Início da campanha |
| data_fim | DATE | Fim da campanha |
| orcamento | DECIMAL | Verba aprovada em BRL (versão mais recente) |
| modelo_atribuicao | VARCHAR | last_touch, first_touch, linear |
| ativo | BOOLEAN | Campanha vigente |
| versao_orcamento | VARCHAR | Identificador da revisão orçamentária (ex: original, revisao_1) |
| valid_from | DATE | SCD Type 2: início de vigência |
| valid_to | DATE | SCD Type 2: fim de vigência (9999-12-31 se atual) |
| fl_current | BOOLEAN | SCD Type 2: registro atual |

> SCD Type 2 aplicado no atributo `orcamento` — revisões de verba mid-flight geram nova versão do registro, preservando o orçamento original para análise de ROI histórico fiel.

#### dim_vendedor
| Campo | Tipo | Descrição |
|-------|------|-----------|
| sk_vendedor | INT (PK) | Surrogate key |
| id_vendedor_nk | VARCHAR | Matrícula do vendedor |
| cpf_hash | VARCHAR | HMAC-SHA256 do CPF |
| primeiro_nome | VARCHAR | Primeiro nome |
| sk_loja | INT (FK) | Loja principal de atuação |
| cargo | VARCHAR | Consultor, Supervisor, Gerente |
| data_admissao | DATE | Data de entrada na empresa |
| meta_mensal_brl | DECIMAL | Meta mensal em BRL |
| ativo | BOOLEAN | Funcionário ativo |
| valid_from | DATE | SCD Type 2 |
| valid_to | DATE | SCD Type 2 |
| fl_current | BOOLEAN | SCD Type 2 |

#### dim_transportadora
| Campo | Tipo | Descrição |
|-------|------|-----------|
| sk_transportadora | INT (PK) | Surrogate key |
| id_transportadora_nk | VARCHAR | Código interno |
| nome_transportadora | VARCHAR | Razão social / nome comercial |
| cnpj_hash | VARCHAR | HMAC-SHA256 do CNPJ |
| tipo | VARCHAR | correios, transportadora_privada, motoboy, retirada_loja |
| sla_dias_padrao | INT | Prazo contratual padrão em dias úteis |
| ativo | BOOLEAN | Transportadora ativa |

#### dim_fornecedor
| Campo | Tipo | Descrição |
|-------|------|-----------|
| sk_fornecedor | INT (PK) | Surrogate key |
| id_fornecedor_nk | VARCHAR | Código interno |
| nome_fornecedor | VARCHAR | Razão social |
| cnpj_hash | VARCHAR | HMAC-SHA256 do CNPJ |
| categoria_principal | VARCHAR | Categoria primária fornecida |
| pais_origem | VARCHAR | País de origem dos produtos |
| prazo_entrega_dias | INT | Prazo padrão de entrega ao CD |
| ativo | BOOLEAN | Fornecedor ativo |

#### dim_modalidade_entrega
| Campo | Tipo | Descrição |
|-------|------|-----------|
| sk_modalidade | INT (PK) | Surrogate key |
| id_modalidade_nk | VARCHAR | Código interno |
| nome_modalidade | VARCHAR | PAC, SEDEX, Same-day, Retirada em Loja, Ship from Store |
| tipo | VARCHAR | correios, transportadora, retirada, ship_from_store |
| prazo_dias_estimado | INT | Prazo médio em dias úteis |
| fl_frete_gratis | BOOLEAN | Modalidade com frete grátis padrão |

### 6.3 Tabelas Fato

#### fato_venda *(grain: 1 linha por item de pedido)*
| Campo | Tipo | Descrição |
|-------|------|-----------|
| sk_tempo | INT (FK) | Data do pedido |
| sk_cliente | INT (FK) | Cliente comprador |
| sk_produto | INT (FK) | Produto vendido |
| sk_loja | INT (FK) | Loja de origem / canal |
| sk_canal | INT (FK) | Canal de venda |
| sk_campanha | INT (FK) | Campanha atribuída (nullable) |
| sk_vendedor | INT (FK) | Vendedor responsável; null para e-commerce |
| nr_pedido_dg | VARCHAR | Chave degenerada — número do pedido |
| nr_item_pedido_dg | VARCHAR | Chave degenerada — número do item |
| qtd_vendida | DECIMAL | Quantidade do item |
| preco_unitario_bruto | DECIMAL | Preço de tabela (sem desconto) |
| desconto_valor | DECIMAL | Valor do desconto aplicado |
| preco_unitario_liquido | DECIMAL | Preço efetivo de venda |
| custo_unitario | DECIMAL | CMV unitário no momento da venda |
| valor_bruto_item | DECIMAL | qtd × preco_unitario_bruto |
| valor_liquido_item | DECIMAL | qtd × preco_unitario_liquido |
| margem_bruta_item | DECIMAL | valor_liquido_item - (qtd × custo_unitario) |
| ponto_fidelidade_pedido | INT | Pontos TechPoints do pedido |
| fl_troca_devolucao | BOOLEAN | Item é resultado de troca/devolução |

#### fato_estoque *(grain: 1 linha por produto × loja × dia)*
| Campo | Tipo | Descrição |
|-------|------|-----------|
| sk_tempo | INT (FK) | Data do snapshot de estoque |
| sk_produto | INT (FK) | Produto |
| sk_loja | INT (FK) | Loja ou CD |
| qtd_disponivel | INT | Quantidade disponível para venda |
| qtd_reservada | INT | Quantidade reservada por pedidos |
| qtd_em_transito | INT | Quantidade em transferência |
| custo_medio_unitario | DECIMAL | Custo médio do estoque |
| valor_estoque_brl | DECIMAL | qtd_disponivel × custo_medio_unitario |
| dias_cobertura | DECIMAL | Estoque disponível / venda média 30d |
| giro_30d | DECIMAL | Unidades vendidas últimos 30d / estoque médio 30d |
| fl_ruptura | BOOLEAN | qtd_disponivel = 0 |

#### fato_entrega *(grain: 1 linha por pedido entregue ou tentativa)*
| Campo | Tipo | Descrição |
|-------|------|-----------|
| sk_tempo_pedido | INT (FK) | Data do pedido |
| sk_tempo_entrega | INT (FK) | Data da entrega efetiva |
| sk_cliente | INT (FK) | Cliente destinatário |
| sk_loja_origem | INT (FK) | CD ou loja SFS de origem |
| sk_transportadora | INT (FK) | Transportadora responsável |
| sk_modalidade | INT (FK) | Modalidade de entrega |
| nr_pedido_dg | VARCHAR | Chave degenerada — número do pedido |
| data_promessa | DATE | Data prometida ao cliente |
| data_efetiva | DATE | Data de entrega efetiva (null se pendente) |
| fl_sla_atendido | BOOLEAN | Entrega realizada dentro do prazo prometido |
| dias_atraso | INT | Dias de atraso (0 se no prazo) |
| motivo_atraso | VARCHAR | Categoria do motivo de atraso |
| custo_frete | DECIMAL | Custo de frete em BRL |
| fl_ship_from_store | BOOLEAN | Entrega expedida a partir de loja (não CD) |
| fl_avaria | BOOLEAN | Produto chegou avariado |
| fl_devolucao | BOOLEAN | Pedido foi devolvido |

#### fato_financeiro *(grain: 1 linha por lançamento financeiro)*
| Campo | Tipo | Descrição |
|-------|------|-----------|
| sk_tempo | INT (FK) | Data do lançamento |
| sk_loja | INT (FK) | Centro de custo / loja |
| sk_canal | INT (FK) | Canal de venda associado |
| nr_documento_dg | VARCHAR | Número de NF, boleto ou lançamento |
| tipo_lancamento | VARCHAR | venda, devolucao, desconto_comercial, imposto, custo_frete, despesa_operacional, comissao_marketplace |
| valor_bruto | DECIMAL | Valor bruto do lançamento |
| valor_liquido | DECIMAL | Valor após deduções |
| cmv | DECIMAL | Custo da mercadoria (somente tipo venda) |
| margem_bruta | DECIMAL | valor_liquido - cmv |
| nr_parcelas | INT | Número de parcelas |
| fl_parcelado | BOOLEAN | Transação parcelada |
| prazo_medio_recebimento_dias | INT | Prazo médio ponderado de recebimento |

#### fato_cliente_interacao *(grain: 1 linha por evento de interação)*

> **Fonte de dados:** Schema `web_analytics` no Supabase — tabelas `sessoes` e `eventos_carrinho`, geradas pelo `generate_daily.py`. Visitantes anônimos são excluídos; apenas sessões vinculadas a um `id_cliente` alimentam a dimensão `sk_cliente`.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| sk_tempo | INT (FK) | Data do evento |
| sk_cliente | INT (FK) | Cliente identificado (nullable para visitas anônimas excluídas na Silver) |
| sk_loja | INT (FK) | Loja associada (nullable) |
| sk_campanha | INT (FK) | Campanha associada (nullable) |
| sk_canal | INT (FK) | Canal da interação |
| id_sessao_dg | VARCHAR | Chave degenerada da sessão web |
| tipo_interacao | VARCHAR | visita_site, abandono_carrinho, compra, devolucao, contato_sac, resgate_ponto |
| valor_carrinho_abandonado | DECIMAL | Valor do carrinho no abandono (nullable) |
| duracao_sessao_min | DECIMAL | Duração da sessão em minutos (de web_analytics.sessoes) |
| nr_paginas_visitadas | INT | Páginas visitadas na sessão (de web_analytics.sessoes) |

#### fato_orcamento *(grain: 1 linha por orçamento × mês × canal × loja)*

> **Fonte de dados:** `financeiro.orcamentos` no Supabase. Permite comparar receita e margem realizadas (`fato_financeiro`) vs. orçadas nesta tabela, habilitando o KPI "Budget vs. Realizado" do Dashboard Financeiro.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| sk_tempo | INT (FK) | Primeiro dia do mês de referência (YYYYMM01) |
| sk_loja | INT (FK) | Loja ou canal central de custo |
| sk_canal | INT (FK) | Canal de venda orçado |
| id_orcamento_dg | VARCHAR | Chave degenerada do orçamento |
| versao_orcamento | VARCHAR | original, revisao_1, revisao_2 — controle de revisões mid-year |
| receita_orcada_brl | DECIMAL | Receita líquida orçada para o mês |
| margem_orcada_brl | DECIMAL | Margem bruta orçada para o mês |
| cmv_orcado_brl | DECIMAL | CMV orçado para o mês |
| despesas_orcadas_brl | DECIMAL | Despesas operacionais orçadas |
| meta_unidades | INT | Meta de unidades vendidas no mês |

---

## 7. Requisitos dos Dashboards

### 7.1 Dashboard Comercial

**Audiência:** Diretores Comerciais, Gerentes de Loja, Regional  
**Frequência de atualização:** Diária (D-1)

| Indicador | Fórmula / Descrição | Granularidade |
|-----------|---------------------|---------------|
| Receita Bruta Total | Soma de valor_bruto_item | Dia, Semana, Mês, Canal |
| Receita Líquida | Soma de valor_liquido_item | Dia, Semana, Mês, Canal |
| Ticket Médio | Receita / Qtd Pedidos | Canal, Loja, Categoria |
| Unidades Vendidas | Soma qtd_vendida | Produto, Categoria |
| Taxa de Desconto Médio | Soma(desconto_valor) / Soma(valor_bruto_item) | Canal, Categoria |
| Mix de Canal | % Físico vs Online vs Marketplace | Mensal |
| vs. Meta (%) | Real / Meta por loja/vendedor | Loja, Vendedor, Mês |
| vs. Período Anterior | YoY, MoM, WoW | Dia, Semana |
| Ranking de Lojas | Receita e margem por loja | Mensal |
| Top 20 Produtos | Receita + Margem + Volume | Categoria, Período |
| Performance por Vendedor | Receita e % da meta por consultor | Loja, Mês |
| Taxa de Devolução | Pedidos devolvidos / Total pedidos | Canal, Categoria |

### 7.2 Dashboard de Clientes

**Audiência:** Gerência de CRM, Marketing, Fidelidade  
**Frequência de atualização:** Diária

| Indicador | Fórmula / Descrição | Granularidade |
|-----------|---------------------|---------------|
| Base Ativa de Clientes | Compraram nos últimos 90 dias | Mensal |
| Novos Clientes | Primeira compra no período | Mês, Canal |
| Taxa de Retenção | Clientes recorrentes / Base total | Mensal |
| Churn Rate | Clientes inativos > 90 dias / Base total anterior | Mensal |
| Historical LTV | Soma de receita líquida por cliente (histórico acumulado) | Segmento, Canal |
| Segmentação RFM | Recência × Frequência × Valor — tabela de calor | Mensal |
| Análise de Cohort | % de retenção mês a mês por coorte de aquisição | Trimestral |
| Programa Fidelidade | Pontos emitidos, resgatados e saldo | Mensal, Nível |
| Clientes Omnichannel | Compraram em canal físico E online no período | Mensal |
| Ticket por Segmento | Ticket médio por nível de fidelidade e segmento RFM | Trimestral |

### 7.3 Dashboard de Produtos

**Audiência:** Compradores, Category Managers, Diretoria de Produto  
**Frequência de atualização:** Diária

| Indicador | Fórmula / Descrição | Granularidade |
|-----------|---------------------|---------------|
| Giro de Estoque | Unidades vendidas / Estoque médio do período | SKU, Categoria |
| Dias de Cobertura | Estoque disponível / Venda média diária (30d) | SKU, Loja |
| Taxa de Ruptura | SKUs com estoque zero / Total SKUs ativos | Loja, Dia |
| Margem por Produto | (Preço venda líq. - CMV) / Preço venda líq. | SKU, Categoria |
| Produtos Sem Giro | SKUs sem venda em 30 / 60 / 90 dias | Loja, CD |
| Curva ABC | Pareto de produtos por receita e margem | Categoria |
| Top e Bottom Performers | Ranking por margem × volume | Categoria |
| Taxa de Devolução por Produto | Devoluções / Vendas por SKU | SKU, Categoria |
| Mix de Marca por Categoria | % de receita por fabricante dentro da categoria | Categoria |

### 7.4 Dashboard de Logística

**Audiência:** Gerência de Logística, Operações  
**Frequência de atualização:** 2× ao dia

| Indicador | Fórmula / Descrição | Granularidade |
|-----------|---------------------|---------------|
| OTD (On-Time Delivery) | Entregas no prazo / Total entregas | Dia, Canal, Transportadora |
| Tempo Médio de Entrega | D+N médio (pedido → entrega) | Região, Canal, Modalidade |
| SLA por Transportadora | OTD por parceiro logístico | Mensal, Transportadora |
| Ship from Store vs CD | % de pedidos expedidos de loja vs CD | Canal, Dia |
| Taxa de Avaria | Pedidos com avaria / Total entregas | Transportadora, Mensal |
| Custo de Frete / Receita | Custo frete total / Receita líquida | Canal, Mensal |
| Pedidos em Aberto (Aging) | Pedidos por faixa de dias sem entrega | Dia |

### 7.5 Dashboard Financeiro

**Audiência:** CFO, Controladoria, Diretoria  
**Frequência de atualização:** Diária (D-1)

| Indicador | Fórmula / Descrição | Granularidade |
|-----------|---------------------|---------------|
| Receita Bruta | Soma de valor_bruto | Mês, Canal |
| Receita Líquida | Bruta - Devoluções - Impostos - Descontos | Mês, Canal |
| CMV | Custo total dos produtos vendidos | Categoria, Mês |
| Margem Bruta | Receita Líquida - CMV | Mês, Canal, Categoria |
| Margem Bruta (%) | Margem Bruta / Receita Líquida | Comparativo MoM |
| EBITDA | Margem Bruta - Despesas Operacionais | Mensal |
| Receita por Canal | Físico vs Online vs Marketplace | Mensal |
| Budget vs Realizado | Receita e margem projetadas vs realizadas | Mês, Canal |
| Contas a Receber | Aging de recebíveis por faixa de vencimento | Mensal |
| Análise de Parcelamento | % parceladas; prazo médio; concentração de recebíveis | Mensal, Canal |

### 7.6 Dashboard de Marketing

**Audiência:** Gerência de Marketing, Growth  
**Frequência de atualização:** Diária

| Indicador | Fórmula / Descrição | Granularidade |
|-----------|---------------------|---------------|
| ROI de Campanha | (Receita Atribuída - Custo) / Custo | Campanha, Canal |
| ROAS | Receita Atribuída / Investimento em Mídia | Canal Pago |
| CAC (Custo por Aquisição) | Investimento / Novos Clientes no período | Campanha, Canal |
| Funil de Conversão | Impressões → Cliques → Sessões → Compras | Campanha, Canal |
| Taxa de Conversão | Compras / Sessões no site | Dia, Campanha |
| Abandono de Carrinho | Carrinhos abandonados / Carrinhos iniciados | Dia |
| Receita Atribuída | Receita por campanha (last-touch ou linear) | Campanha |
| Clientes Reativados | Inativos que compraram após campanha | Campanha, Mensal |

---

## 8. Fases do Projeto

### Fase 1 — Geração de Dados + Ingestão Bronze (Meses 1–2)

**Objetivo:** Supabase populado com 3 anos de histórico, pipeline Bronze funcionando com ingestão incremental diária via GitHub Actions.

**Entregas:**
- [ ] Setup Supabase: criar projeto, schemas, tabelas, índices em `updated_at`
- [ ] Script `scripts/generate_data.py`: gera 3 anos de dados sintéticos e insere no Supabase
- [ ] Script `scripts/generate_daily.py`: gera ~2.000 vendas do dia e insere no Supabase
- [ ] Conector de ingestão: Python + psycopg2 extraindo por `updated_at` → Parquet Bronze local
- [ ] Estrutura de pastas `data/bronze/` com partição `year=YYYY/month=MM/day=DD/`
- [ ] GitHub Actions workflow: cron diário (01:00 BRT) → `generate_daily.py` + ingestão Bronze
- [ ] Módulo de pseudonimização LGPD (`quality/lgpd/pseudonimizacao.py`)
- [ ] Watermark de controle incremental por tabela (`data/bronze/.watermarks/`)
- [ ] Repositório GitHub: estrutura de pastas, `requirements.txt`, `.env.example`, `README.md`

**Critérios de Aceite:**
- 3 anos de dados populados no Supabase sem erros
- Pipeline Bronze rodando diariamente por 3 dias consecutivos via GitHub Actions
- Apenas novos registros (delta) escritos no Bronze a cada execução
- Nenhum dado pessoal direto (CPF, e-mail) no Parquet Bronze

---

### Fase 2 — Data Warehouse Silver + Gold + dbt (Meses 3–4)

**Objetivo:** Camadas Silver e Gold com modelagem dimensional incremental completa, pronta para consumo no Power BI.

**Entregas:**
- [ ] Projeto dbt configurado com profile DuckDB (`profiles.yml`)
- [ ] dbt seed `feriados_nacionais.csv` (2023–2027) populando `fl_feriado_nacional` na `dim_tempo`
- [ ] Camada Silver: modelos dbt staging (`stg_*`) e intermediários (`int_*`) — todos incrementais
- [ ] SCD Type 2 via macro `scd2_merge.sql` para `dim_cliente`, `dim_produto`, `dim_vendedor`, `dim_loja`, `dim_campanha`
- [ ] 10 dimensões conformadas no DuckDB (`dim_*.sql`)
- [ ] 6 tabelas fato no DuckDB (`fato_*.sql`) — modelos incrementais por data (inclui `fato_orcamento`)
- [ ] `fato_cliente_interacao` alimentada por `web_analytics.sessoes` + `web_analytics.eventos_carrinho`
- [ ] `fato_orcamento` alimentada por `financeiro.orcamentos` — habilita KPI "Budget vs. Realizado"
- [ ] `schema.yml` com testes dbt (`not_null`, `unique`, `relationships`, `accepted_values`) em todos os modelos Gold
- [ ] Script LGPD de exclusão de titular (`quality/lgpd/exclusao_titular.py`)
- [ ] RIPD inicial documentado (`docs/lgpd/RIPD_JSTechStore.md`)
- [ ] GitHub Actions: workflow `dbt run` incremental após ingestão Bronze
- [ ] Script `quality/monitoring/check_data_freshness.py` integrado no pipeline
- [ ] Script `quality/reconciliation/reconcile_gold_vs_source.py` cobrindo todas as 6 tabelas fato

**Critérios de Aceite:**
- `dbt run` com 3 anos de histórico concluindo sem erros (`--full-refresh` na primeira vez)
- `dbt test` 100% passando nos modelos Gold
- `dbt run` incremental diário processando apenas dados novos (< 2 min de execução)
- Reconciliação de totais `fato_venda.valor_liquido_item` vs. Supabase com desvio < 0,1%
- Gold ≤ 900 MB no `jstechstore.duckdb`

---

### Fase 3 — Dashboards Power BI com Incremental Refresh (Meses 5–6)

**Objetivo:** 6 dashboards executivos publicados no Power BI com Incremental Refresh configurado e validados.

**Entregas:**
- [ ] Conexão Power BI → DuckDB via DuckDB ODBC Driver 64-bit + DSN "JSTechStoreGold" (ver `docs/arquitetura/powerbi_gateway_setup.md`)
- [ ] On-premises Data Gateway instalado como serviço Windows automático e registrado no Power BI Service
- [ ] Política de Incremental Refresh configurada em `fato_venda` (`RangeStart`/`RangeEnd`)
- [ ] Dashboard Comercial (aprovado)
- [ ] Dashboard de Clientes (aprovado)
- [ ] Dashboard de Produtos (aprovado)
- [ ] Dashboard de Logística (aprovado)
- [ ] Dashboard Financeiro (aprovado)
- [ ] Dashboard de Marketing (aprovado)
- [ ] Dicionário de Métricas Power BI (`docs/dicionario_dados/metricas_powerbi.md`)

**Critérios de Aceite:**
- Refresh diário do Power BI processando apenas delta (< 30s para tabelas fato com Incremental Refresh)
- Todos os KPIs reconciliados entre Power BI e DuckDB Gold
- Cada dashboard aprovado formalmente pelo responsável da área

---

### Fase 4 — Analytics Avançado (Meses 7–9)

**Objetivo:** Análises preditivas e evolução da plataforma.

**Entregas:**
- [ ] Segmentação RFM automatizada com atualização mensal via dbt
- [ ] Previsão de demanda por SKU (Prophet / scikit-learn)
- [ ] Score de propensão ao churn de clientes
- [ ] Self-service BI: workspace Power BI para analistas de negócio
- [ ] Revisão de agregações Gold para manter dataset < 900 MB

---

## 9. Qualidade de Dados

### Camada Bronze
- Dados extraídos sem transformação — fiel à fonte Supabase
- Campos de metadados obrigatórios: `_source_schema`, `_source_table`, `_ingested_at`, `_row_count_batch`
- **Nenhum dado pessoal direto** (pseudonimização antes da escrita em Parquet)

### Camada Silver (via dbt tests)

| Regra | Implementação dbt |
|-------|-------------------|
| Deduplicação | `unique` test em chave natural + `ROW_NUMBER()` no modelo |
| Campos críticos não nulos | `not_null` em `cpf_hash`, `sku`, `sk_tempo`, valores monetários |
| Padronização | dbt `macros/` para datas UTC, BRL 2 decimais, strings lowercase |
| Harmonização de cliente | `cpf_hash` como chave única entre POS e e-commerce |
| Validação de domínio | `accepted_values` para status de pedido, UF, tipo de canal |
| SCD Type 2 | macro `scd2_merge.sql` aplicada em dim_cliente, dim_produto, dim_vendedor |

### Camada Gold (via dbt tests + scripts de qualidade)

| Regra | Implementação |
|-------|---------------|
| Reconciliação completa | Script `quality/reconciliation/reconcile_gold_vs_source.py` — cobre **todas as 6 tabelas fato** (contagem + métricas financeiras, tolerância ≤ 0,1%) |
| Integridade referencial | `relationships` test em todas as FKs das tabelas fato |
| Atualidade (frescor) | Script `quality/monitoring/check_data_freshness.py` — verifica Bronze por tabela e MAX(sk_tempo) de cada fato após dbt run |
| Volume de batch | check_data_freshness valida faixa esperada de linhas por tabela/dia |

---

## 10. Estrutura de Pastas do Projeto

```
Ecommerce_Varejo/
│
├── docs/
│   ├── PRD_JSTechStore_Brasil_DataEngineering.md   ← este documento
│   ├── arquitetura/          # Diagramas e ADRs
│   ├── dicionario_dados/     # Dicionário por camada e métricas PBI
│   └── lgpd/
│       └── RIPD_JSTechStore.md
│
├── scripts/
│   ├── generate_data.py      # Geração de 3 anos de dados sintéticos → Supabase
│   └── generate_daily.py     # Geração incremental diária → Supabase
│
├── ingestion/
│   ├── connectors/
│   │   └── postgres/         # Conector Supabase (PostgreSQL)
│   │       ├── __init__.py
│   │       ├── extract.py    # Full load + incremental por updated_at
│   │       └── config.py     # Mapeamento de tabelas e controle incremental
│   └── watermarks/           # Alias — em data/bronze/.watermarks/
│
├── transformation/
│   └── dbt_project/
│       ├── dbt_project.yml
│       ├── profiles.yml      # Profile DuckDB lendo Parquet local
│       ├── packages.yml
│       ├── models/
│       │   ├── bronze/       # stg_<schema>__<tabela>.sql — lê Parquet Bronze
│       │   ├── silver/       # int_<dominio>__<entidade>.sql — incrementais
│       │   └── gold/
│       │       ├── dimensions/   # dim_*.sql
│       │       └── facts/        # fato_*.sql — incrementais por data
│       ├── tests/            # Testes dbt singulares
│       └── macros/
│           ├── rfm_score.sql
│           ├── scd2_merge.sql
│           └── hash_pii.sql
│
├── quality/
│   ├── reconciliation/       # Script de reconciliação Gold vs. Supabase
│   └── lgpd/
│       ├── pseudonimizacao.py   # Módulo HMAC-SHA256
│       ├── exclusao_titular.py  # Right-to-erasure no DuckDB
│       └── logs/
│
├── powerbi/
│   ├── datasets/             # Arquivos .pbix dos datasets
│   └── reports/              # Arquivos .pbix dos relatórios
│
├── data/                     # Dados locais (Bronze + Silver + Gold)
│   ├── bronze/               # Parquet particionado por data
│   │   └── .watermarks/      # JSON com último updated_at por tabela
│   ├── silver/               # Parquet Silver (saída dbt)
│   └── gold/
│       └── jstechstore.duckdb
│
├── .github/
│   └── workflows/
│       ├── daily_pipeline.yml    # Cron 01:00 BRT: gerar dados + Bronze + dbt
│       └── ci_dbt_tests.yml      # CI: dbt test em PRs
│
├── tests/                    # Testes unitários Python
├── .env.example
├── requirements.txt
└── CLAUDE.md
```

---

## 11. Orquestração — GitHub Actions

### Workflow Diário (`daily_pipeline.yml`)

```
Cron: 0 4 * * *  (04:00 UTC = 01:00 BRT)

Jobs (sequenciais — falha em qualquer step interrompe o pipeline):
  1. generate_daily        → python scripts/generate_daily.py --date today
  2. ingest_bronze         → python -m ingestion.connectors.postgres.extract --mode incremental
                             (watermark atualizado somente após escrita Parquet confirmada)
  3. dbt_seed              → dbt seed --select feriados_nacionais
     dbt_run_incremental   → dbt run
  4. dbt_test              → dbt test --select gold
  5. check_freshness       → python quality/monitoring/check_data_freshness.py
                             (verifica MAX(sk_tempo) Gold >= D-1 e volume de batch)
  6. reconcile             → python quality/reconciliation/reconcile_gold_vs_source.py
                             (6 tabelas fato — tolerância ≤ 0,1% em métricas financeiras)
  7. backup_gold           → python scripts/backup_gold.py --keep-days 7
                             + upload GitHub Actions Artifact (retenção 30 dias)
  8. notify_on_failure     → GitHub notification em caso de falha (qualquer step)
```

### Workflow CI (`ci_dbt_tests.yml`)

```
Trigger: Pull Request para main

Jobs:
  1. dbt_compile           → dbt compile
  2. dbt_test              → dbt test
```

---

## 12. Variáveis de Ambiente

Arquivo `.env.example` (nunca commitar `.env`):

```bash
# Supabase / PostgreSQL
SUPABASE_DB_URL=postgresql://postgres:<password>@<project>.supabase.co:5432/postgres

# DuckDB
DUCKDB_PATH=data/gold/jstechstore.duckdb

# LGPD
LGPD_HMAC_SALT=<salt-secreto-gerado-aleatoriamente>

# Caminhos locais
BRONZE_PATH=data/bronze
SILVER_PATH=data/silver
```

---

## 13. Riscos e Mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|-------|--------------|---------|-----------|
| Limite do dataset Power BI (1 GB) | Média | Médio | Incremental Refresh em fato_venda; agregar mais na Gold |
| GitHub Actions: limite de minutos gratuitos | Baixa | Baixo | Pipeline diário roda em < 5 min; plano gratuito tem 2.000 min/mês |
| Parquet local: falta de backup | Média | Médio | Commitar `.watermarks/` no Git; regenerar Bronze a partir do Supabase se necessário |
| Supabase free tier: 500 MB de banco | Baixa | Médio | Supabase free inclui 500 MB; dados sintéticos gerados ficam ~200–300 MB no PostgreSQL |
| Dados sintéticos não realistas | Média | Baixo | Usar seeds fixas (`--seed 42`) e distribuições sazonais validadas; revisar com análise exploratória antes da Fase 3 |
| dbt run --full-refresh lento (3 anos) | Baixa | Baixo | Rodado apenas 1 vez na Fase 2; incrementais subsequentes < 2 min |

---

## 14. Critérios de Sucesso

### Por Fase
- **Fase 1:** Pipeline Bronze rodando diariamente por 3 dias consecutivos; delta correto (apenas registros novos); Supabase populado com 3 anos de histórico
- **Fase 2:** `dbt test` 100% passando; reconciliação ≤ 0,1% de desvio; Gold ≤ 900 MB; `dbt run` incremental diário < 2 min
- **Fase 3:** 6 dashboards aprovados; Incremental Refresh funcionando (< 30s para fato_venda); usuários-chave treinados
- **Fase 4:** Modelos preditivos com métricas aprovadas; self-service workspace ativo

### Critérios Gerais
- Latência de dados conforme SLA por dashboard (D-1 ou 2× ao dia)
- Disponibilidade dos pipelines GitHub Actions ≥ 99%
- Nenhuma violação de LGPD identificada em auditoria interna

---

## 15. Glossário

| Termo | Definição |
|-------|-----------|
| OTD | On-Time Delivery — % de entregas realizadas dentro do prazo prometido |
| SFS | Ship from Store — entrega expedida a partir de loja física |
| RFM | Recência, Frequência, Valor Monetário — modelo de segmentação de clientes |
| Historical LTV | Receita líquida total acumulada por cliente (não preditivo) |
| CMV | Custo da Mercadoria Vendida |
| EBITDA | Lucro antes de juros, impostos, depreciação e amortização |
| CAC | Custo de Aquisição de Cliente |
| ROAS | Return on Ad Spend — retorno sobre investimento em mídia paga |
| SCD | Slowly Changing Dimension — gestão de histórico de dimensões |
| SKU | Stock Keeping Unit — código único de produto |
| CDC | Change Data Capture — captura incremental de mudanças no banco |
| Incremental Refresh | Funcionalidade do Power BI que recarrega apenas partições de dados novas |
| RangeStart / RangeEnd | Parâmetros M obrigatórios para Incremental Refresh no Power BI |
| RIPD | Registro de Atividades de Tratamento de Dados (LGPD Art. 37) |
| DPO | Data Protection Officer (Encarregado LGPD) |
| HMAC-SHA256 | Algoritmo de hash criptográfico com chave secreta — usado para pseudonimização |
| Watermark | Valor do último `updated_at` processado com sucesso — controla ingestão incremental |
| Supabase | Plataforma BaaS open-source baseada em PostgreSQL — usada como fonte OLTP do projeto |
