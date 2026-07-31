{{ config(unique_key='id_vendedor') }}

{% if execute %}{% set _n = run_query("SELECT count(*) FROM glob('" ~ var('bronze_path') ~ "/rh/vendedores/**/*.parquet')").columns[0].values()[0] %}{% else %}{% set _n = 1 %}{% endif %}
{% if _n == 0 and is_incremental() %}SELECT * FROM {{ this }} WHERE false{% else %}

WITH source AS (
    SELECT *
    FROM read_parquet('{{ var("bronze_path") }}/rh/vendedores/**/*.parquet')
    {% if is_incremental() %}
    WHERE _ingested_at::TIMESTAMPTZ > (
        SELECT COALESCE(MAX(_ingested_at::TIMESTAMPTZ), '1970-01-01'::TIMESTAMPTZ)
        FROM {{ this }}
    )
    {% endif %}
),
deduplicado AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY id_vendedor ORDER BY updated_at DESC) AS rn
    FROM source
)
SELECT
    id_vendedor::INTEGER              AS id_vendedor,
    id_loja::INTEGER                  AS id_loja,
    TRIM(nome)::VARCHAR               AS nome,
    TRIM(cpf)::VARCHAR                AS cpf,
    TRIM(email)::VARCHAR              AS email,
    cargo::VARCHAR                    AS cargo,
    data_admissao::DATE               AS data_admissao,
    ativo::BOOLEAN                    AS ativo,
    updated_at::TIMESTAMPTZ           AS updated_at,
    _ingested_at::TIMESTAMPTZ         AS _ingested_at
FROM deduplicado WHERE rn = 1
{% endif %}
