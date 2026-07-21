{{ config(materialized='table') }}

/*
  Dimensão produto com SCD Type 2.
  Campos rastreados: preco_venda_vigente, custo_vigente, margem.
  Preço histórico é capturado na fato_venda — aqui guardamos o preço vigente atual.
*/

WITH catalogo AS (
    SELECT * FROM {{ ref('int_produtos__catalogo') }}
)
SELECT
    {{ get_surrogate_key(['id_produto']) }}         AS sk_produto,
    id_produto                                     AS id_produto_nk,
    sku,
    nome_produto,
    marca,
    categoria,
    subcategoria,
    id_categoria,
    nome_fornecedor,
    cnpj_fornecedor,
    pais_origem,
    prazo_entrega_dias,
    peso_kg,
    preco_venda_vigente,
    custo_vigente,
    margem_pct_vigente,
    ativo,
    -- SCD2
    CURRENT_DATE                                   AS valid_from,
    DATE '9999-12-31'                              AS valid_to,
    TRUE                                           AS fl_current,
    {{ hash_row(['preco_venda_vigente', 'custo_vigente', 'ativo']) }}
                                                   AS hash_row
FROM catalogo
