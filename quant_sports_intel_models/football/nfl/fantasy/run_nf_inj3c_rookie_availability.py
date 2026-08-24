#!/usr/bin/env python3
"""NF-INJ3c — VERIFY THE ROOKIE AVAILABILITY ROUTING AGAINST REALITY, not against fixtures.

    uv run python quant_sports_intel_models/football/nfl/fantasy/run_nf_inj3c_rookie_availability.py \
        --duckdb <path>/sports.duckdb --artifacts <path>/artifacts

⭐ WHY A RUNNER AND NOT ONLY TESTS. The defect this story closes was invisible to every test in the
suite for the whole life of the mechanism, and was found by resolving the population against the
REAL BUILT BOARD (NF-INJ-NEWS-1's own method lesson, the NF-C0e wired-vs-invoked class). A synthetic
frame cannot tell you whether the production function you think you fixed is the one that built the
artifact. So the acceptance evidence is measured on real boards, the real roster feed and the real
rookie classes — the same three inputs the recorded 50-of-60 finding was measured on.

FOUR LEGS, in the order that makes each one interpretable:

  1. REPRODUCTION PIN — recompute NF-INJ3's recorded rookie-bypass measurement over the PUBLISHED
     2019–2025 boards. It must return **50 of 60** flagged rookies above the incumbent ceiling and
     **0 of 496** veterans. ⚠️ A pin proves I am measuring the same population; it does NOT prove the
     shared computation is correct (NCAAF-CLV-repair: a pin can faithfully reproduce a bug). Its job
     here is only to establish the denominator leg 2 is judged against.

  2. THE WITH-FIX READ ON THE SAME REAL ROWS — apply the NEW rookie formal step to exactly those
     published rookie rows and re-count. Flagged rookies must now sit at or below the ceiling (0
     above); **0 unflagged rows may move**. This is the 50/60 basis re-read.

  3. THE WIRING PROOF, END TO END — call `project_rookies` itself on the real incoming rookie class
     with the real forward roster status, against the same call with `roster_status=None` (the
     pre-NF-INJ3c behaviour). Flagged rookies must cap; unflagged rookies must be BYTE-IDENTICAL;
     the whole scored line must move with games. ⭐ THIS is the leg that answers "is the fix
     INVOKED" — leg 2 only answers "does the function do the right arithmetic".

  4. THE LIVE METER — `_warn_formal_tag_without_discount` over the with-fix rookie frame. It must
     read 0. ⚠️ The FULL-BOARD meter reading is the operator's dry-run rebuild (leg 4 here sees the
     rookie half only, which is the half this story moves).

⛔ READ-ONLY. Nothing here writes a board, publishes, or fits a model; it opens the warehouse
read-only and reads published parquet.
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from quant_sports_intel_models.football.nfl.fantasy import nf_inj3_injury_games as _IG
from quant_sports_intel_models.football.nfl.fantasy import season_projection as SP
from quant_sports_intel_models.football.nfl.fantasy import run_season_projection as R

log = logging.getLogger("nf_inj3c")

#: The board years NF-INJ3 measured the rookie bypass over. ⚠️ NOT its FOLD list (2019–2025): the
#: runner calls `rookie_bypass_evidence` with `hist_seasons = range(ERA_MIN_SEASON, max(folds)+1)`,
#: i.e. **2016–2025**. Reading the folds instead measured 42/34 against a recorded 60/50 — the pin
#: caught it, which is the entire reason a pin is run before the with-fix leg rather than after.
#: DERIVED from the study's own constants so it cannot drift from them.
PIN_SEASONS: tuple[int, ...] = tuple(range(_IG.ERA_MIN_SEASON, max(_IG.FOLDS) + 1))
#: NF-INJ3's recorded figures (`ablation_results/nf_inj3_injury_games.json` → `rookie_bypass`).
RECORDED = {"rookie_flagged": 60, "rookie_above_ceiling": 50,
            "veteran_flagged": 496, "veteran_above_ceiling": 0}
SERVING_SEASON = 2026


def _status(con, season: int, sleeper: bool) -> pd.DataFrame:
    """Week-1 roster status, read exactly as NF-INJ3's own `load_status` reads it."""
    nv = con.sql(f"""
        select player_id, first(status order by week asc) as proj_status
        from {R.STAGING_SCHEMA}.stg_nfl_weekly_rosters
        where season = {season} and player_id is not null group by 1
    """).df()
    if not sleeper:
        return nv
    sl = con.sql(f"""
        select player_id, first(proj_status order by ingested_at desc) as ps
        from {R.STAGING_SCHEMA}.stg_nfl_sleeper_injuries
        where season = {season} and player_id is not null and proj_status is not null group by 1
    """).df()
    m = nv.merge(sl, on="player_id", how="outer")
    m["proj_status"] = m["ps"].where(m["ps"].notna(), m["proj_status"])
    return m[["player_id", "proj_status"]]


