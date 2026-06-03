"""
calibrate_totals_v1.py — Epic 10, Story 10.4

Retrospective calibration of the Layer 3 totals champion (`totals_v1`) against
actual outcomes and Bovada's historical totals lines (2021–2025 regular season).

This is a *validation* step, NOT a training step. It answers: when the model
says P(over) = 0.60, does the over actually hit ~60% of the time? It also asks
whether the model's `totals_edge` identifies genuinely mispriced games, via TWO
complementary lenses (per the Story 10.4 design decision):

  * ROI proxy  — realized win-rate / ROI at -110 of following the edge signal on
                 all Bovada-line games (large coverage, but realized P&L is noisy).
  * True CLV   — did the model-direction bet, placed at the BOVADA line, beat
                 PINNACLE's (sharper) closing total? (cross-book line-CLV; partial
                 coverage — documented per bucket.)

The three-case agreement read (user framework):
  both positive            → strong validation, edge is real AND profitable.
  CLV+ / ROI≈0             → edge real, outcomes noisy; be patient, not abandon.
  ROI+ / CLV≈0             → profitable now but not from line-beating; suspect
                             variance/over-fit, not sustainable. (the concerning one)

Scoring reuses `score_totals_layer3.score_games()` (the 10.3 engine). The heavy
score-all-games run is HANDED OFF (>1 min). The pure metric functions are
unit-tested offline.

Calibration is computed entirely from the in-memory scored frame, so it does NOT
require the `daily_model_predictions` column backfill (spec task 1). That backfill
writes onto live prediction rows — which `model_version`, insert vs. update — which
is a production-wiring decision, so it is consolidated into Story 10.7 alongside the
`predict_today --model-source layer3` routing (same deferral 10.3 made). Deviation D1.

Outputs:
  * ablation_results/totals_v1_reliability_diagram.md  (reliability, ECE, Brier, CLV)
  * model_registry.yaml -> layer3_totals.calibration_results
  * betting_ml/models/layer3/totals_v1_platt.json  (only if raw ECE > gate)
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.scripts.load_layer3_features import _schemas  # noqa: E402
from betting_ml.scripts.score_totals_layer3 import score_games  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

_REGISTRY_PATH = _PROJECT_ROOT / "betting_ml" / "models" / "model_registry.yaml"
_REPORT_PATH = _PROJECT_ROOT / "quant_sports_intel_models" / "baseball" / "ablation_results" / "totals_v1_reliability_diagram.md"
_PLATT_PATH = _PROJECT_ROOT / "betting_ml" / "models" / "layer3" / "totals_v1_platt.json"

_ECE_GATE = 0.05
_EDGE_STRONG = 0.03            # |edge| threshold for a "strong" directional pick
_ROI_PAYOUT = 100.0 / 110.0    # win profit per 1u staked at -110
_SCORE_BATCH = 1500            # game_pks per score_games call (keeps the IN-list sane)


# ---------------------------------------------------------------------------
# Pure metric functions (unit-tested offline — no Snowflake)
# ---------------------------------------------------------------------------

def reliability_table(p: np.ndarray, y: np.ndarray, n_bins: int = 10) -> pd.DataFrame:
    """10 equal-width P(over) bins → mean predicted vs actual over-hit fraction."""
    p = np.asarray(p, dtype=float)
    y = np.asarray(y, dtype=float)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    # rightmost bin inclusive of 1.0
    idx = np.clip(np.digitize(p, edges[1:-1], right=False), 0, n_bins - 1)
    rows = []
    for b in range(n_bins):
        m = idx == b
        n = int(m.sum())
        rows.append({
            "bin": f"[{edges[b]:.2f}, {edges[b + 1]:.2f}{']' if b == n_bins - 1 else ')'}",
            "n": n,
            "mean_pred": float(p[m].mean()) if n else np.nan,
            "frac_over": float(y[m].mean()) if n else np.nan,
            "gap": float(p[m].mean() - y[m].mean()) if n else np.nan,
        })
    return pd.DataFrame(rows)


def expected_calibration_error(p: np.ndarray, y: np.ndarray, n_bins: int = 10) -> float:
    """ECE = Σ (n_b/N) · |mean_pred_b − frac_actual_b|."""
    tbl = reliability_table(p, y, n_bins)
    tbl = tbl[tbl["n"] > 0]
    w = tbl["n"] / tbl["n"].sum()
    return float((w * (tbl["mean_pred"] - tbl["frac_over"]).abs()).sum())


def brier_score(p: np.ndarray, y: np.ndarray) -> float:
    p = np.asarray(p, dtype=float)
    y = np.asarray(y, dtype=float)
    return float(np.mean((p - y) ** 2))


def fit_platt(p: np.ndarray, y: np.ndarray) -> dict:
    """Platt scaling: logistic on the predicted P(over) logit. Returns {a, b}.

    calibrated = sigmoid(a · logit(p) + b). Applied only if raw ECE > gate.
    """
    from sklearn.linear_model import LogisticRegression
    p = np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)
    z = np.log(p / (1 - p)).reshape(-1, 1)
    lr = LogisticRegression(C=1e6, solver="lbfgs")
    lr.fit(z, np.asarray(y, dtype=int))
    return {"a": float(lr.coef_[0][0]), "b": float(lr.intercept_[0])}


def apply_platt(p: np.ndarray, params: dict) -> np.ndarray:
    p = np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)
    z = np.log(p / (1 - p))
    return 1.0 / (1.0 + np.exp(-(params["a"] * z + params["b"])))


def roi_proxy_by_bucket(df: pd.DataFrame) -> pd.DataFrame:
    """Realized win-rate / ROI at -110 of following the edge signal, per edge bucket.

    Direction = over when edge > 0, under when edge < 0. A pick "wins" when the
    realized total lands on the bet's side (pushes excluded upstream). ROI per 1u:
    win → +_ROI_PAYOUT, loss → −1.
    """
    out = []
    for label, mask in _edge_buckets(df["totals_edge"]):
        g = df[mask]
        if g.empty:
            out.append({"bucket": label, "n": 0, "win_rate": np.nan, "roi": np.nan})
            continue
        bet_over = g["totals_edge"] > 0
        won = np.where(bet_over, g["over_hit"] == 1, g["over_hit"] == 0)
        roi = np.where(won, _ROI_PAYOUT, -1.0)
        out.append({
            "bucket": label, "n": int(len(g)),
            "win_rate": float(won.mean()),
            "roi": float(roi.mean()),
        })
    return pd.DataFrame(out)


def true_clv_by_bucket(df: pd.DataFrame) -> pd.DataFrame:
    """Cross-book line CLV vs the Pinnacle close, per edge bucket (partial coverage).

    For an OVER bet at the Bovada line `L_bov`, CLV-positive when Pinnacle's closing
    total `L_pin` > `L_bov` (we hold the over at a lower number). For an UNDER bet,
    CLV-positive when `L_pin < L_bov`. Reported as signed runs in the bet direction
    (`clv_runs`) and as an implied-prob delta (`clv_prob`) using Pinnacle's posted
    over/under prices when present (else line-only). Coverage = share of bucket
    games carrying a Pinnacle total.
    """
    out = []
    for label, mask in _edge_buckets(df["totals_edge"]):
        g = df[mask]
        n_bucket = int(len(g))
        cov = g.dropna(subset=["pinnacle_total"])
        if cov.empty:
            out.append({"bucket": label, "n": n_bucket, "n_clv": 0,
                        "coverage": 0.0, "mean_clv_runs": np.nan, "pct_clv_pos": np.nan})
            continue
        bet_over = cov["totals_edge"] > 0
        # signed line move in the bet's favor (runs)
        clv_runs = np.where(bet_over,
                            cov["pinnacle_total"] - cov["bovada_line"],
                            cov["bovada_line"] - cov["pinnacle_total"])
        out.append({
            "bucket": label, "n": n_bucket, "n_clv": int(len(cov)),
            "coverage": float(len(cov) / n_bucket) if n_bucket else np.nan,
            "mean_clv_runs": float(np.mean(clv_runs)),
            "pct_clv_pos": float(np.mean(clv_runs > 0)),
        })
    return pd.DataFrame(out)


def _edge_buckets(edge: pd.Series):
    e = pd.to_numeric(edge, errors="coerce")
    yield f"strong over (edge > +{_EDGE_STRONG})", e > _EDGE_STRONG
    yield f"near-zero (|edge| <= {_EDGE_STRONG})", e.abs() <= _EDGE_STRONG
    yield f"strong under (edge < -{_EDGE_STRONG})", e < -_EDGE_STRONG


# ---------------------------------------------------------------------------
# Snowflake loaders (HAND OFF the full run — these scan 2021–2025)
# ---------------------------------------------------------------------------

def load_calibration_universe(start_year: int, end_year: int, env: str) -> pd.DataFrame:
    """Regular-season played games with Layer 3 signals → game_pk, total_runs, dates."""
    from betting_ml.utils.data_loader import get_snowflake_connection
    features_schema, mart_schema = _schemas(env)
    sql = f"""
        select g.game_pk,
               g.game_date,
               g.game_year,
               (g.home_final_score + g.away_final_score) as total_runs
        from {mart_schema}.mart_game_results g
        where g.game_type = 'R'
          and g.game_year between {int(start_year)} and {int(end_year)}
          and g.home_final_score is not null
          and g.away_final_score is not null
          and exists (
              select 1 from {features_schema}.feature_pregame_sub_model_signals f
              where f.game_pk = g.game_pk
          )
    """
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql)
        cols = [d[0].lower() for d in cur.description]
        df = pd.DataFrame(cur.fetchall(), columns=cols)
    finally:
        conn.close()
    df["total_runs"] = pd.to_numeric(df["total_runs"], errors="coerce")
    log.info("Calibration universe: %d reg-season games %d-%d", len(df), start_year, end_year)
    return df


def load_pinnacle_close_totals(env: str) -> pd.DataFrame:
    """Pinnacle closing total (+ over/under prices) per game_pk — the sharp reference.

    Pinnacle carries ~1 snapshot per game for totals, treated as the close. Returns
    game_pk, pinnacle_total, pin_over_price, pin_under_price.
    """
    from betting_ml.utils.data_loader import get_snowflake_connection
    _, _ = _schemas(env)
    sql = """
        with ranked as (
            select game_pk, total_line, over_price, under_price,
                   row_number() over (partition by game_pk order by snapshot_ts desc) as rn
            from baseball_data.oddsapi.odds_snapshots_historical
            where lower(bookmaker) = 'pinnacle' and total_line is not null
        )
        select game_pk,
               total_line  as pinnacle_total,
               over_price  as pin_over_price,
               under_price as pin_under_price
        from ranked where rn = 1
    """
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql)
        cols = [d[0].lower() for d in cur.description]
        df = pd.DataFrame(cur.fetchall(), columns=cols)
    finally:
        conn.close()
    for c in ("pinnacle_total", "pin_over_price", "pin_under_price"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    log.info("Pinnacle close totals: %d games", len(df))
    return df


def score_in_batches(game_pks: list[int], env: str) -> pd.DataFrame:
    """score_games over chunks to keep the Snowflake IN-list bounded."""
    frames = []
    for i in range(0, len(game_pks), _SCORE_BATCH):
        chunk = game_pks[i:i + _SCORE_BATCH]
        log.info("Scoring batch %d-%d / %d", i, i + len(chunk), len(game_pks))
        frames.append(score_games(chunk, env=env))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def build_scored_frame(start_year: int, end_year: int, env: str) -> pd.DataFrame:
    """Score every universe game and attach actuals + the Pinnacle reference."""
    universe = load_calibration_universe(start_year, end_year, env)
    scored = score_in_batches(universe["game_pk"].astype(int).tolist(), env)
    pin = load_pinnacle_close_totals(env)

    df = (scored
          .merge(universe[["game_pk", "total_runs", "game_date", "game_year"]], on="game_pk", how="left")
          .merge(pin, on="game_pk", how="left"))

    # over_hit defined only on games with a line, a prob, and a non-push outcome.
    df["over_hit"] = np.where(df["total_runs"] > df["bovada_line"], 1,
                              np.where(df["total_runs"] < df["bovada_line"], 0, np.nan))
    return df


def run(start_year: int, end_year: int, env: str, bovada_only: bool = True,
        write_registry: bool = True) -> dict:
    df = build_scored_frame(start_year, end_year, env)

    n_total = len(df)
    n_consensus = int((df["total_line_source"] == "consensus_fallback").sum())
    # Headline calibration = Bovada-line games with a settled (non-push) outcome.
    cal = df[(df["totals_p_over"].notna()) & (df["over_hit"].notna())].copy()
    if bovada_only:
        cal = cal[cal["total_line_source"] == "bovada"].copy()

    p = cal["totals_p_over"].to_numpy(dtype=float)
    y = cal["over_hit"].to_numpy(dtype=float)

    rel = reliability_table(p, y)
    ece = expected_calibration_error(p, y)
    brier = brier_score(p, y)
    brier_naive = brier_score(np.full_like(p, 0.5), y)
    bov_mask = cal["bovada_devig_over_prob"].notna()
    brier_bovada = (brier_score(cal.loc[bov_mask, "bovada_devig_over_prob"].to_numpy(float),
                                y[bov_mask.to_numpy()]) if bov_mask.any() else np.nan)

    platt = None
    ece_after = None
    if ece > _ECE_GATE:
        platt = fit_platt(p, y)
        ece_after = expected_calibration_error(apply_platt(p, platt), y)
        _PLATT_PATH.parent.mkdir(parents=True, exist_ok=True)
        _PLATT_PATH.write_text(yaml.safe_dump(platt))
        log.warning("ECE %.4f > %.2f → fit Platt (ECE after %.4f), saved %s",
                    ece, _ECE_GATE, ece_after, _PLATT_PATH)

    roi = roi_proxy_by_bucket(cal)
    clv = true_clv_by_bucket(cal)

    # Low-coverage → wider-CI empirical check (9.3/10.3 carry-over).
    cal["ci_width"] = cal["totals_p_over_ci_high"] - cal["totals_p_over_ci_low"]
    cov_corr = float(cal[["combined_sigma", "ci_width"]].notna().all(axis=1).pipe(
        lambda m: np.corrcoef(cal.loc[m, "combined_sigma"], cal.loc[m, "ci_width"])[0, 1]
    )) if len(cal) > 2 else np.nan

    metrics = {
        "n_scored": n_total,
        "n_consensus_fallback": n_consensus,
        "n_calibration": int(len(cal)),
        "ece": round(ece, 4),
        "ece_gate": _ECE_GATE,
        "ece_pass": bool(ece <= _ECE_GATE),
        "ece_after_platt": (round(ece_after, 4) if ece_after is not None else None),
        "platt": platt,
        "brier": round(brier, 4),
        "brier_naive_0p50": round(brier_naive, 4),
        "brier_bovada_devig": (None if np.isnan(brier_bovada) else round(brier_bovada, 4)),
        "beats_naive": bool(brier < brier_naive),
        "beats_bovada": (None if np.isnan(brier_bovada) else bool(brier < brier_bovada)),
        "sigma_ci_corr": (None if np.isnan(cov_corr) else round(cov_corr, 3)),
    }
    _write_report(metrics, rel, roi, clv, env, start_year, end_year)
    if write_registry:
        _update_registry(metrics, start_year, end_year)
    log.info("Calibration done: ECE %.4f (pass=%s), Brier %.4f vs naive %.4f / bovada %s",
             ece, metrics["ece_pass"], brier, brier_naive, metrics["brier_bovada_devig"])
    return {"metrics": metrics, "reliability": rel, "roi": roi, "clv": clv, "frame": df}


def _md_table(df: pd.DataFrame) -> str:
    return df.to_markdown(index=False, floatfmt=".4f")


def _write_report(metrics, rel, roi, clv, env, start_year, end_year) -> None:
    g = metrics
    lines = [
        "# Totals v1 — Calibration & Reliability (Story 10.4)",
        "",
        f"- **Window:** {start_year}–{end_year} regular season · env=`{env}`",
        f"- **Scored games:** {g['n_scored']} ({g['n_consensus_fallback']} consensus-fallback excluded from headline)",
        f"- **Calibration set (Bovada-line, settled):** {g['n_calibration']}",
        "",
        "## Calibration",
        f"- **ECE:** {g['ece']:.4f} (gate ≤ {g['ece_gate']}) → **{'PASS' if g['ece_pass'] else 'FAIL'}**"
        + (f"; after Platt **{g['ece_after_platt']:.4f}**" if g["ece_after_platt"] is not None else ""),
        f"- **Brier:** {g['brier']:.4f} vs naive-0.50 {g['brier_naive_0p50']:.4f} "
        f"({'beats' if g['beats_naive'] else 'does NOT beat'} naive) · "
        f"vs Bovada de-vig {g['brier_bovada_devig']} "
        f"({'beats' if g['beats_bovada'] else 'does NOT beat' if g['beats_bovada'] is not None else 'n/a'} Bovada)",
        f"- **σ ↔ CI-width corr:** {g['sigma_ci_corr']} (positive ⇒ wider CIs on higher-σ/low-coverage games — the 9.3/10.3 check)",
        "",
        "### Reliability diagram (10 bins)",
        _md_table(rel),
        "",
        "## Edge → outcome (two lenses)",
        "### ROI proxy (realized, −110, all Bovada-line games)",
        _md_table(roi),
        "",
        "### True CLV vs Pinnacle close (cross-book, partial coverage)",
        _md_table(clv),
        "",
        "### Three-case agreement read",
        "- **Both +** → strong validation: model finds good numbers *and* they win above break-even; supports scaling.",
        "- **CLV + / ROI ≈ 0** → edge is real, outcomes noisy; be patient (ROI should converge), don't abandon.",
        "- **ROI + / CLV ≈ 0** → profitable now but not from line-beating; suspect variance/over-fit — *not* sustainable if the market is right.",
        "",
        "_True-CLV coverage is partial (Pinnacle pairing < 100%); interpret each bucket against its `coverage` column._",
        "",
        "## Acceptance criteria",
        f"- [{'x' if g['ece_pass'] else ' '}] ECE ≤ 0.05 (else Platt applied & re-checked)",
        f"- [{'x' if g['beats_naive'] else ' '}] Brier beats naive 0.50; vs Bovada de-vig documented "
        f"({'beats' if g['beats_bovada'] else 'does not beat — defer to Epic 12 gate' if g['beats_bovada'] is not None else 'n/a'})",
        "- [ ] Reliability shows no systematic bias (inspect `gap` column above)",
        "- [ ] `edge > +0.03` bucket shows positive mean CLV / ROI (see tables)",
    ]
    _REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    _REPORT_PATH.write_text("\n".join(lines) + "\n")
    log.info("Wrote %s", _REPORT_PATH)


def _update_registry(metrics, start_year, end_year) -> None:
    reg = yaml.safe_load(_REGISTRY_PATH.read_text()) or {}
    entry = reg.setdefault("layer3_totals", {})
    entry["calibration_results"] = {
        "story": "10.4",
        "window": f"{start_year}-{end_year} regular season",
        "n_calibration_games": metrics["n_calibration"],
        "ece": metrics["ece"],
        "ece_pass": metrics["ece_pass"],
        "ece_after_platt": metrics["ece_after_platt"],
        "platt": metrics["platt"],
        "brier": metrics["brier"],
        "brier_naive_0p50": metrics["brier_naive_0p50"],
        "brier_bovada_devig": metrics["brier_bovada_devig"],
        "beats_naive": metrics["beats_naive"],
        "beats_bovada": metrics["beats_bovada"],
        "sigma_ci_corr": metrics["sigma_ci_corr"],
        "report": "ablation_results/totals_v1_reliability_diagram.md",
        "evaluated": pd.Timestamp.utcnow().strftime("%Y-%m-%d"),
    }
    _REGISTRY_PATH.write_text(yaml.safe_dump(reg, sort_keys=False, default_flow_style=False))
    log.info("Updated %s -> layer3_totals.calibration_results", _REGISTRY_PATH)


def main() -> None:
    p = argparse.ArgumentParser(description="Story 10.4 — totals_v1 historical calibration")
    p.add_argument("--env", choices=["prod", "dev"], default="prod")
    p.add_argument("--start-year", type=int, default=2021)
    p.add_argument("--end-year", type=int, default=2025)
    p.add_argument("--include-consensus", action="store_true",
                   help="include consensus-fallback lines in the headline set (default: Bovada-only)")
    p.add_argument("--no-registry", action="store_true", help="skip writing model_registry.yaml")
    args = p.parse_args()
    run(args.start_year, args.end_year, args.env,
        bovada_only=not args.include_consensus, write_registry=not args.no_registry)


if __name__ == "__main__":
    main()
