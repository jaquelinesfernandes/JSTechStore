# Dicionário de Métricas Power BI — JSTechStore Brasil

**Versão:** 1.0  
**Data:** 2026-07-22  
**Autor:** Equipe de Engenharia de Dados

---

## Convenções

| Símbolo | Significado |
|---------|-------------|
| `fv` | `fato_venda` |
| `ffe` | `fato_financeiro` |
| `fen` | `fato_entrega` |
| `fes` | `fato_estoque` |
| `fci` | `fato_cliente_interacao` |
| `dc` | `dim_cliente` |
| `dp` | `dim_produto` |
| `dl` | `dim_loja` |
| `dt` | `dim_tempo` |
| `dv` | `dim_vendedor` |
| `dca` | `dim_campanha` |
| `dtr` | `dim_transportadora` |
| `dme` | `dim_modalidade_entrega` |
| `dch` | `dim_canal_venda` |

**Filtro padrão de período:** todas as medidas de período usam `dt[data_completa]` como eixo de tempo.  
**Moeda:** BRL com 2 casas decimais.  
**Atualizações:** D-1 (dados do dia anterior), exceto Logística (2×/dia).

---

## 1. Dashboard Comercial

**Audiência:** Diretores Comerciais, Gerentes de Loja, Regional  
**Tabela principal:** `fato_venda`  
**Granularidade:** Dia / Semana / Mês / Canal / Loja / Vendedor / Categoria

### 1.1 Receita Bruta Total

| Campo | Detalhe |
|-------|---------|
| **Definição** | Soma do valor de venda antes de descontos |
| **Fórmula DAX** | `SUMX(fato_venda, fato_venda[valor_bruto_item])` |
| **Coluna fonte** | `fv.valor_bruto_item` |
| **Filtros obrigatórios** | Excluir `status_pedido = 'cancelado'` |
| **Granularidade** | Dia, Semana, Mês, Canal, Loja |

### 1.2 Receita Líquida

| Campo | Detalhe |
|-------|---------|
| **Definição** | Receita após descontos comerciais e devoluções |
| **Fórmula DAX** | `SUMX(fato_venda, fato_venda[valor_liquido_item])` |
| **Coluna fonte** | `fv.valor_liquido_item` |
| **Regra** | `valor_liquido_item = valor_bruto_item - desconto_valor` (descontos não negativos) |
| **Granularidade** | Dia, Semana, Mês, Canal |

### 1.3 Ticket Médio

| Campo | Detalhe |
|-------|---------|
| **Definição** | Receita líquida por pedido |
| **Fórmula DAX** | `DIVIDE([Receita Líquida], DISTINCTCOUNT(fato_venda[id_pedido_nk]))` |
| **Chave de pedido** | `fv.id_pedido_nk` (degenerate key) |
| **Granularidade** | Canal, Loja, Categoria |

### 1.4 Unidades Vendidas

| Campo | Detalhe |
|-------|---------|
| **Definição** | Quantidade total de itens vendidos |
| **Fórmula DAX** | `SUM(fato_venda[qtd_vendida])` |
| **Coluna fonte** | `fv.qtd_vendida` |
| **Granularidade** | Produto, Categoria |

### 1.5 Taxa de Desconto Médio

| Campo | Detalhe |
|-------|---------|
| **Definição** | Percentual médio de desconto sobre receita bruta |
| **Fórmula DAX** | `DIVIDE(SUM(fato_venda[desconto_valor]), SUM(fato_venda[valor_bruto_item]))` |
| **Colunas fonte** | `fv.desconto_valor`, `fv.valor_bruto_item` |
| **Regra** | Nunca negativo; desconto zero se `desconto_valor IS NULL` |
| **Formato** | Percentual (0,00%) |

### 1.6 Mix de Canal

| Campo | Detalhe |
|-------|---------|
| **Definição** | Participação percentual de cada canal na receita líquida |
| **Fórmula DAX** | `DIVIDE([Receita Líquida], CALCULATE([Receita Líquida], ALL(dim_canal_venda)))` |
| **Canais** | Físico, Online, Marketplace |
| **Granularidade** | Mensal |

### 1.7 vs. Meta (%)

