{{ config(unique_key='id_modalidade') }}

{% if execute %}{% set _n = run_query("SELECT count(*) FROM glob('" ~ var('bronze_path') ~ "/logistica/modalidades/**/*.parquet')").columns[0].values()[0] %}{% else %}{% set _n = 1 %}{% endif %}
{% if _n == 0 %}
  {% if is_incremental() %}SELECT * FROM {{ this }} WHERE false
  {% else %}
SELECT NULL::INTEGER AS id_modalidade, NULL::INTEGER AS id_transportadora,
       NULL::VARCHAR AS nome, NULL::VARCHAR AS codigo, NULL::INTEGER AS prazo_dias,
       NULL::DECIMAL AS frete_base, NULL::VARCHAR AS tipo,
       NULL::TIMESTAMPTZ AS updated_at, NULL::TIMESTAMPTZ AS _ingested_at
WHERE false
  {% endif %}
{% else %}

WITH source AS (
    SELECT *
    FROM read_parquet('{{ var("bronze_path") }}/logistica/modalidades/**/*.parquet')
    {% if is_incremental() %}
    WHERE _ingested_at::TIMESTAMPTZ > (
        SELECT COALESCE(MAX(_ingested_at::TIMESTAMPTZ), '1970-01-01'::TIMESTAMPTZ)
        FROM {{ this }}
    )
    {% endif %}
),
deduplicado AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY id_modalidade ORDER BY updated_at DESC) AS rn
    FROM source
)
SELECT
    id_modalidade::INTEGER            AS id_modalidade,
    id_transportadora::INTEGER        AS id_transportadora,
    TRIM(nome)::VARCHAR               AS nome,
    TRIM(codigo)::VARCHAR             AS codigo,
    prazo_dias::INTEGER               AS prazo_dias,
    frete_base::NUMERIC(10,2)         AS frete_base,
    tipo::VARCHAR                     AS tipo,
    updated_at::TIMESTAMPTZ           AS updated_at,
    _ingested_at::TIMESTAMPTZ         AS _ingested_at
FROM deduplicado WHERE rn = 1
{% endif %}
