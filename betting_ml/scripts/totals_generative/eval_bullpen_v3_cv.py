"""eval_bullpen_v3_cv.py — Story E2.1b gate: does `bullpen_v3` beat the STATIC team EB?

THE GATE (E2.1b AC)
-------------------
"Beats the STATIC team EB on per-side-runs NLL under E1.1 purged CV." We measure the
bullpen input's marginal contribution to the E2.1 per-side NegBin model by an A/B that
holds EVERYTHING else fixed and swaps only the bullpen channel:

  BASELINE  — `bp_eb_xwoba` = the static `eb_bullpen_team_posteriors` value (outs-weighted;
              the leaky weighting E2.1b replaces).
  V3-LEAKFIX — `bp_eb_xwoba` (+ uncertainty) replaced by the expected-leverage×availability
              weighted `bullpen_v3` value. SAME feature surface ⇒ isolates the leak fix.
  V3-PENSTATE — V3-LEAKFIX + the new v3 channels (platoon L/R + availability diagnostics)
              added as extra features ⇒ measures whether pen-state ADDS over the static EB.

Reported per fold under `PurgedWalkForwardSplit`: per-side NegBin NLL for each variant, the
mean gain (BASELINE − V3), and a `k`-sweep (prior-precision multiplier). Gate PASS ⇔
V3-LEAKFIX mean NLL < BASELINE mean NLL at the chosen `k`.

EFFICIENCY: the heavy work is ONE operator job — `compute_bullpen_v3.py --backfill-season`
writes the per-reliever cache (parquet). This harness aggregates that cache at each sweep-`k`
PURELY in Python (aggregate_team_v3) and only pays the (already-required) E2.1 wide-mart
Snowflake load once. No per-`k` Snowflake round-trips.

HONEST-MDA FOLLOW-UP (required by the E2.1b design decision): after the leak fix, the E1.3
clustered MDA must be re-run with the v3 column swapped in and report whether
`bp_eb_xwoba`'s importance DROPS once the leaky weighting is gone — see
clustered_feature_importance.py and the §E2.1b note. This harness covers the NLL gate; the
MDA re-check is the companion step.

EXPERIMENT B (per-reliever × handedness EB) — NOT built here. Per the design decision it is
a GATED experiment that must beat channel (a) (the team L/R split shipped in V3-PENSTATE) on
held-out per-side NLL; expected to shrink toward (a) given thin per-reliever×handedness
samples. Build only if (a)'s platoon channel proves insufficient here.

Usage (operator; >1-min Snowflake wide-mart load):
    uv run python betting_ml/scripts/totals_generative/eval_bullpen_v3_cv.py \
        --min-year 2018 --k-sweep 0.5 1.0 2.0 4.0
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.utils.data_loader import get_snowflake_connection
from betting_ml.scripts.eb_priors.compute_bullpen_v3 import aggregate_team_v3, _cache_path
from betting_ml.scripts.totals_generative.train_perside_negbin import (
    OPP_PITCH_BASES,
    build_perside_frame,
    load_wide,
    run_cv,
)

_RESULTS_DIR = _PROJECT_ROOT / "quant_sports_intel_models" / "baseball" / "edge_program" / "ablation_results"

# The v3 channels added in the PENSTATE variant (appended to OPP_PITCH_BASES = the faced pen).
_V3_PENSTATE_BASES = [
    "bp_eb_xwoba_vs_lhb_v3", "bp_eb_xwoba_vs_rhb_v3",
    "pen_available_arms", "pen_projected_unavailable_arms",
    "pen_effective_size", "pen_avg_rest_days",
]


def _load_team_sides(min_year: int) -> pd.DataFrame:
    """(game_pk, home_team, away_team) from mart_game_results — the final feature mart does
    not expose team abbreviations, so the per-side v3 join needs them separately."""
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            select game_pk::varchar as game_pk, home_team, away_team
            from baseball_data.betting.mart_game_results
            where game_type = 'R' and game_year >= %(min_year)s
            """,
            {"min_year": int(min_year)},
        )
        cols = [d[0].lower() for d in cur.description]
        df = pd.DataFrame(cur.fetchall(), columns=cols)
    finally:
        conn.close()
    df["game_pk"] = df["game_pk"].astype(str)
    return df


