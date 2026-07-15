{#-
  ncaaf_delta(source) — the FROM-clause expression for an NCAAF raw Delta lake table.

  Raw tables are Delta (NCAAF is Delta-native from day one — E11.20 inheritance), so reads
  go through DuckDB's read-only `delta` extension via delta_scan(). The `lake_root` var
  routes to a LOCAL-FS Delta tree (offline dev / the P0.2 smoke); empty → S3.

  Usage:  select ... from {{ ncaaf_delta('games') }}
-#}
{% macro ncaaf_delta(source, tier='raw') %}
  {%- set root = var('lake_root', '') -%}
  {%- if root and root | length > 0 -%}
    delta_scan('{{ root }}/ncaaf/{{ tier }}/{{ source }}')
  {%- else -%}
    delta_scan('s3://{{ var('lake_bucket') }}/ncaaf/{{ tier }}/{{ source }}')
  {%- endif -%}
{% endmacro %}
