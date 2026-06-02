"""
fit_matchup_cell_priors.py — Phase 1 EB matchup cell prior estimation (Epic 8.0)

Computes grand_mean, batter_effect[b], pitcher_effect[p], and σ_interaction from
the 2016–2020 pre-training window using end-of-season soft-weighted snapshots from
mart_batter_archetype_vs_pitcher_cluster. Applies hierarchical shrinkage to all
25 (batter × pitcher) interaction terms and writes results to:
    betting_ml/models/eb_priors/matchup_cell_priors.json

Model: μ_cell(b, p) = grand_mean + batter_effect[b] + pitcher_effect[p] + shrunk_interaction[b, p]
Shrinkage: raw_interaction × n_cell / (n_cell + σ²_noise / σ²_interaction)

Usage:
    uv run python betting_ml/scripts/eb_priors/fit_matchup_cell_priors.py
    uv run python betting_ml/scripts/eb_priors/fit_matchup_cell_priors.py --min-season 2016 --max-season 2020
    uv run python betting_ml/scripts/eb_priors/fit_matchup_cell_priors.py --sigma-noise 0.43
    uv run python betting_ml/scripts/eb_priors/fit_matchup_cell_priors.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.utils.data_loader import get_snowflake_connection

_OUTPUT_PATH = _PROJECT_ROOT / "betting_ml" / "models" / "eb_priors" / "matchup_cell_priors.json"

_SKEW_KURTOSIS_FLAG_THRESHOLD = 1.0
_MARGINALS_ONLY_THRESHOLD = 50.0
_SIGMA_FIT_MIN_PA = 200.0

_CALIBRATION_SQL = """
SELECT
    batter_cluster_label,
    pitcher_cluster_label,
    YEAR(game_date)   AS season,
    game_date,
    pa_weight,
    raw_xwoba
