{{
    config(
        unique_key='sk_estoque',
        post_hook="ANALYZE {{ this }}"
    )
}}

/*
  Fato estoque: snapshot diário de saldo por produto × loja.
  Grão = 1 linha por produto × loja × dia (a partir das movimentações).
*/

WITH saldo AS (
    SELECT * FROM {{ ref('stg_estoque__saldo_estoque') }}
    {% if is_incremental() %}
    WHERE _ingested_at > (
        SELECT COALESCE(MAX(_ingested_at), '1970-01-01'::TIMESTAMPTZ) FROM {{ this }}
    )
    {% endif %}
),
movs_agg AS (
    SELECT
        id_produto,
        id_loja,
        CAST(dt_movimentacao AS DATE)              AS dt_mov,
        SUM(CASE WHEN qtd > 0 THEN qtd  ELSE 0 END) AS qtd_entrada,
        SUM(CASE WHEN qtd < 0 THEN ABS(qtd) ELSE 0 END) AS qtd_saida,
        COUNT(DISTINCT id_pedido)                  AS qtd_pedidos_movs
    FROM {{ ref('stg_estoque__movimentacoes') }}
    GROUP BY id_produto, id_loja, CAST(dt_movimentacao AS DATE)
),
dp AS (SELECT sk_produto, id_produto_nk FROM {{ ref('dim_produto') }} WHERE fl_current = TRUE),
dl AS (SELECT sk_loja,    id_loja_nk    FROM {{ ref('dim_loja') }}    WHERE fl_current = TRUE),
dt AS (SELECT sk_tempo,   data_full     FROM {{ ref('dim_tempo') }})
SELECT
    {{ get_surrogate_key(['s.id_produto', 's.id_loja', 's.dt_ultima_atualizacao']) }}
                                                        AS sk_estoque,
    COALESCE(dp.sk_produto, 'DESCONHECIDO')             AS sk_produto,
    COALESCE(dl.sk_loja,    'DESCONHECIDO')             AS sk_loja,
    COALESCE(dt.sk_tempo,   -1)                         AS sk_tempo,

    s.id_produto                                        AS id_produto_nk,
    s.id_loja                                           AS id_loja_nk,
    s.dt_ultima_atualizacao,

    s.qtd_disponivel,
    s.qtd_reservada,
    s.qtd_minima,
    (s.qtd_disponivel + s.qtd_reservada)               AS qtd_total,
    (s.qtd_disponivel <= s.qtd_minima)                 AS fl_estoque_critico,
    (s.qtd_disponivel = 0)                             AS fl_ruptura,

    COALESCE(m.qtd_entrada,      0)                    AS qtd_entrada_dia,
    COALESCE(m.qtd_saida,        0)                    AS qtd_saida_dia,
    COALESCE(m.qtd_pedidos_movs, 0)                    AS qtd_pedidos_movs

FROM saldo s
LEFT JOIN movs_agg m ON m.id_produto = s.id_produto
                    AND m.id_loja    = s.id_loja
                    AND m.dt_mov     = s.dt_ultima_atualizacao
LEFT JOIN dp ON dp.id_produto_nk = s.id_produto
LEFT JOIN dl ON dl.id_loja_nk    = s.id_loja
LEFT JOIN dt ON dt.data_full     = s.dt_ultima_atualizacao
