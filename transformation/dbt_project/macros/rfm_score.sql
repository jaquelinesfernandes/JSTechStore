{% macro rfm_recency_score(recencia_dias) %}
    {#
      Pontua recência em quintis: 5 = comprou há menos de 30 dias, 1 = mais de 365 dias.
    #}
    CASE
        WHEN {{ recencia_dias }} <=  30 THEN 5
        WHEN {{ recencia_dias }} <=  90 THEN 4
        WHEN {{ recencia_dias }} <= 180 THEN 3
        WHEN {{ recencia_dias }} <= 365 THEN 2
        ELSE 1
    END
{% endmacro %}

{% macro rfm_frequencia_score(qtd_pedidos) %}
    {#
      Pontua frequência: 5 = 20+ pedidos, 1 = apenas 1.
    #}
    CASE
        WHEN {{ qtd_pedidos }} >= 20 THEN 5
        WHEN {{ qtd_pedidos }} >= 10 THEN 4
        WHEN {{ qtd_pedidos }} >=  5 THEN 3
        WHEN {{ qtd_pedidos }} >=  2 THEN 2
        ELSE 1
    END
{% endmacro %}

{% macro rfm_monetario_score(ltv) %}
    {#
      Pontua valor: baseado em quintis do LTV.
      Os thresholds abaixo são calibrados para o ticket médio da JSTechStore (~R$800).
    #}
    CASE
        WHEN {{ ltv }} >= 10000 THEN 5
        WHEN {{ ltv }} >=  5000 THEN 4
        WHEN {{ ltv }} >=  2000 THEN 3
        WHEN {{ ltv }} >=   800 THEN 2
        ELSE 1
    END
{% endmacro %}

{% macro rfm_segmento(score_r, score_f, score_m) %}
    {#
      Classifica o cliente em segmento RFM baseado nos scores individuais.
    #}
    CASE
        WHEN {{ score_r }} = 5 AND {{ score_f }} >= 4                     THEN 'Campeoes'
        WHEN {{ score_r }} >= 4 AND {{ score_f }} >= 3                    THEN 'Clientes_Fieis'
        WHEN {{ score_r }} = 5 AND {{ score_f }} <= 2                     THEN 'Novos_Clientes'
        WHEN {{ score_r }} >= 3 AND {{ score_f }} >= 3 AND {{ score_m }} >= 3 THEN 'Potencial_Fidelizacao'
        WHEN {{ score_r }} >= 4 AND {{ score_f }} <= 2 AND {{ score_m }} <= 2 THEN 'Promissores'
        WHEN {{ score_r }} <= 2 AND {{ score_f }} >= 4 AND {{ score_m }} >= 4 THEN 'Em_Risco'
        WHEN {{ score_r }} <= 2 AND {{ score_f }} >= 3                    THEN 'Hibernando'
        WHEN {{ score_r }} = 1 AND {{ score_f }} = 1 AND {{ score_m }} = 1 THEN 'Perdidos'
        ELSE 'Regulares'
    END
{% endmacro %}

{% macro nivel_fidelidade(ltv, qtd_pedidos) %}
    {#
      Mapeia LTV + frequência para nível de fidelidade (programa TechPoints).
    #}
    CASE
        WHEN {{ ltv }} >= 15000 OR {{ qtd_pedidos }} >= 15 THEN 'Platinum'
        WHEN {{ ltv }} >=  6000 OR {{ qtd_pedidos }} >=  8 THEN 'Gold'
        WHEN {{ ltv }} >=  2000 OR {{ qtd_pedidos }} >=  3 THEN 'Silver'
        ELSE 'Bronze'
    END
{% endmacro %}
