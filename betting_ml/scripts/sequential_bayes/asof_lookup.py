"""
asof_lookup.py — Leakage-safe as-of sequential posterior lookup (Epic 16.2)

THE single sequential-posterior lookup used by BOTH the historical training-feature
backfill and the daily inference path. Centralizing it here guarantees the two paths
share identical semantics and cannot drift.

LEAKAGE-CRITICAL CONTRACT — read before changing:
  The lookup selects the latest `player_sequential_posteriors` row with
  `game_date < scoring_date` (STRICT inequality). It must NEVER use `is_current`:
  `is_current` marks the season-FINAL posterior, which is correct only when scoring
  "today" (no future data exists), but catastrophic when rebuilding the 2021-2025
  training feature matrix — it would inject end-of-season information into mid-season
  games, reintroducing exactly the in-sample leakage the leakage-fix work removed.
  Strict `game_date < scoring_date` is correct and leakage-safe for BOTH paths
  (for "today", the latest completed game's posterior naturally has game_date < today).

16.2 design: parallel columns, no overwrite. Callers expose the sequential
posterior_mu in a NEW column alongside (not replacing) the static EB value, plus
`posterior_source` and `prior_age_days`. Existing models are unaffected until they
are retrained to consume the new columns.
"""

from __future__ import annotations

from datetime import date
from typing import Any

_SEQ_TABLE = "baseball_data.betting.player_sequential_posteriors"


def load_seq_posteriors_asof(
    conn,
    player_ids: list[str],
    player_type: str,
    metric: str,
    game_date: date,
    season: int,
) -> dict[str, dict]:
    """Latest sequential posterior per player STRICTLY BEFORE `game_date` (as-of).

    Args:
        player_type: 'batter' | 'starter' | 'bullpen'
        metric:      'xwoba' (batter) | 'xwoba_against' (starter/bullpen)

    Returns dict keyed by str(player_id) → {posterior_mu, posterior_sigma2,
    last_game_date (date), n_cumulative}. Players with no prior-game posterior in
    the season are absent (→ caller falls back to the static EB prior).
    """
    if not player_ids:
        return {}
    ids_sql = ", ".join(f"'{p}'" for p in player_ids)
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT player_id, posterior_mu, posterior_sigma2, game_date, n_cumulative
        FROM {_SEQ_TABLE}
        WHERE player_id IN ({ids_sql})
          AND player_type = %(player_type)s
          AND metric      = %(metric)s
          AND season      = %(season)s
          AND game_date   < %(game_date)s          -- STRICT: leakage-safe as-of
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY player_id ORDER BY game_date DESC
        ) = 1
        """,
        {"player_type": player_type, "metric": metric,
         "season": season, "game_date": game_date.isoformat()},
    )
    cols = [d[0].lower() for d in cur.description]
    out: dict[str, dict] = {}
    for row in cur.fetchall():
        r = dict(zip(cols, row))
        gd = r["game_date"]
        out[str(r["player_id"])] = {
            "posterior_mu": float(r["posterior_mu"]) if r["posterior_mu"] is not None else None,
            "posterior_sigma2": float(r["posterior_sigma2"]) if r["posterior_sigma2"] is not None else None,
            "last_game_date": gd if isinstance(gd, date) else None,
            "n_cumulative": int(r["n_cumulative"]) if r["n_cumulative"] is not None else None,
        }
    cur.close()
    return out


def resolve_posterior_source(
    seq: dict | None, eb_data_source: str | None, game_date: date,
) -> tuple[str, int | None]:
    """Map (as-of sequential row, static EB source) → (posterior_source, prior_age_days).

    posterior_source ∈ {sequential, season_eb, prior_only}:
      * sequential — an as-of sequential posterior exists (prior_age_days = days since
        its last update; high values flag stale beliefs: injury/bench/recall).
      * season_eb  — no sequential row, but the static EB used real in-season data
        (full_eb / zips_blend / il_return_blend).
      * prior_only — no sequential row and the EB fell back to the population prior.
    """
    if seq is not None and seq.get("posterior_mu") is not None:
        last = seq.get("last_game_date")
        age = (game_date - last).days if isinstance(last, date) else None
        return "sequential", age
    if eb_data_source == "prior_only":
        return "prior_only", None
    return "season_eb", None
