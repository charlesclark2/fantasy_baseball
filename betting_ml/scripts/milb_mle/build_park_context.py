"""build_park_context.py — MLB Edge-E7.12 SLICE 1: assemble the minor-league PARK + LEVEL-RUN-ENVIRONMENT
context ONCE → parquet, SF-free (DuckDB over the S3 lakehouse).

⚠️ **OPERATOR-RUN (>2 min, S3 I/O).** It scans the full E7.1 MiLB substrate (~4.6M player-game rows) four
times — once per level — and builds a leave-one-player-out park-factor table. `--limit-seasons` /
`--levels` give a cheap smoke that proves the code path without the full run.

WHAT IT PRODUCES — `mle_park_context.parquet`, ONE row per (player_id, level), the join key the E7.3
`mle_graduated_pairs` artifact already uses:

  * `pf_<metric>_exposure`        ⭐ the headline — the player's **actual PA-exposure-weighted**
                                  (geometric-mean) park factor across EVERY park he took a plate
                                  appearance in, **leave-one-player-out**.
  * `pf_<metric>_exposure_noloo`  the same without the LOO subtraction — a DIAGNOSTIC arm, not a
                                  candidate (see the self-shrinkage trap below).
  * `pf_<metric>_home`            the factor of his primary (most-PA) HOME park → the memo's
                                  half-weight foil `(1 + pf_home)/2` is derived from it at apply time.
  * `env_<metric>`                his PA-weighted level×SEASON run environment.
  * `env_level_<metric>`          his level's POOLED run environment (the normalisation anchor).
  * coverage columns             `pf_<metric>_covered_pa_share`, `pf_n_park_seasons`, `context_pa`.

WHY WE CAN COMPUTE OUR OWN PARK FACTORS AT ALL (the memo assumed we'd have to hand-key BA's table):
the E7.1 ingest denormalises `venue_id` / `venue_name` / `team_side` / `game_pk` onto EVERY player-game
row, so the free substrate we already land nightly contains the complete home/road split. No paywalled
Baseball America table, no pybaseball dependency, no new ingest — and because we have per-game venue, we
get **true per-player park exposure** instead of the "~half his games were at home" approximation the
published-table route forces.

THE PARK FACTOR (classic Bill James / Davenport form, per park team T, metric m, trailing 3-season window)

    PF(T) = rate_m( every batter-row in T's HOME games ) / rate_m( every batter-row in T's ROAD games )

Both buckets contain T's own hitters, so team offensive quality largely cancels; the residual difference
is the park (plus the opponent mix, which averages out over a 3-season window). Then EB-shrunk toward
1.0 in log space by the BINDING side's PA and clamped — see `park_context.shrink_log_pf`.

🪤 **THE SELF-SHRINKAGE TRAP — why LEAVE-ONE-PLAYER-OUT is load-bearing, not hygiene.** A player's own
hot line inflates his home park's factor. Dividing his rate by a factor he helped create shrinks *him
specifically* toward the mean — and shrinkage toward the mean reduces MAE against a regressed target
**whether or not parks exist**. A non-LOO park adjustment would therefore MANUFACTURE the very lift this
slice is trying to measure, and no deflation gate (PBO/DSR) could see it, because every fold would agree.
So every headline factor here subtracts the player's OWN counting stats from BOTH buckets before taking
the ratio, and the non-LOO version ships beside it as a labelled diagnostic so the size of the trap is
reported rather than assumed. (Same family as the repo's oracle-floor / degenerate-ceiling rule: score
the thing that must lose.)

Run (LAPTOP or BOX; DuckDB-S3 needs `AWS_DEFAULT_REGION=us-east-2`):
    uv run python -m betting_ml.scripts.milb_mle.build_park_context --season-floor 2015
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

from betting_ml.scripts.milb_mle.milb_mle import LEVEL_ORDER  # noqa: E402
from betting_ml.scripts.milb_mle.park_context import (  # noqa: E402
    DEFAULT_PF_PSEUDO_PA,
    DEFAULT_PF_WINDOW,
    PF_CLAMP,
    PF_METRICS,
    exposure_weighted_pf,
    park_factors_from_buckets,
    rates_from_reduced,
    reduced_aggregate_sql,
)

log = logging.getLogger("e7_12.park_context")

BUCKET = "s3://baseball-betting-ml-artifacts"
MILB = f"{BUCKET}/baseball/milb"
_DEFAULT_OUT = (_PROJECT_ROOT
                / "quant_sports_intel_models/baseball/edge_program/ablation_results/e7_12_artifacts")


def _connect():
    """DuckDB with the S3 credential chain + the Delta extension. Mirrors `build_graduated_pairs._connect`
    — same substrate, same reader, so a lakehouse-routing change lands in both."""
    from scripts.utils.lakehouse_read import duck_connect, register_views

    conn = duck_connect()
    try:
        conn.execute("INSTALL delta; LOAD delta")
    except Exception as e:  # noqa: BLE001
        log.warning("delta extension load failed (%s) — MiLB delta_scan may fail", e)
    register_views(conn, ["mart_batter_rolling_stats"])
    conn.execute(f"CREATE OR REPLACE VIEW milb_logs AS SELECT * FROM delta_scan('{MILB}/player_game_logs')")
    return conn


# ══════════════════════════════════════════════════════════════════════════════════════
# SQL — one level at a time (bounds peak memory; a park team plays at exactly one level)
# ══════════════════════════════════════════════════════════════════════════════════════


def _level_sql(level: str, window: int, season_floor: int | None) -> str:
    """The per-level park/exposure assembly.

    Returns one row per (player_id, park_team_id, season) the player took a PRE-DEBUT plate appearance
    in, carrying the window-summed HOME and ROAD reduced buckets ALREADY leave-one-player-out subtracted
    (`h_*` / `r_*`), the non-LOO buckets (`nh_*` / `nr_*`), and the exposure weight (`pa_exposure`).
    """
    season_filter = f"and l0.season >= {season_floor}" if season_floor else ""
    w = window - 1
    park_h = reduced_aggregate_sql("h", "l.")
    park_r = reduced_aggregate_sql("r", "l.")
    play_h = reduced_aggregate_sql("ph", "l.")
    play_r = reduced_aggregate_sql("pr", "l.")
    fields = ("pa", "ab", "so", "bb", "h", "tb", "woba_num", "woba_den")
    win_park = ",\n           ".join(
        [f"sum(b.h_{f}) as h_{f}" for f in fields] + [f"sum(b.r_{f}) as r_{f}" for f in fields])
    win_play = ",\n           ".join(
        [f"sum(b.ph_{f}) as ph_{f}" for f in fields] + [f"sum(b.pr_{f}) as pr_{f}" for f in fields])
    loo = ",\n           ".join(
        [f"pw.h_{f} - coalesce(uw.ph_{f}, 0) as h_{f}" for f in fields]
        + [f"pw.r_{f} - coalesce(uw.pr_{f}, 0) as r_{f}" for f in fields]
        + [f"pw.h_{f} as nh_{f}" for f in fields]
        + [f"pw.r_{f} as nr_{f}" for f in fields])

    return f"""
    with logs as (
        select l0.*
        from milb_logs l0
        where l0.is_batter = true and l0.game_type = 'R' and l0.level_name = '{level}'
          {season_filter}
    ),
    mlb_debut as (
        select batter_id::varchar as player_id, min(game_date::date) as debut_date
        from mart_batter_rolling_stats group by batter_id
    ),
    -- ONE row per game: who hosted it (the park team) and where. Aggregated rather than SELECT DISTINCT
    -- so a stray disagreeing row can never duplicate a game into the bucket twice.
    home_map as (
        select game_pk, min(team_id) as park_team_id, any_value(season) as season,
               any_value(venue_id) as venue_id, any_value(venue_name) as venue_name
        from logs where team_side = 'home' group by game_pk
    ),
    away_map as (
        select game_pk, min(team_id) as park_team_id from logs where team_side = 'away' group by game_pk
    ),
    -- the park's two buckets, per season: EVERY batter row in its home games vs in the park team's road games
    park_home as (
        select hm.park_team_id, hm.season, any_value(hm.venue_id) as venue_id,
               any_value(hm.venue_name) as venue_name,
               {park_h}
        from logs l join home_map hm on l.game_pk = hm.game_pk
        group by 1, 2
    ),
    park_road as (
        select am.park_team_id, l.season, {park_r}
        from logs l join away_map am on l.game_pk = am.game_pk
        group by 1, 2
    ),
    park_season as (
        select coalesce(h.park_team_id, r.park_team_id) as park_team_id,
               coalesce(h.season, r.season) as season,
               h.venue_id, h.venue_name,
               {", ".join(f"coalesce(h.h_{f}, 0) as h_{f}" for f in fields)},
               {", ".join(f"coalesce(r.r_{f}, 0) as r_{f}" for f in fields)}
        from park_home h
        full outer join park_road r on r.park_team_id = h.park_team_id and r.season = h.season
    ),
    -- TRAILING {window}-season window ([S-{w}, S]) — never reads a season after the one it is applied in
    park_window as (
        select a.park_team_id, a.season, any_value(a.venue_id) as venue_id,
               any_value(a.venue_name) as venue_name,
               {win_park}
        from park_season a
        join park_season b on b.park_team_id = a.park_team_id
                          and b.season between a.season - {w} and a.season
        group by 1, 2
    ),
    -- the SAME player's own contribution to each bucket (all games, not just pre-debut — the bucket it
    -- is subtracted from is all-games too)
    player_home as (
        select l.player_id, hm.park_team_id, hm.season, {play_h}
        from logs l join home_map hm on l.game_pk = hm.game_pk
        group by 1, 2, 3
    ),
    player_road as (
        select l.player_id, am.park_team_id, l.season, {play_r}
        from logs l join away_map am on l.game_pk = am.game_pk
        group by 1, 2, 3
    ),
    player_park as (
        select coalesce(h.player_id, r.player_id) as player_id,
               coalesce(h.park_team_id, r.park_team_id) as park_team_id,
               coalesce(h.season, r.season) as season,
               {", ".join(f"coalesce(h.ph_{f}, 0) as ph_{f}" for f in fields)},
               {", ".join(f"coalesce(r.pr_{f}, 0) as pr_{f}" for f in fields)}
        from player_home h
        full outer join player_road r
          on r.player_id = h.player_id and r.park_team_id = h.park_team_id and r.season = h.season
    ),
    player_window as (
        select a.player_id, a.park_team_id, a.season, {win_play}
        from player_park a
        join player_park b on b.player_id = a.player_id and b.park_team_id = a.park_team_id
                          and b.season between a.season - {w} and a.season
        group by 1, 2, 3
    ),
    -- exposure = the player's PRE-DEBUT plate appearances at that park in that season (the weight), and
    -- whether those PA came as the HOME side (which identifies his primary home park for the foil)
    exposure as (
        select l.player_id, hm.park_team_id, hm.season,
               sum(coalesce(l.bat_plate_appearances, 0)) as pa_exposure,
               sum(case when l.team_side = 'home'
                        then coalesce(l.bat_plate_appearances, 0) else 0 end) as pa_home_side
        from logs l
        join home_map hm on l.game_pk = hm.game_pk
        left join mlb_debut d on d.player_id = l.player_id::varchar
        where (d.debut_date is null or l.official_date::date < d.debut_date)
        group by 1, 2, 3
        having sum(coalesce(l.bat_plate_appearances, 0)) > 0
    )
    select e.player_id::varchar as player_id,
           '{level}' as level,
           e.park_team_id, e.season, e.pa_exposure, e.pa_home_side,
           pw.venue_id, pw.venue_name,
           {loo}
    from exposure e
    join park_window pw on pw.park_team_id = e.park_team_id and pw.season = e.season
    left join player_window uw on uw.player_id = e.player_id
                              and uw.park_team_id = e.park_team_id and uw.season = e.season
    """


def _env_sql(level: str, season_floor: int | None) -> str:
    """The level×SEASON run environment, and each player's PRE-DEBUT PA in each of those seasons."""
    season_filter = f"and l0.season >= {season_floor}" if season_floor else ""
    env_agg = reduced_aggregate_sql("e", "l.")
    return f"""
    with logs as (
        select l0.* from milb_logs l0
        where l0.is_batter = true and l0.game_type = 'R' and l0.level_name = '{level}' {season_filter}
    ),
    mlb_debut as (
        select batter_id::varchar as player_id, min(game_date::date) as debut_date
        from mart_batter_rolling_stats group by batter_id
    ),
    env as (select l.season, {env_agg} from logs l group by 1),
    player_season as (
        select l.player_id::varchar as player_id, l.season,
               sum(coalesce(l.bat_plate_appearances, 0)) as pa
        from logs l
        left join mlb_debut d on d.player_id = l.player_id::varchar
        where (d.debut_date is null or l.official_date::date < d.debut_date)
        group by 1, 2
        having sum(coalesce(l.bat_plate_appearances, 0)) > 0
    )
    select ps.player_id, '{level}' as level, ps.season, ps.pa,
           {", ".join(f"e.e_{f}" for f in ("pa", "ab", "so", "bb", "h", "tb", "woba_num", "woba_den"))}
    from player_season ps join env e on e.season = ps.season
    """


