"""Edge Program E13.11 — fit + persist the de-leaked v6 champion for serving.

The E1.9 v6 challengers were validated by a per-fold, in-memory promotion gate and were
NEVER persisted (registry `artifact_path: null`, note: "persisting an un-served model now
would be premature"). E13.11 is the operator re-decision to DEPLOY v6 regardless of lift —
the win is methodology integrity (the production explanations stop being dominated by the
within-game bullpen leak the v5 champion still carries) + removing the leak from prod.

This script does the one thing the gate didn't: fit each v6 model on the FULL clean matrix
(the same load_clean_matrix() de-leaked surface, refreshed so it reflects the E13.7 cold-start
convention) restricted to its tier contract, then serialize it with a served-column sidecar
and upload to S3 — exactly the artifact predict_today loads.

Why a served sidecar (not the raw clustered-MDA contract): build_imputation_pipeline() ALWAYS
appends has_starter_platoon_data + is_new_venue, so the fitted model's n_features = contract +
2. predict_today's CONTRACT-GUARD requires the registry feature_columns_path to list EXACTLY
the model's input columns, in order. We therefore write the POST-imputation column list as the
sidecar and the registry must point at it (see the printed registry-update block).

Model classes (E1.9 bake-off winners; market-blind, PBO/DSR-disciplined):
  - home_win  → glm_elasticnet (Pipeline[StandardScaler, LogisticRegression(elasticnet)]) +
    a Platt calibrator (out-of-fold), wrapped in PlattCalibratedLinearClassifier so serving is
    class-agnostic and the explainer can run exact linear SHAP.
  - run_diff / total_runs → NGBoost Normal (raw NGBRegressor; predict_today calls .pred_dist).

Tier-aware: post_lineup (dense champion) and pre_lineup (morning) are SEPARATE fits on their
own contracts. One --target + --tier per invocation (each fit is a >1-min hand-off).

Usage (operator):
  uv run python betting_ml/scripts/finalize_v6_champion.py --target home_win  --tier post_lineup
  uv run python betting_ml/scripts/finalize_v6_champion.py --target home_win  --tier pre_lineup
  uv run python betting_ml/scripts/finalize_v6_champion.py --target run_diff  --tier post_lineup
  ... (run_diff/total_runs × post_lineup/pre_lineup)
  # add --no-upload to skip S3, --smoke for a fast 400-rows/season sanity fit.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import joblib
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from betting_ml.scripts.ablation_identifier_features import _impute
from betting_ml.scripts.model_bakeoff import _assert_market_blind, load_clean_matrix
from betting_ml.utils.artifact_store import upload_artifact
from betting_ml.utils.calibrated_classifier import PlattCalibratedLinearClassifier
from betting_ml.utils.feature_hygiene import is_identifier_name

S3_BUCKET = "s3://baseball-betting-ml-artifacts"
SEED = 42

# Columns build_imputation_pipeline() ADDS (never present in the raw matrix). Some v6 contracts
# were derived from a post-imputation surface and already list these; others (clustered-MDA) do
# not. Either way we strip them before _impute (which re-adds them) and let the post-imputation
# matrix define the authoritative served column set.
_IMPUTER_ADDED = ("has_starter_platoon_data", "is_new_venue")

# finalize target -> (registry top-level key, df target column, kind, model_class, model subdir)
_TARGET_SPEC = {
    "home_win":   ("home_win",         "home_win",         "clf", "glm_elasticnet", "home_win"),
    "run_diff":   ("run_differential", "run_differential", "reg", "ngboost_normal", "run_differential"),
    "total_runs": ("total_runs",       "total_runs",       "reg", "ngboost_normal", "total_runs"),
}

# The FINAL v6 contracts as referenced by the registry challenger stanzas. NOTE: the pre_lineup
# home_win + total_runs use the WINNER-CONDITIONED re-prune variants (the gate ran with a
# --contract override) — NOT the model_bakeoff _CONTRACTS pre_lineup defaults.
_CONTRACTS = {
    ("home_win",   "post_lineup"): "betting_ml/models/home_win/feature_columns_xgb_classifier_pruned_clustered_deleaked_2026.json",
    ("home_win",   "pre_lineup"):  "betting_ml/models/home_win/feature_columns_pre_lineup_home_win_reprune_glm.json",
    ("run_diff",   "post_lineup"): "betting_ml/models/run_differential/feature_columns_ngboost_pruned_clustered_deleaked_2026.json",
    ("run_diff",   "pre_lineup"):  "betting_ml/models/run_differential/feature_columns_pre_lineup_run_diff.json",
    ("total_runs", "post_lineup"): "betting_ml/models/total_runs/feature_columns_ngboost_pruned_clustered_deleaked_2026.json",
    ("total_runs", "pre_lineup"):  "betting_ml/models/total_runs/feature_columns_pre_lineup_total_runs_reprune_ngb.json",
}

# Default config — home_win is fixed default-config (HPO overfits the thin signal; registry
# E1.9 note); ngboost defaults reproduce the bake-off non-smoke config (v6 ≈ defaults per the
# registry: HPO gains were sub-noise). Override ngboost via --n-estimators / --learning-rate.
_GLM = {"l1_ratio": 0.5, "C": 0.5}
_NGB = {"n_estimators": 400, "learning_rate": 0.01, "minibatch_frac": 1.0, "dist": "Normal"}


def _load_contract(target: str, tier: str, df) -> list[str]:
    path = _CONTRACTS[(target, tier)]
    raw = json.loads((PROJECT_ROOT / path).read_text())
    cols = raw["feature_cols"] if isinstance(raw, dict) else raw
    # Imputer-added indicators are produced by the pipeline, not the raw matrix — strip them
    # here (re-added by _impute) so a post-imputation-derived contract isn't false-flagged.
    cols = [c for c in cols if c not in _IMPUTER_ADDED]
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise SystemExit(
            f"❌ {len(missing)} contract column(s) ABSENT from the clean matrix for "
            f"{target}/{tier} — the model would be fit on fewer features than the contract "
            f"lists, breaking the serve-time CONTRACT-GUARD. Missing: {missing[:20]}"
            f"{'...' if len(missing) > 20 else ''}. Rebuild the feature store, then re-run."
        )
    _assert_market_blind(cols)
    ident = [c for c in cols if is_identifier_name(c)]
    if ident:
        raise SystemExit(f"❌ identifier column(s) in contract: {ident}")
    return cols


def _fit_glm_clf(X, y):
    """glm_elasticnet pipeline + out-of-fold Platt, wrapped (mirrors v5 architecture)."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import KFold, cross_val_predict
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    def _make():
        return make_pipeline(
            StandardScaler(),
            LogisticRegression(penalty="elasticnet", l1_ratio=_GLM["l1_ratio"], C=_GLM["C"],
                               solver="saga", max_iter=3000, random_state=SEED),
        )

    yi = np.asarray(y).astype(int)
    # Out-of-fold raw probs → Platt fit (no in-sample leakage into the calibrator); the served
    # TemperatureCalibrator (E13.6, refit on v6) is the primary calibration layer on the consensus.
    cv = KFold(n_splits=5, shuffle=True, random_state=SEED)
    oof_raw = cross_val_predict(_make(), X, yi, cv=cv, method="predict_proba", n_jobs=-1)[:, 1]
    platt = LogisticRegression(C=1.0, solver="lbfgs", max_iter=1000)
    platt.fit(oof_raw.reshape(-1, 1), yi)

    pipeline = _make()
    pipeline.fit(X, yi)  # final fit on ALL data
    return PlattCalibratedLinearClassifier(pipeline, platt)


