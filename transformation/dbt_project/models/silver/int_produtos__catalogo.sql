{{
    config(
        unique_key='id_produto',
        post_hook="ANALYZE {{ this }}"
    )
}}

/*
  Catálogo enriquecido: produto + categoria + fornecedor + preço vigente.
  Preço vigente = maior dt_vigencia_inicio com dt_vigencia_fim IS NULL ou > hoje.
*/

WITH produtos AS (
    SELECT * FROM {{ ref('stg_produtos__produtos') }}
),
categorias AS (
    SELECT * FROM {{ ref('stg_produtos__categorias') }}
),
fornecedores AS (
    SELECT * FROM {{ ref('stg_produtos__fornecedores') }}
),
precos_vigentes AS (
    SELECT DISTINCT ON (id_produto)
        id_produto,
        preco_venda,
        custo_unitario,
        dt_vigencia_inicio
    FROM {{ ref('stg_produtos__precos') }}
    WHERE dt_vigencia_fim IS NULL
       OR dt_vigencia_fim >= DATE '{{ var("end_date") }}'
    ORDER BY id_produto, dt_vigencia_inicio DESC
)
SELECT
    p.id_produto,
    p.sku,
    p.nome                             AS nome_produto,
    p.marca,
    p.peso_kg,
    p.ativo,
    c.id_categoria,
    c.nome                             AS categoria,
    c.subcategoria,
    f.id_fornecedor,
    f.nome_fornecedor,
    f.cnpj                             AS cnpj_fornecedor,
    f.pais_origem,
    f.prazo_entrega_dias,
    pv.preco_venda                     AS preco_venda_vigente,
    pv.custo_unitario                  AS custo_vigente,
    ROUND(
        (pv.preco_venda - pv.custo_unitario) / NULLIF(pv.preco_venda, 0),
        4
    )                                  AS margem_pct_vigente,
    p.updated_at,
    p._ingested_at
FROM produtos p
LEFT JOIN categorias      c  ON c.id_categoria  = p.id_categoria
LEFT JOIN fornecedores    f  ON f.id_fornecedor  = p.id_fornecedor
LEFT JOIN precos_vigentes pv ON pv.id_produto    = p.id_produto
{% if is_incremental() %}
WHERE p._ingested_at > (
    SELECT COALESCE(MAX(_ingested_at), '1970-01-01'::TIMESTAMPTZ) FROM {{ this }}
)
{% endif %}
