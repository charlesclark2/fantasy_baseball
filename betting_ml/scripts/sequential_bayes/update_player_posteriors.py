"""
update_player_posteriors.py — Epic 16, Story 16.1

Sequential Normal-Normal conjugate update of per-player xwOBA belief state from
observed plate-appearance outcomes in completed games.

This is TRUE sequential Bayes, not per-game re-shrinkage. The EB posterior from
Epic 4A/5A/6A is the player's *season-opening* belief, captured ONCE at their
first appearance of the season. From there each game's posterior becomes the
next game's prior — beliefs accumulate through the season without re-anchoring
to the EB base:

    Game 1:  prior_mu = eb_woba (first-appearance EB posterior)  →  posterior_1
    Game 2:  prior_mu = posterior_1                              →  posterior_2
    Game 3:  prior_mu = posterior_2                              →  posterior_3
    ...

Contrast with the WRONG pattern (prior_mu = current eb_woba every game), which
would discard the sequential learning and restart from the EB prior each game.

Update rule (Normal-Normal, known per-observation variance sigma_obs^2):
    prior:      N(prior_mu, prior_var)
    observe:    n_obs PAs with sample mean obs_mean, each variance sigma_obs^2
    post_var  = 1 / (1/prior_var + n_obs/sigma_obs^2)
    post_mu   = post_var * (prior_mu/prior_var + n_obs*obs_mean/sigma_obs^2)

Cold start (first appearance of the season):
    prior_mu  = eb_mu_0       (eb_woba / eb_xwoba_against)
    prior_var = max(eb_sigma_0, sigma_floor)^2
    where sigma_floor = sigma_obs / sqrt(prior_neff_cap) guards against a
    pathologically tight EB uncertainty (e.g. bullpen min 0.005) producing an
    immovable prior. Default cap = 400 equivalent PA/BF.

Players who do NOT appear on a given day keep their existing is_current row
untouched — belief persists (graceful degradation; no row is written for them).

Metrics (v1): xwOBA only.
    batter  -> metric='xwoba'         from eb_batter_posteriors_raw.eb_woba
    starter -> metric='xwoba_against'  from eb_starter_posteriors.eb_xwoba_against
    bullpen -> metric='xwoba_against'  from eb_bullpen_posteriors.eb_xwoba_against
A pitcher who both starts and relieves keeps SEPARATE chains (different baseline).
K% / BB% are a fast-follow (the `metric` column already supports them).

Table: baseball_data.betting.player_sequential_posteriors
  Grain: (player_id, player_type, metric, season, game_pk)
  is_current = True marks the latest posterior per (player_id, player_type, metric, season)

Usage:
    # Daily update — run after mart_pitch_play_event loads for completed games
    uv run python betting_ml/scripts/sequential_bayes/update_player_posteriors.py --date 2026-06-02
    uv run python betting_ml/scripts/sequential_bayes/update_player_posteriors.py --date 2026-06-02 --dry-run

    # Season backfill — processes each game day in chronological order
    uv run python betting_ml/scripts/sequential_bayes/update_player_posteriors.py --backfill --season 2026
    uv run python betting_ml/scripts/sequential_bayes/update_player_posteriors.py --backfill --season 2026 --dry-run
"""

from __future__ import annotations

import argparse
import hashlib
import math
import sys
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(_PROJECT_ROOT / ".env")

from betting_ml.utils.data_loader import get_snowflake_connection
# E11.20 phase 1.5 (the W1 SF decommission): reuse the canonical W7a DuckDB/S3 helpers
# (one source of truth for the connection + view registration + the table-name rewrite)
# so `--s3` can read the mart_pitch_play_event PA substrate from the lakehouse instead of
# Snowflake — the LAST daily Snowflake read of the W1 pitch-mart family. The EB prior /
# role reads and the SCD-2 seq-posterior read/write STAY on Snowflake (dual-connection
# pattern, exactly like the sibling update_matchup_cell_posteriors.py --s3).
from betting_ml.scripts.eb_priors.generate_matchup_signals import (
    _get_duckdb,
    _register_s3_views,
    _duck_sql_for,
    _fetch_duck,
)

