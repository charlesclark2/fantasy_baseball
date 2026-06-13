"""season_normalization.py — Story 27.7 shared util.

Single source of truth (Python side) for the contact-quality season-normalization
productionized in dbt (Story 27.7). The dbt macro `contact_quality_columns()`
(dbt/macros/season_normalize_contact.sql) owns the IDENTICAL 34-name list on the
SQL side; the public feature mart `feature_pregame_game_features` exposes a
`<col>_seasonnorm` column for each — a z-score against a STRICTLY-PRIOR, AS-OF
league baseline (leakage-safe, prior-season-anchored early).

WHY: the totals 2025 over-bias (+0.67) is a real contact->runs CONVERSION regime
(2025 contact got harder but runs stayed flat). The contact-quality feature LEVEL
inflated without more runs; re-centering each to its season league distribution
removes the spurious level shift. Validated offline in
betting_ml/scripts/regime/totals_season_norm_fix.py (pooled bias +0.367 -> +0.111).

PRODUCTION CONTRACT: training and serving must agree. So we do NOT z-score in
pandas at train time (that was the offline prototype, and it cannot be reproduced
live where the season mean is unknown early). Instead we SWAP the feature NAME:
each contact column `c` is replaced by `c_seasonnorm`, so the saved contract
records `c_seasonnorm` and predict_today pulls the dbt-normalized value at serve
time — full train/serve parity.

The 34 names below MUST stay byte-for-byte in sync with the dbt macro. A drift
guard test (test_season_norm_parity) compares the two.
"""

from __future__ import annotations

# Canonical contact-quality columns — keep IDENTICAL to contact_quality_columns()
# in dbt/macros/season_normalize_contact.sql.
CONTACT_QUALITY_COLUMNS: list[str] = [
    "home_bp_eb_xwoba",
    "away_bp_eb_xwoba",
    "away_pit_xwoba_against_30d",
    "home_lineup_avg_xwoba_vs_cluster",
    "away_starter_xwoba_against_std",
    "away_xwoba_with_runners_on_30d",
    "away_off_hard_hit_pct_std",
    "home_starter_xwoba_against_30d",
    "home_starter_xwoba_against_7d",
    "away_vs_lhp_xwoba_30d",
    "home_off_xwoba_30d",
    "away_xwoba_with_risp_30d",
    "home_lineup_vs_away_starter_xwoba_adj",
    "home_bp_xwoba_against_30d",
    "home_pit_xwoba_against_7d",
    "away_lineup_vs_home_starter_xwoba_adj",
    "home_off_barrel_pct_30d",
    "away_off_hard_hit_pct_7d",
    "home_pit_hard_hit_pct_30d",
    "home_pit_hard_hit_pct_7d",
    "home_bp_xwoba_against_14d",
    "home_pit_barrel_pct_30d",
    "away_starter_eb_xwoba_uncertainty",
    "home_starter_xwoba_7d_minus_std",
    "home_bp_hard_hit_pct_14d",
    "home_bp_hard_hit_pct_30d",
    "away_starter_hard_hit_pct_std",
    "away_starter_xwoba_vs_lhb",
    "home_starter_barrel_pct_std",
    "away_starter_hard_hit_pct_7d",
    "home_team_sequential_bullpen_xwoba",
    "away_team_sequential_bullpen_xwoba",
    "home_starter_eb_xwoba_against_sequential",
    "away_starter_eb_xwoba_against_sequential",
]

_CONTACT_SET = set(CONTACT_QUALITY_COLUMNS)

SEASONNORM_SUFFIX = "_seasonnorm"


def seasonnorm_name(col: str) -> str:
    """The dbt-emitted season-normalized column name for a raw contact column."""
    return f"{col}{SEASONNORM_SUFFIX}"


def swap_contact_to_seasonnorm(
    feature_cols: list[str], available_columns: set | list,
) -> tuple[list[str], list[str], list[str]]:
    """Rewrite a feature list to consume the leakage-safe dbt `_seasonnorm` columns.

    For each contact-quality column `c` in `feature_cols`, replace it with
    `c_seasonnorm` IFF that column exists in `available_columns` (i.e. the dbt
    Story-27.7 build is live). Non-contact columns and contact columns whose
    `_seasonnorm` counterpart is absent are left unchanged.

    Returns (new_feature_cols, swapped, missing):
      - new_feature_cols: the rewritten list (order preserved)
      - swapped:  raw contact names that WERE swapped to `_seasonnorm`
      - missing:  contact names whose `_seasonnorm` column was NOT found (left raw)
                  — a non-empty `missing` means the dbt build is stale; the caller
                  should fail loudly rather than silently train on raw features.
    """
    avail = set(available_columns)
    new_cols: list[str] = []
    swapped: list[str] = []
    missing: list[str] = []
    for c in feature_cols:
        if c in _CONTACT_SET:
            sn = seasonnorm_name(c)
            if sn in avail:
                new_cols.append(sn)
                swapped.append(c)
            else:
                new_cols.append(c)
                missing.append(c)
        else:
            new_cols.append(c)
    return new_cols, swapped, missing
