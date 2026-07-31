{{ config(unique_key=['id_produto', 'id_loja']) }}

{% if execute %}{% set _n = run_query("SELECT count(*) FROM glob('" ~ var('bronze_path') ~ "/estoque/saldo_estoque/**/*.parquet')").columns[0].values()[0] %}{% else %}{% set _n = 1 %}{% endif %}
{% if _n == 0 and is_incremental() %}SELECT * FROM {{ this }} WHERE false{% else %}

WITH source AS (
    SELECT *
    FROM read_parquet('{{ var("bronze_path") }}/estoque/saldo_estoque/**/*.parquet')
    {% if is_incremental() %}
    WHERE _ingested_at::TIMESTAMPTZ > (
        SELECT COALESCE(MAX(_ingested_at::TIMESTAMPTZ), '1970-01-01'::TIMESTAMPTZ)
        FROM {{ this }}
    )
    {% endif %}
),
deduplicado AS (
    SELECT *,
        ROW_NUMBER() OVER (PARTITION BY id_produto, id_loja ORDER BY updated_at DESC) AS rn
    FROM source
)
SELECT
    id_saldo::INTEGER                 AS id_saldo,
    id_produto::INTEGER               AS id_produto,
    id_loja::INTEGER                  AS id_loja,
    qtd_disponivel::INTEGER           AS qtd_disponivel,
    qtd_reservada::INTEGER            AS qtd_reservada,
    qtd_minima::INTEGER               AS qtd_minima,
    dt_ultima_atualizacao::DATE       AS dt_ultima_atualizacao,
    updated_at::TIMESTAMPTZ           AS updated_at,
    _ingested_at::TIMESTAMPTZ         AS _ingested_at
FROM deduplicado WHERE rn = 1
{% endif %}
