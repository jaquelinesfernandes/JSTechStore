{{ config(materialized='table') }}

WITH transportadoras AS (
    SELECT * FROM {{ ref('stg_logistica__transportadoras') }}
)
SELECT
    {{ get_surrogate_key(['id_transportadora']) }}  AS sk_transportadora,
    id_transportadora                              AS id_transportadora_nk,
    nome,
    cnpj,
    prazo_dias_min,
    prazo_dias_max,
    ROUND((prazo_dias_min + prazo_dias_max) / 2.0, 1) AS prazo_medio_dias,
    ativo
FROM transportadoras
