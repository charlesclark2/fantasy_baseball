"""Fit + persist the MH2.1 champion for ``total_runs``/``post_lineup`` (2026-08-02).

WHAT THIS PROMOTES
------------------
MH2.1 re-ran E7.9's retrain bake-off on the WIDE window (2016–2026 ⇒ 8 purged/embargoed folds
instead of 3) with a pre-registered 4-arm family, and returned SHIP_CHALLENGER for

    plus_eb  ×  glm_elasticnet          (contract variant × learner class)

replacing the served ``incumbent × ngboost_normal`` (E13.11 v6).

⚠️ **THE HEADLINE IS "LEARNER SWAP + FEATURE BLOCK", NOT "plus_eb WON".** The +0.0297 CRPS
margin decomposes into **+0.0175 (59%) from the LEARNER SWAP** and **+0.0122 from the plus_eb
block** — and **neither component alone clears the 0.02 noise floor**. Only their sum does.
Any record that reads "the EB block earned a champion" is wrong.

⚠️ **THE WIDE-WINDOW CERTIFICATION IS BOUNDED — only 3 of the 8 folds test the contract that is
actually served.** Two of the incumbent's 13 columns are *structurally absent* in the early
folds: ``away_lineup_bat_speed_vs_starter_velo`` (Statcast bat-tracking; 0.000 through 2022) and
``home_starter_proj_fip`` (0.000 for 2016–2019). The CONTRAST stays fair — both arms take the
identical handicap every fold — but the extra folds certify less about the SERVED model than the
fold count suggests.

⚠️ **E2.1-r CAVEAT CARRIED: this selection is on PRICING (CRPS + conditional calibration).** A
later edge-detection story wanting sharp per-side means must RE-SELECT on a discrimination
metric — it may not inherit this winner.

WHY IT WON (the decisive evidence was calibration, not the thin CRPS margin)
---------------------------------------------------------------------------
RMS |Var(z) − 1| across σ-deciles (``Var(z) = 1`` in every stratum is the analytic truth for a
conditionally calibrated predictive; see ``mh2_1_conditional_calibration.py``)::

    incumbent::ngboost_normal (SERVED)   0.158    pooled Var(z) 1.124
    plus_eb::ngboost_normal              0.180    pooled Var(z) 1.111
    plus_eb::glm_elasticnet (THIS)       0.050    pooled Var(z) 0.997
    ngboost with σ deliberately FLAT     0.107    pooled Var(z) 1.090

The served NGBoost under-estimates σ, worst in the games it calls calm (Var(z) 1.44 in the calmest
decile ⇒ served P(over) is overconfident exactly where P(over)-at-a-line is most sensitive), and
FLATTENING its σ *improves* its calibration. The per-game σ being retired was actively wrong, not
merely uninformative.

``best_alpha = 0``. This is a PRICING/CALIBRATION promotion. **No edge, win-rate, or ROI claim.**

THE FIT IS THE VALIDATED OBJECT
-------------------------------
``model_bakeoff.PointNormalSpec`` is what the bake-off actually scored: a point learner wrapped as
``Normal(pred(X), σ̂)`` with σ̂ frozen at the **training residual std**. This script reproduces that
verbatim and persists it via ``HomoscedasticNormalRegressor`` so the object that SERVES is the
object that was VALIDATED. Deviating (e.g. serving the glm mean beside the NGBoost's σ) would
serve a model no gate ever scored — and would re-import the miscalibrated σ this promotion exists
to remove.

💸 **SNOWFLAKE-FREE BY DEFAULT.** Reads the cached feature matrix; ``--refresh-cache`` is opt-in
and wakes the warehouse (~80% of the SF bill is wake/idle — E11.20-COST).

USAGE (LAPTOP)
--------------
    uv run python betting_ml/scripts/finalize_mh2_1_champion.py --no-upload     # local rehearsal
    uv run python betting_ml/scripts/finalize_mh2_1_champion.py                 # fit + S3 upload
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timezone, datetime
from pathlib import Path

import joblib
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from betting_ml.scripts.ablation_identifier_features import _impute
from betting_ml.scripts.model_bakeoff import _assert_market_blind, load_clean_matrix
from betting_ml.utils.artifact_store import upload_artifact
from betting_ml.utils.feature_hygiene import is_identifier_name
from betting_ml.utils.homoscedastic_regressor import HomoscedasticNormalRegressor

STORY = "MH2.1"
BEST_ALPHA = 0
S3_BUCKET = "s3://baseball-betting-ml-artifacts"
SEED = 42
SUBDIR = "total_runs"

# The window MH2.1 validated on. NOT the incumbent's 2021+ — widening the window IS the story
# (MH2 measured that E7.9's 3-fold ceiling was a WINDOW CHOICE, not a data limit), and every arm
# in the pre-registered family was fit on this window in every fold.
MIN_YEAR = 2016

# The incumbent's served 13-col contract — the base every MH2.1 variant extends.
BASE_CONTRACT = "betting_ml/models/total_runs/feature_columns_ngboost_pruned_clustered_deleaked_2026.json"

# `plus_eb` = base + the E7.5 / E7.5p MLE-corrected EB columns the base contract does NOT carry.
# Mirrors e7_9_train_serve_consistency.MLE_AFFECTED_COLS exactly; a drift guard pins the equality.
E75_BATTER_COLS = tuple(
    f"{side}_avg_eb_{m}" for side in ("home", "away") for m in ("k_pct", "bb_pct", "iso")
)
E75P_STARTER_COLS = tuple(
    f"{side}_starter_eb_{m}" for side in ("home", "away") for m in ("k_pct", "bb_pct")
)
PLUS_EB_COLS = E75_BATTER_COLS + E75P_STARTER_COLS

# build_imputation_pipeline() ALWAYS appends these; strip before _impute (which re-adds them).
IMPUTER_ADDED = ("has_starter_platoon_data", "is_new_venue")

# The bake-off's glm_elasticnet, verbatim (model_bakeoff._candidates, reg branch).
GLM = {"alpha": 0.1, "l1_ratio": 0.5, "random_state": SEED}

# `_swap_bullpen_v3` rewrites these two CONTRACT columns (plus `*_bp_eb_xwoba`, which the contract
# does not carry) from the per-season bullpen_v3 caches. A season with no cache keeps its ORIGINAL
# (pre-de-leak) values, so a window spanning the cache boundary trains one coefficient across TWO
# measurement conventions. Detected + quantified rather than assumed — see `bullpen_v3_provenance`.
BULLPEN_V3_SWAPPED_CONTRACT_COLS = ("home_bp_eb_uncertainty", "away_bp_eb_uncertainty")


def bullpen_v3_provenance(df) -> dict:
    """Which training seasons carry de-leaked bullpen_v3 values, and how big is the seam?

    ⚠️ This is a REPORTING obligation, not a gate. The MH2.1 bake-off scored every arm on this same
    matrix, so the CONTEST was fair; but a CHAMPION FIT bakes the seam into served coefficients,
    which the contest did not. Quantifying it is what makes "we chose the validated window anyway"
    a disclosed decision rather than an unnoticed one.
    """
    from betting_ml.scripts.eb_priors.compute_bullpen_v3 import _CACHE_DIR

    years = sorted({int(y) for y in df["game_year"].dropna().unique()})
    covered = [y for y in years if (_CACHE_DIR / f"per_reliever_{y}.parquet").exists()]
    missing = [y for y in years if y not in covered]
    out = {"seasons": years, "bullpen_v3_covered": covered, "bullpen_v3_missing": missing,
           "seam_by_column": {}}
    if missing and covered:
        yr = df["game_year"].astype(int)
        pre, post = yr.isin(missing), yr.isin(covered)
        for c in BULLPEN_V3_SWAPPED_CONTRACT_COLS:
            if c in df.columns:
                out["seam_by_column"][c] = {
                    "uncovered_mean": round(float(df.loc[pre, c].mean()), 6),
                    "covered_mean": round(float(df.loc[post, c].mean()), 6),
                }
    return out


def build_estimator():
    """`Pipeline(StandardScaler, ElasticNet)` — byte-for-byte the bake-off's `glm_elasticnet`."""
    from sklearn.linear_model import ElasticNet
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    return make_pipeline(StandardScaler(), ElasticNet(**GLM))