| Campo | Detalhe |
|-------|---------|
| **Definição** | Percentual de atingimento de meta por loja/vendedor |
| **Fórmula DAX** | `DIVIDE([Receita Líquida], SUM(dim_vendedor[meta_valor_mensal]))` |
| **Fonte da meta** | `dv.meta_valor_mensal` (atualizado mensalmente via dbt) |
| **Granularidade** | Loja, Vendedor, Mês |

### 1.8 vs. Período Anterior

| Campo | Detalhe |
|-------|---------|
| **YoY** | `CALCULATE([Receita Líquida], SAMEPERIODLASTYEAR(dim_tempo[data_completa]))` |
| **MoM** | `CALCULATE([Receita Líquida], DATEADD(dim_tempo[data_completa], -1, MONTH))` |
| **WoW** | `CALCULATE([Receita Líquida], DATEADD(dim_tempo[data_completa], -7, DAY))` |

### 1.9 Ranking de Lojas

| Campo | Detalhe |
|-------|---------|
| **Definição** | Posição da loja por receita e margem brutas no mês |
| **Fórmula DAX** | `RANKX(ALL(dim_loja[nome_loja]), [Receita Líquida],, DESC)` |
| **Granularidade** | Mensal |

### 1.10 Top 20 Produtos

| Campo | Detalhe |
|-------|---------|
| **Definição** | 20 SKUs com maior receita no período |
| **Implementação** | Visual de tabela com `TOPN(20, ALL(dim_produto[sku_nk]), [Receita Líquida])` |
| **Colunas exibidas** | SKU, Nome, Categoria, Receita, Margem Bruta, Unidades |

### 1.11 Performance por Vendedor

| Campo | Detalhe |
|-------|---------|
| **Definição** | Receita e atingimento de meta por consultor no mês |
| **Colunas** | `dv.nome_vendedor`, `[Receita Líquida]`, `[vs. Meta (%)]` |
| **Granularidade** | Loja, Mês |

### 1.12 Taxa de Devolução

| Campo | Detalhe |
|-------|---------|
| **Definição** | Percentual de pedidos com pelo menos um item devolvido |
| **Fórmula DAX** | `DIVIDE(CALCULATE(DISTINCTCOUNT(fato_venda[id_pedido_nk]), fato_venda[fl_devolucao] = TRUE()), DISTINCTCOUNT(fato_venda[id_pedido_nk]))` |
| **Flag fonte** | `fv.fl_devolucao` |
| **Granularidade** | Canal, Categoria |

---

## 2. Dashboard de Clientes

**Audiência:** Gerência de CRM, Marketing, Fidelidade  
**Tabelas principais:** `dim_cliente`, `fato_venda`, `fato_cliente_interacao`  
**Granularidade:** Mês / Segmento / Canal / Nível de fidelidade

### 2.1 Base Ativa de Clientes

| Campo | Detalhe |
|-------|---------|
| **Definição** | Clientes distintos com compra nos últimos 90 dias |
| **Fórmula DAX** | `CALCULATE(DISTINCTCOUNT(fato_venda[sk_cliente]), fato_venda[data_pedido] >= TODAY() - 90)` |
| **Granularidade** | Mensal |

### 2.2 Novos Clientes

| Campo | Detalhe |
|-------|---------|
| **Definição** | Clientes cuja primeira compra ocorreu no período selecionado |
| **Fórmula DAX** | `CALCULATE(DISTINCTCOUNT(dim_cliente[cpf_hash]), dim_cliente[data_primeira_compra] >= MIN(dim_tempo[data_completa]) && dim_cliente[data_primeira_compra] <= MAX(dim_tempo[data_completa]))` |
| **Coluna fonte** | `dc.data_primeira_compra` |
| **Granularidade** | Mês, Canal |

### 2.3 Taxa de Retenção

| Campo | Detalhe |
|-------|---------|
| **Definição** | Percentual de clientes que compraram em dois meses consecutivos |
| **Fórmula DAX** | `DIVIDE([Clientes Recorrentes no Mês], [Base Ativa Mês Anterior])` |
| **Granularidade** | Mensal |

### 2.4 Churn Rate

| Campo | Detalhe |
|-------|---------|
| **Definição** | Clientes que ficaram > 90 dias sem comprar / base total do mês anterior |
| **Fórmula DAX** | `DIVIDE([Clientes Inativos > 90d], [Base Total Mês Anterior])` |
| **Granularidade** | Mensal |

