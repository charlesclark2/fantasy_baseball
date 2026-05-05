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

# Per-target thresholds
_PCT_POS_DROP_WARN  = 5.0      # pp drop in pct_positive triggers MONITORING flag
_PCT_OVER_WARN_LOW  = 10.0     # pct_over_edge below this flags directional bias
_PCT_OVER_WARN_HIGH = 90.0     # pct_over_edge above this flags directional bias

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


def _pct_over_edge(df: pd.DataFrame) -> float | None:
    mask = df["totals_edge"].notna()
    if mask.sum() == 0:
        return None
    return float((df.loc[mask, "totals_edge"] > 0).mean() * 100)


def _fmt(v: float | None, decimals: int = 4) -> str:
    if v is None:
        return "—"
    return f"{v:.{decimals}f}"


def _fmt_pct(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{v:.1f}%"


# ---------------------------------------------------------------------------
# Per-target verdict helpers
# ---------------------------------------------------------------------------

def _target_verdict_run_diff(champ_m: dict, chall_m: dict, champion: str, challenger: str) -> list[str]:
    lines: list[str] = []
    lines.append("\n### run_diff\n")

    c0 = champ_m.get("run_diff_mae")
    c1 = chall_m.get("run_diff_mae")
    delta = (c1 - c0) if (c0 is not None and c1 is not None) else None
    delta_str = f"{delta:+.3f}" if delta is not None else "—"

    lines.append(f"| Metric | {champion} | {challenger} | Delta |")
    lines.append("|--------|---------|---------|-------|")
    lines.append(f"| RunDiff_MAE | {_fmt(c0, 3)} | {_fmt(c1, 3)} | {delta_str} |")
    lines.append("")

    if c0 is None or c1 is None:
        lines.append("**INCONCLUSIVE** — missing run_diff_mae for one version.")
    elif c1 < c0:
        lines.append(f"**PROMOTE** — challenger improves run_diff_mae ({_fmt(c0,3)} → {_fmt(c1,3)}).")
    else:
        lines.append(f"**DO NOT PROMOTE** — challenger does not improve run_diff_mae ({_fmt(c0,3)} → {_fmt(c1,3)}).")
    return lines


def _target_verdict_home_win(champ_m: dict, chall_m: dict, champion: str, challenger: str) -> list[str]:
    lines: list[str] = []
    lines.append("\n### home_win\n")

    b0 = champ_m.get("brier")
    b1 = chall_m.get("brier")
    p0 = champ_m.get("pct_positive")
    p1 = chall_m.get("pct_positive")
    delta_b = (b1 - b0) if (b0 is not None and b1 is not None) else None
    delta_p = (p1 - p0) if (p0 is not None and p1 is not None) else None

    lines.append(f"| Metric | {champion} | {challenger} | Delta |")
    lines.append("|--------|---------|---------|-------|")
    lines.append(f"| Brier | {_fmt(b0)} | {_fmt(b1)} | {f'{delta_b:+.4f}' if delta_b is not None else '—'} |")
    lines.append(f"| Pct_Positive | {_fmt_pct(p0)} | {_fmt_pct(p1)} | {f'{delta_p:+.1f} pp' if delta_p is not None else '—'} |")
    lines.append("")

    if b0 is None or b1 is None:
        lines.append("**INCONCLUSIVE** — missing Brier for one version.")
        return lines

    brier_improves = b1 < b0
    brier_regresses = (b1 - b0) > _BRIER_REGRESS_MAX
    pct_drops = (delta_p is not None and delta_p < -_PCT_POS_DROP_WARN)

    if brier_regresses:
        lines.append(
            f"**DO NOT PROMOTE** — Brier regresses beyond threshold "
            f"({_fmt(b0)} → {_fmt(b1)}, delta={_fmt(b1-b0)})."
        )
    elif brier_improves and not pct_drops:
        lines.append(f"**PROMOTE** — Brier improves ({_fmt(b0)} → {_fmt(b1)}) with no selectivity concern.")
    else:
        lines.append(
            f"**PROMOTE WITH MONITORING** — Brier {'improves' if brier_improves else 'is flat'} "
            f"({_fmt(b0)} → {_fmt(b1)}) but Pct_Positive dropped "
            f"{abs(delta_p):.1f} pp ({_fmt_pct(p0)} → {_fmt_pct(p1)}). "
            "Monitor live selectivity."
        )
    return lines


def _target_verdict_total_runs(champ_m: dict, chall_m: dict, champion: str, challenger: str,
                                champ_df: pd.DataFrame, chall_df: pd.DataFrame) -> list[str]:
    lines: list[str] = []
    lines.append("\n### total_runs\n")

    t0 = champ_m.get("totals_mae")
    t1 = chall_m.get("totals_mae")
    poe0 = _pct_over_edge(champ_df)
    poe1 = _pct_over_edge(chall_df)
    delta_t = (t1 - t0) if (t0 is not None and t1 is not None) else None

    lines.append(f"| Metric | {champion} | {challenger} | Delta |")
    lines.append("|--------|---------|---------|-------|")
    lines.append(f"| Tot_MAE | {_fmt(t0, 3)} | {_fmt(t1, 3)} | {f'{delta_t:+.3f}' if delta_t is not None else '—'} |")
    lines.append(f"| Pct_Over_Edge | {_fmt_pct(poe0)} | {_fmt_pct(poe1)} | — |")
    lines.append("")

    if t0 is None or t1 is None:
        lines.append("**INCONCLUSIVE** — missing totals_mae for one version.")
        return lines

    mae_improves = t1 < t0
    bias_flag = (
        poe1 is not None
        and (poe1 < _PCT_OVER_WARN_LOW or poe1 > _PCT_OVER_WARN_HIGH)
    )

    if mae_improves and not bias_flag:
        lines.append(f"**PROMOTE** — challenger improves Tot_MAE ({_fmt(t0,3)} → {_fmt(t1,3)}).")
    elif mae_improves and bias_flag:
        direction = "under" if poe1 < 50 else "over"
        lines.append(
            f"**PROMOTE WITH MONITORING** — challenger improves Tot_MAE ({_fmt(t0,3)} → {_fmt(t1,3)}) "
            f"but shows directional bias: Pct_Over_Edge={_fmt_pct(poe1)} "
            f"(model predicts {direction} on {100-poe1:.1f}% of games). "
            "Investigate bias before relying on totals betting signal."
        )
    else:
        lines.append(
            f"**DO NOT PROMOTE** — challenger does not improve Tot_MAE ({_fmt(t0,3)} → {_fmt(t1,3)})."
        )
        if bias_flag:
            direction = "under" if poe1 < 50 else "over"
            lines.append(
                f"  Additional concern: Pct_Over_Edge={_fmt_pct(poe1)} "
                f"(directional bias toward {direction})."
            )
    return lines


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

    # Per-target verdicts (2024+)
    lines.append("\n---\n")
    lines.append("## Per-Target Verdicts (2024+)\n")
    champ_df_2024 = df[(df["season"] >= 2024) & (df["model_version"] == champion)]
    chall_df_2024 = df[(df["season"] >= 2024) & (df["model_version"] == challenger)]
    lines.extend(_target_verdict_run_diff(champ_m, chall_m, champion, challenger))
    lines.extend(_target_verdict_home_win(champ_m, chall_m, champion, challenger))
    lines.extend(_target_verdict_total_runs(champ_m, chall_m, champion, challenger,
                                             champ_df_2024, chall_df_2024))

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
