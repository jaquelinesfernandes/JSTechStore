{{ config(unique_key='id_produto') }}

{% if execute %}{% set _n = run_query("SELECT count(*) FROM glob('" ~ var('bronze_path') ~ "/produtos/produtos/**/*.parquet')").columns[0].values()[0] %}{% else %}{% set _n = 1 %}{% endif %}
{% if _n == 0 %}
  {% if is_incremental() %}SELECT * FROM {{ this }} WHERE false
  {% else %}
SELECT NULL::INTEGER AS id_produto, NULL::INTEGER AS id_categoria, NULL::INTEGER AS id_fornecedor,
       NULL::VARCHAR AS sku, NULL::VARCHAR AS nome, NULL::VARCHAR AS marca,
       NULL::DECIMAL AS peso_kg, NULL::BOOLEAN AS ativo,
       NULL::TIMESTAMPTZ AS created_at, NULL::TIMESTAMPTZ AS updated_at,
       NULL::TIMESTAMPTZ AS _ingested_at
WHERE false
  {% endif %}
{% else %}

WITH source AS (
    SELECT *
    FROM read_parquet('{{ var("bronze_path") }}/produtos/produtos/**/*.parquet')
    {% if is_incremental() %}
    WHERE _ingested_at::TIMESTAMPTZ > (
        SELECT COALESCE(MAX(_ingested_at::TIMESTAMPTZ), '1970-01-01'::TIMESTAMPTZ)
        FROM {{ this }}
    )
    {% endif %}
),
deduplicado AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY id_produto ORDER BY updated_at DESC) AS rn
    FROM source
)
SELECT
    id_produto::INTEGER               AS id_produto,
    id_categoria::INTEGER             AS id_categoria,
    id_fornecedor::INTEGER            AS id_fornecedor,
    TRIM(sku)::VARCHAR                AS sku,
    TRIM(nome)::VARCHAR               AS nome,
    TRIM(marca)::VARCHAR              AS marca,
    peso_kg::NUMERIC(8,3)            AS peso_kg,
    ativo::BOOLEAN                    AS ativo,
    created_at::TIMESTAMPTZ           AS created_at,
    updated_at::TIMESTAMPTZ           AS updated_at,
    _ingested_at::TIMESTAMPTZ         AS _ingested_at
FROM deduplicado WHERE rn = 1
{% endif %}
