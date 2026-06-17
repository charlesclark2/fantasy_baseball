"""train_bayesian_meta_model.py — Story 12.4: Bayesian sequential CLV meta-model (v0).

The first working market-meta model. A Bayesian logistic regression that, for a game
scored at MORNING (market-blind, pre-lineup), estimates P(CLV > 0) — the probability the
closing line moves TOWARD the side the morning model favored — with an 80% credible
interval. The CI width is the trust signal: it narrows as live games accumulate.

WHY THIS FEATURE SET (and not the 8-feature spec wishlist):
  The original 12.4 spec assumed conviction score, gate-signals, win-prob CI width, Epic-16
  posteriors and a Bovada-vs-Pinnacle sharp signal. Empirically (2026-06-16), on the
  validated morning population ALL of those are NULL at morning — they are post-lineup /
  Layer-4 artifacts not written on the live morning row — and the Pinnacle sharp signal was
  separately killed in Story 12.10' (no incremental CLV lift, OPEN lift +0.0095 < +0.01).
  So the honest morning meta-model uses only what is actually present and pre-test-validated:

    edge_mag      = |centered morning H2H edge|       primary signal (pre-test: bigger edge →
                                                       more reliable CLV; monotone by quintile)
    pub_align     = handle_ticket_div * sign(edge)    does public sharp money sit on our side?
                    (AN money% − ticket%; 98% coverage)   (spec β_public_fade — sign learned)
    open_extremity= |open_home_win_prob − 0.5|        mean-reversion control: extreme opens
                                                       revert regardless of our edge

POPULATION (reuses the proven 12.4 pre-test surface — NOT the empty prod meta-model mart):
  earliest LIVE morning prediction per 2026 game (is_backfill=false)
    ⋈ mart_odds_line_movement (Bovada, snapshot_count>1, open→close).
  LABEL clv_positive (moved games only, h2h_line_movement≠0): sign(centered edge)==sign(move).

The morning predictions were generated live each day → the edge↔movement signal is genuinely
OOS (pre-test established it). This model CALIBRATES that signal into P(CLV>0)+CI; the 12.4
convergence gates are in-sample (MCMC convergence + CI width + quartile separation), which is
correct for a sequential model. A temporal-split frequentist AUC is reported as an honest
generalization sanity check (not a gate).

Convergence gates (spec):
  1. max R-hat < 1.01 (MCMC converged)            [AC: < 1.05 at n=50; we have ~900]
  2. mean(meta_ci_width) < 0.25 (confident enough to be useful)
  3. top-quartile minus bottom-quartile actual CLV+ rate ≥ 0.05 (separation)

Outputs:
  betting_ml/models/meta_model/bayesian_meta_trace_{n}.nc      (arviz trace)
  betting_ml/models/meta_model/meta_model_scaler_{n}.json      (feature spec + standardization)
  quant_sports_intel_models/baseball/ablation_results/bayesian_meta_model_12_4.md

Run (hand-off — Snowflake + NUTS, ~1 min):
    uv run python betting_ml/scripts/train_bayesian_meta_model.py
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from betting_ml.utils.data_loader import get_snowflake_connection  # noqa: E402

_MODELS = PROJECT_ROOT / "betting_ml" / "models" / "meta_model"
_OUT = (PROJECT_ROOT / "quant_sports_intel_models" / "baseball"
        / "ablation_results" / "bayesian_meta_model_12_4.md")

FEATURES = ["edge_mag", "pub_align", "open_extremity"]
DRAWS, TUNE, CHAINS, TARGET_ACCEPT, SEED = 1000, 1000, 4, 0.9, 124

_SQL = """
with morn as (
  select game_pk, game_date,
         coalesce(calibrated_win_prob, consensus_win_prob, h2h_posterior_prob) as model_home_prob
  from baseball_data.betting_ml.daily_model_predictions
  where prediction_type='morning' and coalesce(is_backfill,false)=false
    and date_part('year', game_date)=2026
  qualify row_number() over (partition by game_pk order by inserted_at asc)=1
),
pb as (
  select game_pk, home_ml_money_pct - home_ml_ticket_pct as handle_ticket_div
  from baseball_data.betting_features.feature_pregame_public_betting_features
)
select
  mv.game_pk, morn.game_date, mv.data_source,
  morn.model_home_prob, mv.open_home_win_prob, mv.h2h_line_movement,
  pb.handle_ticket_div
