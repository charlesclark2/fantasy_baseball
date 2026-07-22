"""
update_team_posteriors.py — Epic 16, Story 16.3

Team-level sequential belief state — the same sequential-Bayes idea as 16.1
(update_player_posteriors.py) applied to whole-team rolling quality signals:

    off_xwoba      Normal-Normal   team offensive xwOBA (batting)
    bullpen_xwoba  Normal-Normal   team bullpen xwOBA-against (relievers only)
    win_prob       Beta-Binomial   team win probability (the Robinson analogue)

This is the direct mapping of Robinson's batting-average example onto the system:
belief about a team's win probability is a Beta distribution that updates after
every game — a 7-game win streak shifts the posterior right, three losses shift
it left — and the full posterior (mean AND variance) flows downstream as a
distribution of team quality rather than a scalar.

Chaining is identical in spirit to 16.1: each game's posterior becomes the next
game's prior. Cold-start (first game of the season) is a LEAGUE-AVERAGE prior,
season-scoped (every team opens league-average / .500 and accumulates), since
there is no per-team EB prior table:

    off_xwoba / bullpen_xwoba : prior_mu = league mean xwOBA (0.324),
                                prior_var = sigma_obs^2 / team_prior_neff
                                (deliberately weak, ~60 PA ≈ 1.6 games)
    win_prob                  : Beta(a0, b0) with a0 = b0 = win_prior_strength/2
                                (default 8 → Beta(4,4), .500 worth 8 games)

Sources (regular season only, game_type='R'):
    offense / bullpen : stg_batter_pitches (per-PA xwoba, inning_half → batting/
                        pitching team); bullpen restricted to reliever PAs via
                        eb_bullpen_posteriors (pitcher_id, game_pk) membership.
    win / loss        : mart_game_results.home_team_won.

Table: baseball_data.betting.team_sequential_posteriors
  Grain: (team, metric, season, game_pk)
  is_current = True marks the latest posterior per (team, metric, season)

Usage:
    uv run python betting_ml/scripts/sequential_bayes/update_team_posteriors.py --date 2026-06-02
    uv run python betting_ml/scripts/sequential_bayes/update_team_posteriors.py --date 2026-06-02 --dry-run
    uv run python betting_ml/scripts/sequential_bayes/update_team_posteriors.py --backfill --season 2026
    uv run python betting_ml/scripts/sequential_bayes/update_team_posteriors.py --backfill --season 2026 --dry-run
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import date, datetime, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(_PROJECT_ROOT / ".env")

from betting_ml.utils.data_loader import get_snowflake_connection
from betting_ml.scripts.sequential_bayes.update_player_posteriors import (
    normal_normal_update,
)

# ── Constants ──────────────────────────────────────────────────────────────────

_TARGET_TABLE = "baseball_data.betting.team_sequential_posteriors"

# Population per-PA xwOBA mean / std (2025: 181,231 PAs) — league-average cold
# start and observation noise for the two Normal-Normal team metrics.
_LEAGUE_MEAN_XWOBA   = 0.324
_SIGMA_OBS_DEFAULT   = 0.385

# Equivalent PA the league-average offense/bullpen prior is worth (weak on
# purpose — team beliefs should track the season, not anchor to the league).
_TEAM_PRIOR_NEFF_DEFAULT = 60

# Beta(a0,b0) = Beta(strength/2, strength/2): a .500 prior worth this many games.
_WIN_PRIOR_STRENGTH_DEFAULT = 8

_FIRST_SEASON = 2021

_M_OFF = "off_xwoba"
_M_PEN = "bullpen_xwoba"
_M_WIN = "win_prob"

_DDL = f"""
CREATE TABLE IF NOT EXISTS {_TARGET_TABLE} (
    team               VARCHAR(10)   NOT NULL,
    metric             VARCHAR(32)   NOT NULL,
    dist_type          VARCHAR(12)   NOT NULL,
    season             INTEGER       NOT NULL,
    game_pk            BIGINT        NOT NULL,
    game_date          DATE          NOT NULL,
    update_ts          TIMESTAMP_NTZ NOT NULL,
    prior_mu           FLOAT         NOT NULL,
    prior_sigma2       FLOAT         NOT NULL,
    obs_value          FLOAT         NOT NULL,
    n_obs              INTEGER       NOT NULL,
    posterior_mu       FLOAT         NOT NULL,
    posterior_sigma2   FLOAT         NOT NULL,
    param_a            FLOAT,
    param_b            FLOAT,
    n_cumulative       INTEGER       NOT NULL,
    is_current         BOOLEAN       NOT NULL,
    record_hash        VARCHAR(64)   NOT NULL
)
"""

# ── SQL ────────────────────────────────────────────────────────────────────────
# inning_half = 'Bot' → home team batting (away pitching); 'Top' → away batting.

_OFFENSE_SQL = """
SELECT
    game_pk,
    game_date,
    CASE WHEN inning_half = 'Bot' THEN home_team ELSE away_team END AS team,
    AVG(xwoba) AS obs_mean,
    COUNT(*)   AS n_obs
