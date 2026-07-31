# Dicionário de Métricas Power BI — JSTechStore Brasil

**Versão:** 2.0 (colunas validadas contra schema Gold real)
**Data:** 2026-07-22

---

## Schema de Referência Rápida

### fato_venda
| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `sk_venda` | VARCHAR | Surrogate key |
| `sk_cliente` | VARCHAR | FK → dim_cliente |
| `sk_produto` | VARCHAR | FK → dim_produto |
| `sk_loja` | VARCHAR | FK → dim_loja |
| `sk_tempo` | INTEGER | FK → dim_tempo |
| `sk_canal_venda` | VARCHAR | FK → dim_canal_venda |
| `sk_campanha` | VARCHAR | FK → dim_campanha (nullable) |
| `id_pedido_dg` | INTEGER | Chave degenerada do pedido |
| `id_item_pedido_dg` | INTEGER | Chave degenerada do item |
| `dt_pedido_data` | DATE | Data do pedido (usar para Incremental Refresh) |
| `dt_pedido` | TIMESTAMP TZ | Timestamp completo do pedido |
| `qtd_vendida` | INTEGER | Unidades do item |
| `preco_unitario` | DECIMAL(12,2) | Preço de venda unitário |
| `custo_unitario` | DECIMAL(12,2) | CMV unitário (capturado na transação) |
| `desconto_item` | DECIMAL(10,2) | Desconto no item |
| `valor_liquido_item` | DECIMAL(12,2) | Receita líquida do item |
| `margem_bruta_item` | DECIMAL(18,2) | Margem bruta do item |
| `taxa_desconto_item` | DOUBLE | % de desconto no item |
| `valor_bruto_pedido` | DECIMAL(12,2) | Total bruto do pedido |
| `valor_desconto_pedido` | DECIMAL(12,2) | Total desconto do pedido |
| `valor_frete_pedido` | DECIMAL(10,2) | Frete do pedido |
| `valor_liquido_pedido` | DECIMAL(12,2) | Total líquido do pedido |
| `qtd_itens_pedido` | BIGINT | Qtd de linhas de item no pedido |
| `parcelas` | INTEGER | Número de parcelas |
| `metodo_pagamento` | VARCHAR | Forma de pagamento |
| `status` | VARCHAR | Status do pedido |
| `fl_venda_valida` | BOOLEAN | Pedido não cancelado nem devolvido |
| `fl_cancelado` | BOOLEAN | Pedido cancelado |
| `fl_devolvido` | BOOLEAN | Pedido com devolução |
| `fl_online` | BOOLEAN | Canal online (TRUE) vs físico (FALSE) |
| `valor_comissao` | DECIMAL(12,2) | Comissão do vendedor |
| `canal_venda` | VARCHAR | Nome do canal (desnormalizado) |

### fato_entrega
| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `sk_entrega` | VARCHAR | Surrogate key |
| `sk_transportadora` | VARCHAR | FK → dim_transportadora |
| `sk_modalidade_entrega` | VARCHAR | FK → dim_modalidade_entrega |
| `id_pedido_dg` | INTEGER | Chave degenerada do pedido |
| `dt_postagem` | DATE | Data de postagem |
| `dt_promessa` | DATE | Data prometida de entrega |
| `dt_efetiva` | DATE | Data efetiva de entrega |
| `lead_time_prometido_dias` | BIGINT | Prazo prometido em dias |
| `lead_time_real_dias` | BIGINT | Prazo real em dias |
| `atraso_dias` | BIGINT | Dias de atraso (0 se no prazo) |
| `fl_sla_atendido` | BOOLEAN | TRUE se `dt_efetiva <= dt_promessa` |
| `fl_entregue` | BOOLEAN | Entrega confirmada |
| `status` | VARCHAR | Status da entrega |
| `canal_venda` | VARCHAR | Canal de origem do pedido |

