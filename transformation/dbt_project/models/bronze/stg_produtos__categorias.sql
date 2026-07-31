{{ config(unique_key='id_categoria') }}

WITH source AS (
    SELECT *
    FROM read_parquet('{{ var("bronze_path") }}/produtos/categorias/**/*.parquet')
    {% if is_incremental() %}
    WHERE _ingested_at::TIMESTAMPTZ > (
        SELECT COALESCE(MAX(_ingested_at::TIMESTAMPTZ), '1970-01-01'::TIMESTAMPTZ)
        FROM {{ this }}
    )
    {% endif %}
),
deduplicado AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY id_categoria ORDER BY updated_at DESC) AS rn
    FROM source
)
SELECT
    id_categoria::INTEGER             AS id_categoria,
    TRIM(nome)::VARCHAR               AS nome,
    TRIM(subcategoria)::VARCHAR       AS subcategoria,
    updated_at::TIMESTAMPTZ           AS updated_at,
    _ingested_at::TIMESTAMPTZ         AS _ingested_at
FROM deduplicado WHERE rn = 1
