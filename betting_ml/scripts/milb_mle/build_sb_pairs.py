"""build_sb_pairs.py — E8.3: assemble the MiLB→MLB STOLEN-BASE translation cohort ONCE.

Reads the E7.1 MiLB game logs + the E8.3 MLB season-hitting lines — all SF-FREE, DuckDB over the S3
lakehouse — and writes ONE `sb_translation_pairs` parquet the bake-off reads (the §0.5 "assemble once →
parquet; every candidate/fold/arm reads the cache" discipline). Nothing here touches Snowflake.

⚠️ OPERATOR-RUN CANDIDATE (S3 I/O over the 4.6M-row MiLB substrate). A `--limit`/`--season-floor` smoke
is provided; the full assembly is ~1 minute on the laptop.

WHAT A ROW IS
-------------
One row per (player_id, level) — a player's pre-debut MiLB RUNNING line at a level, joined to his
realized early-career MLB running line. Mirrors `build_graduated_pairs` exactly (same grain, same
debut source, same as-of leakage guard) so the SB cohort is the SAME POPULATION the board already
serves — a different cohort would make an SB weight incommensurable with the k_pct/bb_pct/iso weights
it would sit beside in `MLE_METRIC_WEIGHTS`.

THE OPPORTUNITY DENOMINATOR (the crux — a raw SB COUNT is the wrong target)
--------------------------------------------------------------------------
A raw SB total confounds ABILITY with OPPORTUNITY (how often he reaches first, how often the team
runs) and with PLAYING TIME. The board ranks players, not playing time, and every other MLE metric is
a per-PA rate — a count would be incommensurable in the percentile blend. So the modelled quantity is
a RATE over stolen-base opportunities:

    sbo = singles + walks + hit_by_pitch = (H − 2B − 3B − HR) + BB + HBP

the standard Bill James stolen-base-opportunity proxy for "times reached first base". Then:

    sb_rate   = SB / SBO                 — the primary ABILITY read
    att_rate  = (SB + CS) / SBO          — how often he GOES (propensity)
    succ_rate = SB / (SB + CS)           — how often he MAKES IT (efficiency)

⭐ WHICH ONE DO LEAGUES ACTUALLY SCORE? Standard roto 5×5 scores GROSS SB, so a 30/10 runner and a
30/2 runner are IDENTICAL in the operator's format — `sb_rate` is the category-relevant target, and
`succ_rate` earns its place as a DRIVER of future attempt volume (a poor success rate gets the red
light) rather than as a scored category. Net-SB and points leagues do price CS, which is why the
decomposition is carried as a pre-registered target FORM rather than dropped.

THE ERA PROBLEM (pre-registered covariate, and it is large)
-----------------------------------------------------------
Measured on this substrate, the running environment moved MASSIVELY, and — the part that matters —
**the two ladders broke at DIFFERENT times**:

    MiLB SB per 1k SBO:  59 (2018) → 75 (2021) → 85 (2022) → 90 (2023) → 110 (2026)
    MLB  SB per 1k SBO:  56 (2018) → 52 (2021) → 58 (2022) → 80 (2023) →  84 (2024)

MiLB's rule changes (bigger bases / pickoff limits / the pitch clock, phased 2021-22) landed a full
season or two BEFORE MLB's 2023 adoption. So a player whose minor line is 2019 and whose MLB label is
2023 crosses TWO different regime shifts in opposite proportions, and a translation fit blind to that
mis-maps every pre-2023 comp. Both sides therefore carry an opportunity-weighted LEAGUE BASELINE
(`minor_env_sb_rate` / `mlb_env_sb_rate`) and a baseline-relative rate (`*_sb_rate_rel`), so an
era-corrected arm can be run beside its raw twin as a MATCHED FOIL (NF-D10) rather than asserted.

Output: `<out>/sb_translation_pairs.parquet`.
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

from betting_ml.scripts.milb_mle.milb_mle import LEVEL_ORDER  # noqa: E402

log = logging.getLogger("e8_3.pairs")

BUCKET = "s3://baseball-betting-ml-artifacts"
MILB = f"{BUCKET}/baseball/milb"
MLB = f"{BUCKET}/baseball/mlb"
MLB_LEVELS = "', '".join(LEVEL_ORDER)

# Pre-registered eligibility floors. `min_minor_pa` mirrors E7.3's 150 EXACTLY so the SB cohort is the
# population the board already publishes a line for. The SBO floors are the rate-specific addition: a
# rate over 3 opportunities is not a thin estimate, it is noise with a denominator.
DEFAULT_MIN_MINOR_PA = 150
DEFAULT_MIN_MINOR_SBO = 50
DEFAULT_MIN_MLB_PA = 150
DEFAULT_MIN_MLB_SBO = 50

# ⚠️ LEFT-CENSORING: `mart_batter_rolling_stats` — the debut source E7.3 and this module share —
# begins in 2015 (verified live: min(game_year)=2015). So EVERY player who actually debuted before
# 2015 is stamped `debut_cohort = 2015`, and the "first 2 MLB seasons" label is then his age-30
# seasons rather than his early career. Measured: the 2015 cohort holds 1,165 of 2,557 labelled rows
# and 60% of them carry a minor line that ends ≥3 seasons before the stamped debut — a gap a true
# debutant does not have (the 2016+ cohorts' median gap is 1 season).
#
# This matters for SB specifically, more than for the rates E7.3 translates: speed is the most
# age-sensitive tool on the diamond, so pairing a 22-year-old's minor line with an age-30 MLB label
# systematically understates the translation. The rows are FLAGGED rather than silently dropped, and
# the runner scores the drop as a pre-registered robustness arm — an artifact this large must be shown
# to not be driving the answer, not assumed away.
DEBUT_MART_FLOOR_SEASON = 2015
CENSORED_MIN_GAP_SEASONS = 2


def _connect():
    """DuckDB with the S3 credential chain + the Delta extension (MiLB/MLB tables are Delta; the MLB
    debut mart globs parquet). Mirrors `build_graduated_pairs._connect`."""
    from scripts.utils.lakehouse_read import duck_connect, register_views

    conn = duck_connect()
    try:
        conn.execute("INSTALL delta; LOAD delta")
    except Exception as e:  # noqa: BLE001
        log.warning("delta extension load failed (%s) — delta_scan may fail", e)
    # the debut source — the SAME table E7.3 keys its cohorts off, so folds align
    register_views(conn, ["mart_batter_rolling_stats"])
    conn.execute(f"CREATE OR REPLACE VIEW milb_logs AS SELECT * FROM delta_scan('{MILB}/player_game_logs')")
    conn.execute(f"CREATE OR REPLACE VIEW mlb_hitting AS SELECT * FROM delta_scan('{MLB}/season_hitting')")
    return conn


# `sbo` = times reached first base = singles + walks + HBP. Written once, here, so the minor and
# major sides can never drift apart in definition (the two use different column prefixes).
_MINOR_SBO = ("(coalesce(bat_hits,0) - coalesce(bat_doubles,0) - coalesce(bat_triples,0) "
              "- coalesce(bat_home_runs,0) + coalesce(bat_walks,0) + coalesce(bat_hit_by_pitch,0))")
_MLB_SBO = ("(coalesce(hits,0) - coalesce(doubles,0) - coalesce(triples,0) "
            "- coalesce(home_runs,0) + coalesce(walks,0) + coalesce(hit_by_pitch,0))")


def _assembly_sql(label_window: int, season_floor: int | None) -> str:
    season_filter = f"and l.season >= {season_floor}" if season_floor else ""
    return f"""
    with mlb_debut as (
        select batter_id::varchar as player_id,
               min(game_date::date) as debut_date,
               min(game_year)       as debut_season
        from mart_batter_rolling_stats
        group by batter_id
    ),
    -- ── ERA BASELINES ────────────────────────────────────────────────────────────────────────
    -- The league-wide running environment, per (season, level) on the minor side and per season on
    -- the major side. These are the pre-registered era covariate: the SAME player line means a
    -- different thing in 2019 than in 2024, and the two ladders moved at different times.
    milb_env as (
        select season, level_name as level,
               sum(coalesce(bat_stolen_bases,0))::double
                   / nullif(sum({_MINOR_SBO}), 0) as env_sb_rate,
               sum(coalesce(bat_stolen_bases,0) + coalesce(bat_caught_stealing,0))::double
                   / nullif(sum({_MINOR_SBO}), 0) as env_att_rate
        from milb_logs
        where is_batter = true and game_type = 'R' and level_name in ('{MLB_LEVELS}')
        group by 1, 2
    ),
    mlb_env as (
        select season,
               sum(coalesce(stolen_bases,0))::double
                   / nullif(sum({_MLB_SBO}), 0) as env_sb_rate,
               sum(coalesce(stolen_bases,0) + coalesce(caught_stealing,0))::double
                   / nullif(sum({_MLB_SBO}), 0) as env_att_rate
        from mlb_hitting
        group by 1
    ),
    -- ── MINOR SIDE (feature) ─────────────────────────────────────────────────────────────────
    -- regular-season MiLB batter games, STRICTLY BEFORE the MLB debut (prospects: keep all games)
    milb_bat as (
        select l.player_id::varchar as player_id, l.player_name, l.level_name as level,
               l.league_name as league, l.age, l.season,
               coalesce(l.bat_plate_appearances,0) as pa,
               coalesce(l.bat_stolen_bases,0)      as sb,
               coalesce(l.bat_caught_stealing,0)   as cs,
               {_MINOR_SBO}                        as sbo,
               e.env_sb_rate                       as env_sb_rate,
               e.env_att_rate                      as env_att_rate
        from milb_logs l
        left join mlb_debut d on d.player_id = l.player_id::varchar
        left join milb_env  e on e.season = l.season and e.level = l.level_name
        where l.is_batter = true
          and l.game_type = 'R'
          and l.level_name in ('{MLB_LEVELS}')
          {season_filter}
          and (d.debut_date is null or l.official_date::date < d.debut_date)
    ),
    milb_level as (
        select player_id, level,
               any_value(player_name) as player_name,
               mode(league)           as league,
               sum(pa)                as minor_pa,
               sum(sb)                as minor_sb,
               sum(cs)                as minor_cs,
               sum(sbo)               as minor_sbo,
               sum(coalesce(age,0) * pa) / nullif(sum(pa), 0)      as age,
               min(season) as first_minor_season,
               max(season) as last_minor_season,
               -- OPPORTUNITY-weighted era baseline: weight each season by the opportunities the
               -- player actually accumulated in it, so a player who spent one cup-of-coffee month in
               -- a new regime is not credited with that regime's whole environment.
               sum(env_sb_rate  * sbo) / nullif(sum(sbo), 0)       as minor_env_sb_rate,
               sum(env_att_rate * sbo) / nullif(sum(sbo), 0)       as minor_env_att_rate
        from milb_bat
        group by player_id, level
    ),
    -- ── MAJOR SIDE (label) ───────────────────────────────────────────────────────────────────
    -- the realized running line over the FIRST `label_window` MLB seasons
    mlb_label as (
        select h.player_id::varchar as player_id,
               sum(coalesce(h.plate_appearances,0)) as mlb_pa,
               sum(coalesce(h.stolen_bases,0))      as mlb_sb,
               sum(coalesce(h.caught_stealing,0))   as mlb_cs,
               sum({_MLB_SBO})                      as mlb_sbo,
               sum(e.env_sb_rate  * {_MLB_SBO}) / nullif(sum({_MLB_SBO}), 0) as mlb_env_sb_rate,
               sum(e.env_att_rate * {_MLB_SBO}) / nullif(sum({_MLB_SBO}), 0) as mlb_env_att_rate,
               min(h.season) as label_first_season,
               max(h.season) as label_last_season
        from mlb_hitting h
        join mlb_debut d on d.player_id = h.player_id::varchar
        left join mlb_env e on e.season = h.season
        where h.season between d.debut_season and d.debut_season + {label_window - 1}
        group by h.player_id
    )
    select m.*,
           d.debut_season                        as debut_cohort,
           (d.player_id is null)                 as is_prospect,
           lab.mlb_pa, lab.mlb_sb, lab.mlb_cs, lab.mlb_sbo,
           lab.mlb_env_sb_rate, lab.mlb_env_att_rate,
           lab.label_first_season, lab.label_last_season
    from milb_level m
    left join mlb_debut d   on d.player_id = m.player_id
    left join mlb_label lab on lab.player_id = m.player_id
    """


def compute_sb_rates(df: pd.DataFrame) -> pd.DataFrame:
    """Derive every rate from the summed counts — ONE formula home for both sides.

    ⚠️ A rate is NULL, never 0, when its denominator is 0. `SB/0` is UNKNOWN ("we never saw him reach
    first"), and coercing it to 0.0 would inject a fabricated "cannot run" into a zero-heavy target —
    the exact direction that flatters an all-zero degenerate. The eligibility floors then exclude
    those rows from training rather than the imputation hiding them.
    """
    out = df.copy()
    for side in ("minor", "mlb"):
        sb = pd.to_numeric(out.get(f"{side}_sb"), errors="coerce")
        cs = pd.to_numeric(out.get(f"{side}_cs"), errors="coerce")
        sbo = pd.to_numeric(out.get(f"{side}_sbo"), errors="coerce")
        att = sb + cs
        sbo_ok = sbo.where(sbo > 0)
        att_ok = att.where(att > 0)
        out[f"{side}_sb_rate"] = sb / sbo_ok
        out[f"{side}_att_rate"] = att / sbo_ok
        out[f"{side}_succ_rate"] = sb / att_ok
        # era-relative: the player's rate as a MULTIPLE of the environment he ran in. 1.0 = league
        # average for his seasons/levels. This is the era-corrected twin of the raw rate.
        env = pd.to_numeric(out.get(f"{side}_env_sb_rate"), errors="coerce")
        env_a = pd.to_numeric(out.get(f"{side}_env_att_rate"), errors="coerce")
        out[f"{side}_sb_rate_rel"] = out[f"{side}_sb_rate"] / env.where(env > 0)
        out[f"{side}_att_rate_rel"] = out[f"{side}_att_rate"] / env_a.where(env_a > 0)
        # per-PA rate — the coarser opportunity proxy, carried as a pre-registered target FORM so
        # "does the SBO refinement earn its keep?" is a measured comparison, not an assumption.
        pa = pd.to_numeric(out.get(f"{side}_pa"), errors="coerce")
        out[f"{side}_sb_per_pa"] = sb / pa.where(pa > 0)
    return out


def apply_eligibility(df: pd.DataFrame, *, min_minor_pa: int = DEFAULT_MIN_MINOR_PA,
                      min_minor_sbo: int = DEFAULT_MIN_MINOR_SBO,
                      min_mlb_pa: int = DEFAULT_MIN_MLB_PA,
                      min_mlb_sbo: int = DEFAULT_MIN_MLB_SBO) -> pd.DataFrame:
    """Attach `has_minor_line` / `has_mlb_label` / `has_target` / `is_prospect`.

    Mirrors `milb_mle.build_target`'s contract: an active prospect or a thin line carries
    `has_target = False` — UNKNOWN, never 0.
    """
    out = df.copy()
    minor_pa = pd.to_numeric(out.get("minor_pa"), errors="coerce").fillna(0.0)
    minor_sbo = pd.to_numeric(out.get("minor_sbo"), errors="coerce").fillna(0.0)
    out["has_minor_line"] = (
        pd.to_numeric(out.get("minor_sb_rate"), errors="coerce").notna()
        & (minor_pa >= min_minor_pa) & (minor_sbo >= min_minor_sbo)
    )
    mlb_pa = pd.to_numeric(out.get("mlb_pa"), errors="coerce").fillna(0.0)
    mlb_sbo = pd.to_numeric(out.get("mlb_sbo"), errors="coerce").fillna(0.0)
    out["has_mlb_label"] = (
        pd.to_numeric(out.get("mlb_sb_rate"), errors="coerce").notna()
        & (mlb_pa >= min_mlb_pa) & (mlb_sbo >= min_mlb_sbo)
    )
    out["has_target"] = out["has_minor_line"] & out["has_mlb_label"]
    out["is_prospect"] = out["has_minor_line"] & ~out["has_mlb_label"]
    out["debut_censored"] = _debut_censored(out)
    return out


def _debut_censored(df: pd.DataFrame) -> pd.Series:
    """True where the stamped debut is a left-censoring artifact of the 2015 mart floor.

    A row is censored iff it sits in the floor cohort AND its minor line ends ≥2 seasons earlier —
    a gap a genuine debutant does not have. Restricting to the floor cohort matters: a LATER cohort
    with a long gap is a real slow-developer / injury case, not a censoring artifact, and sweeping
    those in would quietly redefine the population the robustness arm is testing.
    """
    cohort = pd.to_numeric(df.get("debut_cohort"), errors="coerce")
    last_minor = pd.to_numeric(df.get("last_minor_season"), errors="coerce")
    gap = cohort - last_minor
    return ((cohort == DEBUT_MART_FLOOR_SEASON)
            & (gap >= CENSORED_MIN_GAP_SEASONS)).fillna(False)


def build_pairs(label_window: int = 2, season_floor: int | None = None,
                limit: int | None = None, **floors) -> pd.DataFrame:
    conn = _connect()
    try:
        sql = _assembly_sql(label_window, season_floor)
        if limit:
            sql += f"\n    limit {limit}"
        log.info("assembling SB translation pairs (label_window=%d) ...", label_window)
        df = conn.execute(sql).df()
    finally:
        conn.close()
    df = apply_eligibility(compute_sb_rates(df), **floors)
    log.info("assembled %d (player, level) rows: %d labelled, %d prospects",
             len(df), int(df["has_target"].fillna(False).sum()),
             int(df["is_prospect"].fillna(False).sum()))
    return df


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="E8.3 — assemble the MiLB→MLB stolen-base pairs")
    p.add_argument("--out-dir", default=str(_PROJECT_ROOT
                   / "quant_sports_intel_models/baseball/edge_program/ablation_results/e8_3_artifacts"))
    p.add_argument("--label-window", type=int, default=2,
                   help="number of first MLB seasons aggregated into the realized label (default 2)")
    p.add_argument("--season-floor", type=int, default=None,
                   help="only MiLB seasons >= this (e.g. 2010)")
    p.add_argument("--min-minor-pa", type=int, default=DEFAULT_MIN_MINOR_PA)
    p.add_argument("--min-minor-sbo", type=int, default=DEFAULT_MIN_MINOR_SBO)
    p.add_argument("--min-mlb-pa", type=int, default=DEFAULT_MIN_MLB_PA)
    p.add_argument("--min-mlb-sbo", type=int, default=DEFAULT_MIN_MLB_SBO)
    p.add_argument("--limit", type=int, default=None, help="row cap for a cheap smoke")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")

    df = build_pairs(args.label_window, args.season_floor, args.limit,
                     min_minor_pa=args.min_minor_pa, min_minor_sbo=args.min_minor_sbo,
                     min_mlb_pa=args.min_mlb_pa, min_mlb_sbo=args.min_mlb_sbo)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / "sb_translation_pairs.parquet"
    df.to_parquet(dest, index=False)
    log.info("wrote %s (%d rows)", dest, len(df))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
