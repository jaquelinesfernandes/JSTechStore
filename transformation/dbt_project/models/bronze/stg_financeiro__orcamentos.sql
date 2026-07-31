{{ config(unique_key='id_orcamento') }}

WITH source AS (
    SELECT *
    FROM read_parquet('{{ var("bronze_path") }}/financeiro/orcamentos/**/*.parquet')
    {% if is_incremental() %}
    WHERE _ingested_at::TIMESTAMPTZ > (
        SELECT COALESCE(MAX(_ingested_at::TIMESTAMPTZ), '1970-01-01'::TIMESTAMPTZ)
        FROM {{ this }}
    )
    {% endif %}
),
deduplicado AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY id_orcamento ORDER BY updated_at DESC) AS rn
    FROM source
)
SELECT
    id_orcamento::INTEGER             AS id_orcamento,
    id_loja::INTEGER                  AS id_loja,
    canal_venda::VARCHAR              AS canal_venda,
    ano::INTEGER                      AS ano,
    mes::INTEGER                      AS mes,
    valor_meta_receita::NUMERIC(14,2) AS valor_meta_receita,
    valor_meta_margem::NUMERIC(14,2)  AS valor_meta_margem,
    qtd_meta_pedidos::INTEGER         AS qtd_meta_pedidos,
    updated_at::TIMESTAMPTZ           AS updated_at,
    _ingested_at::TIMESTAMPTZ         AS _ingested_at
FROM deduplicado WHERE rn = 1
