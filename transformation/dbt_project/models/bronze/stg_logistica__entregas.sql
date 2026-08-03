{{ config(unique_key='id_entrega') }}

WITH source AS (
    SELECT *
    FROM read_parquet('{{ var("bronze_path") }}/logistica/entregas/**/*.parquet', union_by_name := true)
    {% if is_incremental() %}
    WHERE _ingested_at::TIMESTAMPTZ > (
        SELECT COALESCE(MAX(_ingested_at::TIMESTAMPTZ), '1970-01-01'::TIMESTAMPTZ)
        FROM {{ this }}
    )
    {% endif %}
),
deduplicado AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY id_entrega ORDER BY updated_at DESC) AS rn
    FROM source
)
SELECT
    id_entrega::INTEGER               AS id_entrega,
    id_pedido::INTEGER                AS id_pedido,
    id_transportadora::INTEGER        AS id_transportadora,
    id_modalidade::INTEGER            AS id_modalidade,
    id_loja_origem::INTEGER           AS id_loja_origem,
    TRIM(codigo_rastreio)::VARCHAR    AS codigo_rastreio,
    dt_postagem::DATE                 AS dt_postagem,
    dt_promessa::DATE                 AS dt_promessa,
    dt_efetiva::DATE                  AS dt_efetiva,
    fl_sla_atendido::BOOLEAN          AS fl_sla_atendido,
    status::VARCHAR                   AS status,
    updated_at::TIMESTAMPTZ           AS updated_at,
    _ingested_at::TIMESTAMPTZ         AS _ingested_at
FROM deduplicado WHERE rn = 1