# ══════════════════════════════════════════════════════════════════════════════════════
# Assembly
# ══════════════════════════════════════════════════════════════════════════════════════


def _level_context(raw: pd.DataFrame, env_raw: pd.DataFrame, level: str,
                   pseudo_pa: float, clamp: tuple[float, float]) -> pd.DataFrame:
    """One level's per-(player, level) context row, from the two SQL results."""
    metrics = PF_METRICS
    if raw.empty:
        return pd.DataFrame()

    # ── park factors: LOO (headline) and non-LOO (diagnostic), both from the same shrink+clamp ──
    loo = park_factors_from_buckets(raw, metrics, pseudo_pa, clamp, "h", "r")
    noloo = park_factors_from_buckets(raw, metrics, pseudo_pa, clamp, "nh", "nr")
    for m in metrics:
        loo[f"pfn_{m}"] = noloo[f"pf_{m}"].to_numpy(float)

    keys = ("player_id", "level")
    exp = exposure_weighted_pf(loo, metrics, "pf_", "pa_exposure", keys)
    exp_n = exposure_weighted_pf(loo, metrics, "pfn_", "pa_exposure", keys)
    out = exp.merge(
        exp_n[list(keys) + [f"pfn_{m}_exposure" for m in metrics]], on=list(keys), how="outer")
    out = out.rename(columns={f"pfn_{m}_exposure": f"pf_{m}_exposure_noloo" for m in metrics})

    # ── the memo's half-weight foil needs the PRIMARY HOME park: the (park_team, season) where the
    #    player took the most PA *as the home side*. `(1 + pf_home)/2` is derived at apply time.
    home_rows = loo[loo["pa_home_side"] > 0].copy()
    if not home_rows.empty:
        idx = home_rows.groupby(list(keys), dropna=False)["pa_home_side"].idxmax()
        primary = home_rows.loc[idx, list(keys) + [f"pf_{m}" for m in metrics]].copy()
        primary = primary.rename(columns={f"pf_{m}": f"pf_{m}_home" for m in metrics})
        out = out.merge(primary, on=list(keys), how="left")
    else:
        for m in metrics:
            out[f"pf_{m}_home"] = np.nan

    tot = (loo.groupby(list(keys), dropna=False)["pa_exposure"].sum()
           .rename("context_pa").reset_index())
    out = out.merge(tot, on=list(keys), how="left")

    # ── level × season run environment ────────────────────────────────────────────────
    if not env_raw.empty:
        env_rates = rates_from_reduced(env_raw, "e", metrics)
        e = env_raw[["player_id", "level", "pa"]].copy()
        for m in metrics:
            e[f"_r_{m}"] = env_rates[m]
        # the player's PA-weighted season environment
        agg: dict[str, str] = {"pa": "sum"}
        for m in metrics:
            e[f"_w_{m}"] = np.where(np.isfinite(e[f"_r_{m}"]), e["pa"], 0.0)
            e[f"_wr_{m}"] = e[f"_w_{m}"] * np.nan_to_num(e[f"_r_{m}"], nan=0.0)
            agg[f"_w_{m}"] = "sum"
            agg[f"_wr_{m}"] = "sum"
        g = e.groupby(["player_id", "level"], dropna=False).agg(agg).reset_index()
        for m in metrics:
            den = g[f"_w_{m}"].to_numpy(float)
            g[f"env_{m}"] = np.divide(g[f"_wr_{m}"].to_numpy(float), den,
                                      out=np.full_like(den, np.nan), where=den > 0)
        # the LEVEL's pooled environment (the normalisation anchor) — pooled over COUNTS, not a mean of
        # per-season rates, so a thin season cannot pull the anchor around
        pooled = env_raw.drop_duplicates(subset=["season"])
        pooled_sum = pooled[[f"e_{f}" for f in
                             ("pa", "ab", "so", "bb", "h", "tb", "woba_num", "woba_den")]].sum().to_frame().T
        pooled_rates = rates_from_reduced(pooled_sum, "e", metrics)
        for m in metrics:
            g[f"env_level_{m}"] = float(pooled_rates[m][0])
        out = out.merge(g[["player_id", "level"] + [f"env_{m}" for m in metrics]
                          + [f"env_level_{m}" for m in metrics]],
                        on=["player_id", "level"], how="left")
    out["level"] = level
    return out


