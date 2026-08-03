# Gabarito de Validação — Power BI vs Gold DuckDB

**Gerado em:** 2026-07-22  
**Fonte:** `data/gold/jstechstore.duckdb`  
**Período dos dados:** 2025-07-21 → 2026-07-20

---

## 1. Números Globais

Conferir no Power BI **sem nenhum filtro de data ou segmentação ativo**.

| KPI | Valor esperado |
|-----|---------------|
| Linhas em `fato_venda` | 221.936 |
| Pedidos distintos (`id_pedido_dg`) | 89.947 |
| Período (min → max `dt_pedido_data`) | 21/07/2025 → 20/07/2026 |
| **Receita Líquida** (`SUM valor_liquido_item` onde `fl_venda_valida = TRUE`) | **R$ 731.381.448,78** |
| **Margem Bruta** (`SUM margem_bruta_item` onde `fl_venda_valida = TRUE`) | **R$ 111.919.491,52** |
| **Margem Bruta %** | **15,3%** |
| Pedidos cancelados (`fl_cancelado = TRUE`) | 6.566 |
| Pedidos devolvidos (`fl_devolvido = TRUE`) | 8.974 |
| Clientes ativos (`dim_cliente` onde `fl_current = TRUE AND ativo = TRUE`) | 10.000 |
| Sessões web (`fato_cliente_interacao` total linhas) | 3.764.369 |
| Taxa de conversão web (`converteu = TRUE / total`) | 1,44% |
| OTD — On-Time Delivery (`fl_sla_atendido = TRUE` onde `fl_entregue = TRUE`) | 39,98% |
| Lead time médio real (dias) | 5,8 dias |
| Meses com orçamento cadastrado (`fato_orcamento`) | 13 meses |

---

## 2. Receita Líquida por Canal de Venda

Criar visual de tabela segmentado por `fato_venda[canal_venda]`.

| Canal | Pedidos distintos | Receita Líquida |
|-------|:-----------------:|----------------:|
| loja_fisica | 31.846 | R$ 275.901.495 |
| site_proprio | 20.994 | R$ 185.021.818 |
| marketplace_ml | 13.987 | R$ 122.878.850 |
| marketplace_amazon | 10.126 | R$ 88.751.531 |
| marketplace_shopee | 6.811 | R$ 58.827.754 |
| **Total** | **89.947 (apróx.)** | **R$ 731.381.448** |

> Filtro aplicado: `fl_venda_valida = TRUE`

---

## 3. Top 5 Categorias por Receita Líquida

Criar visual segmentado por `dim_produto[categoria]`.

| # | Categoria | Receita Líquida |
|---|-----------|----------------:|
| 1 | Notebooks e Desktops | R$ 251.802.603 |
| 2 | Smartphones e Tablets | R$ 225.717.617 |
| 3 | TVs e Áudio | R$ 162.695.757 |
| 4 | Games e Consoles | R$ 72.271.878 |
| 5 | Periféricos e Acessórios | R$ 18.893.593 |

---

## 4. Integridade Referencial (FK Orphans)

Todos os resultados abaixo devem ser **zero** no Gold. Se o Power BI exibir linhas em branco em dimensões, há problema de relacionamento.

| Verificação | Resultado |
|-------------|:---------:|
| `fato_venda` → `dim_cliente` (sk_cliente sem match) | ✅ 0 |
| `fato_venda` → `dim_produto` (sk_produto sem match) | ✅ 0 |
| `fato_venda` → `dim_loja` (sk_loja sem match) | ✅ 0 |
| `fato_venda` → `dim_tempo` (sk_tempo sem match) | ✅ 0 |
| `fato_venda` → `dim_canal_venda` (sk_canal_venda sem match) | ✅ 0 |
| `fato_entrega` → `dim_transportadora` (sk_transportadora sem match) | ✅ 0 |
| `fato_estoque` → `dim_produto` (sk_produto sem match) | ✅ 0 |

---

## 5. Relacionamentos Obrigatórios no Modelo Power BI

Verificar em **Modelagem → Exibição de modelo**. Todos devem ser N:1, direção de filtro da dimensão para o fato.