def train_residual_sigma(estimator, X, y) -> float:
    """σ̂ = std of the TRAINING residuals — `PointNormalSpec.fit` verbatim (ddof=0, `or 1.0`)."""
    resid = np.asarray(y, float) - np.asarray(estimator.predict(X), float)
    return float(np.std(resid)) or 1.0


def oof_residual_sigma(X, y, n_splits: int = 5) -> float:
    """An out-of-fold σ̂, computed ONLY as a disclosure — never served.

    The in-sample σ̂ that `PointNormalSpec` freezes could in principle be optimistically NARROW.
    MH2.1's calibration evidence says it is not (that σ̂ produced pooled Var(z) 0.997 on HELD-OUT
    folds), but "the evidence says it's fine" is worth a number rather than an assertion, so the
    two are reported side by side. A large gap here would mean the served σ is too tight.
    """
    from sklearn.model_selection import KFold, cross_val_predict

    pred = cross_val_predict(build_estimator(), X, y,
                             cv=KFold(n_splits=n_splits, shuffle=True, random_state=SEED))
    return float(np.std(np.asarray(y, float) - np.asarray(pred, float))) or 1.0


def resolve_contract(df_cols) -> tuple[list[str], list[str]]:
    """(base 13, plus_eb adds) restricted to columns actually present in the matrix."""
    raw = json.loads((PROJECT_ROOT / BASE_CONTRACT).read_text())
    base = [c for c in (raw["feature_cols"] if isinstance(raw, dict) else raw)
            if c not in IMPUTER_ADDED]
    missing = [c for c in base if c not in df_cols]
    if missing:
        raise SystemExit(
            f"❌ {len(missing)} base-contract column(s) absent from the matrix: {missing}. "
            "The model would be fit on fewer features than the contract lists, breaking the "
            "serve-time CONTRACT-GUARD. Rebuild the feature store, then re-run."
        )
    adds = [c for c in PLUS_EB_COLS if c in df_cols and c not in base]
    if len(adds) != len(PLUS_EB_COLS):
        # Not fatal for a fit, but it would mean serving a DIFFERENT arm than the one scored.
        raise SystemExit(
            f"❌ plus_eb resolves to {len(adds)} of {len(PLUS_EB_COLS)} columns "
            f"(missing: {[c for c in PLUS_EB_COLS if c not in adds]}). The bake-off scored the "
            "full block — fitting a subset would serve an arm no gate evaluated."
        )
    return base, adds


