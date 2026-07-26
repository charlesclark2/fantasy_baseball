"""build_graduated_pairs.py — MLB Edge-E7.3: assemble the graduated-player training matrix ONCE.

Reads the E7.1 MiLB game logs + the E7.2 AAA-Statcast summaries + the realized MLB batter line — all
SF-FREE, DuckDB over the S3 lakehouse — and writes ONE `mle_graduated_pairs` parquet the bake-off reads
(the §0.5 "assemble once → parquet; every candidate/fold reads the cache" discipline). Nothing here
touches Snowflake.

⚠️ OPERATOR-RUN (>1 min, S3 I/O). Per the repo's >1-minute + runtime-gate rules this is NOT a session
inline run — it reads the full 4.6M-row MiLB substrate + the MLB rolling-stats mart. A `--limit`/
`--seasons` smoke is provided for a cheap first pass.

WHAT A ROW IS
-------------
One row per (player_id, level) — a player's pre-debut MiLB line AT A LEVEL, joined to their realized
early-career MLB line. A player's AAA and AA lines are two rows sharing the same MLB label (the
per-level rows are what let the model estimate LEVEL factors; the shared label is a stated limitation).

  * FEATURE side (E7.1/E7.2, SF-free):
      - `minor_woba/k_pct/bb_pct/iso` + `minor_pa` — from the `bat_*` box counts summed over the
        player's regular-season MiLB games at that level, STRICTLY BEFORE the MLB debut date (the as-of
        leakage guard). Rates computed by `milb_mle.compute_rate_metrics_from_counts` (one formula home).
      - `age` — PA-weighted mean age at that level pre-debut; `league` — the modal MiLB league.
      - `sc_*` — the E7.2 AAA-Statcast summary add (AAA rows only, PA-weighted over pre-debut AAA games);
        NULL for non-AAA levels / pre-2022 (a coverage-conditioned feature, honest-null where absent).
  * LABEL side (realized MLB line):
      - `mlb_woba/k_pct/bb_pct/iso` + `mlb_pa` — PA-weighted over the player's FIRST `label_window` MLB
        seasons, from `mart_batter_rolling_stats` season-to-date `_std` columns; `has_mlb_label` iff
        `mlb_pa ≥ min_mlb_pa`. `debut_cohort` = the first MLB season (the CV fold unit).
  * PROSPECTS: a player with a usable MiLB line but NO MLB debut → `is_prospect=true`, no label, the MLE's
    real deliverable (emitted from the latest map). Their MiLB line aggregates ALL their games (no debut
    cutoff exists).

Output: `<out>/mle_graduated_pairs.parquet` (+ `--s3` lands `baseball/milb/derived/mle_graduated_pairs`).
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
    compute_rate_metrics_from_counts,
)

log = logging.getLogger("e7_3.pairs")

BUCKET = "s3://baseball-betting-ml-artifacts"
MILB = f"{BUCKET}/baseball/milb"
MLB_LEVELS = "', '".join(LEVEL_ORDER)

# The summed box columns the wOBA/rate formulas need (mirrors milb_mle.compute_rate_metrics_from_counts).
_BAT_SUMS = [
    "bat_plate_appearances", "bat_at_bats", "bat_hits", "bat_doubles", "bat_triples",
    "bat_home_runs", "bat_walks", "bat_intentional_walks", "bat_hit_by_pitch", "bat_sac_flies",
    "bat_strike_outs", "bat_total_bases",
]


def _connect():
    """DuckDB with the S3 credential chain + the Delta extension (the MiLB tables are Delta; the MLB
    marts glob parquet). Reuses the canonical prediction-path connector, then force-loads delta (the
    MiLB read needs it regardless of the W1 cutover mode)."""
    from scripts.utils.lakehouse_read import duck_connect, register_views

    conn = duck_connect()
    try:
        conn.execute("INSTALL delta; LOAD delta")
    except Exception as e:  # noqa: BLE001
        log.warning("delta extension load failed (%s) — MiLB delta_scan may fail", e)
    # the realized-MLB label mart (globs parquet or delta_scan per the registry)
    register_views(conn, ["mart_batter_rolling_stats"])
    # the MiLB feature tables (Delta at a separate prefix — register explicitly)
    conn.execute(f"CREATE OR REPLACE VIEW milb_logs AS SELECT * FROM delta_scan('{MILB}/player_game_logs')")
    conn.execute(f"CREATE OR REPLACE VIEW milb_statcast AS SELECT * FROM delta_scan('{MILB}/statcast_aaa')")
    return conn


def _assembly_sql(label_window: int, min_mlb_pa: int, season_floor: int | None) -> str:
    bat_sum_select = ",\n        ".join(f"sum(coalesce({c}, 0)) as {c}" for c in _BAT_SUMS)
    season_filter = f"and season >= {season_floor}" if season_floor else ""
    return f"""
    with mlb_debut as (
        -- first MLB appearance per batter (min game_date) + debut season (the CV fold unit)
        select batter_id::varchar as player_id,
               min(game_date::date) as debut_date,
               min(game_year)       as debut_season
        from mart_batter_rolling_stats
        group by batter_id
    ),
    mlb_season_line as (
        -- the season-to-date line at the LAST game of each MLB season (the realized full-season line)
        select batter_id::varchar as player_id, game_year,
               pa_count_std, woba_std, k_pct_std, bb_pct_std, iso_std
        from (
            select *, row_number() over (
                       partition by batter_id, game_year order by game_date::date desc) as rn
            from mart_batter_rolling_stats
        ) t
        where rn = 1
    ),
    mlb_label as (
        -- PA-weight the realized line over the FIRST `label_window` MLB seasons
        select s.player_id,
               sum(s.pa_count_std)                                as mlb_pa,
               sum(s.woba_std   * s.pa_count_std) / nullif(sum(s.pa_count_std), 0) as mlb_woba,
               sum(s.k_pct_std  * s.pa_count_std) / nullif(sum(s.pa_count_std), 0) as mlb_k_pct,
               sum(s.bb_pct_std * s.pa_count_std) / nullif(sum(s.pa_count_std), 0) as mlb_bb_pct,
               sum(s.iso_std    * s.pa_count_std) / nullif(sum(s.pa_count_std), 0) as mlb_iso
        from mlb_season_line s
        join mlb_debut d on d.player_id = s.player_id
        where s.game_year between d.debut_season and d.debut_season + {label_window - 1}
        group by s.player_id
    ),
    milb_bat as (
        -- regular-season MiLB batter games, STRICTLY BEFORE the MLB debut (prospects: keep all games)
        select l.player_id::varchar as player_id, l.player_name, l.level_name as level,
               l.league_name as league, l.age, l.official_date::date as official_date,
               {", ".join("l." + c for c in _BAT_SUMS)}
        from milb_logs l
        left join mlb_debut d on d.player_id = l.player_id::varchar
        where l.is_batter = true
          and l.game_type = 'R'
          and l.level_name in ('{MLB_LEVELS}')
          {season_filter}
          and (d.debut_date is null or l.official_date::date < d.debut_date)
    ),
    milb_level as (
        -- one row per (player_id, level): summed box line + PA-weighted age + modal league
        select player_id, level,
               any_value(player_name) as player_name,
               mode(league) as league,
               sum(coalesce(age, 0) * coalesce(bat_plate_appearances, 0))
                   / nullif(sum(coalesce(bat_plate_appearances, 0)), 0) as age,
               {bat_sum_select}
        from milb_bat
        group by player_id, level
    ),
    statcast_aaa as (
        -- PA-weighted AAA-Statcast summary per player, pre-debut (prospects: all AAA games)
        select sc.player_id::varchar as player_id,
               sum(sc.woba                    * coalesce(sc.plate_appearances, 0)) / nullif(sum(sc.plate_appearances), 0) as sc_xwoba,
               sum(sc.barrels_per_pa_percent  * coalesce(sc.plate_appearances, 0)) / nullif(sum(sc.plate_appearances), 0) as sc_barrels_per_pa_percent,
               sum(sc.hardhit_percent         * coalesce(sc.plate_appearances, 0)) / nullif(sum(sc.plate_appearances), 0) as sc_hardhit_percent,
               sum(sc.avg_exit_velocity_mph   * coalesce(sc.plate_appearances, 0)) / nullif(sum(sc.plate_appearances), 0) as sc_avg_exit_velocity_mph,
               sum(sc.avg_bat_speed_mph       * coalesce(sc.plate_appearances, 0)) / nullif(sum(sc.plate_appearances), 0) as sc_avg_bat_speed_mph
        from milb_statcast sc
        left join mlb_debut d on d.player_id = sc.player_id::varchar
        where sc.player_type = 'batter'
          and (d.debut_date is null or sc.game_date::date < d.debut_date)
        group by sc.player_id
    )
    select m.*,
           d.debut_season                              as debut_cohort,
           (d.player_id is null)                       as is_prospect,
           lab.mlb_pa, lab.mlb_woba, lab.mlb_k_pct, lab.mlb_bb_pct, lab.mlb_iso,
           (lab.mlb_pa is not null and lab.mlb_pa >= {min_mlb_pa}) as has_mlb_label,
           sc.sc_xwoba, sc.sc_barrels_per_pa_percent, sc.sc_hardhit_percent,
           sc.sc_avg_exit_velocity_mph, sc.sc_avg_bat_speed_mph
    from milb_level m
    left join mlb_debut d   on d.player_id = m.player_id
    left join mlb_label lab on lab.player_id = m.player_id
    left join statcast_aaa sc on sc.player_id = m.player_id and m.level = 'Triple-A'
    """


def build_pairs(label_window: int = 2, min_mlb_pa: int = 150,
                season_floor: int | None = None, limit: int | None = None) -> pd.DataFrame:
    conn = _connect()
    try:
        sql = _assembly_sql(label_window, min_mlb_pa, season_floor)
        if limit:
            sql += f"\n    limit {limit}"
        log.info("assembling graduated pairs (label_window=%d, min_mlb_pa=%d) ...", label_window, min_mlb_pa)
        df = conn.execute(sql).df()
    finally:
        conn.close()
    # rate metrics from the summed box counts — the single formula home (milb_mle)
    df = compute_rate_metrics_from_counts(df)
    log.info("assembled %d (player, level) rows: %d graduated w/ label, %d prospects",
             len(df), int(df["has_mlb_label"].fillna(False).sum()),
             int(df["is_prospect"].fillna(False).sum()))
    return df


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="E7.3 — assemble the MiLB→MLB graduated-player pairs")
    p.add_argument("--out-dir", default=str(_PROJECT_ROOT
                   / "quant_sports_intel_models/baseball/edge_program/ablation_results/e7_3_artifacts"))
    p.add_argument("--label-window", type=int, default=2,
                   help="number of first MLB seasons to PA-weight into the realized label (default 2)")
    p.add_argument("--min-mlb-pa", type=int, default=150,
                   help="min realized MLB PA over the label window for a labelled graduate (default 150)")
    p.add_argument("--season-floor", type=int, default=None,
                   help="only MiLB seasons >= this (e.g. 2015 to bound to the MLB-Statcast label era)")
    p.add_argument("--limit", type=int, default=None, help="row cap for a cheap smoke")
    p.add_argument("--s3", action="store_true",
                   help="also land the pairs at baseball/milb/derived/mle_graduated_pairs (Delta)")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")

    df = build_pairs(args.label_window, args.min_mlb_pa, args.season_floor, args.limit)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / "mle_graduated_pairs.parquet"
    df.to_parquet(dest, index=False)
    log.info("wrote %s (%d rows)", dest, len(df))

    if args.s3:
        from scripts.utils.delta_lake import storage_options
        from deltalake import write_deltalake

        write_deltalake(f"{MILB}/derived/mle_graduated_pairs", df, mode="overwrite",
                        storage_options=storage_options())
        log.info("landed pairs at %s/derived/mle_graduated_pairs", MILB)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
