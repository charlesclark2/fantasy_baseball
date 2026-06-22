"""reprune.py — Edge Program E1.9: winner-conditioned re-prune in one command.

Chains the three steps so the operator doesn't hand-copy the long auto-generated MDA filename:
  1. clustered-MDA on the de-leaked matrix with the bake-off WINNER as the importance scorer
     (--scorer), optionally on an explicit feature set (--input-contract, e.g. a morning
     contract that was never clustered-MDA-pruned),
  2. derive the slim contract reproducibly (E1.3 non-noise rule) to --out-path,
  3. re-run the bake-off on the new contract and print it next to the incumbent-tier result,
     so you can see whether the winner-conditioned prune actually helps (CRPS/Brier + PBO).

Always runs the MDA with --bullpen-version v3 --stuff-plus-version deleaked (the leakage guard
in derive requires it). The MDA (esp. an NGBoost scorer) is multi-minute → this is an operator
job. Nothing is promoted — it produces a candidate contract + a comparison for the human.

Usage:
    # totals morning (the PBO-0.543 fix): ngboost-scored prune of the 87-feat morning contract
    uv run python betting_ml/scripts/reprune.py --target total_runs --tier pre_lineup \
        --scorer ngboost_normal \
        --input-contract betting_ml/models/total_runs/feature_columns_pre_lineup_total_runs.json \
        --out-path betting_ml/models/total_runs/feature_columns_pre_lineup_total_runs_reprune_ngb.json

    # home_win post: glm-scored re-prune of the full 209 contract (no --input-contract → default set)
    uv run python betting_ml/scripts/reprune.py --target home_win --tier post_lineup \
        --scorer glm_elasticnet \
        --out-path betting_ml/models/home_win/feature_columns_home_win_post_reprune_glm.json
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from betting_ml.scripts.clustered_feature_importance import run as mda_run
from betting_ml.scripts.derive_clustered_contract import derive
from betting_ml.scripts.model_bakeoff import _CONTRACTS, run_bakeoff


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target", choices=["home_win", "run_diff", "total_runs"], required=True)
    ap.add_argument("--tier", choices=["post_lineup", "pre_lineup"], default="post_lineup")
    ap.add_argument("--scorer", required=True,
                    choices=["xgboost", "lightgbm", "catboost", "ngboost_normal",
                             "ngboost_lognormal", "glm_elasticnet"])
    ap.add_argument("--input-contract", default=None,
                    help="Feature set to audit (default: the target's challenger contract).")
    ap.add_argument("--out-path", type=Path, required=True, help="Where to write the re-pruned contract.")
    ap.add_argument("--n-repeats", type=int, default=3)
    ap.add_argument("--embargo-days", type=int, default=3)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--no-bakeoff", action="store_true", help="Stop after deriving the contract.")
    args = ap.parse_args()

    print(f"\n━━━ STEP 1/3 — clustered MDA (scorer={args.scorer}) ━━━")
    payload = mda_run(args.target, corr_threshold=0.75, n_repeats=args.n_repeats, seed=args.seed,
                      refresh_cache=False, use_champion=False, embargo_days=args.embargo_days,
                      bullpen_version="v3", shrinkage_k=1.0, stuff_plus_version="deleaked",
                      scorer=args.scorer, input_contract=args.input_contract)
    json_path = Path(payload["_json_path"])

    print(f"\n━━━ STEP 2/3 — derive contract → {args.out_path} ━━━")
    contract = derive(args.target, json_path, allow_leaky=False, dry_run=False,
                      date="2026-06-19", out_path=args.out_path)
    n_new = len(contract["feature_cols"])

    if args.no_bakeoff:
        print(f"\n✅ re-pruned contract written ({n_new} feats). --no-bakeoff: skipping comparison.")
        return

    print(f"\n━━━ STEP 3/3 — bake-off on the re-pruned contract ({n_new} feats) ━━━")
    res = run_bakeoff(args.target, args.tier, seed=args.seed, smoke=False, refresh_cache=False,
                      embargo_days=args.embargo_days, contract=str(args.out_path))

    print("\n" + "=" * 64)
    print(f"RE-PRUNE SUMMARY — {args.target}/{args.tier}  (scorer={args.scorer})")
    print(f"  incumbent contract : {_CONTRACTS[args.tier][args.target]}")
    print(f"  re-pruned contract : {args.out_path}  ({n_new} feats)")
    print(f"  re-pruned winner   : {res['winner']}  | {res['metric']}="
          f"{[r for r in res['table'] if r['candidate']==res['winner']][0][res['metric']+'_mean']:.4f}"
          f"  | PBO={res['pbo_slate']:.3f}")
    print(f"  → compare the {res['metric']} + PBO above to the incumbent-tier bakeoff_{args.target}_{args.tier}.md;")
    print(f"    if the re-pruned contract wins (or de-overfits) → HPO/gate it with --contract {args.out_path}")
    print("=" * 64)


if __name__ == "__main__":
    main()