FROM baseball_data.betting.mart_batter_archetype_vs_pitcher_cluster
WHERE YEAR(game_date) BETWEEN %(min_season)s AND %(max_season)s
  AND raw_xwoba IS NOT NULL
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY batter_cluster_label, pitcher_cluster_label, YEAR(game_date)
    ORDER BY game_date DESC
) = 1
ORDER BY batter_cluster_label, pitcher_cluster_label, season
"""


def _load_data(conn, min_season: int, max_season: int) -> list[dict]:
    cur = conn.cursor()
    cur.execute(_CALIBRATION_SQL, {"min_season": min_season, "max_season": max_season})
    cols = [d[0].lower() for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    cur.close()
    return rows


def _weighted_mean(values: list[float], weights: list[float]) -> float:
    total_w = sum(weights)
    if total_w == 0:
        return float("nan")
    return sum(v * w for v, w in zip(values, weights)) / total_w


def _compute_priors(
    rows: list[dict],
    sigma_noise: float,
) -> dict:
    """
    Core EB estimation. Returns the full prior dict ready for JSON serialisation.
    """
    # ── Aggregate end-of-season snapshots per cell ─────────────────────────────
    from collections import defaultdict

    cell_pa: dict[tuple, float] = defaultdict(float)
    cell_woba_num: dict[tuple, float] = defaultdict(float)
    cell_seasons: dict[tuple, list] = defaultdict(list)

    for r in rows:
        key = (r["batter_cluster_label"], r["pitcher_cluster_label"])
        w = float(r["pa_weight"])
        xw = float(r["raw_xwoba"])
        cell_pa[key] += w
        cell_woba_num[key] += xw * w
        cell_seasons[key].append(xw)

    cells_list = sorted(cell_pa.keys())
    cell_mean = {k: cell_woba_num[k] / cell_pa[k] for k in cells_list}

    # ── Grand mean (PA-weight-weighted average across all cells) ───────────────
    all_pa = [cell_pa[k] for k in cells_list]
    all_means = [cell_mean[k] for k in cells_list]
    grand_mean = _weighted_mean(all_means, all_pa)

    # ── Batter marginal effects ────────────────────────────────────────────────
    batter_archetypes = sorted({k[0] for k in cells_list})
    pitcher_archetypes = sorted({k[1] for k in cells_list})

    batter_effect: dict[str, float] = {}
    for b in batter_archetypes:
        b_means = [cell_mean[(b, p)] for p in pitcher_archetypes if (b, p) in cell_mean]
        b_weights = [cell_pa[(b, p)] for p in pitcher_archetypes if (b, p) in cell_mean]
        batter_effect[b] = _weighted_mean(b_means, b_weights) - grand_mean

    # ── Pitcher marginal effects ───────────────────────────────────────────────
    pitcher_effect: dict[str, float] = {}
    for p in pitcher_archetypes:
        p_means = [cell_mean[(b, p)] for b in batter_archetypes if (b, p) in cell_mean]
        p_weights = [cell_pa[(b, p)] for b in batter_archetypes if (b, p) in cell_mean]
        pitcher_effect[p] = _weighted_mean(p_means, p_weights) - grand_mean

    # ── Raw interaction residuals ──────────────────────────────────────────────
    raw_interaction: dict[tuple, float] = {}
    for k in cells_list:
        b, p = k
        raw_interaction[k] = (
            cell_mean[k] - grand_mean - batter_effect[b] - pitcher_effect[p]
        )

    # ── Estimate σ_interaction from cells with sufficient PA ──────────────────
    eligible = [k for k in cells_list if cell_pa[k] >= _SIGMA_FIT_MIN_PA]
    if len(eligible) < 3:
        print(
            f"WARNING: only {len(eligible)} cells have pa_weight ≥ {_SIGMA_FIT_MIN_PA}; "
            "σ_interaction estimate may be unreliable"
        )
    eligible_residuals = [raw_interaction[k] for k in eligible]
    sigma_interaction = float(np.std(eligible_residuals)) if eligible_residuals else 0.01

    # ── Residual distribution validation ──────────────────────────────────────
    try:
        from scipy import stats as scipy_stats

        skewness = float(scipy_stats.skew(eligible_residuals)) if len(eligible_residuals) >= 3 else 0.0
        kurtosis = float(scipy_stats.kurtosis(eligible_residuals)) if len(eligible_residuals) >= 3 else 0.0
    except ImportError:
        skewness = float(_skew_fallback(eligible_residuals))
        kurtosis = 0.0

    if abs(skewness) > _SKEW_KURTOSIS_FLAG_THRESHOLD:
        print(f"FLAG: residual skewness = {skewness:.3f} exceeds {_SKEW_KURTOSIS_FLAG_THRESHOLD} — "
              "Normal prior family may not be appropriate")
    if abs(kurtosis) > _SKEW_KURTOSIS_FLAG_THRESHOLD:
        print(f"FLAG: residual excess kurtosis = {kurtosis:.3f} exceeds {_SKEW_KURTOSIS_FLAG_THRESHOLD} — "
              "consider heavier-tailed prior in Phase 2")

    # ── Shrinkage formula ──────────────────────────────────────────────────────
    sigma2_noise = sigma_noise ** 2
    sigma2_interaction = sigma_interaction ** 2
    k_ratio = sigma2_noise / sigma2_interaction if sigma2_interaction > 0 else float("inf")

    cell_output: dict[str, dict] = {}
    for cell_key in cells_list:
        b, p = cell_key
        n_cell = cell_pa[cell_key]
        shrink_factor = n_cell / (n_cell + k_ratio) if k_ratio < float("inf") else 1.0
        shrunk = raw_interaction[cell_key] * shrink_factor
        mu_cell = grand_mean + batter_effect[b] + pitcher_effect[p] + shrunk
        data_source = "full_eb" if n_cell >= _MARGINALS_ONLY_THRESHOLD else "marginals_only"

        cell_output[f"{b}__{p}"] = {
            "batter_archetype": b,
            "pitcher_archetype": p,
            "cell_mean_xwoba": round(cell_mean[cell_key], 6),
            "raw_interaction": round(raw_interaction[cell_key], 6),
            "shrunk_interaction": round(shrunk, 6),
            "mu_cell": round(mu_cell, 6),
            "cell_n_pa": round(n_cell, 2),
            "cell_shrinkage_factor": round(shrink_factor, 6),
            "cell_data_source": data_source,
        }

    return {
        "metadata": {
            "fit_date": date.today().isoformat(),
            "calibration_window": [int(min(r["season"] for r in rows)),
                                   int(max(r["season"] for r in rows))],
            "n_batter_archetypes": len(batter_archetypes),
            "n_pitcher_archetypes": len(pitcher_archetypes),
            "n_cells": len(cells_list),
            "sigma_noise": sigma_noise,
            "sigma_noise_squared": round(sigma2_noise, 6),
        },
        "global": {
            "grand_mean_xwoba": round(grand_mean, 6),
            "sigma_interaction": round(sigma_interaction, 6),
            "sigma_interaction_squared": round(sigma2_interaction, 6),
            "k_ratio": round(k_ratio, 4),
            "residual_skewness": round(skewness, 4),
            "residual_kurtosis": round(kurtosis, 4),
            "n_cells_used_for_sigma_fit": len(eligible),
        },
        "batter_effects": {b: round(v, 6) for b, v in sorted(batter_effect.items())},
        "pitcher_effects": {p: round(v, 6) for p, v in sorted(pitcher_effect.items())},
        "cells": cell_output,
    }


def _skew_fallback(values: list[float]) -> float:
    if len(values) < 3:
        return 0.0
    arr = np.array(values)
    mean = arr.mean()
    std = arr.std()
    if std == 0:
        return 0.0
    return float(np.mean(((arr - mean) / std) ** 3))


def _print_ac_report(result: dict) -> None:
    print("\n── Acceptance Criteria ──────────────────────────────────────────────────────")

    cells = result["cells"]
    grand_mean = result["global"]["grand_mean_xwoba"]
    skewness = result["global"]["residual_skewness"]
    kurtosis = result["global"]["residual_kurtosis"]

    # AC1: shrinkage factors are valid and monotone increasing with cell PA
    # The 50%-shrinkage crossover occurs at n_cell = k_ratio = σ²_noise / σ²_interaction.
    # If k_ratio >> typical n_cell, interactions are genuinely small and heavy shrinkage
    # toward the additive model is the correct Bayesian answer.
    k_ratio = result["global"]["k_ratio"]
    crossover_pa = k_ratio  # n_cell where shrinkage_factor = 0.50
    all_sfs = [(v["cell_n_pa"], v["cell_shrinkage_factor"], k) for k, v in cells.items()]
    all_sfs_sorted = sorted(all_sfs)
    sf_valid = all(0 < sf < 1 for _, sf, _ in all_sfs_sorted)
    sf_monotone = all(
        all_sfs_sorted[i][1] <= all_sfs_sorted[i + 1][1]
        for i in range(len(all_sfs_sorted) - 1)
    )
    ac1_pass = sf_valid and sf_monotone
    min_sf = min(sf for _, sf, _ in all_sfs_sorted)
    max_sf = max(sf for _, sf, _ in all_sfs_sorted)
    print(f"AC1 (shrinkage valid 0<s<1, monotone with PA): {'PASS ✓' if ac1_pass else 'FAIL ✗'}")
    print(f"     shrinkage range: [{min_sf:.4f}, {max_sf:.4f}]  k_ratio={k_ratio:.0f}")
    print(f"     50%-crossover at n_cell={crossover_pa:.0f} PA (heavy prior dominance expected if cells below this)")

    # AC: cells < 100 PA → shrinkage_factor < 0.40
    low_pa = {k: v for k, v in cells.items() if v["cell_n_pa"] < 100}
    ac2_pass = all(v["cell_shrinkage_factor"] < 0.40 for v in low_pa.values()) if low_pa else True
    print(f"AC2 (<100 PA → shrinkage < 0.40):  {'PASS ✓' if ac2_pass else 'FAIL ✗'} "
          f"({'vacuous — no sparse cells' if not low_pa else f'{len(low_pa)} cells evaluated'})")

    # AC: grand_mean within 0.005 of the typical xwOBA range (verified against query)
    print(f"AC4 (grand_mean ≈ league xwOBA):    grand_mean = {grand_mean:.4f}")
    print(f"     (verify within 0.005 of league-wide observed xwOBA for 2016–2020)")

    # AC: known favorable matchup shows positive interaction
    favorable = cells.get("power_pull__soft_command") or cells.get("power_pull__contact_sinker_ball")
    if favorable:
        sign_ok = favorable["shrunk_interaction"] > 0
        label = "power_pull__soft_command" if "power_pull__soft_command" in cells else "power_pull__contact_sinker_ball"
        print(f"AC3 (power_pull vs finesse pitcher → positive interaction): "
              f"{'PASS ✓' if sign_ok else 'FAIL ✗'}")
        print(f"     {label}: shrunk_interaction = {favorable['shrunk_interaction']:.4f}")
    else:
        print("AC3: could not locate expected cell — check batter/pitcher archetype labels")

    # Skewness / kurtosis flags
    print(f"\nResidual distribution: skewness={skewness:.3f}  kurtosis={kurtosis:.3f} "
          f"({'OK' if abs(skewness) <= 1.0 and abs(kurtosis) <= 1.0 else 'FLAG — see output above'})")

    # Print interaction matrix
    print("\n── Interaction matrix (shrunk, xwOBA relative to additive prediction) ───────")
    b_archs = sorted({v["batter_archetype"] for v in cells.values()})
    p_archs = sorted({v["pitcher_archetype"] for v in cells.values()})
    header = f"{'':22s}" + "".join(f"{p[:14]:>16s}" for p in p_archs)
    print(header)
    for b in b_archs:
        row = f"{b:<22s}"
        for p in p_archs:
            key = f"{b}__{p}"
            val = cells[key]["shrunk_interaction"] if key in cells else float("nan")
            row += f"{val:+.4f}        "
        print(row)

    # Print batter/pitcher effects
    print("\n── Batter effects ──────────────────────────────────────────────────────────")
    for b, e in sorted(result["batter_effects"].items()):
        print(f"  {b:<25s} {e:+.4f}")

    print("\n── Pitcher effects ─────────────────────────────────────────────────────────")
    for p, e in sorted(result["pitcher_effects"].items()):
        print(f"  {p:<25s} {e:+.4f}")

    print(f"\n── Global ───────────────────────────────────────────────────────────────────")
    g = result["global"]
    print(f"  grand_mean_xwoba   = {g['grand_mean_xwoba']:.4f}")
    print(f"  sigma_interaction  = {g['sigma_interaction']:.4f}")
    print(f"  k_ratio (σ²n/σ²i) = {g['k_ratio']:.1f}")
    print(f"  cells used for σ   = {g['n_cells_used_for_sigma_fit']}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fit matchup cell EB priors (Epic 8.0)"
    )
    parser.add_argument("--min-season", type=int, default=2016)
    parser.add_argument("--max-season", type=int, default=2020)
    parser.add_argument("--sigma-noise", type=float, default=0.43,
                        help="Per-PA xwOBA standard deviation (default 0.43)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Compute and print but do not write JSON")
    args = parser.parse_args()

    print(f"Loading calibration data ({args.min_season}–{args.max_season})...")
    conn = get_snowflake_connection()
    try:
        rows = _load_data(conn, args.min_season, args.max_season)
    finally:
        conn.close()

    if not rows:
        print("ERROR: no rows returned. Has mart_batter_archetype_vs_pitcher_cluster "
              "been rebuilt with game_year >= 2016? See implementation guide 8.0.")
        sys.exit(1)

    seasons = sorted({r["season"] for r in rows})
    cells_found = len({(r["batter_cluster_label"], r["pitcher_cluster_label"]) for r in rows})
    print(f"  {len(rows)} season-end snapshots loaded across {len(seasons)} seasons: {seasons}")
    print(f"  {cells_found} distinct cells")

    print(f"\nFitting EB priors (σ_noise={args.sigma_noise})...")
    result = _compute_priors(rows, sigma_noise=args.sigma_noise)

    _print_ac_report(result)

    if args.dry_run:
        print(f"\n[dry-run] Would write to {_OUTPUT_PATH}. No file written.")
    else:
        _OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        _OUTPUT_PATH.write_text(json.dumps(result, indent=2))
        print(f"\nWrote {_OUTPUT_PATH}")


if __name__ == "__main__":
    main()
