"""build_miss_distance_feature.py — Edge Program E13.2b (the EXPLORATORY half; lakehouse).

INC-13 shipped Savant `miss_distance` (whiff-severity: how far the bat missed the ball, populated
ONLY on swinging strikes). It is a genuinely NEW bat-tracking axis — so E13.2b tests it for
incremental lift over the v6/log5 baseline alongside the zone-matchup PROFILE features.

⚠️ DATA CONSTRAINT (INC-13): miss_distance is **2026-ONLY** — Savant did not backfill prior
seasons. So it CANNOT be multi-season purged-CV'd.

⚠️ HARNESS LIMITATION (proven E13.2b 2026-06-24): incremental_lift_eval's purged CV is
SEASON-walk-forward (it trains each eval-season fold on all PRIOR seasons). A single-season feature
therefore yields **n_eval=0** (no prior-season train fold) → the degeneracy guard fires INVALID —
this is NOT a signal null and NOT a build bug (the parquet builds at 100% coverage with real
variance). `--min-year 2025` does not help either: the feature is null on all 2025 train rows →
imputed to a constant → still degenerate. ⇒ This feature is **not evaluable in this harness until a
full prior season of miss_distance accrues (≈2027)**. Build is preserved for that re-run. Treat any
2026-only read as SUGGESTIVE only; do not draw a firm verdict from the thin sample.

Two game-grain features per side (game_pk-keyed, the E13.4 harness ingests via --feature-parquet):
  * <side>_starter_miss_induced — the side's STARTER's prior mean induced miss_distance
    (a deception / swing-and-miss-severity proxy; bigger ⇒ uglier whiffs ⇒ more K-suppression).
  * <side>_lineup_miss          — the side's first-time-through LINEUP's prior mean own-whiff
    miss_distance (how badly the side's hitters miss when they whiff).
Both EB-shrunk toward the as-of league mean (k pseudo-whiffs) so a 3-whiff sample can't spike, and
strictly leak-clean: a feature for a game on date D uses only whiffs with game_date < D.

RUNTIME: scans 2026 pitches from S3 — HAND THE FULL RUN TO THE OPERATOR (CLAUDE.md >1-min rule).
`--limit-games N` gives a fast smoke. Writes nothing to prod / no Snowflake.

Usage (operator):
    uv run python betting_ml/scripts/build_miss_distance_feature.py \
        --season 2026 --out artifacts/miss_distance_feature.parquet
    # then (NOTE --min-year 2026 — the feature is 2026-only):
    uv run python betting_ml/scripts/incremental_lift_eval.py --target perside_runs \
        --min-year 2026 --feature-parquet artifacts/miss_distance_feature.parquet \
        --add-features opp_starter_miss_induced,off_lineup_miss --run-name e13_2b_miss_distance
    uv run python betting_ml/scripts/incremental_lift_eval.py --target home_win \
        --min-year 2026 --feature-parquet artifacts/miss_distance_feature.parquet \
        --add-features home_starter_miss_induced,away_starter_miss_induced,home_lineup_miss,away_lineup_miss \
        --run-name e13_2b_miss_distance
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from betting_ml.scripts.zone_matchup import lakehouse

K_MISS = 30.0   # EB pseudo-whiffs: shrink a thin prior sample toward the as-of league mean


def _daily(con, season: int, entity: str) -> pd.DataFrame:
    """Per (<entity>_id, game_date) whiff count + summed miss_distance for the season (whiffs =
    rows with a non-null miss_distance — it is populated only on swinging strikes)."""
    glob = lakehouse._read([season])
    sql = f"""
        SELECT {entity}_id AS id, game_date::date AS game_date,
               count(*) AS n, sum(try_cast(miss_distance AS DOUBLE)) AS s
        FROM read_parquet({glob}, union_by_name=true, hive_partitioning=false)
        WHERE game_year = {season} AND game_type = 'R'
          AND {entity}_id IS NOT NULL
          AND try_cast(miss_distance AS DOUBLE) IS NOT NULL
        GROUP BY 1, 2
    """
    return con.execute(sql).fetchdf()


def _asof_prior_mean(daily: pd.DataFrame, targets: pd.DataFrame, league_daily: pd.DataFrame,
                     out_col: str) -> pd.DataFrame:
    """Leak-clean prior mean for each (id, game_date) in `targets`: EB-shrink the cumulative
    miss_distance over that id's whiffs STRICTLY BEFORE game_date toward the as-of league mean.

    daily/targets/league_daily all carry game_date as datetime64. merge_asof(direction=backward,
    allow_exact_matches=False) picks the latest row with date < the target date, whose INCLUSIVE
    cumulative therefore covers exactly the whiffs before the game."""
    d = daily.sort_values("game_date").copy()
    d["cum_n"] = d.groupby("id")["n"].cumsum()
    d["cum_s"] = d.groupby("id")["s"].cumsum()

    lg = league_daily.sort_values("game_date").copy()
    lg["lg_cum_n"] = lg["n"].cumsum()
    lg["lg_cum_s"] = lg["s"].cumsum()
    lg["lg_mean"] = lg["lg_cum_s"] / lg["lg_cum_n"].replace(0, np.nan)
    lg = lg[["game_date", "lg_mean"]]

    tg = targets.sort_values("game_date").copy()
    # per-id as-of cumulative (strictly before the game date)
    parts = []
    for _id, grp in tg.groupby("id", sort=False):
        di = d[d["id"] == _id][["game_date", "cum_n", "cum_s"]]
        if di.empty:
            g2 = grp.copy()
            g2["cum_n"] = 0.0
            g2["cum_s"] = np.nan
            parts.append(g2)
            continue
        m = pd.merge_asof(grp.sort_values("game_date"), di, on="game_date",
                          direction="backward", allow_exact_matches=False)
        parts.append(m)
    merged = pd.concat(parts, ignore_index=True)
    merged["cum_n"] = merged["cum_n"].fillna(0.0)

    # as-of league mean (strictly before the game date)
    merged = pd.merge_asof(merged.sort_values("game_date"), lg, on="game_date",
                           direction="backward", allow_exact_matches=False)
    prior = merged["lg_mean"].to_numpy(float)
    prior = np.where(np.isnan(prior), np.nanmean(prior), prior)  # earliest games → season-edge fill
    raw = (merged["cum_s"] / merged["cum_n"].replace(0, np.nan)).to_numpy(float)
    # EB shrink toward the PER-ROW as-of league mean (eb_shrink_toward_mean only takes a scalar
    # prior, so apply its `(n·raw + k·prior)/(n+k)` form directly with the per-row prior):
    n = merged["cum_n"].to_numpy(float)
    merged[out_col] = (n * np.where(np.isnan(raw), 0.0, raw) + K_MISS * prior) / (n + K_MISS)
    return merged[["id", "game_date", out_col]]


def _starters_lineups(con, season: int):
    """game_pk, game_date, each side's starter + first-3-innings lineup (reuses the leak-clean
    lakehouse proxy; adds game_date for the as-of join)."""
    glob = lakehouse._read([season])
    common = (f"FROM read_parquet({glob}, union_by_name=true, hive_partitioning=false) "
              f"WHERE game_year = {season} AND game_type = 'R'")
    starters = con.execute(f"""
        WITH p1 AS (
            SELECT game_pk, game_date::date AS game_date,
                   CASE WHEN inning_half = 'Top' THEN 'home' ELSE 'away' END AS side,
                   pitcher_id,
                   row_number() OVER (PARTITION BY game_pk,
                       CASE WHEN inning_half = 'Top' THEN 'home' ELSE 'away' END
                       ORDER BY at_bat_number, pitch_number) AS rn
            {common} AND inning = 1 AND pitcher_id IS NOT NULL)
        SELECT game_pk, game_date, side, pitcher_id FROM p1 WHERE rn = 1
    """).fetchdf()
    lineups = con.execute(f"""
        SELECT DISTINCT game_pk, game_date::date AS game_date,
               CASE WHEN inning_half = 'Top' THEN 'away' ELSE 'home' END AS side,
               batter_id
        {common} AND inning <= 3 AND batter_id IS NOT NULL
    """).fetchdf()
    return starters, lineups


def main() -> None:
    ap = argparse.ArgumentParser(description="E13.2b miss_distance whiff-severity feature (2026-only)")
    ap.add_argument("--season", type=int, default=2026, help="2026-only by data constraint (INC-13)")
    ap.add_argument("--out", required=True, help="output parquet (game_pk-keyed)")
    ap.add_argument("--limit-games", type=int, default=0, help="smoke: only first N games")
    args = ap.parse_args()

    if args.season != 2026:
        print(f"  [warn] miss_distance is 2026-only (INC-13); season={args.season} will be empty.")

    con = lakehouse.connect()
    print(f"season {args.season}: reading whiff miss_distance + starters/lineups from S3 ...")
    p_daily = _daily(con, args.season, "pitcher")
    b_daily = _daily(con, args.season, "batter")
    lg_daily = (pd.concat([p_daily[["game_date", "n", "s"]]])
                .groupby("game_date", as_index=False).sum())
    starters, lineups = _starters_lineups(con, args.season)
    con.close()

    for df in (p_daily, b_daily, lg_daily, starters, lineups):
        df["game_date"] = pd.to_datetime(df["game_date"])

    if args.limit_games:
        keep = starters["game_pk"].drop_duplicates().head(args.limit_games)
        starters = starters[starters["game_pk"].isin(keep)]
        lineups = lineups[lineups["game_pk"].isin(keep)]
    print(f"  pitcher-days:{len(p_daily)}  batter-days:{len(b_daily)}  "
          f"games:{starters['game_pk'].nunique()}")

    # Starter induced-miss (per pitcher, as-of). targets keyed by (id=pitcher_id, game_date).
    s_tgt = starters.rename(columns={"pitcher_id": "id"})[["id", "game_date"]].drop_duplicates()
    s_feat = _asof_prior_mean(p_daily, s_tgt, lg_daily, "starter_miss_induced")
    starters = starters.merge(s_feat.rename(columns={"id": "pitcher_id"}),
                              on=["pitcher_id", "game_date"], how="left")
    st_wide = starters.pivot_table(index="game_pk", columns="side",
                                   values="starter_miss_induced", aggfunc="first")
    st_wide.columns = [f"{c}_starter_miss_induced" for c in st_wide.columns]

    # Lineup own-miss (per batter, as-of) → side mean.
    b_tgt = lineups.rename(columns={"batter_id": "id"})[["id", "game_date"]].drop_duplicates()
    b_feat = _asof_prior_mean(b_daily, b_tgt, lg_daily, "batter_miss")
    lineups = lineups.merge(b_feat.rename(columns={"id": "batter_id"}),
                            on=["batter_id", "game_date"], how="left")
    lu_side = (lineups.groupby(["game_pk", "side"])["batter_miss"].mean().reset_index())
    lu_wide = lu_side.pivot(index="game_pk", columns="side", values="batter_miss")
    lu_wide.columns = [f"{c}_lineup_miss" for c in lu_wide.columns]

    out = (st_wide.join(lu_wide, how="outer").reset_index())
    out["season"] = args.season
    for c in ["home_starter_miss_induced", "away_starter_miss_induced",
              "home_lineup_miss", "away_lineup_miss"]:
        if c not in out.columns:
            out[c] = np.nan

    outp = Path(args.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(outp, index=False)
    print(f"\nwrote per-game miss_distance feature ({len(out)} games) → {outp}")
    cov = out[["home_starter_miss_induced", "home_lineup_miss"]].notna().mean()
    print(f"  coverage — starter:{cov['home_starter_miss_induced']:.1%}  "
          f"lineup:{cov['home_lineup_miss']:.1%}")
    print("⚠️  2026-ONLY / underpowered — run the harness with --min-year 2026; "
          "treat any verdict as SUGGESTIVE (no historical fold).")


if __name__ == "__main__":
    main()
