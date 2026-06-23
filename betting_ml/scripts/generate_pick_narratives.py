"""E9.13 — generate plain-English pick narratives via Snowflake Cortex.

Run AFTER predict_today.py for the same date. Reads rows where pick_explanation
is populated but pick_narrative is NULL, calls Snowflake Cortex COMPLETE
(mistral-7b), and writes pick_narrative back on the same row.

Cost guard: only processes has_odds=TRUE rows, so LLM spend is bounded to
games that actually appear on the app (~10-15 calls/day, ≈$0.05/day).

Versioning: pick_narrative is keyed to (game_pk, model_version). The predict_today
UPDATE path ensures that a post-lineup re-score NULLs pick_narrative, so this
script re-generates it automatically — no stale morning text persists.

E9.20 — side-attribution guard:
  calibrated_win_prob is ALWAYS P(home team wins). Prompts must label each
  probability by team name so the LLM can't flip home↔away attribution.
  A pre-generation consistency check skips any row where pick_side direction
  contradicts calibrated_win_prob (model data integrity guard).

Usage:
    uv run python betting_ml/scripts/generate_pick_narratives.py --date 2026-06-18
    uv run python betting_ml/scripts/generate_pick_narratives.py  # defaults to today
    uv run python betting_ml/scripts/generate_pick_narratives.py --date 2026-06-18 --dry-run
    uv run python betting_ml/scripts/generate_pick_narratives.py --date 2026-06-18 --reset-narratives
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

# 3-letter MLB abbreviations → full city+nickname.
# Mistral-7B has no baseball context; "ATH" → "Atlanta Hawks" is a real hallucination
# unless we expand abbreviations before they enter the prompt.
_MLB_ABBR_TO_FULL: dict[str, str] = {
    # AL East
    "BAL": "Baltimore Orioles",
    "BOS": "Boston Red Sox",
    "NYY": "New York Yankees",
    "TB":  "Tampa Bay Rays",
    "TBR": "Tampa Bay Rays",
    "TOR": "Toronto Blue Jays",
    # AL Central
    "CWS": "Chicago White Sox",
    "CHW": "Chicago White Sox",
    "CLE": "Cleveland Guardians",
    "DET": "Detroit Tigers",
    "KC":  "Kansas City Royals",
    "KCR": "Kansas City Royals",
    "MIN": "Minnesota Twins",
    # AL West
    "HOU": "Houston Astros",
    "LAA": "Los Angeles Angels",
    "ANA": "Los Angeles Angels",
    "ATH": "Athletics",          # Sacramento/Oakland Athletics; NOT Atlanta anything
    "OAK": "Oakland Athletics",
    "SAC": "Sacramento Athletics",
    "SEA": "Seattle Mariners",
    "TEX": "Texas Rangers",
    # NL East
    "ATL": "Atlanta Braves",
    "MIA": "Miami Marlins",
    "NYM": "New York Mets",
    "PHI": "Philadelphia Phillies",
    "WSH": "Washington Nationals",
    "WAS": "Washington Nationals",
    # NL Central
    "CHC": "Chicago Cubs",
    "CIN": "Cincinnati Reds",
    "MIL": "Milwaukee Brewers",
    "PIT": "Pittsburgh Pirates",
    "STL": "St. Louis Cardinals",
    # NL West
    "ARI": "Arizona Diamondbacks",
    "COL": "Colorado Rockies",
    "LAD": "Los Angeles Dodgers",
    "SD":  "San Diego Padres",
    "SDP": "San Diego Padres",
    "SF":  "San Francisco Giants",
    "SFG": "San Francisco Giants",
}

# Legacy/renamed team corrections applied AFTER abbreviation expansion.
_TEAM_NAME_CORRECTIONS: dict[str, str] = {
    "Indians": "Guardians",  # Cleveland renamed to Guardians in 2022
    "Oakland Athletics": "Athletics",  # franchise moved; use city-neutral name
}


def _canonical_team_name(name: str) -> str:
    """Expand MLB abbreviations and apply rename corrections."""
    if not name:
        return name
    expanded = _MLB_ABBR_TO_FULL.get(name, name)
    return _TEAM_NAME_CORRECTIONS.get(expanded, expanded)

_FETCH_QUERY_BASE = f"""
SELECT
    game_pk,
    home_team,
    away_team,
    pick,
    model_version,
    score_date,
    prediction_type,
    totals_edge,
    totals_model_prob,
    over_prob_consensus,
    total_line_consensus,
    calibrated_win_prob,
    h2h_market_implied_prob,
    layer4_h2h_decision,
    qualified_bet,
    game_conviction_score,
    sigma_tier,
    pick_explanation,
    MAX(meta_p_clv_positive) OVER (PARTITION BY game_pk) AS meta_p_clv_positive,
    MAX(meta_ci_low)         OVER (PARTITION BY game_pk) AS meta_ci_low,
    MAX(meta_ci_high)        OVER (PARTITION BY game_pk) AS meta_ci_high
