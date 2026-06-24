"""fit_totals_distribution.py — Edge Program Story E2.3 (Convolution → predictive distributions).

Stage 3 of the Per-Side Generative Totals epic (E2). E2.1 built the per-SIDE NegBin marginal;
E2.2 found home/away runs essentially INDEPENDENT (ρ=−0.0035) and pinned the totals variance
deficiency on the **marginal dispersion** (E2.1 fits `r` on optimistic train-fit means →
under-dispersed). This story:

  1. CALIBRATES a single stable per-side NegBin dispersion `r ≈ 3.71` on HELD-OUT residuals,
     leakage-safe (expanding walk-forward window — season T's `r` sees only seasons < T). E2.2's
     dispersion diagnostic showed this `r` is stable across folds (CV 0.054), so a single global
     served `r` is correct — we do NOT condition on period (the apparent train-fit drift is an
     estimation artifact).
  2. CONVOLVES the two marginals INDEPENDENTLY (ρ=0; no copula — E2.2) by drawing N independent
     (home, away) NegBin samples/game, then derives the TOTAL (sum), RUN-DIFF (difference) and
     TEAM TOTALS (marginals).
  3. EMITS a P05…P95 quantile grid + p_over(line) per game and stores PARAMS + GRID (never raw
     samples — §6 cost).
  4. VALIDATES the AC: PIT-flat / calib_80 ≥ 0.80 for the full-game total, and PIT-calibrated
     run-diff + team-total marginals.

LEAKAGE / LEAK-GUARD (verified 2026-06-24): the E2.1 marginals load
feature_pregame_game_features live, and its bullpen channel `bp_eb_xwoba` is sourced from the
E1.7-de-leaked eb_bullpen_team_posteriors (strictly-prior trailing-30d pool, `appearance_date <
game_date`, equal-weight) → no within-game peek. So re-deriving the marginals here is already
leak-clean; the within-game leak E2.1b found was fixed at the dbt layer (E1.7), not deferred.

MARKET-BLIND (architecture Principle 3): the marginal matrix is the E2.1 baseball-only
allow-list, re-verified with `assert_market_blind`. The convolution adds NO features.

This is a >1-min Snowflake + multi-fold LightGBM job — HAND IT TO THE OPERATOR. Outputs:
  * betting_ml/models/sub_models/totals_perside_v1/totals_distribution_v1.json   (served params)
  * ablation_results/e2_3_convolution_calibration.json  +  e2_3_convolution_calibration.md

Usage (operator):
    uv run python betting_ml/scripts/totals_generative/fit_totals_distribution.py
    uv run python betting_ml/scripts/totals_generative/fit_totals_distribution.py --fast   # artifact μ (quick)
    uv run python betting_ml/scripts/totals_generative/fit_totals_distribution.py --no-save
"""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings(
    "ignore", message="X does not have valid feature names", category=UserWarning,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(_PROJECT_ROOT / ".env")

from betting_ml.utils.market_blind import assert_market_blind, find_market_columns
from betting_ml.utils.totals_distribution import (
    CALIB_80_GATE,
    DEFAULT_QUANTILES,
    TotalsDistributionParams,
    calibrate_dispersion_expanding,
    derive_distributions,
    draw_independent_samples,
    fit_negbin_dispersion,
    interval_coverage,
    pit_flatness,
    prob_over,
    quantile_grid,
    randomized_pit,
)
# Reuse the E2.2 OOS-marginal machinery verbatim (re-derives the E2.1 per-side NegBin means
# under the E1.1 purged walk-forward CV from the LIVE, de-leaked feature mart — no saved-artifact
# optimism, no leakage). --fast swaps in the artifact's in-sample μ for quick iteration.
from betting_ml.scripts.totals_generative.fit_copula import (
    collect_artifact_marginals,
    collect_oos_marginals,
    pivot_to_games,
)
from betting_ml.scripts.totals_generative.train_perside_negbin import (
    _MODEL_VERSION,
    build_perside_frame,
    load_wide,
)

_SEED = 42
_N_DRAWS = 10_000              # capped per-game independent draws (§6 cost guard)
# Lines the served contract prices p_over at (a representative ladder; E2.5/E2.7 widen as needed).
_TOTAL_LINES = [float(x) for x in np.arange(6.5, 12.6, 0.5)]
_TEAM_TOTAL_LINES = [float(x) for x in np.arange(2.5, 6.6, 0.5)]
_RUN_DIFF_LINES = [-2.5, -1.5, -0.5, 0.0, 0.5, 1.5, 2.5]   # 0.0 ⇒ distributional P(home wins)

_OUTPUT_DIR = _PROJECT_ROOT / "betting_ml" / "models" / "sub_models" / _MODEL_VERSION
_RESULTS_DIR = (
    _PROJECT_ROOT / "quant_sports_intel_models" / "baseball" / "edge_program" / "ablation_results"
)


# ---------------------------------------------------------------------------
# Calibration validation: PIT + calib_80 for total / run-diff / team-totals
# ---------------------------------------------------------------------------

def validate_calibration(
    g: pd.DataFrame,
    r_home_by_season: dict[int, float],
    r_away_by_season: dict[int, float],
    rng: np.random.Generator,
) -> dict:
    """Leakage-safe calibration check: for each eval season with strictly-prior per-side `r`,
    draw the independent convolution under THAT season's leakage-safe (r_home, r_away), then pool
    the realised PIT / calib_80 across seasons. The earliest season (no prior OOS `r`) is the
    un-gated seed.

    Per-side dispersion (vs a single shared r): the run-diff PIT is sensitive to a home/away
    dispersion asymmetry the sum is blind to (home over-covers at the shared r → it wants a
    larger r). Returns pooled PIT-flatness + calib_80 for total / run_diff / home_total /
    away_total, plus an oracle under the per-side pooled global r (what the served artifact uses)."""
    gated_years = sorted(y for y in g["game_year"].unique() if int(y) in r_home_by_season)
    seed_years = sorted(y for y in g["game_year"].unique() if int(y) not in r_home_by_season)

    # Accumulate per-distribution: PIT draws + interval-hit booleans, pooled across seasons.
    pit_acc: dict[str, list[np.ndarray]] = {k: [] for k in ("total", "run_diff", "home_total", "away_total")}
    hit_acc: dict[str, list[np.ndarray]] = {k: [] for k in ("total", "run_diff", "home_total", "away_total")}
    per_season: list[dict] = []

    for yr in gated_years:
        sub = g[g["game_year"] == yr]
        rh, ra = r_home_by_season[int(yr)], r_away_by_season[int(yr)]
        yh, ya = draw_independent_samples(
            sub["mu_home"].to_numpy(), sub["mu_away"].to_numpy(), rh, rng,
            r_away=ra, n_draws=_N_DRAWS,
        )
        dists = derive_distributions(yh, ya)
        obs = {
            "total": (sub["y_home"] + sub["y_away"]).to_numpy(float),
            "run_diff": (sub["y_home"] - sub["y_away"]).to_numpy(float),
            "home_total": sub["y_home"].to_numpy(float),
            "away_total": sub["y_away"].to_numpy(float),
        }
        row = {"eval_year": int(yr), "n": int(len(sub)), "r_home": round(rh, 4), "r_away": round(ra, 4)}
        for key, samp in dists.items():
            u = randomized_pit(obs[key], samp, rng)
            lo = np.quantile(samp, 0.10, axis=1)
            hi = np.quantile(samp, 0.90, axis=1)
            hit = (obs[key] >= lo) & (obs[key] <= hi)
            pit_acc[key].append(u)
            hit_acc[key].append(hit)
            row[f"calib80_{key}"] = round(float(hit.mean()), 4)
        per_season.append(row)

    pooled: dict[str, dict] = {}
    for key in pit_acc:
        u = np.concatenate(pit_acc[key]) if pit_acc[key] else np.array([])
        hit = np.concatenate(hit_acc[key]) if hit_acc[key] else np.array([])
        flat = pit_flatness(u) if u.size else {"is_flat": False}
        pooled[key] = {
            "calib_80": round(float(hit.mean()), 4) if hit.size else float("nan"),
            "pit": flat,
        }

    # Oracle: per-side pooled global r (the deployable estimate through the latest season) — what
    # the served artifact uses. Reported for context next to the leakage-safe walk-forward gate.
    r_home_global = fit_negbin_dispersion(g["y_home"].to_numpy(float), g["mu_home"].to_numpy(float))
    r_away_global = fit_negbin_dispersion(g["y_away"].to_numpy(float), g["mu_away"].to_numpy(float))
    yh, ya = draw_independent_samples(
        g["mu_home"].to_numpy(), g["mu_away"].to_numpy(), r_home_global, rng,
        r_away=r_away_global, n_draws=_N_DRAWS,
    )
    tot_samp = yh + ya
    tot_obs = (g["y_home"] + g["y_away"]).to_numpy(float)
    oracle = {
        "r_home_global": round(r_home_global, 4),
        "r_away_global": round(r_away_global, 4),
        "calib_80_total": round(interval_coverage(tot_obs, tot_samp), 4),
        "pit_total": pit_flatness(randomized_pit(tot_obs, tot_samp, rng)),
    }

    return {
        "gated_years": [int(y) for y in gated_years],
        "seed_years": [int(y) for y in seed_years],
        "r_home_by_season": {int(k): v for k, v in r_home_by_season.items()},
        "r_away_by_season": {int(k): v for k, v in r_away_by_season.items()},
        "per_season": per_season,
        "pooled": pooled,
        "oracle_global_r": oracle,
    }


def served_example(
    g: pd.DataFrame, r_home: float, r_away: float, rng: np.random.Generator,
) -> dict:
    """A few games' worth of the served contract — params + the P05…P95 quantile grid + p_over
    ladders — so E2.5 (backfill) / E2.7 (UX) consume an exact shape, not a hand-wave. NEVER the
    raw samples (§6)."""
    sub = g.head(3)
    yh, ya = draw_independent_samples(
        sub["mu_home"].to_numpy(), sub["mu_away"].to_numpy(), r_home, rng,
        r_away=r_away, n_draws=_N_DRAWS,
    )
    dists = derive_distributions(yh, ya)
    grids = {k: quantile_grid(v) for k, v in dists.items()}
    p_over_total = prob_over(dists["total"], _TOTAL_LINES)
    p_over_home = prob_over(dists["home_total"], _TEAM_TOTAL_LINES)
    p_over_away = prob_over(dists["away_total"], _TEAM_TOTAL_LINES)
    p_home_win = prob_over(dists["run_diff"], [0.0])[0.0]   # P(run_diff > 0) = P(home wins)
    rows = []
    for i, gp in enumerate(sub["game_pk"].to_numpy()):
        rows.append({
            "game_pk": int(gp),
            "params": {
                "mu_home": round(float(sub["mu_home"].iloc[i]), 4),
                "mu_away": round(float(sub["mu_away"].iloc[i]), 4),
                "dispersion_r_home": round(r_home, 4),
                "dispersion_r_away": round(r_away, 4),
                "rho": 0.0,
            },
            "quantile_levels": list(DEFAULT_QUANTILES),
            "quantile_grid": {k: [round(float(x), 2) for x in grids[k][i]] for k in grids},
            "p_over_total": {str(ln): round(float(p_over_total[ln][i]), 4) for ln in _TOTAL_LINES},
            "p_over_home_total": {str(ln): round(float(p_over_home[ln][i]), 4) for ln in _TEAM_TOTAL_LINES},
            "p_over_away_total": {str(ln): round(float(p_over_away[ln][i]), 4) for ln in _TEAM_TOTAL_LINES},
            "p_home_win_distributional": round(float(p_home_win[i]), 4),
        })
    return {"lines": {"total": _TOTAL_LINES, "team_total": _TEAM_TOTAL_LINES, "run_diff": _RUN_DIFF_LINES},
            "examples": rows}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Story E2.3 — convolution → predictive distributions")
    ap.add_argument("--min-year", type=int, default=2018, help="Earliest season to load (E2.1 default).")
    ap.add_argument("--fast", action="store_true",
                    help="Use the saved E2.1 artifact's in-sample μ (quick) instead of refitting OOS.")
    ap.add_argument("--no-save", action="store_true", help="Skip params/results write.")
    args = ap.parse_args()

    rng = np.random.default_rng(_SEED)

    print("=== STORY E2.3 — CONVOLUTION → PREDICTIVE DISTRIBUTIONS (independent; market-blind) ===")
    print("Loading wide per-game mart from Snowflake ...")
    wide = load_wide(args.min_year)
    print(f"  {len(wide):,} games, seasons {int(wide['game_year'].min())}–{int(wide['game_year'].max())}")

    df, numeric_cols, cat_cols = build_perside_frame(wide)
    # ── CONTRACT-GUARD: the marginal matrix must stay market-blind ──
    assert_market_blind(numeric_cols + cat_cols, context=f"{_MODEL_VERSION} convolution marginal matrix")
    assert not find_market_columns(numeric_cols + cat_cols)
    print(f"  Per-side rows: {len(df):,}  |  CONTRACT-GUARD: market-blind ✅")

    marg = (collect_artifact_marginals if args.fast else collect_oos_marginals)(df, numeric_cols, cat_cols)
    g = pivot_to_games(marg)
    print(f"\n  Games with both sides (eval seasons): {len(g):,}")

    # ── Step 1: leakage-safe PER-SIDE dispersion calibration on held-out residuals ──
    # Per-side (not a single shared r): the run-diff PIT is sensitive to a home/away dispersion
    # asymmetry the sum is blind to (home over-covers at the shared r → wants a larger r).
    seasons_int = g["game_year"].to_numpy(int)
    r_home_by_season = calibrate_dispersion_expanding(seasons_int, g["mu_home"].to_numpy(float), g["y_home"].to_numpy(float))
    r_away_by_season = calibrate_dispersion_expanding(seasons_int, g["mu_away"].to_numpy(float), g["y_away"].to_numpy(float))
    r_train_mean = round(float(g["r_home"].mean()), 3)        # E2.1 train-fit r (the biased one)
    print("\n── Per-side dispersion calibration (leakage-safe expanding window on HELD-OUT residuals) ──")
    print(f"  E2.1 train-fit r (biased high, under-dispersed): {r_train_mean}")
    for yr in sorted(r_home_by_season):
        print(f"  season {yr}: r_home={r_home_by_season[yr]}  r_away={r_away_by_season.get(yr)}  (prior seasons only)")
    rh_vals = np.array(list(r_home_by_season.values()), dtype=float)
    ra_vals = np.array(list(r_away_by_season.values()), dtype=float)
    if rh_vals.size:
        cvh = float(rh_vals.std() / rh_vals.mean()); cva = float(ra_vals.std() / ra_vals.mean())
        print(f"  → r_home mean {rh_vals.mean():.3f} CV {cvh:.3f} | r_away mean {ra_vals.mean():.3f} CV {cva:.3f}  "
              f"({'STABLE → single global per-side r' if max(cvh, cva) < 0.15 else 'drifting'})")

    # ── Steps 2–4: convolve + validate calibration ──
    val = validate_calibration(g, r_home_by_season, r_away_by_season, rng)
    pooled = val["pooled"]
    print("\n── Calibration AC (leakage-safe walk-forward, pooled over gated seasons) ──")
    print(f"  {'distribution':<12} {'calib_80':>9} {'PIT mean':>9} {'maxDecDev':>10} {'PIT flat':>9}")
    for key in ("total", "run_diff", "home_total", "away_total"):
        p = pooled[key]
        print(f"  {key:<12} {p['calib_80']:>9.3f} {p['pit'].get('mean', float('nan')):>9.3f} "
              f"{p['pit'].get('max_decile_dev', float('nan')):>10.4f} "
              f"{'✅' if p['pit'].get('is_flat') else '❌':>9}")
    orc = val["oracle_global_r"]
    print(f"\n  Oracle (per-side global r_home={orc['r_home_global']} r_away={orc['r_away_global']}): "
          f"total calib_80 {orc['calib_80_total']:.3f}, PIT flat {'✅' if orc['pit_total']['is_flat'] else '❌'}")

    # ── Gate ──
    total = pooled["total"]
    calib_ok = (not np.isnan(total["calib_80"])) and total["calib_80"] >= CALIB_80_GATE
    total_flat = bool(total["pit"].get("is_flat"))
    rd_flat = bool(pooled["run_diff"]["pit"].get("is_flat"))
    tt_flat = bool(pooled["home_total"]["pit"].get("is_flat")) and bool(pooled["away_total"]["pit"].get("is_flat"))
    print("\n" + "=" * 72)
    print("E2.3 GATE")
    print("=" * 72)
    print(f"  Full-game total calib_80 ≥ {CALIB_80_GATE:.2f}        : {'✅' if calib_ok else '❌'} ({total['calib_80']:.3f})")
    print(f"  Full-game total PIT histogram flat        : {'✅' if total_flat else '❌'} "
          f"(max decile dev {total['pit'].get('max_decile_dev')})")
    print(f"  Run-diff marginal PIT-calibrated          : {'✅' if rd_flat else '❌'}")
    print(f"  Team-total marginals PIT-calibrated       : {'✅' if tt_flat else '❌'}")
    print(f"  Market-leakage guard passes               : ✅")
    gate_pass = calib_ok and total_flat and rd_flat and tt_flat

    r_home_global, r_away_global = orc["r_home_global"], orc["r_away_global"]
    r_pooled = round((r_home_global + r_away_global) / 2.0, 4)
    if args.no_save:
        print("\n[--no-save] Skipping params + results write.")
        print(f"\nE2.3 GATE: {'PASS ✅' if gate_pass else 'NOT MET ❌ (see calibration record)'}")
        return

    # ── Served params (stable per-side global r — the deployable estimate) ──
    params = TotalsDistributionParams(
        dispersion_r=r_pooled,
        dispersion_r_home=round(r_home_global, 4),
        dispersion_r_away=round(r_away_global, 4),
        rho=0.0,
        n_draws=_N_DRAWS,
        quantile_levels=DEFAULT_QUANTILES,
        notes=(
            f"E2.3 independent convolution (E2.2 ρ≈0). Stable per-side held-out-calibrated "
            f"r_home={r_home_global:.3f} / r_away={r_away_global:.3f} (E2.1 train-fit r={r_train_mean} "
            f"was under-dispersed). Leakage-safe expanding-window calibration confirms r stable across "
            f"seasons → single global per-side r served. Per-side (not shared) calibrates run-diff, "
            f"which is sensitive to the home/away dispersion asymmetry the sum is blind to."
        ),
    )
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    params_path = _OUTPUT_DIR / "totals_distribution_v1.json"
    params_path.write_text(json.dumps(params.to_dict(), indent=2))
    print(f"\nServed params → {params_path.relative_to(_PROJECT_ROOT)}")

    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    results_doc = {
        "story": "E2.3",
        "model_version": _MODEL_VERSION,
        "fit_at": date.today().isoformat(),
        "min_year": args.min_year,
        "marginal_source": "artifact_in_sample" if args.fast else "oos_purged_cv",
        "n_games": int(len(g)),
        "n_draws": _N_DRAWS,
        "rho": 0.0,
        "leak_guard": (
            "bp_eb_xwoba sourced from E1.7-de-leaked eb_bullpen_team_posteriors "
            "(appearance_date < game_date, equal-weight trailing-30d pool); marginals leak-clean."
        ),
        "dispersion": {
            "r_train_fit_e2_1": r_train_mean,
            "r_home_by_season_leakage_safe": {int(k): v for k, v in r_home_by_season.items()},
            "r_away_by_season_leakage_safe": {int(k): v for k, v in r_away_by_season.items()},
            "r_home_global_served": round(r_home_global, 4),
            "r_away_global_served": round(r_away_global, 4),
        },
        "calibration": val,
        "served_contract": served_example(g, r_home_global, r_away_global, rng),
        "gate": {
            "total_calib_80": total["calib_80"],
            "total_calib_80_ok": calib_ok,
            "total_pit_flat": total_flat,
            "run_diff_pit_flat": rd_flat,
            "team_total_pit_flat": tt_flat,
            "market_blind": True,
            "pass": gate_pass,
        },
        "params": params.to_dict(),
    }
    results_path = _RESULTS_DIR / "e2_3_convolution_calibration.json"
    results_path.write_text(json.dumps(results_doc, indent=2))
    print(f"Results → {results_path.relative_to(_PROJECT_ROOT)}")

    _write_decision_md(results_doc)
    print(f"\nE2.3 GATE: {'PASS ✅' if gate_pass else 'NOT MET ❌ (calibration record written)'}")
    print("Next: E2.5 registers totals_generative_v1 + leakage-safe backfill; the served contract "
          "(params + P05…P95 grid + p_over) feeds E2.7 distribution UX. Params NOT promoted to S3 (gated at E2.6).")


def _write_decision_md(doc: dict) -> None:
    d = doc["dispersion"]
    pooled = doc["calibration"]["pooled"]
    orc = doc["calibration"]["oracle_global_r"]
    g = doc["gate"]
    rhbs = d["r_home_by_season_leakage_safe"]
    rabs = d["r_away_by_season_leakage_safe"]
    lines = [
        "# E2.3 — Convolution → predictive distributions: calibration record",
        "",
        f"_Fit {doc['fit_at']} · {doc['n_games']:,} games · marginals = {doc['marginal_source']} · "
        f"{doc['n_draws']:,} draws/game · independent (ρ=0) · per-side dispersion · market-blind._",
        "",
        "## What E2.3 does",
        "- **Convolves the two E2.1 per-side NegBin marginals INDEPENDENTLY** (E2.2: residual ρ=−0.0035 "
        "⇒ home/away runs essentially independent; no copula).",
        "- **Calibrates a stable PER-SIDE dispersion `r_home`/`r_away` on HELD-OUT residuals** — the lever E2.2 "
        "identified for the ~24% totals variance deficiency (E2.1 fits `r` on optimistic train-fit means → "
        "under-dispersed). Per-side (not a single shared r) because the run-diff PIT is sensitive to a "
        "home/away dispersion asymmetry the sum is blind to.",
        "- Derives **total** (sum), **run-diff** (difference; distributional H2H), **team totals** (marginals); "
        "emits a P05…P95 quantile grid + `p_over(line)` and stores **params + grid, not raw samples**.",
        "",
        "## Leak-guard (verified 2026-06-24)",
        f"- {doc['leak_guard']} The within-game leak E2.1b found was fixed at the dbt layer by E1.7 (not "
        "deferred); re-deriving the marginals here reads the de-leaked channel live.",
        "",
        "## Per-side dispersion calibration (leakage-safe expanding window)",
        "",
        "| dispersion source | r_home | r_away |",
        "|---|---|---|",
        f"| E2.1 train-fit (biased high, under-dispersed) | {d['r_train_fit_e2_1']} | {d['r_train_fit_e2_1']} |",
    ]
    for yr in sorted(rhbs):
        lines.append(f"| held-out, seasons < {yr} (leakage-safe) | {rhbs[yr]} | {rabs.get(yr)} |")
    lines += [
        f"| **global served (per-side held-out)** | **{d['r_home_global_served']}** | **{d['r_away_global_served']}** |",
        "",
        "The held-out `r` is stable across seasons (E2.2 CV 0.054) → a **single global per-side served `r`** is "
        "correct; we do NOT condition `r` on period (E2.1's apparent drift is an estimation artifact of "
        "fitting `r` on optimistic train means).",
        "",
        "## Calibration AC (leakage-safe walk-forward, pooled over gated seasons)",
        "",
        "| distribution | calib_80 | PIT mean | max decile dev | PIT flat |",
        "|---|---|---|---|---|",
    ]
    for key in ("total", "run_diff", "home_total", "away_total"):
        p = pooled[key]
        pit = p["pit"]
        lines.append(
            f"| {key} | {p['calib_80']:.3f} | {pit.get('mean')} | {pit.get('max_decile_dev')} | "
            f"{'✅' if pit.get('is_flat') else '❌'} |"
        )
    lines += [
        "",
        f"Oracle (per-side global r_home={orc['r_home_global']}/r_away={orc['r_away_global']}): total "
        f"calib_80 {orc['calib_80_total']:.3f}, PIT flat {'✅' if orc['pit_total']['is_flat'] else '❌'}.",
        "",
        "## Gate",
        f"- Full-game total calib_80 ≥ 0.80: {'✅' if g['total_calib_80_ok'] else '❌'} ({g['total_calib_80']:.3f})",
        f"- Full-game total PIT histogram flat: {'✅' if g['total_pit_flat'] else '❌'}",
        f"- Run-diff marginal PIT-calibrated: {'✅' if g['run_diff_pit_flat'] else '❌'}",
        f"- Team-total marginals PIT-calibrated: {'✅' if g['team_total_pit_flat'] else '❌'}",
        f"- **Overall: {'PASS ✅' if g['pass'] else 'NOT MET ❌'}**",
        "",
        "> The fix for the totals variance deficiency is the **dispersion calibration**, not a copula "
        "(E2.2). The served distribution is honest calibration — NOT an edge claim (the main-line total is "
        "efficient per E13.8; the derivative-edge question is E2.6).",
    ]
    path = _RESULTS_DIR / "e2_3_convolution_calibration.md"
    path.write_text("\n".join(lines) + "\n")
    print(f"Calibration record → {path.relative_to(_PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
