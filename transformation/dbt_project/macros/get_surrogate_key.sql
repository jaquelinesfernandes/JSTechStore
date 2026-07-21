{% macro get_surrogate_key(fields) %}
    {#
      Gera surrogate key MD5 a partir de uma lista de campos.
      Equivalente ao dbt_utils.generate_surrogate_key mas explícito para DuckDB.

      Uso: {{ get_surrogate_key(['id_pedido', 'id_item_pedido']) }}
    #}
    MD5(
        CONCAT_WS(
            '-',
            {% for field in fields %}
                COALESCE(CAST({{ field }} AS VARCHAR), 'NULL')
                {%- if not loop.last %}, {% endif %}
            {% endfor %}
        )
    )
{% endmacro %}
