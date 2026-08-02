"""build_opponent_context.py — MLB Edge-E7.15 H2: assemble the OPPONENT-QUALITY context ONCE → parquet,
SF-free (DuckDB over the S3 lakehouse).

⚠️ **OPERATOR-RUN (>2 min, S3 I/O).** It scans the full E7.1 MiLB substrate (~4.6M player-game rows) once
per level and builds a leave-the-player's-own-games-out opponent-quality table. `--levels` / `--season-floor`
give a cheap smoke that proves the code path without the full run.

WHAT IT PRODUCES — `mle_opponent_context.parquet`, ONE row per (player_id, level), the same join key the
E7.3 `mle_graduated_pairs` artifact and the slice-1 park context already use:

  * `of_<metric>_exposure`        ⭐ the headline — the player's **actual PA-exposure-weighted**
                                  (geometric-mean) opponent-quality factor across every opponent he
                                  faced, **leave-his-own-games-out**.
  * `of_<metric>_exposure_noloo`  the same WITHOUT the LOO removal — a DIAGNOSTIC arm, not a candidate
                                  (see the self-inflation trap in `opponent_context`).
  * `of_<metric>_covered_pa_share`, `of_n_opponent_seasons`, `opp_context_pa` — coverage.

⭐ **THE SCOPE-GATE THIS STORY CARRIED, AND HOW IT RESOLVED.** The E7.15 prompt flagged "confirm opponent
identity is in the MiLB game logs first" as a real risk — a story that turns out to need a new ingest is a
different story. The logs carry **no opponent column**: 75 columns, and `team_id` is the player's OWN
team. But `game_pk` IS denormalised onto every row and BOTH teams' players are present in every game
(verified: 1,559 of 1,559 sampled 2024 games carry exactly 2 distinct `team_id`s, ~27 player-rows each).
So opponent identity is recoverable by a self-join on `game_pk` from the substrate we already land
nightly — **no new ingest, no new source, no paywalled schedule table.** H2 is a modelling story.

THE OPPONENT FACTOR (per opponent team T, metric m, trailing `--window` seasons)

    OF(T) = rate_m( every BATTER row in T's matchups ) / rate_m( the level-season pooled batter rate )

measured in batter counting stats on BOTH sides, because a pitcher's K% and the opposing lineup's K% are
the same physical event seen from opposite sides of the plate. The GROUPING is what differs:

  * BATTER focal player — his opponents are pitching staffs ⇒ bucket = batter rows of teams facing T
    (i.e. "how did batters hit against T"). High ⇒ T's pitching is weak.
  * PITCHER focal player — his opponents are lineups ⇒ bucket = T's OWN batter rows ("how did T hit").
    High ⇒ T's hitters are strong.

Then EB-shrunk toward 1.0 in log space by the bucket's PA and clamped, then geometrically averaged over
the player's real per-opponent exposure.

🪤 **LEAVE-ONE-OUT IS AT GAME LEVEL AND IT IS LOAD-BEARING.** A batter's own hits are IN his opponents'
allowed-rate bucket, so a great hitter makes every team he faced look weaker and dividing by that
weakness shrinks *him* toward the mean — which lowers MAE against a regressed target whether or not
opponent quality exists. The focal player's entire games are therefore removed from the bucket. Game
level rather than row level because it is the only form that works identically on both sides: a
pitcher's influence on the opposing lineup's numbers is real but is not a row he owns.

Run (LAPTOP or BOX; DuckDB-S3 needs `AWS_DEFAULT_REGION=us-east-2`):
    uv run python -m betting_ml.scripts.milb_mle.build_opponent_context --season-floor 2015
    uv run python -m betting_ml.scripts.milb_mle.build_opponent_context --season-floor 2015 \
        --player-type pitcher
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

from betting_ml.scripts.milb_mle.milb_mle import LEVEL_ORDER, _WOBA_W  # noqa: E402
from betting_ml.scripts.milb_mle.opponent_context import (  # noqa: E402
    DEFAULT_OPP_WINDOW,
    OPP_FIELDS,
    OPPONENT_METRICS,
    exposure_weighted_opponent,
    opponent_factors_from_buckets,
    opponent_spread,
    split_half_reliability,
)
from betting_ml.scripts.milb_mle.park_context import ReducedSpec, reduced_spec  # noqa: E402

log = logging.getLogger("e7_15.build_opp")

BUCKET = "s3://baseball-betting-ml-artifacts"
MILB = f"{BUCKET}/baseball/milb"
_DEFAULT_OUT = (_PROJECT_ROOT
                / "quant_sports_intel_models/baseball/edge_program/ablation_results/e7_15_artifacts")


def _connect(spec: ReducedSpec):
    """DuckDB with the S3 credential chain + the Delta extension. Mirrors `build_park_context._connect`
    — same substrate, same reader, so a lakehouse-routing change lands in both."""
    from scripts.utils.lakehouse_read import duck_connect, register_views

    conn = duck_connect()
    try:
        conn.execute("INSTALL delta; LOAD delta")
    except Exception as e:  # noqa: BLE001
        log.warning("delta extension load failed (%s) — MiLB delta_scan may fail", e)
    register_views(conn, [spec.debut_table])
    conn.execute(f"CREATE OR REPLACE VIEW milb_logs AS SELECT * FROM delta_scan('{MILB}/player_game_logs')")
    return conn


def _bat_reduce_sql(prefix: str, c: str = "b.") -> str:
    """`sum(...) as <prefix>_<field>` over the BATTER counting stats, for every `OPP_FIELDS` entry.

    The wOBA numerator is generated from `milb_mle._WOBA_W` (the single formula home) so the opponent
    bucket's wOBA can never drift from the player's own — the same discipline
    `park_context.woba_numerator_sql` applies to the park buckets.
    """
    w = _WOBA_W
    b1 = (f"greatest(coalesce({c}bat_hits,0) - coalesce({c}bat_doubles,0) "
          f"- coalesce({c}bat_triples,0) - coalesce({c}bat_home_runs,0), 0)")
    ubb = f"greatest(coalesce({c}bat_walks,0) - coalesce({c}bat_intentional_walks,0), 0)"
    woba_num = (f"{w['ubb']}*({ubb}) + {w['hbp']}*coalesce({c}bat_hit_by_pitch,0) + {w['b1']}*({b1}) "
                f"+ {w['b2']}*coalesce({c}bat_doubles,0) + {w['b3']}*coalesce({c}bat_triples,0) "
                f"+ {w['hr']}*coalesce({c}bat_home_runs,0)")
    woba_den = (f"coalesce({c}bat_at_bats,0) + ({ubb}) + coalesce({c}bat_sac_flies,0) "
                f"+ coalesce({c}bat_hit_by_pitch,0)")
    expr = {
        "pa": f"coalesce({c}bat_plate_appearances,0)",
        "ab": f"coalesce({c}bat_at_bats,0)",
        "so": f"coalesce({c}bat_strike_outs,0)",
        "bb": ubb,
        "h": f"coalesce({c}bat_hits,0)",
        "tb": f"coalesce({c}bat_total_bases,0)",
        "hr": f"coalesce({c}bat_home_runs,0)",
        "go": f"coalesce({c}bat_ground_outs,0)",
        "ao": f"coalesce({c}bat_air_outs,0)",
        "woba_num": woba_num,
        "woba_den": woba_den,
    }
    return ",\n           ".join(f"sum({expr[f]}) as {prefix}_{f}" for f in OPP_FIELDS)


def _level_sql(level: str, season_floor: int | None, spec: ReducedSpec) -> str:
    """Per-level assembly → one row per (player_id, opp_team_id, season).

    Carries the season's opponent bucket (`o_*`), the SAME bucket minus the focal player's own games
    (`l_*` — the LOO version), the level-season pooled batter bucket (`lv_*`, the normalisation anchor)
    and the player's exposure against that opponent-season.
    """
    season_filter = f"and l0.season >= {season_floor}" if season_floor else ""
    # ⭐ WHICH BUCKET IS "THE OPPONENT" DEPENDS ON WHICH SIDE THE FOCAL PLAYER IS.
    #   batter focal → his opponents are pitching staffs → bucket = batter rows of teams FACING T
    #   pitcher focal → his opponents are lineups        → bucket = T's OWN batter rows
    # One line of SQL, and getting it backwards produces a plausible factor that measures the player's
    # OWN league-mates instead of his opposition — which is why it is spelled out rather than inferred.
    bucket_key = "gt.other_team_id" if spec.player_type == "batter" else "b.team_id"
    return f"""
    with logs as (
        select l0.* from milb_logs l0
        where l0.game_type = 'R' and l0.level_name = '{level}' {season_filter}
    ),
    mlb_debut as (
        select {spec.debut_id_col}::varchar as player_id, min(game_date::date) as debut_date
        from {spec.debut_table} group by {spec.debut_id_col}
    ),
    -- the two teams in every game (verified: exactly 2 distinct team_id per game_pk)
    game_teams as (select distinct game_pk, team_id, season from logs),
    pairs as (
        select a.game_pk, a.season, a.team_id, b.team_id as other_team_id
        from game_teams a join game_teams b
          on a.game_pk = b.game_pk and a.team_id <> b.team_id
    ),
    bat as (select * from logs where is_batter = true),
    -- the OPPONENT-QUALITY bucket, per (opponent team, season)
    bucket as (
        select {bucket_key} as opp_team_id, b.season,
           {_bat_reduce_sql('o')}
        from bat b
        join pairs gt on gt.game_pk = b.game_pk and gt.team_id = b.team_id
        group by 1, 2
    ),
    -- ⭐ TWO NORMALISATION ANCHORS, because the choice is load-bearing and was settled by measurement.
    -- LEVEL-season pooled is the naive anchor. But 45-62% of the resulting factor's variance is
    -- BETWEEN-LEAGUE (measured: Mexican League 0.89 vs International League 1.03 on k_pct), and E7.3
    -- ALREADY fits a per-league random intercept — so a level-normalised factor is roughly half a
    -- re-encoding of a feature the model has, and a lift on it would be unattributable to opponent
    -- quality. The LEAGUE-season anchor removes exactly what the model already knows, leaving
    -- WITHIN-league strength of schedule = the genuinely new information H2 is about.
    level_pooled as (
        select b.season,
           {_bat_reduce_sql('lv')}
        from bat b group by 1
    ),
    team_league as (
        select team_id, season, mode(league_name) as league_name
        from logs group by 1, 2
    ),
    league_pooled as (
        select tl.league_name, b.season,
           {_bat_reduce_sql('lg')}
        from bat b
        join team_league tl on tl.team_id = b.team_id and tl.season = b.season
        group by 1, 2
    ),
    -- the FOCAL player's pre-debut appearances, and which opponent each was against
    focal as (
        select l.player_id::varchar as player_id, l.game_pk, l.season, gt.other_team_id,
               coalesce(l.{spec.exposure_col}, 0) as exposure
        from logs l
        join pairs gt on gt.game_pk = l.game_pk and gt.team_id = l.team_id
        left join mlb_debut d on d.player_id = l.player_id::varchar
        where l.{spec.is_flag} = true
          and (d.debut_date is null or l.official_date::date < d.debut_date)
    ),
    -- ⭐ THE LEAVE-ONE-OUT SUBTRACTION: the focal player's OWN GAMES' contribution to that opponent's
    -- bucket. A batter's hits are IN his opponents' allowed-rate bucket, so dividing by a weakness he
    -- created shrinks HIM toward the mean and manufactures lift no deflation gate can see.
    own as (
        select f.player_id, {'gt.other_team_id' if spec.player_type == 'batter' else 'b.team_id'} as opp_team_id,
               b.season,
           {_bat_reduce_sql('own')}
        from (select distinct player_id, game_pk from focal) f
        join bat b on b.game_pk = f.game_pk
        join pairs gt on gt.game_pk = b.game_pk and gt.team_id = b.team_id
        group by 1, 2, 3
    ),
    exposure as (
        select player_id, other_team_id as opp_team_id, season,
               sum(exposure) as pa
        from focal group by 1, 2, 3
    )
    select e.player_id, e.opp_team_id, e.season, e.pa,
           {", ".join(f"coalesce(bk.o_{f}, 0) as no_{f}" for f in OPP_FIELDS)},
           {", ".join(f"coalesce(bk.o_{f}, 0) - coalesce(ow.own_{f}, 0) as o_{f}" for f in OPP_FIELDS)},
           {", ".join(f"coalesce(lp.lv_{f}, 0) as lv_{f}" for f in OPP_FIELDS)},
           {", ".join(f"coalesce(gp.lg_{f}, 0) as lg_{f}" for f in OPP_FIELDS)},
           otl.league_name as opp_league
    from exposure e
    left join bucket bk on bk.opp_team_id = e.opp_team_id and bk.season = e.season
    left join own ow on ow.player_id = e.player_id and ow.opp_team_id = e.opp_team_id
                     and ow.season = e.season
    left join level_pooled lp on lp.season = e.season
    left join team_league otl on otl.team_id = e.opp_team_id and otl.season = e.season
    left join league_pooled gp on gp.league_name = otl.league_name and gp.season = e.season
    where e.pa > 0
    """


def _window_sum(raw: pd.DataFrame, window: int) -> pd.DataFrame:
    """Trailing `window`-season sums of the opponent buckets, per (player, opponent).

    `window=1` (the default) is a pass-through: a MiLB team's roster turns over every year, so quality is
    a SEASON property unlike a park. `window=3` is a registered candidate because 3 is the window the
    park slice's assertion named.

    🪤 **THE FIRST VERSION SILENTLY PRODUCED A CONSTANT 1.0 FACTOR.** It built the rolling frame and then
    assigned the key columns back onto it positionally, which misaligned the index and left the bucket
    sums at 0 — and a 0-PA bucket has shrink weight 0, so every factor came out EXACTLY 1.000. That is
    the worst possible failure shape: not a crash, not a NaN, but a perfectly plausible neutral factor
    whose arm then reports as an honest null. `sd == 0` on a factor column is the tell, and the runner's
    `pct_rows_moved` check is what actually caught it.
    """
    if window <= 1:
        return raw
    val_cols = [c for c in raw.columns
                if c.split("_", 1)[0] in ("o", "no", "lv", "lg") and c != "opp_team_id"]
    key_cols = [c for c in raw.columns if c not in val_cols]
    out = (raw.sort_values(["player_id", "opp_team_id", "season"])
              .reset_index(drop=True))
    rolled = (out.groupby(["player_id", "opp_team_id"], sort=False)[val_cols]
                 .rolling(window, min_periods=1).sum()
                 .reset_index(level=[0, 1], drop=True))
    out[val_cols] = rolled
    return out[key_cols + val_cols]


# ⭐ THE FACTOR VARIANTS, all produced in ONE SQL pass because the scan is the expensive part.
#    of_<m>_exposure            league-season normalised, window 1, LOO   ← the HEADLINE (new information)
#    of_<m>_exposure_levelnorm  level-season normalised,  window 1, LOO   ← the naive form; the gap
#                                                                          between it and the headline
#                                                                          IS the league re-encoding
#    of_<m>_exposure_noloo      league-season normalised, window 1, NO LOO ← the self-inflation anchor
#    of_<m>_exposure_w3         league-season normalised, window 3, LOO   ← the window formulation
_VARIANTS: tuple[tuple[str, str, str, int], ...] = (
    ("", "o", "lg", 1),
    ("_levelnorm", "o", "lv", 1),
    ("_noloo", "no", "lg", 1),
    ("_w3", "o", "lg", 3),
)


def build_opponent_context(levels: tuple[str, ...] = LEVEL_ORDER, season_floor: int | None = None,
                           window: int = DEFAULT_OPP_WINDOW,
                           player_type: str = "batter") -> tuple[pd.DataFrame, pd.DataFrame]:
    """One row per (player_id, level) carrying every pre-registered factor variant.

    `window` is retained as the DEFAULT for the headline variant; `_VARIANTS` pins the rest, so a
    caller cannot accidentally ship a run whose anchor was built on a different window than the arm it
    is anchoring.
    """
    spec = reduced_spec(player_type)
    metrics = OPPONENT_METRICS[player_type]
    conn = _connect(spec)
    frames: list[pd.DataFrame] = []
    rel_frames: list[pd.DataFrame] = []
    try:
        for level in levels:
            log.info("[%s] %s — scanning opponent buckets ...", player_type, level)
            raw = conn.execute(_level_sql(level, season_floor, spec)).df()
            if raw.empty:
                log.warning("[%s] %s produced no rows", player_type, level)
                continue
            per_level: pd.DataFrame | None = None
            for suffix, bucket_prefix, anchor_prefix, win in _VARIANTS:
                w = _window_sum(raw, win if suffix == "_w3" else window)
                fac = opponent_factors_from_buckets(
                    w, metrics, bucket_prefix=bucket_prefix, level_prefix=anchor_prefix)
                fac["level"] = level
                pp = exposure_weighted_opponent(fac, metrics).rename(
                    columns={f"of_{m}_exposure": f"of_{m}_exposure{suffix}" for m in metrics}
                    | {f"of_{m}_covered_pa_share": f"of_{m}_covered_pa_share{suffix}"
                       for m in metrics})
                if suffix:
                    # only the headline variant contributes the shared bookkeeping column, or the
                    # outer merge would produce `_x`/`_y` duplicates of it per variant
                    pp = pp.drop(columns=["of_n_opponent_seasons"], errors="ignore")
                per_level = pp if per_level is None else per_level.merge(
                    pp, on=["player_id", "level"], how="outer")
                # ⭐ RELIABILITY FOR THE HEADLINE **AND** THE LEVEL-NORMALISED VARIANT — the second is
                # the POSITIVE CONTROL. An instrument that reports "this factor is pure noise" is worth
                # nothing unless the SAME instrument, on the SAME rows, can report a high reliability
                # for a factor that has one (NF1.7 (a) / E7.16's leakage-scan control). The
                # level-normalised factor carries a large real between-league component, so it is the
                # known-positive; if it ever stops reading high, the splitter is broken, not the world.
                if suffix in ("", "_levelnorm"):
                    rel_frames.append(split_half_reliability(fac, metrics).assign(
                        level=level, variant="league_normalised (headline)" if suffix == ""
                        else "level_normalised (POSITIVE CONTROL)"))
            pa = raw.groupby("player_id")["pa"].sum().rename("opp_context_pa").reset_index()
            pa["level"] = level
            frames.append(per_level.merge(pa, on=["player_id", "level"], how="left"))
    finally:
        conn.close()
    if not frames:
        return pd.DataFrame(), pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    out["player_id"] = out["player_id"].astype(str)
    rel = pd.concat(rel_frames, ignore_index=True) if rel_frames else pd.DataFrame()
    return out, rel


def league_variance_decomposition(ctx: pd.DataFrame, pairs: pd.DataFrame,
                                  metrics: tuple[str, ...]) -> pd.DataFrame:
    """⭐ **HOW MUCH OF THE OPPONENT FACTOR IS SOMETHING THE MODEL ALREADY KNOWS?**

    E7.3 fits a per-LEAGUE random intercept. Any part of the opponent factor that is constant within a
    league is therefore NOT new information — it is a re-encoding of a feature that already ships, and a
    lift on it would be unattributable to opponent quality. Measured on the live Triple-A substrate,
    45-62% of the level-normalised factor's variance is between-league (the Mexican League sits at 0.89
    on k_pct against the International League's 1.03), which is why the HEADLINE variant is
    league-normalised. This table is the evidence for that design choice, published rather than asserted.
    """
    if ctx.empty or "league" not in pairs.columns:
        return pd.DataFrame()
    j = ctx.merge(pairs[["player_id", "level", "league"]].assign(
        player_id=lambda d: d["player_id"].astype(str)), on=["player_id", "level"], how="left")
    j = j.dropna(subset=["league"])
    rows = []
    for m in metrics:
        for tag, col in (("level_normalised", f"of_{m}_exposure_levelnorm"),
                         ("league_normalised (headline)", f"of_{m}_exposure")):
            if col not in j.columns:
                continue
            v = pd.to_numeric(j[col], errors="coerce")
            v = np.log(v.where(v > 0)).dropna()
            if len(v) < 30:
                continue
            g = j.loc[v.index, "league"]
            tot = float(v.var(ddof=0))
            within = float(v.groupby(g).transform(lambda s: s - s.mean()).var(ddof=0))
            rows.append({
                "metric": m, "variant": tag,
                "total_sd_pct": round(100.0 * np.sqrt(tot), 3),
                "between_league_sd_pct": round(100.0 * np.sqrt(max(tot - within, 0.0)), 3),
                "within_league_sd_pct": round(100.0 * np.sqrt(within), 3),
                "between_league_share_pct": round(100.0 * (1 - within / tot), 1) if tot > 0 else None,
            })
    return pd.DataFrame(rows)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="E7.15 H2 — assemble the MiLB opponent-quality context")
    p.add_argument("--player-type", choices=["batter", "pitcher"], default="batter")
    p.add_argument("--levels", nargs="+", default=list(LEVEL_ORDER))
    p.add_argument("--season-floor", type=int, default=None)
    p.add_argument("--window", type=int, default=DEFAULT_OPP_WINDOW,
                   help="trailing seasons per opponent bucket (default 1 — team quality is a SEASON "
                        "property; 3 is the window the park slice's assertion assumed)")
    p.add_argument("--out-dir", default=str(_DEFAULT_OUT))
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")

    spec = reduced_spec(args.player_type)
    metrics = OPPONENT_METRICS[args.player_type]
    ctx, rel = build_opponent_context(tuple(args.levels), args.season_floor, args.window,
                                      args.player_type)
    if ctx.empty:
        log.error("no opponent context produced — check the level/season filters")
        return 1

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = spec.artifact_suffix
    name = f"mle_opponent_context{suffix}" + (f"_w{args.window}" if args.window != 1 else "")
    dest = out_dir / f"{name}.parquet"
    ctx.to_parquet(dest, index=False)
    log.info("wrote %s (%d rows, %d players)", dest, len(ctx), ctx["player_id"].nunique())

    # ⭐ THE PRIMARY DELIVERABLE — printed at build time so the assertion is measured even if the
    # bake-off never runs.
    spread = opponent_spread(ctx, metrics)
    print(f"\n=== OPPONENT-QUALITY SPREAD ({args.player_type}, window={args.window}) — the direct test "
          f"of build_park_context's 'the opponent mix averages out' assertion ===")
    print(spread.to_string(index=False) if not spread.empty else "  (no factors produced)")
    # ⚠️ A SPREAD WITHOUT A RELIABILITY SUPPORTS NO CLAIM IN EITHER DIRECTION. A per-player factor is an
    # average of noisy per-opponent estimates, so it has spread even when every player faced identical
    # competition. `sd_true = sd_observed · sqrt(reliability)` is the number the assertion is judged on.
    print(f"\n=== SPLIT-HALF RELIABILITY of the per-player opponent factor ({args.player_type}) — is "
          f"that spread REAL, or is it the estimator? ===")
    print(rel.to_string(index=False) if not rel.empty else "  (not estimable)")
    if not rel.empty and not spread.empty:
        r = (rel.groupby("metric")["reliability_spearman_brown"].mean().rename("reliability"))
        merged = spread.merge(r, on="metric", how="left")
        merged["sd_true_pct"] = (merged["sd_pct"] * merged["reliability"].clip(lower=0) ** 0.5).round(3)
        merged["p95_minus_p5_true_pct"] = (
            merged["p95_minus_p5_pct"] * merged["reliability"].clip(lower=0) ** 0.5).round(2)
        print("\n=== NOISE-CORRECTED SPREAD (what the assertion is actually judged on) ===")
        print(merged[["metric", "sd_pct", "reliability", "sd_true_pct",
                      "p95_minus_p5_pct", "p95_minus_p5_true_pct"]].to_string(index=False))
        spread = merged
    e73 = (_PROJECT_ROOT / "quant_sports_intel_models/baseball/edge_program/ablation_results"
           / ("e7_3p_artifacts" if args.player_type == "pitcher" else "e7_3_artifacts")
           / (f"mle_graduated_pairs{suffix}.parquet"))
    if e73.exists():
        dec = league_variance_decomposition(ctx, pd.read_parquet(e73), metrics)
        print(f"\n=== HOW MUCH OF THE FACTOR IS A LEAGUE EFFECT THE MODEL ALREADY HAS? "
              f"({args.player_type}) ===")
        print(dec.to_string(index=False) if not dec.empty else "  (not estimable)")
        dec.assign(player_type=args.player_type).to_csv(
            out_dir / f"e7_15_h2_league_decomposition{suffix}.csv", index=False)

    spread.assign(player_type=args.player_type, window=args.window).to_csv(
        out_dir / f"e7_15_h2_opponent_spread{suffix}.csv", index=False)
    if not rel.empty:
        rel.assign(player_type=args.player_type, window=args.window).to_csv(
            out_dir / f"e7_15_h2_opponent_reliability{suffix}.csv", index=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
