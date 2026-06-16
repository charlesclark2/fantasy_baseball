"""lineup_actual_vs_projected_33_7.py — Story 33.7: marginal value of the ACTUAL lineup over the projection.

33.5 showed the projected `exp_*` aggregates don't beat the 33.0 floor (no signal over team offense). 33.7 asks
the dual, sharper question: holding the model + EVERYTHING else fixed, how much does the REAL (confirmed) lineup
beat the PROJECTION? This decides whether Epic 33's projection thread keeps going or CLOSES — and it gates the
Bayesian "projected=prior → actual=posterior" idea.

CLEAN ISOLATION (the whole point): two arms, IDENTICAL tuned HP, IDENTICAL feature set EXCEPT the lineup-offense
block, which maps 1:1 confirmed↔projected by construction:
  - confirmed arm = 33.0 Class-A floor + the CONFIRMED `avg_*` lineup block  (what a post-lineup serve sees)
  - projected arm = 33.0 Class-A floor + the PROJECTED `exp_*` block          (33.3 / what morning can see)
The block = 26 cols/side (14 rolling-30d/std + 10 prior-season platoon + L/R batter counts). `expected_lineup_mass`
and `n_candidates` are EXCLUDED (projection-only, no confirmed analog) so the ONLY difference between arms is
confirmed-vs-projected lineup offense. ALL other Class-B matchup families (archetype/cluster/sequential/bat-tracking)
are absent from BOTH arms (not in the floor) → can't confound.

VERDICT (MEASUREMENT, not a promote): `promotion_gate.evaluate_promotion` with champion=PROJECTED, challenger=CONFIRMED
→ pooled Δ = value of the ACTUAL lineup over the projection. Clears the noise floor + paired-bootstrap-significant ⇒
the real lineup carries info the projection misses (lineups matter; better projection / Part-B Bayesian is a real lever).
Inside the floor ⇒ the projection is AS GOOD AS the real lineup for the model ⇒ CLOSE the projection thread (consistent
with the team-level-dominance lesson: 30.2 / weather-OAA / 33.5).

Runtime: refits 2 arms per season fold (NGBoost) → HAND OFF, ONE --target per invocation.

Usage:
    uv run python betting_ml/scripts/lineup_actual_vs_projected_33_7.py --target home_win
    uv run python betting_ml/scripts/lineup_actual_vs_projected_33_7.py --target run_diff
    uv run python betting_ml/scripts/lineup_actual_vs_projected_33_7.py --target total_runs
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from betting_ml.scripts.pre_lineup_baseline_30_8 import _TARGETS, _cols  # noqa: E402
from betting_ml.scripts.pre_lineup_proj_gate_33_5 import _per_game_scores  # noqa: E402
from betting_ml.utils.cv_splits import all_season_splits  # noqa: E402
from betting_ml.utils.data_loader import load_features  # noqa: E402
from betting_ml.utils.promotion_gate import evaluate_promotion  # noqa: E402

_OUT_DIR = PROJECT_ROOT / "betting_ml" / "evaluation" / "feature_selection" / "lineup_actual_vs_projected_33_7"

# The 1:1 lineup-offense swap STEMS (confirmed `avg_<stem>` ↔ projected `exp_<stem>`).
_ROLL = ["woba_30d", "xwoba_30d", "k_pct_30d", "bb_pct_30d", "hard_hit_pct_30d", "barrel_pct_30d",
         "whiff_rate_30d", "chase_rate_30d",
         "woba_std", "xwoba_std", "k_pct_std", "bb_pct_std", "hard_hit_pct_std", "barrel_pct_std"]
_PLAT = ["woba_vs_lhp", "xwoba_vs_lhp", "k_pct_vs_lhp", "bb_pct_vs_lhp", "hard_hit_pct_vs_lhp",
         "woba_vs_rhp", "xwoba_vs_rhp", "k_pct_vs_rhp", "bb_pct_vs_rhp", "hard_hit_pct_vs_rhp"]


def _merge_expected_lineup(df: pd.DataFrame) -> pd.DataFrame:
    """Source the projected `exp_*` block from the standalone `feature_pregame_expected_lineup`
    table (grain game_pk × home_away) and merge it in as home_/away_-prefixed columns by game_pk.

    Decouples 33.7 from `feature_pregame_game_features`: a scheduled Dagster rebuild running the
    DEPLOYED (pre-33.3) dbt project CREATE-OR-REPLACE's that table without the exp_* columns
    (33.3 Part-b is built locally, not deployed). The source table is a 33.3-only model the
    deployed project never touches, so it survives — read exp_* straight from it."""
    from betting_ml.utils.data_loader import get_snowflake_connection
    src_cols = [f"exp_{s}" for s in _ROLL + _PLAT] + ["exp_lhb_count", "exp_rhb_count"]
    sql = (f"select game_pk, home_away, {', '.join(src_cols)} "
           f"from baseball_data.betting_features.feature_pregame_expected_lineup")
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql)
        el = cur.fetch_pandas_all()
    finally:
        conn.close()
    el.columns = [c.lower() for c in el.columns]
    out = df
    for side in ("home", "away"):
        sub = el[el["home_away"] == side].copy()
        ren = {c: f"{side}_{c}" for c in src_cols}   # exp_woba_30d -> home_exp_woba_30d, etc.
        sub = sub.rename(columns=ren)[["game_pk"] + list(ren.values())]
        out = out.merge(sub, on="game_pk", how="left")
    n_present = sum(c in out.columns for c in _projected_block())
    print(f"  [exp_* merge] sourced from feature_pregame_expected_lineup: {n_present}/52 projected cols merged "
          f"({el['game_pk'].nunique():,} games)")
    return out


def _confirmed_block() -> list[str]:
    out = []
    for side in ("home", "away"):
        out += [f"{side}_avg_{s}" for s in _ROLL + _PLAT]
        out += [f"{side}_lhb_count", f"{side}_rhb_count"]
    return out


def _projected_block() -> list[str]:
    out = []
    for side in ("home", "away"):
        out += [f"{side}_exp_{s}" for s in _ROLL + _PLAT]
        out += [f"{side}_exp_lhb_count", f"{side}_exp_rhb_count"]
    return out


def _run(target: str, df: pd.DataFrame) -> dict:
    cfg = _TARGETS[target]
    floor = [c for c in _cols(cfg["pre"]) if c in df.columns]            # 33.0 Class-A floor
    conf_block = [c for c in _confirmed_block() if c in df.columns]
    proj_block = [c for c in _projected_block() if c in df.columns]
    # floor should hold neither block (avg_* dropped as Class-B; exp_* didn't exist) — dedup defensively.
    confirmed = floor + [c for c in conf_block if c not in floor]
    projected = floor + [c for c in proj_block if c not in floor]
    metric = "brier" if cfg["kind"] == "classification" else "mae"

    print(f"\n=== {target} ({cfg['kind']}) — ISOLATED lineup-offense swap, metric={metric} ===")
    print(f"  floor={len(floor)}  + confirmed avg_* block={len(conf_block)} → confirmed arm={len(confirmed)}")
    print(f"  floor={len(floor)}  + projected exp_* block={len(proj_block)} → projected arm={len(projected)}")

    seasons, s_conf, s_proj, ctx = [], [], [], {}
    for tr, ev in all_season_splits(df, min_train_seasons=3):
        yr = int(df.loc[ev, "game_year"].mode()[0])
        sc_conf = _per_game_scores(df, cfg, confirmed, tr, ev)
        sc_proj = _per_game_scores(df, cfg, projected, tr, ev)
        seasons.append(np.full(len(ev), yr))
        s_conf.append(sc_conf); s_proj.append(sc_proj)
        ctx[yr] = {"confirmed": float(sc_conf.mean()), "projected": float(sc_proj.mean()), "n": int(len(ev))}
        print(f"    {yr} (n={len(ev):4d}): confirmed {sc_conf.mean():.4f}  projected {sc_proj.mean():.4f}  "
              f"Δ(confirmed−projected) {sc_conf.mean()-sc_proj.mean():+.4f}")

    season = np.concatenate(seasons)
    # champion = PROJECTED, challenger = CONFIRMED → pooled Δ = value of the ACTUAL lineup over the projection.
    verdict = evaluate_promotion(season, np.concatenate(s_proj), np.concatenate(s_conf), metric=metric)
    print("\n" + str(verdict))

    actual_matters = verdict.single_eval_pass  # confirmed reliably beats projected beyond the noise floor
    headline = ("ACTUAL LINEUP MATTERS — confirmed beats the projection beyond the noise floor → a better projection "
                "(or Part-B Bayesian uncertainty propagation) is a real lever; KEEP the projection thread."
                if actual_matters else
                "PROJECTION ≈ ACTUAL — the real lineup does NOT beat the projection beyond noise → the projection is as "
                "good as the confirmed lineup for the model → CLOSE the projection thread (33.6 floor is offense-optimal).")
    print(f"\n  >>> 33.7 VERDICT: {headline}")
    if 2026 in ctx:
        c = ctx[2026]
        print(f"  honest-2026: confirmed {c['confirmed']:.4f}  projected {c['projected']:.4f}  "
              f"Δ {c['confirmed']-c['projected']:+.4f}")

    return {"target": target, "metric": metric, "n_floor": len(floor),
            "n_confirmed_arm": len(confirmed), "n_projected_arm": len(projected),
            "n_swap_block": len(conf_block), "per_year": ctx,
            "actual_lineup_matters": actual_matters, "headline": headline,
            "gate": {"decision": verdict.decision, "single_eval_pass": verdict.single_eval_pass,
                     "overall_delta": verdict.overall_delta, "boot_ci": list(verdict.boot_ci),
                     "effect_size_pass": verdict.effect_size_pass, "significant": verdict.significant,
                     "consistency_pass": verdict.consistency_pass, "tolerance": verdict.tolerance,
                     "reasons": verdict.reasons, "per_season": [vars(s) for s in verdict.per_season]}}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", choices=["home_win", "run_diff", "total_runs"], required=True)
    args = ap.parse_args()
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("Loading features from Snowflake...")
    df = load_features().reset_index(drop=True)
    print(f"Loaded {len(df)} rows, seasons {sorted(df['game_year'].dropna().unique().tolist())}")
    df = _merge_expected_lineup(df)   # exp_* from the source table (game_features store may be clobbered)
    res = _run(args.target, df)
    out = _OUT_DIR / f"lineup_actual_vs_projected_{args.target}.json"
    out.write_text(json.dumps(res, indent=2))
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
