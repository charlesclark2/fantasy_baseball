"""
parity_check_w7a_matchup.py   (E11.1-W7a — matchup-signal consumer read parity)
-------------------------------------------------------------------------------
W7a adds an `--s3` read mode to the four matchup-signal consumer scripts so they READ
their source tables (batter_clusters / pitcher_clusters / mart_player_archetype_posteriors /
mart_pitch_play_event / mart_batter_archetype_vs_pitcher_cluster / the games spine) from S3
parquet via DuckDB instead of Snowflake — while their WRITES stay on Snowflake. This check
runs each consumer's KEY READ query BOTH ways (Snowflake vs DuckDB-S3) and compares row counts
plus a sample of values, so the operator can trust the --s3 reads before flipping the daily
pipeline / decommissioning the Snowflake cluster + posterior builds.

Like the rest of the lakehouse waves, the S3 pitch substrate is a SUPERSET of Snowflake on the
current in-flight season (freshness), so for season-scoped reads we gate `DuckDB >= Snowflake`
rather than exact-equal, and we compare VALUES only on keys present in BOTH (non-freshness rows).
The cluster / posterior / games reads ARE expected to match closely (the parquet is a 1:1 export).

⚠️ This mirrors the read SQL in the four consumer scripts. If you change a query there, mirror it
here (the SQL constants are imported from the scripts where importable; the DuckDB rewrites reuse
each script's own `_duck_sql_for`).

Run (after the S3 source parquet exist):
  uv run python scripts/parity_check_w7a_matchup.py --season 2025
  uv run python scripts/parity_check_w7a_matchup.py --date 2026-06-01 --check pa
  uv run python scripts/parity_check_w7a_matchup.py --season 2025 --check cells
"""

import argparse
import os
import sys
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd
import snowflake.connector
from dotenv import load_dotenv

load_dotenv()

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))

# Reuse the consumer scripts' OWN read SQL + DuckDB rewrites — single source of truth.
from betting_ml.scripts.eb_priors.generate_matchup_signals import (
    _CELL_HARD_SQL,
    _CELL_SOFT_SQL,
    _POSTERIORS_SQL,
    _duck_sql_for as _gms_duck_sql_for,
    _register_s3_views as _gms_register_s3_views,
)
# NOTE (E11.1-W7a): _GAMES_SQL is NOT parity-checked — its two staging joins
# (stg_statsapi_probable_pitchers / stg_statsapi_lineups_wide) are NOT in the S3 lakehouse, so
# the games spine stays on Snowflake in --s3 mode (mart_game_results there is a lakehouse_ext
# view). There's no S3 read to compare against. The credit-drop tables (clusters/posteriors) and
# the pitch substrate ARE parity-checked below.
from betting_ml.scripts.sequential_bayes.update_matchup_cell_posteriors import (
    _PA_SQL,
    _PA_SEASON_SQL,
)
from betting_ml.scripts.eb_priors.fit_archetype_priors import (
    _BATTER_ROWS_SQL,
    _duck_sql_for as _fit_duck_sql_for,
    _register_s3_views as _fit_register_s3_views,
    _FIRST_SEASON,
)

# Tolerance bands
_TOL_ROWS_FRAC = 0.999   # season-scoped: DuckDB >= Snowflake * this (freshness ⇒ DuckDB ⊇ SF)
_TOL_MEAN_ABS  = 0.005   # mean |Δ| on a joined numeric value column


# ── Connections (house style, from parity_check_w5b.py) ───────────────────────

def get_sf():
    # INC-22 straggler cure (2026-07-05): the box authenticates via the INLINE key
    # (SNOWFLAKE_PRIVATE_KEY), NOT a key FILE, and has NO SNOWFLAKE_PASSWORD — the old
    # file-path→password resolver KeyError'd on the box. Delegate to the shared resolver.
    from betting_ml.utils.data_loader import get_snowflake_connection
    return get_snowflake_connection(schema="betting")


def get_duck():
    c = duckdb.connect()
    c.execute("INSTALL httpfs; LOAD httpfs")
    c.execute("CREATE OR REPLACE SECRET baseball_s3 (TYPE S3, PROVIDER credential_chain, REGION 'us-east-2')")
    for p in ("SET http_timeout=600000", "SET http_retries=8", "SET preserve_insertion_order=false"):
        try:
            c.execute(p)
        except Exception:
            pass
    # Register every source view both consumers read (the generate_matchup_signals set is a
    # superset; the fit set adds nothing new but registering twice is harmless / idempotent).
    _gms_register_s3_views(c)
    _fit_register_s3_views(c)
    return c


def _sf_df(sf, sql: str, params=None) -> pd.DataFrame:
    cur = sf.cursor()
    cur.execute(sql, params or {})
    df = pd.DataFrame(cur.fetchall(), columns=[d[0].lower() for d in cur.description])
    cur.close()
    return df


def _duck_df(duck, sql: str) -> pd.DataFrame:
    cur = duck.execute(sql)
    return pd.DataFrame(cur.fetchall(), columns=[d[0].lower() for d in cur.description])


