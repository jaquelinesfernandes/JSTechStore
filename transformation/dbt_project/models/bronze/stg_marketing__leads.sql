{{ config(unique_key='id_lead') }}

WITH source AS (
    SELECT *
    FROM read_parquet('{{ var("bronze_path") }}/marketing/leads/**/*.parquet', union_by_name := true)
    {% if is_incremental() %}
    WHERE _ingested_at::TIMESTAMPTZ > (
        SELECT COALESCE(MAX(_ingested_at::TIMESTAMPTZ), '1970-01-01'::TIMESTAMPTZ)
        FROM {{ this }}
    )
    {% endif %}
),
deduplicado AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY id_lead ORDER BY updated_at DESC) AS rn
    FROM source
)
SELECT
    id_lead::INTEGER                  AS id_lead,
    id_campanha::INTEGER              AS id_campanha,
    id_cliente::INTEGER               AS id_cliente,
    canal::VARCHAR                    AS canal,
    dt_lead::DATE                     AS dt_lead,
    convertido::BOOLEAN               AS convertido,
    updated_at::TIMESTAMPTZ           AS updated_at,
    _ingested_at::TIMESTAMPTZ         AS _ingested_at
FROM deduplicado WHERE rn = 1
