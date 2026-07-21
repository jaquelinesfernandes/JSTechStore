{{
    config(
        unique_key='sk_lancamento',
        post_hook="ANALYZE {{ this }}"
    )
}}

/*
  Fato financeiro: grão = 1 linha por lançamento financeiro.
  Cobre receitas, custos, fretes e comissões em base de competência.
*/

WITH lancamentos AS (
    SELECT * FROM {{ ref('stg_financeiro__lancamentos') }}
    {% if is_incremental() %}
    WHERE _ingested_at > (
        SELECT COALESCE(MAX(_ingested_at), '1970-01-01'::TIMESTAMPTZ) FROM {{ this }}
    )
    {% endif %}
),
contas_receber AS (
    SELECT id_pedido, status AS status_cr, dt_pagamento, valor_pago
    FROM {{ ref('stg_financeiro__contas_receber') }}
),
dl AS (SELECT sk_loja, id_loja_nk FROM {{ ref('dim_loja') }} WHERE fl_current = TRUE),
dt AS (SELECT sk_tempo, data_full  FROM {{ ref('dim_tempo') }})
SELECT
    {{ get_surrogate_key(['l.id_lancamento']) }}             AS sk_lancamento,

    COALESCE(dl.sk_loja,  'DESCONHECIDO')                  AS sk_loja,
    COALESCE(dt.sk_tempo, -1)                              AS sk_tempo_competencia,

    l.id_lancamento                                        AS id_lancamento_dg,
    l.id_pedido                                            AS id_pedido_dg,
    l.tipo,
    l.valor,
    l.dt_lancamento,
    l.dt_competencia,
    l.descricao,

    -- Sinal: receita é positivo, custo é negativo
    CASE l.tipo
        WHEN 'receita'      THEN  l.valor
        WHEN 'desconto'     THEN -l.valor
        WHEN 'custo_produto' THEN -l.valor
        WHEN 'frete_custo'  THEN -l.valor
        WHEN 'comissao'     THEN -l.valor
        ELSE l.valor
    END                                                    AS valor_sinal,

    -- Conta a receber
    cr.status_cr,
    cr.dt_pagamento,
    cr.valor_pago,
    (cr.status_cr = 'pago')                               AS fl_pago
FROM lancamentos l
LEFT JOIN contas_receber cr ON cr.id_pedido = l.id_pedido
LEFT JOIN dl                ON dl.id_loja_nk  = l.id_loja
LEFT JOIN dt                ON dt.data_full   = l.dt_competencia
