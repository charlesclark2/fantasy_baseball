"""build_zone_matchup.py — Edge Program E13.10 operator CLI (lakehouse; NOT Snowflake).

Builds the leak-clean batter/pitcher zone profiles ONCE, then serves both deliverables:

  profiles  Build batter-value + pitcher-usage + league profiles for a leak window [start, end)
            and write them to local parquet (and optionally S3). `end` is the as-of leak boundary.
  viz       TRACK A — render the marketable matchup OVERLAY (JSON spec + static PNG proof) for
            one or more batter×pitcher matchups, from already-built profiles.
  feature   TRACK B — build the per-game zone-overlap scalar (home/away_zone_overlap) for one or
            more seasons (each season profiled from PRIOR seasons only ⇒ strictly leak-clean) and
            write a game_pk-keyed parquet the E13.4 lift harness ingests via --feature-parquet.

RUNTIME: the profile/feature reads scan millions of pitches from S3 — HAND THE FULL RUNS TO THE
OPERATOR (CLAUDE.md >1-min rule). `--sample-days N` (profiles/viz) and `--limit-games N`
(feature) give fast smoke modes for verification. Writes nothing to prod / no Snowflake.

Usage:
    # smoke (fast — a 2-week window):
    uv run python betting_ml/scripts/build_zone_matchup.py profiles \
        --start 2026-06-06 --end 2026-06-20 --out-dir /tmp/zm
    uv run python betting_ml/scripts/build_zone_matchup.py viz --profiles-dir /tmp/zm --top 6

    # full profiles as-of today (operator):
    uv run python betting_ml/scripts/build_zone_matchup.py profiles \
        --start 2023-01-01 --end 2026-06-24 --out-dir artifacts/zm_2026 --s3
    # full Track-B feature for the lift test (operator):
    uv run python betting_ml/scripts/build_zone_matchup.py feature \
        --seasons 2021,2022,2023,2024,2025,2026 --window-seasons 3 \
        --out artifacts/zone_overlap_feature.parquet
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from betting_ml.scripts.zone_matchup import lakehouse, overlap, profiles, viz
from betting_ml.scripts.zone_matchup.grid import GridSpec

_S3_ZM = f"{lakehouse.BUCKET}/zone_matchup"                       # profile parquet (lakehouse)
_S3_BUCKET = "baseball-betting-ml-artifacts"
_S3_OVERLAY_PREFIX = "baseball/serving/zone_matchup/overlay"      # JSON = the served product
_S3_PROOF_PREFIX = "baseball/artifacts/zone_matchup_proofs"       # PNG = research proof only


def _s3_put(key: str, body: bytes, content_type: str) -> str:
    import boto3
    boto3.client("s3", region_name="us-east-2").put_object(
        Bucket=_S3_BUCKET, Key=key, Body=body, ContentType=content_type)
    return f"s3://{_S3_BUCKET}/{key}"


# ──────────────────────────────────────────────────────────────────────────────
def _player_names(con, ids: list[int]) -> dict:
    """Best-effort id→name from stg_ref_players in S3 (None on any failure — names are cosmetic)."""
    if not ids:
        return {}
    try:
        glob = f"{lakehouse.BUCKET}/stg_ref_players/**/*.parquet"
        df = con.execute(
            f"SELECT * FROM read_parquet('{glob}', union_by_name=true) LIMIT 1").fetchdf()
        cols = {c.lower(): c for c in df.columns}
        idc = next((cols[c] for c in ("mlb_bam_id", "player_id", "mlbam_id", "mlb_id",
                                      "key_mlbam", "id") if c in cols), None)
        if not idc:
            return {}
        if "first_name" in cols and "last_name" in cols:
            namesel = f"trim({cols['first_name']} || ' ' || {cols['last_name']})"
        else:
            namec = next((cols[c] for c in cols if "name" in c), None)
            if not namec:
                return {}
            namesel = namec
        idlist = ",".join(str(int(i)) for i in ids)
        nm = con.execute(
            f"SELECT {idc} AS id, {namesel} AS nm FROM read_parquet('{glob}', union_by_name=true) "
            f"WHERE {idc} IN ({idlist})").fetchdf()
        return {int(r.id): r.nm for r in nm.itertuples() if r.nm}
    except Exception as e:  # noqa: BLE001 — names are cosmetic; never block the build
        print(f"  [names] skipped ({e})")
        return {}


def _build_profiles(con, grid: GridSpec, window: lakehouse.Window):
    print(f"  reading pitch window [{window.start}, {window.end}) from S3 ...")
    league = lakehouse.league_raw(con, grid, window)
    braw = lakehouse.batter_raw(con, grid, window)
    praw = lakehouse.pitcher_raw(con, grid, window)
    print(f"  raw rows — league:{len(league)}  batter:{len(braw)}  pitcher:{len(praw)}")
    bval = profiles.build_batter_value(braw, league, grid=grid)
    pfreq = profiles.build_pitcher_freq(praw, league)
    zbounds = lakehouse.batter_zone_bounds(con, window)
    print(f"  profiles — batter_value:{len(bval)}  pitcher_freq:{len(pfreq)}  "
          f"zone_bounds:{len(zbounds)}  "
          f"(batters cold:{bval.groupby('batter_id')['is_cold_start'].any().sum()}, "
          f"pitchers cold:{pfreq.groupby('pitcher_id')['is_cold_start'].any().sum()})")
    return bval, pfreq, league, zbounds


def cmd_profiles(args) -> None:
    grid = GridSpec()
    end = args.end
    start = args.start
    if args.sample_days:
        # smoke: shrink the window to the last N days before `end`
        start = (pd.to_datetime(end) - pd.Timedelta(days=args.sample_days)).strftime("%Y-%m-%d")
        print(f"  [sample] window narrowed to last {args.sample_days}d: [{start}, {end})")
    con = lakehouse.connect()
    bval, pfreq, league, zbounds = _build_profiles(con, grid, lakehouse.Window(start, end))

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    bval.to_parquet(out / "batter_value.parquet", index=False)
    pfreq.to_parquet(out / "pitcher_freq.parquet", index=False)
    league.to_parquet(out / "league_raw.parquet", index=False)
    zbounds.to_parquet(out / "batter_zone.parquet", index=False)
    (out / "_meta.json").write_text(
        f'{{"start": "{start}", "end": "{end}", "grid_nx": {grid.nx}, "grid_nz": {grid.nz}}}')
    print(f"  wrote profiles → {out}")
    if args.s3:
        for name, df in (("batter_value", bval), ("pitcher_freq", pfreq),
                         ("league_raw", league), ("batter_zone", zbounds)):
            loc = f"{_S3_ZM}/{name}/as_of={end}/data.parquet"
            con.execute(f"COPY (SELECT * FROM df) TO '{loc}' (FORMAT PARQUET)")
            print(f"  s3 ← {loc}")
    con.close()


def cmd_viz(args) -> None:
    grid = GridSpec()
    pdir = Path(args.profiles_dir)
    bval = pd.read_parquet(pdir / "batter_value.parquet")
    pfreq = pd.read_parquet(pdir / "pitcher_freq.parquet")
    zb = pd.read_parquet(pdir / "batter_zone.parquet") if (pdir / "batter_zone.parquet").exists() \
        else pd.DataFrame(columns=["batter_id", "sz_top", "sz_bot"])
    sz_map = {int(r.batter_id): (r.sz_top, r.sz_bot) for r in zb.itertuples()}
    import json as _json
    meta = _json.loads((pdir / "_meta.json").read_text())
    as_of = meta["end"]

    if args.batter and args.pitcher:
        b_hand = _hand_of(bval, "batter_id", args.batter)
        p_hand = _hand_of(pfreq, "pitcher_id", args.pitcher, hand_col="p_hand")
        matchups = [(args.batter, b_hand, args.pitcher, p_hand)]
    else:
        matchups = _top_matchups(bval, pfreq, top=args.top)

    con = lakehouse.connect()
    ids = sorted({m[0] for m in matchups} | {m[2] for m in matchups})
    names = _player_names(con, ids)
    con.close()

    local = Path(args.local_dir) if args.local_dir else None
    if local:
        local.mkdir(parents=True, exist_ok=True)
    do_s3 = not args.no_s3
    for (bid, bh, pid, ph) in matchups:
        sz_top, sz_bot = sz_map.get(bid, (None, None))
        ov = viz.build_overlay(bval, pfreq, batter_id=bid, b_hand=bh, pitcher_id=pid, p_hand=ph,
                               grid=grid, as_of_date=as_of, sz_top=sz_top, sz_bot=sz_bot,
                               batter_name=names.get(bid), pitcher_name=names.get(pid))
        stem = f"{bid}_vs_{pid}"
        # JSON = the served product → S3 serving prefix, partitioned by as-of date + matchup.
        if do_s3:
            jkey = f"{_S3_OVERLAY_PREFIX}/as_of={as_of}/{stem}.json"
            print(f"  json → {_s3_put(jkey, _json.dumps(ov).encode(), 'application/json')}")
        if local:
            viz.write_overlay_json(ov, local / f"overlay_{stem}.json")
        # PNG = research proof only → S3 artifact prefix (NOT git, NOT user-served).
        if do_s3 or local:
            png_local = (local / f"proof_{stem}.png") if local \
                else Path(args.tmp_dir or ".") / f"proof_{stem}.png"
            viz.render_overlay_png(ov, png_local)
            if do_s3:
                pkey = f"{_S3_PROOF_PREFIX}/as_of={as_of}/{stem}.png"
                print(f"  proof → {_s3_put(pkey, png_local.read_bytes(), 'image/png')}")
        print(f"  {stem}: overlap={ov.get('overlap_scalar')}  cold={ov['is_cold_start']}")
    print(f"  done: {len(matchups)} matchups (JSON=product/serving-S3, PNG=proof/artifact-S3)")


def _hand_of(df, id_col, val, hand_col=None):
    hand_col = hand_col or ("b_hand" if id_col == "batter_id" else "p_hand")
    sub = df[df[id_col] == val]
    return sub[hand_col].mode().iloc[0] if not sub.empty else "R"


def _top_matchups(bval, pfreq, top=6):
    """Heuristic showcase set: pair high-volume non-cold batters with high-volume non-cold
    starters and rank by |overlap| so the proof shows visually distinct, data-rich overlays."""
    b_tot = (bval.groupby(["batter_id", "b_hand"])["n_pitches"].sum().reset_index()
             .sort_values("n_pitches", ascending=False))
    p_tot = (pfreq[~pfreq["is_cold_start"]].groupby(["pitcher_id", "p_hand"])["n_pitches"].sum()
             .reset_index().sort_values("n_pitches", ascending=False))
    b_top = b_tot.head(40)
    p_top = p_tot.head(20)
    pairs = b_top.assign(_k=1).merge(p_top.assign(_k=1), on="_k").drop(columns="_k")
    pairs = pairs.rename(columns={"batter_id": "batter_id", "pitcher_id": "pitcher_id"})
    ov = overlap.compute_overlap(
        bval, pfreq,
        pairs[["batter_id", "b_hand", "pitcher_id", "p_hand"]].copy())
    ov = ov[ov["overlap"].notna() & (ov["overlap_cells"] >= 10)]
    ov["absov"] = ov["overlap"].abs()
    ov = ov.sort_values("absov", ascending=False).head(top)
    return [(int(r.batter_id), r.b_hand, int(r.pitcher_id), r.p_hand) for r in ov.itertuples()]


def cmd_feature(args) -> None:
    grid = GridSpec()
    seasons = [int(s) for s in args.seasons.split(",") if s.strip()]
    con = lakehouse.connect()
    all_games = []
    for season in seasons:
        win = lakehouse.Window(f"{season - args.window_seasons}-01-01", f"{season}-01-01")
        print(f"season {season}: profiling prior window [{win.start}, {win.end}) ...")
        bval, pfreq, _, _ = _build_profiles(con, grid, win)
        lineups, starters = lakehouse.lineups_and_starters(con, season)
        if args.limit_games:
            keep = lineups["game_pk"].drop_duplicates().head(args.limit_games)
            lineups = lineups[lineups["game_pk"].isin(keep)]
            starters = starters[starters["game_pk"].isin(keep)]
        if args.rich:
            feat = overlap.game_side_profile_features(lineups, starters, bval, pfreq)
            cov_col = "home_zone_value"
        else:
            feat = overlap.game_side_overlap(lineups, starters, bval, pfreq)
            cov_col = "home_zone_overlap"
        feat["season"] = season
        print(f"  games with overlap: {feat[cov_col].notna().sum()} / {len(feat)}")
        all_games.append(feat)
    con.close()

    out_df = pd.concat(all_games, ignore_index=True) if all_games else pd.DataFrame()
    outp = Path(args.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_parquet(outp, index=False)
    if args.rich:
        # E13.2b — the decomposed PROFILE channels (the richer form the E13.10 scalar collapsed).
        chans = overlap.PROFILE_CHANNELS
        print(f"\nwrote per-game zone-PROFILE features ({len(out_df)} games, "
              f"{len(chans)} channels × 2 sides) → {outp}")
        print("Harness wiring (operator) — test the NEW channels (zone_value≈the already-null scalar):")
        new = [c for c in chans if c != "zone_value"]
        print(f"  uv run python betting_ml/scripts/incremental_lift_eval.py --target perside_runs \\")
        print(f"      --feature-parquet {outp} \\")
        print(f"      --add-features {','.join('off_' + c for c in new)} --run-name e13_2b_zone_profile")
        print(f"  uv run python betting_ml/scripts/incremental_lift_eval.py --target home_win \\")
        print(f"      --feature-parquet {outp} \\")
        print(f"      --add-features {','.join(f'home_{c},away_{c}' for c in new)} \\")
        print(f"      --run-name e13_2b_zone_profile")
        return
    print(f"\nwrote per-game zone-overlap feature ({len(out_df)} games) → {outp}")
    print("Harness wiring (operator):")
    print(f"  uv run python betting_ml/scripts/incremental_lift_eval.py --target perside_runs \\")
    print(f"      --feature-parquet {outp} --add-features opp_zone_overlap --run-name e13_10_zone")
    print(f"  uv run python betting_ml/scripts/incremental_lift_eval.py --target home_win \\")
    print(f"      --feature-parquet {outp} --add-features home_zone_overlap,away_zone_overlap \\")
    print(f"      --run-name e13_10_zone")


def main() -> None:
    ap = argparse.ArgumentParser(description="E13.10 zone-matchup builder (lakehouse)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("profiles", help="build leak-clean batter/pitcher zone profiles")
    p.add_argument("--start", required=True, help="window start (YYYY-MM-DD, inclusive)")
    p.add_argument("--end", required=True, help="window end (YYYY-MM-DD, EXCLUSIVE = as-of)")
    p.add_argument("--out-dir", required=True)
    p.add_argument("--sample-days", type=int, default=0, help="smoke: only last N days before end")
    p.add_argument("--s3", action="store_true", help="also write profiles to the lakehouse bucket")
    p.set_defaults(func=cmd_profiles)

    v = sub.add_parser("viz", help="emit matchup overlay JSON (product→S3) + PNG proof (artifact→S3)")
    v.add_argument("--profiles-dir", required=True)
    v.add_argument("--batter", type=int, default=None)
    v.add_argument("--pitcher", type=int, default=None)
    v.add_argument("--top", type=int, default=6, help="#showcase matchups when ids not given")
    v.add_argument("--no-s3", action="store_true", help="skip S3 writes (local-only, for dev)")
    v.add_argument("--local-dir", default=None,
                   help="also write JSON + proof PNG here (dev/verification; not for git/serving)")
    v.add_argument("--tmp-dir", default=None, help="scratch dir for the proof PNG when S3-only")
    v.set_defaults(func=cmd_viz)

    f = sub.add_parser("feature", help="build per-game zone-overlap scalar (Track B)")
    f.add_argument("--seasons", required=True, help="comma list, e.g. 2021,2022,2023,2024,2025,2026")
    f.add_argument("--window-seasons", type=int, default=3, help="prior seasons per profile window")
    f.add_argument("--out", required=True, help="output parquet (game_pk-keyed)")
    f.add_argument("--limit-games", type=int, default=0, help="smoke: only first N games/season")
    f.add_argument("--rich", action="store_true",
                   help="E13.2b: emit the DECOMPOSED profile channels (per-pitch-group value + "
                        "whiff + xwoba + peak) instead of the single collapsed overlap scalar")
    f.set_defaults(func=cmd_feature)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
