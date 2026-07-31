{{ config(unique_key='id_produto') }}

WITH source AS (
    SELECT *
    FROM read_parquet('{{ var("bronze_path") }}/produtos/produtos/**/*.parquet')
    {% if is_incremental() %}
    WHERE _ingested_at::TIMESTAMPTZ > (
        SELECT COALESCE(MAX(_ingested_at::TIMESTAMPTZ), '1970-01-01'::TIMESTAMPTZ)
        FROM {{ this }}
    )
    {% endif %}
),
deduplicado AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY id_produto ORDER BY updated_at DESC) AS rn
    FROM source
)
SELECT
    id_produto::INTEGER               AS id_produto,
    id_categoria::INTEGER             AS id_categoria,
    id_fornecedor::INTEGER            AS id_fornecedor,
    TRIM(sku)::VARCHAR                AS sku,
    TRIM(nome)::VARCHAR               AS nome,
    TRIM(marca)::VARCHAR              AS marca,
    peso_kg::NUMERIC(8,3)            AS peso_kg,
    ativo::BOOLEAN                    AS ativo,
    created_at::TIMESTAMPTZ           AS created_at,
    updated_at::TIMESTAMPTZ           AS updated_at,
    _ingested_at::TIMESTAMPTZ         AS _ingested_at
FROM deduplicado WHERE rn = 1
