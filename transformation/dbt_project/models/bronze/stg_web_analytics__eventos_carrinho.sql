{{ config(unique_key='id_evento') }}

WITH source AS (
    SELECT *
    FROM read_parquet('{{ var("bronze_path") }}/web_analytics/eventos_carrinho/**/*.parquet')
    {% if is_incremental() %}
    WHERE _ingested_at::TIMESTAMPTZ > (
        SELECT COALESCE(MAX(_ingested_at::TIMESTAMPTZ), '1970-01-01'::TIMESTAMPTZ)
        FROM {{ this }}
    )
    {% endif %}
),
deduplicado AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY id_evento ORDER BY updated_at DESC) AS rn
    FROM source
)
SELECT
    id_evento::INTEGER                AS id_evento,
    id_sessao::INTEGER                AS id_sessao,
    id_produto::INTEGER               AS id_produto,
    tipo_evento::VARCHAR              AS tipo_evento,
    dt_evento::TIMESTAMPTZ            AS dt_evento,
    qtd::INTEGER                      AS qtd,
    preco_na_epoca::NUMERIC(12,2)     AS preco_na_epoca,
    updated_at::TIMESTAMPTZ           AS updated_at,
    _ingested_at::TIMESTAMPTZ         AS _ingested_at
FROM deduplicado WHERE rn = 1
