"""xfp_source.py — NF-D7 EXPECTED FANTASY POINTS (xFP) + TD REGRESSION.

The fantasy field's most-cited projection stabilizers, built from nflverse PLAY-BY-PLAY opportunity:

  • EXPECTED TOUCHDOWNS (xTD) — TDs are the biggest AND noisiest fantasy driver. A player's realized
    TD count in a season is a noisy draw around the TDs his OPPORTUNITY implies. We assign every carry
    and every target a TD probability from its FIELD POSITION (`yardline_100` bucket — goal-line carries
    convert ~50%, end-zone/red-zone targets ~29–44%, midfield ~0.5–2%), computed empirically league-
    wide, and sum to an EXPECTED-TD count. Blending last year's ACTUAL TD rate toward this expected rate
    ("TD regression") is a strictly better forward predictor of next-year TDs than carrying the lucky/
    unlucky actual forward — VALIDATED on our data (rush: forward ρ 0.618 xTD vs 0.578 actual; rec: the
    50/50 blend beats either alone). This is the primary, non-double-counting lever.

  • EXPECTED RECEIVING (xREC / xRecYds) — expected catches = Σ catch-probability (`cp`) over targets;
    expected receiving yards = Σ cp·(air_yards + expected-YAC). Opportunity-based receiving efficiency,
    orthogonal to the realized catch/yard outcome. Delivered as FEATURES for NF1.1/NF1.2 (the recency-
    weighted production line already carries most receiving-efficiency signal — the NF-D2 slice-2 NGS
    lesson — so these are candidate features, not a heuristic blend into MVP-1).

Everything here is LEAKAGE-SAFE by construction: the per-player opportunity and the league TD-
conversion rates are read from the BASE-season recency window (≤ base_season) only; nothing peeks at
the projected season. The heavy S3 play-by-play read is CACHED per season to parquet (assemble-once
cost hygiene) so the ablation / feature assembly reads the cache, never S3 per config.

Pure helpers (`league_td_rates`, `expected_td_from_opportunity`, `regress_td_rate`, `window_weight`)
take DataFrames/arrays in and out with NO IO, so the construct is unit-tested offline against the fast
gate; the DuckDB/S3 read + caching live in `load_opportunity` / `load_xfp_features`.
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger("nfl.fantasy.xfp")

_ART = Path(__file__).resolve().parent / "artifacts"
_CACHE = _ART / "xfp_cache"

# Field-position buckets for TD-conversion rates (distance to the end zone, `yardline_100`). The rate
# gradient is enormous — a goal-line carry and a midfield carry are not the same "opportunity" — so
# TDs must be modelled per bucket, not as a flat per-touch rate.
_BUCKETS = ("gl", "rz5", "rz10", "rz20", "ff")
_YL_BUCKET = """case
    when yardline_100 is null then 'ff'
    when yardline_100 <= 2 then 'gl'
    when yardline_100 <= 5 then 'rz5'
    when yardline_100 <= 10 then 'rz10'
    when yardline_100 <= 20 then 'rz20'
    else 'ff' end"""

# Per-player bucketed carry / target count columns (opportunity) and bucketed TD columns.
_RUSH_OPP = {b: f"c_{b}" for b in _BUCKETS}
_RUSH_TD = {b: f"ctd_{b}" for b in _BUCKETS}
_REC_OPP = {b: f"t_{b}" for b in _BUCKETS}
_REC_TD = {b: f"ttd_{b}" for b in _BUCKETS}

# The recency window + decay match `run_season_projection.load_base_season` so the xTD per-game rate is
# on the SAME footing as the realized `rush_td_pg` / `rec_td_pg` it regresses (base season + 2 prior).
RECENCY_DECAY = 0.6
WINDOW_YEARS = 3

# Standard PPR scoring weights for the xFP-per-game construct (mirror season_projection.SCORING_STD).
_PTS_RUSH_YD, _PTS_REC_YD, _PTS_TD, _PTS_REC = 0.1, 0.1, 6.0, 1.0

# The play-by-play S3 Delta relation (raw nflverse pbp). Overridable for an offline/local Delta tree.
PBP_RELATION = "delta_scan('s3://credence-sports-lakehouse/nfl/raw/pbp')"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# S3 play-by-play → per-(season, player_id) opportunity aggregate (cached per season)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _ensure_s3(con) -> None:
    """Make a plain DuckDB connection able to `delta_scan` the S3 lake (the dbt profile does this on
    connect, but a raw `duckdb.connect(file)` does not). Idempotent + best-effort — a connection that
    already has the extension/secret (or has no network) just proceeds."""
    for stmt in ("install delta", "load delta", "install httpfs", "load httpfs",
                 "create secret (type s3, provider credential_chain, region 'us-east-2')"):
        try:
            con.sql(stmt)
        except Exception:  # noqa: BLE001 — extension already loaded / secret already exists
            pass


def _bucket_agg(prefix_opp: dict, prefix_td: dict, td_expr: str) -> str:
    """SQL fragment: bucketed opportunity counts + bucketed TD sums for one role."""
    parts = []
    for b in _BUCKETS:
        parts.append(f"count(*) filter (where yl = '{b}') as {prefix_opp[b]}")
        parts.append(f"sum({td_expr}) filter (where yl = '{b}') as {prefix_td[b]}")
    return ",\n        ".join(parts)


_OPPORTUNITY_SQL = f"""
with plays as (
    select season,
        rusher_player_id, receiver_player_id,
        {_YL_BUCKET} as yl,
        coalesce(rush_touchdown, 0) as rush_td,
        coalesce(pass_touchdown, 0) as pass_td,
        air_yards, cp, xyac_mean_yardage
    from {{pbp}}
    where season between {{lo}} and {{hi}} and season_type = 'REG' and play_type in ('run', 'pass')
),
rush as (
    select season, rusher_player_id as player_id,
        count(*) as carries, sum(rush_td) as rush_td_actual,
        {_bucket_agg(_RUSH_OPP, _RUSH_TD, 'rush_td')}
    from plays where rusher_player_id is not null group by 1, 2
),
rec as (
    select season, receiver_player_id as player_id,
        count(*) as targets, sum(pass_td) as rec_td_actual,
        {_bucket_agg(_REC_OPP, _REC_TD, 'pass_td')},
        sum(cp) as sum_cp,
        sum(coalesce(cp, 0.0) * (coalesce(air_yards, 0.0) + coalesce(xyac_mean_yardage, 0.0))) as sum_xrecyds
    from plays where receiver_player_id is not null group by 1, 2
)
select
    coalesce(rush.season, rec.season)       as season,
    coalesce(rush.player_id, rec.player_id) as player_id,
    rush.* exclude (season, player_id),
    rec.*  exclude (season, player_id)
