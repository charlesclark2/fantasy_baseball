#!/usr/bin/env python
"""Story A2.1 — Honest live-skill metrics + health gate for the deployed models.

Productionizes the one-off 2026-06-10 audit (which found the live home_win champion
has ~zero skill: corr(calibrated, outcome)=0.001, live Brier 0.252 ≈ no-skill) into a
repeatable, schedulable check. It measures the DEPLOYED model's real-world skill on
COMPLETED games by joining the prediction log to actual outcomes — no backtest, no CV,
the honest live surface.

For each target it reports, vs the no-skill baseline AND vs the market:
  - home_win        corr / Brier / spread / accuracy of calibrated, consensus, market
  - total_runs      MAE / RMSE / corr / spread, plus over/under Brier vs market when present
  - run_differential MAE / RMSE / corr / spread

…then evaluates a per-target health gate (minimum spread, minimum corr, Brier strictly
below no-skill) and prints a PASS / FAIL / INSUFFICIENT verdict. With --write-snowflake
it persists one metrics row per target to baseball_data.betting_ml.model_health_metrics
so A2.6's standing gate and trend tracking have a durable record. Exit code is non-zero
when any enabled gate FAILS on a sufficient sample, so a Dagster op / cron can alert.

IMPORTANT (design note, A2.4/A2.6): the model's full discriminative feature set
(lineup archetype / cluster / h2h matchups, ~12 cols) is LINEUP-GATED — it is
structurally null on morning/pre-lineup predictions. Measure skill on `post_lineup`
predictions (`--prediction-type post_lineup`) for the honest verdict; morning-only
metrics understate true skill. The default dedup already prefers the post_lineup row
per game, but --prediction-type pins it explicitly.

Conventions: reads PROD predictions from baseball_data.betting_ml (override with
--schema). Hand off to run with real credentials (queries can exceed 1 min):

    python scripts/ops/model_health_metrics.py --days 30 --prediction-type post_lineup
    python scripts/ops/model_health_metrics.py --since 2026-05-20 --write-snowflake
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

# Allow running as a bare script (python scripts/ops/model_health_metrics.py) by
# putting the repo root on the path, mirroring the other ops helpers.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from betting_ml.utils.data_loader import get_snowflake_connection  # noqa: E402

# ---------------------------------------------------------------------------
# Health-gate thresholds. Shared with A2.6's standing gate — import from here,
# do not redefine, so the live gate and the re-measure use identical criteria.
# ---------------------------------------------------------------------------
MIN_GAMES = 30                 # below this the sample can't support a verdict → INSUFFICIENT
MIN_CORR_CLASS = 0.05          # corr(prob, binary outcome) floor for a classifier to have signal
MIN_CORR_REG = 0.05            # corr(pred, actual) floor for a regressor to have signal
# E13.6 TemperatureCalibrator (T=6.30) compresses calibrated_win_prob spread to ~0.030; the
# original INC-17 flat-output incident had spread ~0.016. 0.025 catches real collapse while
# giving calibrated models (v6 spread=0.0299) a healthy margin (INC-17-P3 fix).
MIN_SPREAD_PROB = 0.025        # std of the probability output; the audit's flat model had 0.016
MIN_SPREAD_TOTALS = 0.50       # std of pred_total_runs (runs); a useful model varies game to game
MIN_SPREAD_RUNDIFF = 0.50      # std of pred_run_diff_loc (runs)
BRIER_MARGIN = 0.002           # Brier must beat no-skill by at least this to count as skill

# INC-24 / E13.8 CALIBRATION — gate the WIN/MARGIN-market targets on FLAT OUTPUT only, not on
# beating the market. MLB moneyline + run-margin are near-efficient markets (E13.8), so a DE-LEAKED
# model (E13.11 v6) sits at their ceiling: an honest, non-leaky home_win / run_differential has
# corr(pred, outcome) near the 0.05 floor and Brier ≈ no-skill — the HONEST LIMIT, not a regression.
# The original gate treated corr/Brier as FAIL legs and cried wolf across (and after) the migration
# window: home_win FAILed on corr 0.028 and run_differential on corr 0.030, while the RE-SCORE on
# corrected features proved both have skill (corr 0.236 / 0.192) — i.e. the live FAILs were a
# serving-window + market-ceiling artifact, not a model regression. So for these targets only the
# SPREAD leg is a FAIL condition: a flat / near-constant output IS real corruption (market-blind or
# constant-imputed features, the INC-24 signature); a corr/Brier miss is EXPECTED → ADVISORY.
#
# total_runs is DELIBERATELY excluded — the over/under market is less efficient and the model retains
# stable, measurable corr there (live 0.176), so its corr leg still gates. And "total_runs
# near-constant" (spread) remains the real INC-24 signal for it, kept via the spread leg below.
SPREAD_ONLY_TARGETS = frozenset({"home_win", "run_differential"})

# INC-17-P3 (recalibrated 2026-07-22 after a soak false-positive): post_lineup feature-coverage
# REGRESSION check. The original fired on a FIXED feature_coverage_score < 0.85 and hard-coded
# "the lineup block (avg_eb_woba) is null." Two defects made it cry wolf on the 2026-07-21 slate
# (avg 0.774, emailed as an INC-17 lineup-block alert):
#   (1) MIS-ATTRIBUTION — the aggregate 6-block score cannot tell WHICH block dropped, and the
#       block actually imputed that day was the sequential/bullpen block, not the lineup block.
#       The block feature columns are not persisted in daily_model_predictions, so we now attribute
#       from the per-row `imputed_features` list instead of assuming.
#   (2) FLOOR ABOVE THE ACHIEVABLE MAX — the sequential/bullpen block has been chronically imputed
#       (healthy baseline ≈ 0.833), so a fixed 0.85 floor can NEVER be met → the alert fired every
#       slate. A genuine lineup-block null (0.833) is ALSO indistinguishable from that steady state
#       by the aggregate alone, so a fixed floor fundamentally cannot work. The trigger is now
#       BASELINE-RELATIVE (today vs its own trailing average), matching check_feature_block_coverage's
#       self-calibrating pattern — it catches a NEW single-block regression without firing on the
#       steady state.
# POST_LINEUP_AVG_COVERAGE_THRESHOLD is retained (the serve-time twin check_served_prediction_
# integrity imports it) but recalibrated to a HARD FLOOR for a BROAD (2+ block) collapse — well
# below the ~0.833 steady state so neither check false-fires on normal operation.
POST_LINEUP_AVG_COVERAGE_THRESHOLD = 0.70   # hard floor: a broad multi-block coverage collapse
POST_LINEUP_MIN_GAMES_FOR_CHECK = 3         # don't alert on single-game or empty slates
POST_LINEUP_COVERAGE_BASELINE_DAYS = 14     # trailing window for the self-calibrating baseline
POST_LINEUP_COVERAGE_DROP = 0.10            # alert when today is >= this far below the baseline
# Tokens in `imputed_features` that mark the lineup/matchup block specifically (the true INC-17
# signature) — used to LABEL a regression, never as the trigger.
_LINEUP_BLOCK_TOKENS = ("avg_eb_woba", "matchup", "archetype", "vs_starter", "h2h", "cluster")

_PRED_SCHEMA_DEFAULT = "betting_ml"
_RESULTS_TABLE = "baseball_data.betting_ml.model_health_metrics"


def _corr(x: np.ndarray, y: np.ndarray) -> float:
    """Pearson corr, NaN-safe and zero-variance-safe (a flat predictor → NaN, not a crash)."""
    if len(x) < 2:
        return float("nan")
    sx, sy = np.std(x), np.std(y)
    if sx == 0 or sy == 0:
        return float("nan")
    return float(np.corrcoef(x, y)[0, 1])


def _brier(p: np.ndarray, outcome: np.ndarray) -> float:
    return float(np.mean((p - outcome) ** 2))


def _fetch(conn, schema: str, start: date, end: date,
           model_version: str | None, prediction_type: str | None) -> pd.DataFrame:
    """One deduped prediction row per completed game, joined to actual outcomes.

    Dedup prefers the most-informed prediction for each game: post_lineup over
    morning, then lineup_confirmed, then the latest inserted_at.
    """
    filters = ["p.score_date between %(start)s and %(end)s"]
    params: dict = {"start": start, "end": end}
    if model_version:
        filters.append("p.model_version = %(mv)s")
        params["mv"] = model_version
    if prediction_type:
        filters.append("p.prediction_type = %(pt)s")
        params["pt"] = prediction_type
    where = " and ".join(filters)

    sql = f"""
        with preds as (
            select
                p.game_pk, p.score_date, p.prediction_type, p.lineup_confirmed,
                p.model_version,
                p.consensus_win_prob, p.calibrated_win_prob, p.h2h_market_implied_prob,
                p.pred_total_runs, p.totals_p_over, p.over_prob_consensus, p.total_line_consensus,
                p.pred_run_diff_loc, p.feature_coverage_score,
                row_number() over (
                    partition by p.game_pk
                    order by
                        iff(p.prediction_type = 'post_lineup', 1, 0) desc,
                        p.lineup_confirmed desc nulls last,
                        p.inserted_at desc
                ) as rn
            from baseball_data.{schema}.daily_model_predictions p
            where {where}
        )
        select
            pr.game_pk, pr.score_date, pr.prediction_type, pr.lineup_confirmed,
            pr.model_version,
            pr.consensus_win_prob, pr.calibrated_win_prob, pr.h2h_market_implied_prob,
            pr.pred_total_runs, pr.totals_p_over, pr.over_prob_consensus, pr.total_line_consensus,
            pr.pred_run_diff_loc, pr.feature_coverage_score,
            r.home_final_score, r.away_final_score, r.run_differential
        from preds pr
        join baseball_data.betting.mart_game_results r
            on r.game_pk = pr.game_pk and r.game_type = 'R'
        where pr.rn = 1
          and r.home_final_score is not null
          and r.away_final_score is not null
    """
    cur = conn.cursor()
    cur.execute(sql, params)
    cols = [c[0].lower() for c in cur.description]
    rows = cur.fetchall()
    cur.close()
    df = pd.DataFrame(rows, columns=cols)
    for c in df.columns:
        if c not in ("prediction_type", "model_version", "lineup_confirmed", "score_date"):
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def _eval_home_win(df: pd.DataFrame, min_games: int = MIN_GAMES) -> dict:
    """Live skill of the deployed home_win classifier vs no-skill and vs market."""
    outcome = (df["home_final_score"] > df["away_final_score"]).astype(float).to_numpy()
    n = len(outcome)
    base_rate = float(outcome.mean()) if n else float("nan")
    no_skill_brier = base_rate * (1 - base_rate) if n else float("nan")

    metrics: dict = {
        "target": "home_win", "n_games": n,
        "base_rate": base_rate, "no_skill_brier": no_skill_brier,
    }
    signals = {
        "calibrated": df["calibrated_win_prob"],
        "consensus": df["consensus_win_prob"],
        "market": df["h2h_market_implied_prob"],
    }
    for name, series in signals.items():
        p = series.to_numpy(dtype=float)
        mask = ~np.isnan(p)
        if mask.sum() < 2:
            metrics[f"{name}_corr"] = metrics[f"{name}_brier"] = float("nan")
            metrics[f"{name}_spread"] = metrics[f"{name}_mean"] = float("nan")
            continue
        pm, om = p[mask], outcome[mask]
        metrics[f"{name}_corr"] = _corr(pm, om)
        metrics[f"{name}_brier"] = _brier(pm, om)
        metrics[f"{name}_spread"] = float(np.std(pm))
        metrics[f"{name}_mean"] = float(np.mean(pm))
    # Accuracy of the calibrated pick (>0.5 → home).
    cal = df["calibrated_win_prob"].to_numpy(dtype=float)
    cmask = ~np.isnan(cal)
    metrics["calibrated_accuracy"] = (
        float(np.mean((cal[cmask] > 0.5).astype(float) == outcome[cmask])) if cmask.sum() else float("nan")
    )
    metrics["beats_market_brier"] = (
        bool(metrics["calibrated_brier"] < metrics["market_brier"])
        if not (np.isnan(metrics.get("calibrated_brier", np.nan)) or np.isnan(metrics.get("market_brier", np.nan)))
        else None
    )

    # Gate. FLAT OUTPUT (spread) is always a FAIL — it means the classifier stopped
    # discriminating (market-blind / constant-imputed features, the INC-24 signature). The
    # corr and beat-no-skill-Brier legs are the market-ceiling legs: for a de-leaked model
    # they are EXPECTED to miss (E13.8), so for a SPREAD_ONLY_TARGETS target they are recorded
    # as ADVISORY rather than FAIL, so the standing gate stops crying wolf on the honest ceiling.
    reasons: list[str] = []
    if not (metrics["calibrated_spread"] >= MIN_SPREAD_PROB):
        reasons.append(f"spread {metrics['calibrated_spread']:.3f} < {MIN_SPREAD_PROB} (flat output)")
    ceiling_notes: list[str] = []
    if not (metrics["calibrated_corr"] >= MIN_CORR_CLASS):
        ceiling_notes.append(f"corr {metrics['calibrated_corr']:.3f} < {MIN_CORR_CLASS}")
    if not (metrics["calibrated_brier"] < metrics["no_skill_brier"] - BRIER_MARGIN):
        ceiling_notes.append(
            f"Brier {metrics['calibrated_brier']:.3f} not below no-skill "
            f"{metrics['no_skill_brier']:.3f}-{BRIER_MARGIN}")
    if "home_win" in SPREAD_ONLY_TARGETS:
        metrics["advisory_flags"] = "; ".join(ceiling_notes)  # at-ceiling, not a failure
    else:
        reasons += ceiling_notes
        metrics["advisory_flags"] = ""
    metrics["verdict"], metrics["fail_reasons"] = _verdict(n, reasons, min_games)
    return metrics


def _eval_regression(df: pd.DataFrame, target: str, min_games: int = MIN_GAMES) -> dict:
    """Live skill of a regression target (total_runs or run_differential)."""
    if target == "total_runs":
        actual = (df["home_final_score"] + df["away_final_score"]).to_numpy(dtype=float)
        pred = df["pred_total_runs"].to_numpy(dtype=float)
        min_spread = MIN_SPREAD_TOTALS
    else:  # run_differential
        actual = df["run_differential"].to_numpy(dtype=float)
        pred = df["pred_run_diff_loc"].to_numpy(dtype=float)
        min_spread = MIN_SPREAD_RUNDIFF

    mask = ~np.isnan(pred) & ~np.isnan(actual)
    pm, am = pred[mask], actual[mask]
    n = int(mask.sum())
    metrics: dict = {"target": target, "n_games": n}
    if n >= 1:
        err = pm - am
        metrics["mae"] = float(np.mean(np.abs(err)))
        metrics["rmse"] = float(np.sqrt(np.mean(err ** 2)))
        metrics["pred_spread"] = float(np.std(pm))
        metrics["pred_mean"] = float(np.mean(pm))
        metrics["actual_mean"] = float(np.mean(am))
        metrics["corr"] = _corr(pm, am)
    else:
        for k in ("mae", "rmse", "pred_spread", "pred_mean", "actual_mean", "corr"):
            metrics[k] = float("nan")

    # Over/under Brier vs market for total_runs when a line + model p_over exist.
    if target == "total_runs":
        line = df["total_line_consensus"].to_numpy(dtype=float)
        p_over_model = df["totals_p_over"].to_numpy(dtype=float)
        p_over_mkt = df["over_prob_consensus"].to_numpy(dtype=float)
        ou_mask = mask & ~np.isnan(line)
        if ou_mask.sum() >= 1:
            ou_outcome = (actual[ou_mask] > line[ou_mask]).astype(float)
            mm = ou_mask & ~np.isnan(p_over_model)
            km = ou_mask & ~np.isnan(p_over_mkt)
            metrics["totals_ou_n"] = int(ou_mask.sum())
            metrics["totals_ou_brier_model"] = (
                _brier(p_over_model[mm], (actual[mm] > line[mm]).astype(float)) if mm.sum() else float("nan")
            )
            metrics["totals_ou_brier_market"] = (
                _brier(p_over_mkt[km], (actual[km] > line[km]).astype(float)) if km.sum() else float("nan")
            )
            metrics["totals_ou_base_rate"] = float(ou_outcome.mean())
        else:
            metrics["totals_ou_n"] = 0

    # SPREAD (near-constant output) is always a FAIL — the INC-24 corruption signal. The corr leg
    # is the market-ceiling leg: for a spread-only target (run_differential — the near-efficient
    # margin market, E13.8) it is ADVISORY, not a FAIL (the rescore proves skill exists; the live
    # dip is a serving-window artifact). total_runs keeps its corr gate.
    reasons: list[str] = []
    ceiling_notes: list[str] = []
    if not (metrics["pred_spread"] >= min_spread):
        reasons.append(f"pred spread {metrics['pred_spread']:.3f} < {min_spread} (near-constant)")
    if not (metrics["corr"] >= MIN_CORR_REG):
        note = f"corr {metrics['corr']:.3f} < {MIN_CORR_REG}"
        if target in SPREAD_ONLY_TARGETS:
            ceiling_notes.append(note)
        else:
            reasons.append(note)
    metrics["advisory_flags"] = "; ".join(ceiling_notes)
    metrics["verdict"], metrics["fail_reasons"] = _verdict(n, reasons, min_games)
    return metrics


def _verdict(n: int, reasons: list[str], min_games: int = MIN_GAMES) -> tuple[str, str]:
    if n < min_games:
        return "INSUFFICIENT", f"only {n} games (< {min_games})"
    if reasons:
        return "FAIL", "; ".join(reasons)
    return "PASS", ""


def _fmt(v) -> str:
    if v is None:
        return "—"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, float):
        return "nan" if np.isnan(v) else f"{v:.4f}"
    return str(v)


def _print_report(window: str, ptype: str | None, model_version: str | None,
                  hw: dict, tot: dict, rd: dict) -> None:
    print("=" * 78)
    print(f"  MODEL HEALTH METRICS — {window}")
    print(f"  prediction_type={ptype or 'best-per-game'}  model_version={model_version or 'all'}")
    print("=" * 78)

    print(f"\n[home_win]  n={hw['n_games']}  base_rate={_fmt(hw['base_rate'])}  "
          f"no_skill_Brier={_fmt(hw['no_skill_brier'])}")
    for name in ("calibrated", "consensus", "market"):
        print(f"   {name:<11} corr={_fmt(hw[f'{name}_corr'])}  Brier={_fmt(hw[f'{name}_brier'])}  "
              f"spread={_fmt(hw[f'{name}_spread'])}  mean={_fmt(hw[f'{name}_mean'])}")
    print(f"   calibrated accuracy={_fmt(hw['calibrated_accuracy'])}  "
          f"beats_market_Brier={_fmt(hw['beats_market_brier'])}")
    print(f"   → {hw['verdict']}" + (f"  ({hw['fail_reasons']})" if hw["fail_reasons"] else ""))
    # INC-17: flat-output early warning. When spread < 2×MIN_SPREAD_PROB the model output
    # is compressed near 0.5 — corr can't reach 0.05 even with correct feature ranking.
    # This distinguishes the "de-leaked model correctly uncertain" case from a serving
    # regression. Run rescore_audit.py --since <date> --compare-live to fork the two.
    hw_spread = hw.get("calibrated_spread", float("nan"))
    if not (hw_spread != hw_spread) and hw_spread < MIN_SPREAD_PROB * 2:
        print(f"   ⚠ FLAT-OUTPUT: calibrated_spread={_fmt(hw_spread)} < {MIN_SPREAD_PROB * 2:.3f}. "
              f"Model output is compressed — check (a) de-leak removed primary discriminator or "
              f"(b) lineup-gated features (matchup woba/archetype) imputed null at serve time. "
              f"Run: uv run python scripts/ops/rescore_audit.py --since <date> --compare-live")

    for m, label in ((tot, "total_runs"), (rd, "run_differential")):
        print(f"\n[{label}]  n={m['n_games']}  MAE={_fmt(m['mae'])}  RMSE={_fmt(m['rmse'])}  "
              f"corr={_fmt(m['corr'])}")
        print(f"   pred_spread={_fmt(m['pred_spread'])}  pred_mean={_fmt(m['pred_mean'])}  "
              f"actual_mean={_fmt(m['actual_mean'])}")
        if label == "total_runs" and m.get("totals_ou_n"):
            print(f"   over/under (n={m['totals_ou_n']}): Brier model={_fmt(m.get('totals_ou_brier_model'))}  "
                  f"market={_fmt(m.get('totals_ou_brier_market'))}  base_rate={_fmt(m.get('totals_ou_base_rate'))}")
        print(f"   → {m['verdict']}" + (f"  ({m['fail_reasons']})" if m["fail_reasons"] else ""))
    print()


_CREATE_RESULTS = f"""
CREATE TABLE IF NOT EXISTS {_RESULTS_TABLE} (
    run_at            TIMESTAMP_NTZ,
    window_start      DATE,
    window_end        DATE,
    prediction_type   VARCHAR(20),
    model_version     VARCHAR(20),
    target            VARCHAR(20),
    n_games           INTEGER,
    verdict           VARCHAR(15),
    fail_reasons      VARCHAR,
    corr              FLOAT,
    brier             FLOAT,
    no_skill_brier    FLOAT,
    spread            FLOAT,
    mae               FLOAT,
    rmse              FLOAT,
    beats_market      BOOLEAN
)
"""


def _persist(conn, run_at: datetime, start: date, end: date, ptype: str | None,
             model_version: str | None, hw: dict, tot: dict, rd: dict) -> None:
    cur = conn.cursor()
    cur.execute(_CREATE_RESULTS)
    rows = [
        (run_at, start, end, ptype, model_version, "home_win", hw["n_games"], hw["verdict"],
         hw["fail_reasons"], hw["calibrated_corr"], hw["calibrated_brier"], hw["no_skill_brier"],
         hw["calibrated_spread"], None, None, hw["beats_market_brier"]),
        (run_at, start, end, ptype, model_version, "total_runs", tot["n_games"], tot["verdict"],
         tot["fail_reasons"], tot["corr"], tot.get("totals_ou_brier_model"), None,
         tot["pred_spread"], tot["mae"], tot["rmse"], None),
        (run_at, start, end, ptype, model_version, "run_differential", rd["n_games"], rd["verdict"],
         rd["fail_reasons"], rd["corr"], None, None, rd["pred_spread"], rd["mae"], rd["rmse"], None),
    ]

    def _nan_to_none(v):
        return None if isinstance(v, float) and np.isnan(v) else v

    rows = [tuple(_nan_to_none(v) for v in r) for r in rows]
    cur.executemany(
        f"INSERT INTO {_RESULTS_TABLE} (run_at, window_start, window_end, prediction_type, "
        f"model_version, target, n_games, verdict, fail_reasons, corr, brier, no_skill_brier, "
        f"spread, mae, rmse, beats_market) VALUES "
        f"(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        rows,
    )
    cur.close()
    print(f"  Wrote {len(rows)} metric row(s) to {_RESULTS_TABLE} (run_at={run_at.isoformat()}).")


def check_post_lineup_matchup_coverage(
    conn, schema: str, check_date: date
) -> dict:
    """INC-17-P3 (recalibrated 2026-07-22): detect a post_lineup feature-coverage REGRESSION and
    report WHICH features are imputed, rather than assuming the lineup block.

    Fires when the slate-average `feature_coverage_score` drops >= POST_LINEUP_COVERAGE_DROP below
    its trailing baseline (self-calibrating, so a chronically-imputed NON-lineup block does not cry
    wolf), OR below the POST_LINEUP_AVG_COVERAGE_THRESHOLD hard floor (a broad multi-block collapse).
    Attribution comes from the per-row `imputed_features` list — the block feature columns are not
    persisted in daily_model_predictions, so the aggregate score alone cannot tell WHICH block fell.

    Returns:
        dict with keys n_games, avg_coverage, baseline_coverage, alert_fired, fail_reason.
    """
    cur = conn.cursor()
    cur.execute(
        f"""
        select feature_coverage_score,
               coalesce(cast(imputed_features as varchar), '') as imputed_features
        from baseball_data.{schema}.daily_model_predictions
        where score_date = %(d)s
          and prediction_type = 'post_lineup'
          and feature_coverage_score is not null
        """,
        {"d": check_date.isoformat()},
    )
    slate = cur.fetchall()
    n_games = len(slate)
    if n_games < POST_LINEUP_MIN_GAMES_FOR_CHECK:
        cur.close()
        return {
            "n_games": n_games,
            "avg_coverage": float("nan"),
            "baseline_coverage": float("nan"),
            "alert_fired": False,
            "fail_reason": f"insufficient post_lineup rows ({n_games}) for {check_date}",
        }
    avg_cov = sum(float(r[0]) for r in slate) / n_games

    # Self-calibrating trailing baseline: the post_lineup slate-average over the prior window
    # (excluding today). A NaN baseline (no history) just falls back to the hard floor below.
    cur.execute(
        f"""
        select avg(feature_coverage_score)
        from baseball_data.{schema}.daily_model_predictions
        where prediction_type = 'post_lineup'
          and feature_coverage_score is not null
          and score_date >= %(lo)s and score_date < %(d)s
        """,
        {
            "lo": (check_date - timedelta(days=POST_LINEUP_COVERAGE_BASELINE_DAYS)).isoformat(),
            "d": check_date.isoformat(),
        },
    )
    brow = cur.fetchone()
    cur.close()
    baseline = float(brow[0]) if brow and brow[0] is not None else float("nan")

    # Attribution: which features are actually imputed across the slate (top tokens), so the alert
    # names the real null block instead of always blaming the lineup block.
    counts: dict[str, int] = {}
    for r in slate:
        for tok in str(r[1]).replace(" ", "").split(","):
            if tok:
                counts[tok] = counts.get(tok, 0) + 1
    top = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:6]
    imp_label = ", ".join(f"{t}x{c}" for t, c in top) if top else "none recorded"
    lineup_block_hit = any(any(k in t for k in _LINEUP_BLOCK_TOKENS) for t in counts)

    has_baseline = baseline == baseline  # False iff NaN
    drop = (baseline - avg_cov) if has_baseline else 0.0
    alert_fired = (avg_cov < POST_LINEUP_AVG_COVERAGE_THRESHOLD) or (
        has_baseline and drop >= POST_LINEUP_COVERAGE_DROP
    )

    if not alert_fired:
        fail_reason = ""
    else:
        block = (
            "the LINEUP/matchup block (avg_eb_woba / matchup woba / archetype)"
            if lineup_block_hit
            else "a NON-lineup block — see the imputed features above, NOT necessarily the lineup block"
        )
        base_txt = "n/a" if not has_baseline else f"{baseline:.3f}"
        fail_reason = (
            f"INC-17 class: post_lineup feature-coverage regression on {check_date}. "
            f"slate avg feature_coverage_score={avg_cov:.3f} vs trailing-"
            f"{POST_LINEUP_COVERAGE_BASELINE_DAYS}d baseline={base_txt} across {n_games} games "
            f"(hard floor {POST_LINEUP_AVG_COVERAGE_THRESHOLD}). Most-imputed features: {imp_label}. "
            f"Likely null block: {block}. If the lineup block: check feature_pregame_lineup_features "
            f"/ feature_pitcher_batter_h2h_matchups lineage AND mart_game_spine coverage of the slate "
            f"(a game rescheduled after the daily --w5 spine build is absent from the store → "
            f"intraday_assembly fallback, which also lowers coverage)."
        )
    return {
        "n_games": n_games,
        "avg_coverage": avg_cov,
        "baseline_coverage": baseline,
        "alert_fired": alert_fired,
        "fail_reason": fail_reason,
    }


def evaluate(conn, schema: str, start: date, end: date,
             model_version: str | None = None, prediction_type: str | None = None,
             min_games: int = MIN_GAMES) -> dict | None:
    """Run the health check and return {target: metrics} (or None if no data).

    Shared by the CLI (main) and the Dagster health-gate sensor so the live gate and
    the ad-hoc report use identical fetch + eval + thresholds. Caller owns `conn`.
    """
    df = _fetch(conn, schema, start, end, model_version, prediction_type)
    if df.empty:
        return None
    return {
        "home_win": _eval_home_win(df, min_games),
        "total_runs": _eval_regression(df, "total_runs", min_games),
        "run_differential": _eval_regression(df, "run_differential", min_games),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Honest live-skill metrics + health gate (A2.1).")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--days", type=int, default=30, help="rolling window ending today (default 30)")
    g.add_argument("--since", type=str, help="window start date YYYY-MM-DD (overrides --days)")
    ap.add_argument("--end", type=str, help="window end date YYYY-MM-DD (default today)")
    ap.add_argument("--prediction-type", choices=["morning", "post_lineup"],
                    help="filter to one prediction pass (post_lineup recommended for honest skill)")
    ap.add_argument("--model-version", help="filter to a model_version (e.g. v4); default all")
    ap.add_argument("--schema", default=_PRED_SCHEMA_DEFAULT,
                    help=f"prediction-log schema (default {_PRED_SCHEMA_DEFAULT}; use betting_ml_dev for local runs)")
    ap.add_argument("--min-games", type=int, default=MIN_GAMES, help=f"gate min sample (default {MIN_GAMES})")
    ap.add_argument("--write-snowflake", action="store_true",
                    help=f"persist a metrics row per target to {_RESULTS_TABLE}")
    args = ap.parse_args()
    min_games = args.min_games

    end = datetime.strptime(args.end, "%Y-%m-%d").date() if args.end else date.today()
    start = datetime.strptime(args.since, "%Y-%m-%d").date() if args.since else end - timedelta(days=args.days)
    window = f"{start.isoformat()} → {end.isoformat()}"

    conn = get_snowflake_connection()
    try:
        result = evaluate(conn, args.schema, start, end, args.model_version,
                          args.prediction_type, min_games)
        if result is None:
            print(f"No completed-game predictions in {window} "
                  f"(schema={args.schema}, type={args.prediction_type or 'any'}).")
            return 0

        hw, tot, rd = result["home_win"], result["total_runs"], result["run_differential"]
        _print_report(window, args.prediction_type, args.model_version, hw, tot, rd)

        if args.write_snowflake:
            # Use a Snowflake-side timestamp to avoid local-clock skew in the record.
            ts_cur = conn.cursor()
            ts_cur.execute("select current_timestamp()::timestamp_ntz")
            run_at = ts_cur.fetchone()[0]
            ts_cur.close()
            _persist(conn, run_at, start, end, args.prediction_type, args.model_version, hw, tot, rd)

        # Alerting contract: non-zero exit when any enabled gate FAILS on a sufficient sample.
        verdicts = {m["target"]: m["verdict"] for m in (hw, tot, rd)}
        failed = [t for t, v in verdicts.items() if v == "FAIL"]
        insufficient = [t for t, v in verdicts.items() if v == "INSUFFICIENT"]
        print(f"GATE: {verdicts}")
        if failed:
            print(f"GATE FAILED for: {', '.join(failed)} — deployed model is not healthy on this window.")
            return 2
        if insufficient and not any(v == "PASS" for v in verdicts.values()):
            print("GATE INCONCLUSIVE — insufficient completed games to judge any target.")
            return 0
        print("GATE PASSED (or inconclusive-but-some-pass) — no FAIL on a sufficient sample.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
