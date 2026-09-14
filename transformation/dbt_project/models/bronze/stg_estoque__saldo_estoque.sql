{{
    config(
        unique_key=['id_produto', 'id_loja', 'dt_ultima_atualizacao']
    )
}}

/*
  Staging saldo_estoque: snapshot diário por produto × loja.
  Grão = 1 linha por (id_produto, id_loja, dt_ultima_atualizacao).
  unique_key inclui a data para preservar o histórico de snapshots —
  cada dia gera uma nova linha no fato, permitindo série temporal de estoque.
*/
WITH source AS (
    SELECT *
    FROM read_parquet('{{ var("bronze_path") }}/estoque/saldo_estoque/**/*.parquet', union_by_name := true)
    {% if is_incremental() %}
    WHERE _ingested_at::TIMESTAMPTZ > (
        SELECT COALESCE(MAX(_ingested_at::TIMESTAMPTZ), '1970-01-01'::TIMESTAMPTZ)
        FROM {{ this }}
    )
    {% endif %}
),
deduplicado AS (
    SELECT *,
        ROW_NUMBER() OVER (
            PARTITION BY id_produto, id_loja, dt_ultima_atualizacao
            ORDER BY updated_at DESC
        ) AS rn
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