FROM baseball_data.betting.stg_batter_pitches
WHERE game_date = %(game_date)s
  AND game_type = 'R'
  AND plate_appearance_event IS NOT NULL
  AND xwoba IS NOT NULL
GROUP BY game_pk, game_date,
         CASE WHEN inning_half = 'Bot' THEN home_team ELSE away_team END
"""

_BULLPEN_SQL = """
SELECT
    p.game_pk,
    p.game_date,
    CASE WHEN p.inning_half = 'Bot' THEN p.away_team ELSE p.home_team END AS team,
    AVG(p.xwoba) AS obs_mean,
    COUNT(*)     AS n_obs
FROM baseball_data.betting.stg_batter_pitches p
JOIN (
    SELECT DISTINCT pitcher_id, game_pk
    FROM baseball_data.betting.eb_bullpen_posteriors
    WHERE game_date = %(game_date)s
) b
  ON p.pitcher_id = b.pitcher_id AND p.game_pk = b.game_pk
WHERE p.game_date = %(game_date)s
  AND p.game_type = 'R'
  AND p.plate_appearance_event IS NOT NULL
  AND p.xwoba IS NOT NULL
GROUP BY p.game_pk, p.game_date,
         CASE WHEN p.inning_half = 'Bot' THEN p.away_team ELSE p.home_team END
"""

_RESULTS_SQL = """
SELECT game_pk, game_date, home_team, away_team, home_team_won
FROM baseball_data.betting.mart_game_results
WHERE game_date = %(game_date)s
  AND game_type = 'R'
  AND home_team_won IS NOT NULL
"""

_SEASON_DATES_SQL = """
SELECT DISTINCT game_date
FROM baseball_data.betting.mart_game_results
WHERE game_year = %(season)s
  AND game_type = 'R'
  AND home_team_won IS NOT NULL
ORDER BY game_date
"""

_CURRENT_SEQ_SQL = """
SELECT team, metric, dist_type, posterior_mu, posterior_sigma2,
       param_a, param_b, n_cumulative
FROM {table}
WHERE is_current = TRUE
  AND season = %(season)s
