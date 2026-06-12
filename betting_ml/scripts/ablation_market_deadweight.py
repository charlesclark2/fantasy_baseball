"""Story 30.4 — market-blind-completion + dead-weight prune ABLATION.

Controlled ablation (same recipe as the 30.1 identifier harness — architecture
held fixed at the tuned champion hyperparameters, ONLY the feature set varies).
Three arms per target:

    champion     = the current *_tuned_2026.json contract (376 feats: 374 base +
                   2 imputation indicators), already 30.1-identifier-scrubbed.
    market_blind = champion minus the 9 leaked market cols (Story 30.4a) — this
                   *completes* market-blindness (the trainers were only
                   consensus-and-moneyline-blind; see _MARKET_LEAK_30_4 below).
    cleaned      = market_blind minus the dead-weight tier (Story 30.4b) — the
                   features whose 2026-OOS permutation importance is ≤0
                   (shuffling them does not hurt), per influence_report.py.

All three are scored on:
  1. Walk-forward temporal CV  (all_season_splits, min_train_seasons=3)
  2. The HONEST 2026 out-of-sample surface (train game_year < 2026, eval == 2026)

Per the Epic 30 operator directive the PRIMARY metric is accuracy-to-truth:
  - run_diff / total_runs : MAE, RMSE, MedAE vs the actual outcome + calib_80.
  - home_win              : Brier, NLL, accuracy, ECE, live corr of P(home win)
                            vs the 0/1 outcome.
Model-vs-market edge is NOT measured here (it is meaningless by construction once
the market cols are removed); the market-blind decision is judged on the ACCURACY
COST of dropping the 9 cols vs the edge-validity GAIN of restoring true blindness.

Two key guards (per the 30.4 spec):
  - The 9 market leaks are isolated in the `market_blind` arm so the dead-weight
    prune is measured on an already-market-blind base (the two effects don't mix).
  - `_PROTECT_FROM_DEADWEIGHT` keeps any mis-served / model-derived feature from
    being mislabeled dead — the umpire z-scores (fixed in 30.5, do NOT treat as
    dead), the imputation indicators, and the sequential posteriors. Overlaps are
    logged, never silently pruned.

Dead-weight source: `…/influence_report/influence_all.json` (run influence_report.py
FIRST — Story 30.4 Task 1). Each target's `all_features[*].tier == "dead"` is the
prune candidate set.

Decision rule (encoded): per target, PROMOTE the `cleaned` contract if neither the
market-blind step nor the dead-weight step regresses the primary CV metric beyond
tolerance (MAE 0.01 / Brier 0.001). The market-blind accuracy cost is reported
explicitly and may be ACCEPTED for the edge-validity gain even at a small regression
(operator call) — that exception is surfaced, not auto-applied.

Runtime: retrains NGBoost / XGBoost per fold for THREE feature sets — minutes, not
seconds. Per project convention, hand off to run with real Snowflake credentials.

Usage:
    uv run python betting_ml/scripts/ablation_market_deadweight.py --target all
    uv run python betting_ml/scripts/ablation_market_deadweight.py --target home_win
    uv run python betting_ml/scripts/ablation_market_deadweight.py --target run_diff --write-exclude
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from betting_ml.scripts.ablation_identifier_features import (  # reuse the exact recipe
    _CV_TOL,
    _TARGETS,
    _eval_one,
    _mean_over_folds,
)
from betting_ml.utils.cv_splits import all_season_splits
from betting_ml.utils.data_loader import load_features

_OUT_DIR = PROJECT_ROOT / "betting_ml" / "evaluation" / "feature_selection" / "market_deadweight"
_INFLUENCE_JSON = (
    PROJECT_ROOT / "betting_ml" / "evaluation" / "feature_selection"
    / "influence_report" / "influence_all.json"
)

# ── Story 30.4a — the 9 market columns that leak into every deployed contract ──
# These were added to the feature store AFTER the trainers' _MARKET_COLS_TO_EXCLUDE
# was authored, so the base models were only "consensus-and-moneyline-blind." Removing
# them completes market-blindness (architecture Principle 3 / §5.6 / §5.7). The first
# 8 are named in the 30.4 spec (+ over_american/under_american confirmed in-contract);
# `total_line_std` (consensus stddev, mart_odds_consensus) is the 9th — a name-collision
# leak (the excluded `totals_line_std` is the plural mart_bookmaker_disagreement col).
_MARKET_LEAK_30_4 = [
    "over_prob_consensus", "under_implied_prob", "total_line_movement",
    "home_ml_money_pct", "over_ticket_pct", "market_bookmaker_count",
    "over_american", "under_american", "total_line_std",
]

# ── Never label these "dead weight" (mis-served / model-derived) ──────────────
# ump_*_zscore: fixed by Story 30.5 (null 34.6%→1.1%) — informative, now served.
# imputation indicators: structural, appended by build_imputation_pipeline.
# sequential posteriors: model-derived; flat 2026 permutation ≠ no live value.
_PROTECT_FROM_DEADWEIGHT_RE = re.compile(
    r"(^ump_.*_zscore$|^has_starter_platoon_data$|^is_new_venue$|sequential_)"
)


def _dead_weight_for(name: str) -> list[str]:
    """Read the tier=='dead' features for this target from influence_all.json."""
    if not _INFLUENCE_JSON.exists():
        raise SystemExit(
            f"\nERROR: {_INFLUENCE_JSON} not found.\n"
            "Story 30.4 Task 1: run the influence report first so dead-weight tiers exist:\n"
            "  uv run python betting_ml/scripts/influence_report.py --target all\n"
        )
    data = json.loads(_INFLUENCE_JSON.read_text())
    if name not in data:
        raise SystemExit(f"ERROR: target '{name}' missing from {_INFLUENCE_JSON}")
    feats = data[name].get("all_features", [])
    return [r["feature"] for r in feats if r.get("tier") == "dead"]


def _arms_for(name: str, df: pd.DataFrame) -> dict:
    """Build the champion / market_blind / cleaned feature lists for a target."""
    cfg = _TARGETS[name]
    contract = json.loads((PROJECT_ROOT / cfg["contract"]).read_text())
    champ_all = contract["feature_cols"]
    # Imputation indicators are re-appended by build_imputation_pipeline, so they are
    # not in raw load_features() — filter to df-present cols (mirrors the 30.1 harness).
    champ = [c for c in champ_all if c in df.columns]

    market_present = [c for c in _MARKET_LEAK_30_4 if c in champ]
    market_blind = [c for c in champ if c not in set(market_present)]

    dead_raw = _dead_weight_for(name)
    # Restrict dead-weight to features still in the market-blind base, minus the
    # protect set (logged), minus any market leak (already handled by the market arm).
    protected_hits = [c for c in dead_raw if _PROTECT_FROM_DEADWEIGHT_RE.search(c)]
    market_in_dead = [c for c in dead_raw if c in set(_MARKET_LEAK_30_4)]
    dead_prune = [
        c for c in dead_raw
        if c in set(market_blind)
        and not _PROTECT_FROM_DEADWEIGHT_RE.search(c)
    ]
    cleaned = [c for c in market_blind if c not in set(dead_prune)]

    return {
        "champion": champ,
        "market_blind": market_blind,
        "cleaned": cleaned,
        "market_present": market_present,
        "market_absent_from_contract": [c for c in _MARKET_LEAK_30_4 if c not in champ],
        "dead_prune": dead_prune,
        "dead_protected_hits": protected_hits,
        "dead_market_overlap": market_in_dead,
    }


def _run_cv_arms(df, cfg, arms: dict[str, list[str]]) -> dict[str, list[dict]]:
    folds = {k: [] for k in arms}
    for train_idx, eval_idx in all_season_splits(df, min_train_seasons=3):
        eval_year = int(df.loc[eval_idx, "game_year"].mode()[0])
        line = [f"    fold {eval_year}:"]
        for arm, cols in arms.items():
            m = _eval_one(df, cfg, cols, train_idx, eval_idx)
            m["eval_year"] = eval_year
            folds[arm].append(m)
            prim = "brier" if cfg["kind"] == "classification" else "mae"
            line.append(f"{arm}={m[prim]:.4f}")
        print("  ".join(line))
    return folds


def _run_target(name: str, df: pd.DataFrame) -> dict:
    cfg = _TARGETS[name]
    arms_def = _arms_for(name, df)
    arms = {k: arms_def[k] for k in ("champion", "market_blind", "cleaned")}

    prim = "brier" if cfg["kind"] == "classification" else "mae"
    metric_keys = (["brier", "nll", "accuracy", "ece", "live_corr", "pred_std"]
                   if cfg["kind"] == "classification"
                   else ["mae", "rmse", "medae", "bias", "pred_std", "calib_80"])

    print(f"\n=== {name} ({cfg['kind']}) ===")
    print(f"  champion feats:     {len(arms['champion'])}")
    print(f"  market leaks dropped ({len(arms_def['market_present'])}): {arms_def['market_present']}")
    if arms_def["market_absent_from_contract"]:
        print(f"    (not in contract, skipped: {arms_def['market_absent_from_contract']})")
    print(f"  market_blind feats: {len(arms['market_blind'])}")
    print(f"  dead-weight pruned ({len(arms_def['dead_prune'])}) → cleaned feats: {len(arms['cleaned'])}")
    if arms_def["dead_protected_hits"]:
        print(f"  ⚠ KEPT (protected from dead-weight prune): {arms_def['dead_protected_hits']}")
    if arms_def["dead_market_overlap"]:
        print(f"  (dead∩market, handled by market arm: {arms_def['dead_market_overlap']})")

    print("  -- walk-forward CV --")
    cv_folds = _run_cv_arms(df, cfg, arms)
    cv = {arm: _mean_over_folds(folds, metric_keys) for arm, folds in cv_folds.items()}

    print("  -- honest 2026 OOS --")
    tr = df.index[df["game_year"] < 2026]
    ev = df.index[df["game_year"] == 2026]
    live = {}
    if len(ev) == 0:
        print("    WARNING: no 2026 rows in load_features() — skipping live surface.")
    else:
        print(f"    train n={len(tr)} (<=2025), eval n={len(ev)} (2026)")
        for arm, cols in arms.items():
            live[arm] = _eval_one(df, cfg, cols, tr, ev)

    # ── Decisions ────────────────────────────────────────────────────────────
    d_market = cv["market_blind"][prim] - cv["champion"][prim]      # >0 = worse
    d_dead = cv["cleaned"][prim] - cv["market_blind"][prim]         # >0 = worse
    d_total = cv["cleaned"][prim] - cv["champion"][prim]
    market_regressed = d_market > _CV_TOL[prim]
    dead_regressed = d_dead > _CV_TOL[prim]

    # Dead-weight prune is a pure hygiene/efficiency move — PROMOTE iff no CV regression.
    # Market-blind completion may be ACCEPTED at a small accuracy cost for edge-validity;
    # flag the cost, do not auto-reject.
    if dead_regressed:
        decision = "KEEP market_blind (dead-weight prune regressed CV — review prune list)"
    elif market_regressed:
        decision = ("PROMOTE cleaned w/ ACCEPTED market-blind accuracy cost "
                    f"(ΔCV {prim} {d_market:+.4f} > tol {_CV_TOL[prim]}) — edge-validity gain")
    else:
        decision = "PROMOTE cleaned (no CV regression — strict hygiene + market-blindness win)"

    result = {
        "target": name, "kind": cfg["kind"], "primary_metric": prim,
        "n_features": {k: len(v) for k, v in arms.items()},
        "market_leaks_dropped": arms_def["market_present"],
        "dead_weight_pruned": arms_def["dead_prune"],
        "dead_weight_protected_kept": arms_def["dead_protected_hits"],
        "cv": {**{f"{arm}": cv[arm] for arm in arms},
               "delta_market_blind": d_market, "delta_dead_weight": d_dead,
               "delta_total": d_total,
               "market_regressed": bool(market_regressed),
               "dead_regressed": bool(dead_regressed),
               "folds": cv_folds},
        "live_2026": live,
        "decision": decision,
    }

    print(f"  CV {prim}: champ={cv['champion'][prim]:.4f}  market_blind={cv['market_blind'][prim]:.4f} "
          f"(Δ{d_market:+.4f})  cleaned={cv['cleaned'][prim]:.4f} (Δdead {d_dead:+.4f})")
    if live:
        if cfg["kind"] == "classification":
            for arm in arms:
                print(f"    LIVE {arm:13s} Brier={live[arm]['brier']:.4f} "
                      f"corr={live[arm]['live_corr']:.4f} acc={live[arm]['accuracy']:.4f}")
        else:
            for arm in arms:
                print(f"    LIVE {arm:13s} MAE={live[arm]['mae']:.4f} "
                      f"RMSE={live[arm]['rmse']:.4f} calib80={live[arm].get('calib_80', float('nan')):.3f}")
    print(f"  → {decision}")
    return result


def _write_exclude_artifact(name: str, result: dict) -> None:
    """Persist the promoted dead-weight prune list so the search trainer can
    regenerate the cleaned contract deterministically (Story 30.4b).

    Written ONLY when the decision PROMOTEs the cleaned contract. The trainer reads
    `betting_ml/models/<target_dir>/dead_weight_exclude.json` via
    feature_hygiene.load_dead_weight_exclude(); the market scrub is handled separately
    by _MARKET_COLS_TO_EXCLUDE, so this file is dead-weight ONLY.
    """
    if not result["decision"].startswith("PROMOTE"):
        print(f"  (decision is not PROMOTE — not writing dead_weight_exclude.json for {name})")
        return
    target_dir = {"home_win": "home_win", "run_diff": "run_differential",
                  "total_runs": "total_runs"}[name]
    out = PROJECT_ROOT / "betting_ml" / "models" / target_dir / "dead_weight_exclude.json"
    out.write_text(json.dumps({
        "target": name,
        "story": "30.4b",
        "source": "ablation_market_deadweight.py",
        "primary_metric": result["primary_metric"],
        "delta_dead_weight_cv": result["cv"]["delta_dead_weight"],
        "features": sorted(result["dead_weight_pruned"]),
        "n": len(result["dead_weight_pruned"]),
    }, indent=2))
    print(f"  wrote dead-weight exclude artifact → {out} ({len(result['dead_weight_pruned'])} cols)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", choices=["home_win", "run_diff", "total_runs", "all"], default="all")
    ap.add_argument("--write-exclude", action="store_true",
                    help="Persist dead_weight_exclude.json for PROMOTE decisions (Story 30.4b "
                         "deterministic regeneration) right after each retrain. Off by default — "
                         "inspect results first, then use --persist-only (no re-run).")
    ap.add_argument("--persist-only", action="store_true",
                    help="Do NOT retrain. Load the saved market_deadweight_*.json and write the "
                         "dead_weight_exclude.json artifacts for PROMOTE targets. Use this AFTER a "
                         "plain run so you don't pay the full ablation cost twice just to persist.")
    args = ap.parse_args()

    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    targets = ["home_win", "run_diff", "total_runs"] if args.target == "all" else [args.target]

    # ── Persist-only: write the exclude artifacts from saved results (no Snowflake, no retrain) ──
    if args.persist_only:
        for name in targets:
            jp = _OUT_DIR / (f"market_deadweight_{name}.json")
            jp_all = _OUT_DIR / "market_deadweight_all.json"
            if jp.exists():
                saved = json.loads(jp.read_text())[name]
            elif jp_all.exists() and name in json.loads(jp_all.read_text()):
                saved = json.loads(jp_all.read_text())[name]
            else:
                print(f"  SKIP {name}: no saved results JSON found — run the ablation first.")
                continue
            _write_exclude_artifact(name, saved)
        return

    print("Loading features from Snowflake...")
    df = load_features().reset_index(drop=True)
    print(f"Loaded {len(df)} rows, seasons: {sorted(df['game_year'].dropna().unique().tolist())}")

    results = {}
    for name in targets:
        results[name] = _run_target(name, df)
        if args.write_exclude:
            _write_exclude_artifact(name, results[name])
        # Per-target sidecar so --persist-only / a later run can reuse a single finished
        # target without re-running the others (user pref: retrain per target, not all).
        (_OUT_DIR / f"market_deadweight_{name}.json").write_text(
            json.dumps({name: results[name]}, indent=2))

    out = _OUT_DIR / ("market_deadweight_all.json" if args.target == "all"
                      else f"market_deadweight_{args.target}.json")
    out.write_text(json.dumps(results, indent=2))
    print(f"\nWrote {out}")
    print("\n=== DECISIONS ===")
    for name, r in results.items():
        print(f"  {name:12s} {r['decision']}")


if __name__ == "__main__":
    main()
