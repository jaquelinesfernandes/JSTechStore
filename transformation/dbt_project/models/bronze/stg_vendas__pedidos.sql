{{ config(unique_key='id_pedido') }}

WITH source AS (
    SELECT *
    FROM read_parquet('{{ var("bronze_path") }}/vendas/pedidos/**/*.parquet')
    {% if is_incremental() %}
    WHERE _ingested_at::TIMESTAMPTZ > (
        SELECT COALESCE(MAX(_ingested_at::TIMESTAMPTZ), '1970-01-01'::TIMESTAMPTZ)
        FROM {{ this }}
    )
    {% endif %}
),
deduplicado AS (
    SELECT *,
        ROW_NUMBER() OVER (PARTITION BY id_pedido ORDER BY updated_at DESC) AS rn
    FROM source
)
SELECT
    id_pedido::INTEGER                AS id_pedido,
    id_cliente::INTEGER               AS id_cliente,
    id_loja::INTEGER                  AS id_loja,
    canal_venda::VARCHAR              AS canal_venda,
    status::VARCHAR                   AS status,
    dt_pedido::TIMESTAMPTZ            AS dt_pedido,
    dt_confirmacao::TIMESTAMPTZ       AS dt_confirmacao,
    dt_cancelamento::TIMESTAMPTZ      AS dt_cancelamento,
    valor_bruto::NUMERIC(12,2)        AS valor_bruto,
    valor_desconto::NUMERIC(12,2)     AS valor_desconto,
    valor_frete::NUMERIC(10,2)        AS valor_frete,
    valor_liquido::NUMERIC(12,2)      AS valor_liquido,
    parcelas::INTEGER                 AS parcelas,
    metodo_pagamento::VARCHAR         AS metodo_pagamento,
    cupom::VARCHAR                    AS cupom,
    id_campanha::INTEGER              AS id_campanha,
    created_at::TIMESTAMPTZ           AS created_at,
    updated_at::TIMESTAMPTZ           AS updated_at,
    _ingested_at::TIMESTAMPTZ         AS _ingested_at
FROM deduplicado
WHERE rn = 1
