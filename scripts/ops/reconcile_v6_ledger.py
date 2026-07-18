"""reconcile_v6_ledger.py — reconcile the Snowflake champion-lineage ledger to v6 (E9.26b).

WHY: E13.11 (2026-06-23) rolled the de-leaked **v6** champions to S3/serving via
`betting_ml/scripts/finalize_v6_champion.py`, which updates `betting_ml/models/model_registry.yaml`
(what predict_today loads → daily_model_predictions stamps v6). But the SEPARATE Snowflake
temporal-lineage table `baseball_data.betting_ml.model_registry` is only maintained by
`model_registry_tracker.record_promotion()` — and that step was never run for the v6 swap.
So the ledger froze at v5 while serving moved to v6, and the Admin → "Model Artifact Freshness"
panel honestly flagged `ledger_behind` (served v6 vs registry v5) for reconciliation. This is
the honest-ledger fix: record the v6 promotions so the lineage matches reality.

WHAT: calls `record_promotion()` (transactional + idempotent — a no-op if v6 is already the
current row) for the three post_lineup v6 champions. Each call closes the outgoing v5 row
(deprecated_date = 2026-06-23, is_current = FALSE) and inserts/activates the v6 row
(is_current = TRUE). Re-running is safe.

Metadata provenance (all sourced, NOT fabricated):
  • artifact_path / feature_columns_path / features → betting_ml/models/model_registry.yaml
    (the served v6 post_lineup entries + the v6 served sidecars).
  • cv_metric_value → the n-weighted pooled purged-CV metric of the v6 CHALLENGER from the
    E1.9→E13.11 promotion gate JSONs (gate_v6_vs_v5_<target>_post_lineup.json). These sit on the
    DE-LEAKED purged-CV surface, so they differ from the pre-de-leak v5 rows (0.1948 / 3.066 /
    3.3251) — recording the honest de-leaked number IS the point.
  • promoted_date = 2026-06-23 (the E13.11 deploy date).
  • training_rows / training_cutoff → the same load_clean_matrix() full window as the v5
    market-blind fit (v6 re-fit on the same rows, de-leaked feature subset).

RUN (laptop, with the DBT_RW Snowflake creds — has write on model_registry):
    uv run python scripts/ops/reconcile_v6_ledger.py            # dry-run (prints the plan)
    uv run python scripts/ops/reconcile_v6_ledger.py --apply    # record the v6 promotions
"""
from __future__ import annotations

import argparse

from betting_ml.utils.model_registry_tracker import record_promotion

# One entry per post_lineup v6 champion. Kwargs match record_promotion() exactly.
_PROMOTIONS = [
    dict(
        target="home_win",
        new_version="v6",
        model_name="glm_elasticnet_deleaked",
        artifact_path="s3://baseball-betting-ml-artifacts/home_win/glm_elasticnet_deleaked_v6_post_lineup_2026.pkl",
        feature_columns_path="betting_ml/models/home_win/feature_columns_v6_home_win_post_lineup_served.json",
        features=21,
        training_rows=10766,
        training_cutoff="2021+",
        cv_metric_name="brier",
        cv_metric_value=0.2447,
        promoted_date="2026-06-23",
        notes=(
            "E13.11 (2026-06-23) de-leaked v6 production rollout (methodology-integrity, edge-agnostic). "
            "Champion = E1.9 v6 glm_elasticnet (21 served = 19 contract + 2 indicators), a ~20x-leaner "
            "leak-clean replacement for the leaky v5 XGBoost. CV brier 0.2447 on the de-leaked purged-CV "
            "surface (v6 vs v5 0.2457 = sub-noise tie; the v5 row 0.1948 was on the pre-de-leak surface). "
            "Lineage reconciled 2026-07-17 (E9.26b): finalize_v6_champion.py updated model_registry.yaml + "
            "served v6 but never called record_promotion(), so this SF lineage table lagged at v5."
        ),
    ),
    dict(
        target="run_differential",
        new_version="v6",
        model_name="ngboost_normal_deleaked",
        artifact_path="s3://baseball-betting-ml-artifacts/run_differential/ngboost_normal_deleaked_v6_post_lineup_2026.pkl",
        feature_columns_path="betting_ml/models/run_differential/feature_columns_v6_run_diff_post_lineup_served.json",
        features=15,
        training_rows=10256,
        training_cutoff="2021+",
        cv_metric_name="mae",
        cv_metric_value=3.4776,
        promoted_date="2026-06-23",
        notes=(
            "E13.11 (2026-06-23) de-leaked v6 production rollout, deployed with the home_win integrity swap "
            "(run_diff feeds the h2h consensus). Champion = E1.9 v6 ngboost_normal (15 served = 13 contract "
            "+ 2 indicators), a ~29x-leaner leak-clean equal of v5. CV mae 3.4776 on the de-leaked purged-CV "
            "surface (v6 vs v5 3.4777 = tie). Lineage reconciled 2026-07-17 (E9.26b): served v6 since "
            "2026-06-23 but record_promotion() was never called, so this table lagged at v5."
        ),
    ),
    dict(
        target="total_runs",
        new_version="v6",
        model_name="ngboost_normal_deleaked",
        artifact_path="s3://baseball-betting-ml-artifacts/total_runs/ngboost_normal_deleaked_v6_post_lineup_2026.pkl",
        feature_columns_path="betting_ml/models/total_runs/feature_columns_v6_total_runs_post_lineup_served.json",
        features=15,
        training_rows=10766,
        training_cutoff="2021+",
        cv_metric_name="mae",
        cv_metric_value=3.4948,
        promoted_date="2026-06-23",
        notes=(
            "E13.11 (2026-06-23) de-leaked v6 production rollout (totals projection source; bet_paused stays "
            "true). Champion = E1.9 v6 ngboost_normal (15 served = 13 contract + 2 indicators), a ~28x-leaner "
            "leak-clean near-equal of v5. CV mae 3.4948 on the de-leaked purged-CV surface (v6 vs v5 3.5046). "
            "Lineage reconciled 2026-07-17 (E9.26b): served v6 since 2026-06-23 but record_promotion() was "
            "never called, so this table lagged at v5."
        ),
    ),
]


def main() -> int:
    ap = argparse.ArgumentParser(description="Reconcile the Snowflake champion-lineage ledger to v6 (E9.26b)")
    ap.add_argument("--apply", action="store_true", help="Actually record the promotions (default: dry-run)")
    args = ap.parse_args()

    if not args.apply:
        print("DRY-RUN — would record these v6 promotions (re-run with --apply):")
        for p in _PROMOTIONS:
            print(f"  {p['target']:<16} v6  {p['model_name']:<24} "
                  f"{p['cv_metric_name']}={p['cv_metric_value']}  promoted={p['promoted_date']}")
        print("record_promotion() is idempotent + transactional (closes the v5 row, opens v6); safe to re-run.")
        return 0

    for p in _PROMOTIONS:
        rec = record_promotion(**p)
        if rec.already_current:
            print(f"✓ {p['target']}: v6 already current — no-op (idempotent).")
        else:
            print(f"✓ {p['target']}: promoted v6, deprecated {rec.deprecated_version or '(none)'}.")
    print("\nLedger reconciled. Admin → Model Artifact Freshness should now show v6 == registry (no ledger_behind).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
