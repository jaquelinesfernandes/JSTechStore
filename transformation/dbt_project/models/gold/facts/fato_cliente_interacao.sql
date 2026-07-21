{{
    config(
        unique_key='sk_sessao',
        post_hook="ANALYZE {{ this }}"
    )
}}

/*
  Fato interação com cliente: grão = 1 linha por sessão web.
  Inclui métricas de engajamento, conversão e carrinho.
*/

WITH sessoes AS (
    SELECT * FROM {{ ref('stg_web_analytics__sessoes') }}
    {% if is_incremental() %}
    WHERE _ingested_at > (
        SELECT COALESCE(MAX(_ingested_at), '1970-01-01'::TIMESTAMPTZ) FROM {{ this }}
    )
    {% endif %}
),
eventos_agg AS (
    SELECT
        id_sessao,
        COUNT(DISTINCT id_produto)                         AS qtd_produtos_vistos,
        SUM(CASE WHEN tipo_evento = 'add_to_cart'  THEN 1 ELSE 0 END) AS qtd_add_cart,
        SUM(CASE WHEN tipo_evento = 'purchase'     THEN 1 ELSE 0 END) AS qtd_compras,
        SUM(CASE WHEN tipo_evento = 'remove_from_cart' THEN 1 ELSE 0 END) AS qtd_remove_cart
    FROM {{ ref('stg_web_analytics__eventos_carrinho') }}
    GROUP BY id_sessao
),
dc AS (SELECT sk_cliente, id_cliente_nk FROM {{ ref('dim_cliente') }} WHERE fl_current = TRUE),
dt AS (SELECT sk_tempo,   data_full     FROM {{ ref('dim_tempo') }})
SELECT
    {{ get_surrogate_key(['s.id_sessao']) }}                AS sk_sessao,

    COALESCE(dc.sk_cliente, 'ANONIMO')                     AS sk_cliente,
    COALESCE(dt.sk_tempo,   -1)                            AS sk_tempo,

    s.id_sessao                                            AS id_sessao_dg,
    s.id_pedido                                            AS id_pedido_dg,
    s.canal_origem,
    s.device_type,
    s.dt_inicio,
    s.dt_fim,

    -- Métricas de engajamento
    s.paginas_visitadas,
    CASE
        WHEN s.dt_fim IS NOT NULL AND s.dt_inicio IS NOT NULL
        THEN EPOCH(s.dt_fim - s.dt_inicio) / 60.0
    END                                                    AS duracao_min,

    -- Conversão
    s.converteu,
    COALESCE(ea.qtd_produtos_vistos, 0)                    AS qtd_produtos_vistos,
    COALESCE(ea.qtd_add_cart, 0)                           AS qtd_add_cart,
    COALESCE(ea.qtd_remove_cart, 0)                        AS qtd_remove_cart,
    COALESCE(ea.qtd_compras, 0)                            AS qtd_compras,
    (ea.qtd_add_cart > 0 AND s.converteu = FALSE)          AS fl_abandono_carrinho,

    CAST(s.dt_inicio AS DATE)                              AS dt_sessao

FROM sessoes s
LEFT JOIN eventos_agg ea ON ea.id_sessao    = s.id_sessao
LEFT JOIN dc             ON dc.id_cliente_nk = s.id_cliente
LEFT JOIN dt             ON dt.data_full     = CAST(s.dt_inicio AS DATE)
