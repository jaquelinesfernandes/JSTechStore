{{ config(unique_key='id_endereco') }}

WITH source AS (
    SELECT *
    FROM read_parquet('{{ var("bronze_path") }}/clientes/enderecos/**/*.parquet')
    {% if is_incremental() %}
    WHERE _ingested_at::TIMESTAMPTZ > (
        SELECT COALESCE(MAX(_ingested_at::TIMESTAMPTZ), '1970-01-01'::TIMESTAMPTZ)
        FROM {{ this }}
    )
    {% endif %}
),
deduplicado AS (
    SELECT *,
        ROW_NUMBER() OVER (PARTITION BY id_endereco ORDER BY updated_at DESC) AS rn
    FROM source
)
SELECT
    id_endereco::INTEGER              AS id_endereco,
    id_cliente::INTEGER               AS id_cliente,
    TRIM(logradouro)::VARCHAR         AS logradouro,
    TRIM(numero)::VARCHAR             AS numero,
    TRIM(complemento)::VARCHAR        AS complemento,
    TRIM(bairro)::VARCHAR             AS bairro,
    TRIM(cep)::VARCHAR                AS cep,
    TRIM(cidade)::VARCHAR             AS cidade,
    UPPER(TRIM(uf))::VARCHAR          AS uf,
    tipo::VARCHAR                     AS tipo,
    updated_at::TIMESTAMPTZ           AS updated_at,
    _ingested_at::TIMESTAMPTZ         AS _ingested_at
FROM deduplicado
WHERE rn = 1
