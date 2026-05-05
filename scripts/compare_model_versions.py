"""Champion/challenger model comparison tool.

Queries daily_model_predictions for two model_version tags, joins to game
outcomes, computes side-by-side metrics, and prints a PROMOTE / DO NOT PROMOTE /
INCONCLUSIVE verdict.

Usage:
    uv run python scripts/compare_model_versions.py \\
        --champion v0 --challenger v1 \\
        --start-date 2024-04-01 --end-date 2026-05-04 \\
        --output-md betting_ml/evaluation/model_comparison_v0_v1.md
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from betting_ml.utils.data_loader import get_snowflake_connection

# ---------------------------------------------------------------------------
# Thresholds for the promotion verdict
# ---------------------------------------------------------------------------

_EDGE_IMPROVE_MIN   = 0.0      # challenger must strictly beat champion
_BRIER_REGRESS_MAX  = 0.002    # challenger Brier can be at most +0.002 worse
_MIN_ODDS_GAMES     = 100      # below this, INCONCLUSIVE regardless

# ---------------------------------------------------------------------------
# Snowflake queries
# ---------------------------------------------------------------------------

_PREDICTIONS_QUERY = """
SELECT
    p.game_pk,
    p.game_date,
    YEAR(p.game_date)                   AS season,
    p.model_version,
    p.feature_version,
    p.has_odds,
    p.calibrated_win_prob,
    p.h2h_edge,
    p.pred_total_runs,
    p.pred_run_diff_loc,
    p.totals_edge
FROM baseball_data.betting_ml.daily_model_predictions p
WHERE p.model_version IN (%(champion)s, %(challenger)s)
  AND p.game_date BETWEEN %(start_date)s AND %(end_date)s
"""

_OUTCOMES_QUERY = """
SELECT
    game_pk,
    home_final_score,
    away_final_score,
    (home_final_score + away_final_score)  AS actual_total_runs,
    (home_final_score - away_final_score)  AS actual_run_diff,
    home_team_won
