"""Card 4.8 — Feature selection for the Phase 4 ML pipeline.

Public API:
    select_features(df, targets, corr_threshold, multicollinearity_threshold)
        -> tuple[list[str], dict[str, str]]

Algorithm:
    1. Candidates = numeric columns minus targets and protected features.
    2. Drop features where |Pearson r| < corr_threshold for ALL three targets.
    3. Resolve multicollinear pairs (|r| > multicollinearity_threshold): drop the
       member with the lower max |r| to any target; break ties by column name.
    4. Unconditionally retain protected features regardless of steps 2–3.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

PROTECTED_FEATURES: frozenset[str] = frozenset(
    {"post_2022_rules", "game_year", "home_win_rate_trailing_3yr"}
)


def select_features(
    df: pd.DataFrame,
    targets: list[str],
    corr_threshold: float = 0.02,
    multicollinearity_threshold: float = 0.85,
) -> tuple[list[str], dict[str, str]]:
    """Return (retained_features, dropped_with_reasons).

    Parameters
    ----------
    df:
        DataFrame containing both feature columns and target columns.
    targets:
        Names of the target columns (excluded from candidate set).
    corr_threshold:
        Features with max |r| < this threshold across all targets are dropped.
    multicollinearity_threshold:
        Within surviving features, pairs with |r| > this threshold trigger a
        drop of the member with the lower max target correlation.

    Returns
    -------
    retained_features:
        List of feature names to pass to downstream model training.
    dropped_with_reasons:
        Dict mapping each dropped feature name to a reason string:
        "near_zero_correlation" or "multicollinearity:<retained_feature>".
    """
    target_set = set(targets)
    dropped: dict[str, str] = {}

    # Candidate set: numeric columns that are not targets.
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    candidates = [c for c in numeric_cols if c not in target_set]

    # --- Step 1: near-zero correlation filter ---
    # Compute Pearson r to each target for all candidates.
    target_corrs: dict[str, pd.Series] = {}
    for t in targets:
        if t not in df.columns:
            continue
        y = df[t].astype(float)
        corrs = {}
        for c in candidates:
            x = df[c].astype(float)
            valid = x.notna() & y.notna()
            if valid.sum() < 10:
                corrs[c] = 0.0
                continue
            r = np.corrcoef(x[valid], y[valid])[0, 1]
            corrs[c] = float(r) if not np.isnan(r) else 0.0
        target_corrs[t] = pd.Series(corrs)

    # max |r| across all targets per candidate
    corr_df = pd.DataFrame(target_corrs, index=candidates).fillna(0.0)
    max_abs_r = corr_df.abs().max(axis=1)

    surviving: list[str] = []
    for c in candidates:
        if c in PROTECTED_FEATURES:
            surviving.append(c)
            continue
        if max_abs_r[c] < corr_threshold:
            dropped[c] = "near_zero_correlation"
        else:
            surviving.append(c)

    # --- Step 2: multicollinearity resolution ---
    # Greedy: repeatedly remove the weaker member of the highest-correlated pair.
    if len(surviving) > 1:
        feature_data = df[surviving].astype(float)
        fc = feature_data.corr().abs()

        # Work with a mutable set so we skip already-dropped features.
        alive = list(surviving)
        alive_set = set(alive)

        # Build all pairs exceeding threshold, sorted descending by |r|.
        pairs: list[tuple[float, str, str]] = []
        for i, a in enumerate(alive):
            for b in alive[i + 1 :]:
                r_val = fc.at[a, b]
                if r_val > multicollinearity_threshold:
                    pairs.append((r_val, a, b))
        pairs.sort(key=lambda x: x[0], reverse=True)

        for r_val, a, b in pairs:
            if a not in alive_set or b not in alive_set:
                continue
            # Protected features are never dropped.
            a_protected = a in PROTECTED_FEATURES
            b_protected = b in PROTECTED_FEATURES
            if a_protected and b_protected:
                continue
            if a_protected:
                loser = b
            elif b_protected:
                loser = a
            else:
                r_a = max_abs_r.get(a, 0.0)
                r_b = max_abs_r.get(b, 0.0)
                if r_b < r_a:
                    loser = b
                elif r_a < r_b:
                    loser = a
                else:
                    # Tie-break: alphabetically later name is dropped.
                    loser = max(a, b)
            winner = b if loser == a else a
            dropped[loser] = f"multicollinearity:{winner}"
            alive_set.discard(loser)

        surviving = [c for c in surviving if c in alive_set]

    # --- Step 3: guarantee protected features are in the retained list ---
    surviving_set = set(surviving)
    for pf in PROTECTED_FEATURES:
        if pf in df.columns and pf not in surviving_set:
            surviving.append(pf)
            dropped.pop(pf, None)

    return surviving, dropped