### fato_financeiro
| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `sk_lancamento` | VARCHAR | Surrogate key |
| `sk_loja` | VARCHAR | FK → dim_loja |
| `sk_tempo_competencia` | INTEGER | FK → dim_tempo |
| `id_pedido_dg` | INTEGER | Chave degenerada do pedido |
| `tipo` | VARCHAR | Tipo do lançamento (receita, despesa, etc.) |
| `valor` | DECIMAL(12,2) | Valor do lançamento |
| `dt_lancamento` | DATE | Data do lançamento |
| `dt_competencia` | DATE | Data de competência |
| `valor_sinal` | DECIMAL(12,2) | Valor com sinal (positivo/negativo) |
| `status_cr` | VARCHAR | Status de contas a receber |
| `dt_pagamento` | DATE | Data de pagamento efetivo |
| `valor_pago` | DECIMAL(12,2) | Valor pago |
| `fl_pago` | BOOLEAN | Pagamento confirmado |

### fato_orcamento
| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `sk_orcamento` | VARCHAR | Surrogate key |
| `sk_loja` | VARCHAR | FK → dim_loja |
| `sk_tempo` | INTEGER | FK → dim_tempo |
| `canal_venda` | VARCHAR | Canal de venda |
| `ano` / `mes` | INTEGER | Período |
| `valor_meta_receita` | DECIMAL(14,2) | Meta de receita do período |
| `valor_meta_margem` | DECIMAL(14,2) | Meta de margem |
| `qtd_meta_pedidos` | INTEGER | Meta de pedidos |
| `receita_realizada` | DECIMAL(38,2) | Receita realizada (pré-calculada) |
| `margem_realizada` | DECIMAL(38,2) | Margem realizada |
| `qtd_pedidos_realizados` | BIGINT | Pedidos realizados |
| `var_receita_pct` | DOUBLE | Variação % receita vs meta |
| `var_margem_pct` | DOUBLE | Variação % margem vs meta |
| `fl_meta_receita_atingida` | BOOLEAN | Meta de receita atingida |

### fato_cliente_interacao
| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `sk_sessao` | VARCHAR | Surrogate key (1 sessão = 1 linha) |
| `sk_cliente` | VARCHAR | FK → dim_cliente |
| `sk_tempo` | INTEGER | FK → dim_tempo |
| `id_pedido_dg` | INTEGER | Pedido gerado (nullable) |
| `canal_origem` | VARCHAR | Canal de origem da sessão |
| `device_type` | VARCHAR | Tipo de dispositivo |
| `dt_sessao` | DATE | Data da sessão |
| `paginas_visitadas` | INTEGER | Páginas visitadas na sessão |
| `duracao_min` | DOUBLE | Duração em minutos |
| `converteu` | BOOLEAN | Sessão gerou compra |
| `qtd_produtos_vistos` | BIGINT | Produtos visualizados |
| `qtd_add_cart` | HUGEINT | Adições ao carrinho |
| `qtd_remove_cart` | HUGEINT | Remoções do carrinho |
| `qtd_compras` | HUGEINT | Compras concluídas na sessão |
| `fl_abandono_carrinho` | BOOLEAN | Sessão com abandono de carrinho |

### dim_cliente
| Coluna relevante | Tipo | Descrição |
|-----------------|------|-----------|
| `sk_cliente` | VARCHAR | Surrogate key |
| `nivel_fidelidade` | VARCHAR | Bronze / Prata / Ouro / Diamante |
| `segmento_rfm` | VARCHAR | Segmento RFM (Champions, At Risk, etc.) |
| `score_recencia` | INTEGER | Score RFM — recência (1–5) |
| `score_frequencia` | INTEGER | Score RFM — frequência (1–5) |
| `score_monetario` | INTEGER | Score RFM — valor monetário (1–5) |
| `ltv` | DECIMAL(38,2) | LTV histórico acumulado |
| `recencia_dias` | INTEGER | Dias desde última compra |
| `ultima_compra` | DATE | Data da última compra |
| `primeira_compra` | DATE | Data da primeira compra |
| `qtd_pedidos` | BIGINT | Total de pedidos histórico |
| `saldo_techpoints` | INTEGER | Saldo de pontos fidelidade |
| `fl_current` | BOOLEAN | Registro SCD2 ativo (sempre filtrar TRUE) |

