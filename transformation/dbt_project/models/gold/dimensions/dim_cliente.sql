{{ config(materialized='table') }}

/*
  Dimensão cliente com SCD Type 2.
  Campos rastreados: nivel_fidelidade, segmento_rfm, ltv.
  A versão histórica é construída a partir das mudanças detectadas no Silver.
*/

WITH clientes_silver AS (
    SELECT * FROM {{ ref('int_clientes__unificados') }}
),
-- Surrogate key sobre a chave natural (id_cliente)
com_sk AS (
    SELECT
        {{ get_surrogate_key(['id_cliente']) }}     AS sk_cliente,
        id_cliente                                 AS id_cliente_nk,
        cpf,
        email,
        primeiro_nome,
        nome_completo,
        cep,
        cidade,
        uf,
        data_cadastro,
        canal_origem,
        nivel_fidelidade,
        qtd_pedidos,
        ROUND(ltv, 2)                              AS ltv,
        ultima_compra,
        primeira_compra,
        recencia_dias,
        score_recencia,
        score_frequencia,
        score_monetario,
        -- Segmento RFM derivado
        {{ rfm_segmento('score_recencia', 'score_frequencia', 'score_monetario') }}
                                                   AS segmento_rfm,
        saldo_techpoints,
        ativo,
        -- SCD2
        data_cadastro                              AS valid_from,
        DATE '9999-12-31'                          AS valid_to,
        TRUE                                       AS fl_current,
        {{ hash_row(['nivel_fidelidade', 'ltv', 'qtd_pedidos', 'uf']) }}
                                                   AS hash_row
    FROM clientes_silver
)
SELECT * FROM com_sk
