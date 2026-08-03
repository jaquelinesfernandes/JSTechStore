{{ config(unique_key='id_campanha') }}

WITH source AS (
    SELECT *
    FROM read_parquet('{{ var("bronze_path") }}/marketing/campanhas/**/*.parquet', union_by_name := true)
    {% if is_incremental() %}
    WHERE _ingested_at::TIMESTAMPTZ > (
        SELECT COALESCE(MAX(_ingested_at::TIMESTAMPTZ), '1970-01-01'::TIMESTAMPTZ)
        FROM {{ this }}
    )
    {% endif %}
),
deduplicado AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY id_campanha ORDER BY updated_at DESC) AS rn
    FROM source
)
SELECT
    id_campanha::INTEGER              AS id_campanha,
    TRIM(nome)::VARCHAR               AS nome,
    tipo::VARCHAR                     AS tipo,
    canal::VARCHAR                    AS canal,
    dt_inicio::DATE                   AS dt_inicio,
    dt_fim::DATE                      AS dt_fim,
    orcamento::NUMERIC(12,2)          AS orcamento,
    objetivo::VARCHAR                 AS objetivo,
    ativo::BOOLEAN                    AS ativo,
    updated_at::TIMESTAMPTZ           AS updated_at,
    _ingested_at::TIMESTAMPTZ         AS _ingested_at
FROM deduplicado WHERE rn = 1
