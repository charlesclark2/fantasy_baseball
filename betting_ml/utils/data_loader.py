from __future__ import annotations

import os
import re
from typing import Any

import pandas as pd
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
import snowflake.connector

_KEY_PATH = os.environ.get("SNOWFLAKE_PRIVATE_KEY_PATH") or os.path.expanduser(
    "~/Documents/machine_learning/baseball/betting_model/jaffle_shop/rsa_key.pem"
)

_QUERY = """
SELECT
    f.*,
    r.home_final_score + r.away_final_score                        AS total_runs,
    r.home_final_score - r.away_final_score                        AS run_differential,
    CASE WHEN r.home_final_score > r.away_final_score THEN 1 ELSE 0 END AS home_win
FROM baseball_data.betting_features.feature_pregame_game_features f
JOIN baseball_data.betting.mart_game_results r USING (game_pk)
WHERE f.has_full_data = TRUE
  AND LEAST(f.home_games_played, f.away_games_played) >= {min_games_played}
  AND f.game_year >= {min_year}
"""

_TODAY_QUERY = """
SELECT f.*
FROM baseball_data.betting_features.feature_pregame_game_features f
WHERE f.game_date = '{target_date}'
"""

_LATEST_HOME_QUERY = """
WITH ranked AS (
  SELECT *,
         ROW_NUMBER() OVER (PARTITION BY home_team ORDER BY game_date DESC, game_pk DESC) AS rn
  FROM baseball_data.betting_features.feature_pregame_game_features
  WHERE home_team IN ({team_list})
    AND game_year >= 2021
)
SELECT * FROM ranked WHERE rn = 1
"""

_LATEST_AWAY_QUERY = """
WITH ranked AS (
  SELECT *,
         ROW_NUMBER() OVER (PARTITION BY away_team ORDER BY game_date DESC, game_pk DESC) AS rn
  FROM baseball_data.betting_features.feature_pregame_game_features
  WHERE away_team IN ({team_list})
    AND game_year >= 2021
)
SELECT * FROM ranked WHERE rn = 1
"""

_TODAY_ODDS_QUERY = """
WITH latest_per_book AS (
    SELECT *,
           ROW_NUMBER() OVER (
               PARTITION BY event_id, bookmaker_key, market_key, outcome_name
               ORDER BY ingestion_ts DESC
           ) AS rn
    FROM baseball_data.betting.mart_odds_outcomes
    WHERE commence_date = '{target_date}'
      AND bookmaker_last_update < commence_time
),
filtered AS (
    SELECT * FROM latest_per_book WHERE rn = 1
),
event_canonical AS (
    SELECT DISTINCT event_id, home_team, away_team
    FROM baseball_data.betting.mart_odds_outcomes
    WHERE commence_date = '{target_date}'
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY home_team, away_team
        ORDER BY ingestion_ts DESC
    ) = 1
),
h2h_per_book AS (
    SELECT
        f.event_id,
        f.bookmaker_key,
        MAX(CASE WHEN f.is_home_outcome THEN f.outcome_price_american END) AS home_price,
        MAX(CASE WHEN f.is_away_outcome THEN f.outcome_price_american END) AS away_price
    FROM filtered f
    WHERE f.market_key = 'h2h'
    GROUP BY f.event_id, f.bookmaker_key
),
h2h_vig AS (
    SELECT
        event_id,
        CASE WHEN home_price < 0
             THEN ABS(home_price) / (ABS(home_price) + 100.0)
             ELSE 100.0 / (home_price + 100.0)
        END /
        NULLIF(
            CASE WHEN home_price < 0
                 THEN ABS(home_price) / (ABS(home_price) + 100.0)
                 ELSE 100.0 / (home_price + 100.0)
            END +
            CASE WHEN away_price < 0
                 THEN ABS(away_price) / (ABS(away_price) + 100.0)
                 ELSE 100.0 / (away_price + 100.0)
            END
        , 0) AS home_imp
    FROM h2h_per_book
    WHERE home_price IS NOT NULL AND away_price IS NOT NULL
),
totals_per_book AS (
    SELECT
        f.event_id,
        f.bookmaker_key,
        MAX(f.outcome_point) AS total_line,
        MAX(CASE WHEN f.outcome_name = 'Over'  THEN f.outcome_price_american END) AS over_price,
        MAX(CASE WHEN f.outcome_name = 'Under' THEN f.outcome_price_american END) AS under_price
    FROM filtered f
    WHERE f.market_key = 'totals'
    GROUP BY f.event_id, f.bookmaker_key
),
totals_vig AS (
    SELECT
        event_id,
        total_line,
        CASE WHEN over_price < 0
             THEN ABS(over_price) / (ABS(over_price) + 100.0)
             ELSE 100.0 / (over_price + 100.0)
        END /
        NULLIF(
            CASE WHEN over_price < 0
                 THEN ABS(over_price) / (ABS(over_price) + 100.0)
                 ELSE 100.0 / (over_price + 100.0)
            END +
            CASE WHEN under_price < 0
                 THEN ABS(under_price) / (ABS(under_price) + 100.0)
                 ELSE 100.0 / (under_price + 100.0)
            END
        , 0) AS over_imp
    FROM totals_per_book
    WHERE over_price IS NOT NULL AND under_price IS NOT NULL
),
h2h_consensus AS (
    SELECT event_id,
           AVG(home_imp)::FLOAT    AS home_win_prob_consensus,
           STDDEV(home_imp)::FLOAT AS ml_consensus_std
    FROM h2h_vig
    GROUP BY event_id
),
totals_consensus AS (
    SELECT event_id,
           AVG(total_line)::FLOAT AS total_line_consensus,
           AVG(over_imp)::FLOAT   AS over_prob_consensus
    FROM totals_vig
    GROUP BY event_id
)
SELECT
    ec.home_team,
    ec.away_team,
    h.home_win_prob_consensus,
    h.ml_consensus_std,
    t.total_line_consensus,
    t.over_prob_consensus
FROM event_canonical ec
JOIN h2h_consensus h ON h.event_id = ec.event_id
LEFT JOIN totals_consensus t ON t.event_id = ec.event_id
"""

