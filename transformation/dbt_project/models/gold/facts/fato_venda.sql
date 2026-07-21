{{
    config(
        unique_key='sk_venda',
        post_hook="ANALYZE {{ this }}"
    )
}}

/*
  Fato venda: grão = 1 linha por item de pedido.
  Power BI Incremental Refresh: filtrar por dt_pedido_data com RangeStart/RangeEnd.
  Refresh window: últimos 3 dias.
*/

WITH pedidos AS (
    SELECT * FROM {{ ref('int_vendas__pedidos_unificados') }}
    {% if is_incremental() %}
    WHERE dt_pedido_data >= (
        SELECT MAX(dt_pedido_data) - INTERVAL '3 days' FROM {{ this }}
    )
    {% endif %}
),
itens AS (
    SELECT * FROM {{ ref('stg_vendas__itens_pedido') }}
),
dc AS (SELECT sk_cliente, id_cliente_nk FROM {{ ref('dim_cliente') }} WHERE fl_current = TRUE),
dp AS (SELECT sk_produto, id_produto_nk FROM {{ ref('dim_produto') }} WHERE fl_current = TRUE),
dl AS (SELECT sk_loja,    id_loja_nk    FROM {{ ref('dim_loja') }}    WHERE fl_current = TRUE),
dt AS (SELECT sk_tempo,   data_full     FROM {{ ref('dim_tempo') }}),
dv AS (SELECT sk_vendedor, id_vendedor_nk FROM {{ ref('dim_vendedor') }} WHERE fl_current = TRUE),
dca AS (SELECT sk_canal_venda, canal_venda FROM {{ ref('dim_canal_venda') }}),
dcm AS (SELECT sk_campanha, id_campanha_nk FROM {{ ref('dim_campanha') }} WHERE fl_current = TRUE),
comissoes AS (
    SELECT id_pedido, id_vendedor, valor_comissao
    FROM {{ ref('stg_rh__comissoes') }}
)
SELECT
    -- Surrogate key: pedido + item
    {{ get_surrogate_key(['p.id_pedido', 'i.id_item_pedido']) }}        AS sk_venda,

    -- FKs para dimensões
    COALESCE(dc.sk_cliente,      'DESCONHECIDO')                        AS sk_cliente,
    COALESCE(dp.sk_produto,      'DESCONHECIDO')                        AS sk_produto,
    COALESCE(dl.sk_loja,         'DESCONHECIDO')                        AS sk_loja,
    COALESCE(dt.sk_tempo,        -1)                                    AS sk_tempo,
    COALESCE(dca.sk_canal_venda, 'DESCONHECIDO')                        AS sk_canal_venda,
    COALESCE(dcm.sk_campanha,    'SEM_CAMPANHA')                        AS sk_campanha,

    -- Chaves degeneradas / naturais
    p.id_pedido                                                         AS id_pedido_dg,
    i.id_item_pedido                                                    AS id_item_pedido_dg,

    -- Datas
    p.dt_pedido_data,
    p.dt_pedido,
    p.dt_confirmacao,

    -- Métricas de item
    i.qtd_vendida,
    i.preco_unitario,
    i.custo_unitario,
    i.desconto_item,
    i.valor_liquido_item,

    -- Métricas derivadas de item
    ROUND(i.valor_liquido_item - (i.qtd_vendida * i.custo_unitario), 2) AS margem_bruta_item,
    ROUND(
        i.desconto_item / NULLIF(i.desconto_item + i.valor_liquido_item, 0),
        4
    )                                                                   AS taxa_desconto_item,

    -- Métricas de cabeçalho do pedido (propagadas para contexto)
    p.valor_bruto                                                       AS valor_bruto_pedido,
    p.valor_desconto                                                    AS valor_desconto_pedido,
    p.valor_frete                                                       AS valor_frete_pedido,
    p.valor_liquido                                                     AS valor_liquido_pedido,
    p.qtd_itens                                                         AS qtd_itens_pedido,
    p.parcelas,
    p.metodo_pagamento,

    -- Status e flags
    p.status,
    (p.status NOT IN ('cancelado', 'devolvido'))                       AS fl_venda_valida,
    (p.status = 'cancelado')                                           AS fl_cancelado,
    (p.status = 'devolvido' OR p.qtd_devolucoes > 0)                  AS fl_devolvido,
    (p.canal_venda <> 'loja_fisica')                                   AS fl_online,

    -- Comissão (somente loja física)
    COALESCE(co.valor_comissao, 0)                                     AS valor_comissao,

    p.canal_venda
FROM pedidos p
INNER JOIN itens        i   ON i.id_pedido         = p.id_pedido
LEFT  JOIN dc               ON dc.id_cliente_nk    = p.id_cliente
LEFT  JOIN dp               ON dp.id_produto_nk    = i.id_produto
LEFT  JOIN dl               ON dl.id_loja_nk       = p.id_loja
LEFT  JOIN dt               ON dt.data_full        = p.dt_pedido_data
LEFT  JOIN dca              ON dca.canal_venda      = p.canal_venda
LEFT  JOIN dcm              ON dcm.id_campanha_nk  = p.id_campanha
LEFT  JOIN comissoes co     ON co.id_pedido         = p.id_pedido
