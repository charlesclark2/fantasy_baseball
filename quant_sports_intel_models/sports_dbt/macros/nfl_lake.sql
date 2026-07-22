{#-
  nfl_delta(source) — the FROM-clause expression for an NFL raw Delta lake table.

  Raw tables are Delta (NFL is Delta-native from day one — E11.20 inheritance), so reads go
  through DuckDB's read-only `delta` extension via delta_scan(). The `lake_root` var routes to
  a LOCAL-FS Delta tree (offline dev / the N0.2 smoke); empty → S3. Parallels ncaaf_delta();
  the only difference is the `nfl/` prefix.

  Usage:  select ... from {{ nfl_delta('schedules') }}
-#}
{% macro nfl_delta(source, tier='raw') %}
  {%- set root = var('lake_root', '') -%}
  {%- if root and root | length > 0 -%}
    delta_scan('{{ root }}/nfl/{{ tier }}/{{ source }}')
  {%- else -%}
    delta_scan('s3://{{ var('lake_bucket') }}/nfl/{{ tier }}/{{ source }}')
  {%- endif -%}
{% endmacro %}

{#-
  nfl_team_norm(col) — normalize an NFL team CODE to its canonical current franchise.

  nflverse uses the CURRENT code for 2020+ (LAR/LAC/LV), but historical rows and some feeds still
  carry the relocation aliases (LA/STL→LAR, SD→LAC, OAK→LV). Applied identically in
  stg_nfl_schedules and stg_nfl_pbp so every team join lands on one code space. `col` is a raw SQL
  column expression.
-#}
{% macro nfl_team_norm(col) %}
  case when {{ col }} in ('LA', 'STL') then 'LAR'
       when {{ col }} in ('SD') then 'LAC'
       when {{ col }} = 'OAK' then 'LV'
       else {{ col }} end
{% endmacro %}
