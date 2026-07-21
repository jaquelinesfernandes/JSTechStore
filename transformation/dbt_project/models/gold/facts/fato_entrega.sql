{{
    config(
        unique_key='sk_entrega',
        post_hook="ANALYZE {{ this }}"
    )
}}

/*
  Fato entrega: grão = 1 linha por entrega (1 pedido online = 1 entrega).
  Mede OTD (On-Time Delivery) e lead time.
*/

WITH entregas AS (
    SELECT * FROM {{ ref('stg_logistica__entregas') }}
    {% if is_incremental() %}
    WHERE _ingested_at > (
        SELECT COALESCE(MAX(_ingested_at), '1970-01-01'::TIMESTAMPTZ) FROM {{ this }}
    )
    {% endif %}
),
pedidos AS (
    SELECT id_pedido, id_cliente, id_loja, canal_venda
    FROM {{ ref('stg_vendas__pedidos') }}
),
dl     AS (SELECT sk_loja,            id_loja_nk            FROM {{ ref('dim_loja') }}              WHERE fl_current = TRUE),
dc     AS (SELECT sk_cliente,         id_cliente_nk         FROM {{ ref('dim_cliente') }}           WHERE fl_current = TRUE),
dtrans AS (SELECT sk_transportadora,  id_transportadora_nk  FROM {{ ref('dim_transportadora') }}),
dmod   AS (SELECT sk_modalidade_entrega, id_modalidade_nk   FROM {{ ref('dim_modalidade_entrega') }}),
dt     AS (SELECT sk_tempo,           data_full             FROM {{ ref('dim_tempo') }})
SELECT
    {{ get_surrogate_key(['e.id_entrega']) }}                AS sk_entrega,

    COALESCE(dc.sk_cliente,              'DESCONHECIDO')    AS sk_cliente,
    COALESCE(dl.sk_loja,                 'DESCONHECIDO')    AS sk_loja,
    COALESCE(dtrans.sk_transportadora,   'DESCONHECIDO')    AS sk_transportadora,
    COALESCE(dmod.sk_modalidade_entrega, 'DESCONHECIDO')    AS sk_modalidade_entrega,
    COALESCE(dt.sk_tempo,               -1)                 AS sk_tempo_postagem,

    e.id_entrega                                            AS id_entrega_dg,
    e.id_pedido                                             AS id_pedido_dg,
    e.codigo_rastreio,

    -- Datas
    e.dt_postagem,
    e.dt_promessa,
    e.dt_efetiva,

    -- Lead times
    (e.dt_promessa - e.dt_postagem)                         AS lead_time_prometido_dias,
    CASE
        WHEN e.dt_efetiva IS NOT NULL
        THEN (e.dt_efetiva - e.dt_postagem)
    END                                                     AS lead_time_real_dias,
    CASE
        WHEN e.dt_efetiva IS NOT NULL AND e.dt_promessa IS NOT NULL
        THEN (e.dt_efetiva - e.dt_promessa)
    END                                                     AS atraso_dias,

    -- Flags de qualidade
    e.fl_sla_atendido,
    (e.status = 'entregue')                                 AS fl_entregue,
    e.status,

    p.canal_venda
FROM entregas e
LEFT JOIN pedidos  p     ON p.id_pedido            = e.id_pedido
LEFT JOIN dc             ON dc.id_cliente_nk       = p.id_cliente
LEFT JOIN dl             ON dl.id_loja_nk          = e.id_loja_origem
LEFT JOIN dtrans         ON dtrans.id_transportadora_nk = e.id_transportadora
LEFT JOIN dmod           ON dmod.id_modalidade_nk  = e.id_modalidade
LEFT JOIN dt             ON dt.data_full           = e.dt_postagem