def _ceiling() -> float:
    """The HIGHEST games the incumbent cap can leave on a flagged row: the blend applied to the
    largest status level against a full 17-game season. A row above this received no cap at all."""
    b = SP._INJURY_OVERRIDE_BLEND
    return (1 - b) * 17.0 + b * max(SP._INJURY_STATUS_GAMES_CAP.values())


def leg1_reproduction(art: Path, con) -> dict:
    """NF-INJ3's `rookie_bypass_evidence`, recomputed here so the pin does not depend on that
    runner's own state. Per-status ceiling, exactly as it computed it."""
    rk_n = rk_above = vet_n = vet_above = 0
    per_season = []
    for y in PIN_SEASONS:
        board = pd.read_parquet(art / f"nfl_fantasy_season_projections_{y}.parquet")
        m = board.merge(_status(con, y, sleeper=False), on="player_id", how="left")
        f = m[m["proj_status"].isin(SP._INJURY_STATUS_GAMES_CAP)].copy()
        cap = f["proj_status"].map(SP._INJURY_STATUS_GAMES_CAP).to_numpy(dtype=float)
        ceil = (1 - SP._INJURY_OVERRIDE_BLEND) * 17.0 + SP._INJURY_OVERRIDE_BLEND * cap
        above = f["proj_games"].to_numpy() > ceil + 1e-9
        isr = f["is_rookie"].astype(bool).to_numpy()
        rk_n += int(isr.sum()); rk_above += int((above & isr).sum())
        vet_n += int((~isr).sum()); vet_above += int((above & ~isr).sum())
        per_season.append({"season": y, "rookie_flagged": int(isr.sum()),
                           "rookie_above_ceiling": int((above & isr).sum())})
    got = {"rookie_flagged": rk_n, "rookie_above_ceiling": rk_above,
           "veteran_flagged": vet_n, "veteran_above_ceiling": vet_above}
    return {"measured": got, "recorded": RECORDED, "reproduces": got == RECORDED,
            "per_season": per_season}


def leg2_with_fix_on_the_same_rows(art: Path, con) -> dict:
    """Apply the NEW rookie formal step to the SAME published rookie rows and re-count.

    ⭐ VALID ON THESE ROWS BECAUSE NO CAP EVER RAN ON THEM. A published rookie's `proj_games` is
    exactly the value `project_rookies` hands the availability chain: the chain sits immediately
    after the line is scored, and neither NF-D16 (which scales the LINE, never games) nor the band
    touches games afterwards. So the published number IS the pre-cap `eg`, with no inversion needed
    — which is why this leg can be read on the artifact rather than on a rebuild.
    """
    rows_above = 0
    flagged = 0
    unflagged_moved = 0
    unflagged_n = 0
    max_drop = 0.0
    per_season = []
    for y in PIN_SEASONS:
        board = pd.read_parquet(art / f"nfl_fantasy_season_projections_{y}.parquet")
        rk = board[board["is_rookie"].astype(bool)].merge(
            _status(con, y, sleeper=False), on="player_id", how="left").reset_index(drop=True)
        if rk.empty:
            continue
        before = pd.to_numeric(rk["proj_games"], errors="coerce").to_numpy(dtype=float)
        after = SP.injury_availability_games(rk)
        cap = rk["proj_status"].map(SP._INJURY_STATUS_GAMES_CAP).to_numpy(dtype=float)
        is_flagged = np.isfinite(cap)
        ceil = (1 - SP._INJURY_OVERRIDE_BLEND) * 17.0 + SP._INJURY_OVERRIDE_BLEND * cap
        above = np.zeros(len(rk), dtype=bool)
        above[is_flagged] = after[is_flagged] > ceil[is_flagged] + 1e-9
        moved = np.abs(after - before) > 1e-9
        flagged += int(is_flagged.sum())
        rows_above += int(above.sum())
        unflagged_n += int((~is_flagged).sum())
        unflagged_moved += int((moved & ~is_flagged).sum())
        if is_flagged.any():
            max_drop = max(max_drop, float(np.max(before[is_flagged] - after[is_flagged])))
        per_season.append({"season": y, "flagged": int(is_flagged.sum()),
                           "above_ceiling_after": int(above.sum()),
                           "mean_games_before": float(before[is_flagged].mean()) if is_flagged.any() else None,
                           "mean_games_after": float(after[is_flagged].mean()) if is_flagged.any() else None})
    return {"flagged_rookies": flagged, "above_ceiling_after": rows_above,
            "unflagged_rows": unflagged_n, "unflagged_rows_moved": unflagged_moved,
            "max_games_dropped": max_drop, "per_season": per_season,
            "passes": rows_above == 0 and unflagged_moved == 0}


