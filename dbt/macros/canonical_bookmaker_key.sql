{#-
  canonical_bookmaker_key(col) — bookmaker IDENTITY reconciliation (2026-06-17)

  Single source of truth for collapsing the DIFFERENT keys that ingestion sources use
  for the SAME sportsbook into one canonical key. Left unmapped, such a book either
  double-counts in cross-book dispersion (mart_bookmaker_disagreement) or splits across
  the Odds-API↔Parlay-API source cutover (mart_odds_consensus, per-book edge, CLV
  backtests) — see the 2026-06-17 fanatics/Caesars coverage reconciliation.

  Current rule(s):
    williamhill_us  ⇒  caesars
        Caesars-US is key 'williamhill_us' on The Odds API (bookmaker_title 'Caesars')
        and key 'caesars' on the Parlay API. The titles already agree; only the keys
        diverge, so we canonicalize the KEY and leave every other book untouched.

  Add a WHEN line here when another book's key diverges across feeds — this macro is the
  ONE place that knowledge lives. Applied at the record of ingestion via
  mart_odds_outcomes.bookmaker_key_canonical; any consumer needing unified book identity
  (disagreement, consensus, per-book edge, CLV backtests) reads that canonical column.

  Note: only `williamhill_us` is remapped; all other keys pass through UNCHANGED (original
  casing preserved) so this is a no-op for every book except Caesars-US.
-#}
{% macro canonical_bookmaker_key(col) -%}
    case when lower({{ col }}) = 'williamhill_us' then 'caesars' else {{ col }} end
{%- endmacro %}
