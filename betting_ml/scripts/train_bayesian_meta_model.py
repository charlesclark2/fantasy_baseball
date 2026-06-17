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
_REPORT_DIR = (PROJECT_ROOT / "quant_sports_intel_models" / "baseball" / "ablation_results")

FEATURES = ["edge_mag", "pub_align", "open_extremity"]   # base feature set (Story 12.4/12.12)

# Story 12.13 — candidate Layer-4-derived extras, per market, added under --features plus_layer4.
# All RECOMPUTED from historically-dense columns (the stored layer4_* columns are <12% populated —
# recent features — so we derive the signal from consensus_win_prob / open line / pred_total scale).
#   h2h  direction_flip — model fades the market favorite (model & open on opposite sides of 0.5).
#        Data-validated 2026-06-17: +0.111 CLV+ within low-edge games, +0.056 within high-edge —
#        ADDITIVE beyond edge_mag. (The conviction/estimator-disagreement signal was weak +
#        non-monotonic → excluded.)
#   totals edge_sigma — |centered totals edge| / pred_total_runs_scale (edge in model-σ units).
#        Speculative candidate only (totals meta v0 had zero OOS discrimination); kept so the
#        ablation tests it, expected to fail its held-out gate.
_EXTRA_FEATURES = {"h2h": ["direction_flip"], "totals": ["edge_sigma"]}
_PRIOR_MU = {"edge_mag": 0.4, "pub_align": 0.0, "open_extremity": 0.0,
             "direction_flip": 0.0, "edge_sigma": 0.0}
_PRIOR_SIGMA = {"edge_mag": 0.5}  # default 0.4 for the rest


def _feature_list(market: str, featureset: str) -> list[str]:
    return FEATURES if featureset == "base" else FEATURES + _EXTRA_FEATURES.get(market, [])


DRAWS, TUNE, CHAINS, TARGET_ACCEPT, SEED = 1000, 1000, 4, 0.9, 124

# Story 12.12 — the H2H meta-model (12.4) and the totals meta-model share this trainer via
# --market. Artifacts: h2h stays at the flat meta_model/ path (backward-compatible with the
# live 12.4 serve + O.5); totals lives under meta_model/totals/.
_REPORT = {"h2h": "bayesian_meta_model_12_4.md", "totals": "bayesian_meta_model_12_12.md"}


def _market_dir(market: str) -> Path:
    return _MODELS if market == "h2h" else _MODELS / market


# Per-market load: the H2H edge is model_home_prob − open_home_win_prob and the CLV label is
# the H2H moneyline open→close move; the totals edge is model_total − open_total_line and the
# label is the over/under line move. Same shape, different market columns.
_SQL_H2H = """
with morn as (
  select game_pk, game_date,
         coalesce(calibrated_win_prob, consensus_win_prob, h2h_posterior_prob) as model_val
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
  morn.model_val, mv.open_home_win_prob as open_val, mv.h2h_line_movement as line_movement,
  pb.handle_ticket_div
from baseball_data.betting.mart_odds_line_movement mv
join morn on morn.game_pk = mv.game_pk
left join pb on pb.game_pk = mv.game_pk
where mv.snapshot_count > 1
"""

_SQL_TOTALS = """
with morn as (
  select game_pk, game_date, pred_total_runs as model_val,
         pred_total_runs_scale as model_scale
  from baseball_data.betting_ml.daily_model_predictions
  where prediction_type='morning' and coalesce(is_backfill,false)=false
    and date_part('year', game_date)=2026
  qualify row_number() over (partition by game_pk order by inserted_at asc)=1
),
pb as (
  select game_pk, over_money_pct - over_ticket_pct as handle_ticket_div
  from baseball_data.betting_features.feature_pregame_public_betting_features
)
select
  mv.game_pk, morn.game_date, mv.data_source,
  morn.model_val, morn.model_scale, mv.open_total_line as open_val,
  mv.total_line_movement as line_movement, pb.handle_ticket_div
from baseball_data.betting.mart_odds_line_movement mv
join morn on morn.game_pk = mv.game_pk
left join pb on pb.game_pk = mv.game_pk
where mv.snapshot_count > 1
"""

_SQL = {"h2h": _SQL_H2H, "totals": _SQL_TOTALS}


