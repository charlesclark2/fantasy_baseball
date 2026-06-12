"""Story 30.1 — identifier/temporal feature-hygiene flagger.

Leakage-prone *identifier* and *temporal* columns (raw entity IDs, park IDs,
the season constant) survive the importance-only prune filters because a tree
can MEMORIZE them: shuffling the column hurts CV error, so they score as
"important" even though they carry no transferable baseball signal and go
out-of-distribution at serve time (`game_year` is the worst case — trained on
2021-2025, served as the constant 2026).

This module provides a single, shared identifier detector so both the SHAP
flagger (`analyze_feature_importance.py`) and the per-target permutation flagger
(`feature_importance_per_target.py`) catch the same columns.

Design note — why NAME is the primary signal, not cardinality:
    Story 30.1 spec suggested "regex on name + cardinality≈n_rows". Empirically
    (2026-06-11, fold_2025, n=10005) cardinality≈n_rows is a POOR discriminator:
      - home_starter_pitcher_id (a real raw identifier): nunique=683, ratio=0.068
        — LOW, because the same pitchers recur across games.
      - venue_id: 30 (ratio 0.003); game_year: 5 (ratio 0.0005) — also low.
      - home_win_prob_consensus (a legitimate CONTINUOUS feature): ratio=0.598
        — HIGH.
    A pure cardinality≈n_rows rule would therefore MISS the recurring IDs and
    FALSE-POSITIVE the continuous probability features. The robust catch is the
    NAME regex; cardinality is retained only as a reported diagnostic and as a
    secondary heuristic for *unnamed* high-cardinality integer codes.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

# Identifier / temporal column-name patterns (Story 30.1 spec set):
#   *_id, *_pk, game_year, season, venue_id, *_cluster_id
# Deliberately does NOT match the *_season STAT suffix (e.g.
# home_starter_csw_pct_season, away_team_oaa_prior_season) — those are
# season-aggregated statistics, not the temporal `season` identifier.
_IDENTIFIER_NAME_RE = re.compile(
    r"(_id$|_pk$|^game_year$|^season$|_cluster_id$)"
)

# Secondary heuristic for raw integer codes that slip past the name regex:
# an integer-valued column whose distinct-value ratio exceeds this fraction of
# rows is suspicious as an unnamed surrogate key.
_HIGH_CARD_INT_RATIO = 0.50


def is_identifier_name(col: str) -> bool:
    """True if the column name matches the identifier/temporal pattern set."""
    return bool(_IDENTIFIER_NAME_RE.search(col))


def flag_identifier_features(
    feature_names: list[str],
    values: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Flag identifier/temporal columns.

    Parameters
    ----------
    feature_names:
        The feature columns to assess.
    values:
        Optional raw (pre-imputation) feature frame. When supplied, per-column
        cardinality, distinct/row ratio, and integer-valued flags are computed
        and used for the secondary unnamed-high-cardinality-int heuristic.

    Returns
    -------
    DataFrame indexed by feature with columns:
        name_match            — name matches the identifier/temporal regex
        cardinality           — distinct non-null values (NaN if no `values`)
        card_ratio            — cardinality / n_rows  (NaN if no `values`)
        integer_valued        — all non-null values are whole numbers
        high_card_int         — integer-valued AND card_ratio > 0.50
        identifier_risk       — name_match OR high_card_int  (the flag)
        reason                — human-readable explanation
    """
    n_rows = len(values) if values is not None else None
    rows = []
    for col in feature_names:
        name_match = is_identifier_name(col)
        cardinality = np.nan
        card_ratio = np.nan
        integer_valued = False
        high_card_int = False

        if values is not None and col in values.columns:
            s = pd.to_numeric(values[col], errors="coerce")
            non_null = s.dropna()
            cardinality = int(non_null.nunique())
            card_ratio = cardinality / n_rows if n_rows else np.nan
            if len(non_null):
                integer_valued = bool(np.allclose(non_null, np.round(non_null)))
            high_card_int = bool(
                integer_valued and card_ratio is not np.nan
                and card_ratio > _HIGH_CARD_INT_RATIO
            )

        identifier_risk = bool(name_match or high_card_int)

        if name_match and high_card_int:
            reason = "name matches identifier/temporal pattern; high-cardinality integer code"
        elif name_match:
            reason = "name matches identifier/temporal pattern (*_id/*_pk/game_year/season/*_cluster_id)"
        elif high_card_int:
            reason = f"unnamed high-cardinality integer code (card_ratio={card_ratio:.3f})"
        else:
            reason = ""

        rows.append(
            {
                "feature": col,
                "name_match": name_match,
                "cardinality": cardinality,
                "card_ratio": card_ratio,
                "integer_valued": integer_valued,
                "high_card_int": high_card_int,
                "identifier_risk": identifier_risk,
                "reason": reason,
            }
        )

    return pd.DataFrame(rows).set_index("feature")