### dim_tempo
| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `sk_tempo` | INTEGER | Surrogate key (formato YYYYMMDD) |
| `data_full` | DATE | Data completa — eixo de tempo no Power BI |
| `ano` / `mes` / `dia` | INTEGER | Componentes da data |
| `trimestre` | INTEGER | Trimestre (1–4) |
| `semana_iso` | INTEGER | Semana ISO |
| `nome_mes` | VARCHAR | Janeiro … Dezembro |
| `nome_dia_semana` | VARCHAR | Segunda … Domingo |
| `ano_mes` | VARCHAR | "2026-07" — útil para agrupamentos mensais |
| `fl_fim_de_semana` | BOOLEAN | Sábado ou domingo |
| `fl_feriado_nacional` | BOOLEAN | Feriado nacional brasileiro |
| `fl_black_friday` | BOOLEAN | Black Friday |

### dim_campanha
| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `sk_campanha` | VARCHAR | Surrogate key |
| `nome` | VARCHAR | Nome da campanha |
| `tipo` | VARCHAR | Tipo (email, pago, social, etc.) |
| `canal` | VARCHAR | Canal de mídia |
| `orcamento` | DECIMAL(12,2) | Investimento da campanha |
| `objetivo` | VARCHAR | Objetivo da campanha |

---

## 1. Dashboard Comercial

**Tabela principal:** `fato_venda` | **Eixo de tempo:** `dim_tempo[data_full]`

### 1.1 Receita Bruta Total
```dax
Receita Bruta =
SUMX(
    FILTER(fato_venda, fato_venda[fl_cancelado] = FALSE()),
    fato_venda[preco_unitario] * fato_venda[qtd_vendida]
)
-- Não existe coluna valor_bruto_item; calcular como preco_unitario × qtd_vendida
```

### 1.2 Receita Líquida
```dax
Receita Liquida = SUM(fato_venda[valor_liquido_item])
-- Filtro recomendado: fato_venda[fl_venda_valida] = TRUE()
```

### 1.3 Ticket Médio
```dax
Ticket Medio =
DIVIDE(
    [Receita Liquida],
    DISTINCTCOUNT(fato_venda[id_pedido_dg])
)
```

### 1.4 Unidades Vendidas
```dax
Unidades Vendidas = SUM(fato_venda[qtd_vendida])
```

### 1.5 Taxa de Desconto Médio
```dax
Taxa Desconto =
DIVIDE(
    SUM(fato_venda[desconto_item]),
    SUMX(fato_venda, fato_venda[preco_unitario] * fato_venda[qtd_vendida])
)
-- Formatar como percentual (%)
```

### 1.6 Mix de Canal
```dax
Mix Canal % =
DIVIDE(
    [Receita Liquida],
    CALCULATE([Receita Liquida], ALL(fato_venda[canal_venda]))
)
-- Segmentar por fato_venda[canal_venda] no visual
```

### 1.7 Atingimento de Meta
```dax
-- Usar fato_orcamento (já tem receita_realizada e valor_meta_receita pré-calculados)
Atingimento Meta % =
DIVIDE(
    SUM(fato_orcamento[receita_realizada]),
    SUM(fato_orcamento[valor_meta_receita])
)
```

### 1.8 YoY / MoM / WoW
```dax
Receita YoY = CALCULATE([Receita Liquida], SAMEPERIODLASTYEAR(dim_tempo[data_full]))
Receita MoM = CALCULATE([Receita Liquida], DATEADD(dim_tempo[data_full], -1, MONTH))
Receita WoW = CALCULATE([Receita Liquida], DATEADD(dim_tempo[data_full], -7, DAY))
```

### 1.9 Ranking de Lojas
```dax
Rank Loja Receita =
RANKX(ALL(dim_loja[nome_loja]), [Receita Liquida],, DESC, DENSE)
```

### 1.10 Taxa de Devolução
```dax
Taxa Devolucao =
DIVIDE(
    CALCULATE(DISTINCTCOUNT(fato_venda[id_pedido_dg]), fato_venda[fl_devolvido] = TRUE()),
    DISTINCTCOUNT(fato_venda[id_pedido_dg])
)
```

### 1.11 Margem Bruta
```dax
Margem Bruta Valor = SUM(fato_venda[margem_bruta_item])

Margem Bruta % =
DIVIDE([Margem Bruta Valor], [Receita Liquida])
```