FROM {_ML_SCHEMA}.daily_model_predictions
WHERE score_date = %(score_date)s
  AND pick_explanation IS NOT NULL
  AND pick_narrative IS NULL
  AND has_odds = TRUE
{{model_version_clause}}
{{game_pks_clause}}
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY game_pk
    ORDER BY
        CASE prediction_type
            WHEN 'post_lineup' THEN 1
            WHEN 'morning'     THEN 2
            ELSE                    3
        END,
        model_version DESC
) = 1
ORDER BY game_pk
"""

# E11.11 — query ALL today's best-prediction-type rows (not just NULL-narrative ones)
# for pick-delta fingerprinting.
_CURRENT_PICKS_SQL = f"""
SELECT game_pk, layer4_h2h_decision, calibrated_win_prob, pick_narrative, model_version
FROM {_ML_SCHEMA}.daily_model_predictions
WHERE score_date = %(score_date)s
  AND has_odds = TRUE
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY game_pk
    ORDER BY
        CASE prediction_type
            WHEN 'post_lineup' THEN 1
            WHEN 'morning'     THEN 2
            ELSE                    3
        END,
        model_version DESC
) = 1
"""

# Restore a cached narrative to a row whose pick_narrative was NULLed by predict_today
# (unchanged pick — no Cortex call needed).
_RESTORE_NARRATIVE_SQL = f"""
UPDATE {_ML_SCHEMA}.daily_model_predictions
SET pick_narrative = %(narrative)s
WHERE game_pk = %(game_pk)s
  AND score_date = %(score_date)s
  AND model_version = %(model_version)s
  AND pick_narrative IS NULL
"""

_RESET_NARRATIVES_SQL = f"""
UPDATE {_ML_SCHEMA}.daily_model_predictions
SET pick_narrative = NULL
WHERE score_date = %(score_date)s
"""

_UPDATE_NARRATIVE = f"""
UPDATE {_ML_SCHEMA}.daily_model_predictions
SET pick_narrative = %(narrative)s
WHERE game_pk = %(game_pk)s
  AND model_version = %(model_version)s
  AND score_date = %(score_date)s
"""


# ── E11.11 pick-delta guard helpers ──────────────────────────────────────────

def _pick_state_path(date_str: str) -> Path:
    return Path(f"/tmp/narrative_pick_state_{date_str}.json")


def _load_pick_state(date_str: str) -> dict:
    p = _pick_state_path(date_str)
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            return {}
    return {}


def _save_pick_state(date_str: str, state: dict) -> None:
    _pick_state_path(date_str).write_text(json.dumps(state))


def _pick_fingerprint(pick_side: str | None, calibrated_win_prob: float | None) -> str:
    """Stable string key for delta comparison: direction + prob rounded to 2dp."""
    side = pick_side or "unknown"
    prob = round(float(calibrated_win_prob or 0.5), 2)
    return f"{side}:{prob}"


def _query_current_picks(conn, score_date_str: str) -> dict[int, dict]:
    """Return {game_pk: row_dict} for today's best prediction rows (all has_odds=TRUE)."""
    cur = conn.cursor()
    cur.execute(_CURRENT_PICKS_SQL, {"score_date": score_date_str})
    rows = cur.fetchall()
    cols = [d[0].lower() for d in cur.description]
    return {int(r[cols.index("game_pk")]): dict(zip(cols, r)) for r in rows}


