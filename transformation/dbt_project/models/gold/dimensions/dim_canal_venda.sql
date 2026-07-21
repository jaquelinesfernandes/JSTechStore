{{ config(materialized='table') }}

/*
  Dimensão canal de venda: tabela estática de 5 canais.
*/

SELECT
    {{ get_surrogate_key(['canal_venda']) }}        AS sk_canal_venda,
    canal_venda,
    CASE canal_venda
        WHEN 'loja_fisica'         THEN 'Loja Física'
        WHEN 'site_proprio'        THEN 'Site Próprio'
        WHEN 'marketplace_ml'      THEN 'Mercado Livre'
        WHEN 'marketplace_amazon'  THEN 'Amazon'
        WHEN 'marketplace_shopee'  THEN 'Shopee'
        ELSE canal_venda
    END                                            AS descricao_canal,
    CASE canal_venda
        WHEN 'loja_fisica'         THEN 'Físico'
        ELSE 'Digital'
    END                                            AS tipo_canal,
    CASE canal_venda
        WHEN 'loja_fisica'         THEN 'Próprio'
        WHEN 'site_proprio'        THEN 'Próprio'
        ELSE 'Marketplace'
    END                                            AS plataforma
FROM (
    VALUES
        ('loja_fisica'),
        ('site_proprio'),
        ('marketplace_ml'),
        ('marketplace_amazon'),
        ('marketplace_shopee')
) t(canal_venda)