# ── Constants ──────────────────────────────────────────────────────────────────

_TARGET_TABLE = "baseball_data.betting.player_sequential_posteriors"

# Population per-PA xwOBA std (2025: 181,231 PAs, std 0.3850) — the known
# observation noise for the conjugate update. Override with --sigma-obs.
_SIGMA_OBS_DEFAULT = 0.385

# Max equivalent PA/BF a cold-start EB prior may be worth. Floors prior sigma at
# sigma_obs/sqrt(cap) so an over-confident EB uncertainty can't freeze the chain.
_PRIOR_NEFF_CAP_DEFAULT = 400

_FIRST_SEASON = 2021  # first season with EB posteriors

_METRIC_BATTER  = "xwoba"
_METRIC_PITCHER = "xwoba_against"

_DDL = f"""
CREATE TABLE IF NOT EXISTS {_TARGET_TABLE} (
    player_id          VARCHAR(20)   NOT NULL,
    player_type        VARCHAR(16)   NOT NULL,
    metric             VARCHAR(32)   NOT NULL,
    season             INTEGER       NOT NULL,
    game_pk            BIGINT        NOT NULL,
    game_date          DATE          NOT NULL,
    update_ts          TIMESTAMP_NTZ NOT NULL,
    eb_mu_0            FLOAT         NOT NULL,
    eb_sigma_0         FLOAT         NOT NULL,
    sigma_obs          FLOAT         NOT NULL,
    prior_mu           FLOAT         NOT NULL,
    prior_sigma2       FLOAT         NOT NULL,
    obs_mean           FLOAT         NOT NULL,
    n_obs              INTEGER       NOT NULL,
    posterior_mu       FLOAT         NOT NULL,
    posterior_sigma2   FLOAT         NOT NULL,
    n_cumulative       INTEGER       NOT NULL,
    is_current         BOOLEAN       NOT NULL,
    record_hash        VARCHAR(64)   NOT NULL
)
"""

# ── SQL ────────────────────────────────────────────────────────────────────────

_PA_SQL = """
SELECT
    game_pk,
    game_date,
    game_year,
    CAST(batter_id  AS VARCHAR) AS batter_id,
    CAST(pitcher_id AS VARCHAR) AS pitcher_id,
    xwoba
FROM baseball_data.betting.mart_pitch_play_event
WHERE game_date = %(game_date)s
  AND plate_appearance_event IS NOT NULL
  AND xwoba IS NOT NULL
ORDER BY game_pk, at_bat_number
"""

_PA_SEASON_DATES_SQL = """
SELECT DISTINCT game_date
FROM baseball_data.betting.mart_pitch_play_event
WHERE game_year = %(season)s
  AND plate_appearance_event IS NOT NULL
ORDER BY game_date
"""

# First-appearance EB prior per player for the season (season-opening belief).
_BATTER_PRIOR_SQL = """
SELECT
    CAST(batter_id AS VARCHAR) AS player_id,
    eb_woba             AS mu_0,
    eb_woba_uncertainty AS sigma_0
FROM baseball_data.betting.eb_batter_posteriors_raw
WHERE season = %(season)s
  AND eb_woba IS NOT NULL
QUALIFY ROW_NUMBER() OVER (PARTITION BY batter_id ORDER BY game_date, game_pk) = 1
"""

_STARTER_PRIOR_SQL = """
SELECT
    CAST(pitcher_id AS VARCHAR) AS player_id,
    eb_xwoba_against     AS mu_0,
    eb_xwoba_uncertainty AS sigma_0
FROM baseball_data.betting.eb_starter_posteriors
WHERE season = %(season)s
  AND eb_xwoba_against IS NOT NULL
QUALIFY ROW_NUMBER() OVER (PARTITION BY pitcher_id ORDER BY game_date, game_pk) = 1
"""

