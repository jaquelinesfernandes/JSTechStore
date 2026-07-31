{{ config(unique_key='id_cliente') }}

{% if execute %}{% set _n = run_query("SELECT count(*) FROM glob('" ~ var('bronze_path') ~ "/clientes/clientes/**/*.parquet')").columns[0].values()[0] %}{% else %}{% set _n = 1 %}{% endif %}
{% if _n == 0 %}
  {% if is_incremental() %}SELECT * FROM {{ this }} WHERE false
  {% else %}
SELECT NULL::INTEGER AS id_cliente, NULL::VARCHAR AS cpf, NULL::VARCHAR AS email,
       NULL::VARCHAR AS telefone, NULL::VARCHAR AS primeiro_nome, NULL::VARCHAR AS nome_completo,
       NULL::VARCHAR AS cep, NULL::VARCHAR AS cidade, NULL::VARCHAR AS uf,
       NULL::DATE AS data_cadastro, NULL::VARCHAR AS canal_origem, NULL::VARCHAR AS nivel_fidelidade,
       NULL::BOOLEAN AS ativo, NULL::TIMESTAMPTZ AS created_at,
       NULL::TIMESTAMPTZ AS updated_at, NULL::TIMESTAMPTZ AS _ingested_at
WHERE false
  {% endif %}
{% else %}

WITH source AS (
    SELECT *
    FROM read_parquet('{{ var("bronze_path") }}/clientes/clientes/**/*.parquet')
    {% if is_incremental() %}
    WHERE _ingested_at::TIMESTAMPTZ > (
        SELECT COALESCE(MAX(_ingested_at::TIMESTAMPTZ), '1970-01-01'::TIMESTAMPTZ)
        FROM {{ this }}
    )
    {% endif %}
),
deduplicado AS (
    SELECT *,
        ROW_NUMBER() OVER (PARTITION BY id_cliente ORDER BY updated_at DESC) AS rn
    FROM source
)
SELECT
    id_cliente::INTEGER               AS id_cliente,
    TRIM(LOWER(cpf))::VARCHAR         AS cpf,
    TRIM(LOWER(email))::VARCHAR       AS email,
    TRIM(telefone)::VARCHAR           AS telefone,
    TRIM(primeiro_nome)::VARCHAR      AS primeiro_nome,
    TRIM(nome_completo)::VARCHAR      AS nome_completo,
    TRIM(cep)::VARCHAR                AS cep,
    TRIM(cidade)::VARCHAR             AS cidade,
    UPPER(TRIM(uf))::VARCHAR          AS uf,
    data_cadastro::DATE               AS data_cadastro,
    canal_origem::VARCHAR             AS canal_origem,
    nivel_fidelidade::VARCHAR         AS nivel_fidelidade,
    ativo::BOOLEAN                    AS ativo,
    created_at::TIMESTAMPTZ           AS created_at,
    updated_at::TIMESTAMPTZ           AS updated_at,
    _ingested_at::TIMESTAMPTZ         AS _ingested_at
FROM deduplicado
WHERE rn = 1
{% endif %}