def _rookie_arms(con, season: int):
    """The pre/post pair for one season, through the REAL production function."""
    rookies_all = R.load_rookie_projection_frame()
    incoming = rookies_all[
        pd.to_numeric(rookies_all["draft_year"], errors="coerce") == season]
    if incoming.empty:
        return None
    curve = SP.fit_rookie_slot_curves(
        R.load_rookie_training(con, season - 1, R.MARTS_SCHEMA),
        band_hist=R.load_rookie_training(con, season - 1, R.MARTS_SCHEMA, include_zero_game=True))
    status = R.load_forward_roster_status(con, season)
    before = SP.project_rookies(incoming, curve, season)                       # pre-NF-INJ3c shape
    after = SP.project_rookies(incoming, curve, season, roster_status=status)  # with the routing
    return before, after, status


def _wiring_one(con, season: int) -> dict:
    arms = _rookie_arms(con, season)
    if arms is None:
        return {"season": season, "skipped": "no incoming rookie class", "active": False}
    before, after, _ = arms
    assert "proj_status" not in before.columns, (
        "the no-feed call attached a status — the two arms are not the pre/post pair")
    keep = ["player_id", "proj_games", "proj_fp_ppr", *SP.AVAILABILITY_LINE_COLS]
    m = before[keep].merge(
        after[[*keep, "proj_status", SP.FORMAL_APPLIED_COL]],
        on="player_id", how="inner", suffixes=("_before", "_after"))
    cap = m["proj_status"].map(SP._INJURY_STATUS_GAMES_CAP).to_numpy(dtype=float)
    is_flagged = np.isfinite(cap)
    ceil = (1 - SP._INJURY_OVERRIDE_BLEND) * 17.0 + SP._INJURY_OVERRIDE_BLEND * cap
    g_before = m["proj_games_before"].to_numpy(dtype=float)
    g_after = m["proj_games_after"].to_numpy(dtype=float)
    fp_before = m["proj_fp_ppr_before"].to_numpy(dtype=float)
    fp_after = m["proj_fp_ppr_after"].to_numpy(dtype=float)
    moved = np.abs(g_after - g_before) > 1e-9
    # ⭐ THE WHOLE LINE MUST MOVE WITH GAMES. A games discount that left the points alone would show
    #    a healthy fantasy total beside a shelved player's game count — the NF-INJ1 coherence class.
    #    ⚠️ ASSERTED ON THE VOLUME COLUMNS, WHICH SCALE EXACTLY, not on the scored point, which does
    #    NOT — and the difference is a measurement, not a tolerance chosen to make a test pass.
    #    `proj_fumbles_lost` is RECOMPUTED from touches and ROUNDED to 2dp on both sides, and it
    #    enters the score at −2/fumble, so `fp_after − s·fp_before = −2(ε_after − s·ε_before)` with
    #    each |ε| ≤ 0.005 ⇒ **|Δfp| ≤ 0.02 points, derived, for any s ∈ [0,1]**. Measured max here:
    #    ~0.014. An `atol=1e-6` on the fp RATIO reported this as a coherence failure on 9 of 10
    #    seasons; the yardage ratios were equal to the games ratio to the last bit throughout.
    sel = is_flagged & moved & (g_before > 1e-6)
    line_follows = True
    fp_max_dev = 0.0
    if sel.any():
        s_ratio = g_after[sel] / g_before[sel]
        for col in SP.AVAILABILITY_LINE_COLS:
            b = m[f"{col}_before"].to_numpy(dtype=float)[sel]
            aft = m[f"{col}_after"].to_numpy(dtype=float)[sel]
            live = np.abs(b) > 1e-9
            if live.any() and not np.allclose(aft[live], b[live] * s_ratio[live], rtol=1e-12,
                                              atol=1e-9):
                line_follows = False
        fp_max_dev = float(np.max(np.abs(fp_after[sel] - fp_before[sel] * s_ratio)))
    above_after = int((g_after[is_flagged] > ceil[is_flagged] + 1e-9).sum()) if is_flagged.any() else 0
    return {
        "season": season, "rookie_rows": int(len(m)),
        "flagged": int(is_flagged.sum()),
        "active": bool(is_flagged.any()),
        "flagged_capped": int((is_flagged & moved).sum()),
        "flagged_above_ceiling_after": above_after,
        "unflagged_rows_moved": int((moved & ~is_flagged).sum()),
        "unflagged_fp_identical": bool(np.array_equal(fp_before[~is_flagged], fp_after[~is_flagged])),
        "line_follows_games": line_follows,
        # the DERIVED fumble-rounding bound (see above), reported beside the measurement so a
        # reader can check the claim rather than take the boolean on trust.
        "fp_max_abs_dev_from_exact_scaling": fp_max_dev,
        "fp_dev_within_fumble_rounding_bound": bool(fp_max_dev <= 0.02 + 1e-9),
        "mean_games_before_flagged": float(g_before[is_flagged].mean()) if is_flagged.any() else None,
        "mean_games_after_flagged": float(g_after[is_flagged].mean()) if is_flagged.any() else None,
        "flagged_detail": [
            {"player_id": m["player_id"].iloc[k], "status": m["proj_status"].iloc[k],
             "games_before": float(g_before[k]), "games_after": float(g_after[k]),
             "fp_before": float(fp_before[k]), "fp_after": float(fp_after[k]),
             "formal_applied": bool(m[SP.FORMAL_APPLIED_COL].iloc[k])}
            for k in np.flatnonzero(is_flagged)],
    }