---

## 2. Dashboard de Clientes

**Tabelas principais:** `dim_cliente`, `fato_venda` | Filtrar sempre `dim_cliente[fl_current] = TRUE()`

### 2.1 Base Ativa de Clientes
```dax
Clientes Ativos 90d =
CALCULATE(
    DISTINCTCOUNT(fato_venda[sk_cliente]),
    fato_venda[dt_pedido_data] >= TODAY() - 90,
    fato_venda[fl_venda_valida] = TRUE()
)
```

### 2.2 Novos Clientes
```dax
-- dim_cliente[primeira_compra] guarda a data da 1ª compra
Novos Clientes =
CALCULATE(
    DISTINCTCOUNT(dim_cliente[sk_cliente]),
    dim_cliente[fl_current] = TRUE(),
    dim_cliente[primeira_compra] >= MIN(dim_tempo[data_full]),
    dim_cliente[primeira_compra] <= MAX(dim_tempo[data_full])
)
```

### 2.3 LTV Histórico
```dax
-- dim_cliente[ltv] já é pré-calculado pelo dbt
LTV Medio =
CALCULATE(
    AVERAGE(dim_cliente[ltv]),
    dim_cliente[fl_current] = TRUE()
)
```

### 2.4 Segmentação RFM
```dax
-- Usar dim_cliente[segmento_rfm] diretamente como dimensão em matriz
-- Scores individuais: score_recencia, score_frequencia, score_monetario (1–5)
Clientes por Segmento =
CALCULATE(
    DISTINCTCOUNT(dim_cliente[sk_cliente]),
    dim_cliente[fl_current] = TRUE()
)
-- Segmentar por dim_cliente[segmento_rfm] no visual
```

### 2.5 Programa Fidelidade — Saldo TechPoints
```dax
-- saldo_techpoints está pré-calculado em dim_cliente
Total TechPoints Saldo =
CALCULATE(
    SUM(dim_cliente[saldo_techpoints]),
    dim_cliente[fl_current] = TRUE()
)
```

### 2.6 Abandono de Carrinho
```dax
-- fato_cliente_interacao tem fl_abandono_carrinho
Taxa Abandono Carrinho =
DIVIDE(
    CALCULATE(COUNT(fato_cliente_interacao[sk_sessao]),
              fato_cliente_interacao[fl_abandono_carrinho] = TRUE()),
    CALCULATE(COUNT(fato_cliente_interacao[sk_sessao]),
              fato_cliente_interacao[qtd_add_cart] > 0)
)
```

---

## 3. Dashboard de Produtos

**Tabelas principais:** `fato_venda`, `fato_estoque`, `dim_produto`

### 3.1 Giro de Estoque
```dax
Giro Estoque =
DIVIDE(
    SUM(fato_venda[qtd_vendida]),
    AVERAGE(fato_estoque[qtd_disponivel])
)
```

### 3.2 Dias de Cobertura
```dax
Venda Media Diaria 30d =
CALCULATE(
    DIVIDE(SUM(fato_venda[qtd_vendida]), 30),
    DATESINPERIOD(dim_tempo[data_full], TODAY(), -30, DAY)
)

Dias Cobertura =
DIVIDE(
    CALCULATE(LASTNONBLANK(fato_estoque[qtd_disponivel], 1)),
    [Venda Media Diaria 30d]
)
```

### 3.3 Taxa de Ruptura
```dax
-- fato_estoque[fl_ruptura] = TRUE quando qtd_disponivel = 0
Taxa Ruptura =
DIVIDE(
    CALCULATE(DISTINCTCOUNT(fato_estoque[sk_produto]),
              fato_estoque[fl_ruptura] = TRUE()),
    DISTINCTCOUNT(fato_estoque[sk_produto])
)
```

### 3.4 Margem por Produto
```dax
-- margem_bruta_item já calculado em fato_venda
Margem Produto % =
DIVIDE(
    SUM(fato_venda[margem_bruta_item]),
    SUM(fato_venda[valor_liquido_item])
)
-- Segmentar por dim_produto[nome_produto] ou [categoria]
```

---

## 4. Dashboard de Logística

