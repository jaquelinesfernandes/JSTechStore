{{ config(unique_key='id_lancamento') }}

WITH source AS (
    SELECT *
    FROM read_parquet('{{ var("bronze_path") }}/financeiro/lancamentos/**/*.parquet', union_by_name := true)
    {% if is_incremental() %}
    WHERE _ingested_at::TIMESTAMPTZ > (
        SELECT COALESCE(MAX(_ingested_at::TIMESTAMPTZ), '1970-01-01'::TIMESTAMPTZ)
        FROM {{ this }}
    )
    {% endif %}
),
deduplicado AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY id_lancamento ORDER BY updated_at DESC) AS rn
    FROM source
)
SELECT
    id_lancamento::INTEGER            AS id_lancamento,
    id_pedido::INTEGER                AS id_pedido,
    id_loja::INTEGER                  AS id_loja,
    tipo::VARCHAR                     AS tipo,
    valor::NUMERIC(12,2)             AS valor,
    dt_lancamento::DATE               AS dt_lancamento,
    dt_competencia::DATE              AS dt_competencia,
    descricao::VARCHAR                AS descricao,
    updated_at::TIMESTAMPTZ           AS updated_at,
    _ingested_at::TIMESTAMPTZ         AS _ingested_at
FROM deduplicado WHERE rn = 1
