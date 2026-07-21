{{ config(unique_key='id_loja') }}

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
    UPPER(TRIM(uf))::CHAR(2)         AS uf,
    TRIM(gerente)::VARCHAR            AS gerente,
    capacidade_m2::INTEGER            AS capacidade_m2,
    dt_abertura::DATE                 AS dt_abertura,
    ativo::BOOLEAN                    AS ativo,
    updated_at::TIMESTAMPTZ           AS updated_at,
    _ingested_at::TIMESTAMPTZ         AS _ingested_at
FROM deduplicado WHERE rn = 1