"""


# ── Beta-Binomial conjugate update ─────────────────────────────────────────────

def beta_binomial_update(alpha: float, beta: float, wins: float, losses: float
                         ) -> tuple[float, float, float, float]:
    """
    Beta-Binomial update. Returns (post_alpha, post_beta, post_mean, post_var).
        post_alpha = alpha + wins ; post_beta = beta + losses
        mean = a/(a+b) ; var = a*b / ((a+b)^2 (a+b+1))
    """
    a = alpha + wins
    b = beta + losses
    s = a + b
    mean = a / s
    var  = (a * b) / (s * s * (s + 1.0))
    return a, b, mean, var


def beta_mean_var(alpha: float, beta: float) -> tuple[float, float]:
    s = alpha + beta
    return alpha / s, (alpha * beta) / (s * s * (s + 1.0))


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


def _load_current_seq(conn, season: int) -> dict[tuple[str, str], dict]:
    try:
        rows = _fetch_dicts(conn, _CURRENT_SEQ_SQL.format(table=_TARGET_TABLE), {"season": season})
    except Exception:
        return {}
    return {(r["team"], r["metric"]): r for r in rows}


# ── Observation collection ─────────────────────────────────────────────────────

def _as_date(v) -> date:
    """Coerce a game_date to a native datetime.date.

    INC-23/INC-27 bite: the offense/bullpen observations read baseball_data.betting.stg_batter_pitches,
    which is now a VIEW over the S3 lakehouse parquet (INC-27) that returns game_date as an ISO VARCHAR,
    while _RESULTS_SQL returns a native date. Mixing str + date breaks the chronological sort below
    (`'<' not supported between 'datetime.date' and 'str'`) and would write a str into the DATE column.
    Normalise at the use-site (same coercion already applied to the _DATES_SQL rows in run_all)."""
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v)[:10])


def _collect_observations(conn, target_date: date) -> list[dict]:
    """
    Chronologically-ordered per-(team, metric, game) observations:
        {team, metric, dist, game_pk, game_date, obs_value, n_obs}
    """
    d = target_date.isoformat()
    obs: list[dict] = []

    for r in _fetch_dicts(conn, _OFFENSE_SQL, {"game_date": d}):
        obs.append({"team": r["team"], "metric": _M_OFF, "dist": "normal",
                    "game_pk": int(r["game_pk"]), "game_date": _as_date(r["game_date"]),
                    "obs_value": float(r["obs_mean"]), "n_obs": int(r["n_obs"])})

    for r in _fetch_dicts(conn, _BULLPEN_SQL, {"game_date": d}):
        obs.append({"team": r["team"], "metric": _M_PEN, "dist": "normal",
                    "game_pk": int(r["game_pk"]), "game_date": _as_date(r["game_date"]),
                    "obs_value": float(r["obs_mean"]), "n_obs": int(r["n_obs"])})

    for r in _fetch_dicts(conn, _RESULTS_SQL, {"game_date": d}):
        home_won = bool(r["home_team_won"])
        obs.append({"team": r["home_team"], "metric": _M_WIN, "dist": "beta",
                    "game_pk": int(r["game_pk"]), "game_date": _as_date(r["game_date"]),
                    "obs_value": 1.0 if home_won else 0.0, "n_obs": 1})
        obs.append({"team": r["away_team"], "metric": _M_WIN, "dist": "beta",
                    "game_pk": int(r["game_pk"]), "game_date": _as_date(r["game_date"]),
                    "obs_value": 0.0 if home_won else 1.0, "n_obs": 1})

    obs.sort(key=lambda o: (o["game_date"], o["game_pk"], o["metric"], o["team"]))
    return obs


# ── Sequential chain ───────────────────────────────────────────────────────────

def _apply_updates(
    observations: list[dict],
    current_seq: dict[tuple[str, str], dict],
    sigma_obs: float,
    team_prior_neff: int,
    win_prior_strength: float,
    season: int,
    update_ts: datetime,
) -> list[dict]:
    normal_prior_var = (sigma_obs * sigma_obs) / team_prior_neff
    a0 = b0 = win_prior_strength / 2.0

    # working state: (team, metric) -> dict
    #   normal: {mu, var, n_cum} ; beta: {a, b, n_cum}
    working: dict[tuple[str, str], dict] = {}
    for key, r in current_seq.items():
        if r["dist_type"] == "beta":
            working[key] = {"a": float(r["param_a"]), "b": float(r["param_b"]),
                            "n_cum": int(r["n_cumulative"])}
        else:
            working[key] = {"mu": float(r["posterior_mu"]), "var": float(r["posterior_sigma2"]),
                            "n_cum": int(r["n_cumulative"])}

    new_rows: list[dict] = []

    for o in observations:
        key = (o["team"], o["metric"])

        if o["dist"] == "beta":
            if key in working:
                prior_a, prior_b, n_cum_prev = working[key]["a"], working[key]["b"], working[key]["n_cum"]
            else:
                prior_a, prior_b, n_cum_prev = a0, b0, 0
            prior_mu, prior_var = beta_mean_var(prior_a, prior_b)

            wins   = o["obs_value"]
            losses = 1.0 - o["obs_value"]
            post_a, post_b, post_mu, post_var = beta_binomial_update(prior_a, prior_b, wins, losses)
            n_cum = n_cum_prev + 1
            working[key] = {"a": post_a, "b": post_b, "n_cum": n_cum}
            param_a, param_b = post_a, post_b
        else:
            if key in working:
                prior_mu, prior_var, n_cum_prev = working[key]["mu"], working[key]["var"], working[key]["n_cum"]
            else:
                prior_mu, prior_var, n_cum_prev = _LEAGUE_MEAN_XWOBA, normal_prior_var, 0

            post_mu, post_var = normal_normal_update(prior_mu, prior_var, o["obs_value"], o["n_obs"], sigma_obs)
            n_cum = n_cum_prev + o["n_obs"]
            working[key] = {"mu": post_mu, "var": post_var, "n_cum": n_cum}
            param_a, param_b = None, None

        payload = (o["team"], o["metric"], o["game_pk"], round(post_mu, 8), round(post_var, 10), n_cum)
        record_hash = hashlib.sha256(str(payload).encode()).hexdigest()

        new_rows.append({
            "team":             o["team"],
            "metric":           o["metric"],
            "dist_type":        o["dist"],
            "season":           season,
            "game_pk":          o["game_pk"],
            "game_date":        o["game_date"],
            "update_ts":        update_ts,
            "prior_mu":         prior_mu,
            "prior_sigma2":     prior_var,
            "obs_value":        o["obs_value"],
            "n_obs":            o["n_obs"],
            "posterior_mu":     post_mu,
            "posterior_sigma2": post_var,
            "param_a":          param_a,
            "param_b":          param_b,
            "n_cumulative":     n_cum,
            "is_current":       True,
            "record_hash":      record_hash,
        })

    return new_rows


# ── Snowflake write ────────────────────────────────────────────────────────────

_COL_ORDER = [
    "team", "metric", "dist_type", "season", "game_pk", "game_date", "update_ts",
    "prior_mu", "prior_sigma2", "obs_value", "n_obs",
    "posterior_mu", "posterior_sigma2", "param_a", "param_b", "n_cumulative",
    "is_current", "record_hash",
]


def _write_updates(conn, new_rows: list[dict], season: int) -> dict[str, int]:
    if not new_rows:
        return {"closed": 0, "inserted": 0}

    affected = sorted({(r["team"], r["metric"]) for r in new_rows})
    cur = conn.cursor()

    placeholders = ", ".join(["(%s, %s)"] * len(affected))
    flat = [v for pair in affected for v in pair]
    cur.execute(
        f"""
        UPDATE {_TARGET_TABLE}
        SET is_current = FALSE
        WHERE is_current = TRUE
          AND season = {season}
          AND (team, metric) IN ({placeholders})
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
    sigma_obs: float,
    team_prior_neff: int,
    win_prior_strength: float,
    dry_run: bool,
) -> dict[str, int]:
    season    = target_date.year
    update_ts = datetime.now(timezone.utc).replace(tzinfo=None)

    conn = get_snowflake_connection()
    try:
        observations = _collect_observations(conn, target_date)
        if not observations:
            print(f"    {target_date}: no regular-season observations — skipping.")
            return {"rows": 0, "off": 0, "pen": 0, "win": 0, "closed": 0, "inserted": 0}

        current_seq = _load_current_seq(conn, season)
        new_rows = _apply_updates(
            observations, current_seq, sigma_obs, team_prior_neff, win_prior_strength, season, update_ts
        )

        by_metric = {m: sum(1 for r in new_rows if r["metric"] == m) for m in (_M_OFF, _M_PEN, _M_WIN)}
        print(f"    {target_date}: {len(new_rows)} updates "
              f"(off={by_metric[_M_OFF]} pen={by_metric[_M_PEN]} win={by_metric[_M_WIN]})")

        if dry_run:
            for r in new_rows[:3]:
                if r["dist_type"] == "beta":
                    print(f"      [DRY] {r['team']:<4} {r['metric']}: "
                          f"prior_mu={r['prior_mu']:.3f} obs={r['obs_value']:.0f} "
                          f"→ post_mu={r['posterior_mu']:.3f} Beta({r['param_a']:.1f},{r['param_b']:.1f}) "
                          f"n_cum={r['n_cumulative']}")
                else:
                    print(f"      [DRY] {r['team']:<4} {r['metric']}: "
                          f"prior_mu={r['prior_mu']:.4f} obs={r['obs_value']:.4f}(n={r['n_obs']}) "
                          f"→ post_mu={r['posterior_mu']:.4f} n_cum={r['n_cumulative']}")
            return {"rows": len(new_rows), **by_metric_to_keys(by_metric), "closed": 0, "inserted": 0}

        result = _write_updates(conn, new_rows, season)
        return {"rows": len(new_rows), **by_metric_to_keys(by_metric), **result}
    finally:
        conn.close()


