{#-
  american_to_implied_sql  (Edge Program — Story E3.0)

  Vig-included implied probability from an American-odds expression, in SQL.
  Mirrors betting_ml/utils/totals_probability.american_to_implied EXACTLY so the
  warehouse de-vig and the Python serve-time de-vig agree:
    favorite (a < 0):  -a / (-a + 100)
    underdog (a >= 0): 100 / (a + 100)
  NULL in → NULL out (so a missing side propagates to a NULL fair prob and the
  downstream additive de-vig yields NULL, not a bogus 0/1).

  `price_expr` is a raw SQL expression string (e.g. 'max(h2h_home_px)'); it is
  substituted verbatim, so pass a single scalar/aggregate expression.

  NET-NEW macro: used only by feature_pregame_edge_market. Does not touch any
  existing model or macro.
-#}
{% macro american_to_implied_sql(price_expr) -%}
    case
        when ({{ price_expr }}) is null then null
        when ({{ price_expr }}) < 0
            then (-({{ price_expr }})) / ((-({{ price_expr }})) + 100.0)
        else 100.0 / (({{ price_expr }}) + 100.0)
    end
{%- endmacro %}
