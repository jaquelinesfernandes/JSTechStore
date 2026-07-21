{{ config(unique_key='id_comissao') }}

WITH source AS (
    SELECT *
    FROM read_parquet('{{ var("bronze_path") }}/rh/comissoes/**/*.parquet')
    {% if is_incremental() %}
    WHERE _ingested_at::TIMESTAMPTZ > (
        SELECT COALESCE(MAX(_ingested_at::TIMESTAMPTZ), '1970-01-01'::TIMESTAMPTZ)
        FROM {{ this }}
    )
    {% endif %}
),
deduplicado AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY id_comissao ORDER BY updated_at DESC) AS rn
    FROM source
)
SELECT
    id_comissao::INTEGER              AS id_comissao,
    id_vendedor::INTEGER              AS id_vendedor,
    id_pedido::INTEGER                AS id_pedido,
    valor_venda::NUMERIC(12,2)        AS valor_venda,
    percentual_comissao::NUMERIC(5,4) AS percentual_comissao,
    valor_comissao::NUMERIC(10,2)     AS valor_comissao,
    dt_competencia::DATE              AS dt_competencia,
    status::VARCHAR                   AS status,
    updated_at::TIMESTAMPTZ           AS updated_at,
    _ingested_at::TIMESTAMPTZ         AS _ingested_at
FROM deduplicado WHERE rn = 1
