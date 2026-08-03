{{ config(unique_key='id_devolucao') }}

WITH source AS (
    SELECT *
    FROM read_parquet('{{ var("bronze_path") }}/vendas/devolucoes/**/*.parquet', union_by_name := true)
    {% if is_incremental() %}
    WHERE _ingested_at::TIMESTAMPTZ > (
        SELECT COALESCE(MAX(_ingested_at::TIMESTAMPTZ), '1970-01-01'::TIMESTAMPTZ)
        FROM {{ this }}
    )
    {% endif %}
),
deduplicado AS (
    SELECT *,
        ROW_NUMBER() OVER (PARTITION BY id_devolucao ORDER BY updated_at DESC) AS rn
    FROM source
)
SELECT
    id_devolucao::INTEGER             AS id_devolucao,
    id_pedido::INTEGER                AS id_pedido,
    id_produto::INTEGER               AS id_produto,
    dt_devolucao::DATE                AS dt_devolucao,
    motivo::VARCHAR                   AS motivo,
    qtd_devolvida::INTEGER            AS qtd_devolvida,
    valor_devolvido::NUMERIC(12,2)    AS valor_devolvido,
    status::VARCHAR                   AS status,
    updated_at::TIMESTAMPTZ           AS updated_at,
    _ingested_at::TIMESTAMPTZ         AS _ingested_at
FROM deduplicado
WHERE rn = 1