def _row_line(label: str, sf_n: int, duck_n: int, superset: bool) -> bool:
    if superset:
        ok = duck_n >= sf_n * _TOL_ROWS_FRAC
        note = "(DuckDB ⊇ Snowflake expected — pitch-substrate freshness)"
    else:
        ok = abs(duck_n - sf_n) <= max(1, sf_n * (1 - _TOL_ROWS_FRAC))
        note = "(1:1 export expected)"
    print(f"  rows   {'✅' if ok else '❌'}  {label}  Snowflake={sf_n:,}  DuckDB={duck_n:,}  {note}")
    return ok


# ── Consumer 1/2: hard-MAP + soft cell reads (generate_matchup_signals, build_matchup_training_data) ──

def check_cells(duck, sf, season: int) -> bool:
    print(f"\n── cell-feature reads (_CELL_HARD_SQL / _CELL_SOFT_SQL)  season={season} ──")
    ok = True

    # Hard MAP (mart_pitch_play_event + batter/pitcher_clusters + stg_batter_pitches)
    sf_hard = _sf_df(sf, _CELL_HARD_SQL, {"season": season})
    duck_hard = _duck_df(duck, _gms_duck_sql_for(_CELL_HARD_SQL).replace("%(season)s", str(int(season))))
    ok &= _row_line("hard-cells", len(sf_hard), len(duck_hard), superset=False)

    # Both should expose the same set of (batter, pitcher) label pairs.
    sf_pairs = {(r.batter_cluster_label, r.pitcher_cluster_label) for r in sf_hard.itertuples()}
    duck_pairs = {(r.batter_cluster_label, r.pitcher_cluster_label) for r in duck_hard.itertuples()}
    grid_ok = sf_pairs == duck_pairs
    print(f"  grid   {'✅' if grid_ok else '❌'}  label-pairs  Snowflake={len(sf_pairs)}  DuckDB={len(duck_pairs)}"
          + ("" if grid_ok else f"  only-SF={sf_pairs - duck_pairs}  only-Duck={duck_pairs - sf_pairs}"))
    ok &= grid_ok

    # Joined-key value drift on hard_xwoba_mean (engine float precision wisp expected).
    j = sf_hard.merge(duck_hard, on=["batter_cluster_label", "pitcher_cluster_label"],
                      suffixes=("_sf", "_duck"))
    if len(j):
        d_xw = (j["hard_xwoba_mean_sf"].astype(float) - j["hard_xwoba_mean_duck"].astype(float)).abs()
        d_k  = (j["k_pct_sf"].astype(float) - j["k_pct_duck"].astype(float)).abs()
        val_ok = d_xw.mean() <= _TOL_MEAN_ABS and d_k.mean() <= _TOL_MEAN_ABS
        print(f"  value  {'✅' if val_ok else '❌'}  joined={len(j)}  mean|Δhard_xwoba|={d_xw.mean():.6f} "
              f"max={d_xw.max():.6f}  mean|Δk_pct|={d_k.mean():.6f}  (≤{_TOL_MEAN_ABS})")
        ok &= val_ok

    # Soft (mart_batter_archetype_vs_pitcher_cluster)
    sf_soft = _sf_df(sf, _CELL_SOFT_SQL, {"season": season})
    duck_soft = _duck_df(duck, _gms_duck_sql_for(_CELL_SOFT_SQL).replace("%(season)s", str(int(season))))
    ok &= _row_line("soft-cells", len(sf_soft), len(duck_soft), superset=False)
    return ok


# ── Consumer 1: archetype posteriors (generate_matchup_signals) ───────────────

def check_posteriors(duck, sf, season: int) -> bool:
    print(f"\n── archetype-posteriors read (_POSTERIORS_SQL)  season={season} ──")
    sf_p = _sf_df(sf, _POSTERIORS_SQL, {"season": season})
    duck_p = _duck_df(duck, _gms_duck_sql_for(_POSTERIORS_SQL).replace("%(season)s", str(int(season))))
    ok = _row_line("posteriors", len(sf_p), len(duck_p), superset=True)

    # MAP-cluster agreement on shared PK (player_id, player_type, as_of_date).
    sf_p["k"] = sf_p["player_id"].astype(str) + "|" + sf_p["player_type"] + "|" + sf_p["as_of_date"].astype(str)
    duck_p["k"] = duck_p["player_id"].astype(str) + "|" + duck_p["player_type"] + "|" + duck_p["as_of_date"].astype(str)
    j = sf_p.merge(duck_p, on="k", suffixes=("_sf", "_duck"))
    if len(j):
        agree = (j["map_cluster_sf"] == j["map_cluster_duck"]).mean()
        agree_ok = agree >= 0.98
        print(f"  map    {'✅' if agree_ok else '❌'}  joined={len(j):,}  MAP-cluster agreement={agree:.3%} (≥98%)")
        ok &= agree_ok
    return ok


# ── Consumer 4: PA substrate (update_matchup_cell_posteriors) ─────────────────

