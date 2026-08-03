{{ config(unique_key='id_parcela') }}

WITH source AS (
    SELECT *
    FROM read_parquet('{{ var("bronze_path") }}/financeiro/parcelas/**/*.parquet', union_by_name := true)
    {% if is_incremental() %}
    WHERE _ingested_at::TIMESTAMPTZ > (
        SELECT COALESCE(MAX(_ingested_at::TIMESTAMPTZ), '1970-01-01'::TIMESTAMPTZ)
        FROM {{ this }}
    )
    {% endif %}
),
deduplicado AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY id_parcela ORDER BY updated_at DESC) AS rn
    FROM source
)
SELECT
    id_parcela::INTEGER               AS id_parcela,
    id_lancamento::INTEGER            AS id_lancamento,
    numero_parcela::INTEGER           AS numero_parcela,
    valor_parcela::NUMERIC(12,2)      AS valor_parcela,
    dt_vencimento::DATE               AS dt_vencimento,
    dt_pagamento::DATE                AS dt_pagamento,
    status::VARCHAR                   AS status,
    updated_at::TIMESTAMPTZ           AS updated_at,
    _ingested_at::TIMESTAMPTZ         AS _ingested_at
FROM deduplicado WHERE rn = 1
