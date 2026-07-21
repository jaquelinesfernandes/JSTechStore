{{ config(unique_key='id_conta') }}

WITH source AS (
    SELECT *
    FROM read_parquet('{{ var("bronze_path") }}/financeiro/contas_receber/**/*.parquet')
    {% if is_incremental() %}
    WHERE _ingested_at::TIMESTAMPTZ > (
        SELECT COALESCE(MAX(_ingested_at::TIMESTAMPTZ), '1970-01-01'::TIMESTAMPTZ)
        FROM {{ this }}
    )
    {% endif %}
),
deduplicado AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY id_conta ORDER BY updated_at DESC) AS rn
    FROM source
)
SELECT
    id_conta::INTEGER                 AS id_conta,
    id_pedido::INTEGER                AS id_pedido,
    valor_original::NUMERIC(12,2)     AS valor_original,
    valor_pago::NUMERIC(12,2)         AS valor_pago,
    dt_vencimento::DATE               AS dt_vencimento,
    dt_pagamento::DATE                AS dt_pagamento,
    status::VARCHAR                   AS status,
    updated_at::TIMESTAMPTZ           AS updated_at,
    _ingested_at::TIMESTAMPTZ         AS _ingested_at
FROM deduplicado WHERE rn = 1
