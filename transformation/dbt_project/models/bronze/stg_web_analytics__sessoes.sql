{{ config(unique_key='id_sessao') }}

WITH source AS (
    SELECT *
    FROM read_parquet('{{ var("bronze_path") }}/web_analytics/sessoes/**/*.parquet', union_by_name := true)
    {% if is_incremental() %}
    WHERE _ingested_at::TIMESTAMPTZ > (
        SELECT COALESCE(MAX(_ingested_at::TIMESTAMPTZ), '1970-01-01'::TIMESTAMPTZ)
        FROM {{ this }}
    )
    {% endif %}
),
deduplicado AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY id_sessao ORDER BY updated_at DESC) AS rn
    FROM source
)
SELECT
    id_sessao::INTEGER                AS id_sessao,
    id_cliente::INTEGER               AS id_cliente,
    canal_origem::VARCHAR             AS canal_origem,
    device_type::VARCHAR              AS device_type,
    dt_inicio::TIMESTAMPTZ            AS dt_inicio,
    dt_fim::TIMESTAMPTZ               AS dt_fim,
    paginas_visitadas::INTEGER        AS paginas_visitadas,
    converteu::BOOLEAN                AS converteu,
    id_pedido::INTEGER                AS id_pedido,
    updated_at::TIMESTAMPTZ           AS updated_at,
    _ingested_at::TIMESTAMPTZ         AS _ingested_at
FROM deduplicado WHERE rn = 1