def _fit_ngb_reg(X, y, cfg):
    """Raw NGBoost Normal regressor (predict_today calls .pred_dist(X).params)."""
    from ngboost import NGBRegressor
    from ngboost.distns import Normal

    m = NGBRegressor(n_estimators=cfg["n_estimators"], Dist=Normal, verbose=False,
                     learning_rate=cfg["learning_rate"], minibatch_frac=cfg["minibatch_frac"],
                     random_state=SEED)
    m.fit(np.asarray(X), np.asarray(y, dtype=float))
    return m


def _pooled_gate_metric(target: str, tier: str) -> tuple[str, float] | None:
    """(metric_name, n-weighted pooled CHALLENGER metric) from the (target, tier) promotion-gate
    JSON — the honest de-leaked purged-CV number to stamp on the lineage row. The gate filename
    uses the --target alias (home_win / run_diff / total_runs). Returns None if the gate JSON is
    absent/unreadable; a gate is a promotion prerequisite, so absence is warned-on, never faked."""
    gate = (PROJECT_ROOT / "betting_ml" / "evaluation" / "feature_selection" / "promotion_gate"
            / f"gate_v6_vs_v5_{target}_{tier}.json")
    if not gate.exists():
        return None
    try:
        d = json.loads(gate.read_text())
        ps = d.get("per_season") or []
        den = sum(s["n"] for s in ps)
        if den <= 0:
            return None
        num = sum(s["challenger"] * s["n"] for s in ps)
        return str(d.get("gate_metric") or "metric"), round(num / den, 4)
    except Exception:  # noqa: BLE001 — a malformed gate file must not fake a metric
        return None


