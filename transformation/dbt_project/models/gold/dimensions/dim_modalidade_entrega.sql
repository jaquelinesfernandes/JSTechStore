{{ config(materialized='table') }}

WITH modalidades AS (
    SELECT * FROM {{ ref('stg_logistica__modalidades') }}
),
transportadoras AS (
    SELECT id_transportadora, nome AS nome_transportadora
    FROM {{ ref('stg_logistica__transportadoras') }}
)
SELECT
    {{ get_surrogate_key(['m.id_modalidade']) }}    AS sk_modalidade_entrega,
    m.id_modalidade                                AS id_modalidade_nk,
    m.codigo,
    m.nome                                         AS nome_modalidade,
    m.tipo,
    m.prazo_dias,
    m.frete_base,
    t.nome_transportadora,
    -- Flag retirada (frete zero e tipo loja)
    (m.tipo = 'loja' AND m.frete_base = 0)         AS fl_retirada_loja
FROM modalidades m
LEFT JOIN transportadoras t ON t.id_transportadora = m.id_transportadora