### 2.5 Historical LTV

| Campo | Detalhe |
|-------|---------|
| **Definição** | Soma acumulada de receita líquida por `cpf_hash` desde a primeira compra |
| **Fórmula DAX** | `CALCULATE(SUM(fato_venda[valor_liquido_item]), ALLSELECTED(dim_tempo))` agrupado por cliente |
| **Nota** | LTV histórico — não preditivo; não inclui previsão futura |
| **Granularidade** | Segmento RFM, Canal |

### 2.6 Segmentação RFM

| Campo | Detalhe |
|-------|---------|
| **Definição** | Matriz de calor com frequência × recência, intensidade = valor monetário |
| **Colunas fonte** | `dc.segmento_rfm`, `dc.score_rfm_recencia`, `dc.score_rfm_frequencia`, `dc.score_rfm_valor` |
| **Segmentos padrão** | Champions, Loyal, Potential Loyalist, At Risk, Lost, New Customer |
| **Atualização** | Mensal via dbt (`int_clientes__unificados` com macro `rfm_score.sql`) |

### 2.7 Análise de Cohort

| Campo | Detalhe |
|-------|---------|
| **Definição** | Percentual de retenção mês a mês por coorte de aquisição (mês da 1ª compra) |
| **Implementação** | Tabela DAX usando `dc.data_primeira_compra` truncada ao mês como coorte |
| **Granularidade** | Trimestral (coortes mensais exibidas em tabela de cohorte) |

### 2.8 Programa Fidelidade

| Campo | Detalhe |
|-------|---------|
| **Pontos emitidos** | `SUM(fato_venda[techpoints_emitidos])` |
| **Pontos resgatados** | `SUM(fato_venda[techpoints_resgatados])` |
| **Saldo** | `[Pontos emitidos] - [Pontos resgatados]` |
| **Nível** | `dc.nivel_fidelidade` (Bronze, Prata, Ouro, Diamante) |
| **Granularidade** | Mensal, Nível |

### 2.9 Clientes Omnichannel

| Campo | Detalhe |
|-------|---------|
| **Definição** | Clientes com compras em canal físico E online no período |
| **Fórmula DAX** | `CALCULATE(DISTINCTCOUNT(fato_venda[sk_cliente]), fato_venda[canal] = "fisico") INTERSECT` com canal online |
| **Granularidade** | Mensal |

### 2.10 Ticket por Segmento

| Campo | Detalhe |
|-------|---------|
| **Definição** | Ticket médio agrupado por nível de fidelidade e segmento RFM |
| **Fórmula DAX** | `DIVIDE([Receita Líquida], DISTINCTCOUNT(fato_venda[id_pedido_nk]))` filtrado por segmento |
| **Granularidade** | Trimestral |

---

## 3. Dashboard de Produtos

**Audiência:** Compradores, Category Managers, Diretoria de Produto  
**Tabelas principais:** `fato_venda`, `fato_estoque`, `dim_produto`  
**Granularidade:** SKU / Categoria / Loja / Período

### 3.1 Giro de Estoque

| Campo | Detalhe |
|-------|---------|
| **Definição** | Unidades vendidas divididas pelo estoque médio do período |
| **Fórmula DAX** | `DIVIDE(SUM(fato_venda[qtd_vendida]), AVERAGE(fato_estoque[qtd_disponivel]))` |
| **Colunas fonte** | `fv.qtd_vendida`, `fes.qtd_disponivel` |
| **Granularidade** | SKU, Categoria |

### 3.2 Dias de Cobertura

| Campo | Detalhe |
|-------|---------|
| **Definição** | Quantos dias o estoque atual suporta, com base na venda média dos últimos 30 dias |
| **Fórmula DAX** | `DIVIDE(LASTNONBLANK(fato_estoque[qtd_disponivel], 1), DIVIDE([Unidades Vendidas 30d], 30))` |
| **Granularidade** | SKU, Loja |

### 3.3 Taxa de Ruptura