def _load(market: str) -> pd.DataFrame:
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(_SQL[market])
        df = cur.fetch_pandas_all()
    finally:
        conn.close()
    df.columns = [c.lower() for c in df.columns]

    df["raw_edge"] = df["model_val"] - df["open_val"]
    # Center the edge to remove the constant vig/baseline bias (open_val carries vig for h2h,
    # a market-baseline total for totals). The median is the de-bias anchor and is a TRAINING
    # statistic — persisted in the scaler so serve-time centering matches.
    df.attrs["edge_median"] = float(df["raw_edge"].median())
    edge_c = df["raw_edge"] - df.attrs["edge_median"]
    df["model_side"] = np.sign(edge_c)                       # h2h: +1 home/−1 away; totals: +1 over/−1 under
    df["edge_mag"] = edge_c.abs()
    df["handle_ticket_div"] = df["handle_ticket_div"].fillna(0.0)  # missing public split = neutral
    df["pub_align"] = df["handle_ticket_div"] * df["model_side"]
    # Mean-reversion control: distance of the open from its neutral anchor. h2h anchor = 0.5
    # (pick'em); totals anchor = the median open total. The anchor is a training statistic.
    open_anchor = 0.5 if market == "h2h" else float(df["open_val"].median())
    df.attrs["open_anchor"] = open_anchor
    df["open_extremity"] = (df["open_val"] - open_anchor).abs()

    # Story 12.13 — recomputed Layer-4 extras (only used under --features plus_layer4).
    if market == "h2h":
        # Model fades the market favorite: model & open on opposite sides of 0.5 (pick'em).
        df["direction_flip"] = ((df["model_val"] > 0.5) != (df["open_val"] > 0.5)).astype(float)
    else:
        # Totals edge in model-σ units (|centered edge| / NGBoost scale); guard scale>0.
        scale = df["model_scale"].where(df["model_scale"] > 0, np.nan)
        df["edge_sigma"] = (df["edge_mag"] / scale).fillna(0.0)

    # Label: did the close move toward our side? Defined on moved games only.
    df["moved"] = df["line_movement"] != 0
    df["clv_positive"] = (np.sign(df["line_movement"]) == df["model_side"]).astype(int)
    return df


def _standardize(X: pd.DataFrame) -> tuple[np.ndarray, dict]:
    mu = X.mean()
    sd = X.std(ddof=0).replace(0, 1.0)
    Z = ((X - mu) / sd).to_numpy(float)
    scaler = {"features": list(X.columns), "mean": mu.to_dict(), "std": sd.to_dict()}
    return Z, scaler


def _posterior_logits(trace, Z: np.ndarray, features: list[str]) -> np.ndarray:
    """Return an (n_samples, n_games) matrix of logit draws."""
    post = trace.posterior
    b0 = post["b0"].values.reshape(-1)                       # (S,)
    betas = np.stack([post[f"b_{f}"].values.reshape(-1) for f in features], axis=1)  # (S,F)
    return b0[:, None] + betas @ Z.T                         # (S, n_games)


_S3_BASE = "s3://baseball-betting-ml-artifacts/meta_model"


def _s3_base(market: str) -> str:
    """h2h uploads to the flat meta_model/ prefix (backward-compatible); totals to a subdir."""
    return _S3_BASE if market == "h2h" else f"{_S3_BASE}/{market}"


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