def leg3_wiring(con, seasons: tuple[int, ...]) -> dict:
    """END-TO-END: `project_rookies` with vs without the roster feed, on the real rookie classes.

    ⭐ Leg 2 measures the FUNCTION on real rows; this measures the PRODUCTION PATH. They are
    different claims and the repo has paid for confusing them (NF-C0e: wired ≠ invoked).

    ⚠️⚠️ AND IT IS RUN OVER MANY SEASONS FOR ONE REASON: **ON THE LIVE 2026 CLASS THE MECHANISM
    CANNOT ACT.** Not one 2026 rookie carries a formal tag today — the 53-man cutdown that creates
    that population is 2026-08-30 — so a 2026-only leg PASSES WITHOUT TESTING ANYTHING, which is
    precisely NF-D20's inactive-gate shape ("count the folds the mechanism could ACT on before
    crediting the passes"). The historical classes are where the routing can be exercised at all, so
    the leg REFUSES a verdict unless at least one season is ACTIVE, and reports the active count
    beside the pass count rather than letting the two be confused.
    """
    per = [_wiring_one(con, y) for y in seasons]
    active = [d for d in per if d.get("active")]
    checked = [d for d in per if not d.get("skipped")]
    passes = bool(
        active                                                  # ⛔ never a vacuous pass
        and all(d["flagged_above_ceiling_after"] == 0 for d in active)
        and all(d["flagged_capped"] == d["flagged"] for d in active)
        and all(d["unflagged_rows_moved"] == 0 for d in checked)
        and all(d["unflagged_fp_identical"] for d in checked)
        and all(d["line_follows_games"] for d in active)
        and all(d["fp_dev_within_fumble_rounding_bound"] for d in active))
    return {
        "seasons_checked": [d["season"] for d in checked],
        "seasons_ACTIVE": [d["season"] for d in active],
        "n_active_seasons": len(active),
        "flagged_rookies_total": sum(d["flagged"] for d in active),
        "flagged_capped_total": sum(d["flagged_capped"] for d in active),
        "above_ceiling_after_total": sum(d["flagged_above_ceiling_after"] for d in active),
        "unflagged_rows_moved_total": sum(d["unflagged_rows_moved"] for d in checked),
        "fp_max_abs_dev_from_exact_scaling": max(
            [d["fp_max_abs_dev_from_exact_scaling"] for d in active] or [0.0]),
        "fp_rounding_bound": 0.02,
        "per_season": per,
        "passes": passes,
        "reading": (
            "the routing is exercised on every season that HAS a flagged rookie; a season with "
            "none is reported INACTIVE, never as a pass. The live 2026 class is inactive today "
            "because the 53-man cutdown (2026-08-30) has not happened — which is the whole reason "
            "this story is dated."),
    }


