{{ config(materialized='table') }}

WITH vendedores AS (
    SELECT * FROM {{ ref('stg_rh__vendedores') }}
),
lojas AS (
    SELECT id_loja, nome_loja, regiao, uf FROM {{ ref('stg_rh__lojas') }}
)
SELECT
    {{ get_surrogate_key(['v.id_vendedor']) }}      AS sk_vendedor,
    v.id_vendedor                                  AS id_vendedor_nk,
    v.nome,
    v.cpf,
    v.email,
    v.cargo,
    v.data_admissao,
    v.ativo,
    v.id_loja,
    l.nome_loja,
    l.regiao,
    l.uf,
    -- SCD2
    v.data_admissao                                AS valid_from,
    DATE '9999-12-31'                              AS valid_to,
    TRUE                                           AS fl_current,
    {{ hash_row(['v.cargo', 'v.ativo', 'v.id_loja']) }}
                                                   AS hash_row
FROM vendedores v
LEFT JOIN lojas l ON l.id_loja = v.id_loja