_BULLPEN_PRIOR_SQL = """
SELECT
    CAST(pitcher_id AS VARCHAR) AS player_id,
    eb_xwoba_against     AS mu_0,
    eb_xwoba_uncertainty AS sigma_0
FROM baseball_data.betting.eb_bullpen_posteriors
WHERE season = %(season)s
  AND eb_xwoba_against IS NOT NULL
QUALIFY ROW_NUMBER() OVER (PARTITION BY pitcher_id ORDER BY game_date, game_pk) = 1
"""

# Per-game pitcher role (starter vs bullpen) for a single date.
_STARTER_ROLE_SQL = """
SELECT DISTINCT CAST(pitcher_id AS VARCHAR) AS player_id, game_pk
FROM baseball_data.betting.eb_starter_posteriors
WHERE game_date = %(game_date)s
"""

_BULLPEN_ROLE_SQL = """
SELECT DISTINCT CAST(pitcher_id AS VARCHAR) AS player_id, game_pk
FROM baseball_data.betting.eb_bullpen_posteriors
WHERE game_date = %(game_date)s
"""

_CURRENT_SEQ_SQL = """
SELECT
    player_id,
    player_type,
    metric,
    posterior_mu,
    posterior_sigma2,
    n_cumulative
FROM {table}
WHERE is_current = TRUE
  AND season = %(season)s
"""


# ── Conjugate math ─────────────────────────────────────────────────────────────

def normal_normal_update(
    prior_mu: float,
    prior_var: float,
    obs_mean: float,
    n_obs: int,
    sigma_obs: float,
) -> tuple[float, float]:
    """
    Normal-Normal conjugate update with known per-observation variance.

    post_var = 1 / (1/prior_var + n/sigma_obs^2)
    post_mu  = post_var * (prior_mu/prior_var + n*obs_mean/sigma_obs^2)
    """
    obs_var      = sigma_obs * sigma_obs
    prior_prec   = 1.0 / prior_var
    data_prec    = n_obs / obs_var
    post_var     = 1.0 / (prior_prec + data_prec)
    post_mu      = post_var * (prior_mu * prior_prec + (n_obs * obs_mean) / obs_var)
    return post_mu, post_var


def cold_start_prior_var(eb_sigma_0: float, sigma_obs: float, prior_neff_cap: int) -> float:
    """Cold-start prior variance, floored so the EB prior is worth <= prior_neff_cap PA/BF."""
    sigma_floor = sigma_obs / math.sqrt(prior_neff_cap)
    prior_sigma = max(float(eb_sigma_0), sigma_floor)
    return prior_sigma * prior_sigma


# ── Loaders ────────────────────────────────────────────────────────────────────

def _ensure_table(conn) -> None:
    cur = conn.cursor()
    cur.execute(_DDL)
    conn.commit()
    cur.close()