def leg4_meter(con, seasons: tuple[int, ...]) -> dict:
    """The live meter (`_warn_formal_tag_without_discount`) over the with-fix ROOKIE frame.

    ⚠️ THE ROOKIE HALF ONLY, and this leg says so rather than letting a reader take it for the
    board reading. The FULL-BOARD meter is the operator's dry-run rebuild — a meter run on a frame
    this session assembled is not the meter run on the built board (INC-39: a monitor reading output
    it did not produce must name WHICH artifact it describes).

    ⚠️ AND IT IS TWO-SIDED. `meter_after == 0` alone is satisfied by a season with no flagged rookie
    at all, so the PRE-fix reading is taken on the identical frame: a season is INFORMATIVE only
    when `meter_before > 0`, and that is what the pass keys on."""
    per = []
    for y in seasons:
        arms = _rookie_arms(con, y)
        if arms is None:
            per.append({"season": y, "skipped": "no incoming rookie class"})
            continue
        before, after, status = arms
        # the PRE-fix reading needs the status attached the way build_projection used to attach it
        before = before.merge(status, on="player_id", how="left")
        per.append({"season": y,
                    "meter_before_fix": int(R._warn_formal_tag_without_discount(before)),
                    "meter_after_fix": int(R._warn_formal_tag_without_discount(after))})
    informative = [d for d in per if d.get("meter_before_fix", 0) > 0]
    return {
        "per_season": per,
        "n_informative_seasons": len(informative),
        "meter_before_fix_total": sum(d.get("meter_before_fix", 0) for d in per),
        "meter_after_fix_total": sum(d.get("meter_after_fix", 0) for d in per),
        "passes": bool(informative and all(d["meter_after_fix"] == 0 for d in informative)),
        "reading": ("a season whose PRE-fix meter already read 0 carries no information about the "
                    "fix — it is counted but excluded from the verdict (NF1.7 (a))."),
    }


