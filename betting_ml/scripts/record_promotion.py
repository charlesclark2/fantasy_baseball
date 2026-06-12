"""
record_promotion.py — CLI to record a champion promotion in the Snowflake lineage table.

Story 30.7. The per-promotion entrypoint that maintains
`baseball_data.betting_ml.model_registry` (promoted_date / deprecated_date /
is_current). Run this as part of the promotion runbook, right AFTER the S3
artifact push and the model_registry.yaml edit, BEFORE the kill-window reset.

Example (Story 30.4 home_win market-blind promotion):
    uv run python betting_ml/scripts/record_promotion.py \
      --target home_win --new-version v5 --model-name xgb_market_blind \
      --artifact-path s3://baseball-betting-ml-artifacts/home_win/xgb_market_blind_2026.pkl \
      --feature-columns-path betting_ml/models/home_win/feature_columns_market_blind.json \
      --features 209 --training-rows 10766 --training-cutoff 2021+ \
      --cv-metric brier --cv-value 0.1919 --promoted-date 2026-06-12 \
      --notes "Story 30.4 market-blind retrain; promoted via correctness override (removes 9 market leaks + 3 identifiers, accuracy non-regression per promotion gate)."

Idempotent: re-running the same (target, new-version) is a no-op.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(_PROJECT_ROOT / ".env")

from betting_ml.utils.model_registry_tracker import record_promotion


def main() -> None:
    p = argparse.ArgumentParser(description="Record a champion promotion in the Snowflake lineage table.")
    p.add_argument("--target", required=True, help="e.g. home_win, run_differential, total_runs")
    p.add_argument("--new-version", required=True, help="e.g. v5")
    p.add_argument("--model-name", required=True, help="e.g. xgb_market_blind")
    p.add_argument("--artifact-path", required=True, help="S3 uri of the promoted artifact")
    p.add_argument("--feature-columns-path", required=True)
    p.add_argument("--features", type=int, required=True, help="POST-pipeline feature count (CONTRACT-GUARD dim)")
    p.add_argument("--training-rows", type=int, required=True)
    p.add_argument("--training-cutoff", required=True, help="e.g. 2021+")
    p.add_argument("--cv-metric", required=True, help="brier | mae | nll | crps ...")
    p.add_argument("--cv-value", type=float, required=True)
    p.add_argument("--promoted-date", required=True, help="ISO date 'YYYY-MM-DD'")
    p.add_argument("--notes", required=True)
    p.add_argument("--dry-run", action="store_true",
                   help="Print the intended promotion without writing to Snowflake.")
    args = p.parse_args()

    if args.dry_run:
        print(f"[DRY RUN] would promote {args.target} → {args.new_version} "
              f"({args.model_name}, {args.features} feats, {args.cv_metric}={args.cv_value}) "
              f"promoted_date={args.promoted_date}")
        print("  → would close the current champion (deprecated_date=promoted_date, is_current=FALSE)")
        print("  → would insert the new champion (is_current=TRUE)")
        return

    rec = record_promotion(
        target=args.target, new_version=args.new_version, model_name=args.model_name,
        artifact_path=args.artifact_path, feature_columns_path=args.feature_columns_path,
        features=args.features, training_rows=args.training_rows,
        training_cutoff=args.training_cutoff, cv_metric_name=args.cv_metric,
        cv_metric_value=args.cv_value, promoted_date=args.promoted_date, notes=args.notes,
    )

    if rec.already_current:
        print(f"NO-OP: {rec.target} {rec.new_version} is already the current champion. "
              f"Nothing changed (idempotent).")
    else:
        retired = rec.deprecated_version or "(none — first champion on record)"
        print(f"PROMOTED: {rec.target} {rec.new_version} is now is_current=TRUE "
              f"(promoted_date={args.promoted_date}).")
        print(f"  retired previous champion: {retired} "
              f"(deprecated_date={args.promoted_date})")
    print("\nVerify:")
    print("  SELECT target, model_version, is_current, promoted_date, deprecated_date")
    print("  FROM baseball_data.betting_ml.model_registry")
    print(f"  WHERE target = '{args.target}' ORDER BY promoted_date;")


if __name__ == "__main__":
    main()
