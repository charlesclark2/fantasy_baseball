"""E9.13 — generate plain-English pick narratives via Snowflake Cortex.

Run AFTER predict_today.py for the same date. Reads rows where pick_explanation
is populated but pick_narrative is NULL, calls Snowflake Cortex COMPLETE
(mistral-7b), and writes pick_narrative back on the same row.

Cost guard: only processes has_odds=TRUE rows, so LLM spend is bounded to
games that actually appear on the app (~10-15 calls/day, ≈$0.05/day).

Versioning: pick_narrative is keyed to (game_pk, model_version). The predict_today
UPDATE path ensures that a post-lineup re-score NULLs pick_narrative, so this
script re-generates it automatically — no stale morning text persists.

Usage:
    uv run python betting_ml/scripts/generate_pick_narratives.py --date 2026-06-18
    uv run python betting_ml/scripts/generate_pick_narratives.py  # defaults to today
    uv run python betting_ml/scripts/generate_pick_narratives.py --date 2026-06-18 --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from betting_ml.utils.data_loader import get_snowflake_connection
from betting_ml.utils.ml_env import ml_schema

_ML_SCHEMA = ml_schema()

# Snowflake Cortex model — mistral-7b is cheap and sufficient for 2-3 sentence summaries.
_CORTEX_MODEL = "mistral-7b"

# Map any legacy/outdated team names to their current official names.
# Checked against MLB.com as of 2026. Add entries here when franchises rename.
_TEAM_NAME_CORRECTIONS: dict[str, str] = {
    "Indians": "Guardians",  # Cleveland renamed to Guardians in 2022
}


def _canonical_team_name(name: str) -> str:
    return _TEAM_NAME_CORRECTIONS.get(name, name)

_FETCH_QUERY_BASE = f"""
SELECT
    game_pk,
    home_team,
    away_team,
    pick,
    model_version,
    score_date,
    h2h_edge,
    totals_edge,
    totals_model_prob,
    over_prob_consensus,
    total_line_consensus,
    calibrated_win_prob,
    h2h_market_implied_prob,
    qualified_bet,
    game_conviction_score,
    sigma_tier,
    pick_explanation
FROM {_ML_SCHEMA}.daily_model_predictions
WHERE score_date = %(score_date)s
  AND pick_explanation IS NOT NULL
  AND pick_narrative IS NULL
  AND has_odds = TRUE
{{model_version_clause}}
ORDER BY game_pk
"""

_UPDATE_NARRATIVE = f"""
UPDATE {_ML_SCHEMA}.daily_model_predictions
SET pick_narrative = %(narrative)s
WHERE game_pk = %(game_pk)s
  AND model_version = %(model_version)s
  AND score_date = %(score_date)s
"""


def _summarize_drivers(drivers: list[dict], limit: int = 4) -> str:
    """Convert top-N driver dicts to a compact text list for the prompt."""
    lines = []
    for d in drivers[:limit]:
        direction = "increases" if d.get("direction") == "increases" else "decreases"
        lines.append(f"- {d.get('label', d.get('feature', '?'))}: {direction} the prediction")
    return "\n".join(lines) if lines else "  (no drivers available)"


def _build_prompt(row: dict, expl: dict) -> str:
    """Construct the Cortex narrative prompt for one game row."""
    home = _canonical_team_name(row["home_team"] or "home team")
    away = _canonical_team_name(row["away_team"] or "away team")
    pick_str = row["pick"] or "N/A"
    score_date = str(row["score_date"])

    # H2H section
    h2h_edge = row.get("h2h_edge")
    cal_win = row.get("calibrated_win_prob")
    mkt_win = row.get("h2h_market_implied_prob")
    h2h_ev_str = ""
    if h2h_edge is not None and cal_win is not None and mkt_win is not None:
        ev_sign = "+" if h2h_edge >= 0 else ""
        h2h_ev_str = (
            f"Model win probability: {cal_win:.1%}. "
            f"Market-implied: {mkt_win:.1%}. "
            f"Edge (EV signal): {ev_sign}{h2h_edge:.1%}."
        )

    # Totals section
    tot_edge = row.get("totals_edge")
    tot_model = row.get("totals_model_prob")
    tot_mkt = row.get("over_prob_consensus")
    tot_line = row.get("total_line_consensus")
    totals_ev_str = ""
    if tot_edge is not None and tot_model is not None and tot_mkt is not None:
        ev_sign = "+" if tot_edge >= 0 else ""
        totals_ev_str = (
            f"Total line: {tot_line}. "
            f"Model P(over): {tot_model:.1%}. "
            f"Market P(over): {tot_mkt:.1%}. "
            f"Edge (EV signal): {ev_sign}{tot_edge:.1%}."
        )

    # Feature drivers from SHAP payload
    targets = expl.get("targets", {})
    hw_drivers_text = ""
    tot_drivers_text = ""
    if "home_win" in targets and targets["home_win"].get("drivers"):
        hw_drivers_text = _summarize_drivers(targets["home_win"]["drivers"])
    if "total_runs" in targets and targets["total_runs"].get("drivers"):
        tot_drivers_text = _summarize_drivers(targets["total_runs"]["drivers"])

    served_tier = expl.get("served_tier", "unknown")
    conviction = row.get("game_conviction_score")
    qualified = row.get("qualified_bet")
    sigma = row.get("sigma_tier", "")

    prompt = f"""You are writing a brief, factual explanation for a baseball analytics app.
