"""build_pre_lineup_proj_contracts_33_5.py — Story 33.5 Step 1: expanded pre-lineup contracts.

The 33.0 pre-lineup contracts are the Class-A subset of each live contract (the audit
SUBTRACTS the Class-B lineup-gated cols). They have NO offense-lineup signal — the dropped
`avg_woba_30d` / `*_vs_lhp/rhp` batter aggregates are exactly what the morning model is blind to.

Story 33.3 built the pre-lineup REPLACEMENT for that signal: the P(start)-weighted expected
batter aggregates (`home_/away_exp_*` in feature_pregame_game_features), validated corr ~0.78–0.80
vs the confirmed-lineup averages. These are Class-A BY CONSTRUCTION (computed from recent start
history + rolling stats, no confirmed lineup) — but the audit cannot pick them up: they are
net-new (not members of any live contract) and would even mis-classify as Class-B today because
the LIVE P(start) table ships with 33.6 (so they're null for future games until then). So we
append them EXPLICITLY here.

Output: `feature_columns_pre_lineup_<target>_proj.json` (the 33.0 Class-A set + the exp_* family).
The 33.0 base contracts are left UNTOUCHED — they remain the deployed floor and the 33.5 gate baseline.

Instant (pure file rewrite, no Snowflake):
    uv run python betting_ml/scripts/build_pre_lineup_proj_contracts_33_5.py
"""
from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# The Story 33.3 expected-lineup family in feature_pregame_game_features (28 cols/side),
# verified present in BETTING_FEATURES.FEATURE_PREGAME_GAME_FEATURES (2026-06-16).
_EXP_STEMS = [
    "expected_lineup_mass", "expected_n_candidates", "exp_lhb_count", "exp_rhb_count",
    "exp_woba_30d", "exp_xwoba_30d", "exp_k_pct_30d", "exp_bb_pct_30d",
    "exp_hard_hit_pct_30d", "exp_barrel_pct_30d", "exp_whiff_rate_30d", "exp_chase_rate_30d",
    "exp_woba_std", "exp_xwoba_std", "exp_k_pct_std", "exp_bb_pct_std",
    "exp_hard_hit_pct_std", "exp_barrel_pct_std",
    "exp_woba_vs_lhp", "exp_xwoba_vs_lhp", "exp_k_pct_vs_lhp", "exp_bb_pct_vs_lhp",
    "exp_hard_hit_pct_vs_lhp",
    "exp_woba_vs_rhp", "exp_xwoba_vs_rhp", "exp_k_pct_vs_rhp", "exp_bb_pct_vs_rhp",
    "exp_hard_hit_pct_vs_rhp",
]
_EXP_FAMILY = [f"{side}_{stem}" for side in ("home", "away") for stem in _EXP_STEMS]

_TARGETS = {
    "home_win":   "betting_ml/models/home_win/feature_columns_pre_lineup_home_win.json",
    "run_diff":   "betting_ml/models/run_differential/feature_columns_pre_lineup_run_diff.json",
    "total_runs": "betting_ml/models/total_runs/feature_columns_pre_lineup_total_runs.json",
}


def main() -> None:
    for tgt, base_rel in _TARGETS.items():
        base_path = PROJECT_ROOT / base_rel
        base = json.loads(base_path.read_text())
        base_cols = base["feature_cols"]
        add = [c for c in _EXP_FAMILY if c not in base_cols]  # no dup (pythagorean_win_exp* differ)
        proj_cols = base_cols + add
        out_path = base_path.with_name(base_path.stem + "_proj.json")
        out_path.write_text(json.dumps({
            "target": base["target"],
            "model_name": f"pre_lineup_{tgt}_proj",
            "story": "33.5",
            "n_features": len(proj_cols),
            "derived_from": (f"{base_rel} ({len(base_cols)} Class-A) + {len(add)} Story-33.3 "
                             f"expected-lineup (exp_*) projection features"),
            "feature_cols": proj_cols,
        }, indent=2))
        print(f"  {tgt:11s}: {len(base_cols)} Class-A + {len(add)} exp_* = {len(proj_cols)}  ->  {out_path.name}")


if __name__ == "__main__":
    main()