def _compute_pick_delta(
    current: dict[int, dict],
    state: dict,
) -> tuple[set[int], dict[int, dict]]:
    """Classify today's games into two buckets.

    Returns:
        changed_or_new: game_pks whose pick fingerprint differs from state (need Cortex).
        to_restore: game_pks with matching pick but NULL narrative (restore from cache).
    """
    changed_or_new: set[int] = set()
    to_restore: dict[int, dict] = {}

    for gp, row in current.items():
        fp = _pick_fingerprint(row.get("layer4_h2h_decision"), row.get("calibrated_win_prob"))
        cached = state.get(str(gp))
        if cached is None or cached.get("pick_fp") != fp:
            changed_or_new.add(gp)
        elif row.get("pick_narrative") is None and cached.get("narrative"):
            to_restore[gp] = cached

    return changed_or_new, to_restore


def _restore_cached_narratives(conn, to_restore: dict[int, dict], score_date_str: str) -> int:
    """Write cached narrative text back for unchanged-pick games without Cortex."""
    restored = 0
    for gp, cached in to_restore.items():
        narrative = cached.get("narrative")
        model_ver = cached.get("model_version")
        if not narrative or not model_ver:
            continue
        cur = conn.cursor()
        cur.execute(_RESTORE_NARRATIVE_SQL, {
            "narrative": narrative,
            "game_pk": gp,
            "score_date": score_date_str,
            "model_version": model_ver,
        })
        if cur.rowcount:
            restored += 1
    if restored:
        conn.commit()
    return restored


# ── end E11.11 helpers ────────────────────────────────────────────────────────


def _summarize_drivers(drivers: list[dict], limit: int = 4) -> str:
    """Convert top-N driver dicts to a compact text list for the prompt."""
    lines = []
    for d in drivers[:limit]:
        direction = "increases" if d.get("direction") == "increases" else "decreases"
        lines.append(f"- {d.get('label', d.get('feature', '?'))}: {direction} the prediction")
    return "\n".join(lines) if lines else "  (no drivers available)"


def _validate_pick_consistency(row: dict) -> tuple[bool, str]:
    """E9.20 guard: verify pick direction agrees with calibrated_win_prob.

    calibrated_win_prob is always P(home team wins).
    If layer4_h2h_decision == 'home', cal_win must be > 0.5 (home favored).
    If layer4_h2h_decision == 'away', cal_win must be < 0.5 (away favored).
    Returns (is_valid, reason_string).
    """
    pick_side = row.get("layer4_h2h_decision")
    cal_win = row.get("calibrated_win_prob")
    game_pk = row.get("game_pk")
    home = row.get("home_team", "?")
    away = row.get("away_team", "?")

    if pick_side is None or cal_win is None:
        return True, ""

    if pick_side == "home" and cal_win < 0.5:
        return False, (
            f"game_pk={game_pk} ({away}@{home}): pick_side=home but "
            f"calibrated_win_prob={cal_win:.3f} < 0.5 — inconsistent model data"
        )
    if pick_side == "away" and cal_win > 0.5:
        return False, (
            f"game_pk={game_pk} ({away}@{home}): pick_side=away but "
            f"calibrated_win_prob={cal_win:.3f} > 0.5 — inconsistent model data"
        )
    return True, ""