def _record_champion_lineage(target: str, reg_key: str, model_class: str, s3_uri: str,
                             reg_cols_path: str, n_served: int, training_rows: int,
                             promoted_date: str) -> None:
    """Record the v6 promotion in the Snowflake champion-lineage table right after the S3 upload,
    so serving and the ledger never diverge.

    E9.26b — this is the missing link the lag came from: finalize updated only model_registry.yaml
    (the served-artifact source) + S3, while the SF `model_registry` lineage table is maintained
    ONLY by record_promotion(). That step was never run for the E13.11 v6 swap, so the ledger
    stuck at v5 and the Admin → Model Artifact Freshness panel read `ledger_behind`.

    Idempotent (record_promotion() no-ops if v6 is already current) and NON-FATAL: the S3 upload
    already succeeded, so a lineage failure must never fail the deploy. On a missing gate JSON
    (no honest CV to stamp) it warns LOUDLY and skips, pointing at reconcile_v6_ledger.py rather
    than recording a fabricated metric."""
    metric = _pooled_gate_metric(target, "post_lineup")
    if metric is None:
        print(f"  ⚠️  LINEAGE NOT RECORDED — gate_v6_vs_v5_{target}_post_lineup.json not found, so "
              "there is no honest CV to stamp. Run the promotion gate first, or reconcile manually: "
              "uv run python scripts/ops/reconcile_v6_ledger.py --apply")
        return
    metric_name, metric_value = metric
    # Lazy import — only a real deploy touches Snowflake (keeps --smoke/--no-upload SF-free).
    from betting_ml.utils.model_registry_tracker import record_promotion
    try:
        rec = record_promotion(
            target=reg_key,
            new_version="v6",
            model_name=f"{model_class}_deleaked",
            artifact_path=s3_uri,
            feature_columns_path=reg_cols_path,
            features=int(n_served),
            training_rows=int(training_rows),
            training_cutoff="2021+",
            cv_metric_name=metric_name,
            cv_metric_value=metric_value,
            promoted_date=promoted_date,
            notes=(
                f"E13.11 de-leaked v6 champion (post_lineup, {n_served}-served {model_class}). "
                "Recorded by finalize_v6_champion.py after the S3 upload (E9.26b lineage-on-promote "
                f"wiring). CV {metric_name} {metric_value} = n-weighted pooled challenger on the "
                "de-leaked purged-CV promotion gate."
            ),
        )
    except Exception as exc:  # noqa: BLE001 — deploy already succeeded; never fail on lineage
        print(f"  ⚠️  LINEAGE record_promotion FAILED ({type(exc).__name__}: {exc}); reconcile "
              "manually: uv run python scripts/ops/reconcile_v6_ledger.py --apply")
        return
    if rec.already_current:
        print("  ✓ SF champion-lineage: v6 already current — no-op (idempotent).")
    else:
        print(f"  ✓ SF champion-lineage: recorded v6 (deprecated {rec.deprecated_version or '(none)'}).")