from rush full join rec using (season, player_id)
"""


def load_opportunity(con, seasons: list[int], *, pbp_relation: str = PBP_RELATION,
                     cache_dir: Path = _CACHE, use_cache: bool = True,
                     refresh: bool = False) -> pd.DataFrame:
    """Per-(season, player_id) bucketed carry/target opportunity + bucketed TDs + receiving-efficiency
    sums, read from the S3 play-by-play. Cached per season to parquet (the heavy S3 read runs once);
    `refresh` forces a re-read. Returns one row per (season, player_id) — the raw material the leakage-
    safe window assembly (`load_xfp_features`) turns into per-game xFP components. Zero-fills the
    opportunity/TD columns (a rush-only or rec-only player has NULLs on the other role's side)."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    frames, to_read = [], []
    for y in seasons:
        cache = cache_dir / f"opp_season={y}.parquet"
        if use_cache and not refresh and cache.exists():
            frames.append(pd.read_parquet(cache))
        else:
            to_read.append(y)
    if to_read:
        _ensure_s3(con)
        for y in to_read:
            df = con.sql(_OPPORTUNITY_SQL.format(pbp=pbp_relation, lo=y, hi=y)).df()
            df.to_parquet(cache_dir / f"opp_season={y}.parquet", index=False)
            log.info("xFP opportunity cache written: season=%d (%d players)", y, len(df))
            frames.append(df)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    fill = ["carries", "rush_td_actual", "targets", "rec_td_actual", "sum_cp", "sum_xrecyds",
            *_RUSH_OPP.values(), *_RUSH_TD.values(), *_REC_OPP.values(), *_REC_TD.values()]
    for c in fill:
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0.0)
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Pure — league TD-conversion rates + expected-TD from opportunity
# ══════════════════════════════════════════════════════════════════════════════════════════════
def league_td_rates(pool: pd.DataFrame) -> tuple[dict, dict]:
    """League P(TD | field-position bucket) for RUSH and REC, from a pool of per-player-season rows.

    rate[bucket] = Σ (bucketed TDs) / Σ (bucketed opportunities) over EVERY player in the pool — the
    exact empirical per-bucket conversion rate (goal-line rush ≈ 0.50, end-zone/RZ target ≈ 0.29–0.44,
    midfield ≈ 0.005–0.02). The caller passes a LEAKAGE-SAFE pool (only seasons ≤ base) so the rate
    never sees the projected year. A bucket with no opportunity in the pool → 0.0. These rates are
    extremely stable league constants, which is precisely why an opportunity-weighted expected-TD
    de-noises the individual player's realized count."""
    rush, rec = {}, {}
    for b in _BUCKETS:
        c_opp = float(pd.to_numeric(pool.get(_RUSH_OPP[b]), errors="coerce").fillna(0.0).sum())
        c_td = float(pd.to_numeric(pool.get(_RUSH_TD[b]), errors="coerce").fillna(0.0).sum())
        rush[b] = c_td / c_opp if c_opp > 0 else 0.0
        t_opp = float(pd.to_numeric(pool.get(_REC_OPP[b]), errors="coerce").fillna(0.0).sum())
        t_td = float(pd.to_numeric(pool.get(_REC_TD[b]), errors="coerce").fillna(0.0).sum())
        rec[b] = t_td / t_opp if t_opp > 0 else 0.0
    return rush, rec