def by_metric_to_keys(by_metric: dict[str, int]) -> dict[str, int]:
    return {"off": by_metric[_M_OFF], "pen": by_metric[_M_PEN], "win": by_metric[_M_WIN]}


# ── Runners ────────────────────────────────────────────────────────────────────

def _prep(season: int, sigma_obs: float, team_prior_neff: int, win_prior_strength: float, dry_run: bool):
    normal_prior_sigma = (sigma_obs / (team_prior_neff ** 0.5))
    a0 = win_prior_strength / 2.0
    print(f"  league_mean_xwoba={_LEAGUE_MEAN_XWOBA}  sigma_obs={sigma_obs:.4f}  "
          f"team_prior_neff={team_prior_neff} (prior_sigma={normal_prior_sigma:.4f})  "
          f"win_prior=Beta({a0:.1f},{a0:.1f})")
    if not dry_run:
        conn = get_snowflake_connection()
        try:
            print(f"\nEnsuring DDL for {_TARGET_TABLE}...")
            _ensure_table(conn)
        finally:
            conn.close()


def run_single_date(target_date: date, sigma_obs, team_prior_neff, win_prior_strength, dry_run: bool) -> None:
    print(f"\nTeam sequential posteriors — {target_date}")
    _prep(target_date.year, sigma_obs, team_prior_neff, win_prior_strength, dry_run)
    result = update_for_date(target_date, sigma_obs, team_prior_neff, win_prior_strength, dry_run)
    print(f"\n  rows={result['rows']}  off={result['off']}  pen={result['pen']}  win={result['win']}  "
          f"closed={result['closed']}  inserted={result['inserted']}")


