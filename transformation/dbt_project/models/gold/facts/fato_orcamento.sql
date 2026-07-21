{{
    config(
        unique_key='sk_orcamento',
        post_hook="ANALYZE {{ this }}"
    )
}}

/*
  Fato orçamento: grão = 1 linha por loja × canal × mês.
  Compara meta vs. realizado (calculado agregando fato_venda do mesmo período).
*/

WITH orcamentos AS (
    SELECT * FROM {{ ref('stg_financeiro__orcamentos') }}
    {% if is_incremental() %}
    WHERE _ingested_at > (
        SELECT COALESCE(MAX(_ingested_at), '1970-01-01'::TIMESTAMPTZ) FROM {{ this }}
    )
    {% endif %}
),
-- Realizado: agrega fato_venda por loja × canal × ano-mês
realizado AS (
    SELECT
        dl.id_loja_nk                                      AS id_loja,
        fv.canal_venda,
        EXTRACT(YEAR  FROM fv.dt_pedido_data)::INTEGER     AS ano,
        EXTRACT(MONTH FROM fv.dt_pedido_data)::INTEGER     AS mes,
        SUM(fv.valor_liquido_item)                         AS receita_realizada,
        SUM(fv.margem_bruta_item)                          AS margem_realizada,
        COUNT(DISTINCT fv.id_pedido_dg)                    AS qtd_pedidos_realizados
    FROM {{ ref('fato_venda') }} fv
    JOIN {{ ref('dim_loja') }} dl ON dl.sk_loja = fv.sk_loja
    WHERE fv.fl_venda_valida = TRUE
    GROUP BY dl.id_loja_nk, fv.canal_venda,
             EXTRACT(YEAR FROM fv.dt_pedido_data),
             EXTRACT(MONTH FROM fv.dt_pedido_data)
),
dl AS (SELECT sk_loja, id_loja_nk FROM {{ ref('dim_loja') }} WHERE fl_current = TRUE),
dt AS (SELECT sk_tempo, data_full  FROM {{ ref('dim_tempo') }})
SELECT
    {{ get_surrogate_key(['o.id_orcamento']) }}             AS sk_orcamento,

    COALESCE(dl.sk_loja,  'DESCONHECIDO')                  AS sk_loja,
    COALESCE(dt.sk_tempo, -1)                              AS sk_tempo,

    o.id_orcamento                                         AS id_orcamento_dg,
    o.id_loja                                              AS id_loja_nk,
    o.canal_venda,
    o.ano,
    o.mes,
    MAKE_DATE(o.ano, o.mes, 1)                             AS dt_inicio_mes,

    -- Metas
    o.valor_meta_receita,
    o.valor_meta_margem,
    o.qtd_meta_pedidos,

    -- Realizado
    COALESCE(r.receita_realizada,       0)                 AS receita_realizada,
    COALESCE(r.margem_realizada,        0)                 AS margem_realizada,
    COALESCE(r.qtd_pedidos_realizados,  0)                 AS qtd_pedidos_realizados,

    -- Variação meta vs realizado
    ROUND(COALESCE(r.receita_realizada, 0) / NULLIF(o.valor_meta_receita, 0) - 1, 4)
                                                           AS var_receita_pct,
    ROUND(COALESCE(r.margem_realizada, 0) / NULLIF(o.valor_meta_margem, 0) - 1, 4)
                                                           AS var_margem_pct,

    -- Flags
    (COALESCE(r.receita_realizada, 0) >= o.valor_meta_receita) AS fl_meta_receita_atingida,
    (COALESCE(r.qtd_pedidos_realizados, 0) >= o.qtd_meta_pedidos) AS fl_meta_pedidos_atingida

FROM orcamentos o
LEFT JOIN realizado r ON r.id_loja     = o.id_loja
                     AND r.canal_venda = o.canal_venda
                     AND r.ano         = o.ano
                     AND r.mes         = o.mes
LEFT JOIN dl          ON dl.id_loja_nk = o.id_loja
LEFT JOIN dt          ON dt.data_full  = MAKE_DATE(o.ano, o.mes, 1)