| Campo | Detalhe |
|-------|---------|
| **Definição** | Percentual de SKUs ativos com estoque zero no dia |
| **Fórmula DAX** | `DIVIDE(CALCULATE(DISTINCTCOUNT(fato_estoque[sk_produto]), fato_estoque[qtd_disponivel] = 0), DISTINCTCOUNT(fato_estoque[sk_produto]))` |
| **Granularidade** | Loja, Dia |

### 3.4 Margem por Produto

| Campo | Detalhe |
|-------|---------|
| **Definição** | Margem bruta percentual por SKU |
| **Fórmula DAX** | `DIVIDE([Margem Bruta Valor], SUM(fato_venda[valor_liquido_item]))` |
| **Margem Bruta Valor** | `SUM(fato_venda[valor_liquido_item]) - SUMX(fato_venda, fato_venda[qtd_vendida] * fato_venda[custo_unitario])` |
| **Regra** | Custo capturado no momento da transação em `fv.custo_unitario` (não na dimensão) |
| **Granularidade** | SKU, Categoria |

### 3.5 Produtos Sem Giro

| Campo | Detalhe |
|-------|---------|
| **Definição** | SKUs sem nenhuma venda em 30/60/90 dias |
| **Fórmula DAX** | `CALCULATE(DISTINCTCOUNT(dim_produto[sk_produto]), FILTER(dim_produto, CALCULATE(SUM(fato_venda[qtd_vendida]), DATESINPERIOD(dim_tempo[data_completa], TODAY(), -30, DAY)) = 0))` |
| **Granularidade** | Loja, CD |

### 3.6 Curva ABC

| Campo | Detalhe |
|-------|---------|
| **Definição** | Classificação Pareto de produtos por receita acumulada |
| **A** | Primeiros SKUs que somam 80% da receita |
| **B** | Próximos que somam 15% da receita |
| **C** | Demais (5%) |
| **Granularidade** | Categoria |

### 3.7 Top e Bottom Performers

| Campo | Detalhe |
|-------|---------|
| **Definição** | Top 10 e Bottom 10 SKUs por margem × volume |
| **Índice** | `[Margem Bruta Valor] * [Unidades Vendidas]` (normalizado) |
| **Granularidade** | Categoria |

### 3.8 Taxa de Devolução por Produto

| Campo | Detalhe |
|-------|---------|
| **Definição** | Percentual de unidades devolvidas sobre vendidas por SKU |
| **Fórmula DAX** | `DIVIDE(SUM(fato_venda[qtd_devolvida]), SUM(fato_venda[qtd_vendida]))` |
| **Granularidade** | SKU, Categoria |

### 3.9 Mix de Marca por Categoria

| Campo | Detalhe |
|-------|---------|
| **Definição** | Participação percentual de receita por fabricante/marca dentro da categoria |
| **Fórmula DAX** | `DIVIDE([Receita Líquida], CALCULATE([Receita Líquida], ALL(dim_produto[marca])))` |
| **Coluna fonte** | `dp.marca` |
| **Granularidade** | Categoria |

---

## 4. Dashboard de Logística

**Audiência:** Gerência de Logística, Operações  
**Tabelas principais:** `fato_entrega`, `dim_transportadora`, `dim_modalidade_entrega`  
**Atualização:** 2× ao dia  
**Granularidade:** Dia / Canal / Transportadora / Região / Modalidade

### 4.1 OTD (On-Time Delivery)

| Campo | Detalhe |
|-------|---------|
| **Definição** | Percentual de entregas realizadas até a data prometida |
| **Fórmula DAX** | `DIVIDE(CALCULATE(COUNT(fato_entrega[sk_entrega]), fato_entrega[fl_sla_atendido] = TRUE()), COUNT(fato_entrega[sk_entrega]))` |
| **Flag fonte** | `fen.fl_sla_atendido` (`TRUE` quando `data_efetiva <= data_promessa`) |
| **Granularidade** | Dia, Canal, Transportadora |

### 4.2 Tempo Médio de Entrega

| Campo | Detalhe |
|-------|---------|
| **Definição** | Média de dias entre data do pedido e data efetiva de entrega |
| **Fórmula DAX** | `AVERAGEX(fato_entrega, fato_entrega[dias_para_entrega])` |
| **Coluna fonte** | `fen.dias_para_entrega` |
| **Granularidade** | Região, Canal, Modalidade |

### 4.3 SLA por Transportadora

