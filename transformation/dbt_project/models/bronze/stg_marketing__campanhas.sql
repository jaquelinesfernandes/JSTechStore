{{ config(unique_key='id_campanha') }}

{% if execute %}{% set _n = run_query("SELECT count(*) FROM glob('" ~ var('bronze_path') ~ "/marketing/campanhas/**/*.parquet')").columns[0].values()[0] %}{% else %}{% set _n = 1 %}{% endif %}
{% if _n == 0 %}
  {% if is_incremental() %}SELECT * FROM {{ this }} WHERE false
  {% else %}
SELECT NULL::INTEGER AS id_campanha, NULL::VARCHAR AS nome, NULL::VARCHAR AS tipo,
       NULL::VARCHAR AS canal, NULL::DATE AS dt_inicio, NULL::DATE AS dt_fim,
       NULL::DECIMAL AS orcamento, NULL::VARCHAR AS objetivo, NULL::BOOLEAN AS ativo,
       NULL::TIMESTAMPTZ AS updated_at, NULL::TIMESTAMPTZ AS _ingested_at
WHERE false
  {% endif %}
{% else %}

WITH source AS (
    SELECT *
    FROM read_parquet('{{ var("bronze_path") }}/marketing/campanhas/**/*.parquet')
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
{% endif %}