from baseball_data.betting.mart_odds_line_movement mv
join morn on morn.game_pk = mv.game_pk
left join pb on pb.game_pk = mv.game_pk
where mv.snapshot_count > 1
"""


def _load() -> pd.DataFrame:
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(_SQL)
        df = cur.fetch_pandas_all()
    finally:
        conn.close()
    df.columns = [c.lower() for c in df.columns]

    df["h2h_edge"] = df["model_home_prob"] - df["open_home_win_prob"]
    # Center the edge to remove the constant vig bias (open_home_win_prob carries vig;
    # the mart stores only the home implied prob so a true de-vig isn't possible). The
    # median is the de-bias anchor used by the pre-test directional-hit metric. It is a
    # TRAINING statistic — persisted in the scaler so serve-time centering matches.
    df.attrs["edge_median"] = float(df["h2h_edge"].median())
    edge_c = df["h2h_edge"] - df.attrs["edge_median"]
    df["edge_signed"] = edge_c
    df["model_side"] = np.sign(edge_c)                       # +1 home, -1 away
    df["edge_mag"] = edge_c.abs()
    df["handle_ticket_div"] = df["handle_ticket_div"].fillna(0.0)  # missing AN = neutral
    df["pub_align"] = df["handle_ticket_div"] * df["model_side"]
    df["open_extremity"] = (df["open_home_win_prob"] - 0.5).abs()

    # Label: did the close move toward our side? Defined on moved games only.
    df["moved"] = df["h2h_line_movement"] != 0
    df["clv_positive"] = (np.sign(df["h2h_line_movement"]) == df["model_side"]).astype(int)
    return df


def _standardize(X: pd.DataFrame) -> tuple[np.ndarray, dict]:
    mu = X.mean()
    sd = X.std(ddof=0).replace(0, 1.0)
    Z = ((X - mu) / sd).to_numpy(float)
    scaler = {"features": FEATURES, "mean": mu.to_dict(), "std": sd.to_dict()}
    return Z, scaler


def _posterior_logits(trace, Z: np.ndarray) -> np.ndarray:
    """Return an (n_samples, n_games) matrix of logit draws."""
    post = trace.posterior
    b0 = post["b0"].values.reshape(-1)                       # (S,)
    betas = np.stack([post[f"b_{f}"].values.reshape(-1) for f in FEATURES], axis=1)  # (S,F)
    return b0[:, None] + betas @ Z.T                         # (S, n_games)


_S3_BASE = "s3://baseball-betting-ml-artifacts/meta_model"


def _convergence_action(max_rhat: float) -> str:
    """Epic O.5 convergence gate on the weekly retrain.

    Returns 'fail' (R-hat > 1.10 → block the S3 upload so serving keeps the last-good
    trace, and exit non-zero so the Dagster alert fires), 'warn' (R-hat > 1.05 →
    upload but flag for review), or 'ok'.
    """
    if max_rhat > 1.10:
        return "fail"
    if max_rhat > 1.05:
        return "warn"
    return "ok"


def _upload_to_s3(trace_path: Path, scaler_path: Path, summary_path: Path, n: int) -> None:
    """Upload the freshly-written trace + scaler + latest-summary to S3 (Epic O.5).

    The per-n trace/scaler are immutable history; `meta_model_latest.json` is the
    stable pointer the weekly job (and any serve-side S3 pull) reads for the newest n.
    """
    from betting_ml.utils.artifact_store import upload_artifact
    upload_artifact(trace_path, f"{_S3_BASE}/{trace_path.name}")
    upload_artifact(scaler_path, f"{_S3_BASE}/{scaler_path.name}")
    upload_artifact(summary_path, f"{_S3_BASE}/meta_model_latest.json")
    print(f"Uploaded trace+scaler+summary (n={n}) → {_S3_BASE}/")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Train the Bayesian CLV meta-model (Story 12.4); weekly retrain via Epic O.5.")
    parser.add_argument("--s3-upload", action="store_true",
                        help="After writing locally, upload trace+scaler+summary to "
                             f"{_S3_BASE}/. Used by the weekly Dagster job (Epic O.5).")
    parser.add_argument("--min-games", type=int, default=50,
                        help="Epic O.5 count gate: if the moved-game training population is "
                             "below this, skip MCMC and exit 0 (never fail below threshold).")
    args = parser.parse_args()

    import pymc as pm
    import arviz as az
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    from sklearn.preprocessing import StandardScaler

    _MODELS.mkdir(parents=True, exist_ok=True)
    _OUT.parent.mkdir(parents=True, exist_ok=True)

    raw = _load()
    df = raw[raw["moved"]].dropna(subset=FEATURES + ["clv_positive"]).copy()
    df = df.sort_values("game_date").reset_index(drop=True)
    n = len(df)
    base_rate = float(df["clv_positive"].mean())
    print(f"Loaded {len(raw)} paired games; {n} moved (label base CLV+ rate {base_rate:.3f}); "
          f"{len(raw) - len(raw[raw['moved']])} flat dropped.")

    # Epic O.5 count gate — never fail below threshold (the weekly Dagster op stays green
    # until enough live CLV labels accrue). Gated on the trainer's ACTUAL training
    # population (moved live-morning games), NOT mart_clv_labeled_games — the 12.4 surface
    # is daily_model_predictions ⋈ mart_odds_line_movement (the contaminated backfill mart
    # is deliberately bypassed; see Story 12.4 notes).
    if n < args.min_games:
        print(f"Insufficient CLV labels ({n}/{args.min_games}) — skipping MCMC.")
        return

    Z, scaler = _standardize(df[FEATURES])
    y = df["clv_positive"].to_numpy(int)

    # ── Bayesian logistic regression ──────────────────────────────────────────────
    # Weakly-informative priors: data (~900 games) dominates. Intercept centered on the
    # known ~0.60 base agreement; β_edge weakly positive (pre-test); others ~0, sign learned.
    with pm.Model() as model:
        b0 = pm.Normal("b0", mu=float(np.log(base_rate / (1 - base_rate))), sigma=0.5)
        b_edge = pm.Normal("b_edge_mag", mu=0.4, sigma=0.5)
        b_pub = pm.Normal("b_pub_align", mu=0.0, sigma=0.4)
        b_open = pm.Normal("b_open_extremity", mu=0.0, sigma=0.4)
        logit_p = (b0
                   + b_edge * Z[:, 0]
                   + b_pub * Z[:, 1]
                   + b_open * Z[:, 2])
        pm.Bernoulli("clv_obs", logit_p=logit_p, observed=y)
        trace = pm.sample(draws=DRAWS, tune=TUNE, chains=CHAINS, target_accept=TARGET_ACCEPT,
                          random_seed=SEED, progressbar=False)

    summary = az.summary(trace, var_names=["b0", "b_edge_mag", "b_pub_align", "b_open_extremity"])
    max_rhat = float(summary["r_hat"].max())

    # ── Per-game posterior P(CLV>0) + 80% CI ──────────────────────────────────────
    logits = _posterior_logits(trace, Z)                     # (S, n_games)
    p_samples = 1.0 / (1.0 + np.exp(-logits))
    meta_p = p_samples.mean(axis=0)
    ci_low = np.percentile(p_samples, 10, axis=0)
    ci_high = np.percentile(p_samples, 90, axis=0)
    ci_width = ci_high - ci_low
    mean_ci_width = float(ci_width.mean())

    # ── Gate 3: top vs bottom quartile actual CLV+ rate separation ────────────────
    q_hi = np.quantile(meta_p, 0.75)
    q_lo = np.quantile(meta_p, 0.25)
    top_rate = float(y[meta_p >= q_hi].mean())
    bot_rate = float(y[meta_p <= q_lo].mean())
    quartile_spread = top_rate - bot_rate

    in_auc = float(roc_auc_score(y, meta_p))

    # ── Honesty check: temporal-split frequentist AUC (train early, test late) ─────
    cut = int(n * 0.7)
    sc = StandardScaler().fit(df[FEATURES].iloc[:cut])
    lr = LogisticRegression(max_iter=1000).fit(sc.transform(df[FEATURES].iloc[:cut]), y[:cut])
    test_p = lr.predict_proba(sc.transform(df[FEATURES].iloc[cut:]))[:, 1]
    temporal_auc = (float(roc_auc_score(y[cut:], test_p))
                    if len(np.unique(y[cut:])) > 1 else float("nan"))

    gate1 = max_rhat < 1.01
    gate2 = mean_ci_width < 0.25
    gate3 = quartile_spread >= 0.05
    all_pass = gate1 and gate2 and gate3

    # ── Persist trace + scaler ─────────────────────────────────────────────────────
    trace_path = _MODELS / f"bayesian_meta_trace_{n:04d}.nc"
    trace.to_netcdf(str(trace_path))
    scaler["n_games"] = n
    scaler["base_rate"] = base_rate
    scaler["edge_median"] = df.attrs["edge_median"]
    scaler_path = _MODELS / f"meta_model_scaler_{n:04d}.json"
    scaler_path.write_text(json.dumps(scaler, indent=2))

    # ── Latest-summary sidecar (Epic O.5) ───────────────────────────────────────────
    # Stable-key JSON the weekly Dagster op reads for run metadata (n_games / mean_ci_width
    # / max_rhat) without opening the .nc, and the pointer to the newest n.
    summary = {
        "n_games": n,
        "mean_ci_width": round(mean_ci_width, 4),
        "max_rhat": round(max_rhat, 4),
        "quartile_spread": round(quartile_spread, 4),
        "in_sample_auc": round(in_auc, 4),
        "gates": {"rhat": gate1, "ci_width": gate2, "quartile": gate3, "all_pass": all_pass},
        "trace_file": trace_path.name,
        "scaler_file": scaler_path.name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    summary_path = _MODELS / "meta_model_latest.json"
    summary_path.write_text(json.dumps(summary, indent=2))

    # ── Report ─────────────────────────────────────────────────────────────────────
    # Coefficient mean + 94% central credible interval straight from posterior samples
    # (robust to arviz version differences in az.summary HDI column names).
    post = trace.posterior

    def _coef(name: str) -> list[float]:
        s = post[name].values.reshape(-1)
        return [round(float(s.mean()), 3),
                round(float(np.percentile(s, 3)), 3),
                round(float(np.percentile(s, 97)), 3)]

    coef = {name: _coef(name) for name in ["b0", "b_edge_mag", "b_pub_align", "b_open_extremity"]}
    L = [
        "# Story 12.4 — Bayesian sequential CLV meta-model (v0)", "",
        f"**Population:** {n} moved 2026 live-morning games ⋈ Bovada open→close movement "
        f"(snapshot_count>1; {len(raw)} paired, flat dropped). Label CLV+ = close moved toward "
        f"the morning model's side; base rate **{base_rate:.3f}**.",
        "",
        "**Honest feature set** (spec's conviction / gate-signals / CI-width / Epic-16 posteriors "
        "are NULL at morning; Pinnacle killed in 12.10′):",
        "- `edge_mag` = |centered morning H2H edge| — primary signal",
        "- `pub_align` = AN (money%−ticket%) × model_side — public sharp money on our side",
        "- `open_extremity` = |open_home_win_prob − 0.5| — mean-reversion control",
        "",
        "## Convergence gates",
        f"| Gate | Value | Threshold | Pass |",
        f"|---|---|---|---|",
        f"| 1. max R-hat | {max_rhat:.4f} | < 1.01 | {'✅' if gate1 else '❌'} |",
        f"| 2. mean CI width | {mean_ci_width:.4f} | < 0.25 | {'✅' if gate2 else '❌'} |",
        f"| 3. top−bottom quartile CLV+ rate | {quartile_spread:+.4f} ({top_rate:.3f} vs {bot_rate:.3f}) | ≥ 0.05 | {'✅' if gate3 else '❌'} |",
        "",
        f"**Verdict: {'✅ ALL GATES PASS — v0 converged' if all_pass else '⚠️ NOT ALL GATES PASS'}** "
        f"(in-sample AUC {in_auc:.3f}; temporal-split freq. AUC {temporal_auc:.3f} — honest "
        f"generalization sanity, not a gate).",
        "",
        "## Coefficient posteriors (mean [94% credible interval], standardized features)",
    ]
    for r, v in coef.items():
        L.append(f"- `{r}` = **{v[0]:+.3f}** [{v[1]:+.3f}, {v[2]:+.3f}]")
    L += [
        "",
        "## Notes",
        f"- Trace: `betting_ml/models/meta_model/bayesian_meta_trace_{n:04d}.nc`; "
        f"scaler/feature-spec sidecar `meta_model_scaler_{n:04d}.json`.",
        "- In-sample gates are correct for a sequential model (the edge↔CLV signal is already "
        "OOS-validated by the pre-test); the temporal-split AUC guards against an in-sample mirage.",
        "- Deferred to integration (overlaps 12.5): Dagster weekly asset, predict_today columns, "
        "Streamlit posterior plots, MLflow CI-width tracker, S3 weekly traces, 2-week convergence confirm.",
    ]
    _OUT.write_text("\n".join(L) + "\n")

    print("\n".join([
        "", f"max R-hat        = {max_rhat:.4f}  (gate <1.01: {'PASS' if gate1 else 'FAIL'})",
        f"mean CI width    = {mean_ci_width:.4f}  (gate <0.25: {'PASS' if gate2 else 'FAIL'})",
        f"quartile spread  = {quartile_spread:+.4f}  (gate ≥0.05: {'PASS' if gate3 else 'FAIL'})",
        f"in-sample AUC    = {in_auc:.3f}",
        f"temporal AUC     = {temporal_auc:.3f}",
        f"coefficients     = " + ", ".join(f"{k}={v[0]:+.3f}" for k, v in coef.items()),
        f"\nVERDICT: {'ALL GATES PASS' if all_pass else 'NOT ALL GATES PASS'}",
        f"Report  → {_OUT}",
        f"Trace   → {trace_path}",
    ]))

    # ── Epic O.5: convergence gate + optional S3 upload ─────────────────────────────
    action = _convergence_action(max_rhat)
    if action == "fail":
        print(f"FAILURE: max R-hat {max_rhat:.4f} > 1.10 — trace NOT uploaded; serving keeps "
              f"the last-good trace. Exiting non-zero so the Dagster alert fires.")
        sys.exit(1)
    if action == "warn":
        print(f"WARNING: max R-hat {max_rhat:.4f} > 1.05 — uploading but flagged for review.")

    if args.s3_upload:
        _upload_to_s3(trace_path, scaler_path, summary_path, n)


if __name__ == "__main__":
    main()