| Campo | Detalhe |
|-------|---------|
| **Definição** | OTD agrupado por parceiro logístico |
| **Implementação** | Medida `[OTD]` segmentada por `dim_transportadora[nome_transportadora]` |
| **Granularidade** | Mensal, Transportadora |

### 4.4 Ship from Store vs CD

| Campo | Detalhe |
|-------|---------|
| **Definição** | Percentual de pedidos expedidos de loja física vs centro de distribuição |
| **Fórmula DAX** | `DIVIDE(CALCULATE(COUNT(fato_entrega[sk_entrega]), fato_entrega[origem_expedicao] = "loja"), COUNT(fato_entrega[sk_entrega]))` |
| **Coluna fonte** | `fen.origem_expedicao` |
| **Granularidade** | Canal, Dia |

### 4.5 Taxa de Avaria

| Campo | Detalhe |
|-------|---------|
| **Definição** | Percentual de entregas com registro de avaria |
| **Fórmula DAX** | `DIVIDE(CALCULATE(COUNT(fato_entrega[sk_entrega]), fato_entrega[fl_avaria] = TRUE()), COUNT(fato_entrega[sk_entrega]))` |
| **Granularidade** | Transportadora, Mensal |

### 4.6 Custo de Frete / Receita

| Campo | Detalhe |
|-------|---------|
| **Definição** | Custo total de frete como percentual da receita líquida |
| **Fórmula DAX** | `DIVIDE(SUM(fato_entrega[custo_frete]), [Receita Líquida])` |
| **Granularidade** | Canal, Mensal |

### 4.7 Pedidos em Aberto (Aging)

| Campo | Detalhe |
|-------|---------|
| **Definição** | Pedidos sem entrega confirmada, classificados por faixa de dias em aberto |
| **Faixas** | 0–3 dias, 4–7 dias, 8–15 dias, >15 dias |
| **Fórmula DAX** | `CALCULATE(COUNT(fato_entrega[sk_entrega]), fato_entrega[data_efetiva] = BLANK())` agrupado por faixa |
| **Granularidade** | Dia |

---

## 5. Dashboard Financeiro

**Audiência:** CFO, Controladoria, Diretoria  
**Tabelas principais:** `fato_financeiro`, `fato_venda`  
**Atualização:** D-1  
**Granularidade:** Mês / Canal / Categoria

### 5.1 Receita Bruta

| Campo | Detalhe |
|-------|---------|
| **Definição** | Soma de todos os lançamentos de receita antes de deduções |
| **Fórmula DAX** | `CALCULATE(SUM(fato_financeiro[valor]), fato_financeiro[tipo_lancamento] = "receita_bruta")` |
| **Granularidade** | Mês, Canal |

### 5.2 Receita Líquida

| Campo | Detalhe |
|-------|---------|
| **Definição** | Receita bruta menos devoluções, impostos e descontos |
| **Fórmula DAX** | `[Receita Bruta FF] - [Devoluções FF] - [Impostos FF] - [Descontos FF]` |
| **Coluna fonte** | `ffe.tipo_lancamento` com valores: `receita_bruta`, `devolucao`, `imposto`, `desconto` |
| **Granularidade** | Mês, Canal |

### 5.3 CMV (Custo da Mercadoria Vendida)

| Campo | Detalhe |
|-------|---------|
| **Definição** | Custo total dos produtos vendidos no período |
| **Fórmula DAX** | `SUMX(fato_venda, fato_venda[qtd_vendida] * fato_venda[custo_unitario])` |
| **Granularidade** | Categoria, Mês |

### 5.4 Margem Bruta

| Campo | Detalhe |
|-------|---------|
| **Valor** | `[Receita Líquida] - [CMV]` |
| **Percentual** | `DIVIDE([Margem Bruta Valor], [Receita Líquida])` |
| **Granularidade** | Mês, Canal, Categoria |

### 5.5 EBITDA

| Campo | Detalhe |
|-------|---------|
| **Definição** | Margem bruta menos despesas operacionais (excluindo D&A) |
| **Fórmula DAX** | `[Margem Bruta Valor] - CALCULATE(SUM(fato_financeiro[valor]), fato_financeiro[tipo_lancamento] = "despesa_operacional")` |
| **Granularidade** | Mensal |

### 5.6 Receita por Canal

