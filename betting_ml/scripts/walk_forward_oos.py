"""
walk_forward_oos.py — Epic 10 (10.6 task 1, pulled forward to unblock 10.5)

Walk-forward OUT-OF-SAMPLE prediction plumbing for the Layer 3 totals model.

Why this exists
---------------
Story 10.4's calibration is IN-SAMPLE: `totals_v1`'s production artifact was refit
on all 2021–2026 data, so scoring those same games inflates ROI/Brier. A trustworthy
calibration (and a defensible 10.6 champion-vs-challenger promotion gate) needs each
game scored by a model trained ONLY on prior seasons.

`train_totals._cv_mean_negbin` already computes exactly these held-out fold
predictions (`mu_ev`, `r_ev`) — it just aggregates them into NLL/MAE and discards the
per-game values. This module re-runs that walk-forward loop and PERSISTS the per-game
held-out `(game_pk, season, oos_mu, oos_r)`, then attaches the Bovada line + actual to
build the OOS surface that 10.5 (alpha) and 10.6 (comparison) both consume.

Faithfulness: it reuses the champion's EXACT tuned hyperparameters, read straight out
of `totals_v1.pkl` (no re-tuning) — so the per-fold refits are the champion architecture
applied walk-forward. ~4 LightGBM fits, cheap.

Scope: the LAYER 3 totals model only. The monolithic NGBoost champion's OOS surface
(the other half of the 10.6 comparison) is NOT built here — it's a different training
path and per the model-retraining-deferral note each NGBoost refit is >1hr; 10.6 will
either add an NGBoost provider below or reuse the champion's live `daily_model_predictions`
history (which is already genuinely OOS). See `_oos_provider` extension point.

Output:
  betting_ml/models/layer3/oos_predictions_totals_v1.parquet
  ablation_results/totals_v1_oos_predictions.md   (per-fold OOS + OOS ECE/Brier)
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

import joblib  # noqa: E402

from betting_ml.scripts.load_layer3_features import build_totals_dataset  # noqa: E402
from betting_ml.utils.cv_splits import all_season_splits  # noqa: E402
from betting_ml.scripts.train_totals import (  # noqa: E402
    _MIN_TRAIN_SEASONS, _N_DECILES,
    _fit_lightgbm, _fit_ridge, fit_decile_r,
    _negbin_nll, _negbin_80pct_calibration,
)
from betting_ml.models.totals_negbin_model import assign_r, coerce_numeric  # noqa: E402
from betting_ml.utils.totals_probability import (  # noqa: E402
    compute_over_under_probs, devig_over_prob, compute_totals_edge,
)
from betting_ml.scripts.calibrate_totals_v1 import (  # noqa: E402
    reliability_table, expected_calibration_error, brier_score,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

_ARTIFACT_PATH = _PROJECT_ROOT / "betting_ml" / "models" / "sub_models" / "totals_v1.pkl"
_OOS_PARQUET = _PROJECT_ROOT / "betting_ml" / "models" / "layer3" / "oos_predictions_totals_v1.parquet"
_OOS_REPORT = _PROJECT_ROOT / "quant_sports_intel_models" / "baseball" / "ablation_results" / "totals_v1_oos_predictions.md"

_LGBM_TUNED_KEYS = ("n_estimators", "learning_rate", "num_leaves",
                    "min_child_samples", "subsample", "colsample_bytree")


# ---------------------------------------------------------------------------
# Champion hyperparameters — read from the saved artifact (no re-tuning)
# ---------------------------------------------------------------------------

def champion_params(artifact_path: Path = _ARTIFACT_PATH) -> tuple[str, dict]:
    """Extract (model_type, tuned params) from the finalized totals_v1 artifact.

    LightGBM → the tuned sklearn params; Ridge → {'alpha': ...} from the pipeline.
    This guarantees the walk-forward refits use the champion's exact configuration.
    """
    model = joblib.load(artifact_path)
    kind = model.model_type
    if kind == "lightgbm":
        all_p = model.mean_model.get_params()
        params = {k: all_p[k] for k in _LGBM_TUNED_KEYS if k in all_p}
    elif kind == "ridge":
        params = {"alpha": float(model.mean_model.named_steps["ridge"].alpha)}
    else:
        raise ValueError(f"Unsupported champion model_type: {kind!r}")
    log.info("Champion params from %s: kind=%s params=%s", artifact_path.name, kind, params)
    return kind, params


# ---------------------------------------------------------------------------
# Walk-forward OOS prediction (per-game held-out scoring)
# ---------------------------------------------------------------------------

def _fit_predict_fold(kind: str, params: dict, X_tr, y_tr, X_ev):
    """Fit the champion architecture on prior seasons, predict (mu, r) on the held-out season."""
    model = _fit_lightgbm(X_tr, y_tr, params) if kind == "lightgbm" else _fit_ridge(X_tr, y_tr, params["alpha"])
    mu_tr = np.clip(model.predict(X_tr), 1e-6, None)
    mu_ev = np.clip(model.predict(X_ev), 1e-6, None)
    edges, r_bin, g_r = fit_decile_r(y_tr, mu_tr, n_deciles=_N_DECILES)   # dispersion from TRAIN residuals only
    r_ev = assign_r(mu_ev, edges, r_bin, g_r)
    return mu_ev, r_ev


def generate_totals_oos(env: str = "prod", kind: str | None = None,
                        params: dict | None = None, drop_pattern: str | None = None) -> pd.DataFrame:
    """Walk-forward held-out predictions for the Layer 3 totals model.

    One row per game from the first held-out season onward (2021–22 are train-only
    under min_train_seasons=2). Returns: game_pk, season, oos_mu, oos_r, actual_total_runs.

    ``drop_pattern`` (e.g. "matchup") drops every X column containing that substring
    before the fold fits — a controlled ablation that reuses the champion's tuned
    hyperparameters so only the feature set changes (Story 10.6 follow-up).
    """
    if kind is None or params is None:
        kind, params = champion_params()

    X, y, _eval_lines, _report, meta = build_totals_dataset(env=env, return_meta=True)
    X = coerce_numeric(X)
    if drop_pattern:
        dropped = [c for c in X.columns if drop_pattern.lower() in c.lower()]
        X = X.drop(columns=dropped)
        log.info("Dropped %d '%s' columns → %d features remain: %s",
                 len(dropped), drop_pattern, X.shape[1], dropped)
    y_arr = y.to_numpy()

    folds = list(all_season_splits(meta, min_train_seasons=_MIN_TRAIN_SEASONS))
    if not folds:
        raise RuntimeError("No walk-forward folds — check the season span.")

    recs = []
    for tr_idx, ev_idx in folds:
        season = int(meta.loc[ev_idx, "game_year"].iloc[0])
        log.info("OOS fold: train n=%d -> hold out %d (n=%d)", len(tr_idx), season, len(ev_idx))
        mu_ev, r_ev = _fit_predict_fold(kind, params, X.loc[tr_idx], y_arr[tr_idx], X.loc[ev_idx])
        recs.append(pd.DataFrame({
            "game_pk": meta.loc[ev_idx, "game_pk"].to_numpy(),
            "season": season,
            "oos_mu": mu_ev,
            "oos_r": r_ev,
            "actual_total_runs": y_arr[ev_idx],
        }))
    oos = pd.concat(recs, ignore_index=True)
    log.info("Generated %d OOS predictions across %d seasons (%s)",
             len(oos), oos["season"].nunique(), sorted(oos["season"].unique()))
    return oos


def attach_lines_and_probs(oos: pd.DataFrame, env: str = "prod") -> pd.DataFrame:
    """Attach the Bovada line/prices and compute the OOS betting surface.

    Adds: bovada_line, total_line_source, over_price, under_price, oos_p_over,
    oos_p_under, oos_p_push, bovada_devig_over_prob, totals_edge, over_hit.
    `over_hit` is defined only on Bovada-line, non-push games.
    """
    from betting_ml.scripts.load_layer3_features import load_total_line_bovada
    lines = load_total_line_bovada(oos["game_pk"].astype(int).tolist(), env=env)
    df = oos.merge(lines.rename(columns={"total_line_bovada": "bovada_line"}), on="game_pk", how="left")

    p_over, p_under, p_push, devig, edge, over_hit = ([] for _ in range(6))
    for row in df.itertuples(index=False):
        line = getattr(row, "bovada_line", None)
        if pd.isna(line):
            p_over.append(np.nan); p_under.append(np.nan); p_push.append(np.nan)
            devig.append(np.nan); edge.append(np.nan); over_hit.append(np.nan)
            continue
        po, pu, pp = compute_over_under_probs(row.oos_mu, row.oos_r, line)
        p_over.append(po); p_under.append(pu); p_push.append(pp)
        op, up = getattr(row, "over_price", None), getattr(row, "under_price", None)
        if not pd.isna(op) and not pd.isna(up):
            dv = devig_over_prob(op, up)
            devig.append(dv); edge.append(compute_totals_edge(po, dv))
        else:
            devig.append(np.nan); edge.append(np.nan)
        actual = row.actual_total_runs
        over_hit.append(1.0 if actual > line else (0.0 if actual < line else np.nan))

    df["oos_p_over"] = p_over
    df["oos_p_under"] = p_under
    df["oos_p_push"] = p_push
    df["bovada_devig_over_prob"] = devig
    df["totals_edge"] = edge
    df["over_hit"] = over_hit
    return df


# ---------------------------------------------------------------------------
# Sanity report — per-fold OOS metrics + OOS ECE/Brier (the honest 10.4 read)
# ---------------------------------------------------------------------------

def _per_fold_metrics(oos: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for season, g in oos.groupby("season"):
        y = g["actual_total_runs"].to_numpy(float)
        mu = g["oos_mu"].to_numpy(float)
        r = float(np.mean(g["oos_r"].to_numpy(float)))
        rows.append({
            "season": int(season), "n": len(g),
            "oos_nll": round(_negbin_nll(y, mu, r), 4),
            "oos_mae": round(float(np.mean(np.abs(y - mu))), 4),
            "oos_calib_80": round(_negbin_80pct_calibration(y, mu, r), 4),
            "oos_std_pred": round(float(np.mean(np.sqrt(mu + mu ** 2 / max(r, 1e-6)))), 4),
        })
    return pd.DataFrame(rows)


def write_oos_report(oos_full: pd.DataFrame) -> None:
    fold = _per_fold_metrics(oos_full)
    cal = oos_full[(oos_full["total_line_source"] == "bovada")
                   & oos_full["oos_p_over"].notna() & oos_full["over_hit"].notna()].copy()
    p = cal["oos_p_over"].to_numpy(float)
    y = cal["over_hit"].to_numpy(float)
    ece = expected_calibration_error(p, y)
    brier = brier_score(p, y)
    brier_naive = brier_score(np.full_like(p, 0.5), y)
    bmask = cal["bovada_devig_over_prob"].notna().to_numpy()
    brier_bov = brier_score(cal.loc[bmask, "bovada_devig_over_prob"].to_numpy(float), y[bmask]) if bmask.any() else np.nan
    rel = reliability_table(p, y)

    brier_line = (f"- **OOS Brier:** {brier:.4f} vs naive-0.50 {brier_naive:.4f} "
                  f"({'beats' if brier < brier_naive else 'does NOT beat'} naive)")
    if not np.isnan(brier_bov):
        brier_line += (f" · vs Bovada de-vig {brier_bov:.4f} "
                       f"({'beats' if brier < brier_bov else 'does NOT beat'} Bovada)")

    lines = [
        "# Totals v1 — Walk-Forward OOS Predictions (10.6 task 1, unblocks 10.5)",
        "",
        f"- **OOS surface:** {len(oos_full)} games, seasons {sorted(int(s) for s in oos_full['season'].unique())} "
        f"(2021–22 train-only under min_train_seasons={_MIN_TRAIN_SEASONS}).",
        f"- **Bovada-line, settled calibration set:** {len(cal)}.",
        "- Each game scored by a model trained ONLY on prior seasons — this is the honest",
        "  out-of-sample surface 10.5 (alpha) and 10.6 (champion-vs-challenger) consume.",
        "",
        "## Per-fold OOS metrics (should track the champion in-sample CV ~NLL 2.78 / MAE 3.22 / calib 0.80)",
        fold.to_markdown(index=False),
        "",
        "## OOS calibration (the honest version of 10.4)",
        f"- **OOS ECE:** {ece:.4f}",
        brier_line,
        "",
        "### OOS reliability (10 bins)",
        rel.to_markdown(index=False, floatfmt=".4f"),
        "",
        "> This is a **sanity read**, not the promotion gate. The formal gate is Story 10.6,",
        "> which adds the NGBoost champion's OOS surface (built there or via its live",
        "> `daily_model_predictions` history) and applies the full champion-vs-challenger rubric.",
    ]
    _OOS_REPORT.parent.mkdir(parents=True, exist_ok=True)
    _OOS_REPORT.write_text("\n".join(lines) + "\n")
    log.info("Wrote OOS report → %s", _OOS_REPORT)
    log.info("OOS: ECE=%.4f Brier=%.4f (naive %.4f / bovada %s)",
             ece, brier, brier_naive, "n/a" if np.isnan(brier_bov) else f"{brier_bov:.4f}")


# ---------------------------------------------------------------------------
# Extension point — register additional model providers here for 10.6
# ---------------------------------------------------------------------------

def _oos_provider(name: str):
    """Provider registry for walk-forward OOS scoring (10.6 will add the NGBoost champion).

    A provider returns a callable(env) -> per-game OOS DataFrame with at least
    `game_pk, season, oos_mu, oos_r, actual_total_runs`. Only the Layer 3 totals
    provider is implemented now; the monolithic NGBoost champion is deferred to 10.6
    (different training path; refits are >1hr each, or reuse live prediction history).
    """
    if name in ("totals_v1", "layer3"):
        return generate_totals_oos
    raise NotImplementedError(
        f"OOS provider {name!r} not implemented. The NGBoost monolithic champion OOS "
        "surface is built in Story 10.6 (or sourced from its live daily_model_predictions)."
    )


def run(env: str = "prod", drop_pattern: str | None = None, out_tag: str | None = None) -> pd.DataFrame:
    oos = generate_totals_oos(env=env, drop_pattern=drop_pattern)
    oos_full = attach_lines_and_probs(oos, env=env)
    out_path = (_OOS_PARQUET.with_name(f"oos_predictions_totals_{out_tag}.parquet")
                if out_tag else _OOS_PARQUET)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    oos_full.to_parquet(out_path, index=False)
    log.info("Saved OOS predictions → %s (%d rows)", out_path, len(oos_full))
    if not out_tag:   # only refresh the canonical v1 report for the default run
        write_oos_report(oos_full)
    return oos_full


def main() -> None:
    p = argparse.ArgumentParser(description="Walk-forward OOS predictions for the Layer 3 totals model (Epic 10)")
    p.add_argument("--env", choices=["prod", "dev"], default="prod")
    p.add_argument("--drop-pattern", default=None,
                   help="drop X columns containing this substring (e.g. 'matchup') — controlled ablation")
    p.add_argument("--out-tag", default=None,
                   help="write to oos_predictions_totals_<tag>.parquet instead of the canonical v1 file")
    args = p.parse_args()
    run(env=args.env, drop_pattern=args.drop_pattern, out_tag=args.out_tag)


if __name__ == "__main__":
    main()
