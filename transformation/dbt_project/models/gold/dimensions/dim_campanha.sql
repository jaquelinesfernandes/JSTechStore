{{ config(materialized='table') }}

WITH campanhas AS (
    SELECT * FROM {{ ref('stg_marketing__campanhas') }}
)
SELECT
    {{ get_surrogate_key(['id_campanha']) }}        AS sk_campanha,
    id_campanha                                    AS id_campanha_nk,
    nome,
    tipo,
    canal,
    dt_inicio,
    dt_fim,
    (dt_fim - dt_inicio + 1)                      AS duracao_dias,
    orcamento,
    objetivo,
    ativo,
    EXTRACT(YEAR FROM dt_inicio)::INTEGER          AS ano_campanha,
    -- SCD2
    dt_inicio                                      AS valid_from,
    DATE '9999-12-31'                              AS valid_to,
    TRUE                                           AS fl_current,
    {{ hash_row(['nome', 'ativo', 'orcamento']) }}  AS hash_row
FROM campanhas