| Campo | Detalhe |
|-------|---------|
| **Definição** | Receita líquida segmentada por canal de venda |
| **Canais** | Físico, Online, Marketplace |
| **Granularidade** | Mensal |

### 5.7 Budget vs. Realizado

| Campo | Detalhe |
|-------|---------|
| **Definição** | Comparação entre receita/margem projetadas e realizadas |
| **Realizado** | `[Receita Líquida]` ou `[Margem Bruta Valor]` |
| **Budget** | `SUM(fato_orcamento[valor_orcado])` filtrado pelo tipo |
| **Desvio (%)** | `DIVIDE([Realizado] - [Budget], [Budget])` |
| **Granularidade** | Mês, Canal |

### 5.8 Contas a Receber

| Campo | Detalhe |
|-------|---------|
| **Definição** | Aging de recebíveis por faixa de vencimento |
| **Faixas** | A vencer, 1–30d vencido, 31–60d, 61–90d, >90d |
| **Fórmula DAX** | `CALCULATE(SUM(fato_financeiro[valor_parcela]), FILTER(fato_financeiro, fato_financeiro[dt_vencimento] >= <faixa_inicio> && ...))` |
| **Granularidade** | Mensal |

### 5.9 Análise de Parcelamento

| Campo | Detalhe |
|-------|---------|
| **% Parceladas** | `DIVIDE(CALCULATE(COUNT(fato_financeiro[id_parcela]), fato_financeiro[nr_parcelas] > 1), COUNT(fato_financeiro[id_parcela]))` |
| **Prazo Médio** | `AVERAGE(fato_financeiro[nr_parcelas])` |
| **Concentração** | Distribuição de parcelas por faixa de número de parcelas |
| **Granularidade** | Mensal, Canal |

---

## 6. Dashboard de Marketing

**Audiência:** Gerência de Marketing, Growth  
**Tabelas principais:** `fato_cliente_interacao`, `dim_campanha`, `fato_venda`  
**Atualização:** Diária  
**Granularidade:** Campanha / Canal / Dia

### 6.1 ROI de Campanha

| Campo | Detalhe |
|-------|---------|
| **Definição** | Retorno sobre investimento por campanha |
| **Fórmula DAX** | `DIVIDE([Receita Atribuída] - SUM(dim_campanha[custo_campanha]), SUM(dim_campanha[custo_campanha]))` |
| **Granularidade** | Campanha, Canal |

### 6.2 ROAS

| Campo | Detalhe |
|-------|---------|
| **Definição** | Receita atribuída dividida pelo investimento em mídia paga |
| **Fórmula DAX** | `DIVIDE([Receita Atribuída], CALCULATE(SUM(dim_campanha[custo_campanha]), dim_campanha[tipo] = "pago"))` |
| **Granularidade** | Canal Pago |

### 6.3 CAC (Custo de Aquisição de Cliente)

| Campo | Detalhe |
|-------|---------|
| **Definição** | Custo total da campanha dividido pelo número de novos clientes adquiridos |
| **Fórmula DAX** | `DIVIDE(SUM(dim_campanha[custo_campanha]), [Novos Clientes])` |
| **Granularidade** | Campanha, Canal |

### 6.4 Funil de Conversão

| Campo | Detalhe |
|-------|---------|
| **Definição** | Volume em cada etapa: Impressões → Cliques → Sessões → Compras |
| **Impressões** | `SUM(fato_cliente_interacao[impressoes])` |
| **Cliques** | `SUM(fato_cliente_interacao[cliques])` |
| **Sessões** | `SUM(fato_cliente_interacao[sessoes])` |
| **Compras** | `DISTINCTCOUNT(fato_venda[id_pedido_nk])` atribuídas à campanha |
| **Granularidade** | Campanha, Canal |

### 6.5 Taxa de Conversão

| Campo | Detalhe |
|-------|---------|
| **Definição** | Compras divididas por sessões no site |
| **Fórmula DAX** | `DIVIDE([Compras], [Sessões])` |
| **Granularidade** | Dia, Campanha |

### 6.6 Abandono de Carrinho

