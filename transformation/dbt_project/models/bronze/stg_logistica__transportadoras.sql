{{ config(unique_key='id_transportadora') }}

{% if execute %}{% set _n = run_query("SELECT count(*) FROM glob('" ~ var('bronze_path') ~ "/logistica/transportadoras/**/*.parquet')").columns[0].values()[0] %}{% else %}{% set _n = 1 %}{% endif %}
{% if _n == 0 %}
  {% if is_incremental() %}SELECT * FROM {{ this }} WHERE false
  {% else %}
SELECT NULL::INTEGER AS id_transportadora, NULL::VARCHAR AS nome, NULL::VARCHAR AS cnpj,
       NULL::INTEGER AS prazo_dias_min, NULL::INTEGER AS prazo_dias_max, NULL::BOOLEAN AS ativo,
       NULL::TIMESTAMPTZ AS updated_at, NULL::TIMESTAMPTZ AS _ingested_at
WHERE false
  {% endif %}
{% else %}

WITH source AS (
    SELECT *
    FROM read_parquet('{{ var("bronze_path") }}/logistica/transportadoras/**/*.parquet')
    {% if is_incremental() %}
    WHERE _ingested_at::TIMESTAMPTZ > (
        SELECT COALESCE(MAX(_ingested_at::TIMESTAMPTZ), '1970-01-01'::TIMESTAMPTZ)
        FROM {{ this }}
    )
    {% endif %}
),
deduplicado AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY id_transportadora ORDER BY updated_at DESC) AS rn
    FROM source
)
SELECT
    id_transportadora::INTEGER        AS id_transportadora,
    TRIM(nome)::VARCHAR               AS nome,
    TRIM(cnpj)::VARCHAR               AS cnpj,
    prazo_dias_min::INTEGER           AS prazo_dias_min,
    prazo_dias_max::INTEGER           AS prazo_dias_max,
    ativo::BOOLEAN                    AS ativo,
    updated_at::TIMESTAMPTZ           AS updated_at,
    _ingested_at::TIMESTAMPTZ         AS _ingested_at
FROM deduplicado WHERE rn = 1
{% endif %}
