{{ config(unique_key='id_techpoints') }}

{% if execute %}{% set _n = run_query("SELECT count(*) FROM glob('" ~ var('bronze_path') ~ "/clientes/techpoints/**/*.parquet')").columns[0].values()[0] %}{% else %}{% set _n = 1 %}{% endif %}
{% if _n == 0 and is_incremental() %}SELECT * FROM {{ this }} WHERE false{% else %}

WITH source AS (
    SELECT *
    FROM read_parquet('{{ var("bronze_path") }}/clientes/techpoints/**/*.parquet')
    {% if is_incremental() %}
    WHERE _ingested_at::TIMESTAMPTZ > (
        SELECT COALESCE(MAX(_ingested_at::TIMESTAMPTZ), '1970-01-01'::TIMESTAMPTZ)
        FROM {{ this }}
    )
    {% endif %}
),
deduplicado AS (
    SELECT *,
        ROW_NUMBER() OVER (PARTITION BY id_techpoints ORDER BY updated_at DESC) AS rn
    FROM source
)
SELECT
    id_techpoints::INTEGER            AS id_techpoints,
    id_cliente::INTEGER               AS id_cliente,
    pontos_acumulados::INTEGER        AS pontos_acumulados,
    pontos_resgatados::INTEGER        AS pontos_resgatados,
    saldo_pontos::INTEGER             AS saldo_pontos,
    nivel_fidelidade::VARCHAR         AS nivel_fidelidade,
    updated_at::TIMESTAMPTZ           AS updated_at,
    _ingested_at::TIMESTAMPTZ         AS _ingested_at
FROM deduplicado
WHERE rn = 1
{% endif %}