_VENUE_COLUMNS = [
    "venue_id", "venue_name", "elevation_ft", "turf_type", "roof_type",
    "left_line_ft", "left_ft", "left_center_ft", "center_ft",
    "right_center_ft", "right_line_ft", "runs_per_game_at_park", "park_run_factor_3yr",
]


def _connect(schema: str | None = None) -> snowflake.connector.SnowflakeConnection:
    with open(_KEY_PATH, "rb") as fh:
        p_key = serialization.load_pem_private_key(
            fh.read(), password=None, backend=default_backend()
        )
    pkb = p_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    kwargs: dict = dict(
        account=os.environ.get("SNOWFLAKE_ACCOUNT", "IHUPICS-DP59975"),
        user=os.environ.get("SNOWFLAKE_USER", "dbt_rw"),
        private_key=pkb,
        role=os.environ.get("SNOWFLAKE_ROLE", "ACCOUNTADMIN"),
        warehouse=os.environ.get("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH"),
        database="baseball_data",
    )
    if schema:
        kwargs["schema"] = schema
    return snowflake.connector.connect(**kwargs)


def get_snowflake_connection(schema: str | None = None) -> snowflake.connector.SnowflakeConnection:
    """Return an open Snowflake connection using the project RSA key.

    Caller is responsible for closing the connection.
    Pass schema to set a default schema for unqualified references (e.g. temp tables).
    """
    return _connect(schema=schema)


def _numeric_convert(df: pd.DataFrame) -> pd.DataFrame:
    for col in df.columns:
        if df[col].dtype == object:
            converted = pd.to_numeric(df[col], errors="coerce")
            if converted.notna().sum() >= df[col].notna().sum():
                df[col] = converted
    return df


# A1.11 Stage 3 — feature-store readiness gate. Once the schedule-spined feature
# pipeline is built to prod, today's games appear in feature_pregame_game_features
# and load_todays_features prefers that path. To avoid auto-flipping live serving
# onto a HALF-populated feature store (e.g. a mart that didn't rebuild), we only
# use the feature_store rows when their mean block coverage clears this gate;
# otherwise we fall back to the intraday assembly. Mirrors the 6 blocks scored by
# predict_today.py::_feature_coverage_score / the A1.10 coverage check.
_FEATURE_STORE_COVERAGE_BLOCKS = {
    "lineup":       ["home_avg_eb_woba", "away_avg_eb_woba"],
    "starter":      ["home_starter_eb_xwoba_against", "away_starter_eb_xwoba_against"],
    "team_rolling": ["home_off_woba_30d", "away_off_woba_30d"],
    "bullpen_eb":   ["home_bp_eb_xwoba", "away_bp_eb_xwoba"],
    "sequential":   ["home_team_sequential_woba", "away_team_sequential_woba"],
    "odds":         ["over_prob_consensus"],
}

