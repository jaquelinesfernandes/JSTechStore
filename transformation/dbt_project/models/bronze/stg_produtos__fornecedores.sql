{{ config(unique_key='id_fornecedor') }}

{% if execute %}{% set _n = run_query("SELECT count(*) FROM glob('" ~ var('bronze_path') ~ "/produtos/fornecedores/**/*.parquet')").columns[0].values()[0] %}{% else %}{% set _n = 1 %}{% endif %}
{% if _n == 0 and is_incremental() %}SELECT * FROM {{ this }} WHERE false{% else %}

WITH source AS (
    SELECT *
    FROM read_parquet('{{ var("bronze_path") }}/produtos/fornecedores/**/*.parquet')
    {% if is_incremental() %}
    WHERE _ingested_at::TIMESTAMPTZ > (
        SELECT COALESCE(MAX(_ingested_at::TIMESTAMPTZ), '1970-01-01'::TIMESTAMPTZ)
        FROM {{ this }}
    )
    {% endif %}
),
deduplicado AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY id_fornecedor ORDER BY updated_at DESC) AS rn
    FROM source
)
SELECT
    id_fornecedor::INTEGER            AS id_fornecedor,
    TRIM(nome_fornecedor)::VARCHAR    AS nome_fornecedor,
    TRIM(cnpj)::VARCHAR               AS cnpj,
    TRIM(categoria_principal)::VARCHAR AS categoria_principal,
    TRIM(pais_origem)::VARCHAR        AS pais_origem,
    prazo_entrega_dias::INTEGER       AS prazo_entrega_dias,
    ativo::BOOLEAN                    AS ativo,
    updated_at::TIMESTAMPTZ           AS updated_at,
    _ingested_at::TIMESTAMPTZ         AS _ingested_at
FROM deduplicado WHERE rn = 1
{% endif %}
