{% macro generate_schema_name(custom_schema_name, node) -%}

    {%- set default_schema = target.schema | trim -%}

    {%- if target.name == 'baseball_betting_and_fantasy' -%}
        {%- if custom_schema_name is none -%}
            {{ default_schema }}
        {%- else -%}
            {{ custom_schema_name | trim }}
        {%- endif -%}

    {%- else -%}
        {#- Non-prod targets (dev, ci): prefix every schema with the target name.
            e.g., dev target → dev_betting, dev_betting_features
                  ci  target → ci_betting,  ci_betting_features        -#}
        {%- if custom_schema_name is none -%}
            {{ default_schema }}
        {%- else -%}
            {{ target.name }}_{{ custom_schema_name | trim }}
        {%- endif -%}

    {%- endif -%}

{%- endmacro %}
