{{ config(unique_key='id_item_pedido') }}

WITH source AS (
    SELECT *
    FROM read_parquet('{{ var("bronze_path") }}/vendas/itens_pedido/**/*.parquet', union_by_name := true)
    {% if is_incremental() %}
    WHERE _ingested_at::TIMESTAMPTZ > (
        SELECT COALESCE(MAX(_ingested_at::TIMESTAMPTZ), '1970-01-01'::TIMESTAMPTZ)
        FROM {{ this }}
    )
    {% endif %}
),
deduplicado AS (
    SELECT *,
        ROW_NUMBER() OVER (PARTITION BY id_item_pedido ORDER BY updated_at DESC) AS rn
    FROM source
)
SELECT
    id_item_pedido::INTEGER           AS id_item_pedido,
    id_pedido::INTEGER                AS id_pedido,
    id_produto::INTEGER               AS id_produto,
    qtd_vendida::INTEGER              AS qtd_vendida,
    preco_unitario::NUMERIC(12,2)     AS preco_unitario,
    custo_unitario::NUMERIC(12,2)     AS custo_unitario,
    desconto_item::NUMERIC(10,2)      AS desconto_item,
    valor_liquido_item::NUMERIC(12,2) AS valor_liquido_item,
    updated_at::TIMESTAMPTZ           AS updated_at,
    _ingested_at::TIMESTAMPTZ         AS _ingested_at
FROM deduplicado
WHERE rn = 1