def main() -> None:
    ap = argparse.ArgumentParser(description="Fit + persist the MH2.1 total_runs/post_lineup champion.")
    ap.add_argument("--refresh-cache", action="store_true",
                    help="💸 Re-pull the feature matrix from Snowflake (wakes the warehouse). "
                         "Default is the CACHED matrix — Snowflake-free.")
    ap.add_argument("--no-upload", action="store_true", help="Skip the S3 upload (local only).")
    ap.add_argument("--smoke", action="store_true", help="Fast sanity fit on a row sample.")
    ap.add_argument("--min-year", type=int, default=MIN_YEAR,
                    help=f"Training window start (default {MIN_YEAR} — the window MH2.1 validated).")
    ap.add_argument("--no-record-lineage", action="store_true",
                    help="Skip the Snowflake champion-lineage row. Without that row the Admin → "
                         "Model Freshness panel keeps showing the RETIRED v6 as the totals "
                         "champion, so a real deploy should record it (E9.26b).")
    args = ap.parse_args()

    if args.refresh_cache:
        print("[💸 WARN] --refresh-cache set: this WAKES Snowflake. The cached matrix is the "
              "default for exactly this reason.")

    df = load_clean_matrix(refresh_cache=args.refresh_cache, smoke=args.smoke,
                           min_year=args.min_year)
    base, adds = resolve_contract(df.columns)
    cols = base + adds
    _assert_market_blind(cols)
    ident = [c for c in cols if is_identifier_name(c)]
    if ident:
        raise SystemExit(f"❌ identifier column(s) in contract: {ident}")

    print(f"{STORY} champion · total_runs/post_lineup · glm_elasticnet (homoscedastic Normal)")
    print(f"  window {args.min_year}+ · {len(df):,} rows")
    print(f"  contract: {len(base)} base + {len(adds)} plus_eb = {len(cols)}")

    bp_prov = bullpen_v3_provenance(df)
    if bp_prov["bullpen_v3_missing"]:
        print(f"  ⚠️ bullpen_v3 de-leak MISSING for {bp_prov['bullpen_v3_missing']} — those seasons "
              f"keep pre-de-leak values in {list(BULLPEN_V3_SWAPPED_CONTRACT_COLS)}, so this fit "
              f"spans two measurement conventions:")
        for c, s in bp_prov["seam_by_column"].items():
            print(f"       {c}: uncovered mean {s['uncovered_mean']:.4f} "
                  f"vs covered {s['covered_mean']:.4f}")
        print("     Durable fix = backfill bullpen_v3 for those seasons; the cheap alternative is "
              "--min-year 2021 (fully covered, and the incumbent's own window).")

    Ximp, _ = _impute(df[cols], df[cols])
    served_cols = list(Ximp.columns)
    y = df["total_runs"].values
    print(f"  post-imputation served features: {len(served_cols)} "
          f"(contract {len(cols)} + {len(served_cols) - len(cols)} indicator col(s))")

    est = build_estimator()
    est.fit(Ximp.values, y)
    sigma = train_residual_sigma(est, Ximp.values, y)
    sigma_oof = oof_residual_sigma(Ximp.values, y)
    print(f"  σ̂ (train residual std, SERVED) = {sigma:.4f}")
    print(f"  σ̂ (out-of-fold, disclosure only) = {sigma_oof:.4f}  "
          f"[ratio {sigma_oof / sigma:.4f} — >1 means the served σ is optimistically tight]")

    model = HomoscedasticNormalRegressor(
        est, sigma,
        sigma_method="train_residual_std (model_bakeoff.PointNormalSpec verbatim)",
        n_train=int(len(df)),
        provenance={
            "story": STORY, "best_alpha": BEST_ALPHA,
            "arm": "plus_eb::glm_elasticnet", "target": "total_runs", "tier": "post_lineup",
            "min_year": int(args.min_year), "seed": SEED, "glm": GLM,
            "sigma_train": sigma, "sigma_oof_disclosure": sigma_oof,
            "fit_at": datetime.now(timezone.utc).isoformat(),
            "margin_decomposition": {
                "total_crps_margin": 0.0297, "learner_swap": 0.0175, "plus_eb_block": 0.0122,
                "noise_floor": 0.02,
                "note": "LEARNER SWAP + FEATURE BLOCK — neither component clears the floor alone.",
            },
            "folds_testing_served_contract": "3 of 8 (2024-26); bat_speed + proj_fip absent earlier",
            "selection_basis": "PRICING (CRPS + conditional calibration) — E2.1-r: an edge-detection "
                               "story must RE-SELECT on a discrimination metric, not inherit this.",
        },
    )

    n_in = model.n_features_in_
    if n_in != len(served_cols):
        raise SystemExit(f"❌ fitted model n_features_in_={n_in} != served_cols={len(served_cols)}; "
                         "this would fail the serve-time CONTRACT-GUARD.")

    # ── the serving-API smoke: predict_today calls EXACTLY this ────────────────────────────
    pd_out = model.pred_dist(Ximp.values[:8])
    assert set(pd_out.params) >= {"loc", "scale"}, "pred_dist must expose loc/scale"
    assert np.all(np.isfinite(pd_out.params["loc"])), "non-finite loc"
    assert len(np.unique(pd_out.params["scale"])) == 1, "homoscedastic σ must be constant"
    print(f"  pred_dist smoke OK · loc[:3]={np.round(pd_out.params['loc'][:3], 3).tolist()} "
          f"scale={pd_out.params['scale'][0]:.4f} (constant by construction)")

    contract_local = PROJECT_ROOT / "betting_ml" / "models" / SUBDIR / "feature_columns_mh2_1_total_runs_post_lineup.json"
    sidecar_local = PROJECT_ROOT / "betting_ml" / "models" / SUBDIR / "feature_columns_mh2_1_total_runs_post_lineup_served.json"
    base_name = "glm_elasticnet_plus_eb_mh2_1_post_lineup_2026"
    artifact_local = PROJECT_ROOT / "betting_ml" / "models" / SUBDIR / f"{base_name}.pkl"
    s3_uri = f"{S3_BUCKET}/{SUBDIR}/{base_name}.pkl"

    provenance = {
        "story": STORY,
        "derived": date.today().isoformat(),
        "model_class": "glm_elasticnet",
        "serving_wrapper": "betting_ml.utils.homoscedastic_regressor.HomoscedasticNormalRegressor",
        "tier": "post_lineup",
        "registry_target": "total_runs",
        "source_contract": BASE_CONTRACT,
        "variant": "plus_eb",
        "n_base": len(base), "n_plus_eb": len(adds),
        "n_contract": len(cols), "n_served": len(served_cols),
        "training_window": f"{args.min_year}+",
        "training_rows": int(len(df)),
        "config": GLM,
        "sigma_served": sigma,
        "sigma_oof_disclosure": sigma_oof,
        "best_alpha": BEST_ALPHA,
        "bullpen_v3_provenance": bp_prov,
        "smoke": args.smoke,
        "refresh_cache": args.refresh_cache,
        "method": "MH2.1 wide-window (2016–2026, 8 purged folds) pre-registered bake-off winner. "
                  "PointNormalSpec (homoscedastic Normal) persisted so the served object is the "
                  "validated object. PRICING/CALIBRATION promotion; best_alpha=0, no edge claim.",
    }
    contract_local.write_text(json.dumps(
        {"feature_cols": cols, "_provenance": provenance}, indent=2))
    sidecar_local.write_text(json.dumps(
        {"feature_cols": served_cols, "_provenance": provenance}, indent=2))
    joblib.dump(model, artifact_local)
    print(f"  saved model    → {artifact_local.relative_to(PROJECT_ROOT)}")
    print(f"  saved contract → {contract_local.relative_to(PROJECT_ROOT)}")
    print(f"  saved sidecar  → {sidecar_local.relative_to(PROJECT_ROOT)}")

    # ── PIN LANDMINE (2026-07-03): prove the artifact ROUND-TRIPS before anything is wired in ──
    reloaded = joblib.load(artifact_local)
    rt = reloaded.pred_dist(Ximp.values[:8])
    if not np.allclose(rt.params["loc"], pd_out.params["loc"]):
        raise SystemExit("❌ round-trip mismatch: the reloaded artifact does not reproduce loc.")
    if not np.isclose(rt.params["scale"][0], sigma):
        raise SystemExit("❌ round-trip mismatch: the reloaded artifact does not reproduce σ.")
    import sklearn
    print(f"  ✅ pickle round-trip OK under scikit-learn=={sklearn.__version__}, "
          f"joblib=={joblib.__version__} (re-fit if these pins move)")

    if args.no_upload or args.smoke:
        print("  [skip] S3 upload (--no-upload or --smoke).")
    else:
        upload_artifact(artifact_local, s3_uri)

    # ── SF champion-lineage (E9.26b) — what makes the swap VISIBLE in Admin → Model Freshness ──
    # That panel joins the SF `model_registry` ledger against the live served version; without a
    # row here it keeps naming the RETIRED v6 as the totals champion indefinitely. Idempotent and
    # NON-FATAL: the artifact is already uploaded, so a ledger failure must never fail the deploy.
    if not (args.no_upload or args.smoke or args.no_record_lineage):
        from betting_ml.utils.model_registry_tracker import record_promotion
        try:
            rec = record_promotion(
                target="total_runs",
                new_version="mh2_1",
                model_name="glm_elasticnet_plus_eb",
                artifact_path=s3_uri,
                feature_columns_path=f"betting_ml/models/{SUBDIR}/{sidecar_local.name}",
                features=int(len(served_cols)),
                training_rows=int(len(df)),
                training_cutoff=f"{args.min_year}+",
                # CRPS is what MH2.1 SELECTED on. Stamping the v6-era MAE here would record a
                # metric this promotion was never judged by (E2.1-r: pricing ≠ discrimination).
                cv_metric_name="crps_margin_vs_incumbent",
                cv_metric_value=0.0297,
                promoted_date=date.today().isoformat(),
                notes=(
                    "MH2.1 wide-window (2016-2026, 8 purged folds) champion, post_lineup. "
                    "LEARNER SWAP + FEATURE BLOCK (+0.0175 swap / +0.0122 plus_eb; neither clears "
                    "the 0.02 noise floor alone). Selected on PRICING: RMS |Var(z)-1| 0.050 vs the "
                    "retired v6's 0.158. Homoscedastic - pred_total_runs_scale is CONSTANT. "
                    "best_alpha=0, no edge claim; bet_paused stays true. Only 3 of 8 folds test "
                    "the served contract. pre_lineup remains v6 NGBoost."
                ),
            )
        except Exception as exc:  # noqa: BLE001 — upload already succeeded; never fail on lineage
            print(f"  ⚠️  LINEAGE record_promotion FAILED ({type(exc).__name__}: {exc}). The Admin "
                  "→ Model Freshness panel will keep showing v6 as the totals champion until this "
                  "is reconciled.")
        else:
            print("  ✓ SF champion-lineage: mh2_1 already current — no-op (idempotent)."
                  if rec.already_current else
                  f"  ✓ SF champion-lineage: recorded mh2_1 "
                  f"(deprecated {rec.deprecated_version or '(none)'}).")

    print("\n── model_registry.yaml (total_runs, post_lineup ONLY — pre_lineup UNTOUCHED) ──")
    print(f"  artifact_path: {s3_uri}")
    print(f"  feature_columns_path: betting_ml/models/{SUBDIR}/{sidecar_local.name}")
    print(f"  features: {len(served_cols)}")
    print("  dist: Normal   # homoscedastic — scale is CONSTANT across games")
    print("──────────────────────────────────────────────────────────────────────────────")


if __name__ == "__main__":
    main()
