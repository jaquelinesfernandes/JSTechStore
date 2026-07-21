{{ config(materialized='table') }}

/*
  Dimensão loja com SCD Type 2.
  Campos rastreados: gerente, ativo.
*/

WITH lojas AS (
    SELECT * FROM {{ ref('stg_rh__lojas') }}
)
SELECT
    {{ get_surrogate_key(['id_loja']) }}            AS sk_loja,
    id_loja                                        AS id_loja_nk,
    codigo,
    nome_loja,
    tipo_loja,
    regiao,
    cidade,
    uf,
    gerente,
    capacidade_m2,
    dt_abertura,
    ativo,
    -- Flags derivadas
    (tipo_loja = 'fisica')                         AS fl_loja_fisica,
    (tipo_loja = 'ecommerce')                      AS fl_ecommerce,
    -- SCD2
    dt_abertura                                    AS valid_from,
    DATE '9999-12-31'                              AS valid_to,
    TRUE                                           AS fl_current,
    {{ hash_row(['gerente', 'ativo', 'nome_loja']) }}
                                                   AS hash_row
FROM lojas
