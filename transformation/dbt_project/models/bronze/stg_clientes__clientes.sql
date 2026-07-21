{{ config(unique_key='id_cliente') }}

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
    UPPER(TRIM(uf))::CHAR(2)         AS uf,
    data_cadastro::DATE               AS data_cadastro,
    canal_origem::VARCHAR             AS canal_origem,
    nivel_fidelidade::VARCHAR         AS nivel_fidelidade,
    ativo::BOOLEAN                    AS ativo,
    created_at::TIMESTAMPTZ           AS created_at,
    updated_at::TIMESTAMPTZ           AS updated_at,
    _ingested_at::TIMESTAMPTZ         AS _ingested_at
FROM deduplicado
WHERE rn = 1