def _load_v3_team(seasons: list[int], shrinkage_k: float, weight_mode: str = "expected") -> pd.DataFrame:
    """Aggregate the per-reliever cache(s) to (game_pk, team) at the given k (pure Python).

    weight_mode='equal' yields the DE-LEAKED CONTROL (leakage-safe roster + EBs, plain average)
    — the apples-to-apples comparison against the leaky incumbent that isolates the leak.
    """
    frames = []
    for s in seasons:
        p = _cache_path(s)
        if not p.exists():
            print(f"  [warn] no per-reliever cache for season {s} ({p.name}); "
                  f"run compute_bullpen_v3.py --backfill-season {s} first.")
            continue
        frames.append(pd.read_parquet(p))
    if not frames:
        raise FileNotFoundError("No per-reliever caches found — run compute_bullpen_v3 backfills first.")
    cache = pd.concat(frames, ignore_index=True)
    team = aggregate_team_v3(cache, shrinkage_k=shrinkage_k, weight_mode=weight_mode)
    team["game_pk"] = team["game_pk"].astype(str)
    return team


def _attach_v3(wide: pd.DataFrame, team_v3: pd.DataFrame, *, penstate: bool) -> pd.DataFrame:
    """Return a copy of the wide per-game mart with the bullpen channel swapped to v3.

    home_*/away_* are filled by joining team_v3 on (game_pk, home_team)/(game_pk, away_team).
    Always overwrites `*_bp_eb_xwoba` / `*_bp_eb_uncertainty` (the leak-fix swap). When
    `penstate`, also lands the new v3 channels as `*_bp_eb_xwoba_vs_lhb_v3` etc.
    """
    w = wide.copy()
    w.columns = [c.lower() for c in w.columns]
    w["game_pk"] = w["game_pk"].astype(str)
    v = team_v3.set_index(["game_pk", "team"])

    def _map(side_team_col: str, value_col: str) -> pd.Series:
        idx = list(zip(w["game_pk"], w[side_team_col].astype(str)))
        return pd.Series(v[value_col].reindex(idx).to_numpy(), index=w.index)

    for side in ("home", "away"):
        team_col = f"{side}_team"
        if team_col not in w.columns:
            raise KeyError(f"wide mart missing {team_col}; cannot attach v3 by team side.")
        # Leak-fix swap (same column slot the static model used). Keep the STATIC value where
        # v3 is absent (no pool / sparse) so the A/B differs only where v3 actually exists —
        # otherwise missing-v3 games would impute to the train mean and unfairly penalise v3.
        for dst, src_col in (("bp_eb_xwoba", "team_eb_bullpen_xwoba_v3"),
                             ("bp_eb_uncertainty", "team_eb_bullpen_uncertainty_v3")):
            col = f"{side}_{dst}"
            new = _map(team_col, src_col)
            w[col] = new.where(new.notna(), w[col]) if col in w.columns else new
        if penstate:
            w[f"{side}_bp_eb_xwoba_vs_lhb_v3"] = _map(team_col, "team_eb_bullpen_xwoba_vs_lhb_v3")
            w[f"{side}_bp_eb_xwoba_vs_rhb_v3"] = _map(team_col, "team_eb_bullpen_xwoba_vs_rhb_v3")
            w[f"{side}_pen_available_arms"] = _map(team_col, "pen_available_arms")
            w[f"{side}_pen_projected_unavailable_arms"] = _map(team_col, "pen_projected_unavailable_arms")
            w[f"{side}_pen_effective_size"] = _map(team_col, "pen_effective_size")
            w[f"{side}_pen_avg_rest_days"] = _map(team_col, "pen_avg_rest_days")
    return w