FROM baseball_data.betting.mart_game_results
WHERE game_date BETWEEN %(start_date)s AND %(end_date)s
"""


def _load_data(champion: str, challenger: str, start_date: str, end_date: str) -> pd.DataFrame:
    params = {
        "champion":   champion,
        "challenger": challenger,
        "start_date": start_date,
        "end_date":   end_date,
    }
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()

        cur.execute(_PREDICTIONS_QUERY, params)
        cols_p = [d[0].lower() for d in cur.description]
        preds = pd.DataFrame(cur.fetchall(), columns=cols_p)

        cur.execute(_OUTCOMES_QUERY, {"start_date": start_date, "end_date": end_date})
        cols_o = [d[0].lower() for d in cur.description]
        outcomes = pd.DataFrame(cur.fetchall(), columns=cols_o)
    finally:
        conn.close()

    if preds.empty:
        return preds

    df = preds.merge(outcomes, on="game_pk", how="left")
    return df


# ---------------------------------------------------------------------------
# Metric computation
# ---------------------------------------------------------------------------

def _brier(df: pd.DataFrame) -> float | None:
    mask = df["home_team_won"].notna() & df["calibrated_win_prob"].notna()
    if mask.sum() == 0:
        return None
    actual = df.loc[mask, "home_team_won"].astype(float)
    pred   = df.loc[mask, "calibrated_win_prob"].astype(float)
    return float(((pred - actual) ** 2).mean())


def _totals_mae(df: pd.DataFrame) -> float | None:
    mask = df["actual_total_runs"].notna() & df["pred_total_runs"].notna()
    if mask.sum() == 0:
        return None
    return float((df.loc[mask, "pred_total_runs"] - df.loc[mask, "actual_total_runs"]).abs().mean())


def _run_diff_mae(df: pd.DataFrame) -> float | None:
    mask = df["actual_run_diff"].notna() & df["pred_run_diff_loc"].notna()
    if mask.sum() == 0:
        return None
    return float((df.loc[mask, "pred_run_diff_loc"] - df.loc[mask, "actual_run_diff"]).abs().mean())


def _compute_metrics(df: pd.DataFrame) -> dict:
    odds_df = df[df["has_odds"].fillna(False).astype(bool)]
    h2h_edge_vals = odds_df["h2h_edge"].dropna()

    return {
        "n_games":        len(df),
        "n_odds_games":   len(odds_df),
        "mean_h2h_edge":  float(h2h_edge_vals.mean()) if len(h2h_edge_vals) > 0 else None,
        "pct_positive":   float((h2h_edge_vals > 0).mean() * 100) if len(h2h_edge_vals) > 0 else None,
        "brier":          _brier(df),
        "totals_mae":     _totals_mae(df),
        "run_diff_mae":   _run_diff_mae(df),
    }


def _fmt(v: float | None, decimals: int = 4) -> str:
    if v is None:
        return "—"
    return f"{v:.{decimals}f}"


def _fmt_pct(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{v:.1f}%"


# ---------------------------------------------------------------------------
# Report building
# ---------------------------------------------------------------------------

def _build_report(
    df: pd.DataFrame,
    champion: str,
    challenger: str,
    start_date: str,
    end_date: str,
) -> str:
    lines: list[str] = []

    lines.append(f"# Model Comparison: {champion} (champion) vs {challenger} (challenger)")
    lines.append(f"\nGenerated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append(f"Window: {start_date} → {end_date}\n")

    # Per-season breakdown
    lines.append("## Per-Season Metrics\n")
    lines.append("| Season | Model | N | N_Odds | Mean_H2H_Edge | Pct_Pos | Brier | Tot_MAE | RunDiff_MAE |")
    lines.append("|--------|-------|---|--------|---------------|---------|-------|---------|-------------|")

    seasons = sorted(df["season"].dropna().unique().astype(int))
    season_metrics: dict[tuple, dict] = {}

    for season in seasons:
        for tag in [champion, challenger]:
            sub = df[(df["season"] == season) & (df["model_version"] == tag)]
            if sub.empty:
                continue
            m = _compute_metrics(sub)
            season_metrics[(season, tag)] = m
            lines.append(
                f"| {season} | {tag} | {m['n_games']} | {m['n_odds_games']} "
                f"| {_fmt(m['mean_h2h_edge'])} | {_fmt_pct(m['pct_positive'])} "
                f"| {_fmt(m['brier'])} | {_fmt(m['totals_mae'], 3)} | {_fmt(m['run_diff_mae'], 3)} |"
            )

    # 2024+ aggregate (primary evaluation window)
    lines.append("\n## 2024+ Aggregate (Primary Evaluation Window)\n")
    lines.append("| Model | N | N_Odds | Mean_H2H_Edge | Pct_Pos | Brier | Tot_MAE | RunDiff_MAE |")
    lines.append("|-------|---|--------|---------------|---------|-------|---------|-------------|")

    agg: dict[str, dict] = {}
    for tag in [champion, challenger]:
        sub = df[(df["season"] >= 2024) & (df["model_version"] == tag)]
        if sub.empty:
            agg[tag] = {}
            continue
        m = _compute_metrics(sub)
        agg[tag] = m
        lines.append(
            f"| {tag} | {m['n_games']} | {m['n_odds_games']} "
            f"| {_fmt(m['mean_h2h_edge'])} | {_fmt_pct(m['pct_positive'])} "
            f"| {_fmt(m['brier'])} | {_fmt(m['totals_mae'], 3)} | {_fmt(m['run_diff_mae'], 3)} |"
        )

    # Verdict
    champ_m = agg.get(champion, {})
    chall_m = agg.get(challenger, {})

    lines.append("\n## Promotion Verdict\n")

    champ_edge  = champ_m.get("mean_h2h_edge")
    chall_edge  = chall_m.get("mean_h2h_edge")
    champ_brier = champ_m.get("brier")
    chall_brier = chall_m.get("brier")
    n_odds      = chall_m.get("n_odds_games", 0) or 0

    verdict_lines: list[str] = []

    if n_odds < _MIN_ODDS_GAMES:
        verdict = "INCONCLUSIVE"
        verdict_lines.append(
            f"Insufficient odds-game sample for {challenger} "
            f"(n_odds_games={n_odds} < {_MIN_ODDS_GAMES} required)."
        )
    elif chall_edge is None or champ_edge is None:
        verdict = "INCONCLUSIVE"
        verdict_lines.append("Cannot compute mean_h2h_edge for one or both versions.")
    else:
        edge_improves  = chall_edge > champ_edge + _EDGE_IMPROVE_MIN
        brier_ok       = (
            chall_brier is None
            or champ_brier is None
            or chall_brier <= champ_brier + _BRIER_REGRESS_MAX
        )
        brier_regresses = (
            chall_brier is not None
            and champ_brier is not None
            and chall_brier > champ_brier + _BRIER_REGRESS_MAX
        )

        if edge_improves and brier_ok:
            verdict = "PROMOTE"
            verdict_lines.append(
                f"Challenger {challenger} improves mean_h2h_edge "
                f"({_fmt(champ_edge)} → {_fmt(chall_edge)}) "
                f"without meaningful Brier regression "
                f"({_fmt(champ_brier)} → {_fmt(chall_brier)})."
            )
        elif edge_improves and brier_regresses:
            verdict = "INCONCLUSIVE"
            verdict_lines.append(
                f"Challenger {challenger} improves mean_h2h_edge "
                f"({_fmt(champ_edge)} → {_fmt(chall_edge)}) "
                f"but Brier regresses beyond threshold "
                f"({_fmt(champ_brier)} → {_fmt(chall_brier)}, "
                f"delta={_fmt(chall_brier - champ_brier)}). Investigate."
            )
        else:
            verdict = "DO NOT PROMOTE"
            verdict_lines.append(
                f"Challenger {challenger} does not improve mean_h2h_edge "
                f"({_fmt(champ_edge)} → {_fmt(chall_edge)})."
            )
            if chall_brier is not None and champ_brier is not None:
                delta_b = chall_brier - champ_brier
                verdict_lines.append(
                    f"Brier delta: {_fmt(delta_b)} "
                    f"({'improved' if delta_b < 0 else 'regressed'})."
                )

    lines.append(f"**{verdict}**\n")
    for vl in verdict_lines:
        lines.append(f"- {vl}")

    lines.append("\n### Decision thresholds")
    lines.append(f"- Edge improvement: challenger > champion + {_EDGE_IMPROVE_MIN}")
    lines.append(f"- Brier regression limit: +{_BRIER_REGRESS_MAX}")
    lines.append(f"- Minimum odds-game sample: {_MIN_ODDS_GAMES}")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare two model versions head-to-head on historical predictions."
    )
    parser.add_argument("--champion",    default="v0",  help="Champion model_version tag (default: v0)")
    parser.add_argument("--challenger",  default="v1",  help="Challenger model_version tag (default: v1)")
    parser.add_argument("--start-date",  required=True, metavar="YYYY-MM-DD")
    parser.add_argument("--end-date",    required=True, metavar="YYYY-MM-DD")
    parser.add_argument(
        "--output-md",
        default=None,
        metavar="PATH",
        help="Write markdown report to this file (default: stdout only).",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    print(f"Loading predictions: {args.champion} vs {args.challenger} "
          f"({args.start_date} → {args.end_date})...")
    df = _load_data(args.champion, args.challenger, args.start_date, args.end_date)

    if df.empty:
        print("No predictions found for the specified versions and date range.", file=sys.stderr)
        sys.exit(1)

    versions_present = df["model_version"].unique().tolist()
    for tag in [args.champion, args.challenger]:
        if tag not in versions_present:
            print(
                f"Warning: model_version='{tag}' not found in daily_model_predictions "
                f"for this date range. Run the backfill first.",
                file=sys.stderr,
            )

    print(f"Loaded {len(df):,} prediction rows "
          f"({df['game_pk'].nunique():,} unique games, "
          f"versions: {versions_present})")

    report = _build_report(df, args.champion, args.challenger, args.start_date, args.end_date)

    print("\n" + report)

    if args.output_md:
        out_path = Path(args.output_md)
        if not out_path.is_absolute():
            out_path = PROJECT_ROOT / out_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report)
        print(f"Report written to {out_path}")


if __name__ == "__main__":
    main()
