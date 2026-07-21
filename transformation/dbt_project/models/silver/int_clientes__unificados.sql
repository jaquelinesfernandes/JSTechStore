{{
    config(
        unique_key='id_cliente',
        post_hook="ANALYZE {{ this }}"
    )
}}

/*
  Modelo intermediário de clientes:
  - Elimina duplicatas pelo CPF (regra: mesmo CPF = mesmo cliente)
  - Calcula métricas RFM para segmentação
  - Atualiza nível de fidelidade com base em LTV e frequência real de compras
*/

WITH clientes AS (
    SELECT * FROM {{ ref('stg_clientes__clientes') }}
),
pedidos_por_cliente AS (
    SELECT
        id_cliente,
        COUNT(*)                                              AS qtd_pedidos,
        SUM(valor_liquido)                                    AS ltv,
        MAX(CAST(dt_pedido AS DATE))                         AS ultima_compra,
        MIN(CAST(dt_pedido AS DATE))                         AS primeira_compra
    FROM {{ ref('stg_vendas__pedidos') }}
    WHERE status NOT IN ('cancelado')
    GROUP BY id_cliente
),
techpoints AS (
    SELECT id_cliente, saldo_pontos
    FROM {{ ref('stg_clientes__techpoints') }}
),
enderecos_principal AS (
    SELECT DISTINCT ON (id_cliente)
        id_cliente, cep, cidade, uf
    FROM {{ ref('stg_clientes__enderecos') }}
    WHERE tipo = 'principal'
    ORDER BY id_cliente, updated_at DESC
),
-- Deduplicação por CPF: mantém o registro mais antigo (data_cadastro menor)
dedup_cpf AS (
    SELECT *,
        ROW_NUMBER() OVER (PARTITION BY cpf ORDER BY data_cadastro ASC, id_cliente ASC) AS rn
    FROM clientes
    WHERE cpf IS NOT NULL AND cpf <> ''
)
SELECT
    dc.id_cliente,
    dc.cpf,
    dc.email,
    dc.telefone,
    dc.primeiro_nome,
    dc.nome_completo,
    COALESCE(ep.cep, dc.cep)         AS cep,
    COALESCE(ep.cidade, dc.cidade)   AS cidade,
    COALESCE(ep.uf, dc.uf)          AS uf,
    dc.data_cadastro,
    dc.canal_origem,
    -- Nível de fidelidade derivado do LTV e frequência reais
    {{ nivel_fidelidade('COALESCE(pc.ltv, 0)', 'COALESCE(pc.qtd_pedidos, 0)') }}
                                     AS nivel_fidelidade,
    COALESCE(pc.qtd_pedidos, 0)      AS qtd_pedidos,
    COALESCE(pc.ltv, 0)             AS ltv,
    pc.ultima_compra,
    pc.primeira_compra,
    -- Recência em dias a partir da data máxima do dataset
    CASE
        WHEN pc.ultima_compra IS NOT NULL
        THEN (DATE '{{ var("end_date") }}' - pc.ultima_compra)::INTEGER
        ELSE NULL
    END                              AS recencia_dias,
    -- Scores RFM
    {{ rfm_recency_score("CASE WHEN pc.ultima_compra IS NOT NULL THEN (DATE '" ~ var("end_date") ~ "' - pc.ultima_compra)::INTEGER ELSE 999 END") }}
                                     AS score_recencia,
    {{ rfm_frequencia_score('COALESCE(pc.qtd_pedidos, 0)') }}
                                     AS score_frequencia,
    {{ rfm_monetario_score('COALESCE(pc.ltv, 0)') }}
                                     AS score_monetario,
    COALESCE(tp.saldo_pontos, 0)     AS saldo_techpoints,
    dc.ativo,
    dc.updated_at,
    dc._ingested_at
FROM dedup_cpf dc
LEFT JOIN pedidos_por_cliente pc ON pc.id_cliente = dc.id_cliente
LEFT JOIN techpoints           tp ON tp.id_cliente = dc.id_cliente
LEFT JOIN enderecos_principal  ep ON ep.id_cliente = dc.id_cliente
WHERE dc.rn = 1
{% if is_incremental() %}
  AND dc._ingested_at > (
      SELECT COALESCE(MAX(_ingested_at), '1970-01-01'::TIMESTAMPTZ) FROM {{ this }}
  )
{% endif %}