def main() -> None:
    ap = argparse.ArgumentParser(description="Fit + persist the de-leaked v6 champion (E13.11).")
    ap.add_argument("--target", required=True, choices=list(_TARGET_SPEC))
    ap.add_argument("--tier", required=True, choices=["post_lineup", "pre_lineup"])
    ap.add_argument("--refresh-cache", action="store_true",
                    help="Re-pull the training matrix (REQUIRED for the E13.7 cold-start "
                         "convention to flow in; the cached matrix predates E13.7).")
    ap.add_argument("--no-upload", action="store_true", help="Skip the S3 upload (local only).")
    ap.add_argument("--sidecar-only", action="store_true",
                    help="Derive + write the served-column sidecar ONLY (no fit/upload). The "
                         "served columns are deterministic (contract + indicators), so this stages "
                         "the committable sidecar + makes the parity-guard CI green before the "
                         "operator's full fit (which regenerates an identical sidecar).")
    ap.add_argument("--smoke", action="store_true", help="Fast 400-rows/season sanity fit.")
    ap.add_argument("--n-estimators", type=int, default=None, help="Override ngboost n_estimators.")
    ap.add_argument("--learning-rate", type=float, default=None, help="Override ngboost lr.")
    ap.add_argument("--no-record-lineage", action="store_true",
                    help="Skip recording the v6 promotion in the Snowflake champion-lineage table. "
                         "By default a real post_lineup deploy records it (E9.26b — stop the ledger "
                         "lagging serving; the Admin freshness panel read `ledger_behind` otherwise).")
    ap.add_argument("--promoted-date", default=None,
                    help="ISO date ('YYYY-MM-DD') to stamp as the v6 promotion date on the lineage "
                         "row (default: today).")
    args = ap.parse_args()

    reg_key, tcol, kind, model_class, subdir = _TARGET_SPEC[args.target]
    if not args.refresh_cache:
        print("[WARN] --refresh-cache NOT set: fitting on the cached matrix, which may predate "
              "the E13.7 cold-start convention. Set --refresh-cache to honor E13.7 (and ensure "
              "the prod dbt feature store has been rebuilt with E13.7 first).")

    df = load_clean_matrix(refresh_cache=args.refresh_cache, smoke=args.smoke)
    cols = _load_contract(args.target, args.tier, df)
    print(f"target={args.target} tier={args.tier} | class={model_class} | "
          f"{len(cols)} contract features | {len(df)} rows")

    # Build X exactly as the gate/serving does: impute on the contract cols (this appends the
    # indicator columns) → the served column set is whatever the imputer emits, in order.
    Ximp, _ = _impute(df[cols], df[cols])
    served_cols = list(Ximp.columns)
    y = df[tcol].values
    print(f"  post-imputation served features: {len(served_cols)} "
          f"(contract {len(cols)} + {len(served_cols) - len(cols)} indicator col(s))")

    # Morning-safety report: a pre_lineup contract must carry NO lineup-composition-gated
    # features (NULL until lineups post → would re-introduce the 30.3/33.0 morning skew).
    import re as _re
    _gated_re = _re.compile(r"lineup_avg|lineup_archetype|_vs_cluster|lineup_slot|xwoba_vs_(?:lhp|rhp)", _re.I)
    _gated = [c for c in served_cols if _gated_re.search(c)]
    print(f"  lineup-gated features in this {args.tier} contract: {len(_gated)} {_gated if _gated else ''}")
    if args.tier == "pre_lineup" and _gated:
        raise SystemExit(f"❌ pre_lineup contract carries lineup-gated features (morning skew): {_gated}")

    sidecar_local = (PROJECT_ROOT / "betting_ml" / "models" / subdir
                     / f"feature_columns_v6_{args.target}_{args.tier}_served.json")
    sidecar = {
        "feature_cols": served_cols,
        "_provenance": {
            "story": "E13.11",
            "derived": date.today().isoformat(),
            "model_class": model_class,
            "tier": args.tier,
            "registry_target": reg_key,
            "source_contract": _CONTRACTS[(args.target, args.tier)],
            "n_contract": len(cols),
            "n_served": len(served_cols),
            "method": "E1.9 v6 de-leaked champion finalized on full load_clean_matrix() "
                      "(bullpen_v3 + Stuff+ prior-season), post-imputation served columns. "
                      "Edge-agnostic integrity deploy (E13.11); v5 retained as rollback.",
            "sidecar_only": args.sidecar_only,
            "smoke": args.smoke,
            "refresh_cache": args.refresh_cache,
        },
    }
    if args.sidecar_only:
        sidecar_local.write_text(json.dumps(sidecar, indent=2))
        print(f"  [sidecar-only] saved sidecar → {sidecar_local.relative_to(PROJECT_ROOT)} "
              f"(no model fit; operator's finalize run regenerates an identical sidecar + the binary)")
        return

    if kind == "clf":
        cfg_used = dict(_GLM)
        model = _fit_glm_clf(Ximp.values, y)
    else:
        cfg = dict(_NGB)
        if args.n_estimators is not None:
            cfg["n_estimators"] = args.n_estimators
        if args.learning_rate is not None:
            cfg["learning_rate"] = args.learning_rate
        cfg_used = cfg
        model = _fit_ngb_reg(Ximp.values, y, cfg)

    # n_features_in_ MUST equal the served sidecar length (the serve-time CONTRACT-GUARD).
    n_in = getattr(model, "n_features_in_", None)
    if n_in is not None and int(n_in) != len(served_cols):
        raise SystemExit(f"❌ fitted model n_features_in_={n_in} != served_cols={len(served_cols)}; "
                         f"sidecar/model mismatch would fail the serve-time CONTRACT-GUARD.")

    # ── persist: artifact + served-column sidecar (reuses the sidecar built above) ──
    base = f"{model_class}_deleaked_v6_{args.tier}_2026"
    artifact_local = PROJECT_ROOT / "betting_ml" / "models" / subdir / f"{base}.pkl"
    s3_uri = f"{S3_BUCKET}/{subdir}/{base}.pkl"

    joblib.dump(model, artifact_local)
    sidecar["_provenance"]["config"] = cfg_used
    sidecar_local.write_text(json.dumps(sidecar, indent=2))
    print(f"  saved model   → {artifact_local.relative_to(PROJECT_ROOT)}")
    print(f"  saved sidecar → {sidecar_local.relative_to(PROJECT_ROOT)}")

    if args.no_upload or args.smoke:
        print("  [skip] S3 upload (--no-upload or --smoke).")
    else:
        upload_artifact(artifact_local, s3_uri)

    # ── registry-update block (step E is mechanical from here) ────────────────
    reg_cols_path = f"betting_ml/models/{subdir}/{sidecar_local.name}"
    print("\n── model_registry.yaml update for this fit ─────────────────────────")
    if args.tier == "post_lineup":
        print(f"  {reg_key}:")
        print(f"    artifact_path: {s3_uri}")
        print(f"    feature_columns_path: {reg_cols_path}")
        print(f"    features: {len(served_cols)}")
        print(f"    model_version: v6   # retain prior as prev_artifact_path / rollback")
        if kind == "reg":
            print(f"    dist: Normal")
    else:
        print(f"  {reg_key}:")
        print(f"    pre_lineup: {s3_uri}")
        print(f"    pre_lineup_feature_columns_path: {reg_cols_path}")
        print(f"    pre_lineup_model_version: v6")
    print("────────────────────────────────────────────────────────────────────")

    # ── SF champion-lineage recording (E9.26b) — keep the ledger from lagging serving ──
    # Only the post_lineup tier records a lineage row: the table is keyed on (target, version),
    # so the pre_lineup fit is the SAME v6 champion row (a tier variant, not a new lineage entry).
    # Skipped on --no-upload/--smoke (no real deploy) and --no-record-lineage.
    if args.tier == "post_lineup" and not (args.no_upload or args.smoke) and not args.no_record_lineage:
        promoted_date = args.promoted_date or date.today().isoformat()
        _record_champion_lineage(args.target, reg_key, model_class, s3_uri, reg_cols_path,
                                 len(served_cols), len(df), promoted_date)


if __name__ == "__main__":
    main()