def run_backfill(season: int, sigma_obs, team_prior_neff, win_prior_strength, dry_run: bool) -> None:
    print(f"\nTeam sequential posteriors — backfill season {season}")
    _prep(season, sigma_obs, team_prior_neff, win_prior_strength, dry_run)

    conn = get_snowflake_connection()
    try:
        rows = _fetch_dicts(conn, _SEASON_DATES_SQL, {"season": season})
    finally:
        conn.close()
    game_dates = [r["game_date"] if isinstance(r["game_date"], date)
                  else date.fromisoformat(str(r["game_date"])) for r in rows]
    print(f"  {len(game_dates)} game dates found")
    if not game_dates:
        print("No game dates found. Exiting.")
        return

    tot = {"rows": 0, "inserted": 0}
    print(f"\nProcessing {len(game_dates)} dates in chronological order...")
    for gd in game_dates:
        r = update_for_date(gd, sigma_obs, team_prior_neff, win_prior_strength, dry_run)
        tot["rows"] += r["rows"]
        tot["inserted"] += r.get("inserted", 0)

    print(f"\n{'[DRY RUN] ' if dry_run else ''}Backfill complete:")
    print(f"  total updates: {tot['rows']:,}")
    print(f"  total rows inserted: {tot['inserted']:,}")


def run_catchup(season_lookback_days: int, sigma_obs: float, team_prior_neff: int,
                win_prior_strength: float, dry_run: bool) -> None:
    """Advance the chain over every completed date missing since the frontier (2026-07-22 durable
    fix — replaces the fragile `--date yesterday`, which silently skipped a day whose source wasn't
    ready). Order-preserving + self-healing; see betting_ml/scripts/sequential_bayes/catchup.py."""
    from betting_ml.utils.game_day import current_game_date
    from betting_ml.scripts.sequential_bayes import catchup as _catchup

    today = current_game_date()
    print(f"update_team_posteriors  CATCHUP  today={today}  lookback={season_lookback_days}d  dry_run={dry_run}")
    _prep(today.year, sigma_obs, team_prior_neff, win_prior_strength, dry_run)
    _catchup.run_catchup(
        label="team-seq-catchup",
        target_table=_TARGET_TABLE,
        today=today,
        lookback_days=season_lookback_days,
        get_connection=get_snowflake_connection,
        fetch_dicts=_fetch_dicts,
        process_date=lambda gd: update_for_date(
            gd, sigma_obs, team_prior_neff, win_prior_strength, dry_run)["rows"],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Story 16.3: team-level sequential belief state")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--date", metavar="YYYY-MM-DD",
                       help="Update team posteriors using completed games on this date")
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
    parser.add_argument("--team-prior-neff", type=int, default=_TEAM_PRIOR_NEFF_DEFAULT,
                        help=f"Equivalent PA the league-average offense/bullpen prior is worth "
                             f"(default {_TEAM_PRIOR_NEFF_DEFAULT})")
    parser.add_argument("--win-prior-strength", type=float, default=_WIN_PRIOR_STRENGTH_DEFAULT,
                        help=f"Beta prior total weight a0+b0 for win_prob (default {_WIN_PRIOR_STRENGTH_DEFAULT})")
    parser.add_argument("--dry-run", action="store_true", help="Compute updates but do not write")
    args = parser.parse_args()

    if args.backfill and not args.season:
        parser.error("--backfill requires --season YEAR")
    if args.season and args.season < _FIRST_SEASON:
        parser.error(f"--season must be >= {_FIRST_SEASON}")

    if args.backfill:
        print(f"update_team_posteriors  backfill season={args.season}  dry_run={args.dry_run}")
        run_backfill(args.season, args.sigma_obs, args.team_prior_neff, args.win_prior_strength, args.dry_run)
    elif args.catchup:
        run_catchup(args.lookback_days, args.sigma_obs, args.team_prior_neff,
                    args.win_prior_strength, args.dry_run)
    else:
        target_date = date.fromisoformat(args.date)
        print(f"update_team_posteriors  date={target_date}  dry_run={args.dry_run}")
        run_single_date(target_date, args.sigma_obs, args.team_prior_neff, args.win_prior_strength, args.dry_run)


if __name__ == "__main__":
    main()
