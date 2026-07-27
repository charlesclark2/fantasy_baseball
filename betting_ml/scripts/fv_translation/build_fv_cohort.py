"""build_fv_cohort.py — MLB Edge-E7.8: assemble the prospect→realized-MLB study matrix ONCE.

Reads THE BOARD's as-of FV/rank snapshots (E7.7), routes each prospect to the MLBAM spine (E7.4),
attaches his MiLB line **as of the board date**, and attaches the realized MLB outcome over the
following `--horizon` seasons — all SF-FREE, DuckDB over the S3 Delta lake. Writes ONE parquet the
bake-off reads (the §0.5 "assemble once → parquet; every candidate/fold reads the cache" discipline).

⚠️ OPERATOR-RUN (>2 min, S3 I/O over the 4.6M-row MiLB substrate + both MLB rolling-stat marts). A
`--seasons`/`--limit` smoke is provided for a cheap first pass.

WHAT A ROW IS
-------------
One row per **(board_season, prospect)** — the player as FanGraphs graded him on that season's board,
paired with what he then did in the majors. The same person appears in several cohorts (that is the
point: the study asks whether the grade AT THAT MOMENT projected), which is exactly why the CV purges
a player from any training fold that also evaluates him (see fv_translation.cohort_folds).

  * **FV side (E7.7, as-of)** — `fv`, `risk`, `eta`, `overall_rank`, `org_rank`,
    `fantasy_dynasty_rank`, read at the season's LATEST `as_of_date` snapshot.
    ⚠️ **PRE-2026 AS-OF IS APPROXIMATE** — FanGraphs serves the RETAINED past board rather than a true
    point-in-time snapshot, and E7.7 stamps those rows `<season>-07-01`. So a pre-2026 grade may embed
    a later revision. The forward daily capture builds the genuine point-in-time series from 2026 on.
    This biases the study TOWARD finding FV lift, so a NULL verdict is conservative; a POSITIVE verdict
    must be read with the caveat attached. Stated in the report, never silently.
  * **NULL side** — `level` (as-of), `age`, `pro_experience_years` (board season − first professional
    season in the E7.1 logs), `pre_board_mlb_pa`. Age-relative-to-level is derived IN-FOLD.
  * **PERF side** — the player's MiLB counting line over every regular-season game STRICTLY BEFORE the
    board's `as_of_date` (the as-of leakage guard), rates computed by the E7.3/E7.3p formula home.
  * **OUTCOME side** — MLB games with `game_date > as_of_date` and `game_year <= board_season +
    horizon`: PA/BF, hits, HR, BB, K (and the pitcher mirror). A prospect who never appears carries
    ZEROS — a realized dynasty outcome, not missing data.

⚠️ **THE BOARD HAS EXACTLY ONE VALID READER** (E7.4 landmines): `delta_scan` hard-errors on its
`void`-typed `mlbam_id`, and a `read_parquet` GLOB unions TOMBSTONED files and fabricates a wrong
number. This module imports `player_xref.register_board` and the xref's own bridge SQL rather than
re-deriving either — one reader, one bridge, one place to fix.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.scripts.milb_mle.milb_mle import (  # noqa: E402
    compute_pitcher_rate_metrics_from_counts,
    compute_rate_metrics_from_counts,
)
from betting_ml.scripts.milb_xref import player_xref as px  # noqa: E402
from betting_ml.scripts.fv_translation.fv_translation import (  # noqa: E402
    attach_outcome,
    resolve_player_type,
    unknown_position_tokens,
)

log = logging.getLogger("e7_8.cohort")

BUCKET = "s3://baseball-betting-ml-artifacts"
MILB = f"{BUCKET}/baseball/milb"

_BAT_SUMS = [
    "bat_plate_appearances", "bat_at_bats", "bat_hits", "bat_doubles", "bat_triples",
    "bat_home_runs", "bat_walks", "bat_intentional_walks", "bat_hit_by_pitch", "bat_sac_flies",
    "bat_strike_outs", "bat_total_bases",
]
_PIT_SUMS = [
    "pit_batters_faced", "pit_strike_outs", "pit_walks", "pit_home_runs",
    "pit_ground_outs", "pit_air_outs", "pit_games_played", "pit_games_started",
]


def _connect():
    """DuckDB with the S3 credential chain + the Delta extension, the MLB marts registered as views,
    and THE BOARD registered through its one valid reader."""
    from scripts.utils.lakehouse_read import duck_connect, register_views

    conn = duck_connect()
    try:
        conn.execute("INSTALL delta; LOAD delta")
    except Exception as e:  # noqa: BLE001
        log.warning("delta extension load failed (%s) — the MiLB delta_scan will fail", e)
    register_views(conn, ["mart_batter_rolling_stats", "mart_pitcher_rolling_stats"])
    conn.execute(f"CREATE OR REPLACE VIEW milb_logs AS SELECT * FROM delta_scan('{MILB}/player_game_logs')")
    px.register_board(conn)          # ⚠️ the ONLY valid board reader (E7.4 landmines 1+2)
    return conn


def _assembly_sql(horizon: int, season_floor: int | None, season_ceiling: int | None,
                  src: "px.XrefSources | None" = None) -> str:
    """The one query. `src` is the xref's own source set so the board dedupe and both MLBAM bridge
    legs are the SAME SQL E7.4 match-counted on the real lake — never a re-derivation.

    ⚠️ `src` is INJECTABLE for the same reason E7.4's is: this SQL is otherwise CI-invisible (it reads
    S3), and a broken assembly is discovered only after a multi-minute operator run. The fast gate
    executes this EXACT string against local DuckDB fixtures — the runtime-gate risk that actually
    bites (CLAUDE.md: CI-green is not a merge gate for lakehouse reads) bought down as far as it can
    be without real S3.
    """
    src = src or px.s3_sources()
    bat_sum = ",\n               ".join(f"sum(coalesce(m.{c}, 0)) as {c}" for c in _BAT_SUMS)
    pit_sum = ",\n               ".join(f"sum(coalesce(m.{c}, 0)) as {c}" for c in _PIT_SUMS)
    season_where = []
    if season_floor:
        season_where.append(f"season >= {int(season_floor)}")
    if season_ceiling:
        season_where.append(f"season <= {int(season_ceiling)}")
    board_filter = ("where " + " and ".join(season_where)) if season_where else ""
    return f"""
    with board_all as ({px._board_latest_sql(src)}),
         board as (select * from board_all {board_filter}),
         lb as ({px._leaderboard_bridge_sql(src)}),
         fg_mlb as ({px._fg_mlb_bridge_sql(src)}),
         resolved as (
            -- the E7.4 chain: leaderboard xMLBAMID first, the numeric graduate leg second
            select b.season                                            as board_season,
                   b.as_of_date                                        as as_of_date,
                   b.as_of_date::date                                  as as_of_dt,
                   b.fg_minor_id, b.fg_player_id, b.player_name, b.org, b.position,
                   b.level, b.age, b.fv, b.risk, b.eta,
                   b.overall_rank, b.org_rank,
                   b.fantasy_dynasty_rank, b.fantasy_redraft_rank,
                   coalesce(l.mlbam_id, g.mlbam_id)                    as mlbam_id
            from board b
            left join lb l on b.fg_minor_id = l.fg_minor_id
            left join fg_mlb g on b.fg_player_id = g.fg_mlb_id
                              and regexp_matches(b.fg_player_id, '^[0-9]+$')
         ),
         milb as (
            select cast(l.player_id as varchar)  as mlbam_id,
                   l.official_date::date         as gd,          -- INC-23: ISO VARCHAR → cast at use
                   l.season, l.level_name, l.is_batter, l.is_pitcher,
                   {", ".join("l." + c for c in _BAT_SUMS + _PIT_SUMS)}
            from milb_logs l
            where l.game_type = 'R'
         ),
         minor_line as (
            -- the player's professional line STRICTLY BEFORE the board snapshot (the as-of guard)
            select r.board_season, r.fg_minor_id,
                   {bat_sum},
                   {pit_sum},
                   min(m.season)                                       as first_milb_season,
                   max(m.season)                                       as last_milb_season,
                   count(*)                                            as milb_games,
                   sum(case when m.is_batter  then 1 else 0 end)       as milb_batter_games,
                   sum(case when m.is_pitcher then 1 else 0 end)       as milb_pitcher_games,
                   argmax(m.level_name, m.gd)                          as top_level_pre_board
            from resolved r
            join milb m on m.mlbam_id = r.mlbam_id and m.gd < r.as_of_dt
            group by 1, 2
         ),
         mlb_bat as (
            select cast(batter_id as varchar) as mlbam_id, game_date::date as gd, game_year,
                   coalesce(pa_count, 0) as pa_count, coalesce(hits, 0) as hits,
                   coalesce(home_runs, 0) as home_runs, coalesce(walks, 0) as walks,
                   coalesce(strikeouts, 0) as strikeouts
            from mart_batter_rolling_stats
         ),
         mlb_pit as (
            select cast(pitcher_id as varchar) as mlbam_id, game_date::date as gd, game_year,
                   coalesce(batters_faced, 0) as batters_faced, coalesce(hits_allowed, 0) as hits_allowed,
                   coalesce(walks, 0) as walks, coalesce(strikeouts, 0) as strikeouts,
                   coalesce(home_runs_allowed, 0) as home_runs_allowed
            from mart_pitcher_rolling_stats
         ),
         bat_window as (
            select r.board_season, r.fg_minor_id,
                   sum(b.pa_count) as mlb_pa, sum(b.hits) as mlb_hits,
                   sum(b.home_runs) as mlb_home_runs, sum(b.walks) as mlb_walks,
                   sum(b.strikeouts) as mlb_strikeouts
            from resolved r
            join mlb_bat b on b.mlbam_id = r.mlbam_id
                          and b.gd > r.as_of_dt
                          and b.game_year <= r.board_season + {int(horizon)}
            group by 1, 2
         ),
         pit_window as (
            select r.board_season, r.fg_minor_id,
                   sum(p.batters_faced) as mlb_batters_faced, sum(p.hits_allowed) as mlb_hits_allowed,
                   sum(p.walks) as mlb_walks_allowed, sum(p.strikeouts) as mlb_strikeouts_pitched,
                   sum(p.home_runs_allowed) as mlb_home_runs_allowed
            from resolved r
            join mlb_pit p on p.mlbam_id = r.mlbam_id
                          and p.gd > r.as_of_dt
                          and p.game_year <= r.board_season + {int(horizon)}
            group by 1, 2
         ),
         pre_board_mlb as (
            -- MLB exposure the prospect ALREADY had at the board date (a control, not an outcome)
            select r.board_season, r.fg_minor_id,
                   coalesce(sum(b.pa_count), 0) as pre_board_mlb_pa
            from resolved r
            left join mlb_bat b on b.mlbam_id = r.mlbam_id and b.gd <= r.as_of_dt
            group by 1, 2
         ),
         pre_board_mlb_pit as (
            select r.board_season, r.fg_minor_id,
                   coalesce(sum(p.batters_faced), 0) as pre_board_mlb_bf
            from resolved r
            left join mlb_pit p on p.mlbam_id = r.mlbam_id and p.gd <= r.as_of_dt
            group by 1, 2
         )
    select r.*,
           ml.* exclude (board_season, fg_minor_id),
           bw.* exclude (board_season, fg_minor_id),
           pw.* exclude (board_season, fg_minor_id),
           coalesce(pb.pre_board_mlb_pa, 0)  as pre_board_mlb_pa,
           coalesce(pp.pre_board_mlb_bf, 0)  as pre_board_mlb_bf
    from resolved r
    left join minor_line        ml on ml.board_season = r.board_season and ml.fg_minor_id = r.fg_minor_id
    left join bat_window        bw on bw.board_season = r.board_season and bw.fg_minor_id = r.fg_minor_id
    left join pit_window        pw on pw.board_season = r.board_season and pw.fg_minor_id = r.fg_minor_id
    left join pre_board_mlb     pb on pb.board_season = r.board_season and pb.fg_minor_id = r.fg_minor_id
    left join pre_board_mlb_pit pp on pp.board_season = r.board_season and pp.fg_minor_id = r.fg_minor_id
    """


def _derive(raw: pd.DataFrame, *, horizon: int, min_debut_pa: int, min_debut_bf: int) -> tuple[pd.DataFrame, dict]:
    """Board rows → the study frame: player type, as-of MiLB rates, the outcome, and the coverage
    report. Kept in pandas (not SQL) so the fast gate exercises it directly on fixtures."""
    df = raw.copy()
    report: dict = {"board_rows": int(len(df))}

    # ── player type: the position string when it is unambiguous, else the MiLB game logs ──────────
    # 🚨 This cascade exists because FanGraphs RELABELLED arms in 2021 (RHP/LHP → SP/SIRP/MIRP) and a
    # regex against the old vocabulary typed 666 relievers as BATTERS — see fv_translation.py. Never
    # trust a vendor position vocabulary alone; the game logs are the objective evidence.
    pg = pd.to_numeric(df.get("milb_pitcher_games"), errors="coerce").fillna(0.0)
    bg = pd.to_numeric(df.get("milb_batter_games"), errors="coerce").fillna(0.0)
    resolved = [resolve_player_type(pos, p, b) for pos, p, b in zip(df["position"], pg, bg)]
    df["player_type"] = [r[0] for r in resolved]
    df["player_type_source"] = [r[1] for r in resolved]
    report["player_type_source"] = pd.Series(df["player_type_source"]).value_counts().to_dict()
    report["unknown_position_tokens"] = sorted(unknown_position_tokens(df["position"]))
    if report["unknown_position_tokens"]:
        log.warning("[ALERT] position tokens in NEITHER vocabulary — FanGraphs may have relabelled "
                    "again; these rows fell through to the game logs: %s",
                    report["unknown_position_tokens"])

    # ── as-of MiLB rate line (the E7.3/E7.3p formula home — one place computes these) ─────────────
    bats = compute_rate_metrics_from_counts(df)
    pits = compute_pitcher_rate_metrics_from_counts(df)
    is_pit = df["player_type"].eq("pitcher").to_numpy()
    for col in ("minor_pa", "minor_k_pct", "minor_bb_pct"):
        df[col] = np.where(is_pit, pits[col], bats[col])
    for col in ("minor_woba", "minor_iso"):
        df[col] = np.where(is_pit, np.nan, bats[col])
    for col in ("minor_hr_rate", "minor_gb_pct", "minor_start_share"):
        df[col] = np.where(is_pit, pits[col], np.nan)

    # ── the null arm's pedigree proxies ──────────────────────────────────────────────────────────
    first_season = pd.to_numeric(df.get("first_milb_season"), errors="coerce")
    df["pro_experience_years"] = (pd.to_numeric(df["board_season"], errors="coerce")
                                  - first_season).clip(lower=0)
    fallback_level = (df["top_level_pre_board"] if "top_level_pre_board" in df.columns
                      else pd.Series(None, index=df.index, dtype=object))
    df["level"] = df["level"].fillna(fallback_level).fillna("(unknown)").astype(str)
    # the null arm's "already had a taste of the majors" control, in each type's own exposure unit.
    # ⚠️ Written to a NEW column: overwriting `pre_board_mlb_pa` in place would make this function
    # non-idempotent (a re-derive would read the pitcher value back through the batter branch), and a
    # derive step must never destroy its own raw input.
    pre_bf = (df["pre_board_mlb_bf"] if "pre_board_mlb_bf" in df.columns
              else pd.Series(0.0, index=df.index))
    df["pre_board_mlb_exposure"] = np.where(
        is_pit,
        pd.to_numeric(pre_bf, errors="coerce").fillna(0),
        pd.to_numeric(df["pre_board_mlb_pa"], errors="coerce").fillna(0))

    # ── outcome: zeros are REAL (never reached the majors), not nulls ────────────────────────────
    for c in ("mlb_pa", "mlb_hits", "mlb_home_runs", "mlb_walks", "mlb_strikeouts",
              "mlb_batters_faced", "mlb_hits_allowed", "mlb_walks_allowed",
              "mlb_strikeouts_pitched", "mlb_home_runs_allowed"):
        # an absent column (a cohort with no pitcher window at all) means ZERO events, not a scalar
        src = df[c] if c in df.columns else pd.Series(0.0, index=df.index)
        df[c] = pd.to_numeric(src, errors="coerce").fillna(0.0)

    # ── the identity key the CV purge groups on ──────────────────────────────────────────────────
    df["player_key"] = df["mlbam_id"].astype(str)

    # ── EXCLUSIONS (each counted, never silent) ──────────────────────────────────────────────────
    unresolved = df["mlbam_id"].isna()
    report["unresolved_no_mlbam"] = int(unresolved.sum())
    df = df[~unresolved].copy()

    # a duplicate (cohort, person) would double-count one realized outcome — keep the higher FV
    before = len(df)
    df = (df.sort_values(["board_season", "player_key", "fv"], ascending=[True, True, False])
            .drop_duplicates(["board_season", "player_key"], keep="first"))
    report["deduped_cohort_person_rows"] = int(before - len(df))

    df = attach_outcome(df, min_debut_pa=min_debut_pa, min_debut_bf=min_debut_bf)
    df["horizon_seasons"] = int(horizon)
    report["player_type_mismatch_by_season"] = _assert_player_type_sane(df)

    report.update({
        "study_rows": int(len(df)),
        "distinct_players": int(df["player_key"].nunique()),
        "board_seasons": sorted(int(s) for s in df["board_season"].dropna().unique()),
        "by_type": df["player_type"].value_counts().to_dict(),
        "debut_rate": {t: round(float(g["debuted"].mean()), 4)
                       for t, g in df.groupby("player_type")},
        "fv_populated": round(float(df["fv"].notna().mean()), 4),
        "minor_line_populated": round(float((pd.to_numeric(df["minor_pa"], errors="coerce")
                                             .fillna(0) > 0).mean()), 4),
        "rows_by_season": df["board_season"].value_counts().sort_index().to_dict(),
    })
    return df.reset_index(drop=True), report


class CohortValidationError(RuntimeError):
    """A cohort invariant failed — the study must not run on mislabelled rows.

    HARD stop, never a quiet mirage: mislabelled players are wrong BEFORE any model runs, so no CV
    split and no deflation gate can detect them (the 2026-07-27 vocabulary change typed 666 relievers
    as batters and flipped the headline verdict).
    """


MAX_TYPE_MISMATCH_RATE = 0.05


def _assert_player_type_sane(df: pd.DataFrame) -> dict:
    """⭐ THE TRIPWIRE THE FIRST RUN LACKED. Per board season, what share of rows typed BATTER have
    MiLB game logs saying they pitched more than they batted?

    After the cascade this should be ~0. A spike means the position vocabulary changed again (or the
    logs are joining wrong) — either way the labels are broken, and a broken label silently becomes a
    fake "never arrived" prospect in the fold. Raising here is the only place this class is catchable.
    """
    pg = pd.to_numeric(df.get("milb_pitcher_games"), errors="coerce").fillna(0.0)
    bg = pd.to_numeric(df.get("milb_batter_games"), errors="coerce").fillna(0.0)
    mismatch = (df["player_type"].eq("batter") & (pg > bg)).astype(float)
    by_season = mismatch.groupby(df["board_season"]).mean().round(4).to_dict()
    worst = max(by_season.values(), default=0.0)
    if worst > MAX_TYPE_MISMATCH_RATE:
        bad = {k: v for k, v in by_season.items() if v > MAX_TYPE_MISMATCH_RATE}
        raise CohortValidationError(
            f"PLAYER-TYPE MISMATCH: {bad} of rows typed 'batter' have pitcher-majority MiLB game "
            f"logs (ceiling {MAX_TYPE_MISMATCH_RATE:.0%}). FanGraphs most likely relabelled the "
            f"position vocabulary again — check `unknown_position_tokens` in the coverage report and "
            f"extend PITCHER_TOKENS/BATTER_TOKENS in fv_translation.py. Do NOT run the study on these "
            f"labels: a mislabelled arm is scored on the batter formula, records ~0 fantasy points, "
            f"and enters the fold as a fake 'never arrived' prospect."
        )
    return {int(k): float(v) for k, v in by_season.items()}


def default_season_ceiling(horizon: int, today=None) -> int:
    """The newest board season whose FULL outcome window has already closed.

    ⚠️ Without this cap the study silently includes cohorts whose window is still OPEN — a 2025 board
    with a 3-season window has one partial season of outcomes, so its prospects look like busts and
    the model learns from a truncated label. That is the "silently wrong, everything green" class, so
    the cap is the DEFAULT and the chosen value is logged, not left to the caller to remember.

    The last COMPLETE MLB season is the previous calendar year (the current season is in progress);
    the date comes from the canonical `current_game_date()` helper, never `date.today()` (INC-22 —
    the box runs UTC and a naive today rolls a day early in the evening).
    """
    if today is None:
        from betting_ml.utils.game_day import current_game_date
        today = current_game_date()
    return int(today.year) - 1 - int(horizon)


def rederive_cohort(path: str | Path, *, horizon: int = 3, min_debut_pa: int = 100,
                    min_debut_bf: int = 150) -> tuple[pd.DataFrame, dict]:
    """Re-run the pandas half on an ALREADY-ASSEMBLED cohort parquet — no S3, no Snowflake, seconds.

    The assembly emits BOTH the batter and the pitcher outcome windows for every prospect (and keeps
    every raw input column), so a fix to classification, the fantasy weights or the debut floors can
    be applied without paying for the multi-minute lakehouse read again. `_derive` is idempotent by
    construction — it only ever writes NEW columns or recomputes them from raw inputs.
    """
    raw = pd.read_parquet(path)
    return _derive(raw, horizon=horizon, min_debut_pa=min_debut_pa, min_debut_bf=min_debut_bf)


def build_cohort(*, horizon: int = 3, season_floor: int | None = None,
                 season_ceiling: int | None = None, min_debut_pa: int = 100,
                 min_debut_bf: int = 150, limit: int | None = None) -> tuple[pd.DataFrame, dict]:
    if season_ceiling is None:
        season_ceiling = default_season_ceiling(horizon)
        log.info("no --season-ceiling given → capping board seasons at %d, the newest cohort whose "
                 "%d-season outcome window has CLOSED (a later cohort would train on a truncated "
                 "label)", season_ceiling, horizon)
    conn = _connect()
    try:
        sql = _assembly_sql(horizon, season_floor, season_ceiling)
        if limit:
            sql += f"\n    limit {int(limit)}"
        log.info("assembling the E7.8 board cohort (horizon=%d seasons) ...", horizon)
        raw = conn.execute(sql).df()
    finally:
        conn.close()
    log.info("board rows read: %d", len(raw))
    return _derive(raw, horizon=horizon, min_debut_pa=min_debut_pa, min_debut_bf=min_debut_bf)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="E7.8 — assemble the FV→realized-MLB study cohort")
    p.add_argument("--out-dir", default=str(_PROJECT_ROOT
                   / "quant_sports_intel_models/baseball/edge_program/ablation_results/e7_8_artifacts"))
    p.add_argument("--horizon", type=int, default=3,
                   help="MLB seasons of outcome window after the board snapshot (default 3)")
    p.add_argument("--season-floor", type=int, default=None, help="earliest board season")
    p.add_argument("--season-ceiling", type=int, default=None,
                   help="latest board season to INCLUDE. DEFAULTS to the newest cohort whose outcome "
                        "window has fully CLOSED (last complete MLB season − horizon); override only "
                        "deliberately — a later cohort trains on a truncated label")
    p.add_argument("--min-debut-pa", type=int, default=100)
    p.add_argument("--min-debut-bf", type=int, default=150)
    p.add_argument("--limit", type=int, default=None, help="row cap for a cheap smoke")
    p.add_argument("--from-parquet", default=None,
                   help="re-derive from an already-assembled cohort parquet (no S3 read — seconds). "
                        "Use after a fix to classification / fantasy weights / debut floors; the "
                        "assembly keeps every raw input column and both outcome windows")
    p.add_argument("--s3", action="store_true",
                   help="also land the cohort at baseball/milb/derived/fv_translation_cohort (Delta)")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")

    if args.from_parquet:
        log.info("re-deriving from %s (no S3 read)", args.from_parquet)
        df, report = rederive_cohort(args.from_parquet, horizon=args.horizon,
                                     min_debut_pa=args.min_debut_pa, min_debut_bf=args.min_debut_bf)
    else:
        df, report = build_cohort(horizon=args.horizon, season_floor=args.season_floor,
                                  season_ceiling=args.season_ceiling, min_debut_pa=args.min_debut_pa,
                                  min_debut_bf=args.min_debut_bf, limit=args.limit)
    for k, v in report.items():
        log.info("coverage %-28s %s", k, v)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / "fv_translation_cohort.parquet"
    df.to_parquet(dest, index=False)
    log.info("wrote %s (%d rows)", dest, len(df))

    import json
    (out_dir / "fv_cohort_coverage.json").write_text(json.dumps(report, indent=2, default=str))

    if args.s3:
        _land_on_s3(df)
    return 0


def _land_on_s3(df: pd.DataFrame) -> bool:
    """Mirror the cohort to S3 Delta. **ALERT-loud-but-continue tier** (never HALT).

    The study's input is the LOCAL parquet written above; this Delta copy is a convenience mirror for
    E8.0 and for re-runs, off every serving path. A failure here after a successful multi-minute
    lakehouse assembly must not discard that work and force the whole read again — so it warns loudly
    to stderr and returns, per the repo's failure-handling contract (never a silent `pass`).

    ⚠️ `schema_mode="overwrite"` is REQUIRED, not decorative: `mode="overwrite"` replaces the DATA but
    keeps the existing table SCHEMA, so once the derive gained columns (`player_type_source`,
    `pre_board_mlb_exposure`) the write failed with `SchemaMismatchError: 73 vs 71`. The sibling
    INGESTS use `schema_mode="merge"` because their column sets only ever grow; this table is a
    FULL-REPLACE research artifact, so `overwrite` is the correct pairing — a future change that
    DROPS a column must not leave a stale one behind.
    """
    import sys as _sys

    try:
        from deltalake import write_deltalake
        from scripts.utils.delta_lake import storage_options

        write_deltalake(f"{MILB}/derived/fv_translation_cohort", df,
                        mode="overwrite", schema_mode="overwrite",
                        storage_options=storage_options())
        log.info("landed the cohort at %s/derived/fv_translation_cohort", MILB)
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[ALERT] E7.8 cohort S3 Delta mirror FAILED ({type(e).__name__}: {e}) — the LOCAL "
              f"parquet is written and the study can run on it unchanged. Re-mirror with "
              f"`--from-parquet <that parquet> --s3` once the cause is fixed.", file=_sys.stderr)
        log.warning("S3 Delta mirror failed (non-fatal): %s: %s", type(e).__name__, e)
        return False


if __name__ == "__main__":
    raise SystemExit(main())