def leg5_board_diff(published: Path, rebuilt: Path) -> dict:
    """THE SHIP-PATH DIFF — a with-fix rebuild against the PUBLISHED board, keyed on the served row.

    ⭐ ROOKIE ROWS ONLY MAY MOVE. This story touches the rookie frame; a veteran row that moved is a
    refusal, not a note. ⚠️ AND ON TODAY'S BOARD THE EXPECTED DIFF IS **EMPTY** — no 2026 rookie
    carries a formal tag until the 2026-08-30 cutdown (§3.1 of the record), which makes this the
    cleanest possible byte-identity check and is exactly how it should be read: the fix is INERT on
    today's board and arms at the cutdown. A non-empty veteran diff is the finding; a non-empty
    rookie diff before the cutdown is also a finding.
    """
    a = pd.read_parquet(published)
    b = pd.read_parquet(rebuilt)
    key = "player_id"
    # a build stamp is EXPECTED to differ; everything else is a claim about the board.
    skip = {"generated_at"}
    common = [c for c in a.columns if c in b.columns and c not in skip and c != key]
    ident = a[[key] + [c for c in ("player_name", "is_rookie") if c in a.columns]].rename(
        columns={"player_name": "_name", "is_rookie": "_rookie"})
    m = (a[[key, *common]].rename(columns={c: f"{c}_pub" for c in common})
         .merge(b[[key, *common]].rename(columns={c: f"{c}_new" for c in common}),
                on=key, how="outer", indicator=True)
         .merge(ident, on=key, how="left"))
    moved_rows, moved_fields = [], {}
    for c in common:
        pub, new_ = m[f"{c}_pub"], m[f"{c}_new"]
        if pd.api.types.is_numeric_dtype(pub) and pd.api.types.is_numeric_dtype(new_):
            d = ~np.isclose(pub.to_numpy(dtype=float), new_.to_numpy(dtype=float),
                            rtol=0, atol=0, equal_nan=True)
        else:
            d = pub.astype(str).to_numpy() != new_.astype(str).to_numpy()
        if d.any():
            moved_fields[c] = int(d.sum())
            for i in np.flatnonzero(d):
                moved_rows.append({"player_id": m[key].iloc[i],
                                   "player_name": m.get("_name", pd.Series(dtype=object)).iloc[i]
                                   if "_name" in m.columns else None,
                                   "is_rookie": bool(m["_rookie"].iloc[i])
                                   if "_rookie" in m.columns else None,
                                   "field": c,
                                   "published": pub.iloc[i], "rebuilt": new_.iloc[i]})
    only = m["_merge"].value_counts().to_dict()
    vet_moved = sorted({r["player_id"] for r in moved_rows if not r["is_rookie"]})
    rk_moved = sorted({r["player_id"] for r in moved_rows if r["is_rookie"]})
    return {
        "published": str(published), "rebuilt": str(rebuilt),
        "rows_published": int(len(a)), "rows_rebuilt": int(len(b)),
        "row_membership": {str(k): int(v) for k, v in only.items()},
        "fields_moved": moved_fields,
        "veteran_players_moved": len(vet_moved), "rookie_players_moved": len(rk_moved),
        "veteran_ids_moved": vet_moved[:50], "rookie_ids_moved": rk_moved[:50],
        "sample": moved_rows[:40],
        "passes": bool(len(vet_moved) == 0 and str(only.get("both", 0)) == str(len(a))),
        "reading": ("PASS requires ZERO veteran rows moved and identical row membership. Rookie "
                    "rows moving is expected only once a 2026 rookie actually carries a formal tag "
                    "(2026-08-30 cutdown); before then the whole diff should be empty."),
    }


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--duckdb", default="quant_sports_intel_models/sports_dbt/sports.duckdb")
    ap.add_argument("--artifacts",
                    default="quant_sports_intel_models/football/nfl/fantasy/artifacts")
    ap.add_argument("--season", type=int, default=SERVING_SEASON)
    ap.add_argument("--out", default="quant_sports_intel_models/football/nfl/fantasy/"
                                     "ablation_results/nf_inj3c_rookie_availability.json")
    ap.add_argument("--diff-published", default=None,
                    help="SHIP-PATH MODE: path to the PUBLISHED board parquet. With "
                         "--diff-rebuilt, runs ONLY the board diff (no warehouse legs) and exits "
                         "non-zero if any VETERAN row moved.")
    ap.add_argument("--diff-rebuilt", default=None,
                    help="SHIP-PATH MODE: path to the with-fix dry-run rebuild's board parquet.")
    a = ap.parse_args()
    if a.diff_published or a.diff_rebuilt:
        if not (a.diff_published and a.diff_rebuilt):
            raise SystemExit("--diff-published and --diff-rebuilt must be given together")
        rep = leg5_board_diff(Path(a.diff_published), Path(a.diff_rebuilt))
        out = Path(a.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(rep, indent=2, default=str))
        print(json.dumps({k: v for k, v in rep.items() if k != "sample"}, indent=2, default=str))
        for row in rep["sample"]:
            print("   ", row)
        print(f"\n{'✅' if rep['passes'] else '❌'} NF-INJ3c board diff -> {out}")
        return 0 if rep["passes"] else 1

    art = Path(a.artifacts)
    con = duckdb.connect(a.duckdb, read_only=True)

    rep = {
        "story": "NF-INJ3c",
        "duckdb": str(a.duckdb), "artifacts": str(art),
        "incumbent_constants": dict(SP._INJURY_STATUS_GAMES_CAP),
        "incumbent_blend": SP._INJURY_OVERRIDE_BLEND,
        "leg1_reproduction": leg1_reproduction(art, con),
        "leg2_with_fix_same_rows": leg2_with_fix_on_the_same_rows(art, con),
        "leg3_wiring_end_to_end": leg3_wiring(con, PIN_SEASONS + (a.season,)),
        "leg4_meter_rookie_half": leg4_meter(con, PIN_SEASONS + (a.season,)),
    }
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, indent=2, default=str))
    print(json.dumps(rep, indent=2, default=str))
    ok = (rep["leg1_reproduction"]["reproduces"]
          and rep["leg2_with_fix_same_rows"]["passes"]
          and rep["leg3_wiring_end_to_end"]["passes"]
          and rep["leg4_meter_rookie_half"]["passes"])
    print(f"\n{'✅' if ok else '❌'} NF-INJ3c reality verification -> {out}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
