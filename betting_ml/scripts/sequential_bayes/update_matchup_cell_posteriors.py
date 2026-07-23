"""
update_matchup_cell_posteriors.py — Epic 8, Story 8.5

Incremental Normal-Normal conjugate update of the 5×5 archetype × archetype
cell posteriors using observed plate appearance outcomes from completed games.

After each game, cells accumulate new (xwOBA − EB_additive_pred) residuals.
The Ridge model's season-start prediction serves as the informed prior with an
equivalent sample size of N_EFF_PRIOR = 30 PAs. As the season progresses, the
posterior shifts toward this season's actual observed outcomes.

Update rule (Normal-Normal, known observation variance):
    n_total   = n_pa_cumulative_prev + n_pa_new
    new_sum   = cumulative_obs_residual_sum_prev + sum_of_new_residuals
    post_mu   = (N_EFF_PRIOR × ridge_mu_0 + new_sum) / (N_EFF_PRIOR + n_total)
    post_σ    = sigma_obs / sqrt(N_EFF_PRIOR + n_total)

Where:
    ridge_mu_0 = Ridge model cell mean for the current season (prior mean)
    sigma_obs  = artifact["sigma"] ≈ model residual std (observation noise)
    N_EFF_PRIOR = 30 (ridge prediction is worth ~30 PA of prior evidence)

Table: baseball_data.betting.matchup_cell_sequential_posteriors
  Grain: (batter_archetype, pitcher_archetype, season, game_pk)
  is_current = True marks the latest posterior per (batter_arch, pitcher_arch, season)

Usage:
    # Daily update — run after mart_pitch_play_event loads for completed games
    uv run python betting_ml/scripts/sequential_bayes/update_matchup_cell_posteriors.py --date 2026-06-01
    uv run python betting_ml/scripts/sequential_bayes/update_matchup_cell_posteriors.py --date 2026-06-01 --dry-run

    # Season backfill — processes each game day in chronological order
    uv run python betting_ml/scripts/sequential_bayes/update_matchup_cell_posteriors.py --backfill --season 2026
    uv run python betting_ml/scripts/sequential_bayes/update_matchup_cell_posteriors.py --backfill --season 2026 --dry-run
"""

from __future__ import annotations

import argparse
import hashlib
import math
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(_PROJECT_ROOT / ".env")

from betting_ml.utils.data_loader import get_snowflake_connection
from betting_ml.scripts.eb_priors.generate_matchup_signals import (
    _load_artifacts,
    _build_cell_df,
    _score_cells,
    _load_posteriors,
    _posterior_as_of,
    _BATTER_CATS,
    _PITCHER_CATS,
    _UNIFORM_BATTER,
    _UNIFORM_PITCHER,
    # E11.1-W7a: reuse the canonical DuckDB/S3 helpers (one source of truth for the
    # connection + view registration + the source-table glob set).
    _get_duckdb,
    _register_s3_views,
    _duck_sql_for,
    _fetch_duck,
)

# ── Constants ──────────────────────────────────────────────────────────────────

_TARGET_TABLE = "baseball_data.betting.matchup_cell_sequential_posteriors"

# Number of PAs the Ridge season-start prediction is "worth" as a prior.
# With 30 equivalent PAs: after 30 new PAs the posterior is 50/50 prior/observed;
# after 90 new PAs the posterior is 75% driven by current-season data.
_N_EFF_PRIOR = 30

_FIRST_SEASON = 2021   # first season with archetype posteriors

_DDL = f"""
CREATE TABLE IF NOT EXISTS {_TARGET_TABLE} (
    batter_archetype             VARCHAR(100)  NOT NULL,
    pitcher_archetype            VARCHAR(100)  NOT NULL,
    season                       INTEGER       NOT NULL,
    game_pk                      BIGINT        NOT NULL,
    update_ts                    TIMESTAMP_NTZ NOT NULL,
    ridge_mu_0                   FLOAT         NOT NULL,
    n_eff_prior                  INTEGER       NOT NULL,
    prior_mu                     FLOAT         NOT NULL,
    prior_sigma                  FLOAT         NOT NULL,
    posterior_mu                 FLOAT         NOT NULL,
    posterior_sigma              FLOAT         NOT NULL,
    n_pa_observed                INTEGER       NOT NULL,
    n_pa_cumulative              INTEGER       NOT NULL,
    cumulative_obs_residual_sum  FLOAT         NOT NULL,
    is_current                   BOOLEAN       NOT NULL,
    record_hash                  VARCHAR(64)   NOT NULL
)
"""

