"""build_graduated_pairs_pitchers.py — MLB Edge-E7.3p: assemble the graduated-PITCHER matrix ONCE.

The pitcher sibling of build_graduated_pairs.py (E7.3). Reads the E7.1 MiLB game logs (pitching
lines) + the E7.2 AAA-Statcast pitcher summaries + the realized MLB pitcher line — all SF-FREE,
DuckDB over the S3 lakehouse — and writes ONE `mle_graduated_pairs_pitchers` parquet the bake-off
reads (the §0.5 "assemble once → parquet; every candidate/fold reads the cache" discipline).
Nothing here touches Snowflake.

⚠️ OPERATOR-RUN (>1 min, S3 I/O). Per the repo's >1-minute + runtime-gate rules this is NOT a
session inline run — it reads the 4.6M-row MiLB substrate, the MLB pitcher mart, AND a
batted-ball aggregate over `stg_batter_pitches` (the GB label). A `--limit` smoke first is wise.

WHAT A ROW IS
-------------
One row per (player_id, level) — a pitcher's pre-debut MiLB line AT A LEVEL, joined to their
realized early-career MLB line. Per-level rows share the player's MLB label (the stated
correlated-observation limit; per-level rows are what let the model estimate LEVEL factors).

  * FEATURE side (E7.1/E7.2, SF-free):
      - `pit_*` box counts summed over the pitcher's regular-season MiLB games at that level,
        STRICTLY BEFORE the MLB debut date (the as-of leakage guard). Rates
        (K%/BB%/HR-rate/GB-out-share/start-share) computed by
        `milb_mle.compute_pitcher_rate_metrics_from_counts` (one formula home). `minor_pa` = TBF.
      - `age` — TBF-weighted mean age at that level pre-debut; `league` — the modal MiLB league.
      - `sc_*` — the E7.2 AAA-Statcast PITCHER summary add (velo/spin/whiff/xwOBA-against etc.,
        TBF-weighted over pre-debut AAA games); NULL for non-AAA levels / pre-2022 (a
        coverage-conditioned feature, honest-null where absent). `sc_xwoba_against` doubles as the
        `xwoba_against` metric's minor feature (no box-line equivalent exists).
  * LABEL side (realized MLB line, `mart_pitcher_rolling_stats` per-game actuals):
      - `mlb_k_pct/bb_pct/hr_rate/xwoba_against` + `mlb_tbf` — TBF-weighted sums over the
        pitcher's FIRST `label_window` MLB seasons; `has_mlb_label` iff `mlb_tbf ≥ min_mlb_tbf`.
        `debut_cohort` = the first MLB season (the CV fold unit).
      - `mlb_gb_pct` — Statcast GB/BIP from `stg_batter_pitches` over the same window. ⚠️ a
        CROSS-DEFINITION label (the MiLB feature is the ground-OUT share GO/(GO+AO) — all the box
        line offers); the MLE regression learns the rescale, and the asymmetry is documented.
  * PROSPECTS: a pitcher with a usable MiLB line but NO MLB debut → `is_prospect=true`, no label,
    the MLE's real deliverable — the E8.0 board's pitcher column (emitted from the latest map).
    Their MiLB line aggregates ALL their games (no debut cutoff exists).

Output: `<out>/mle_graduated_pairs_pitchers.parquet`
        (+ `--s3` lands `baseball/milb/derived/mle_graduated_pairs_pitchers`, Delta).
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.scripts.milb_mle.milb_mle import (  # noqa: E402
    LEVEL_ORDER,
    compute_pitcher_rate_metrics_from_counts,
)

log = logging.getLogger("e7_3p.pairs")

BUCKET = "s3://baseball-betting-ml-artifacts"
MILB = f"{BUCKET}/baseball/milb"
MLB_LEVELS = "', '".join(LEVEL_ORDER)

# The summed pitching box columns the rate formulas need (mirrors
# milb_mle.compute_pitcher_rate_metrics_from_counts).
_PIT_SUMS = [
    "pit_batters_faced", "pit_strike_outs", "pit_walks", "pit_home_runs",
    "pit_ground_outs", "pit_air_outs", "pit_games_played", "pit_games_started", "pit_outs",
]


def _connect():
    """DuckDB with the S3 credential chain + the Delta extension (the MiLB tables are Delta; the MLB
    marts route per the registry). Reuses the canonical prediction-path connector."""
    from scripts.utils.lakehouse_read import duck_connect, register_views

    conn = duck_connect()
    try:
        conn.execute("INSTALL delta; LOAD delta")
    except Exception as e:  # noqa: BLE001
        log.warning("delta extension load failed (%s) — MiLB delta_scan may fail", e)
    # the realized-MLB label sources (per-game pitcher line + the batted-ball GB substrate)
    register_views(conn, ["mart_pitcher_rolling_stats", "stg_batter_pitches"])
    # the MiLB feature tables (Delta at a separate prefix — register explicitly)
    conn.execute(f"CREATE OR REPLACE VIEW milb_logs AS SELECT * FROM delta_scan('{MILB}/player_game_logs')")
    conn.execute(f"CREATE OR REPLACE VIEW milb_statcast AS SELECT * FROM delta_scan('{MILB}/statcast_aaa')")
    return conn


def _assembly_sql(label_window: int, min_mlb_tbf: int, season_floor: int | None) -> str:
    pit_sum_select = ",\n        ".join(f"sum(coalesce({c}, 0)) as {c}" for c in _PIT_SUMS)
    season_filter = f"and season >= {season_floor}" if season_floor else ""
    return f"""
    with mlb_debut as (
        -- first MLB appearance per pitcher (min game_date) + debut season (the CV fold unit)
        select pitcher_id::varchar as player_id,
               min(game_date::date) as debut_date,
               min(game_year)       as debut_season
        from mart_pitcher_rolling_stats
        group by pitcher_id
    ),
    mlb_label as (
        -- TBF-weighted realized line over the FIRST `label_window` MLB seasons, from the mart's
        -- single-game actuals (exact sums — no season-to-date snapshot needed on the pitcher side)
        select m.pitcher_id::varchar as player_id,
               sum(m.batters_faced)                                        as mlb_tbf,
               sum(m.strikeouts)        / nullif(sum(m.batters_faced), 0)  as mlb_k_pct,
               sum(m.walks)             / nullif(sum(m.batters_faced), 0)  as mlb_bb_pct,
               sum(m.home_runs_allowed) / nullif(sum(m.batters_faced), 0)  as mlb_hr_rate,
               sum(case when m.xwoba_against is not null
                        then m.xwoba_against * m.batters_faced end)
                 / nullif(sum(case when m.xwoba_against is not null
                                   then m.batters_faced end), 0)           as mlb_xwoba_against
        from mart_pitcher_rolling_stats m
        join mlb_debut d on d.player_id = m.pitcher_id::varchar
        where m.game_year between d.debut_season and d.debut_season + {label_window - 1}
        group by m.pitcher_id
    ),
    mlb_gb as (
        -- Statcast GB/BIP over the same first-seasons window (the GB label; cross-definition vs the
        -- MiLB ground-OUT share — documented, the regression learns the rescale)
        select p.pitcher_id::varchar as player_id,
               sum(case when p.batted_ball_type = 'ground_ball' then 1 else 0 end)::double
                 / nullif(count(*), 0)                                     as mlb_gb_pct,
               count(*)                                                    as mlb_bip
        from stg_batter_pitches p
        join mlb_debut d on d.player_id = p.pitcher_id::varchar
        where p.batted_ball_type is not null
          and p.game_year between d.debut_season and d.debut_season + {label_window - 1}
        group by p.pitcher_id
    ),
    milb_pit as (
        -- regular-season MiLB pitching games, STRICTLY BEFORE the MLB debut (prospects: keep all)
        select l.player_id::varchar as player_id, l.player_name, l.level_name as level,
               l.league_name as league, l.age, l.official_date::date as official_date,
               l.season,
               {", ".join("l." + c for c in _PIT_SUMS)}
        from milb_logs l
        left join mlb_debut d on d.player_id = l.player_id::varchar
        where l.is_pitcher = true
          and l.game_type = 'R'
          and l.level_name in ('{MLB_LEVELS}')
          {season_filter}
          and (d.debut_date is null or l.official_date::date < d.debut_date)
    ),
    milb_level as (
        -- one row per (player_id, level): summed pitching line + TBF-weighted age + modal league
        select player_id, level,
               any_value(player_name) as player_name,
               mode(league) as league,
               sum(coalesce(age, 0) * coalesce(pit_batters_faced, 0))
                   / nullif(sum(coalesce(pit_batters_faced, 0)), 0) as age,
               -- E7.12-S2 (survivorship) — see the batter builder for why: a never-promoted player has
               -- no `debut_cohort`, so without an as-of season there is no leakage-safe in-fold
               -- promotion model and no way to see right-censoring ("not promoted YET" vs "not promoted").
               min(season) as first_minor_season,
               max(season) as last_minor_season,
               {pit_sum_select}
        from milb_pit
        group by player_id, level
    ),
    statcast_pit as (
        -- TBF-weighted AAA-Statcast PITCHER summary per player, pre-debut (prospects: all AAA games)
        select sc.player_id::varchar as player_id,
               sum(sc.xwoba                    * coalesce(sc.plate_appearances, 0)) / nullif(sum(sc.plate_appearances), 0) as sc_xwoba_against,
               sum(sc.swing_miss_percent       * coalesce(sc.plate_appearances, 0)) / nullif(sum(sc.plate_appearances), 0) as sc_swing_miss_percent,
               sum(sc.avg_pitch_velocity_mph   * coalesce(sc.plate_appearances, 0)) / nullif(sum(sc.plate_appearances), 0) as sc_avg_pitch_velocity_mph,
               sum(sc.avg_spin_rate_rpm        * coalesce(sc.plate_appearances, 0)) / nullif(sum(sc.plate_appearances), 0) as sc_avg_spin_rate_rpm,
               sum(sc.avg_release_extension_ft * coalesce(sc.plate_appearances, 0)) / nullif(sum(sc.plate_appearances), 0) as sc_avg_release_extension_ft,
               sum(sc.hardhit_percent          * coalesce(sc.plate_appearances, 0)) / nullif(sum(sc.plate_appearances), 0) as sc_hardhit_percent_against
        from milb_statcast sc
        left join mlb_debut d on d.player_id = sc.player_id::varchar
        where sc.player_type = 'pitcher'
          and (d.debut_date is null or sc.game_date::date < d.debut_date)
        group by sc.player_id
    )
    select m.*,
           d.debut_season                              as debut_cohort,
           (d.player_id is null)                       as is_prospect,
           lab.mlb_tbf                                 as mlb_pa,
           lab.mlb_k_pct, lab.mlb_bb_pct, lab.mlb_hr_rate, lab.mlb_xwoba_against,
           gb.mlb_gb_pct, gb.mlb_bip,
           (lab.mlb_tbf is not null and lab.mlb_tbf >= {min_mlb_tbf}) as has_mlb_label,
           sc.sc_xwoba_against, sc.sc_swing_miss_percent, sc.sc_avg_pitch_velocity_mph,
           sc.sc_avg_spin_rate_rpm, sc.sc_avg_release_extension_ft, sc.sc_hardhit_percent_against
    from milb_level m
    left join mlb_debut d   on d.player_id = m.player_id
    left join mlb_label lab on lab.player_id = m.player_id
    left join mlb_gb gb     on gb.player_id = m.player_id
    left join statcast_pit sc on sc.player_id = m.player_id and m.level = 'Triple-A'
    """


def build_pairs(label_window: int = 2, min_mlb_tbf: int = 150,
                season_floor: int | None = None, limit: int | None = None) -> pd.DataFrame:
    conn = _connect()
    try:
        sql = _assembly_sql(label_window, min_mlb_tbf, season_floor)
        if limit:
            sql += f"\n    limit {limit}"
        log.info("assembling graduated PITCHER pairs (label_window=%d, min_mlb_tbf=%d) ...",
                 label_window, min_mlb_tbf)
        df = conn.execute(sql).df()
    finally:
        conn.close()
    # rate metrics from the summed pitching counts — the single formula home (milb_mle)
    df = compute_pitcher_rate_metrics_from_counts(df)
    log.info("assembled %d (pitcher, level) rows: %d graduated w/ label, %d prospects",
             len(df), int(df["has_mlb_label"].fillna(False).sum()),
             int(df["is_prospect"].fillna(False).sum()))
    return df


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="E7.3p — assemble the MiLB→MLB graduated-PITCHER pairs")
    p.add_argument("--out-dir", default=str(_PROJECT_ROOT
                   / "quant_sports_intel_models/baseball/edge_program/ablation_results/e7_3p_artifacts"))
    p.add_argument("--label-window", type=int, default=2,
                   help="number of first MLB seasons to TBF-weight into the realized label (default 2)")
    p.add_argument("--min-mlb-tbf", type=int, default=150,
                   help="min realized MLB batters faced over the label window (default 150, ~8 starts)")
    p.add_argument("--season-floor", type=int, default=None,
                   help="only MiLB seasons >= this (e.g. 2015 to bound to the MLB-Statcast label era)")
    p.add_argument("--limit", type=int, default=None, help="row cap for a cheap smoke")
    p.add_argument("--s3", action="store_true",
                   help="also land the pairs at baseball/milb/derived/mle_graduated_pairs_pitchers (Delta)")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")

    df = build_pairs(args.label_window, args.min_mlb_tbf, args.season_floor, args.limit)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / "mle_graduated_pairs_pitchers.parquet"
    df.to_parquet(dest, index=False)
    log.info("wrote %s (%d rows)", dest, len(df))

    if args.s3:
        from scripts.utils.delta_lake import storage_options
        from deltalake import write_deltalake

        write_deltalake(f"{MILB}/derived/mle_graduated_pairs_pitchers", df, mode="overwrite",
                        storage_options=storage_options())
        log.info("landed pairs at %s/derived/mle_graduated_pairs_pitchers", MILB)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