def _cv_mean_nll(wide: pd.DataFrame, extra_opp_bases: list[str] | None = None) -> dict:
    """Build the per-side frame and return E2.1 purged-CV results (mean per-side NegBin NLL)."""
    if extra_opp_bases:
        # Temporarily extend the opposing-pen base list so build_perside_frame picks up v3 channels.
        added = [b for b in extra_opp_bases if b not in OPP_PITCH_BASES]
        OPP_PITCH_BASES.extend(added)
        try:
            df, num, cat = build_perside_frame(wide)
            return run_cv(df, num, cat)
        finally:
            for b in added:
                OPP_PITCH_BASES.remove(b)
    df, num, cat = build_perside_frame(wide)
    return run_cv(df, num, cat)


def main() -> None:
    ap = argparse.ArgumentParser(description="E2.1b gate — bullpen_v3 vs static team EB (per-side NLL)")
    ap.add_argument("--min-year", type=int, default=2018)
    ap.add_argument("--k-sweep", type=float, nargs="+", default=[0.5, 1.0, 2.0, 4.0],
                    help="Shrinkage-k grid for the per-reliever EB prior precision.")
    ap.add_argument("--no-save", action="store_true")
    args = ap.parse_args()

    print("=== STORY E2.1b GATE — bullpen_v3 vs STATIC team EB (per-side-runs NLL, purged CV) ===")
    print("Loading wide per-game mart (E2.1 surface) from Snowflake ...")
    wide = load_wide(args.min_year)
    wide.columns = [c.lower() for c in wide.columns]
    wide["game_pk"] = wide["game_pk"].astype(str)
    seasons = sorted({int(y) for y in pd.to_numeric(wide["game_year"]).dropna().unique()})
    print(f"  {len(wide):,} games, seasons {seasons[0]}–{seasons[-1]}")

    # The final feature mart lacks team abbreviations; join them for the per-side v3 attach.
    if "home_team" not in wide.columns or "away_team" not in wide.columns:
        sides = _load_team_sides(args.min_year)
        wide = wide.merge(sides, on="game_pk", how="left")
        print(f"  joined team sides ({wide['home_team'].notna().sum():,}/{len(wide):,} matched)")

    # ── BASELINE: static eb_bullpen_team_posteriors (the leaky-weight champion) ──
    # NOTE: this incumbent feature weights per-reliever EB by outs_in_game over the roster of
    # arms that ACTUALLY pitched the eval game (eb_bullpen_team_posteriors.sql) → a WITHIN-GAME
    # peek that purged CV cannot catch. So its NLL is inflated by outcome information v3 lacks.
    print("\n── BASELINE (static team EB — leaky outs-weight, within-game peek) ──")
    base = _cv_mean_nll(wide)
    base_nll = base["mean_negbin_nll"]

    # ── DE-LEAKED CONTROL: same leakage-safe roster+EBs as v3, equal-weight (no leverage/avail) ──
    # The apples-to-apples test: if this ≈ V3-LEAKFIX but both > leaky-static, the static gap is
    # the leak (roster/outs peek), NOT v3 being worse.
    print("\n── DE-LEAKED CONTROL (equal-weight, leakage-safe roster) ──")
    team_equal = _load_v3_team(seasons, shrinkage_k=1.0, weight_mode="equal")
    wide_equal = _attach_v3(wide, team_equal, penstate=False)
    equal_res = _cv_mean_nll(wide_equal)
    equal_nll = equal_res["mean_negbin_nll"]
    print(f"  DE-LEAKED equal-weight: mean NLL {equal_nll:.4f}  (leaky-static {base_nll:.4f})")

    # ── k-sweep: V3-LEAKFIX (swap only the bullpen quality channel) ──
    sweep: list[dict] = []
    for k in args.k_sweep:
        print(f"\n── V3-LEAKFIX  (k={k}) ──")
        team_v3 = _load_v3_team(seasons, shrinkage_k=k)
        wide_v3 = _attach_v3(wide, team_v3, penstate=False)
        res = _cv_mean_nll(wide_v3)
        sweep.append({"k": k, "mean_negbin_nll": res["mean_negbin_nll"],
                      "gain_vs_static": round(base_nll - res["mean_negbin_nll"], 4),
                      "folds": res["folds"]})
        print(f"  V3-LEAKFIX k={k}: mean NLL {res['mean_negbin_nll']:.4f}  "
              f"(static {base_nll:.4f}, gain {base_nll - res['mean_negbin_nll']:+.4f})")

    best = min(sweep, key=lambda s: s["mean_negbin_nll"])
    best_k = best["k"]

    # ── V3-PENSTATE at best k: add platoon + availability channels ──
    print(f"\n── V3-PENSTATE (best k={best_k}; + platoon + availability) ──")
    team_best = _load_v3_team(seasons, shrinkage_k=best_k)
    wide_pen = _attach_v3(wide, team_best, penstate=True)
    pen = _cv_mean_nll(wide_pen, extra_opp_bases=_V3_PENSTATE_BASES)
    pen_nll = pen["mean_negbin_nll"]

    # ── Gate verdict ──
    leakfix_pass = best["mean_negbin_nll"] < base_nll
    penstate_adds = pen_nll < best["mean_negbin_nll"]
    # Leak signature: the leaky-static beats BOTH leakage-safe variants (equal + v3) by a
    # similar margin ⇒ its edge is the within-game peek, not real pre-game skill.
    static_minus_equal = equal_nll - base_nll
    static_minus_v3 = best["mean_negbin_nll"] - base_nll
    leak_signature = (equal_nll > base_nll) and (best["mean_negbin_nll"] > base_nll) and \
                     (abs(static_minus_equal - static_minus_v3) < 0.01)
    print("\n" + "=" * 72)
    print("E2.1b GATE — bullpen_v3 vs STATIC team EB  (lower per-side NegBin NLL = better)")
    print("=" * 72)
    print(f"  LEAKY-STATIC (incumbent; outs/roster peek eval game) : {base_nll:.4f}")
    print(f"  DE-LEAKED equal-weight (leakage-safe control)        : {equal_nll:.4f}  "
          f"vs leaky {static_minus_equal:+.4f}")
    print(f"  V3-LEAKFIX best (k={best_k:<4})                          : {best['mean_negbin_nll']:.4f}  "
          f"vs leaky {static_minus_v3:+.4f}  {'✅' if leakfix_pass else '❌'}")
    print(f"  V3-PENSTATE (+platoon/availability)                  : {pen_nll:.4f}  "
          f"add {best['mean_negbin_nll'] - pen_nll:+.4f}  {'✅ adds' if penstate_adds else '— no add'}")
    print(f"\n  GATE (beat static team EB on per-side NLL)           : {'PASS ✅' if leakfix_pass else 'FAIL ❌'}")
    if not leakfix_pass and leak_signature:
        print("  ⚠️  LEAK SIGNATURE: the leaky-static beats BOTH leakage-safe variants (equal AND v3)")
        print("      by a near-identical margin ⇒ its NLL edge is the WITHIN-GAME PEEK, not pre-game")
        print("      skill. The NLL gate as specified rewards the leak; it cannot fairly rank a clean")
        print("      feature against a contaminated incumbent. v3 is the leakage-safe replacement;")
        print("      the actionable finding is that the #1 feature must be DE-LEAKED.")
    print("  Honest framing: a measured-lift check on the proven-dominant signal — not a presumed edge.")
    print("  NEXT: re-run E1.3 clustered MDA with the v3 column swapped in and report whether")
    print("        bp_eb_xwoba importance DROPS once the leaky weighting is gone (required follow-up).")

    if args.no_save:
        return
    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = {
        "story": "E2.1b",
        "evaluated_at": date.today().isoformat(),
        "min_year": args.min_year,
        "leaky_static_mean_negbin_nll": base_nll,
        "deleaked_equal_weight_nll": equal_nll,
        "k_sweep": sweep,
        "best_k": best_k,
        "v3_leakfix_best_nll": best["mean_negbin_nll"],
        "v3_penstate_nll": pen_nll,
        "static_minus_equal": round(static_minus_equal, 4),
        "static_minus_v3": round(static_minus_v3, 4),
        "gate": {
            "v3_beats_static": leakfix_pass,
            "penstate_adds_over_leakfix": penstate_adds,
            "leak_signature_detected": bool(leak_signature),
        },
    }
    path = _RESULTS_DIR / "e2_1b_bullpen_v3_cv.json"
    path.write_text(json.dumps(out, indent=2))
    print(f"\nResults → {path.relative_to(_PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