| Tabela Fato | Coluna FK | → | Dimensão | Coluna PK |
|-------------|-----------|---|----------|-----------|
| `fato_venda` | `sk_cliente` | → | `dim_cliente` | `sk_cliente` |
| `fato_venda` | `sk_produto` | → | `dim_produto` | `sk_produto` |
| `fato_venda` | `sk_loja` | → | `dim_loja` | `sk_loja` |
| `fato_venda` | `sk_tempo` | → | `dim_tempo` | `sk_tempo` |
| `fato_venda` | `sk_canal_venda` | → | `dim_canal_venda` | `sk_canal_venda` |
| `fato_venda` | `sk_campanha` | → | `dim_campanha` | `sk_campanha` |
| `fato_venda` | `sk_vendedor` ⚠️ | → | `dim_vendedor` | `sk_vendedor` |
| `fato_entrega` | `sk_transportadora` | → | `dim_transportadora` | `sk_transportadora` |
| `fato_entrega` | `sk_modalidade_entrega` | → | `dim_modalidade_entrega` | `sk_modalidade_entrega` |
| `fato_entrega` | `sk_loja` | → | `dim_loja` | `sk_loja` |
| `fato_entrega` | `sk_tempo_postagem` | → | `dim_tempo` | `sk_tempo` |
| `fato_estoque` | `sk_produto` | → | `dim_produto` | `sk_produto` |
| `fato_estoque` | `sk_loja` | → | `dim_loja` | `sk_loja` |
| `fato_estoque` | `sk_tempo` | → | `dim_tempo` | `sk_tempo` |
| `fato_financeiro` | `sk_loja` | → | `dim_loja` | `sk_loja` |
| `fato_financeiro` | `sk_tempo_competencia` | → | `dim_tempo` | `sk_tempo` |
| `fato_orcamento` | `sk_loja` | → | `dim_loja` | `sk_loja` |
| `fato_orcamento` | `sk_tempo` | → | `dim_tempo` | `sk_tempo` |
| `fato_cliente_interacao` | `sk_cliente` | → | `dim_cliente` | `sk_cliente` |
| `fato_cliente_interacao` | `sk_tempo` | → | `dim_tempo` | `sk_tempo` |

> ⚠️ `fato_venda[sk_vendedor]` — verificar se a coluna existe; se não existir, o relacionamento com `dim_vendedor` deve ser feito via `dim_loja` (vendedor → loja).

---

## 6. Alertas para o Modelo Power BI

### SCD Type 2 — Dimensões com histórico
`dim_cliente`, `dim_produto`, `dim_vendedor` e `dim_loja` têm múltiplos registros por entidade (histórico SCD2). O relacionamento com as tabelas fato já aponta para a versão correta via `sk_*`. Em medidas DAX que agregam diretamente a dimensão (ex: contagem de clientes), **sempre filtrar `fl_current = TRUE`**:

```dax
Clientes Ativos =
CALCULATE(
    DISTINCTCOUNT(dim_cliente[sk_cliente]),
    dim_cliente[fl_current] = TRUE()
)
```

### dim_tempo com múltiplas fatos (Role-Playing)
`dim_tempo` está ligada a múltiplas tabelas fato por colunas diferentes:
- `fato_venda[sk_tempo]` → data do pedido
- `fato_entrega[sk_tempo_postagem]` → data de postagem
- `fato_financeiro[sk_tempo_competencia]` → data de competência
- `fato_orcamento[sk_tempo]` → mês do orçamento
- `fato_cliente_interacao[sk_tempo]` → data da sessão

O Power BI só ativa **um relacionamento por vez** entre duas tabelas. Os relacionamentos secundários ficam **inativos** (linha tracejada). Use `USERELATIONSHIP()` no DAX quando precisar filtrar pelo relacionamento inativo:

```dax
-- Exemplo: receita filtrada pela data de competência financeira
Receita por Competencia =
CALCULATE(
    SUM(fato_financeiro[valor]),
    USERELATIONSHIP(fato_financeiro[sk_tempo_competencia], dim_tempo[sk_tempo])
)
```

### sk_campanha nullable
`fato_venda[sk_campanha]` é NULL para vendas sem campanha atribuída (verificado: 0 NULLs no dataset atual — todas as vendas têm campanha). O relacionamento N:1 com `dim_campanha` funciona normalmente.

---

## 7. Medidas DAX de Validação Rápida

Criar estas medidas no Power BI e comparar com a coluna "Valor esperado" acima:

```dax
[Receita Liquida] = SUM(fato_venda[valor_liquido_item])
-- Esperado (sem filtros): R$ 731.381.448,78

[Margem Bruta Valor] = SUM(fato_venda[margem_bruta_item])
-- Esperado (sem filtros): R$ 111.919.491,52

[Margem Bruta %] = DIVIDE([Margem Bruta Valor], [Receita Liquida])
-- Esperado: 15,3%

[Total Pedidos] = DISTINCTCOUNT(fato_venda[id_pedido_dg])
-- Esperado: 89.947

[OTD %] =
DIVIDE(
    CALCULATE(COUNT(fato_entrega[sk_entrega]), fato_entrega[fl_sla_atendido] = TRUE()),
    CALCULATE(COUNT(fato_entrega[sk_entrega]), fato_entrega[fl_entregue] = TRUE())
)
-- Esperado: 39,98%
```