Do NOT recommend placing a bet. Do NOT use phrases like "you should bet" or "this is a good bet."
Frame the explanation as "what drives the model's prediction" and note the EV signal (edge) as
a statistical measure — not as a guarantee of profit.
IMPORTANT: Use ONLY the exact team names as given below. Do not substitute historical, previous,
or alternate franchise names (e.g., if the team is called "Guardians", never write "Indians").

Game: {away} at {home} on {score_date}.
Model pick (moneyline): {pick_str}.
Prediction basis: {served_tier} features.
{f"Conviction score: {conviction:.2f} / qualified: {qualified}" if conviction is not None else ""}
{f"Confidence tier: {sigma}" if sigma else ""}

Moneyline (H2H) metrics:
{h2h_ev_str or "  (no H2H market data)"}

Totals metrics:
{totals_ev_str or "  (no totals market data)"}

Top model drivers for moneyline prediction:
{hw_drivers_text or "  (not available)"}

Top model drivers for total runs prediction:
{tot_drivers_text or "  (not available)"}

Write 2-3 sentences explaining what these statistics mean for today's game in plain language.
Mention the EV signal (edge) as a measure of how much the model's probability differs from
the market — higher absolute edge means larger model-vs-market divergence, but does not
guarantee a winning bet. Use "what drove the model's number" framing, not "why you'll win."
"""
    return prompt.strip()


def _call_cortex(conn, prompt: str) -> str | None:
    """Call Snowflake Cortex COMPLETE and return the text response."""
    try:
        cur = conn.cursor()
        cur.execute(
            f"SELECT SNOWFLAKE.CORTEX.COMPLETE('{_CORTEX_MODEL}', %s)::VARCHAR",
            [prompt],
        )
        row = cur.fetchone()
        if row and row[0]:
            return str(row[0]).strip()
        return None
    except Exception as exc:
        print(f"    [E9.13] Cortex call failed: {exc}")
        return None


def generate_narratives(
    score_date_str: str,
    dry_run: bool = False,
    model_version: str | None = None,
) -> None:
    mv_clause = "AND model_version = %(model_version)s" if model_version else ""
    fetch_query = _FETCH_QUERY_BASE.format(model_version_clause=mv_clause)
    fetch_params: dict = {"score_date": score_date_str}
    if model_version:
        fetch_params["model_version"] = model_version

    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(fetch_query, fetch_params)
        rows = cur.fetchall()
        cols = [d[0].lower() for d in cur.description]
        records = [dict(zip(cols, r)) for r in rows]
    finally:
        conn.close()

    if not records:
        print(f"[E9.13] No eligible rows for {score_date_str} (pick_explanation populated, "
              f"pick_narrative NULL, has_odds=TRUE). Nothing to do.")
        return

    mv_label = f"model_version={model_version}" if model_version else "all model_versions"
    print(f"[E9.13] Generating narratives for {len(records)} game(s) on {score_date_str} "
          f"({mv_label}) via Cortex {_CORTEX_MODEL}{' [DRY RUN]' if dry_run else ''}")

    conn = get_snowflake_connection()
    try:
        generated = 0
        failed = 0
        for rec in records:
            game_pk = rec.get("game_pk")
            home = rec.get("home_team", "?")
            away = rec.get("away_team", "?")
            model_ver = rec.get("model_version", "?")

            expl_raw = rec.get("pick_explanation")
            try:
                expl = json.loads(expl_raw) if expl_raw else {}
            except (json.JSONDecodeError, TypeError):
                expl = {}

            prompt = _build_prompt(rec, expl)

            if dry_run:
                print(f"  [dry-run] {away} @ {home} (game_pk={game_pk}, model={model_ver})")
                print(f"  Prompt (first 200 chars): {prompt[:200]}…")
                generated += 1
                continue

            narrative = _call_cortex(conn, prompt)
            if narrative:
                cur = conn.cursor()
                cur.execute(
                    _UPDATE_NARRATIVE,
                    {
                        "narrative": narrative,
                        "game_pk": game_pk,
                        "model_version": model_ver,
                        "score_date": score_date_str,
                    },
                )
                conn.commit()
                print(f"  ✓ {away} @ {home} (game_pk={game_pk}): {narrative[:80]}…")
                generated += 1
            else:
                print(f"  ✗ {away} @ {home} (game_pk={game_pk}): Cortex returned nothing")
                failed += 1

        if not dry_run:
            print(f"\n[E9.13] Done: {generated} narrative(s) written, {failed} failed.")
    finally:
        conn.close()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--date",
        default=None,
        help="Score date to generate narratives for (YYYY-MM-DD). Defaults to today.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print prompts without calling Cortex or writing to Snowflake.",
    )
    parser.add_argument(
        "--model-version",
        default=None,
        help=(
            "Only generate narratives for this model_version (e.g. v3, pre_lineup_v1). "
            "Omit to process all versions. Recommended: pass the champion version "
            "to avoid generating narratives for every served tier."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    score_date_str = args.date or date.today().isoformat()
    generate_narratives(score_date_str, dry_run=args.dry_run, model_version=args.model_version)


if __name__ == "__main__":
    main()
