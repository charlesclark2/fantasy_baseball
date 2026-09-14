{#-
  sport_delta(sport, source) — the FROM-clause expression for ANY sport's raw Delta table.

  `ncaaf_lake.sql` and `nfl_lake.sql` are the same six lines twice, differing only in the
  prefix, which is one logical thing with two owners (INC-30 / INC-36 / INC-38). Rather than
  add a third copy for NCAAB, the body lives here once and `ncaab_delta` delegates. Migrating
  `ncaaf_delta` / `nfl_delta` onto it is a one-line change each, left as a follow-up because
  both verticals are in-season and this story should not move their SQL.
-#}
{% macro sport_delta(sport, source, tier='raw') %}
  {%- set root = var('lake_root', '') -%}
  {%- if root and root | length > 0 -%}
    delta_scan('{{ root }}/{{ sport }}/{{ tier }}/{{ source }}')
  {%- else -%}
    delta_scan('s3://{{ var('lake_bucket') }}/{{ sport }}/{{ tier }}/{{ source }}')
  {%- endif -%}
{% endmacro %}

{#- ncaab_delta(source) — NCAAB's seam onto the shared expression. -#}
{% macro ncaab_delta(source, tier='raw') %}
  {{- sport_delta('ncaab', source, tier) -}}
{% endmacro %}
