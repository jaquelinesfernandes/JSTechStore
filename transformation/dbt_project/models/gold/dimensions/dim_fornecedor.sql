{{ config(materialized='table') }}

WITH fornecedores AS (
    SELECT * FROM {{ ref('stg_produtos__fornecedores') }}
)
SELECT
    {{ get_surrogate_key(['id_fornecedor']) }}      AS sk_fornecedor,
    id_fornecedor                                  AS id_fornecedor_nk,
    nome_fornecedor,
    cnpj,
    categoria_principal,
    pais_origem,
    prazo_entrega_dias,
    ativo,
    -- Flag importado vs nacional
    (pais_origem <> 'Brasil')                      AS fl_importado
FROM fornecedores