def _build_prompt(row: dict, expl: dict) -> str:
    """Construct the Cortex narrative prompt for one game row.

    E9.20: calibrated_win_prob is always P(home wins). All probabilities are
    labelled by team name in the prompt so the LLM cannot flip home↔away.
    """
    home = _canonical_team_name(row["home_team"] or "home team")
    away = _canonical_team_name(row["away_team"] or "away team")
    raw_pick = row.get("pick")
    pick_str = _canonical_team_name(raw_pick) if raw_pick else "N/A"
    score_date = str(row["score_date"])

    # Determine backed team for unambiguous LLM framing
    pick_side = row.get("layer4_h2h_decision")
    if pick_side == "home":
        model_backed_team = home
    elif pick_side == "away":
        model_backed_team = away
    else:
        model_backed_team = None
    backed_line = f"The model backs {model_backed_team} to win." if model_backed_team else ""

    # H2H section — cal_win / mkt_win are BOTH P(home wins); label by team name.
    cal_win = row.get("calibrated_win_prob")   # P(home wins)
    mkt_win = row.get("h2h_market_implied_prob")  # P(home wins)
    h2h_ev_str = ""
    if cal_win is not None and mkt_win is not None:
        # Edge matches what the pick chip displays: abs(P_home_model − P_home_market)
        edge_display = abs(cal_win - mkt_win)
        model_favors = home if cal_win >= 0.5 else away
        h2h_ev_str = (
            f"Model P({home} wins): {cal_win:.1%}.  "
            f"Model P({away} wins): {1 - cal_win:.1%}.  "
            f"Market P({home} wins): {mkt_win:.1%}.  "
            f"Market P({away} wins): {1 - mkt_win:.1%}.  "
            f"Model-vs-market divergence (edge): {edge_display:.1%} "
            f"(model favors {model_favors})."
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

    # CLV confidence — only H2H; totals CLV is explicitly low-information and omitted.
    meta_p = row.get("meta_p_clv_positive")
    meta_ci_low = row.get("meta_ci_low")
    meta_ci_high = row.get("meta_ci_high")
    clv_str = ""
    if meta_p is not None and meta_ci_low is not None and meta_ci_high is not None:
        clv_str = (
            f"CLV confidence: P(closing line moves toward model's pick) = {meta_p:.1%} "
            f"(80% credible interval: {meta_ci_low:.1%}–{meta_ci_high:.1%}). "
            f"This is a market-transparency indicator — it does not imply a winning bet."
        )

    prompt = f"""You are writing a brief, factual explanation for a baseball analytics app.
These are MLB (Major League Baseball) teams — not NBA, NFL, or any other sport.
Do NOT recommend placing a bet. Do NOT use phrases like "you should bet" or "this is a good bet."
Frame the explanation as "what drives the model's prediction" and note the EV signal (edge) as
a statistical measure — not as a guarantee of profit.
IMPORTANT: Use ONLY the exact team names given in the "Home team" and "Away team" fields below.
Do not invent, substitute, or infer other names — the exact strings below are definitive.
(e.g., if the team is called "Guardians", never write "Indians"; if it is "Athletics", never write "Hawks" or any NBA/NFL team).

Game: {away} at {home} on {score_date}.
Home team: {home}. Away team: {away}.
Model pick (moneyline): {pick_str}. {backed_line}
Prediction basis: {served_tier} features.
{f"Conviction score: {conviction:.2f} / qualified: {qualified}" if conviction is not None else ""}
{f"Confidence tier: {sigma}" if sigma else ""}

Moneyline (H2H) metrics (all probabilities labelled by team):
{h2h_ev_str or "  (no H2H market data)"}

Totals metrics:
{totals_ev_str or "  (no totals market data)"}

Top model drivers for moneyline prediction:
{hw_drivers_text or "  (not available)"}

Top model drivers for total runs prediction:
{tot_drivers_text or "  (not available)"}

CLV confidence (line-value transparency):
{clv_str or "  (not available)"}

Write 2-3 sentences explaining what these statistics mean for today's game in plain language.
Use the exact team names above and reference each team's win probability by name
(e.g. "{home}: X%, {away}: Y%"). Mention the model-vs-market edge as a measure of divergence —
it does not guarantee a winning bet. If CLV confidence is provided, mention it briefly as the
model's estimate of whether the closing line will move toward its pick — frame it as additional
context, not as a signal to place a bet. Use "what drove the model's number" framing, not "why you'll win."
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
    reset_narratives: bool = False,
    pick_delta_guard: bool = False,
) -> None:
    # E9.20: optionally wipe all narratives for the date so they regenerate cleanly.
    if reset_narratives and not dry_run:
        conn = get_snowflake_connection()
        try:
            cur = conn.cursor()
            cur.execute(_RESET_NARRATIVES_SQL, {"score_date": score_date_str})
            conn.commit()
            print(f"[E9.20] Reset {cur.rowcount} pick_narrative row(s) for {score_date_str}.")
        finally:
            conn.close()

    # E11.11 pick-delta guard: before calling Cortex, check if any picks changed
    # since the last generation cycle. If not, restore cached narratives (fast DB
    # write) and skip the Cortex calls entirely. State is keyed by date so it resets
    # naturally each day; a missing state file forces a full regeneration (first run).
    game_pks_filter: set[int] | None = None
    state = _load_pick_state(score_date_str)
    if pick_delta_guard and not reset_narratives and not dry_run:
        conn_delta = get_snowflake_connection()
        try:
            current = _query_current_picks(conn_delta, score_date_str)
        finally:
            conn_delta.close()

        if current:
            changed_or_new, to_restore = _compute_pick_delta(current, state)
            if not changed_or_new and not to_restore:
                print(f"[E11.11] Pick delta: 0 changed games, 0 pending restoration "
                      f"— skipping Cortex for {score_date_str}.")
                return

            if to_restore:
                conn_restore = get_snowflake_connection()
                try:
                    n_restored = _restore_cached_narratives(conn_restore, to_restore, score_date_str)
                finally:
                    conn_restore.close()
                print(f"[E11.11] Restored {n_restored} cached narrative(s) (pick unchanged).")

            if changed_or_new:
                game_pks_filter = changed_or_new
                print(f"[E11.11] Pick delta: {len(game_pks_filter)} game(s) changed — "
                      f"generating via Cortex.")
            else:
                print(f"[E11.11] No changed picks after restoration — done.")
                return

    mv_clause = "AND model_version = %(model_version)s" if model_version else ""
    gp_clause = ""
    if game_pks_filter:
        pks_sql = ", ".join(str(int(gp)) for gp in sorted(game_pks_filter))
        gp_clause = f"AND game_pk IN ({pks_sql})"
    fetch_query = _FETCH_QUERY_BASE.format(model_version_clause=mv_clause, game_pks_clause=gp_clause)
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
        skipped = 0
        for rec in records:
            game_pk = rec.get("game_pk")
            home = rec.get("home_team", "?")
            away = rec.get("away_team", "?")
            model_ver = rec.get("model_version", "?")
            pred_type = rec.get("prediction_type", "?")

            # E9.20 guard: skip before calling Cortex if pick direction is inconsistent.
            is_valid, reason = _validate_pick_consistency(rec)
            if not is_valid:
                print(f"  [E9.20 GUARD] SKIP — {reason}")
                skipped += 1
                continue

            expl_raw = rec.get("pick_explanation")
            try:
                expl = json.loads(expl_raw) if expl_raw else {}
            except (json.JSONDecodeError, TypeError):
                expl = {}

            prompt = _build_prompt(rec, expl)

            if dry_run:
                print(f"  [dry-run] {away} @ {home} (game_pk={game_pk}, model={model_ver}, "
                      f"type={pred_type})")
                print(f"  Prompt (first 300 chars): {prompt[:300]}…")
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
                print(f"  ✓ {away} @ {home} (game_pk={game_pk}, {pred_type}): {narrative[:80]}…")
                generated += 1
            else:
                print(f"  ✗ {away} @ {home} (game_pk={game_pk}): Cortex returned nothing")
                failed += 1

        if not dry_run:
            print(f"\n[E9.13] Done: {generated} written, {failed} failed, {skipped} guard-skipped.")
            # E11.11: update the pick-state file so the next cycle can delta-detect.
            if pick_delta_guard:
                conn_fp = get_snowflake_connection()
                try:
                    refreshed = _query_current_picks(conn_fp, score_date_str)
                finally:
                    conn_fp.close()
                new_state: dict = {}
                for gp, row in refreshed.items():
                    narrative_text = row.get("pick_narrative")
                    if narrative_text:
                        new_state[str(gp)] = {
                            "pick_fp": _pick_fingerprint(
                                row.get("layer4_h2h_decision"),
                                row.get("calibrated_win_prob"),
                            ),
                            "model_version": row.get("model_version"),
                            "narrative": narrative_text,
                        }
                # Preserve cached entries for games not present in refreshed (edge case)
                for k, v in state.items():
                    if k not in new_state:
                        new_state[k] = v
                _save_pick_state(score_date_str, new_state)
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
    parser.add_argument(
        "--reset-narratives",
        action="store_true",
        default=False,
        help=(
            "NULL out all pick_narrative rows for the target date before generating. "
            "Use after a prompt-fix to force full regeneration. Cannot be combined with --dry-run."
        ),
    )
    parser.add_argument(
        "--pick-delta-guard",
        action="store_true",
        default=False,
        help=(
            "E11.11: skip Cortex calls when picks are unchanged since last generation. "
            "Restores cached narrative text for unchanged-pick games instead. "
            "Uses /tmp/narrative_pick_state_{date}.json as the state file. "
            "Incompatible with --reset-narratives (reset forces full regeneration)."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    score_date_str = args.date or date.today().isoformat()
    generate_narratives(
        score_date_str,
        dry_run=args.dry_run,
        model_version=args.model_version,
        reset_narratives=args.reset_narratives,
        pick_delta_guard=args.pick_delta_guard,
    )


if __name__ == "__main__":
    main()
