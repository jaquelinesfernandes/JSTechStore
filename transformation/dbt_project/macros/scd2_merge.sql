{% macro scd2_fields(source_alias='s', current_alias='c') %}
    {#
      Gera campos padrão SCD Type 2.
      Uso nos modelos de dimensão:
        {{ scd2_fields() }}
    #}
    CASE
        WHEN {{ current_alias }}.sk IS NULL THEN CURRENT_DATE                 -- novo registro
        WHEN {{ source_alias }}.hash_row <> {{ current_alias }}.hash_row
             THEN CURRENT_DATE                                                 -- mudança detectada
        ELSE {{ current_alias }}.valid_from
    END AS valid_from,

    DATE '9999-12-31'                                                         AS valid_to,
    TRUE                                                                      AS fl_current
{% endmacro %}


{% macro scd2_close_expired() %}
    {#
      UPDATE para fechar registros expirados — chamado ANTES do INSERT no modelo SCD2.
      Deve ser executado via pre-hook no modelo dim correspondente.

      Uso no dbt_project.yml (ou no {{ config() }} do modelo):
        pre_hook: "{{ scd2_close_expired() }}"

      O modelo deve ter colunas: hash_row, sk, valid_to, fl_current, <nk_col>.
    #}
    UPDATE {{ this }}
    SET
        valid_to   = CURRENT_DATE - INTERVAL '1 day',
        fl_current = FALSE
    WHERE fl_current = TRUE
      AND sk NOT IN (
          SELECT {{ get_surrogate_key(['nk']) }}
          FROM {{ this }}
          WHERE fl_current = TRUE
      )
{% endmacro %}


{% macro hash_row(fields) %}
    {#
      Gera hash MD5 de um conjunto de campos para detecção de mudança (SCD2).
      Uso: {{ hash_row(['nome', 'email', 'nivel_fidelidade']) }}
    #}
    MD5(
        CONCAT_WS(
            '|',
            {% for field in fields %}
                COALESCE(CAST({{ field }} AS VARCHAR), '')
                {%- if not loop.last %}, {% endif %}
            {% endfor %}
        )
    )
{% endmacro %}