# Minimum mean coverage for the feature_store path to be trusted for live serving.
# Default 0.70 matches the A1.10 warn threshold (below the ~0.77 intraday-assembly
# steady state, so the store is used once it reaches assembly-equivalent coverage).
_MIN_FEATURE_STORE_COVERAGE = float(os.environ.get("FEATURE_STORE_MIN_COVERAGE", "0.70"))


def _feature_store_mean_coverage(df: pd.DataFrame) -> float:
    """Mean fraction of populated feature blocks across today's feature-store rows."""
    if df.empty:
        return 0.0
    n_blocks = len(_FEATURE_STORE_COVERAGE_BLOCKS)
    total = 0.0
    for _, row in df.iterrows():
        covered = sum(
            1
            for cols in _FEATURE_STORE_COVERAGE_BLOCKS.values()
            if all(c in df.columns and pd.notna(row[c]) for c in cols)
        )
        total += covered / n_blocks
    return round(total / len(df), 3)


# A1.9 — cross-source team joins resolve through the canonical team dimension
# (dim_team_name_lookup) instead of an inline alias map. The MLB Stats API and
# the odds feeds disagree on a few franchise names (most notably the Athletics:
# Stats API "Athletics" vs odds-feed "Oakland Athletics"), which silently dropped
# odds for the affected game. Both sides now resolve to team_id, so any current
# OR future name divergence is handled by adding a row to the ref_team_aliases
# seed — no code change.
_TEAM_LOOKUP_QUERY = "SELECT name_lower, team_id FROM baseball_data.betting.dim_team_name_lookup"


def _load_team_id_lookup(
    conn: snowflake.connector.SnowflakeConnection,
) -> dict[str, int]:
    """Return a {name_lower -> team_id} map from the canonical team dimension."""
    cur = conn.cursor()
    cur.execute(_TEAM_LOOKUP_QUERY)
    return {name_lower: team_id for name_lower, team_id in cur.fetchall()}


def _resolve_team_id(name: str | None, lookup: dict[str, int]) -> int | None:
    """Resolve any feed/Stats API team name to a team_id via the canonical lookup.

    Applies dim_team_name_lookup's consumer contract — strip the Parlay
    doubleheader marker ("G1 "/"G2 ") then lowercase — before matching, so it
    mirrors the SQL join exactly. Returns None for an unmapped (e.g. non-MLB)
    name or a None input.
    """
    if name is None:
        return None
    key = re.sub(r"^G[12] ", "", str(name).strip()).lower()
    return lookup.get(key)


def _get_statsapi_team_abbrevs() -> dict[int, str]:
    """Return mapping from MLB team ID to team abbreviation (e.g. 116 -> 'DET')."""
    import statsapi
    resp = statsapi.get("teams", {"sportIds": 1})
    return {t["id"]: t["abbreviation"] for t in resp["teams"]}


