"""fit_batter_tb.py — E5.9: fit + persist the served batter TOTAL-BASES champion.

Fits the Phase-2 SHIP_CANDIDATE recipe (`glm_nb`: Poisson-GLM mean + in-fold NB2 dispersion —
the arm that beat the Poisson foil 6/6 folds, CRPS 0.8631 vs 0.9026, PBO 0.0, DSR 0.9993) on
the FULL substrate and persists a versioned serving bundle. Every modelling function is
IMPORTED from the Phase-2 harness (`batter_props_phase2_bakeoff`): `build_design`,
`_fit_poisson_mu`, `fit_nb_alpha`, `nb_pmf_grid`, `NUMERIC_FEATURES`, `GRID_CAP` — so
research, fit, and serve share ONE implementation (train/serve consistency by construction;
the E7.9 check in `write_batter_tb_projections.py --consistency-check` proves the FEATURE
side against the live marts).

Market-blind (§5 of the pre-registration): the substrate's price columns never enter the
design matrix — `build_design` re-raises on any contract violation.

RETRAIN CADENCE (decided at ship, E5.9 — do not inherit the "42 days since fit" drift class):
MONTHLY during the regular season. The refit is seconds; the operator flow is
  1) rebuild the substrate:  uv run scripts/build_batter_prop_substrate.py            (LAPTOP, >2 min)
  2) refit + stage:          uv run python betting_ml/scripts/prop_pricing/fit_batter_tb.py
  3) promote to S3:          uv run python betting_ml/scripts/prop_pricing/fit_batter_tb.py --promote
The serving writer WARNs loudly when the served bundle's fit date is older than
STALE_AFTER_DAYS (45) so a lapsed cadence is visible, never silent.

USAGE
    # fit from the published substrate (default) and stage the local bundle:
    uv run python betting_ml/scripts/prop_pricing/fit_batter_tb.py

    # fit then upload the bundle to the serving S3 key (operator, post-merge):
    uv run python betting_ml/scripts/prop_pricing/fit_batter_tb.py --promote

Output: betting_ml/models/sub_models/prop_pricing_v1/batter_tb_glm_nb_v1.pkl (gitignored)
        → promoted to s3://baseball-betting-ml-artifacts/mlb/models/prop_pricing_v1/
"""

from __future__ import annotations

import argparse
import pickle
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from betting_ml.scripts.batter_props_phase2_bakeoff import (  # noqa: E402
    GRID_CAP,
    NUMERIC_FEATURES,
    build_design,
    crps_discrete,
    fit_nb_alpha,
    nb_pmf_grid,
)
from betting_ml.utils.tb_projection_serving import MODEL_VERSION  # noqa: E402

MARKET = "batter_total_bases"
SEED = 20260814  # the Phase-2 registered seed

DEFAULT_SUBSTRATE = (
    "s3://baseball-betting-ml-artifacts/baseball/research/batter_prop_substrate/"
    "batter_prop_substrate_v1.parquet"
)
BUNDLE_LOCAL = (Path(__file__).resolve().parents[3] / "betting_ml" / "models" / "sub_models"
                / "prop_pricing_v1" / f"{MODEL_VERSION}.pkl")
BUNDLE_S3 = f"s3://baseball-betting-ml-artifacts/mlb/models/prop_pricing_v1/{MODEL_VERSION}.pkl"

STALE_AFTER_DAYS = 45  # the writer WARNs past this — cadence is monthly, this is the slack


def fit_bundle(df: pd.DataFrame, substrate_path: str) -> dict:
    """Fit the champion on every labelled TB row and package the serving bundle.

    The bundle stores the DESIGN STATE (train medians / mean / std) as plain values so the
    serving writer reconstructs the exact standardization applied at fit time — imputing or
    scaling with anything else is the E7.9 train/serve-mismatch class."""
    d = df[(df["market_key"] == MARKET) & df["y_actual"].notna()].copy()
    if len(d) < 10_000:
        raise RuntimeError(f"substrate has only {len(d)} labelled TB rows — refusing to fit "
                           "a serving champion on a partial substrate")
    np.random.seed(SEED)
    X, design = build_design(d)
    y = d["y_actual"].to_numpy(float)
    # EXACTLY the harness `_fit_poisson_mu` configuration (pinned by
    # test_fit_batter_tb.py::test_fit_matches_harness_arm — a param drift goes red there).
    from sklearn.linear_model import PoissonRegressor
    model = PoissonRegressor(alpha=1e-4, max_iter=500, tol=1e-7)
    model.fit(X, y)
    mu = model.predict(X)
    alpha = fit_nb_alpha(y, mu)
    K = GRID_CAP[MARKET]
    # In-sample sanity read (NOT a selection metric — the OOS figures live in the bake-off
    # record): the fitted predictive's CRPS on the training rows.
    crps_in = float(np.mean(crps_discrete(nb_pmf_grid(mu, alpha, K), y)))
    train_start = str(pd.to_datetime(d["game_date"]).min().date())
    train_end = str(pd.to_datetime(d["game_date"]).max().date())
    return {
        "model_version": MODEL_VERSION,
        "market": MARKET,
        "model": model,
        "nb_alpha": float(alpha),
        "grid_cap": K,
        "features": list(NUMERIC_FEATURES),
        "design": {
            "medians": {k: (None if pd.isna(v) else float(v))
                        for k, v in design.medians.items()},
            "mean": [float(v) for v in design.mean],
            "std": [float(v) for v in design.std],
        },
        "fit": {
            "n_rows": int(len(d)),
            "train_start": train_start,
            "train_end": train_end,
            "substrate": substrate_path,
            "seed": SEED,
            "fitted_at": datetime.now(timezone.utc).isoformat(),
            "fit_date": datetime.now(timezone.utc).date().isoformat(),
            "crps_in_sample": round(crps_in, 5),
            "oos_reference": "ablation_results/mlb_batter_props_phase2_readout.md "
                             "(glm_nb OOS CRPS 0.8631 vs foil 0.9026, 6/6 folds)",
        },
        "refit_cadence_days": 30,
        "stale_after_days": STALE_AFTER_DAYS,
        "best_alpha": 0,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="E5.9 — fit the served batter-TB champion")
    ap.add_argument("--substrate", default=DEFAULT_SUBSTRATE)
    ap.add_argument("--out", default=str(BUNDLE_LOCAL))
    ap.add_argument("--promote", action="store_true",
                    help="After fitting, upload the bundle to the serving S3 key "
                         f"({BUNDLE_S3}). Operator step, post-merge.")
    args = ap.parse_args()

    print(f"[fit-batter-tb] loading substrate: {args.substrate}")
    df = pd.read_parquet(args.substrate)
    bundle = fit_bundle(df, args.substrate)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("wb") as fh:
        pickle.dump(bundle, fh)
    f = bundle["fit"]
    print(f"[fit-batter-tb] {bundle['model_version']}: {f['n_rows']} rows "
          f"({f['train_start']} → {f['train_end']}), nb_alpha={bundle['nb_alpha']:.4f}, "
          f"in-sample CRPS={f['crps_in_sample']}")
    print(f"[fit-batter-tb] staged → {out}")

    if args.promote:
        from betting_ml.utils.artifact_store import upload_artifact
        upload_artifact(out, BUNDLE_S3)
        print(f"[fit-batter-tb] promoted → {BUNDLE_S3}")
    else:
        print(f"[fit-batter-tb] NOT promoted (run with --promote to upload to {BUNDLE_S3})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
