{{ config(unique_key='id_loja') }}

{% if execute %}{% set _n = run_query("SELECT count(*) FROM glob('" ~ var('bronze_path') ~ "/rh/lojas/**/*.parquet')").columns[0].values()[0] %}{% else %}{% set _n = 1 %}{% endif %}
{% if _n == 0 %}
  {% if is_incremental() %}SELECT * FROM {{ this }} WHERE false
  {% else %}
SELECT NULL::INTEGER AS id_loja, NULL::VARCHAR AS codigo, NULL::VARCHAR AS nome_loja,
       NULL::VARCHAR AS tipo_loja, NULL::VARCHAR AS regiao, NULL::VARCHAR AS cidade,
       NULL::VARCHAR AS uf, NULL::VARCHAR AS gerente, NULL::INTEGER AS capacidade_m2,
       NULL::DATE AS dt_abertura, NULL::BOOLEAN AS ativo,
       NULL::TIMESTAMPTZ AS updated_at, NULL::TIMESTAMPTZ AS _ingested_at
WHERE false
  {% endif %}
{% else %}

WITH source AS (
    SELECT *
    FROM read_parquet('{{ var("bronze_path") }}/rh/lojas/**/*.parquet')
    {% if is_incremental() %}
    WHERE _ingested_at::TIMESTAMPTZ > (
        SELECT COALESCE(MAX(_ingested_at::TIMESTAMPTZ), '1970-01-01'::TIMESTAMPTZ)
        FROM {{ this }}
    )
    {% endif %}
),
deduplicado AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY id_loja ORDER BY updated_at DESC) AS rn
    FROM source
)
SELECT
    id_loja::INTEGER                  AS id_loja,
    TRIM(codigo)::VARCHAR             AS codigo,
    TRIM(nome_loja)::VARCHAR          AS nome_loja,
    tipo_loja::VARCHAR                AS tipo_loja,
    regiao::VARCHAR                   AS regiao,
    TRIM(cidade)::VARCHAR             AS cidade,
    UPPER(TRIM(uf))::VARCHAR          AS uf,
    TRIM(gerente)::VARCHAR            AS gerente,
    capacidade_m2::INTEGER            AS capacidade_m2,
    dt_abertura::DATE                 AS dt_abertura,
    ativo::BOOLEAN                    AS ativo,
    updated_at::TIMESTAMPTZ           AS updated_at,
    _ingested_at::TIMESTAMPTZ         AS _ingested_at
FROM deduplicado WHERE rn = 1
{% endif %}