def expected_td_from_opportunity(df: pd.DataFrame, rush_rates: dict, rec_rates: dict) -> pd.DataFrame:
    """Per-row EXPECTED rush & rec TDs = Σ_bucket (bucketed opportunity × league bucket rate). PURE.

    Returns a copy of `df` with `xrush_td` and `xrec_td` (season totals of expected TDs) added. A player
    with elite goal-line volume but unlucky finishing gets a HIGH xTD and a LOW actual — the exact
    'regress up' case; the inverse is 'regress down'."""
    out = df.copy()
    xr = np.zeros(len(out))
    xc = np.zeros(len(out))
    for b in _BUCKETS:
        xr += pd.to_numeric(out.get(_RUSH_OPP[b]), errors="coerce").fillna(0.0).to_numpy() * rush_rates.get(b, 0.0)
        xc += pd.to_numeric(out.get(_REC_OPP[b]), errors="coerce").fillna(0.0).to_numpy() * rec_rates.get(b, 0.0)
    out["xrush_td"] = xr
    out["xrec_td"] = xc
    return out


def regress_td_rate(actual_pg: np.ndarray, expected_pg: np.ndarray, blend: float) -> np.ndarray:
    """TD REGRESSION (pure): blend a realized per-game TD rate toward its opportunity-based expected
    per-game rate. `blend`∈[0,1] = weight on the expected rate (0 = pure actual = the ablation baseline;
    the shipped value is set by the NF-D7 ablation verdict). Where the expected rate is unknown (NaN —
    a player with no cached opportunity), the actual is kept unchanged (no-op)."""
    a = np.asarray(actual_pg, dtype=float)
    x = np.asarray(expected_pg, dtype=float)
    out = np.where(np.isfinite(x), (1.0 - blend) * a + blend * x, a)
    return np.where(np.isfinite(out), out, a)


def window_weight(season_ages: np.ndarray, games: np.ndarray) -> np.ndarray:
    """Recency×games weight (RECENCY_DECAY^age × games) matching `load_base_season` — a season one year
    older counts 0.6×, and an injury-shortened season contributes less. PURE."""
    return (RECENCY_DECAY ** np.asarray(season_ages, dtype=float)) * np.asarray(games, dtype=float)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Assembly — per-player leakage-safe window-weighted xFP FEATURES (the entry point)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _games_per_season(con, lo: int, hi: int, schema: str) -> pd.DataFrame:
    """Realized games per (season, player_id) from the marts — the SAME denominator
    `load_base_season` uses (`played_flag and not is_bye`), so xTD/g aligns with `rush_td_pg`."""
    return con.sql(f"""
        select season, player_id, count_if(played_flag and not is_bye) as games
        from {schema}.fct_player_week where season between {lo} and {hi} and week > 0
        group by 1, 2 having games > 0
    """).df()


