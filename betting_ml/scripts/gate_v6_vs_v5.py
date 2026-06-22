"""gate_v6_vs_v5.py — Edge Program E1.9 step 3: promotion gate, v6 candidate vs v5 champion.

WHY
---
Steps 1-2 picked the learner class (`model_bakeoff.py`) and tuned it (`optuna_hpo.py`). This
runs the CODIFIED promotion gate (`evaluate_promotion`, Case 3) of the v6 candidate — the
tuned winning class on the E1.8 FINAL slim contract — against the deployed v5 champion, BOTH
retrained per fold on the same de-leaked clean matrix under E1.1 purged CV. Output is a
PROMOTE / HOLD verdict with the per-season deltas + paired-bootstrap CI. v6 is NOT promoted
here — it stays a challenger until this gate passes AND the forward/serving-parity check does
(hysteresis ≥2 passes; see promotion_gate). Both arms retrain on the clean matrix so the
comparison isolates v6's class+tuning, not the already-shipped de-leak.

The v6 candidate is read from the `optuna_hpo.py` tuning JSON (`best_params` + `model_class`).
Champion (v5) = the deployed recipe via promotion_gate_eval's champion builders.

Multi-minute (both arms × folds, NGBoost/CatBoost) → operator. `--smoke` for a harness check.

Usage:
    uv run python betting_ml/scripts/gate_v6_vs_v5.py --target total_runs \
        --tuning-json betting_ml/evaluation/tuning_results_v6_ngboost_normal_total_runs_post_lineup.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from betting_ml.scripts.model_bakeoff import (
    _CONTRACTS, _TARGETS as _BO_TARGETS, _assert_market_blind, _contract_cols as _bo_contract_cols,
    load_clean_matrix,
)
from betting_ml.scripts.optuna_hpo import _make_spec
from betting_ml.scripts.promotion_gate_eval import (
    _TARGETS as _PGE_TARGETS, _build_specs, _contract_cols as _pge_contract_cols,
    _reconstruct_champion_cols, make_gate_splitter, walk_forward_gate,
)

_OUT_DIR = PROJECT_ROOT / "betting_ml" / "evaluation" / "feature_selection" / "promotion_gate"


def run_gate(target: str, tier: str, tuning_json: str, *, seed: int, smoke: bool,
             refresh_cache: bool, embargo_days: int) -> dict:
    tune = json.loads((PROJECT_ROOT / tuning_json).read_text())
    model_class = tune["model_class"]
    best_params = tune["best_params"]
    pge = _PGE_TARGETS[target]
    bo = _BO_TARGETS[target]
    kind, metric, tcol = bo["kind"], pge["metric"], pge["target_col"]
    if not smoke and tune.get("overfit_gate") == "FAIL":
        print("⚠️  the v6 tuning config FAILED its PBO/DSR overfit gate — gating anyway for the record, "
              "but DO NOT promote on a passing gate alone until the overfit gate is cleared.")

    df = load_clean_matrix(refresh_cache=refresh_cache, smoke=smoke)

    # v6 challenger: the tuned winning class on the SAME contract the HPO tuned (canonical slim
    # or an E1.9 re-prune variant — read from the tuning JSON so the gate can't drift off it).
    v6_contract = tune.get("contract")
    chal_cols = _bo_contract_cols(target, tier, df, override=v6_contract)
    _assert_market_blind(chal_cols)
    challenger = _make_spec(model_class, kind, best_params, seed=seed)
    variant = tune.get("variant")
    challenger.name = f"v6:{model_class}({tier}{'/' + variant if variant else ''})"

    # Baseline (the "champion" arm):
    #  - post_lineup → the DEPLOYED DENSE v5 (reconstruct for h2h/run_diff, eb for totals). Both
    #    arms are dense → apples-to-apples.
    #  - pre_lineup  → the CURRENT 33.0 MORNING model (champion architecture on the 33.0
    #    pre_lineup contract), NOT the dense v5. The morning tier has a structurally lower ceiling
    #    (sparse point-in-time data); gating morning-v6 vs dense-v5 is the optimistic-ceiling trap.
    #    Both arms are scored on the SAME morning matrix and the bar is "beat what we serve in the
    #    morning today", not "match the dense ceiling".
    champion, _ = _build_specs(target, pge, seed=seed)
    if tier == "pre_lineup":
        champ_cols = _bo_contract_cols(target, "pre_lineup", df)  # the ORIGINAL 33.0 morning contract
        champion.name = f"morning_baseline_33.0:{champion.name}"
        baseline_label = "33.0 morning baseline"
    else:
        champ_cols = (_reconstruct_champion_cols(df) if pge["champion_kind"] == "reconstruct"
                      else _pge_contract_cols(pge["champion_contract"], df))
        baseline_label = "dense v5 champion"

    print(f"\n=== E1.9 GATE  {target} ({kind}, gate-metric={metric}, tier={tier}) ===")
    print(f"  v6 challenger: {len(chal_cols):3d} feats  {challenger.name}")
    print(f"  baseline:      {len(champ_cols):3d} feats  {champion.name}  [{baseline_label}]")
    splitter, sp = make_gate_splitter(True, feature_cols=set(champ_cols) | set(chal_cols),
                                      embargo_days=embargo_days)
    verdict = walk_forward_gate(
        df, tcol, champion=champion, challenger=challenger,
        champion_cols=champ_cols, challenger_cols=chal_cols, metric=metric,
        seed=seed, splitter=splitter)
    print(verdict)

    result = {
        "target": target, "tier": tier, "gate_metric": metric, "model_class": model_class,
        "baseline": baseline_label, "tuning_json": tuning_json, "smoke": smoke,
        "v6_overfit_gate": tune.get("overfit_gate"),
        "n_features": {"v6": len(chal_cols), "baseline": len(champ_cols)},
        "decision": verdict.decision, "overall_delta": verdict.overall_delta,
        "boot_ci": list(verdict.boot_ci), "single_eval_pass": verdict.single_eval_pass,
        "per_season": [vars(s) for s in verdict.per_season], "reasons": verdict.reasons,
    }
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    stem = (f"gate_v6_vs_v5_{target}_{tier}" + (f"_{variant}" if variant else "")
            + ("_smoke" if smoke else ""))
    (_OUT_DIR / f"{stem}.json").write_text(json.dumps(result, indent=2, default=float))
    print(f"\nWrote {_OUT_DIR / f'{stem}.json'}")
    print(f"→ {target}/{tier}: v6 vs {baseline_label} = {verdict.decision}  (Δ={verdict.overall_delta:+.4f}, "
          f"metric={metric}; keep the incumbent until v6 ALSO clears forward/serving-parity + hysteresis)")
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target", choices=list(_PGE_TARGETS), required=True)
    ap.add_argument("--tier", default="post_lineup", choices=list(_CONTRACTS))
    ap.add_argument("--tuning-json", required=True, help="optuna_hpo.py output for the v6 candidate.")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--embargo-days", type=int, default=3)
    ap.add_argument("--refresh-cache", action="store_true")
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args()
    run_gate(args.target, args.tier, args.tuning_json, seed=args.seed, smoke=args.smoke,
             refresh_cache=args.refresh_cache, embargo_days=args.embargo_days)


if __name__ == "__main__":
    main()
