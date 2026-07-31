{{ config(unique_key='id_meta') }}

{% if execute %}{% set _n = run_query("SELECT count(*) FROM glob('" ~ var('bronze_path') ~ "/rh/metas/**/*.parquet')").columns[0].values()[0] %}{% else %}{% set _n = 1 %}{% endif %}
{% if _n == 0 %}
  {% if is_incremental() %}SELECT * FROM {{ this }} WHERE false
  {% else %}
SELECT NULL::INTEGER AS id_meta, NULL::INTEGER AS id_vendedor,
       NULL::INTEGER AS ano, NULL::INTEGER AS mes,
       NULL::DECIMAL AS meta_valor, NULL::INTEGER AS meta_qtd_pedidos,
       NULL::TIMESTAMPTZ AS updated_at, NULL::TIMESTAMPTZ AS _ingested_at
WHERE false
  {% endif %}
{% else %}

WITH source AS (
    SELECT *
    FROM read_parquet('{{ var("bronze_path") }}/rh/metas/**/*.parquet')
    {% if is_incremental() %}
    WHERE _ingested_at::TIMESTAMPTZ > (
        SELECT COALESCE(MAX(_ingested_at::TIMESTAMPTZ), '1970-01-01'::TIMESTAMPTZ)
        FROM {{ this }}
    )
    {% endif %}
),
deduplicado AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY id_meta ORDER BY updated_at DESC) AS rn
    FROM source
)
SELECT
    id_meta::INTEGER                  AS id_meta,
    id_vendedor::INTEGER              AS id_vendedor,
    ano::INTEGER                      AS ano,
    mes::INTEGER                      AS mes,
    meta_valor::NUMERIC(12,2)         AS meta_valor,
    meta_qtd_pedidos::INTEGER         AS meta_qtd_pedidos,
    updated_at::TIMESTAMPTZ           AS updated_at,
    _ingested_at::TIMESTAMPTZ         AS _ingested_at
FROM deduplicado WHERE rn = 1
{% endif %}
