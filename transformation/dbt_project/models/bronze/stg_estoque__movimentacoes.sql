{{ config(unique_key='id_movimentacao') }}

WITH source AS (
    SELECT *
    FROM read_parquet('{{ var("bronze_path") }}/estoque/movimentacoes/**/*.parquet')
    {% if is_incremental() %}
    WHERE _ingested_at::TIMESTAMPTZ > (
        SELECT COALESCE(MAX(_ingested_at::TIMESTAMPTZ), '1970-01-01'::TIMESTAMPTZ)
        FROM {{ this }}
    )
    {% endif %}
),
deduplicado AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY id_movimentacao ORDER BY updated_at DESC) AS rn
    FROM source
)
SELECT
    id_movimentacao::INTEGER          AS id_movimentacao,
    id_produto::INTEGER               AS id_produto,
    id_loja::INTEGER                  AS id_loja,
    tipo_mov::VARCHAR                 AS tipo_mov,
    qtd::INTEGER                      AS qtd,
    dt_movimentacao::TIMESTAMPTZ      AS dt_movimentacao,
    id_pedido::INTEGER                AS id_pedido,
    custo_unitario::NUMERIC(12,2)     AS custo_unitario,
    observacao::VARCHAR               AS observacao,
    updated_at::TIMESTAMPTZ           AS updated_at,
    _ingested_at::TIMESTAMPTZ         AS _ingested_at
FROM deduplicado WHERE rn = 1