# ── PA query ───────────────────────────────────────────────────────────────────

_PA_SQL = """
SELECT
    game_pk,
    game_date,
    game_year,
    batter_id,
    pitcher_id,
    xwoba
FROM baseball_data.betting.mart_pitch_play_event
WHERE game_date = %(game_date)s
  AND plate_appearance_event IS NOT NULL
  AND xwoba IS NOT NULL
ORDER BY game_pk, at_bat_number
"""

_PA_SEASON_SQL = """
SELECT DISTINCT game_date
FROM baseball_data.betting.mart_pitch_play_event
WHERE game_year = %(season)s
  AND plate_appearance_event IS NOT NULL
ORDER BY game_date
"""

# ── Current sequential posteriors ─────────────────────────────────────────────

_CURRENT_SEQ_SQL = """
SELECT
    batter_archetype,
    pitcher_archetype,
    posterior_mu,
    posterior_sigma,
    n_pa_cumulative,
    cumulative_obs_residual_sum,
    ridge_mu_0
FROM {table}
WHERE is_current = TRUE
  AND season = %(season)s
"""


def _ensure_table(conn) -> None:
    cur = conn.cursor()
    cur.execute(_DDL)
    conn.commit()
    cur.close()


def _load_pas(conn, target_date: date, duck=None) -> list[dict]:
    # E11.1-W7a: --s3 reads mart_pitch_play_event from S3 parquet via DuckDB. game_date is
    # VARCHAR ISO in parquet, so the equality vs the ISO literal matches as a string compare.
    if duck is not None:
        sql = _duck_sql_for(_PA_SQL).replace("%(game_date)s", f"'{target_date.isoformat()}'")
        return _fetch_duck(duck, sql)
    cur = conn.cursor()
    cur.execute(_PA_SQL, {"game_date": target_date.isoformat()})
    cols = [d[0].lower() for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    cur.close()
    return rows


def _load_game_dates_for_season(conn, season: int, duck=None) -> list[date]:
    # E11.1-W7a: --s3 reads mart_pitch_play_event from S3 parquet via DuckDB.
    if duck is not None:
        sql = _duck_sql_for(_PA_SEASON_SQL).replace("%(season)s", str(int(season)))
        dates = [r["game_date"] for r in _fetch_duck(duck, sql)]
    else:
        cur = conn.cursor()
        cur.execute(_PA_SEASON_SQL, {"season": season})
        dates = [r[0] for r in cur.fetchall()]
        cur.close()
    return [d if isinstance(d, date) else date.fromisoformat(str(d)) for d in dates]


def _load_current_seq_posteriors(conn, season: int) -> dict[tuple[str, str], dict]:
    """Return {(batter_arch, pitcher_arch): row_dict} for is_current=True rows.
    Returns {} gracefully if the table doesn't exist yet (first run / dry-run)."""
    try:
        cur = conn.cursor()
        cur.execute(
            _CURRENT_SEQ_SQL.format(table=_TARGET_TABLE),
            {"season": season},
        )
        cols = [d[0].lower() for d in cur.description]
        rows = {
            (r[0], r[1]): dict(zip(cols, r))
            for r in cur.fetchall()
        }
        cur.close()
        return rows
    except Exception:
        return {}


# ── Cell observation collection ────────────────────────────────────────────────

def _map_cluster_for_update(posteriors: dict, player_id, player_type: str, game_date) -> str | None:
    """
    MAP archetype for cell assignment in the update script.

    First tries the most recent row with as_of_date < game_date (same temporal guard
    as _posterior_as_of). Falls back to any available seasonal row — mart_player_archetype_posteriors
    has one row per player (their first-threshold date), so early-season games have no
    prior-dated row and would otherwise be dropped entirely.
    """
    if player_id is None:
        return None
    rows = posteriors.get((int(player_id), player_type), [])
    if not rows:
        return None
    best = None
    for r in rows:
        aod = r["as_of_date"]
        if isinstance(aod, str):
            aod = date.fromisoformat(aod)
        elif isinstance(aod, datetime):  # S3 parquet may hand back TIMESTAMP → datetime; narrow to date
            aod = aod.date()
        if aod < game_date:
            best = r
        else:
            break
    target_row = best if best is not None else rows[-1]
    return target_row.get("map_cluster")


def _collect_cell_observations(
    pas: list[dict],
    posteriors: dict,
    eb: dict,
) -> dict[tuple[str, str], dict]:
    """
    For each PA, resolve batter/pitcher MAP archetypes and compute the
    interaction residual (xwOBA − EB_additive_pred). Group by (b_arch, p_arch).

    Returns {(batter_arch, pitcher_arch): {"n_pa": int, "residual_sum": float, "game_pk": int}}
    """
    batt_effects  = eb["batter_effects"]
    pitch_effects = eb["pitcher_effects"]
    grand_mean    = eb["global"]["grand_mean_xwoba"]

    cell_obs: dict[tuple[str, str], dict] = defaultdict(lambda: {"n_pa": 0, "residual_sum": 0.0, "game_pk": None})

    for pa in pas:
        game_date = pa["game_date"]
        if isinstance(game_date, str):
            game_date = date.fromisoformat(game_date)

        batter_id  = pa.get("batter_id")
        pitcher_id = pa.get("pitcher_id")
        xwoba      = float(pa["xwoba"])

        b_map = _map_cluster_for_update(posteriors, batter_id, "batter", game_date)
        p_map = _map_cluster_for_update(posteriors, pitcher_id, "pitcher", game_date)

        if b_map is None or p_map is None:
            continue
        if b_map not in _BATTER_CATS or p_map not in _PITCHER_CATS:
            continue

        eb_additive_pred = grand_mean + batt_effects.get(b_map, 0.0) + pitch_effects.get(p_map, 0.0)
        residual = xwoba - eb_additive_pred

        key = (b_map, p_map)
        cell_obs[key]["n_pa"]         += 1
        cell_obs[key]["residual_sum"] += residual
        cell_obs[key]["game_pk"]       = int(pa["game_pk"])

    return dict(cell_obs)


# ── Normal-Normal conjugate update ─────────────────────────────────────────────

def _apply_updates(
    cell_obs: dict[tuple[str, str], dict],
    current_seq: dict[tuple[str, str], dict],
    ridge_cell_means: dict[tuple[str, str], float],
    sigma_obs: float,
    season: int,
    update_ts: datetime,
) -> list[dict]:
    """
    Apply incremental Normal-Normal update for each cell with new observations.

    Returns list of new rows to insert (all with is_current=True).
    """
    new_rows: list[dict] = []

    for (b_arch, p_arch), obs in cell_obs.items():
        n_pa_new     = obs["n_pa"]
        residual_sum = obs["residual_sum"]
        game_pk      = obs["game_pk"]

        ridge_mu_0 = ridge_cell_means.get((b_arch, p_arch), 0.0)

        if (b_arch, p_arch) in current_seq:
            prev = current_seq[(b_arch, p_arch)]
            prior_mu              = float(prev["posterior_mu"])
            prior_sigma           = float(prev["posterior_sigma"])
            n_pa_cumulative_prev  = int(prev["n_pa_cumulative"])
            cumulative_sum_prev   = float(prev["cumulative_obs_residual_sum"])
        else:
            # Cold start: prior is the Ridge model prediction
            prior_mu             = ridge_mu_0
            prior_sigma          = sigma_obs / math.sqrt(_N_EFF_PRIOR)
            n_pa_cumulative_prev = 0
            cumulative_sum_prev  = 0.0

        n_pa_total  = n_pa_cumulative_prev + n_pa_new
        cumul_sum   = cumulative_sum_prev + residual_sum

        # Normal-Normal update: known observation variance sigma_obs^2
        # post_mu   = (N_EFF * mu_0 + cumul_sum) / (N_EFF + n_total)
        # post_sigma = sigma_obs / sqrt(N_EFF + n_total)
        n_eff_total     = _N_EFF_PRIOR + n_pa_total
        posterior_mu    = (_N_EFF_PRIOR * ridge_mu_0 + cumul_sum) / n_eff_total
        posterior_sigma = sigma_obs / math.sqrt(n_eff_total)

        payload = (posterior_mu, posterior_sigma, n_pa_total, cumul_sum)
        record_hash = hashlib.sha256(str(payload).encode()).hexdigest()[:32]

        new_rows.append({
            "batter_archetype":            b_arch,
            "pitcher_archetype":           p_arch,
            "season":                      season,
            "game_pk":                     game_pk,
            "update_ts":                   update_ts,
            "ridge_mu_0":                  ridge_mu_0,
            "n_eff_prior":                 _N_EFF_PRIOR,
            "prior_mu":                    prior_mu,
            "prior_sigma":                 prior_sigma,
            "posterior_mu":                posterior_mu,
            "posterior_sigma":             posterior_sigma,
            "n_pa_observed":               n_pa_new,
            "n_pa_cumulative":             n_pa_total,
            "cumulative_obs_residual_sum": cumul_sum,
            "is_current":                  True,
            "record_hash":                 record_hash,
        })

    return new_rows


# ── Snowflake write ────────────────────────────────────────────────────────────

def _write_updates(
    conn,
    new_rows: list[dict],
    season: int,
    game_pk: int,
) -> dict[str, int]:
    """
    SCD-2 write pattern:
      1. Flip is_current=False for affected cells in this season
      2. INSERT new rows with is_current=True
    """
    if not new_rows:
        return {"closed": 0, "inserted": 0}

    affected_cells = [(r["batter_archetype"], r["pitcher_archetype"]) for r in new_rows]
    cur = conn.cursor()

    # Step 1: flip existing current rows for affected cells
    placeholders = ", ".join(["(%s, %s)"] * len(affected_cells))
    flat_values  = [v for pair in affected_cells for v in pair]
    update_sql = f"""
    UPDATE {_TARGET_TABLE}
    SET is_current = FALSE
    WHERE is_current = TRUE
      AND season = {season}
      AND (batter_archetype, pitcher_archetype) IN ({placeholders})
    """
    cur.execute(update_sql, flat_values)
    closed = cur.rowcount

    # Step 2: INSERT new rows
    # Use VARCHAR temp table + PARSE_JSON-free approach (all columns are scalar)
    col_order = [
        "batter_archetype", "pitcher_archetype", "season", "game_pk", "update_ts",
        "ridge_mu_0", "n_eff_prior", "prior_mu", "prior_sigma",
        "posterior_mu", "posterior_sigma",
        "n_pa_observed", "n_pa_cumulative", "cumulative_obs_residual_sum",
        "is_current", "record_hash",
    ]
    placeholders_row = ", ".join(["%s"] * len(col_order))
    insert_sql = f"""
    INSERT INTO {_TARGET_TABLE}
        ({", ".join(col_order)})
    VALUES ({placeholders_row})
    """
    data = [[r[c] for c in col_order] for r in new_rows]
    cur.executemany(insert_sql, data)
    inserted = len(new_rows)

    conn.commit()
    cur.close()
    return {"closed": closed, "inserted": inserted}


# ── Per-date orchestration ─────────────────────────────────────────────────────

# ── E11.1-W7a lakehouse: read-on-DuckDB ───────────────────────────────────────
# `--s3` repoints the SOURCE reads (mart_pitch_play_event PA substrate via _PA_SQL/_PA_SEASON_SQL,
# and the cell-feature/posteriors reads inherited from generate_matchup_signals._build_cell_df /
# _load_posteriors) at S3 parquet via DuckDB so the operator can stop running the Snowflake
# cluster/posterior builds. The WRITES stay on Snowflake: the matchup_cell_sequential_posteriors
# read (_load_current_seq_posteriors) and the UPDATE/INSERT (_write_updates + _ensure_table) are
# UNCHANGED. So in --s3 mode this script holds BOTH a DuckDB connection (S3 reads) and a Snowflake
# connection (seq-posteriors read + write).


def _build_ridge_cell_means(
    artifact: dict,
    eb: dict,
    conn,
    season: int,
    duck=None,
) -> dict[tuple[str, str], float]:
    """Build Ridge model cell mean lookup for the given season.

    E11.1-W7a: when `duck` is provided (--s3), the cell features read from S3 via DuckDB.
    """
    prior_season = season - 1
    cell_df = _build_cell_df(conn, prior_season, eb, duck=duck)
    cell_means, _, _, _ = _score_cells(artifact, cell_df)
    means: dict[tuple[str, str], float] = {}
    for bi, b in enumerate(_BATTER_CATS):
        for pi, p in enumerate(_PITCHER_CATS):
            means[(b, p)] = float(cell_means[bi, pi])
    return means


def update_for_date(
    target_date: date,
    artifact: dict,
    eb: dict,
    ridge_cell_means: dict[tuple[str, str], float],
    posteriors: dict,
    dry_run: bool,
    duck=None,
) -> dict[str, int]:
    """
    Update sequential cell posteriors for all completed games on target_date.
    Artifacts and posteriors are passed in (cached by caller for backfill runs).

    E11.1-W7a: when `duck` is provided (--s3), the PA substrate reads from S3 via DuckDB.
    The seq-posteriors read + write below STILL use the Snowflake `conn`.
    """
    season      = target_date.year
    sigma_obs   = float(artifact["sigma"])
    update_ts   = datetime.now(timezone.utc).replace(tzinfo=None)

    conn = get_snowflake_connection()
    try:
        pas = _load_pas(conn, target_date, duck=duck)
        if not pas:
            print(f"    {target_date}: no PAs found — skipping.")
            return {"cells_updated": 0, "pa_processed": 0, "closed": 0, "inserted": 0}

        current_seq = _load_current_seq_posteriors(conn, season)
        cell_obs    = _collect_cell_observations(pas, posteriors, eb)

        if not cell_obs:
            print(f"    {target_date}: {len(pas):,} PAs — no cell assignments (no archetype posteriors). Skipping.")
            return {"cells_updated": 0, "pa_processed": len(pas), "closed": 0, "inserted": 0}

        n_pa_assigned = sum(v["n_pa"] for v in cell_obs.values())
        new_rows = _apply_updates(
            cell_obs, current_seq, ridge_cell_means, sigma_obs, season, update_ts
        )

        example_game_pk = next(v["game_pk"] for v in cell_obs.values() if v["game_pk"])

        print(
            f"    {target_date}: {len(pas):,} PAs → {n_pa_assigned:,} assigned "
            f"({100*n_pa_assigned/len(pas):.0f}%) across {len(new_rows)} cells"
        )

        if dry_run:
            # Print a sample cell update
            if new_rows:
                r = new_rows[0]
                print(
                    f"      [DRY RUN] {r['batter_archetype']} × {r['pitcher_archetype']}: "
                    f"prior_mu={r['prior_mu']:+.5f} → post_mu={r['posterior_mu']:+.5f}  "
                    f"n_pa_cumulative={r['n_pa_cumulative']}"
                )
            return {"cells_updated": len(new_rows), "pa_processed": n_pa_assigned, "closed": 0, "inserted": 0}

        result = _write_updates(conn, new_rows, season, example_game_pk)
        return {
            "cells_updated": len(new_rows),
            "pa_processed":  n_pa_assigned,
            **result,
        }
    finally:
        conn.close()


# ── Main orchestration ─────────────────────────────────────────────────────────

def run_single_date(target_date: date, dry_run: bool, use_s3: bool = False) -> None:
    season = target_date.year

    # E11.1-W7a: in --s3 mode the SOURCE reads (cell features, posteriors, PA substrate) come
    # from S3 via this DuckDB connection; the DDL + seq-posteriors read/write stay on Snowflake.
    duck = None
    if use_s3:
        print("\n[--s3] Reading matchup sources from S3 lakehouse via DuckDB...")
        duck = _get_duckdb()
        _register_s3_views(duck)

    print(f"\nLoading artifacts...")
    artifact, eb = _load_artifacts()
    sigma_obs = float(artifact["sigma"])
    print(f"  sigma_obs={sigma_obs:.5f}  N_EFF_PRIOR={_N_EFF_PRIOR}")

    print(f"\nBuilding Ridge cell means for season {season} (prior_season={season-1})...")
    src_conn = None if use_s3 else get_snowflake_connection()
    try:
        ridge_cell_means = _build_ridge_cell_means(artifact, eb, src_conn, season, duck=duck)
        print(f"  {len(ridge_cell_means)} cells built")

        print(f"\nLoading archetype posteriors (season={season})...")
        posteriors = _load_posteriors(src_conn, season, duck=duck)
        print(f"  {len(posteriors):,} player-seasons loaded")
    finally:
        if src_conn is not None:
            src_conn.close()

    if not dry_run:
        print(f"\nEnsuring DDL for {_TARGET_TABLE} (Snowflake)...")
        conn = get_snowflake_connection()
        try:
            _ensure_table(conn)
        finally:
            conn.close()

    print(f"\nUpdating sequential posteriors for {target_date}...")
    result = update_for_date(target_date, artifact, eb, ridge_cell_means, posteriors, dry_run, duck=duck)
    print(f"\n  cells_updated={result['cells_updated']}  pa_processed={result['pa_processed']}  "
          f"closed={result['closed']}  inserted={result['inserted']}")

    if duck is not None:
        duck.close()


def run_backfill(season: int, dry_run: bool, use_s3: bool = False) -> None:
    # E11.1-W7a: --s3 reads sources from S3 via DuckDB; DDL + seq-posteriors read/write stay on Snowflake.
    duck = None
    if use_s3:
        print("\n[--s3] Reading matchup sources from S3 lakehouse via DuckDB...")
        duck = _get_duckdb()
        _register_s3_views(duck)

    print(f"\nLoading artifacts...")
    artifact, eb = _load_artifacts()
    sigma_obs = float(artifact["sigma"])
    print(f"  sigma_obs={sigma_obs:.5f}  N_EFF_PRIOR={_N_EFF_PRIOR}")

    print(f"\nBuilding Ridge cell means for season {season} (prior_season={season-1})...")
    src_conn = None if use_s3 else get_snowflake_connection()
    try:
        ridge_cell_means = _build_ridge_cell_means(artifact, eb, src_conn, season, duck=duck)
        print(f"  {len(ridge_cell_means)} cells built")

        print(f"\nLoading archetype posteriors (season={season})...")
        posteriors = _load_posteriors(src_conn, season, duck=duck)
        print(f"  {len(posteriors):,} player-seasons loaded")

        print(f"\nFetching game dates for season {season}...")
        game_dates = _load_game_dates_for_season(src_conn, season, duck=duck)
        print(f"  {len(game_dates)} game dates found")
    finally:
        if src_conn is not None:
            src_conn.close()

    if not dry_run:
        print(f"\nEnsuring DDL for {_TARGET_TABLE} (Snowflake)...")
        conn = get_snowflake_connection()
        try:
            _ensure_table(conn)
        finally:
            conn.close()

    if not game_dates:
        print("No game dates found. Exiting.")
        if duck is not None:
            duck.close()
        return

    total_cells = 0
    total_pa    = 0
    total_ins   = 0

    print(f"\nProcessing {len(game_dates)} dates in chronological order...")
    for gd in game_dates:
        result = update_for_date(gd, artifact, eb, ridge_cell_means, posteriors, dry_run, duck=duck)
        total_cells += result["cells_updated"]
        total_pa    += result["pa_processed"]
        total_ins   += result["inserted"]

    print(f"\n{'[DRY RUN] ' if dry_run else ''}Backfill complete:")
    print(f"  total cells updated: {total_cells:,}")
    print(f"  total PAs processed: {total_pa:,}")
    print(f"  total rows inserted: {total_ins:,}")

    if duck is not None:
        duck.close()


def run_catchup(lookback_days: int, dry_run: bool, use_s3: bool = False) -> None:
    """Advance the chain over every completed date missing since the frontier (2026-07-22 durable
    fix — replaces the fragile `--date yesterday`). Mirrors run_backfill's one-time artifact/ridge/
    posterior setup, then drives the shared catch-up. See catchup.py."""
    from betting_ml.utils.game_day import current_game_date
    from betting_ml.scripts.sequential_bayes import catchup as _catchup

    today = current_game_date()
    season = today.year
    print(f"update_matchup_cell_posteriors  CATCHUP  today={today}  lookback={lookback_days}d  "
          f"dry_run={dry_run}  s3={use_s3}")

    duck = None
    if use_s3:
        print("\n[--s3] Reading matchup sources from S3 lakehouse via DuckDB...")
        duck = _get_duckdb()
        _register_s3_views(duck)

    artifact, eb = _load_artifacts()
    src_conn = None if use_s3 else get_snowflake_connection()
    try:
        ridge_cell_means = _build_ridge_cell_means(artifact, eb, src_conn, season, duck=duck)
        posteriors = _load_posteriors(src_conn, season, duck=duck)
    finally:
        if src_conn is not None:
            src_conn.close()

    if not dry_run:
        conn = get_snowflake_connection()
        try:
            _ensure_table(conn)
        finally:
            conn.close()

    _catchup.run_catchup(
        label="matchup-seq-catchup",
        target_table=_TARGET_TABLE,
        today=today,
        lookback_days=lookback_days,
        get_connection=get_snowflake_connection,
        # This chain is grained on (batter_arch, pitcher_arch, season, game_pk) — no game_date
        # column — so derive the frontier date by joining game_pk → mart_game_results.game_date.
        frontier_sql=(
            f"SELECT MAX(r.game_date) AS d FROM {_TARGET_TABLE} p "
            "JOIN baseball_data.betting.mart_game_results r ON p.game_pk = r.game_pk "
            "WHERE p.season = %(season)s"
        ),
        process_date=lambda gd: update_for_date(
            gd, artifact, eb, ridge_cell_means, posteriors, dry_run, duck=duck)["cells_updated"],
    )
    if duck is not None:
        duck.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Story 8.5: update archetype cell sequential posteriors"
    )
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
    parser.add_argument("--season", type=int,
                        help="Season year for --backfill (e.g. 2026)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Compute updates but do not write to Snowflake")
    parser.add_argument("--s3", action="store_true",
                        help="E11.1-W7a: read SOURCE tables (mart_pitch_play_event PA substrate, "
                             "cell features, archetype posteriors) from S3 parquet via DuckDB. "
                             "The seq-posteriors read + UPDATE/INSERT stay on Snowflake.")
    args = parser.parse_args()

    if args.backfill and not args.season:
        parser.error("--backfill requires --season YEAR")
    if args.season and args.season < _FIRST_SEASON:
        parser.error(f"--season must be >= {_FIRST_SEASON} (first season with archetype posteriors)")

    if args.backfill:
        print(f"update_matchup_cell_posteriors  backfill season={args.season}  "
              f"dry_run={args.dry_run}  s3={args.s3}")
        run_backfill(args.season, dry_run=args.dry_run, use_s3=args.s3)
    elif args.catchup:
        run_catchup(args.lookback_days, dry_run=args.dry_run, use_s3=args.s3)
    else:
        target_date = date.fromisoformat(args.date)
        print(f"update_matchup_cell_posteriors  date={target_date}  "
              f"dry_run={args.dry_run}  s3={args.s3}")
        run_single_date(target_date, dry_run=args.dry_run, use_s3=args.s3)


if __name__ == "__main__":
    main()