def _load_latest_team_features(
    conn: snowflake.connector.SnowflakeConnection,
    home_abbrevs: list[str],
    away_abbrevs: list[str],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Fetch the most recent home/away game row per team from Snowflake.

    Returns (home_rows, away_rows), each keyed by team abbreviation.
    """
    home_list = ", ".join(f"'{a}'" for a in home_abbrevs)
    away_list = ", ".join(f"'{a}'" for a in away_abbrevs)

    cur = conn.cursor()

    cur.execute(_LATEST_HOME_QUERY.format(team_list=home_list))
    cols = [d[0].lower() for d in cur.description]
    home_rows: dict[str, dict[str, Any]] = {}
    for raw_row in cur.fetchall():
        row = dict(zip(cols, raw_row))
        home_rows[row["home_team"]] = row

    cur.execute(_LATEST_AWAY_QUERY.format(team_list=away_list))
    cols = [d[0].lower() for d in cur.description]
    away_rows: dict[str, dict[str, Any]] = {}
    for raw_row in cur.fetchall():
        row = dict(zip(cols, raw_row))
        away_rows[row["away_team"]] = row

    return home_rows, away_rows


def _load_todays_odds(
    conn: snowflake.connector.SnowflakeConnection,
    target_date: str,
    team_lookup: dict[str, int],
) -> dict[tuple[int, int], dict[str, Any]]:
    """Compute consensus implied probabilities for today's games from mart_odds_outcomes.

    Replicates mart_odds_consensus logic inline since mart_game_odds_bridge requires
    completed games (joined to mart_game_results) and won't have today's games.

    Returns a dict keyed by (home_team_id, away_team_id) — resolved through the
    canonical team dimension so it joins cleanly to the Stats API side regardless
    of name drift — with keys:
        home_win_prob_consensus, ml_consensus_std, total_line_consensus, over_prob_consensus
    Rows whose feed name does not resolve to a team_id are skipped. Returns an
    empty dict if no odds are available.
    """
    query = _TODAY_ODDS_QUERY.format(target_date=target_date)
    cur = conn.cursor()
    cur.execute(query)
    cols = [d[0].lower() for d in cur.description]
    result: dict[tuple[int, int], dict[str, Any]] = {}
    for raw_row in cur.fetchall():
        row = dict(zip(cols, raw_row))
        home_id = _resolve_team_id(row["home_team"], team_lookup)
        away_id = _resolve_team_id(row["away_team"], team_lookup)
        if home_id is None or away_id is None:
            continue
        result[(home_id, away_id)] = {
            "home_win_prob_consensus": row.get("home_win_prob_consensus"),
            "ml_consensus_std":        row.get("ml_consensus_std"),
            "total_line_consensus":    row.get("total_line_consensus"),
            "over_prob_consensus":     row.get("over_prob_consensus"),
        }
    return result


_TODAY_LINEUP_QUERY = """
SELECT * FROM baseball_data.betting_features.feature_pregame_lineup_features
WHERE game_date = '{target_date}'
"""

_TODAY_STARTER_QUERY = """
SELECT * FROM baseball_data.betting_features.feature_pregame_starter_features
WHERE game_date = '{target_date}'
"""

# Key/meta columns to drop before overlaying; everything else is a feature.
_LINEUP_STARTER_META_COLS = {"game_pk", "game_date", "game_year", "side"}


def _load_todays_lineup_starter(
    conn,
    target_date: str,
) -> tuple[dict[tuple[int, str], dict], dict[tuple[int, str], dict]]:
    """Return today's lineup and starter feature rows keyed by (game_pk, side).

    Epic A1 — unlike the team / rolling marts (which are spined on completed
    games and have no rows for today), feature_pregame_lineup_features and
    feature_pregame_starter_features are forward-looking (spined on the SCD-2
    lineup state / probable pitchers) and DO contain today's games. Columns are
    returned with the SAME prefixing convention feature_pregame_game_features
    uses — lineup col C -> {side}_C, starter col C -> {side}_starter_C — so they
    can overlay the carried-forward team row directly. EB batter/pitcher
    posteriors ride along inside these marts (avg_eb_woba, eb_xwoba_against, …).
    """
    lineup_by_game: dict[tuple[int, str], dict] = {}
    starter_by_game: dict[tuple[int, str], dict] = {}
    cur = conn.cursor()

    cur.execute(_TODAY_LINEUP_QUERY.format(target_date=target_date))
    cols = [d[0].lower() for d in cur.description]
    for raw in cur.fetchall():
        r = dict(zip(cols, raw))
        side = r.get("side")
        if side not in ("home", "away"):
            continue
        lineup_by_game[(r["game_pk"], side)] = {
            f"{side}_{c}": v for c, v in r.items() if c not in _LINEUP_STARTER_META_COLS
        }

    cur.execute(_TODAY_STARTER_QUERY.format(target_date=target_date))
    cols = [d[0].lower() for d in cur.description]
    for raw in cur.fetchall():
        r = dict(zip(cols, raw))
        side = r.get("side")
        if side not in ("home", "away"):
            continue
        starter_by_game[(r["game_pk"], side)] = {
            f"{side}_starter_{c}": v for c, v in r.items() if c not in _LINEUP_STARTER_META_COLS
        }

    return lineup_by_game, starter_by_game


def _platoon_weighted(rhb, lhb, vs_rhb, vs_lhb):
    """Lineup-handedness-weighted average of an opposing starter's platoon split.

    Mirrors the inline computation in feature_pregame_game_features
    (pct_rhb × split_vs_rhb + pct_lhb × split_vs_lhb). Returns None when the
    handedness counts or starter splits are missing (→ imputed downstream).
    Casts to float so Decimal/str values from the cursor don't raise.
    """
    try:
        rhb = float(rhb)
        lhb = float(lhb)
        vs_rhb = float(vs_rhb)
        vs_lhb = float(vs_lhb)
    except (TypeError, ValueError):
        return None
    denom = rhb + lhb
    if not denom:
        return None
    return round((rhb / denom) * vs_rhb + (lhb / denom) * vs_lhb, 3)


def _enrich_row_with_today(
    row: dict,
    game_pk: int,
    lineup_by_game: dict[tuple[int, str], dict],
    starter_by_game: dict[tuple[int, str], dict],
) -> int:
    """Overlay today's lineup + starter features onto a carried-forward team row
    and recompute the handedness adjustments. Mutates ``row`` in place; returns
    the number of game-sides overlaid. Pure (no I/O) so it is unit-testable.

    A1.8: only non-null today-values overwrite, so the overlay strictly adds
    information (a confirmed lineup / probable starter and its EB posteriors)
    without clobbering a carried-forward value with NULL.
    """
    enriched = 0
    for src in (
        lineup_by_game.get((game_pk, "home")),
        lineup_by_game.get((game_pk, "away")),
        starter_by_game.get((game_pk, "home")),
        starter_by_game.get((game_pk, "away")),
    ):
        if src:
            enriched += 1
            for k, v in src.items():
                if v is not None:
                    row[k] = v

    # Recompute lineup-vs-opposing-starter handedness adjustments from the
    # overlaid lineup counts + opposing-starter splits (mirrors the dbt model).
    for _metric in ("xwoba", "k_pct", "bb_pct"):
        _home_adj = _platoon_weighted(
            row.get("home_rhb_count"), row.get("home_lhb_count"),
            row.get(f"away_starter_{_metric}_vs_rhb"), row.get(f"away_starter_{_metric}_vs_lhb"),
        )
        if _home_adj is not None:
            row[f"home_lineup_vs_away_starter_{_metric}_adj"] = _home_adj
        _away_adj = _platoon_weighted(
            row.get("away_rhb_count"), row.get("away_lhb_count"),
            row.get(f"home_starter_{_metric}_vs_rhb"), row.get(f"home_starter_{_metric}_vs_lhb"),
        )
        if _away_adj is not None:
            row[f"away_lineup_vs_home_starter_{_metric}_adj"] = _away_adj

    # A1.12 — lineup confirmation must reflect TODAY's overlay, not the stale
    # carried-forward has_full_lineup (which is from each team's LAST game and
    # would falsely mark a game "confirmed" when no lineup is posted today, e.g.
    # a late game whose lineup hasn't dropped). Force both flags from whether
    # today's lineup features were actually overlaid for the side.
    row["home_has_full_lineup"] = bool(
        (lineup_by_game.get((game_pk, "home")) or {}).get("home_has_full_lineup")
    )
    row["away_has_full_lineup"] = bool(
        (lineup_by_game.get((game_pk, "away")) or {}).get("away_has_full_lineup")
    )
    return enriched


def load_todays_features_via_statsapi(target_date: str) -> pd.DataFrame:
    """Build today's feature rows via MLB Stats API schedule + latest Snowflake team stats.

    Assembly logic:
      - HOME_* columns from the home team's most recent home game row in Snowflake
      - AWAY_* columns from the away team's most recent away game row in Snowflake
      - Venue columns from the home team's row (home team always plays at their park)
      - Game metadata (game_pk, game_date, series_game_number) from Stats API
      - Odds consensus columns from mart_odds_outcomes (same logic as mart_odds_consensus)
      - has_full_data = False, has_odds = True when odds are available

    Returns an empty DataFrame if no games are scheduled or no Snowflake data found.
    """
    import statsapi

    games = statsapi.schedule(date=target_date, sportId=1)
    if not games:
        return pd.DataFrame()

    team_abbrevs = _get_statsapi_team_abbrevs()

    game_records = []
    home_abbrevs: list[str] = []
    away_abbrevs: list[str] = []
    for g in games:
        home_abbr = team_abbrevs.get(g["home_id"])
        away_abbr = team_abbrevs.get(g["away_id"])
        if home_abbr is None or away_abbr is None:
            continue
        if home_abbr not in home_abbrevs:
            home_abbrevs.append(home_abbr)
        if away_abbr not in away_abbrevs:
            away_abbrevs.append(away_abbr)
        game_records.append({
            "game_pk":            g["game_id"],
            "home_abbr":          home_abbr,
            "away_abbr":          away_abbr,
            "home_name":          g.get("home_name"),   # full name for odds matching
            "away_name":          g.get("away_name"),
            "venue_id":           g.get("venue_id"),
            "venue_name":         g.get("venue_name"),
            "series_game_number": g.get("series_game_number"),
            "game_datetime":      g.get("game_datetime"),
        })

    if not game_records:
        return pd.DataFrame()

    conn = _connect()
    try:
        home_rows, away_rows = _load_latest_team_features(conn, home_abbrevs, away_abbrevs)
        team_lookup = _load_team_id_lookup(conn)
        odds_by_matchup = _load_todays_odds(conn, target_date, team_lookup)
        lineup_by_game, starter_by_game = _load_todays_lineup_starter(conn, target_date)
    finally:
        conn.close()

    if odds_by_matchup:
        print(f"  Loaded odds for {len(odds_by_matchup)} game(s) from mart_odds_outcomes")
    else:
        print("  No odds found in mart_odds_outcomes for today")

    today_year = int(target_date[:4])
    rows = []
    enriched_sides = 0
    for g in game_records:
        home_r = home_rows.get(g["home_abbr"], {})
        away_r = away_rows.get(g["away_abbr"], {})
        if not home_r or not away_r:
            continue

        row: dict[str, Any] = {}

        # Game metadata
        row["game_pk"] = g["game_pk"]
        row["game_date"] = target_date
        row["game_year"] = today_year
        row["home_team"] = g["home_abbr"]
        row["away_team"] = g["away_abbr"]
        # Explicit abbrev + full-name columns so the scorer writes both correctly.
        # (home_team itself stays the abbrev — the model features key on it.)
        # Without these, predict_today.py fell through to NULL team_abbrevs and
        # stored the abbrev in the full-name column.
        row["home_team_abbrev"] = g["home_abbr"]
        row["away_team_abbrev"] = g["away_abbr"]
        row["home_name"] = g.get("home_name")
        row["away_name"] = g.get("away_name")
        row["series_game_number"] = g.get("series_game_number")
        row["game_datetime"] = g.get("game_datetime")
        row["post_2022_rules"] = 1 if today_year >= 2023 else 0
        row["has_full_data"] = False

        # Venue from home team's latest home game (correct park)
        for col in _VENUE_COLUMNS:
            row[col] = home_r.get(col)
        if g.get("venue_id"):
            row["venue_id"] = g["venue_id"]
        if g.get("venue_name"):
            row["venue_name"] = g["venue_name"]

        # Home team stats (HOME_* columns)
        for col, val in home_r.items():
            if col.startswith("home_"):
                row[col] = val

        # Away team stats (AWAY_* columns)
        for col, val in away_r.items():
            if col.startswith("away_"):
                row[col] = val

        # Odds consensus — match by team_id resolved through the canonical team
        # dimension on both sides. This survives cross-source name drift (e.g.
        # Stats API "Athletics" vs odds-feed "Oakland Athletics") that would
        # otherwise silently drop odds for the affected game.
        odds = odds_by_matchup.get(
            (_resolve_team_id(g.get("home_name"), team_lookup),
             _resolve_team_id(g.get("away_name"), team_lookup)),
            {},
        )
        if odds:
            row["has_odds"] = True
            row["home_win_prob_consensus"] = odds.get("home_win_prob_consensus")
            row["ml_consensus_std"]        = odds.get("ml_consensus_std")
            row["total_line_consensus"]    = odds.get("total_line_consensus")
            row["over_prob_consensus"]     = odds.get("over_prob_consensus")
        else:
            row["has_odds"] = False
            row["home_win_prob_consensus"] = None
            row["ml_consensus_std"]        = None
            row["total_line_consensus"]    = None
            row["over_prob_consensus"]     = None

        # Epic A1 — overlay TODAY's actual lineup + starter features (incl. EB
        # posteriors) onto the carried-forward team row and recompute the
        # handedness adjustments. The team-level rolling columns legitimately
        # carry forward from each team's last game; lineup/starter reflect
        # today. (The pitcher-batter H2H matchup block is NOT recomputed here —
        # its mart is completed-game-spined with no today rows; deferred to A1.11.)
        _n = _enrich_row_with_today(row, g["game_pk"], lineup_by_game, starter_by_game)
        enriched_sides += _n
        # A1.10 — per-game data_source: 'intraday_assembly' when today's lineup/
        # starter features were overlaid, else 'intraday_fallback' (team carry-
        # forward only — e.g. lineup not yet posted for this game).
        row["data_source"] = "intraday_assembly" if _n > 0 else "intraday_fallback"

        rows.append(row)

    if not rows:
        return pd.DataFrame()

    print(
        f"  [Epic A1] Enriched {enriched_sides} game-side(s) with today's "
        f"lineup/starter features (EB posteriors included)"
    )
    df = pd.DataFrame(rows)
    return _numeric_convert(df)


# E13.11 backfill cost optimization — when this in-memory frame is set, load_todays_features
# serves each date's slice FROM IT (sourced once via load_range_features → a local parquet in
# the predict_today driver) instead of issuing one Snowflake read per date across a multi-date
# backfill. None on every live/single-date path, so live serving is byte-for-byte unchanged.
_RANGE_FEATURE_CACHE: pd.DataFrame | None = None


def set_range_feature_cache(df: pd.DataFrame | None) -> None:
    """Install (or clear with None) the backfill range feature cache. Set by the
    predict_today range driver; reset in its finally so the process never leaks it."""
    global _RANGE_FEATURE_CACHE
    _RANGE_FEATURE_CACHE = df


def load_range_features(start_date: str, end_date: str) -> pd.DataFrame:
    """One-shot pull of feature_store rows for every game_date in [start_date, end_date]
    (inclusive). Backs the backfill parquet cache: ONE Snowflake read for the whole window
    instead of one per date. Mirrors _TODAY_QUERY's `SELECT f.*` so the per-date slices are
    schema-identical to the live single-date path."""
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT f.* FROM baseball_data.betting_features.feature_pregame_game_features f "
            "WHERE f.game_date BETWEEN %(s)s AND %(e)s",
            {"s": start_date, "e": end_date},
        )
        columns = [desc[0].lower() for desc in cur.description]
        rows = cur.fetchall()
    finally:
        conn.close()
    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(rows, columns=columns)


def load_todays_features(target_date: str) -> pd.DataFrame:
    """Load pregame features for all regular-season games on target_date.

    Path selection (A1.11):
      1. feature_store — query feature_pregame_game_features directly. After the
         schedule-spine re-spine (A1.11) this contains today's not-yet-played
         games. Used only when the rows clear the coverage gate
         (_MIN_FEATURE_STORE_COVERAGE), so a half-built feature store can't
         silently degrade serving.
      2. intraday assembly — the fallback (Stats API schedule + latest per-team
         stats + today's lineup/starter/EB overlay). Used when the feature store
         has no rows for today (pipeline not yet run) OR its coverage is below the
         gate. Pre-A1.11 this was the everyday path; post-A1.11 it is the
         outage / low-coverage fallback.

    Does NOT join to mart_game_results (today's scores don't exist yet).
    Does NOT apply has_full_data or min_games_played filters.
    """
    # E13.11 backfill cache — serve this date's slice from the pre-pulled range frame
    # (one Snowflake read for the whole window). Same coverage gate / numeric coercion /
    # data_source stamp as the live feature_store branch, so downstream is identical. If a
    # cached slice is empty or below the coverage gate, fall through to the normal live path
    # (which may re-query or assemble via Stats API) — never silently degrade a backfill.
    if _RANGE_FEATURE_CACHE is not None:
        df = _RANGE_FEATURE_CACHE[
            _RANGE_FEATURE_CACHE["game_date"].astype(str) == target_date
        ]
        if not df.empty:
            cov = _feature_store_mean_coverage(df)
            if cov >= _MIN_FEATURE_STORE_COVERAGE:
                print(f"[INFO] [backfill-cache] feature_store serving {len(df)} game(s) for "
                      f"{target_date} from local parquet (mean block coverage {cov:.2f} ≥ "
                      f"{_MIN_FEATURE_STORE_COVERAGE:.2f}); no per-date Snowflake read.")
                df = df.copy()
                df["data_source"] = "feature_store"
                return _numeric_convert(df)
            print(f"[INFO] [backfill-cache] cached rows for {target_date} below coverage gate "
                  f"({cov:.2f} < {_MIN_FEATURE_STORE_COVERAGE:.2f}); falling through to live load.")

    conn = _connect()
    try:
        query = _TODAY_QUERY.format(target_date=target_date)
        cur = conn.cursor()
        cur.execute(query)
        columns = [desc[0].lower() for desc in cur.description]
        rows = cur.fetchall()
        if rows:
            df = pd.DataFrame(rows, columns=columns)
            # A1.11 Stage 3 — only trust the feature_store path if today's rows
            # actually clear the coverage gate; otherwise fall through to the
            # intraday assembly so a half-built feature store can't silently
            # degrade live serving.
            cov = _feature_store_mean_coverage(df)
            if cov >= _MIN_FEATURE_STORE_COVERAGE:
                print(f"[INFO] feature_store serving {len(df)} game(s) for {target_date} "
                      f"(mean block coverage {cov:.2f} ≥ {_MIN_FEATURE_STORE_COVERAGE:.2f}).")
                df["data_source"] = "feature_store"
                return _numeric_convert(df)
            print(f"[INFO] feature_store rows found for {target_date} but mean coverage "
                  f"{cov:.2f} < {_MIN_FEATURE_STORE_COVERAGE:.2f}; falling back to intraday assembly.")
    finally:
        conn.close()

    print(f"  No usable feature-store rows for {target_date}; assembling from Stats API schedule...")
    print("[INFO] Intraday assembly active — team-level rolling/EB-bullpen/standings columns carry "
          "forward from each team's last completed game; today's lineup + starter features (incl. EB "
          "batter/pitcher posteriors) are overlaid fresh by game_pk (Epic A1).")
    df = load_todays_features_via_statsapi(target_date)
    # A1.10 — data_source is set per-row inside the assembly (intraday_assembly
    # when lineup/starter overlay applied, else intraday_fallback). Only default
    # it if the assembly somehow didn't stamp it.
    if not df.empty and "data_source" not in df.columns:
        df["data_source"] = "intraday_fallback"
    return df


def load_features(min_games_played: int = 15, min_year: int = 2021) -> pd.DataFrame:
    """Training/offline feature surface — `feature_pregame_game_features` joined to
    final scores, filtered to `has_full_data` + min games.

    `min_year` (default 2021) is the earliest season loaded. The mart is populated back to
    2015, so Story E1.6 can opt into `min_year=2016` to roughly double the sample — but ONLY
    in combination with the regime-similarity weighting (`run_env_regime`), because the older
    seasons span different run-environment regimes (2019 ≈ peak juiced ball). Pre-2021 rows
    carry NULL for the Epic-16 sequential posteriors (backfilled 2021+) and FanGraphs Stuff+
    (2020+); those impute to constants, so a model that relies on them should drop them (the
    E1.3 slim contracts already largely do). Default stays 2021 so production loading is
    unchanged unless a caller deliberately extends.

    ⚠ NOT POINT-IN-TIME (Story 30.3). This reads each game's row AS IT EXISTS NOW —
    i.e. POST-game-backfilled and dense (lineups, starters, EB posteriors, umpire
    tendency all populated after the fact). The live serve only ever saw the
    PRE-game (sparse) row for the same game_pk. So any skill measured here (e.g. the
    home_win corr 0.42) is an upper-bound CEILING, NOT the achievable live number.
    For the honest, point-in-time live skill, score the ACTUALLY-SERVED predictions
    in `daily_model_predictions` against the outcome — see
    `betting_ml/scripts/honest_live_skill.py`. Until the feature store is
    AS-OF-snapshotted (refined_architecture_proposal §Point-in-Time), treat offline
    evals via this loader as ceilings, not live KPIs.
    """
    conn = _connect()
    try:
        query = _QUERY.format(min_games_played=int(min_games_played), min_year=int(min_year))
        cur = conn.cursor()
        cur.execute(query)
        columns = [desc[0].lower() for desc in cur.description]
        rows = cur.fetchall()
        df = pd.DataFrame(rows, columns=columns)
        # Snowflake returns NUMERIC/DECIMAL columns as decimal.Decimal objects.
        # Convert object-dtype columns that contain numeric values to float64 so
        # downstream arithmetic (Bayesian shrinkage, pandas ops) works correctly.
        return _numeric_convert(df)
    finally:
        conn.close()