def build_park_context(levels: tuple[str, ...] = LEVEL_ORDER,
                       window: int = DEFAULT_PF_WINDOW,
                       season_floor: int | None = None,
                       pseudo_pa: float = DEFAULT_PF_PSEUDO_PA,
                       clamp: tuple[float, float] = PF_CLAMP) -> pd.DataFrame:
    conn = _connect()
    parts: list[pd.DataFrame] = []
    try:
        for level in levels:
            log.info("[%s] park buckets + leave-one-player-out exposure ...", level)
            raw = conn.execute(_level_sql(level, window, season_floor)).df()
            log.info("[%s] %d (player, park, season) exposure rows", level, len(raw))
            env_raw = conn.execute(_env_sql(level, season_floor)).df()
            part = _level_context(raw, env_raw, level, pseudo_pa, clamp)
            log.info("[%s] → %d (player, level) context rows", level, len(part))
            if not part.empty:
                parts.append(part)
    finally:
        conn.close()
    if not parts:
        return pd.DataFrame()
    ctx = pd.concat(parts, ignore_index=True)
    ctx["pf_window_seasons"] = window
    ctx["pf_pseudo_pa"] = pseudo_pa
    return ctx


def summarise(ctx: pd.DataFrame) -> dict:
    """The face-validity read the report leads with — a park-factor table whose spread is ~0 has
    silently failed (a dead join, a collapsed shrink) even though every gate downstream would pass."""
    out: dict = {"n_rows": int(len(ctx)), "n_players": int(ctx["player_id"].nunique()) if len(ctx) else 0}
    for m in PF_METRICS:
        col = f"pf_{m}_exposure"
        if col not in ctx:
            continue
        v = pd.to_numeric(ctx[col], errors="coerce").dropna()
        out[m] = {
            "n": int(len(v)),
            "p05": round(float(v.quantile(0.05)), 4) if len(v) else None,
            "median": round(float(v.median()), 4) if len(v) else None,
            "p95": round(float(v.quantile(0.95)), 4) if len(v) else None,
            "spread_p95_p05": round(float(v.quantile(0.95) - v.quantile(0.05)), 4) if len(v) else None,
        }
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="E7.12 slice 1 — assemble the MiLB park + level-run-environment context")
    p.add_argument("--out-dir", default=str(_DEFAULT_OUT))
    p.add_argument("--levels", nargs="+", default=list(LEVEL_ORDER))
    p.add_argument("--pf-window", type=int, default=DEFAULT_PF_WINDOW,
                   help="trailing seasons pooled into a park factor (default 3 — single-season MiLB "
                        "park factors are noisy)")
    p.add_argument("--season-floor", type=int, default=None,
                   help="only MiLB seasons >= this (use the SAME floor as the pairs build)")
    p.add_argument("--pf-pseudo-pa", type=float, default=DEFAULT_PF_PSEUDO_PA,
                   help="EB pseudo-count (PA) shrinking a thin park toward neutral")
    p.add_argument("--s3", action="store_true",
                   help="also land at baseball/milb/derived/mle_park_context (Delta)")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")

    ctx = build_park_context(tuple(args.levels), args.pf_window, args.season_floor, args.pf_pseudo_pa)
    if ctx.empty:
        log.error("no park context assembled — check the MiLB substrate / level names")
        return 1

    summary = summarise(ctx)
    log.info("park-context summary: %s", summary)
    # FACE VALIDITY (not a gate — a HALT): a park-factor table with no spread is a dead join wearing a
    # successful run's clothes. Real MiLB parks differ by tens of points on ISO.
    iso = summary.get("iso") or {}
    if iso.get("spread_p95_p05") is not None and iso["spread_p95_p05"] < 0.01:
        raise AssertionError(
            f"park factors have essentially NO spread (ISO p95-p05 = {iso['spread_p95_p05']}) — the "
            f"home/road buckets are not resolving. A dispersion-free park factor cannot be a park "
            f"factor; do NOT run the ablation on this artifact.")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / "mle_park_context.parquet"
    ctx.to_parquet(dest, index=False)
    log.info("wrote %s (%d rows)", dest, len(ctx))

    if args.s3:
        from deltalake import write_deltalake

        from scripts.utils.delta_lake import storage_options
        write_deltalake(f"{MILB}/derived/mle_park_context", ctx, mode="overwrite",
                        storage_options=storage_options())
        log.info("landed park context at %s/derived/mle_park_context", MILB)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