def load_xfp_features(con, base_season: int, schema: str = "main_nfl_marts", *,
                      window: int = WINDOW_YEARS, pbp_relation: str = PBP_RELATION,
                      cache_dir: Path = _CACHE, use_cache: bool = True) -> pd.DataFrame:
    """The leakage-safe, per-player xFP FEATURE row for projecting `base_season + 1`.

    Reads the base-season recency window (base−window+1 … base) opportunity from the cache, fits the
    league TD-conversion rates ON THAT WINDOW (≤ base — leakage-safe), computes each player's expected
    TDs, then window-weights every quantity to a PER-GAME rate on the same recency×games weights as the
    projection's production line. Returns one row per `player_id` with:

      • `xrush_td_pg`, `xrec_td_pg`   — expected TD per game (the TD-regression targets)
      • `rush_td_pg_actual`, `rec_td_pg_actual` — realized TD per game (for the luck ratio / diagnostics)
      • `xrec_pg`, `xrec_yds_pg`      — expected catches / receiving yards per game (NF1 features)
      • `xfp_pg`                      — an opportunity-based expected fantasy points per game (a compact
                                        feature: expected receiving + expected TD, actual rush/pass yards
                                        carried since yardage is far more stable than TDs)
      • `td_luck_ratio`              — (actual − expected) rush+rec TD per game (>0 = lucky; the
                                        regression signal). NaN-safe.

    Every column is a base-season-window quantity; nothing reads the projected season. A player absent
    from the play-by-play window (no cached opportunity) simply does not appear (the caller's LEFT JOIN
    then leaves the TD-regression a no-op for them)."""
    lo = base_season - (window - 1)
    seasons = list(range(lo, base_season + 1))
    opp = load_opportunity(con, seasons, pbp_relation=pbp_relation, cache_dir=cache_dir,
                           use_cache=use_cache)
    if opp.empty:
        return pd.DataFrame(columns=["player_id"])
    opp = opp[opp["season"].between(lo, base_season)].copy()

    # leakage-safe league rates fit on the whole window pool, then per-player expected TDs
    rush_rates, rec_rates = league_td_rates(opp)
    opp = expected_td_from_opportunity(opp, rush_rates, rec_rates)

    # per-season games (marts) → per-game rates on the SAME denominator as the production line
    games = _games_per_season(con, lo, base_season, schema)
    opp = opp.merge(games, on=["season", "player_id"], how="left")
    opp = opp[pd.to_numeric(opp["games"], errors="coerce").fillna(0.0) > 0].copy()
    if opp.empty:
        return pd.DataFrame(columns=["player_id"])
    g = opp["games"].to_numpy(dtype=float)
    opp["_w"] = window_weight(base_season - opp["season"].to_numpy(), g)
    # season totals → per-game
    for tot, pg in (("xrush_td", "xrush_td_pg"), ("xrec_td", "xrec_td_pg"),
                    ("rush_td_actual", "rush_td_pg_actual"), ("rec_td_actual", "rec_td_pg_actual"),
                    ("sum_cp", "xrec_pg"), ("sum_xrecyds", "xrec_yds_pg")):
        opp[pg] = pd.to_numeric(opp[tot], errors="coerce").fillna(0.0).to_numpy() / g

    pg_cols = ["xrush_td_pg", "xrec_td_pg", "rush_td_pg_actual", "rec_td_pg_actual",
               "xrec_pg", "xrec_yds_pg"]

    def _blend(gr: pd.DataFrame) -> pd.Series:
        w = gr["_w"].to_numpy()
        wsum = w.sum() or 1.0
        return pd.Series({c: float((gr[c].to_numpy() * w).sum() / wsum) for c in pg_cols})

    feat = opp.groupby("player_id").apply(_blend, include_groups=False).reset_index()

    # compact opportunity-based expected fantasy points per game (receiving + TD legs; the yardage/
    # passing legs are production-stable so a feature that swaps them for "expected" would just re-encode
    # the recency line — the NF-D2 slice-2 lesson). Used as an NF1 feature, not a heuristic MVP-1 blend.
    feat["xfp_pg"] = (_PTS_REC * feat["xrec_pg"] + _PTS_REC_YD * feat["xrec_yds_pg"]
                      + _PTS_TD * (feat["xrush_td_pg"] + feat["xrec_td_pg"]))
    feat["td_luck_ratio"] = ((feat["rush_td_pg_actual"] + feat["rec_td_pg_actual"])
                             - (feat["xrush_td_pg"] + feat["xrec_td_pg"]))
    feat["xfp_base_season"] = int(base_season)
    return feat