def _upload_to_s3(trace_path: Path, scaler_path: Path, summary_path: Path, n: int, market: str) -> None:
    """Upload the freshly-written trace + scaler + latest-summary to S3 (Epic O.5).

    The per-n trace/scaler are immutable history; `meta_model_latest.json` is the
    stable pointer the weekly job (and the serve-side S3 pull) reads for the newest n.
    Per-market prefix so h2h and totals never collide.
    """
    from betting_ml.utils.artifact_store import upload_artifact
    base = _s3_base(market)
    upload_artifact(trace_path, f"{base}/{trace_path.name}")
    upload_artifact(scaler_path, f"{base}/{scaler_path.name}")
    upload_artifact(summary_path, f"{base}/meta_model_latest.json")
    print(f"Uploaded trace+scaler+summary (n={n}) → {base}/")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Train the Bayesian CLV meta-model (Story 12.4); weekly retrain via Epic O.5.")
    parser.add_argument("--s3-upload", action="store_true",
                        help="After writing locally, upload trace+scaler+summary to "
                             f"{_S3_BASE}/. Used by the weekly Dagster job (Epic O.5).")
    parser.add_argument("--min-games", type=int, default=50,
                        help="Epic O.5 count gate: if the moved-game training population is "
                             "below this, skip MCMC and exit 0 (never fail below threshold).")
    parser.add_argument("--market", choices=["h2h", "totals"], default="h2h",
                        help="Which market to train (Story 12.12). h2h → flat meta_model/ path "
                             "(12.4 default); totals → meta_model/totals/.")
    parser.add_argument("--features", choices=["base", "plus_layer4"], default="base",
                        help="Story 12.13 ablation. base = 3-feature 12.4/12.12 model (the served one). "
                             "plus_layer4 = base + recomputed Layer-4 extras (h2h direction_flip / totals "
                             "edge_sigma). plus_layer4 writes to an ablation subdir — never clobbers or serves "
                             "the base trace; promote only on a held-out lift.")
    args = parser.parse_args()
    market, featureset = args.market, args.features
    features = _feature_list(market, featureset)

    import pymc as pm
    import arviz as az
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    from sklearn.preprocessing import StandardScaler

    # base → served path (12.4/12.12); plus_layer4 → ablation subdir so it can never be picked up
    # by load_latest_meta_model's glob or uploaded as the live trace.
    models_dir = _market_dir(market) if featureset == "base" else _market_dir(market) / f"ablation_{featureset}"
    out_path = (_REPORT_DIR / _REPORT[market] if featureset == "base"
                else _REPORT_DIR / f"bayesian_meta_model_12_13_{market}_{featureset}.md")
    models_dir.mkdir(parents=True, exist_ok=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    raw = _load(market)
    df = raw[raw["moved"]].dropna(subset=features + ["clv_positive"]).copy()
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
        print(f"[{market}/{featureset}] Insufficient CLV labels ({n}/{args.min_games}) — skipping MCMC.")
        return

    Z, scaler = _standardize(df[features])
    y = df["clv_positive"].to_numpy(int)

    # ── Bayesian logistic regression (N features) ─────────────────────────────────
    # Weakly-informative priors: data (~900 games) dominates. Intercept centered on the
    # known base rate; β_edge weakly positive (pre-test); all others ~0, sign learned.
    with pm.Model() as model:
        b0 = pm.Normal("b0", mu=float(np.log(base_rate / (1 - base_rate))), sigma=0.5)
        betas = [pm.Normal(f"b_{f}", mu=_PRIOR_MU.get(f, 0.0), sigma=_PRIOR_SIGMA.get(f, 0.4))
                 for f in features]
        logit_p = b0 + sum(betas[i] * Z[:, i] for i in range(len(features)))
        pm.Bernoulli("clv_obs", logit_p=logit_p, observed=y)
        trace = pm.sample(draws=DRAWS, tune=TUNE, chains=CHAINS, target_accept=TARGET_ACCEPT,
                          random_seed=SEED, progressbar=False)

    summary = az.summary(trace, var_names=["b0"] + [f"b_{f}" for f in features])
    max_rhat = float(summary["r_hat"].max())

    # ── Per-game posterior P(CLV>0) + 80% CI ──────────────────────────────────────
    logits = _posterior_logits(trace, Z, features)           # (S, n_games)
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
    sc = StandardScaler().fit(df[features].iloc[:cut])
    lr = LogisticRegression(max_iter=1000).fit(sc.transform(df[features].iloc[:cut]), y[:cut])
    test_p = lr.predict_proba(sc.transform(df[features].iloc[cut:]))[:, 1]
    temporal_auc = (float(roc_auc_score(y[cut:], test_p))
                    if len(np.unique(y[cut:])) > 1 else float("nan"))

    gate1 = max_rhat < 1.01
    gate2 = mean_ci_width < 0.25
    gate3 = quartile_spread >= 0.05
    all_pass = gate1 and gate2 and gate3

    # ── Persist trace + scaler ─────────────────────────────────────────────────────
    trace_path = models_dir / f"bayesian_meta_trace_{n:04d}.nc"
    trace.to_netcdf(str(trace_path))
    scaler["n_games"] = n
    scaler["base_rate"] = base_rate
    scaler["edge_median"] = df.attrs["edge_median"]
    scaler["market"] = market                                # serve-side market-aware feature build
    scaler["open_anchor"] = df.attrs["open_anchor"]          # h2h 0.5 / totals median open total
    scaler["featureset"] = featureset                        # Story 12.13 — base vs plus_layer4
    scaler_path = models_dir / f"meta_model_scaler_{n:04d}.json"
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
        "temporal_auc": round(temporal_auc, 4),       # Story 12.13 — the honest discrimination gate
        "gates": {"rhat": gate1, "ci_width": gate2, "quartile": gate3, "all_pass": all_pass},
        "trace_file": trace_path.name,
        "scaler_file": scaler_path.name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    summary["market"] = market
    summary["featureset"] = featureset
    summary["features"] = features
    summary_path = models_dir / "meta_model_latest.json"
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

    story = "12.4" if market == "h2h" else "12.12"
    mkt_label = "H2H" if market == "h2h" else "totals"
    edge_desc = ("|centered morning H2H edge| (model_home_prob − open_home_win_prob)"
                 if market == "h2h"
                 else "|centered morning totals edge| (pred_total_runs − open_total_line)")
    open_desc = ("|open_home_win_prob − 0.5|" if market == "h2h"
                 else "|open_total_line − median open total|")
    pub_desc = ("public (money%−ticket%) × model_side — sharp money on our side" if market == "h2h"
                else "public over (money%−ticket%) × model_side — sharp O/U money on our side")
    _extra_desc = {
        "direction_flip": "1 if the model fades the market favorite (model & open on opposite sides "
                          "of 0.5) — Story 12.13, +0.11/+0.06 CLV+ lift validated beyond edge_mag",
        "edge_sigma": "|centered totals edge| / pred_total_runs_scale (edge in model-σ units) — Story 12.13 candidate",
    }
    coef = {name: _coef(name) for name in ["b0"] + [f"b_{f}" for f in features]}
    L = [
        f"# Story {story} — Bayesian sequential CLV meta-model — {mkt_label} (featureset={featureset})", "",
        f"**Population:** {n} moved 2026 live-morning games ⋈ Bovada open→close {mkt_label} movement "
        f"(snapshot_count>1; {len(raw)} paired, flat dropped). Label CLV+ = close moved toward "
        f"the morning model's side; base rate **{base_rate:.3f}**.",
        "",
        f"**Feature set ({featureset}):** base 3 features (market-specific derivation)"
        + (f" + Story 12.13 extra(s): {', '.join(_EXTRA_FEATURES.get(market, []))}"
           if featureset != "base" else "") + ".",
        f"- `edge_mag` = {edge_desc} — primary signal",
        f"- `pub_align` = {pub_desc}",
        f"- `open_extremity` = {open_desc} — mean-reversion control",
    ] + [f"- `{f}` = {_extra_desc.get(f, '')}" for f in features if f not in FEATURES] + [
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
        f"- Trace: `{trace_path.relative_to(PROJECT_ROOT)}`; scaler/feature-spec sidecar "
        f"`{scaler_path.name}`.",
        "- In-sample gates are correct for a sequential model (the edge↔CLV signal is already "
        "OOS-validated by the pre-test); the temporal-split AUC guards against an in-sample mirage.",
        f"- base rate {base_rate:.3f} (moved games; line moved toward the model's side).",
        f"- **Honest discrimination check: temporal AUC {temporal_auc:.3f} vs in-sample {in_auc:.3f}.** "
        + ("Temporal ≥ in-sample ⇒ the features generalize." if temporal_auc >= in_auc
           else "Temporal < in-sample ⇒ the features do NOT generalize out-of-sample (in-sample "
                "separation is a mirage). The 3 convergence gates can still PASS — they test the "
                "sampler + in-sample quartile spread, NOT OOS skill — so treat 'ALL GATES PASS' as "
                "'converged', not 'has edge'. A near-flat served P(CLV>0) (clustered at the base "
                "rate) is the honest signal; do not present it as conviction."),
    ]
    out_path.write_text("\n".join(L) + "\n")

    print("\n".join([
        "", f"max R-hat        = {max_rhat:.4f}  (gate <1.01: {'PASS' if gate1 else 'FAIL'})",
        f"mean CI width    = {mean_ci_width:.4f}  (gate <0.25: {'PASS' if gate2 else 'FAIL'})",
        f"quartile spread  = {quartile_spread:+.4f}  (gate ≥0.05: {'PASS' if gate3 else 'FAIL'})",
        f"in-sample AUC    = {in_auc:.3f}",
        f"temporal AUC     = {temporal_auc:.3f}",
        f"coefficients     = " + ", ".join(f"{k}={v[0]:+.3f}" for k, v in coef.items()),
        f"\nVERDICT [{market}/{featureset}]: {'ALL GATES PASS' if all_pass else 'NOT ALL GATES PASS'}",
        f"Report  → {out_path}",
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

    if args.s3_upload and featureset != "base":
        # Safety: plus_layer4 is an ablation artifact. NEVER upload it as the live trace — that
        # would clobber the served base model's S3 pointer with a feature set the serve can't build.
        print(f"[12.13] featureset={featureset}: skipping S3 upload (ablation artifact, not the "
              f"served model). Promote by re-running --features base once a held-out lift is confirmed.")
    elif args.s3_upload:
        _upload_to_s3(trace_path, scaler_path, summary_path, n, market)


if __name__ == "__main__":
    main()
