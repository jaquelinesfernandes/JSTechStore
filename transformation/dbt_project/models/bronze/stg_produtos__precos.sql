{{ config(unique_key=['id_produto', 'dt_vigencia_inicio']) }}

WITH source AS (
    SELECT *
    FROM read_parquet('{{ var("bronze_path") }}/produtos/precos/**/*.parquet')
    {% if is_incremental() %}
    WHERE _ingested_at::TIMESTAMPTZ > (
        SELECT COALESCE(MAX(_ingested_at::TIMESTAMPTZ), '1970-01-01'::TIMESTAMPTZ)
        FROM {{ this }}
    )
    {% endif %}
),
deduplicado AS (
    SELECT *,
        ROW_NUMBER() OVER (
            PARTITION BY id_produto, dt_vigencia_inicio
            ORDER BY updated_at DESC
        ) AS rn
    FROM source
)
SELECT
    id_preco::INTEGER                 AS id_preco,
    id_produto::INTEGER               AS id_produto,
    preco_venda::NUMERIC(12,2)        AS preco_venda,
    custo_unitario::NUMERIC(12,2)     AS custo_unitario,
    dt_vigencia_inicio::DATE          AS dt_vigencia_inicio,
    dt_vigencia_fim::DATE             AS dt_vigencia_fim,
    updated_at::TIMESTAMPTZ           AS updated_at,
    _ingested_at::TIMESTAMPTZ         AS _ingested_at
FROM deduplicado WHERE rn = 1