**Tabela principal:** `fato_entrega`

### 4.1 OTD (On-Time Delivery)
```dax
OTD % =
DIVIDE(
    CALCULATE(COUNT(fato_entrega[sk_entrega]),
              fato_entrega[fl_sla_atendido] = TRUE()),
    COUNT(fato_entrega[sk_entrega])
)
```

### 4.2 Tempo Médio de Entrega
```dax
Lead Time Medio Dias = AVERAGE(fato_entrega[lead_time_real_dias])
```

### 4.3 Atraso Médio
```dax
Atraso Medio Dias =
CALCULATE(
    AVERAGE(fato_entrega[atraso_dias]),
    fato_entrega[fl_sla_atendido] = FALSE()
)
```

### 4.4 Pedidos em Aberto (Aging)
```dax
-- fl_entregue = FALSE indica pendente
Pedidos Abertos =
CALCULATE(
    COUNT(fato_entrega[sk_entrega]),
    fato_entrega[fl_entregue] = FALSE()
)
```

### 4.5 Custo de Frete / Receita
```dax
-- valor_frete_pedido está em fato_venda, não em fato_entrega
Custo Frete Pct Receita =
DIVIDE(
    SUM(fato_venda[valor_frete_pedido]),
    [Receita Liquida]
)
```

---

## 5. Dashboard Financeiro

**Tabelas principais:** `fato_financeiro`, `fato_orcamento`

### 5.1 Receita Bruta / Líquida
```dax
-- Usar fato_venda como fonte primária (mais granular)
Receita Bruta FF =
CALCULATE(
    SUM(fato_financeiro[valor]),
    fato_financeiro[tipo] = "receita"
)
```

### 5.2 Budget vs. Realizado
```dax
-- fato_orcamento tem ambos pré-calculados pelo dbt
Budget Receita = SUM(fato_orcamento[valor_meta_receita])
Realizado Receita = SUM(fato_orcamento[receita_realizada])

Variacao Receita % = SUM(fato_orcamento[var_receita_pct])
-- Ou calcular manualmente: DIVIDE([Realizado] - [Budget], [Budget])
```

### 5.3 CMV
```dax
CMV Total =
SUMX(fato_venda, fato_venda[qtd_vendida] * fato_venda[custo_unitario])
```

### 5.4 Contas a Receber (Aging)
```dax
-- Usar fato_financeiro[dt_pagamento] e [fl_pago]
CR Vencer =
CALCULATE(
    SUM(fato_financeiro[valor]),
    fato_financeiro[fl_pago] = FALSE(),
    fato_financeiro[dt_pagamento] >= TODAY()
)

CR Vencido =
CALCULATE(
    SUM(fato_financeiro[valor]),
    fato_financeiro[fl_pago] = FALSE(),
    fato_financeiro[dt_pagamento] < TODAY()
)
```

---

## 6. Dashboard de Marketing

**Tabelas principais:** `fato_cliente_interacao`, `dim_campanha`

### 6.1 Sessões e Conversão
```dax
Total Sessoes = COUNT(fato_cliente_interacao[sk_sessao])

Taxa Conversao =
DIVIDE(
    CALCULATE(COUNT(fato_cliente_interacao[sk_sessao]),
              fato_cliente_interacao[converteu] = TRUE()),
    [Total Sessoes]
)
```

### 6.2 ROI de Campanha
```dax
-- dim_campanha[orcamento] = investimento
-- Receita atribuída = fato_venda onde sk_campanha não é blank
Receita Atribuida =
CALCULATE(
    [Receita Liquida],
    NOT ISBLANK(fato_venda[sk_campanha])
)

ROI Campanha =
DIVIDE(
    [Receita Atribuida] - SUM(dim_campanha[orcamento]),
    SUM(dim_campanha[orcamento])
)
```

### 6.3 Abandono de Carrinho
```dax
-- Reutilizar medida do Dashboard de Clientes (seção 2.6)
Taxa Abandono Carrinho =
DIVIDE(
    CALCULATE(COUNT(fato_cliente_interacao[sk_sessao]),
              fato_cliente_interacao[fl_abandono_carrinho] = TRUE()),
    CALCULATE(COUNT(fato_cliente_interacao[sk_sessao]),
              fato_cliente_interacao[qtd_add_cart] > 0)
)
```

