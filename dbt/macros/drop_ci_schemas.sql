{% macro drop_ci_schemas() %}
    {% set schemas = [
        "baseball_data.ci_betting",
        "baseball_data.ci_betting_features"
    ] %}
    {% for schema in schemas %}
        {% do run_query("DROP SCHEMA IF EXISTS " ~ schema ~ " CASCADE") %}
        {{ log("Dropped: " ~ schema, info=True) }}
    {% endfor %}
{% endmacro %}
