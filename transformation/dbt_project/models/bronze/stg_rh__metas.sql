{{ config(unique_key='id_meta') }}

WITH source AS (
    SELECT *
    FROM read_parquet('{{ var("bronze_path") }}/rh/metas/**/*.parquet', union_by_name := true)
    {% if is_incremental() %}
    WHERE _ingested_at::TIMESTAMPTZ > (
        SELECT COALESCE(MAX(_ingested_at::TIMESTAMPTZ), '1970-01-01'::TIMESTAMPTZ)
        FROM {{ this }}
    )
    {% endif %}
),
deduplicado AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY id_meta ORDER BY updated_at DESC) AS rn
    FROM source
)
SELECT
    id_meta::INTEGER                  AS id_meta,
    id_vendedor::INTEGER              AS id_vendedor,
    ano::INTEGER                      AS ano,
    mes::INTEGER                      AS mes,
    meta_valor::NUMERIC(12,2)         AS meta_valor,
    meta_qtd_pedidos::INTEGER         AS meta_qtd_pedidos,
    updated_at::TIMESTAMPTZ           AS updated_at,
    _ingested_at::TIMESTAMPTZ         AS _ingested_at
FROM deduplicado WHERE rn = 1