---

## 7. Configuração de Incremental Refresh

### Coluna de filtro: `fato_venda[dt_pedido_data]` (tipo DATE)

```m
// No Power Query, criar os parâmetros:
// RangeStart — tipo DateTime
// RangeEnd   — tipo DateTime

// Filtro obrigatório na query de fato_venda:
Table.SelectRows(
    fato_venda_source,
    each
        Date.From([dt_pedido_data]) >= Date.From(RangeStart) and
        Date.From([dt_pedido_data]) < Date.From(RangeEnd)
)
```

**Política recomendada:**
- Arquivar dados mais antigos que: **2 anos**
- Atualizar os últimos: **3 dias** (buffer para reprocessamento)

---

## 8. Relacionamentos no Modelo Power BI

| Tabela | Coluna | → | Tabela | Coluna | Cardinalidade |
|--------|--------|---|--------|--------|---------------|
| `fato_venda` | `sk_cliente` | → | `dim_cliente` | `sk_cliente` | N:1 |
| `fato_venda` | `sk_produto` | → | `dim_produto` | `sk_produto` | N:1 |
| `fato_venda` | `sk_loja` | → | `dim_loja` | `sk_loja` | N:1 |
| `fato_venda` | `sk_tempo` | → | `dim_tempo` | `sk_tempo` | N:1 |
| `fato_venda` | `sk_canal_venda` | → | `dim_canal_venda` | `sk_canal_venda` | N:1 |
| `fato_venda` | `sk_campanha` | → | `dim_campanha` | `sk_campanha` | N:1 |
| `fato_entrega` | `sk_transportadora` | → | `dim_transportadora` | `sk_transportadora` | N:1 |
| `fato_entrega` | `sk_modalidade_entrega` | → | `dim_modalidade_entrega` | `sk_modalidade_entrega` | N:1 |
| `fato_entrega` | `sk_loja` | → | `dim_loja` | `sk_loja` | N:1 |
| `fato_entrega` | `sk_tempo_postagem` | → | `dim_tempo` | `sk_tempo` | N:1 |
| `fato_estoque` | `sk_produto` | → | `dim_produto` | `sk_produto` | N:1 |
| `fato_estoque` | `sk_loja` | → | `dim_loja` | `sk_loja` | N:1 |
| `fato_estoque` | `sk_tempo` | → | `dim_tempo` | `sk_tempo` | N:1 |
| `fato_financeiro` | `sk_loja` | → | `dim_loja` | `sk_loja` | N:1 |
| `fato_financeiro` | `sk_tempo_competencia` | → | `dim_tempo` | `sk_tempo` | N:1 |
| `fato_orcamento` | `sk_loja` | → | `dim_loja` | `sk_loja` | N:1 |
| `fato_orcamento` | `sk_tempo` | → | `dim_tempo` | `sk_tempo` | N:1 |
| `fato_cliente_interacao` | `sk_cliente` | → | `dim_cliente` | `sk_cliente` | N:1 |
| `fato_cliente_interacao` | `sk_tempo` | → | `dim_tempo` | `sk_tempo` | N:1 |

> **Atenção SCD2:** `dim_cliente`, `dim_produto`, `dim_vendedor`, `dim_loja` têm múltiplos registros por entidade (histórico). Sempre filtrar `fl_current = TRUE()` em medidas de dimensão, ou usar o `sk_*` de `fato_venda` (que aponta para a versão correta na época da transação).

---

## 9. Limites e SLAs

| Item | Limite | Ação se excedido |
|------|--------|-----------------|
| Tamanho do dataset Power BI Pro | 1 GB | Gold atual: 362 MB — margem de 638 MB |
| Gold DuckDB alvo | ≤ 900 MB | Pipeline diário adiciona ~15 MB/dia → ~43 dias de margem |
| Tempo de refresh `fato_venda` (IR) | < 30s | Verificar se Incremental Refresh está ativo |
| Refresh máximo/dia | 8× (Pro) | Consolidar em 1×/dia após pipeline (05:30 BRT) |