def check_pa(duck, sf, target_date: date) -> bool:
    print(f"\n── PA-substrate read (_PA_SQL)  date={target_date} ──")
    sf_pa = _sf_df(sf, _PA_SQL, {"game_date": target_date.isoformat()})
    # _PA_SQL has no fully-qualified rewrite collisions handled by _gms_duck_sql_for beyond table
    # names; the named %(game_date)s param is substituted to a quoted literal here.
    duck_sql = _gms_duck_sql_for(_PA_SQL).replace("%(game_date)s", f"'{target_date.isoformat()}'")
    duck_pa = _duck_df(duck, duck_sql)
    ok = _row_line("PA-rows", len(sf_pa), len(duck_pa), superset=True)

    if len(sf_pa) and len(duck_pa):
        sf_mean = sf_pa["xwoba"].astype(float).mean()
        duck_mean = duck_pa["xwoba"].astype(float).mean()
        dist_ok = abs(sf_mean - duck_mean) <= _TOL_MEAN_ABS
        print(f"  dist   {'✅' if dist_ok else '❌'}  mean(xwoba)  Snowflake={sf_mean:.5f}  "
              f"DuckDB={duck_mean:.5f}  |Δ|={abs(sf_mean - duck_mean):.5f} (≤{_TOL_MEAN_ABS})")
        ok &= dist_ok
    return ok


def check_pa_dates(duck, sf, season: int) -> bool:
    print(f"\n── PA game-dates read (_PA_SEASON_SQL)  season={season} ──")
    sf_d = _sf_df(sf, _PA_SEASON_SQL, {"season": season})
    duck_d = _duck_df(duck, _gms_duck_sql_for(_PA_SEASON_SQL).replace("%(season)s", str(int(season))))
    return _row_line("game-dates", len(sf_d), len(duck_d), superset=True)


# ── Consumer 3: fit-priors cluster + profile read ─────────────────────────────

def check_fit_priors(duck, sf) -> bool:
    print(f"\n── fit-archetype-priors read (_BATTER_ROWS_SQL, batter_clusters ⋈ profiles)  season≥{_FIRST_SEASON} ──")
    sf_b = _sf_df(sf, _BATTER_ROWS_SQL, {"first_season": _FIRST_SEASON})
    duck_b = _duck_df(duck, _fit_duck_sql_for(_BATTER_ROWS_SQL).replace("%(first_season)s", str(int(_FIRST_SEASON))))
    ok = _row_line("batter-cluster-seasons", len(sf_b), len(duck_b), superset=False)

    # birth_date join completeness should match (LEFT JOIN profiles).
    sf_bd = sf_b["birth_date"].notna().mean() if len(sf_b) else 0.0
    duck_bd = duck_b["birth_date"].notna().mean() if len(duck_b) else 0.0
    bd_ok = abs(sf_bd - duck_bd) <= 0.01
    print(f"  join   {'✅' if bd_ok else '❌'}  birth_date non-null  Snowflake={sf_bd:.3%}  DuckDB={duck_bd:.3%}")
    return ok and bd_ok


# ── Main ──────────────────────────────────────────────────────────────────────

_CHECKS = ["cells", "posteriors", "pa", "pa_dates", "fit_priors"]


def main():
    ap = argparse.ArgumentParser(description="E11.1-W7a matchup-consumer read parity (Snowflake vs DuckDB-S3)")
    ap.add_argument("--season", type=int, default=2025,
                    help="Season for season-scoped reads (cells / posteriors / pa_dates / fit_priors).")
    ap.add_argument("--date", help="Date (YYYY-MM-DD) for the PA-substrate read; default = season opener-ish.")
    ap.add_argument("--check", choices=_CHECKS + ["all"], default="all")
    args = ap.parse_args()

    season = args.season
    if args.date:
        target_date = date.fromisoformat(args.date)
    else:
        target_date = date(season, 6, 1)  # mid-season default with PA volume
    start_date = f"{season}-01-01"
    end_date = f"{season}-12-31"

    duck = get_duck()
    sf = get_sf()

    runners = {
        "cells":      lambda: check_cells(duck, sf, season),
        "posteriors": lambda: check_posteriors(duck, sf, season),
        "pa":         lambda: check_pa(duck, sf, target_date),
        "pa_dates":   lambda: check_pa_dates(duck, sf, season),
        "fit_priors": lambda: check_fit_priors(duck, sf),
    }
    to_run = _CHECKS if args.check == "all" else [args.check]

    ok = True
    for name in to_run:
        try:
            ok &= runners[name]()
        except Exception as e:
            print(f"\n❌ {name}: raised {type(e).__name__}: {e}")
            ok = False

    sf.close()
    duck.close()

    print("\n── Summary ──")
    if ok:
        print("✅ W7a matchup-consumer reads within tolerance — safe to flip the consumers to --s3.")
    else:
        print("❌ W7a matchup-consumer reads OUTSIDE tolerance — investigate before cutover.")
        sys.exit(1)


if __name__ == "__main__":
    main()
