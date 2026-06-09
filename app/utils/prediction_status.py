"""Single source of truth for prediction lineup-confirmation status, shared by
every Streamlit page (Today's Picks, Game Insights, EV/Kelly, Market Comparison)
and the FastAPI picks router.

Why this exists: the `prediction_basis` classification, the per-game dedup
priority, and the user-facing provisional wording were copy-pasted across pages
and had started to diverge in *presentation* (a game shown as an actionable pick
on one page and as "provisional — wait for re-score" on another). Centralizing
guarantees continuity: change the rule here and every page moves together.

Two prediction-quality axes — keep them distinct:
  - prediction_basis : is the *displayed prediction* lineup-aware? (post_lineup
                       re-score ran). This drives whether an edge is trustworthy.
  - both_confirmed   : are both teams' lineups *posted* yet? (raw StatsAPI). A
                       game can have lineups posted while the shown prediction is
                       still the provisional morning one — the dangerous mismatch.
"""

from __future__ import annotations

# ── Canonical SQL (inject into page queries so the classification can't drift) ──

# Classify a daily_model_predictions row's basis. Mirrors the columns written by
# scripts/predict_today.py (prediction_type, data_source).
PREDICTION_BASIS_CASE = """CASE
    WHEN prediction_type = 'post_lineup'                 THEN 'lineup_confirmed'
    WHEN COALESCE(data_source, '') = 'intraday_fallback' THEN 'provisional_fallback'
    ELSE 'provisional_pre_lineup'
END"""

# Per-game dedup priority (higher = preferred row). post_lineup > morning-with-odds
# > fallback-with-odds > morning-no-odds > fallback-no-odds; recency breaks ties.
DEDUP_PRIORITY_CASE = """CASE
    WHEN prediction_type = 'post_lineup'                                          THEN 4
    WHEN COALESCE(data_source, '') != 'intraday_fallback' AND has_odds = TRUE     THEN 3
    WHEN has_odds = TRUE                                                          THEN 2
    WHEN COALESCE(data_source, '') != 'intraday_fallback'                        THEN 1
    ELSE 0
END"""

# ── Basis values ────────────────────────────────────────────────────────────────

LINEUP_CONFIRMED = "lineup_confirmed"
PROVISIONAL_FALLBACK = "provisional_fallback"
PROVISIONAL_PRE_LINEUP = "provisional_pre_lineup"

_DEFAULT = PROVISIONAL_PRE_LINEUP

# ── Display semantics (identical wording everywhere) ────────────────────────────

_LABEL = {
    LINEUP_CONFIRMED: "Lineup-confirmed",
    PROVISIONAL_FALLBACK: "Provisional (fallback)",
    PROVISIONAL_PRE_LINEUP: "Provisional (pre-lineup)",
}

_MESSAGE = {
    LINEUP_CONFIRMED: (
        "✅ Lineup-confirmed prediction (post-lineup re-score — accounts for "
        "confirmed starters & lineups)."
    ),
    PROVISIONAL_FALLBACK: (
        "⚠️ Provisional prediction (intraday fallback) — scored on team rolling "
        "stats only, **blind to the confirmed starting pitcher and lineup**. The "
        "edge may be a feature gap, not real value. Wait for the post-lineup "
        "re-score before trusting it."
    ),
    PROVISIONAL_PRE_LINEUP: (
        "⚠️ Provisional prediction (pre-lineup) — generated before lineups were "
        "confirmed, so it may not reflect the confirmed starter/lineup. Wait for "
        "the post-lineup re-score."
    ),
}


def is_confirmed(basis: str | None) -> bool:
    """True only when the displayed prediction is the lineup-confirmed re-score."""
    return basis == LINEUP_CONFIRMED


def basis_label(basis: str | None) -> str:
    return _LABEL.get(basis or _DEFAULT, _LABEL[_DEFAULT])


def basis_message(basis: str | None) -> str:
    """Full prose status message (the exact wording shown on every page)."""
    return _MESSAGE.get(basis or _DEFAULT, _MESSAGE[_DEFAULT])


def lineup_status_emoji(basis: str | None, both_confirmed: bool) -> str:
    """Compact lineup-status icon for tables.

    ✅ the prediction is lineup-confirmed (post-lineup re-score)
    ⚠️ lineups are posted but the prediction is still provisional — re-score
       pending; the edge is not yet trustworthy
    ⏳ lineups not posted yet (provisional)
    """
    if is_confirmed(basis):
        return "✅"
    return "⚠️" if both_confirmed else "⏳"