def _fetch_dicts(conn, sql: str, params: dict) -> list[dict]:
    cur = conn.cursor()
    cur.execute(sql, params)
    cols = [d[0].lower() for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    cur.close()
    return rows


def _load_pas(conn, target_date: date, duck=None) -> list[dict]:
    # E11.20 phase 1.5: --s3 reads mart_pitch_play_event from the S3 lakehouse via DuckDB.
    # game_date is VARCHAR ISO in the parquet, so equality vs the ISO literal matches as a
    # string compare (same note as the sibling update_matchup_cell_posteriors._load_pas);
    # downstream _collect_observations already coerces str → date.
    if duck is not None:
        sql = _duck_sql_for(_PA_SQL).replace("%(game_date)s", f"'{target_date.isoformat()}'")
        return _fetch_duck(duck, sql)
    return _fetch_dicts(conn, _PA_SQL, {"game_date": target_date.isoformat()})


def _load_game_dates_for_season(conn, season: int, duck=None) -> list[date]:
    # E11.20 phase 1.5: --s3 reads mart_pitch_play_event from the S3 lakehouse via DuckDB.
    # VARCHAR ISO game_date sorts correctly lexicographically; caller coerces str → date.
    if duck is not None:
        sql = _duck_sql_for(_PA_SEASON_DATES_SQL).replace("%(season)s", str(int(season)))
        rows = _fetch_duck(duck, sql)
    else:
        rows = _fetch_dicts(conn, _PA_SEASON_DATES_SQL, {"season": season})
    return [r["game_date"] if isinstance(r["game_date"], date)
            else date.fromisoformat(str(r["game_date"])) for r in rows]


def _load_eb_priors(conn, season: int) -> dict[str, dict[str, tuple[float, float]]]:
    """
    {player_type: {player_id: (mu_0, sigma_0)}} from first-appearance EB rows.
    player_type in {batter, starter, bullpen}.
    """
    out: dict[str, dict[str, tuple[float, float]]] = {}
    for ptype, sql in (
        ("batter",  _BATTER_PRIOR_SQL),
        ("starter", _STARTER_PRIOR_SQL),
        ("bullpen", _BULLPEN_PRIOR_SQL),
    ):
        rows = _fetch_dicts(conn, sql, {"season": season})
        out[ptype] = {
            r["player_id"]: (float(r["mu_0"]), float(r["sigma_0"]))
            for r in rows
        }
    return out


def _load_pitcher_roles(conn, target_date: date) -> dict[tuple[str, int], str]:
    """{(pitcher_id, game_pk): 'starter'|'bullpen'} for the date."""
    roles: dict[tuple[str, int], str] = {}
    for r in _fetch_dicts(conn, _STARTER_ROLE_SQL, {"game_date": target_date.isoformat()}):
        roles[(r["player_id"], int(r["game_pk"]))] = "starter"
    for r in _fetch_dicts(conn, _BULLPEN_ROLE_SQL, {"game_date": target_date.isoformat()}):
        # starter takes precedence if (rare) a pitcher is in both for the same game_pk
        roles.setdefault((r["player_id"], int(r["game_pk"])), "bullpen")
    return roles


def _load_current_seq(conn, season: int) -> dict[tuple[str, str, str], dict]:
    """{(player_id, player_type, metric): row} for is_current=True. {} if table absent."""
    try:
        rows = _fetch_dicts(conn, _CURRENT_SEQ_SQL.format(table=_TARGET_TABLE), {"season": season})
    except Exception:
        return {}
    return {(r["player_id"], r["player_type"], r["metric"]): r for r in rows}


# ── Observation collection ─────────────────────────────────────────────────────

def _collect_observations(
    pas: list[dict],
    pitcher_roles: dict[tuple[str, int], str],
) -> list[dict]:
    """
    Aggregate PAs into per-player-game observations.

    Returns a chronologically-ordered list of:
        {player_id, player_type, metric, game_pk, game_date, obs_mean, n_obs}

    batter  : mean xwoba over the batter's PAs in the game     (n_obs = PA)
    pitcher : mean xwoba-against over batters faced in the game (n_obs = BF),
              player_type resolved by EB-table role membership for (pitcher, game).
    """
    batter_acc:  dict[tuple[int, str], list[float]] = defaultdict(list)
    pitcher_acc: dict[tuple[int, str], list[float]] = defaultdict(list)
    game_date_of: dict[int, date] = {}

    for pa in pas:
        game_pk = int(pa["game_pk"])
        gd = pa["game_date"]
        if isinstance(gd, str):
            gd = date.fromisoformat(gd)
        game_date_of[game_pk] = gd

        xwoba = float(pa["xwoba"])
        if pa.get("batter_id") is not None:
            batter_acc[(game_pk, pa["batter_id"])].append(xwoba)
        if pa.get("pitcher_id") is not None:
            pitcher_acc[(game_pk, pa["pitcher_id"])].append(xwoba)

    obs: list[dict] = []

    for (game_pk, bid), vals in batter_acc.items():
        obs.append({
            "player_id":   bid,
            "player_type": "batter",
            "metric":      _METRIC_BATTER,
            "game_pk":     game_pk,
            "game_date":   game_date_of[game_pk],
            "obs_mean":    sum(vals) / len(vals),
            "n_obs":       len(vals),
        })

    for (game_pk, pid), vals in pitcher_acc.items():
        role = pitcher_roles.get((pid, game_pk))
        if role is None:
            continue  # no EB role for this pitcher-game → no prior to seed; skip
        obs.append({
            "player_id":   pid,
            "player_type": role,
            "metric":      _METRIC_PITCHER,
            "game_pk":     game_pk,
            "game_date":   game_date_of[game_pk],
            "obs_mean":    sum(vals) / len(vals),
            "n_obs":       len(vals),
        })

    obs.sort(key=lambda o: (o["game_date"], o["game_pk"], o["player_type"], o["player_id"]))
    return obs


# ── Sequential chain ───────────────────────────────────────────────────────────

def _apply_updates(
    observations: list[dict],
    current_seq: dict[tuple[str, str, str], dict],
    eb_priors: dict[str, dict[str, tuple[float, float]]],
    sigma_obs: float,
    prior_neff_cap: int,
    season: int,
    update_ts: datetime,
) -> tuple[list[dict], int]:
    """
    Walk observations in chronological order, chaining each player's belief.

    Working state is seeded from the DB is_current rows and updated in memory so
    intra-run multiplicity (e.g. doubleheaders) chains correctly.

    Returns (new_rows, n_skipped_no_prior).
    """
    # Mutable working state: (player_id, player_type, metric) -> (mu, var, n_cum)
    working: dict[tuple[str, str, str], tuple[float, float, int]] = {
        key: (float(r["posterior_mu"]), float(r["posterior_sigma2"]), int(r["n_cumulative"]))
        for key, r in current_seq.items()
    }

    new_rows: list[dict] = []
    n_skipped = 0

    for o in observations:
        key = (o["player_id"], o["player_type"], o["metric"])

        prior = eb_priors.get(o["player_type"], {}).get(o["player_id"])
        if key in working:
            prior_mu, prior_var, n_cum_prev = working[key]
            # eb anchor (for provenance) — fall back to current prior if absent
            eb_mu_0, eb_sigma_0 = prior if prior is not None else (prior_mu, math.sqrt(prior_var))
        else:
            if prior is None:
                # No season-opening EB belief for this player → cannot seed. Skip.
                n_skipped += 1
                continue
            eb_mu_0, eb_sigma_0 = prior
            prior_mu  = eb_mu_0
            prior_var = cold_start_prior_var(eb_sigma_0, sigma_obs, prior_neff_cap)
            n_cum_prev = 0

        post_mu, post_var = normal_normal_update(
            prior_mu, prior_var, o["obs_mean"], o["n_obs"], sigma_obs
        )
        n_cum = n_cum_prev + o["n_obs"]
        working[key] = (post_mu, post_var, n_cum)

        payload = (o["player_id"], o["player_type"], o["metric"], o["game_pk"],
                   round(post_mu, 8), round(post_var, 10), n_cum)
        record_hash = hashlib.sha256(str(payload).encode()).hexdigest()

        new_rows.append({
            "player_id":        o["player_id"],
            "player_type":      o["player_type"],
            "metric":           o["metric"],
            "season":           season,
            "game_pk":          o["game_pk"],
            "game_date":        o["game_date"],
            "update_ts":        update_ts,
            "eb_mu_0":          eb_mu_0,
            "eb_sigma_0":       eb_sigma_0,
            "sigma_obs":        sigma_obs,
            "prior_mu":         prior_mu,
            "prior_sigma2":     prior_var,
            "obs_mean":         o["obs_mean"],
            "n_obs":            o["n_obs"],
            "posterior_mu":     post_mu,
            "posterior_sigma2": post_var,
            "n_cumulative":     n_cum,
            "is_current":       True,
            "record_hash":      record_hash,
        })

    return new_rows, n_skipped


# ── Snowflake write ────────────────────────────────────────────────────────────

_COL_ORDER = [
    "player_id", "player_type", "metric", "season", "game_pk", "game_date", "update_ts",
    "eb_mu_0", "eb_sigma_0", "sigma_obs", "prior_mu", "prior_sigma2",
    "obs_mean", "n_obs", "posterior_mu", "posterior_sigma2", "n_cumulative",
    "is_current", "record_hash",
]


def _write_updates(conn, new_rows: list[dict], season: int) -> dict[str, int]:
    """
    SCD-2 write:
      1. flip is_current=FALSE for affected (player_id, player_type, metric) in season
      2. INSERT new is_current=TRUE rows (all scalar columns — no PARSE_JSON)
    """
    if not new_rows:
        return {"closed": 0, "inserted": 0}

    affected = sorted({(r["player_id"], r["player_type"], r["metric"]) for r in new_rows})
    cur = conn.cursor()

    placeholders = ", ".join(["(%s, %s, %s)"] * len(affected))
    flat = [v for triple in affected for v in triple]
    cur.execute(
        f"""
        UPDATE {_TARGET_TABLE}
        SET is_current = FALSE
        WHERE is_current = TRUE
          AND season = {season}
          AND (player_id, player_type, metric) IN ({placeholders})
        """,
        flat,
    )
    closed = cur.rowcount

    row_ph = ", ".join(["%s"] * len(_COL_ORDER))
    cur.executemany(
        f"INSERT INTO {_TARGET_TABLE} ({', '.join(_COL_ORDER)}) VALUES ({row_ph})",
        [[r[c] for c in _COL_ORDER] for r in new_rows],
    )

    conn.commit()
    cur.close()
    return {"closed": closed, "inserted": len(new_rows)}


# ── Per-date orchestration ─────────────────────────────────────────────────────

def update_for_date(
    target_date: date,
    eb_priors: dict[str, dict[str, tuple[float, float]]],
    sigma_obs: float,
    prior_neff_cap: int,
    dry_run: bool,
    duck=None,
) -> dict[str, int]:
    """E11.20 phase 1.5: when `duck` is provided (--s3), the PA substrate reads from the
    S3 lakehouse via DuckDB. The EB role reads + seq-posterior read/write below STILL use
    the Snowflake `conn`."""
    season    = target_date.year
    update_ts = datetime.now(timezone.utc).replace(tzinfo=None)

    conn = get_snowflake_connection()
    try:
        pas = _load_pas(conn, target_date, duck=duck)
        if not pas:
            print(f"    {target_date}: no PAs found — skipping.")
            return {"players_updated": 0, "obs_processed": 0, "skipped": 0, "closed": 0, "inserted": 0}

        pitcher_roles = _load_pitcher_roles(conn, target_date)
        current_seq   = _load_current_seq(conn, season)
        observations  = _collect_observations(pas, pitcher_roles)

        new_rows, n_skipped = _apply_updates(
            observations, current_seq, eb_priors, sigma_obs, prior_neff_cap, season, update_ts
        )

        n_cold = sum(1 for r in new_rows if r["n_cumulative"] == r["n_obs"])
        print(
            f"    {target_date}: {len(pas):,} PAs → {len(observations):,} player-games "
            f"→ {len(new_rows):,} updates ({n_cold} cold-start, {n_skipped} skipped no-prior)"
        )

        if dry_run:
            for r in new_rows[:3]:
                eff = "cold" if r["n_cumulative"] == r["n_obs"] else "chain"
                print(
                    f"      [DRY] {r['player_type']:<7} {r['player_id']:>7} {r['metric']}: "
                    f"prior_mu={r['prior_mu']:.4f} obs={r['obs_mean']:.4f}(n={r['n_obs']}) "
                    f"→ post_mu={r['posterior_mu']:.4f} post_sd={math.sqrt(r['posterior_sigma2']):.4f} "
                    f"n_cum={r['n_cumulative']} [{eff}]"
                )
            return {"players_updated": len(new_rows), "obs_processed": len(observations),
                    "skipped": n_skipped, "closed": 0, "inserted": 0}

        result = _write_updates(conn, new_rows, season)
        return {"players_updated": len(new_rows), "obs_processed": len(observations),
                "skipped": n_skipped, **result}
    finally:
        conn.close()


# ── Runners ────────────────────────────────────────────────────────────────────

def _load_priors_and_prep(season: int, sigma_obs: float, prior_neff_cap: int, dry_run: bool):
    print(f"\nLoading EB season-opening priors (season={season})...")
    conn = get_snowflake_connection()
    try:
        eb_priors = _load_eb_priors(conn, season)
        for ptype in ("batter", "starter", "bullpen"):
            print(f"  {ptype:<7}: {len(eb_priors.get(ptype, {})):,} players")
        if not dry_run:
            print(f"\nEnsuring DDL for {_TARGET_TABLE}...")
            _ensure_table(conn)
    finally:
        conn.close()
    sigma_floor = sigma_obs / math.sqrt(prior_neff_cap)
    print(f"  sigma_obs={sigma_obs:.4f}  prior_neff_cap={prior_neff_cap}  "
          f"prior_sigma_floor={sigma_floor:.4f}")
    return eb_priors


def _maybe_duck(use_s3: bool):
    """E11.20 phase 1.5: a registered DuckDB/S3 connection when --s3, else None."""
    if not use_s3:
        return None
    print("\n[--s3] Reading the PA substrate from the S3 lakehouse via DuckDB...")
    duck = _get_duckdb()
    _register_s3_views(duck)
    return duck


def run_single_date(target_date: date, sigma_obs: float, prior_neff_cap: int, dry_run: bool,
                    use_s3: bool = False) -> None:
    eb_priors = _load_priors_and_prep(target_date.year, sigma_obs, prior_neff_cap, dry_run)
    duck = _maybe_duck(use_s3)
    print(f"\nUpdating sequential player posteriors for {target_date}...")
    result = update_for_date(target_date, eb_priors, sigma_obs, prior_neff_cap, dry_run, duck=duck)
    print(f"\n  players_updated={result['players_updated']}  obs_processed={result['obs_processed']}  "
          f"skipped={result['skipped']}  closed={result['closed']}  inserted={result['inserted']}")


def run_backfill(season: int, sigma_obs: float, prior_neff_cap: int, dry_run: bool,
                 use_s3: bool = False) -> None:
    eb_priors = _load_priors_and_prep(season, sigma_obs, prior_neff_cap, dry_run)
    duck = _maybe_duck(use_s3)

    print(f"\nFetching game dates for season {season}...")
    conn = get_snowflake_connection()
    try:
        game_dates = _load_game_dates_for_season(conn, season, duck=duck)
    finally:
        conn.close()
    print(f"  {len(game_dates)} game dates found")
    if not game_dates:
        print("No game dates found. Exiting.")
        return

    tot = {"players_updated": 0, "obs_processed": 0, "skipped": 0, "inserted": 0}
    print(f"\nProcessing {len(game_dates)} dates in chronological order...")
    for gd in game_dates:
        r = update_for_date(gd, eb_priors, sigma_obs, prior_neff_cap, dry_run, duck=duck)
        for k in tot:
            tot[k] += r.get(k, 0)

    print(f"\n{'[DRY RUN] ' if dry_run else ''}Backfill complete:")
    print(f"  total players updated: {tot['players_updated']:,}")
    print(f"  total obs processed:   {tot['obs_processed']:,}")
    print(f"  total skipped no-prior:{tot['skipped']:,}")
    print(f"  total rows inserted:   {tot['inserted']:,}")


def run_catchup(lookback_days: int, sigma_obs: float, prior_neff_cap: int, dry_run: bool,
                use_s3: bool = False) -> None:
    """Advance the chain over every completed date missing since the frontier (2026-07-22 durable
    fix — replaces the fragile `--date yesterday`). Order-preserving + self-healing; shared logic in
    betting_ml/scripts/sequential_bayes/catchup.py."""
    from betting_ml.utils.game_day import current_game_date
    from betting_ml.scripts.sequential_bayes import catchup as _catchup

    today = current_game_date()
    print(f"update_player_posteriors  CATCHUP  today={today}  lookback={lookback_days}d  dry_run={dry_run}")
    eb_priors = _load_priors_and_prep(today.year, sigma_obs, prior_neff_cap, dry_run)
    duck = _maybe_duck(use_s3)
    _catchup.run_catchup(
        label="player-seq-catchup",
        target_table=_TARGET_TABLE,
        today=today,
        lookback_days=lookback_days,
        get_connection=get_snowflake_connection,
        fetch_dicts=_fetch_dicts,
        process_date=lambda gd: update_for_date(
            gd, eb_priors, sigma_obs, prior_neff_cap, dry_run, duck=duck)["players_updated"],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Story 16.1: sequential per-player xwOBA posteriors")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--date", metavar="YYYY-MM-DD",
                       help="Update posteriors using completed games on this date")
    group.add_argument("--catchup", action="store_true",
                       help="Advance the chain over every completed date missing since the frontier "
                            "(in order, self-healing) — the daily default (replaces --date yesterday)")
    group.add_argument("--backfill", action="store_true",
                       help="Backfill entire season in chronological order (requires --season)")
    parser.add_argument("--lookback-days", type=int, default=10,
                        help="Catch-up window: max days back the chain can auto-advance (default 10)")
    parser.add_argument("--season", type=int, help="Season year for --backfill (e.g. 2026)")
    parser.add_argument("--sigma-obs", type=float, default=_SIGMA_OBS_DEFAULT,
                        help=f"Per-PA xwOBA observation std (default {_SIGMA_OBS_DEFAULT})")
    parser.add_argument("--prior-neff-cap", type=int, default=_PRIOR_NEFF_CAP_DEFAULT,
                        help=f"Max equivalent PA/BF a cold-start EB prior may be worth "
                             f"(default {_PRIOR_NEFF_CAP_DEFAULT})")
    parser.add_argument("--dry-run", action="store_true",
                        help="Compute updates but do not write to Snowflake")
    parser.add_argument("--s3", action="store_true",
                        help="E11.20 phase 1.5: read the mart_pitch_play_event PA substrate "
                             "from the S3 lakehouse via DuckDB instead of Snowflake (the EB "
                             "prior/role reads and the seq-posterior read/write stay on "
                             "Snowflake). Precondition for dropping the SF mart_pitch_* views.")
    args = parser.parse_args()

    if args.backfill and not args.season:
        parser.error("--backfill requires --season YEAR")
    if args.season and args.season < _FIRST_SEASON:
        parser.error(f"--season must be >= {_FIRST_SEASON} (first season with EB posteriors)")

    if args.backfill:
        print(f"update_player_posteriors  backfill season={args.season}  dry_run={args.dry_run}")
        run_backfill(args.season, args.sigma_obs, args.prior_neff_cap, dry_run=args.dry_run,
                     use_s3=args.s3)
    elif args.catchup:
        run_catchup(args.lookback_days, args.sigma_obs, args.prior_neff_cap, dry_run=args.dry_run,
                    use_s3=args.s3)
    else:
        target_date = date.fromisoformat(args.date)
        print(f"update_player_posteriors  date={target_date}  dry_run={args.dry_run}")
        run_single_date(target_date, args.sigma_obs, args.prior_neff_cap, dry_run=args.dry_run,
                        use_s3=args.s3)


if __name__ == "__main__":
    main()
