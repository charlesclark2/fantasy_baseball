"""build_pipeline_cohort.py — MLB Edge-E7.16: the POINT-IN-TIME comp cohort, on the MLB Pipeline
archive instead of the retained FanGraphs board.

E7.13's comp engine is fine; its FUEL was the problem. E7.8's `fv_translation_cohort` is built from
FanGraphs' **retained** past board — 5 board seasons (2018–2022), and a snapshot that may embed a
later revision (E7.8's stated caveat, which E7.13 then MEASURED: the retained `level` column is a
near-perfect one-sided bust tell). This module rebuilds the same cohort shape from
`baseball/milb/mlb_pipeline_rankings` (E7.11), which is:

  * **genuinely point-in-time** — MLB.com serves the archived ranking for `/prospects/<year>/…`, and
    the scouting report is selected by `mlb_pipeline._select_bio` as the report titled `season`, else
    the newest one NOT AFTER it (verified live on the whole archive: **zero** rows carry a bio from
    after their season);
  * **100% MLBAM-keyed**, so it joins the MiLB game logs and the MLB outcome marts with no name
    matching and no xref bridge loss;
  * **17 seasons deep** (2010–2026) rather than 5.

⚠️ WHAT IS *NOT* POINT-IN-TIME ON THAT SOURCE, AND HOW IT IS AVOIDED
--------------------------------------------------------------------
The page's `Person`/`Team` entities are LIVE records (mlb_pipeline.py §"current-state
contamination"): on the 2015 page Byron Buxton comes back age 32 and Kris Bryant comes back COL.
Every such field is suffixed `_current` in the table, and **this module reads none of them.** Age is
recomputed from the static `birth_date` against the board's own `as_of_date`; organisation is not a
comp feature at all; the level context comes from the MiLB game logs strictly before the board date,
exactly as E7.8 derived `top_level_pre_board`.

🎓 THE `fv` SLOT = MLB Pipeline's published **Overall** grade (`pipeline_grade_overall`), the same
20-80 scouting scale FanGraphs' FV is on, parsed from the season's own scouting report. Coverage is
97–99% of rows from 2014 on (0% before — the reports pre-date the graded era), which is one of the
three independent reasons the cohort floor is 2015. The E7.13 arm field already carries a matched
`comp_no_fv_k15` foil, so "is the comp carried by the grade" is measured on this pool too rather
than assumed to transfer.

📅 WHY THE SEASON WINDOW IS 2015–2022 — three independent bounds that happen to agree
-------------------------------------------------------------------------------------
  1. **THE LABEL.** The realized-MLB outcome comes from `mart_batter_rolling_stats` /
     `mart_pitcher_rolling_stats`, which are Statcast-era and start at **2015**. A 2014 board's
     3-season window opens in 2014 and would carry a truncated label — a real player scored as a
     partial bust. This is the BINDING constraint and it is a property of our warehouse, not of the
     Pipeline archive.
  2. **THE GRADE.** `pipeline_grade_overall` is absent before 2014.
  3. **LIST DEPTH.** MLB Pipeline's org lists were Top 10 in 2011, Top 20 in 2012–2014 and Top 30
     only from **2015** (`mlb_pipeline.ORG_LIST_DEPTH_BY_ERA`) — so a pre-2015 cohort is both
     smaller and differently selected, and "absent from the 2013 org list" is a materially weaker
     statement than the same absence in 2023.

The ceiling is the last board season whose full outcome window has CLOSED (`default_season_ceiling`
= last complete MLB season − horizon = 2022 today), for the reason E7.8 states: a still-open window
makes real players look like busts.

⚠️ **OPERATOR-RUN (cold ~3 min).** Measured 2026-08-01: **29 s** against a warm S3/DuckDB cache but
**2 min 59 s** cold on the operator's own laptop — the 4.6M-row MiLB `delta_scan` plus both MLB
rolling marts is the cost, and a session that has already read those parquets in the same process
tree does NOT see it. So this crosses the repo's >2-min hand-off rule and belongs to the operator,
exactly like E7.8's `build_fv_cohort.py`. A `--season-floor/--season-ceiling` single-season smoke
(~24 s) is the cheap in-session proof of the code path. Downstream is cheap: the two runners read the
cached parquet and take ~90 s / ~15 s with no IO at all.

🦠 THE 2020 SEASON IS A REAL DISCONTINUITY, NOT A BUG. MiLB was cancelled in 2020 (the game-log
table has no 2020 rows at all), so a 2021 board's as-of performance line is necessarily from 2019;
and MLB 2020 was 60 games, so every outcome window covering it is depressed. Both are what an
evaluator actually faced, both are shared by every arm, and both are reported rather than patched.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.scripts.fv_translation.build_fv_cohort import (  # noqa: E402
    _BAT_SUMS,
    _PIT_SUMS,
    CohortValidationError,
    _assert_player_type_sane,
    default_season_ceiling,
)
from betting_ml.scripts.fv_translation.fv_translation import (  # noqa: E402
    attach_outcome,
    resolve_player_type,
    unknown_position_tokens,
)
from betting_ml.scripts.milb_mle.milb_mle import (  # noqa: E402
    compute_pitcher_rate_metrics_from_counts,
    compute_rate_metrics_from_counts,
)

log = logging.getLogger("e7_16.cohort")

BUCKET = "s3://baseball-betting-ml-artifacts"
MILB = f"{BUCKET}/baseball/milb"
PIPELINE_TABLE = f"{MILB}/mlb_pipeline_rankings"

#: The earliest board season whose realized-MLB outcome window is fully covered by the Statcast-era
#: rolling marts. See the module docstring — this is the binding bound on the fold count.
LABEL_FLOOR_SEASON = 2015
#: The list depth published per era, used to normalize a rank across eras (a rank of 15 is mid-pack
#: on a Top-30 list and does not exist on a Top-10 one).
DEFAULT_HORIZON = 3


def _connect():
    """DuckDB over S3 with the Delta extension: the Pipeline archive, the MiLB logs, the MLB marts."""
    from scripts.utils.lakehouse_read import duck_connect, register_views

    conn = duck_connect()
    conn.execute("INSTALL delta; LOAD delta")
    register_views(conn, ["mart_batter_rolling_stats", "mart_pitcher_rolling_stats"])
    conn.execute(f"CREATE OR REPLACE VIEW milb_logs AS "
                 f"SELECT * FROM delta_scan('{MILB}/player_game_logs')")
    conn.execute(f"CREATE OR REPLACE VIEW pipeline_ranks AS "
                 f"SELECT * FROM delta_scan('{PIPELINE_TABLE}')")
    return conn


def _assembly_sql(horizon: int, season_floor: int, season_ceiling: int) -> str:
    """The one query. Deliberately parallel to `build_fv_cohort._assembly_sql` so the two cohorts are
    the SAME OBJECT with a different source board — that is what makes E7.16 a fuel swap.

    ⚠️ Injected as a string and executed against local DuckDB fixtures by the fast gate, for the same
    reason E7.8's is: a lakehouse assembly is otherwise CI-invisible and a broken one is discovered
    only after a multi-minute read.
    """
    bat_sum = ",\n               ".join(f"sum(coalesce(m.{c}, 0)) as {c}" for c in _BAT_SUMS)
    pit_sum = ",\n               ".join(f"sum(coalesce(m.{c}, 0)) as {c}" for c in _PIT_SUMS)
    return f"""
    with ranked as (
        select season, as_of_date, mlbam_id, list_type, rank, position, player_name,
               birth_date, eta, draft_year, pipeline_grade_overall, bio_season, org
        from pipeline_ranks
        where mlbam_id is not null
          and season >= {int(season_floor)} and season <= {int(season_ceiling)}
    ),
    -- a season may hold several snapshots; a point-in-time cohort takes the season's FIRST
    -- (preseason) snapshot, never the latest — the latest would be the freshest opinion, which is
    -- exactly the hindsight this cohort exists to remove.
    first_snap as (
        select season, min(as_of_date) as as_of_date from ranked group by 1
    ),
    snap as (
        select r.* from ranked r join first_snap f
          on f.season = r.season and f.as_of_date = r.as_of_date
    ),
    -- ONE ROW PER (season, player). A ranked player appears on BOTH the Top 100 and his club's org
    -- list; those are two views of one opinion, not two opinions, so they collapse to one row that
    -- carries both ranks. Duplicating him would double-count one realized outcome (E7.13 defect 2.3,
    -- one level up: there it was one PERSON across seasons, here it is one person within a season).
    board as (
        select season                                                      as board_season,
               min(as_of_date)                                             as as_of_date,
               min(as_of_date)::date                                       as as_of_dt,
               mlbam_id,
               min(case when list_type = 'top100' then rank end)           as overall_rank,
               min(case when list_type = 'org'    then rank end)           as org_rank,
               max(case when list_type = 'org'    then org end)            as org,
               -- the display/typing attributes: identical across a player's two list rows
               any_value(player_name)                                      as player_name,
               any_value(position)                                         as position,
               any_value(birth_date)                                       as birth_date,
               max(eta)                                                    as eta,
               max(draft_year)                                             as draft_year,
               max(pipeline_grade_overall)                                 as fv,
               max(bio_season)                                             as bio_season
        from snap group by season, mlbam_id
    ),
    milb as (
        select cast(l.player_id as varchar)  as mlbam_id,
               l.official_date::date         as gd,     -- INC-23: ISO VARCHAR → cast at the use-site
               l.season, l.level_name, l.is_batter, l.is_pitcher,
               {", ".join("l." + c for c in _BAT_SUMS + _PIT_SUMS)}
        from milb_logs l
        where l.game_type = 'R'
    ),
    minor_line as (
        -- the professional line STRICTLY BEFORE the board snapshot (the as-of guard)
        select b.board_season, b.mlbam_id,
               {bat_sum},
               {pit_sum},
               min(m.season)                                  as first_milb_season,
               max(m.season)                                  as last_milb_season,
               count(*)                                       as milb_games,
               sum(case when m.is_batter  then 1 else 0 end)  as milb_batter_games,
               sum(case when m.is_pitcher then 1 else 0 end)  as milb_pitcher_games,
               argmax(m.level_name, m.gd)                     as top_level_pre_board
        from board b
        join milb m on m.mlbam_id = b.mlbam_id and m.gd < b.as_of_dt
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
               coalesce(batters_faced, 0) as batters_faced,
               coalesce(hits_allowed, 0) as hits_allowed,
               coalesce(walks, 0) as walks, coalesce(strikeouts, 0) as strikeouts,
               coalesce(home_runs_allowed, 0) as home_runs_allowed
        from mart_pitcher_rolling_stats
    ),
    bat_window as (
        select b.board_season, b.mlbam_id,
               sum(x.pa_count) as mlb_pa, sum(x.hits) as mlb_hits,
               sum(x.home_runs) as mlb_home_runs, sum(x.walks) as mlb_walks,
               sum(x.strikeouts) as mlb_strikeouts
        from board b
        join mlb_bat x on x.mlbam_id = b.mlbam_id
                      and x.gd > b.as_of_dt
                      and x.game_year <= b.board_season + {int(horizon)}
        group by 1, 2
    ),
    pit_window as (
        select b.board_season, b.mlbam_id,
               sum(x.batters_faced) as mlb_batters_faced, sum(x.hits_allowed) as mlb_hits_allowed,
               sum(x.walks) as mlb_walks_allowed, sum(x.strikeouts) as mlb_strikeouts_pitched,
               sum(x.home_runs_allowed) as mlb_home_runs_allowed
        from board b
        join mlb_pit x on x.mlbam_id = b.mlbam_id
                      and x.gd > b.as_of_dt
                      and x.game_year <= b.board_season + {int(horizon)}
        group by 1, 2
    ),
    pre_board_mlb as (
        select b.board_season, b.mlbam_id, coalesce(sum(x.pa_count), 0) as pre_board_mlb_pa
        from board b
        left join mlb_bat x on x.mlbam_id = b.mlbam_id and x.gd <= b.as_of_dt
        group by 1, 2
    ),
    pre_board_mlb_pit as (
        select b.board_season, b.mlbam_id, coalesce(sum(x.batters_faced), 0) as pre_board_mlb_bf
        from board b
        left join mlb_pit x on x.mlbam_id = b.mlbam_id and x.gd <= b.as_of_dt
        group by 1, 2
    )
    select b.*,
           ml.* exclude (board_season, mlbam_id),
           bw.* exclude (board_season, mlbam_id),
           pw.* exclude (board_season, mlbam_id),
           coalesce(pb.pre_board_mlb_pa, 0) as pre_board_mlb_pa,
           coalesce(pp.pre_board_mlb_bf, 0) as pre_board_mlb_bf
    from board b
    left join minor_line        ml on ml.board_season = b.board_season and ml.mlbam_id = b.mlbam_id
    left join bat_window        bw on bw.board_season = b.board_season and bw.mlbam_id = b.mlbam_id
    left join pit_window        pw on pw.board_season = b.board_season and pw.mlbam_id = b.mlbam_id
    left join pre_board_mlb     pb on pb.board_season = b.board_season and pb.mlbam_id = b.mlbam_id
    left join pre_board_mlb_pit pp on pp.board_season = b.board_season and pp.mlbam_id = b.mlbam_id
    """


def as_of_age(birth_date: pd.Series, as_of: pd.Series) -> pd.Series:
    """Age in years AT THE BOARD DATE, from the static birth date.

    ⭐ This is the single most important line in the module. MLB Pipeline's archived page returns the
    player's **CURRENT** age (`age_current`: Byron Buxton comes back 32 on the 2015 page, when he was
    21), so reading that column would put ten years of hindsight into a point-in-time feature. The
    birth date is a static fact and the board date is known, so the as-of age is exactly computable
    and no contaminated column is ever read.
    """
    bd = pd.to_datetime(birth_date, errors="coerce", utc=False)
    ao = pd.to_datetime(as_of, errors="coerce", utc=False)
    try:                                       # tz-naive on both sides or the subtraction raises
        bd = bd.dt.tz_localize(None)
    except (TypeError, AttributeError):
        pass
    try:
        ao = ao.dt.tz_localize(None)
    except (TypeError, AttributeError):
        pass
    return (ao - bd).dt.days / 365.25


def _derive(raw: pd.DataFrame, *, horizon: int, min_debut_pa: int,
            min_debut_bf: int) -> tuple[pd.DataFrame, dict]:
    """Pipeline rows → the study frame. Kept in pandas (not SQL) so the fast gate exercises it."""
    df = raw.copy()
    report: dict = {"board_rows": int(len(df))}

    # ── player type: the position token when it is unambiguous, else the MiLB game logs ──────────
    pg = pd.to_numeric(df.get("milb_pitcher_games"), errors="coerce").fillna(0.0)
    bg = pd.to_numeric(df.get("milb_batter_games"), errors="coerce").fillna(0.0)
    resolved = [resolve_player_type(pos, p, b) for pos, p, b in zip(df["position"], pg, bg)]
    df["player_type"] = [r[0] for r in resolved]
    df["player_type_source"] = [r[1] for r in resolved]
    report["player_type_source"] = pd.Series(df["player_type_source"]).value_counts().to_dict()
    report["unknown_position_tokens"] = sorted(unknown_position_tokens(df["position"]))
    if report["unknown_position_tokens"]:
        log.warning("[ALERT] position tokens in NEITHER vocabulary — MLB Pipeline uses its own "
                    "position vocabulary and these rows fell through to the game logs: %s",
                    report["unknown_position_tokens"])

    # ── as-of MiLB rate line (the E7.3/E7.3p formula home — one place computes these) ────────────
    bats = compute_rate_metrics_from_counts(df)
    pits = compute_pitcher_rate_metrics_from_counts(df)
    is_pit = df["player_type"].eq("pitcher").to_numpy()
    for col in ("minor_pa", "minor_k_pct", "minor_bb_pct"):
        df[col] = np.where(is_pit, pits[col], bats[col])
    for col in ("minor_woba", "minor_iso"):
        df[col] = np.where(is_pit, np.nan, bats[col])
    for col in ("minor_hr_rate", "minor_gb_pct", "minor_start_share"):
        df[col] = np.where(is_pit, pits[col], np.nan)

    # ── the point-in-time null block ────────────────────────────────────────────────────────────
    df["age"] = as_of_age(df["birth_date"], df["as_of_date"])
    first_season = pd.to_numeric(df.get("first_milb_season"), errors="coerce")
    df["pro_experience_years"] = (pd.to_numeric(df["board_season"], errors="coerce")
                                  - first_season).clip(lower=0)
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
        src = df[c] if c in df.columns else pd.Series(0.0, index=df.index)
        df[c] = pd.to_numeric(src, errors="coerce").fillna(0.0)

    df["player_key"] = df["mlbam_id"].astype(str)
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
        "age_populated": round(float(df["age"].notna().mean()), 4),
        "minor_line_populated": round(float((pd.to_numeric(df["minor_pa"], errors="coerce")
                                             .fillna(0) > 0).mean()), 4),
        "rows_by_season": df["board_season"].value_counts().sort_index().to_dict(),
        "bio_never_from_the_future": bool(
            (pd.to_numeric(df.get("bio_season"), errors="coerce")
             <= pd.to_numeric(df["board_season"], errors="coerce")).fillna(True).all()),
    })
    if not report["bio_never_from_the_future"]:
        raise CohortValidationError(
            "a scouting report DATED AFTER its board season reached the cohort — "
            "`mlb_pipeline._select_bio`'s point-in-time rule has regressed. The whole premise of "
            "this cohort is that the grade is as-of; do not run the study on it."
        )
    return df.reset_index(drop=True), report


def build_cohort(*, horizon: int = DEFAULT_HORIZON, season_floor: int = LABEL_FLOOR_SEASON,
                 season_ceiling: int | None = None, min_debut_pa: int = 100,
                 min_debut_bf: int = 150) -> tuple[pd.DataFrame, dict]:
    if season_ceiling is None:
        season_ceiling = default_season_ceiling(horizon)
        log.info("no --season-ceiling given → capping board seasons at %d (the newest cohort whose "
                 "%d-season outcome window has CLOSED)", season_ceiling, horizon)
    conn = _connect()
    try:
        sql = _assembly_sql(horizon, season_floor, season_ceiling)
        log.info("assembling the E7.16 Pipeline cohort (seasons %d–%d, horizon=%d) ...",
                 season_floor, season_ceiling, horizon)
        raw = conn.execute(sql).df()
    finally:
        conn.close()
    log.info("board rows read: %d", len(raw))
    return _derive(raw, horizon=horizon, min_debut_pa=min_debut_pa, min_debut_bf=min_debut_bf)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="E7.16 — assemble the point-in-time Pipeline comp cohort")
    p.add_argument("--out-dir", default=str(
        _PROJECT_ROOT / "quant_sports_intel_models/baseball/edge_program/ablation_results"
        / "e7_16_artifacts"))
    p.add_argument("--horizon", type=int, default=DEFAULT_HORIZON)
    p.add_argument("--season-floor", type=int, default=LABEL_FLOOR_SEASON,
                   help="earliest board season (default = the Statcast-era outcome-mart floor)")
    p.add_argument("--season-ceiling", type=int, default=None)
    p.add_argument("--min-debut-pa", type=int, default=100)
    p.add_argument("--min-debut-bf", type=int, default=150)
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")

    df, report = build_cohort(horizon=args.horizon, season_floor=args.season_floor,
                              season_ceiling=args.season_ceiling,
                              min_debut_pa=args.min_debut_pa, min_debut_bf=args.min_debut_bf)
    for k, v in report.items():
        log.info("coverage %-32s %s", k, v)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / "pipeline_comp_cohort.parquet"
    df.to_parquet(dest, index=False)
    log.info("wrote %s (%d rows)", dest, len(df))
    (out_dir / "pipeline_cohort_coverage.json").write_text(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
