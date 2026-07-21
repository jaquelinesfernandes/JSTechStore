{{ config(unique_key='id_atribuicao') }}

WITH source AS (
    SELECT *
    FROM read_parquet('{{ var("bronze_path") }}/marketing/atribuicao/**/*.parquet')
    {% if is_incremental() %}
    WHERE _ingested_at::TIMESTAMPTZ > (
        SELECT COALESCE(MAX(_ingested_at::TIMESTAMPTZ), '1970-01-01'::TIMESTAMPTZ)
        FROM {{ this }}
    )
    {% endif %}
),
deduplicado AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY id_atribuicao ORDER BY updated_at DESC) AS rn
    FROM source
)
SELECT
    id_atribuicao::INTEGER            AS id_atribuicao,
    id_pedido::INTEGER                AS id_pedido,
    id_campanha::INTEGER              AS id_campanha,
    canal_atribuicao::VARCHAR         AS canal_atribuicao,
    tipo_atribuicao::VARCHAR          AS tipo_atribuicao,
    peso::NUMERIC(5,4)               AS peso,
    updated_at::TIMESTAMPTZ           AS updated_at,
    _ingested_at::TIMESTAMPTZ         AS _ingested_at
FROM deduplicado WHERE rn = 1
