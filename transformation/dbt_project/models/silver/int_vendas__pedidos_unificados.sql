{{
    config(
        unique_key='id_pedido',
        post_hook="ANALYZE {{ this }}"
    )
}}

/*
  Modelo intermediário de pedidos:
  - Une pedidos com seus itens (agregado)
  - Aplica hierarquia de status (cancelado > devolvido > entregue)
  - Calcula métricas derivadas de margem e desconto
  - Identifica se o pedido tem devolução
*/

WITH pedidos AS (
    SELECT * FROM {{ ref('stg_vendas__pedidos') }}
),
itens_agg AS (
    SELECT
        id_pedido,
        COUNT(*)                              AS qtd_itens,
        SUM(qtd_vendida)                      AS qtd_total_produtos,
        SUM(valor_liquido_item)               AS valor_itens_liquido,
        SUM(qtd_vendida * custo_unitario)     AS custo_total
    FROM {{ ref('stg_vendas__itens_pedido') }}
    GROUP BY id_pedido
),
devolucoes_agg AS (
    SELECT
        id_pedido,
        COUNT(*)                              AS qtd_devolucoes,
        SUM(valor_devolvido)                  AS valor_devolvido_total
    FROM {{ ref('stg_vendas__devolucoes') }}
    WHERE status = 'aprovada'
    GROUP BY id_pedido
),
status_hierarquia AS (
    SELECT
        p.id_pedido,
        CASE
            WHEN p.status = 'cancelado'                                  THEN 'cancelado'
            WHEN d.qtd_devolucoes > 0 OR p.status = 'devolvido'         THEN 'devolvido'
            WHEN p.status = 'entregue'                                   THEN 'entregue'
            WHEN p.status = 'enviado'                                    THEN 'enviado'
            ELSE p.status
        END AS status_final
    FROM pedidos p
    LEFT JOIN devolucoes_agg d ON d.id_pedido = p.id_pedido
)
SELECT
    p.id_pedido,
    p.id_cliente,
    p.id_loja,
    p.canal_venda,
    sh.status_final                                           AS status,
    p.dt_pedido,
    CAST(p.dt_pedido AS DATE)                                AS dt_pedido_data,
    p.dt_confirmacao,
    p.dt_cancelamento,
    p.valor_bruto,
    p.valor_desconto,
    p.valor_frete,
    p.valor_liquido,
    COALESCE(ia.qtd_itens, 0)                                AS qtd_itens,
    COALESCE(ia.qtd_total_produtos, 0)                       AS qtd_total_produtos,
    COALESCE(ia.custo_total, 0)                              AS custo_total,
    -- Margem bruta
    ROUND(p.valor_liquido - COALESCE(ia.custo_total, 0), 2) AS margem_bruta,
    -- Taxa de desconto: desc / (desc + liq)
    CASE
        WHEN p.valor_bruto > 0
        THEN ROUND(p.valor_desconto / p.valor_bruto, 4)
        ELSE 0
    END                                                      AS taxa_desconto,
    p.parcelas,
    p.metodo_pagamento,
    p.cupom,
    p.id_campanha,
    COALESCE(da.qtd_devolucoes, 0)                           AS qtd_devolucoes,
    COALESCE(da.valor_devolvido_total, 0)                    AS valor_devolvido_total,
    p.updated_at,
    p._ingested_at
FROM pedidos p
LEFT JOIN itens_agg       ia ON ia.id_pedido = p.id_pedido
LEFT JOIN devolucoes_agg  da ON da.id_pedido = p.id_pedido
LEFT JOIN status_hierarquia sh ON sh.id_pedido = p.id_pedido
{% if is_incremental() %}
WHERE p._ingested_at > (
    SELECT COALESCE(MAX(_ingested_at), '1970-01-01'::TIMESTAMPTZ) FROM {{ this }}
)
{% endif %}
