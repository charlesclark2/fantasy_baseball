"""
quantile_totals_layer3_oos.py — Story 10.10 (Epic 10 REOPENED)

Quantile-regression-forest Layer-3 challenger for `total_runs`. Tests ONE hypothesis:

    Does dropping the NegBin log-link remove the §10 Jensen floor?

The NegBin champion's `exp(beta·z)` link forces E[total] = E[exp(beta·z + ...)] >
exp(beta·mu) by Jensen's inequality on the convex exp — at beta_bullpen≈0.172, σ_z≈1.0
this pins the predicted mean at ~8.87 > the 8.81 May-2026 kill threshold BEFORE any
signal moves it (the 8th-confirmation closure, §11 of totals_2026_failure_analysis.md).
A quantile model predicts the conditional quantiles of `total_runs` DIRECTLY (pinball
loss, no parameterization through exp) → there is no structural floor by construction.

What this script does
---------------------
1. Builds the canonical Layer-3 totals matrix (`build_totals_dataset` — completeness ≥
   0.40, leakage-validated, market-blind: the total line never enters X).
2. Walk-forward OOS: for each held-out season, fit 5 LightGBM quantile models
   (q=0.10,0.25,0.50,0.75,0.90) on PRIOR seasons only (no re-tuning — the 8.P approach,
   `quantile_forest` is not installed). This mirrors `walk_forward_oos.py` exactly so the
   2026 fold is the SAME leakage-free OOS surface 27.3 / evaluate_totals_bayesian use.
3. Derives P(over market line) DIRECTLY from the predictive quantiles via linear
   interpolation (`quantile_inference._interpolate_one`) — NO NegBin CDF, NO exp-link.
4. Reports, on the 2026 OOS surface ONLY (2023–25 Layer-3 is leakage-contaminated and is
   shown for context but EXCLUDED from the verdict):
     - May-2026 mean predicted total (q50) vs 8.81  — the headline Jensen-floor check.
     - calib_80 (empirical coverage of the [q10,q90] 80% PI), Brier vs market / naive.
     - A promote/defer verdict.

This is an HONEST verdict — no re-tuning to force a pass.

Run from project root (HAND-OFF, >1 min — ~20 LightGBM fits):
    uv run python betting_ml/scripts/quantile_totals_layer3_oos.py --env prod
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.scripts.load_layer3_features import (  # noqa: E402
    build_totals_dataset, load_total_line_bovada,
)
from betting_ml.utils.cv_splits import all_season_splits  # noqa: E402
from betting_ml.models.totals_negbin_model import coerce_numeric  # noqa: E402
from betting_ml.models.total_runs.quantile_inference import _interpolate_one  # noqa: E402
from betting_ml.utils.totals_probability import devig_over_prob  # noqa: E402
from betting_ml.scripts.calibrate_totals_v1 import brier_score  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

# Mirror walk_forward_oos.py: min_train_seasons=2 → eval folds 2023..2026.
_MIN_TRAIN_SEASONS = 2
_OOS_YEAR = 2026
# Pre-committed totals kill threshold (§11). The Jensen floor pins the log-link mean at
# ~8.87; a quantile model with no exp-link should NOT be structurally pinned ≥ this.
_KILL_THRESHOLD = 8.81

ALPHAS = [0.10, 0.25, 0.50, 0.75, 0.90]

# Same LightGBM quantile config as Story 8.P (no re-tuning — honest re-run under v4 gates).
_LGB_PARAMS = dict(
    objective="quantile",
    n_estimators=300,
    learning_rate=0.05,
    max_depth=5,
    num_leaves=31,
    n_jobs=-1,
    verbose=-1,
)

_OOS_PARQUET = _PROJECT_ROOT / "betting_ml" / "models" / "layer3" / "oos_predictions_totals_quantile_10_10.parquet"
_REPORT = _PROJECT_ROOT / "quant_sports_intel_models" / "baseball" / "ablation_results" / "totals_quantile_layer3_10_10.md"


# ---------------------------------------------------------------------------
# Walk-forward OOS quantile predictions
# ---------------------------------------------------------------------------

def _fit_predict_fold(X_tr: pd.DataFrame, y_tr: np.ndarray, X_ev: pd.DataFrame) -> dict[float, np.ndarray]:
    """Fit 5 quantile models on prior seasons, predict each quantile on the held-out season."""
    preds: dict[float, np.ndarray] = {}
    for alpha in ALPHAS:
        model = lgb.LGBMRegressor(alpha=alpha, **_LGB_PARAMS)
        model.fit(X_tr.values, y_tr)
        preds[alpha] = model.predict(X_ev.values)
    return preds


def generate_quantile_oos(env: str = "prod") -> pd.DataFrame:
    """Walk-forward held-out quantile predictions for the Layer-3 quantile challenger.

    One row per game from the first held-out season (2023) onward. Returns:
    game_pk, season, game_date, q10..q90, actual_total_runs.
    """
    X, y, _eval_lines, _report, meta = build_totals_dataset(env=env, return_meta=True)
    X = coerce_numeric(X)
    y_arr = y.to_numpy(float)

    folds = list(all_season_splits(meta, min_train_seasons=_MIN_TRAIN_SEASONS))
    if not folds:
        raise RuntimeError("No walk-forward folds — check the season span.")

    recs = []
    for tr_idx, ev_idx in folds:
        season = int(meta.loc[ev_idx, "game_year"].iloc[0])
        log.info("OOS fold: train n=%d -> hold out %d (n=%d)", len(tr_idx), season, len(ev_idx))
        qp = _fit_predict_fold(X.loc[tr_idx], y_arr[tr_idx], X.loc[ev_idx])
        rec = pd.DataFrame({
            "game_pk": meta.loc[ev_idx, "game_pk"].to_numpy(),
            "season": season,
            "game_date": pd.to_datetime(meta.loc[ev_idx, "game_date"].to_numpy()),
            "actual_total_runs": y_arr[ev_idx],
        })
        for a in ALPHAS:
            rec[f"q{int(a * 100):02d}"] = qp[a]
        recs.append(rec)

    oos = pd.concat(recs, ignore_index=True)
    # Enforce per-game quantile monotonicity (isotonic across the fitted levels) so the
    # interpolation is well-defined — independent per-quantile fits can cross occasionally.
    qcols = [f"q{int(a * 100):02d}" for a in ALPHAS]
    oos[qcols] = np.maximum.accumulate(oos[qcols].to_numpy(float), axis=1)
    log.info("Generated %d OOS quantile predictions across seasons %s",
             len(oos), sorted(oos["season"].unique()))
    return oos


def attach_lines_and_probs(oos: pd.DataFrame, env: str = "prod") -> pd.DataFrame:
    """Attach Bovada line/prices and derive P(over) DIRECTLY from the predictive quantiles.

    Adds: bovada_line, total_line_source, over_price, under_price, oos_p_over,
    bovada_devig_over_prob, over_hit. `over_hit` is defined only on Bovada-line,
    non-push games.
    """
    lines = load_total_line_bovada(oos["game_pk"].astype(int).tolist(), env=env)
    df = oos.merge(lines.rename(columns={"total_line_bovada": "bovada_line"}), on="game_pk", how="left")

    qcols = [f"q{int(a * 100):02d}" for a in ALPHAS]
    p_over, devig, over_hit = [], [], []
    for row in df.itertuples(index=False):
        line = getattr(row, "bovada_line", None)
        if pd.isna(line):
            p_over.append(np.nan); devig.append(np.nan); over_hit.append(np.nan)
            continue
        preds_i = [float(getattr(row, c)) for c in qcols]
        # P(over line) = 1 - P(under line) from the interpolated predictive CDF (no exp-link).
        p_over.append(_interpolate_one(preds_i, ALPHAS, float(line)))
        op, up = getattr(row, "over_price", None), getattr(row, "under_price", None)
        devig.append(devig_over_prob(op, up) if not (pd.isna(op) or pd.isna(up)) else np.nan)
        actual = row.actual_total_runs
        over_hit.append(1.0 if actual > line else (0.0 if actual < line else np.nan))

    df["oos_p_over"] = p_over
    df["bovada_devig_over_prob"] = devig
    df["over_hit"] = over_hit
    return df


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def _season_metrics(g: pd.DataFrame) -> dict:
    """Distributional + betting metrics for one season slice (q-cols present)."""
    y = g["actual_total_runs"].to_numpy(float)
    q10 = g["q10"].to_numpy(float)
    q50 = g["q50"].to_numpy(float)
    q90 = g["q90"].to_numpy(float)
    # calib_80 = empirical coverage of the [q10,q90] central 80% predictive interval.
    calib_80 = float(np.mean((y >= q10) & (y <= q90)))
    cal = g[(g["total_line_source"] == "bovada") & g["oos_p_over"].notna()
            & g["over_hit"].notna() & g["bovada_devig_over_prob"].notna()]
    out = {
        "n": len(g),
        "mean_q50": float(np.mean(q50)),
        "mean_actual": float(np.mean(y)),
        "mae_q50": float(np.mean(np.abs(q50 - y))),
        "mean_resid_q50": float(np.mean(q50 - y)),
        "std_q50": float(np.std(q50)),
        "calib_80": calib_80,
        "pi80_width": float(np.mean(q90 - q10)),
        "n_settled": len(cal),
    }
    if len(cal):
        p = cal["oos_p_over"].to_numpy(float)
        dv = cal["bovada_devig_over_prob"].to_numpy(float)
        oh = cal["over_hit"].to_numpy(float)
        out.update({
            "brier_model": brier_score(p, oh),
            "brier_market": brier_score(dv, oh),
            "brier_naive": brier_score(np.full_like(p, 0.5), oh),
            "mean_p_over": float(np.mean(p)),
            "actual_over_rate": float(np.mean(oh)),
        })
    return out


def evaluate(oos: pd.DataFrame) -> dict:
    per_season = {int(s): _season_metrics(g) for s, g in oos.groupby("season")}

    oos26 = oos[oos["season"] == _OOS_YEAR].copy()
    may26 = oos26[oos26["game_date"].dt.month == 5]
    may_mean_q50 = float(np.mean(may26["q50"].to_numpy(float))) if len(may26) else float("nan")
    may_mean_actual = float(np.mean(may26["actual_total_runs"].to_numpy(float))) if len(may26) else float("nan")

    return {
        "per_season": per_season,
        "oos26": per_season.get(_OOS_YEAR, {}),
        "may26_n": int(len(may26)),
        "may26_mean_q50": may_mean_q50,
        "may26_mean_actual": may_mean_actual,
    }


# ---------------------------------------------------------------------------
# Verdict + report
# ---------------------------------------------------------------------------

def verdict(R: dict) -> dict:
    may_q50 = R["may26_mean_q50"]
    o26 = R["oos26"]
    floor_removed = bool(may_q50 <= _KILL_THRESHOLD)
    kill_pass = floor_removed  # May-2026 PPM ≤ 8.81 is the pre-committed kill criterion
    calib_ok = bool(0.75 <= o26.get("calib_80", 0.0) <= 0.85)
    beats_market = bool(o26.get("brier_model", np.inf) < o26.get("brier_market", np.inf))
    beats_naive = bool(o26.get("brier_model", np.inf) < o26.get("brier_naive", np.inf))
    # Promote requires clearing the kill criterion AND beating the market on the deployable
    # number. Anything short is DEFER (the totals book stays paused — §11).
    promote = kill_pass and calib_ok and beats_market
    return {
        "floor_removed": floor_removed,
        "kill_pass": kill_pass,
        "calib_ok": calib_ok,
        "beats_market": beats_market,
        "beats_naive": beats_naive,
        "decision": "PROMOTE" if promote else "DEFER",
    }


def _b(x: bool) -> str:
    return "✅" if x else "❌"


def write_report(R: dict, V: dict) -> None:
    o26 = R["oos26"]
    may_q50 = R["may26_mean_q50"]
    floor_line = (
        f"**Jensen floor REMOVED** — the quantile model's May-2026 mean predicted total "
        f"({may_q50:.4f}) is **below** the 8.81 threshold and tracks the league actual "
        f"({R['may26_mean_actual']:.4f}), not pinned ≥8.87 like the log-link champion."
        if V["floor_removed"] else
        f"**Jensen floor NOT the binding constraint** — the quantile model has no exp-link, "
        f"yet its May-2026 mean predicted total ({may_q50:.4f}) is still "
        f"{'above' if may_q50 > _KILL_THRESHOLD else 'at'} 8.81 "
        f"(actual {R['may26_mean_actual']:.4f}). Removing the log-link did not, on its own, "
        f"clear the kill criterion."
    )

    # Per-season context table (2023–25 leakage-contaminated; 2026 = honest verdict surface).
    rows = ["| Season | n | mean q50 | mean actual | MAE(q50) | calib_80 | PI80 width | Brier model | Brier market |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for s in sorted(R["per_season"]):
        m = R["per_season"][s]
        tag = " *(OOS verdict)*" if s == _OOS_YEAR else " *(leakage-contam.)*"
        bm = f"{m.get('brier_model', float('nan')):.4f}" if "brier_model" in m else "—"
        bk = f"{m.get('brier_market', float('nan')):.4f}" if "brier_market" in m else "—"
        rows.append(
            f"| {s}{tag} | {m['n']} | {m['mean_q50']:.3f} | {m['mean_actual']:.3f} | "
            f"{m['mae_q50']:.3f} | {m['calib_80']:.3f} | {m['pi80_width']:.3f} | {bm} | {bk} |"
        )

    lines = [
        "# Story 10.10 — Quantile-Regression Layer-3 Challenger (Totals)",
        "",
        "**Hypothesis tested:** does dropping the NegBin `exp(β·z)` log-link remove the §10 "
        "Jensen floor (β_bullpen≈0.172 → predicted mean pinned ≥8.87 > 8.81 before any signal)?",
        "",
        "A LightGBM quantile-regression model (q=0.10/0.25/0.50/0.75/0.90, pinball loss) predicts "
        "the conditional quantiles of `total_runs` directly — no `exp()` parameterization, so no "
        "structural floor by construction. Trained walk-forward on the Layer-3 matrix "
        "(`build_totals_dataset`, completeness ≥0.40, market-blind); P(over) interpolated DIRECTLY "
        "from the predictive quantiles (no NegBin CDF). Same 2026 leakage-free OOS surface as 27.3.",
        "",
        "## HEADLINE — kill criterion first (May-2026 mean predicted total vs 8.81)",
        "",
        f"- **May-2026 mean predicted total (q50): {may_q50:.4f}** (n={R['may26_n']}); "
        f"threshold ≤ 8.81 → **{'PASS' if V['kill_pass'] else 'FAIL'}**.",
        f"- May-2026 actual mean total: {R['may26_mean_actual']:.4f}.",
        f"- {floor_line}",
        "",
        "## 2026 OOS surface (the only leakage-free verdict surface)",
        "",
        f"- Games: {o26.get('n', 0)} (settled Bovada-line: {o26.get('n_settled', 0)}).",
        f"- **calib_80** (empirical [q10,q90] coverage): **{o26.get('calib_80', float('nan')):.4f}** "
        f"(nominal 0.80, gate 0.75–0.85) → {_b(V['calib_ok'])}.",
        f"- Mean 80% PI width: {o26.get('pi80_width', float('nan')):.3f} runs.",
        f"- MAE(q50): {o26.get('mae_q50', float('nan')):.4f} · mean residual: {o26.get('mean_resid_q50', float('nan')):+.4f} · std(q50): {o26.get('std_q50', float('nan')):.4f}.",
        f"- **Brier vs market:** model **{o26.get('brier_model', float('nan')):.4f}** vs Bovada de-vig "
        f"**{o26.get('brier_market', float('nan')):.4f}** vs naive-0.50 {o26.get('brier_naive', float('nan')):.4f} "
        f"→ beats market {_b(V['beats_market'])}, beats naive {_b(V['beats_naive'])}.",
        f"- Mean P(over): {o26.get('mean_p_over', float('nan')):.3f} · actual over-rate: {o26.get('actual_over_rate', float('nan')):.3f}.",
        "",
        "## Per-season walk-forward (2023–25 are leakage-CONTAMINATED — context only, NOT the verdict)",
        "",
        *rows,
        "",
        "## Decision gates",
        "",
        "| Gate | Result |",
        "|---|:--:|",
        f"| Kill criterion: May-2026 mean q50 ≤ 8.81 | {_b(V['kill_pass'])} |",
        f"| calib_80 ∈ [0.75, 0.85] | {_b(V['calib_ok'])} |",
        f"| Brier(P_over) < market | {_b(V['beats_market'])} |",
        f"| Brier(P_over) < naive-0.50 | {_b(V['beats_naive'])} |",
        "",
        f"## VERDICT: **{V['decision']}**",
        "",
        (
            "The quantile model clears the kill criterion AND beats the market on the deployable "
            "number — promote to a shadow window and re-confirm before any live totals deployment."
            if V["decision"] == "PROMOTE" else
            "The quantile model does NOT clear the bar to un-pause totals. "
            + ("Even with the log-link removed, the May-2026 mean still exceeds 8.81 — the OVER bias is "
               "NOT purely a Jensen artifact of the exp-link; it reflects a real 2026 OOS scoring-environment "
               "shift the covariates cannot price (consistent with the §11 8th-confirmation finding)."
               if not V["floor_removed"] else
               "The Jensen floor IS removed (May-2026 mean ≤ 8.81), but the model does not beat the market "
               "on the 2026 OOS Brier — removing the structural floor is necessary but not sufficient; the "
               "covariates still add no deployable edge over Bovada. Totals stays paused (§11).")
            + " No re-tuning to force a pass."
        ),
        "",
        "_Leakage guard: the verdict is computed on the 2026 OOS surface ONLY; 2023–25 Layer-3 "
        "predictions are contaminated by in-sample sub-model signal leakage and are shown for context only._",
        "",
    ]
    _REPORT.parent.mkdir(parents=True, exist_ok=True)
    _REPORT.write_text("\n".join(lines) + "\n")
    log.info("Wrote report → %s", _REPORT)


def run(env: str = "prod") -> dict:
    oos = generate_quantile_oos(env=env)
    oos = attach_lines_and_probs(oos, env=env)
    _OOS_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    oos.to_parquet(_OOS_PARQUET, index=False)
    log.info("Saved OOS quantile predictions → %s (%d rows)", _OOS_PARQUET, len(oos))

    R = evaluate(oos)
    V = verdict(R)
    write_report(R, V)

    o26 = R["oos26"]
    print("\n" + "=" * 72)
    print("STORY 10.10 — QUANTILE LAYER-3 CHALLENGER (TOTALS)")
    print("=" * 72)
    print(f"HEADLINE  May-2026 mean q50 = {R['may26_mean_q50']:.4f}  (threshold ≤ 8.81 → "
          f"{'PASS' if V['kill_pass'] else 'FAIL'}; actual {R['may26_mean_actual']:.4f})")
    print(f"          Jensen log-link floor removed: {V['floor_removed']}")
    print(f"2026 OOS  calib_80={o26.get('calib_80', float('nan')):.4f}  "
          f"Brier model={o26.get('brier_model', float('nan')):.4f} "
          f"vs market={o26.get('brier_market', float('nan')):.4f} "
          f"vs naive={o26.get('brier_naive', float('nan')):.4f}")
    print(f"VERDICT   {V['decision']}")
    print("=" * 72)
    return {"R": R, "V": V}


def main() -> None:
    p = argparse.ArgumentParser(description="Story 10.10 — quantile Layer-3 totals challenger (walk-forward OOS)")
    p.add_argument("--env", choices=["prod", "dev"], default="prod")
    args = p.parse_args()
    run(env=args.env)


if __name__ == "__main__":
    main()