| Campo | Detalhe |
|-------|---------|
| **Definição** | Carrinhos iniciados sem compra concluída |
| **Fórmula DAX** | `DIVIDE(CALCULATE(COUNT(fato_cliente_interacao[sk_interacao]), fato_cliente_interacao[tipo_evento] = "carrinho_abandonado"), CALCULATE(COUNT(fato_cliente_interacao[sk_interacao]), fato_cliente_interacao[tipo_evento] IN {"carrinho_iniciado","carrinho_abandonado","compra"}))` |
| **Granularidade** | Dia |

### 6.7 Receita Atribuída

| Campo | Detalhe |
|-------|---------|
| **Definição** | Receita de pedidos atribuídos a uma campanha (modelo last-touch) |
| **Fórmula DAX** | `CALCULATE([Receita Líquida], NOT ISBLANK(fato_venda[sk_campanha]))` |
| **Modelo** | Last-touch por padrão; atribuição linear disponível via `dim_campanha[modelo_atribuicao]` |
| **Granularidade** | Campanha |

### 6.8 Clientes Reativados

| Campo | Detalhe |
|-------|---------|
| **Definição** | Clientes que estavam inativos (>90 dias) e compraram após uma campanha |
| **Fórmula DAX** | `CALCULATE(DISTINCTCOUNT(fato_venda[sk_cliente]), FILTER(dim_cliente, dim_cliente[dias_desde_ultima_compra_antes_campanha] > 90))` |
| **Granularidade** | Campanha, Mensal |

---

## 7. Métricas Transversais

Estas métricas aparecem em múltiplos dashboards.

| Métrica | Fórmula DAX | Dashboards |
|---------|-------------|-----------|
| **Receita Líquida** | `SUM(fato_venda[valor_liquido_item])` | Todos |
| **Margem Bruta (%)** | `DIVIDE([Margem Bruta Valor], [Receita Líquida])` | Comercial, Produtos, Financeiro |
| **Pedidos Totais** | `DISTINCTCOUNT(fato_venda[id_pedido_nk])` | Comercial, Clientes, Logística |
| **Clientes Únicos** | `DISTINCTCOUNT(fato_venda[sk_cliente])` | Clientes, Marketing |
| **YoY Receita** | `CALCULATE([Receita Líquida], SAMEPERIODLASTYEAR(dim_tempo[data_completa]))` | Comercial, Financeiro |
| **MoM Receita** | `CALCULATE([Receita Líquida], DATEADD(dim_tempo[data_completa], -1, MONTH))` | Todos |

---

## 8. Configuração de Incremental Refresh

### Tabela elegível: `fato_venda`

| Parâmetro | Valor |
|-----------|-------|
| **Parâmetro M `RangeStart`** | Tipo `DateTime`; valor inicial `#datetime(2024, 1, 1, 0, 0, 0)` |
| **Parâmetro M `RangeEnd`** | Tipo `DateTime`; valor inicial `#datetime(2027, 12, 31, 23, 59, 59)` |
| **Coluna de filtro** | `fato_venda[data_pedido]` (tipo `DateTime`) |
| **Arquivar dados >** | 2 anos |
| **Atualizar os últimos** | 3 dias |
| **Resultado esperado** | Delta diário ~15 MB vs. carga completa ~700 MB |

### Filtro Power Query obrigatório (na query de `fato_venda`)

```m
Table.SelectRows(
    fato_venda_source,
    each [data_pedido] >= RangeStart and [data_pedido] < RangeEnd
)
```

> **Atenção:** os parâmetros `RangeStart` e `RangeEnd` devem ser do tipo `DateTime`
> (não `Date`), caso contrário o Incremental Refresh não é reconhecido pelo Power BI Service.

---

## 9. Limites e SLAs

| Item | Limite | Ação se excedido |
|------|--------|-----------------|
| Tamanho do dataset Power BI Pro | 1 GB | Agregar fato_venda anualmente; considerar PPU |
| Gold DuckDB alvo | ≤ 900 MB | Rodar `scripts/compact_gold.py` (agregação anual) |
| Tempo de refresh (fato_venda com IR) | < 30s | Verificar se IR está ativo; checar tamanho da janela |
| Refresh máximo/dia | 8× (Pro) / 48× (PPU) | Consolidar em 1×/dia após pipeline |
| Tempo máximo de refresh total | 2 horas (Pro) | Aumentar agregações; migrar para PPU |
