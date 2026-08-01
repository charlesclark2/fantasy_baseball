"""grade_context.py — MLB Edge-E7.12 SLICE 4: 20-80 scouting grades as MLE component priors.

Builds ONE cached parquet of as-of-safe tool grades per (player_id, level), which every S4 arm, fold and
ablation then reads (the §0.5 "assemble once → parquet" discipline).

WHY THIS SLICE IS DIFFERENT FROM EVERY OTHER E7.12 SLICE
---------------------------------------------------------------------------------------------------
Park, run-environment, reliability and label weights are all re-expressions of the SAME minor-league box
score. A 20-80 grade is the one input we carry that is **not derived from the line at all** — a human
watched the player. That is the whole reason to try it, and it is also why the leakage risk is unlike
anything in slices 1-2: a scouting grade published AFTER a player debuted has the answer in it.

🚨 **THE AS-OF GUARD IS THE SLICE.** A grade is admissible for a (player, level) row only if it comes
from the latest board snapshot **STRICTLY BEFORE** that player's debut season. Without it a 2026 grade
"predicts" a 2019 debut and the slice reports an enormous, entirely fake win.

📉 **WHAT THE GUARD COSTS — MEASURED 2026-07-31, AND IT SHAPES THE WHOLE DESIGN.** `the_board` begins at
`2018-07-01`, so a 2018 debut would need a 2017 snapshot that does not exist:

    labelled rows with an admissible grade:  batters 1,189 / 2,171 (54.8%) · pitchers 1,169 / 3,031 (38.6%)
    debut cohorts 2015-2018:                 STRUCTURALLY ZERO coverage (603 batter / 1,101 pitcher rows)

⇒ under the E7.3 fold structure **4 of 11 folds (2016-2019) carry no graded TRAINING row at all**, so the
grade arm is byte-identical to the baseline there and scores `delta = 0`, which the `d > 0` fold test
counts as a LOSS. Maximum achievable fold-win-rate is therefore **7/11 = 0.636 against a 0.60 gate** — a
PERFECT grade signal would clear by one fold, and a single loss among the seven live folds fails outright.
Scoring a mechanism on folds where it provably cannot act is not a stricter test, it is a broken one, so
`ACTIVE_FOLD_MIN` restricts the fold set and the inert folds are REPORTED rather than silently dropped.

⚠️ **A GRADED PLAYER IS A SELECTED PLAYER, AND THIS SLICE THEREFORE INTERACTS WITH S2.** Grade coverage is
monotone in S2's promotion propensity — batters 38.0% / 58.1% / 68.1% and pitchers 21.7% / 40.3% / 53.7%
across the low/mid/high terciles. So **the tool grade is least available exactly where S2 showed the model
most needs help**: the low-propensity end that stands in for the prospects we actually serve. That bounds
what this slice can deliver for the served population however well it scores, and it is the reason
`A_flag_only` exists — "this player was RANKED" is itself a signal, and it must be separated from "this
player's tool grade says X" or the slice will credit selection to scouting.
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger("grade_context")

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_ABLATION = _PROJECT_ROOT / "quant_sports_intel_models/baseball/edge_program/ablation_results"
MILB = "s3://baseball-betting-ml-artifacts/baseball/milb"

# The first debut cohort whose FOLD carries graded training rows. Folds below this are structurally inert
# (see the module docstring) and are excluded from the gate rather than counted as losses.
ACTIVE_FOLD_MIN = 2020

# Grade → component mapping. ⚠️ Deliberately SPARSE, and the gaps are honest rather than filled:
# a metric with NO scouting analogue gets an UNSELECTABLE NO-OP arm (the slice-1p `xwoba_against`
# precedent), never a fabricated neutral value.
#   • batters have NO plate-discipline grade — {Hit, Game, Raw, Spd, Fld} contains nothing that describes
#     walk rate, so `bb_pct` has no mapped grade. (The story prompt wrote "CMD→BB%" for batters; CMD is a
#     PITCHER grade and is simply absent from the batter grade set — trust the field list, not the prose.)
#   • `gb_pct` and `xwoba_against` have no single-tool analogue either.
GRADE_FOR_METRIC: dict[str, dict[str, str]] = {
    "batter": {
        "k_pct": "grade_hit",          # the hit tool IS bat-to-ball ⇒ contact ⇒ strikeout rate
        "iso": "grade_game_pwr",       # GAME power, not raw — game power is what shows up in ISO
        "woba": "grade_hit",           # the closest single tool to overall offensive value
    },
    "pitcher": {
        "bb_pct": "grade_cmd",         # command is precisely the walk-rate tool
        "k_pct": "grade_fb",           # fastball quality is the primary bat-missing tool
    },
}

# Every grade the side carries — the kitchen-sink arm, and the source of the `A_flag_only` indicator.
SIDE_GRADES: dict[str, tuple[str, ...]] = {
    "batter": ("grade_hit", "grade_game_pwr", "grade_raw_pwr", "grade_spd", "grade_fld"),
    "pitcher": ("grade_fb", "grade_sl", "grade_cb", "grade_ch", "grade_ct", "grade_spl", "grade_cmd"),
}

GRADE_COLS = tuple(dict.fromkeys(SIDE_GRADES["batter"] + SIDE_GRADES["pitcher"]))
FLAG_COL = "grade_is_present"
FV_COL = "board_fv"
_KEYS = ["player_id", "level"]


def load_board_grades(con) -> pd.DataFrame:
    """THE BOARD, deduped to one row per (season, fg_minor_id), with every 20-80 grade parsed out.

    🚨 Reads via `player_xref.register_board` and nothing else — `delta_scan` HARD-ERRORS on the
    void-typed `mlbam_id` column and a `read_parquet` glob reads TOMBSTONED files (3,870 rows vs the ACID
    1,290), which would FABRICATE the match rate. A guard test pins this; do not route around it.

    ⚠️ `mlbam_id` on the board itself is 100% NULL (it is that void column), so the identity bridge MUST
    go through `dim_player_xref.fg_minor_id` → `mlbam_id`. Joining on the board's own `mlbam_id` would
    silently match nothing and produce a clean, entirely false null.
    """
    from betting_ml.scripts.milb_xref.player_xref import register_board
    from betting_ml.scripts.prospect_board.board_assembly import (
        BATTER_GRADE_FIELDS, PITCHER_GRADE_FIELDS, parse_grade,
    )

    register_board(con)
    # the 2026 season carries two as_of snapshots; keep the latest per (season, player)
    b = con.execute("""
        select fg_minor_id, season, position, fv, as_of_date, raw_json,
               row_number() over (partition by season, fg_minor_id order by as_of_date desc) rn
        from board_src
        qualify rn = 1
    """).fetchdf()
    fields = {**BATTER_GRADE_FIELDS, **PITCHER_GRADE_FIELDS}
    parsed = pd.DataFrame([
        {dst: parse_grade(_blob(r).get(src)) for src, dst in fields.items()}
        for r in b["raw_json"]
    ], index=b.index)
    out = pd.concat([b.drop(columns=["raw_json", "rn"]), parsed], axis=1)
    out[FV_COL] = pd.to_numeric(out["fv"], errors="coerce")
    return out


def _blob(raw) -> dict:
    if not raw:
        return {}
    try:
        return json.loads(raw) if isinstance(raw, str) else dict(raw)
    except (ValueError, TypeError):
        return {}


def asof_grades(pairs: pd.DataFrame, board: pd.DataFrame, xref: pd.DataFrame,
                *, side: str) -> pd.DataFrame:
    """One row per (player_id, level) carrying the LATEST admissible board grades.

    Admissible = `board.season < debut_cohort`. For a row with NO debut cohort (a PROSPECT — the emission
    population) every snapshot is admissible, because nothing has happened yet that a grade could leak.

    🪤 The as-of bound is `<`, not `<=`. A board dated 2019-07-01 is published mid-season, so for a player
    who debuted in 2019 it may well post-date the callup — `<=` would admit exactly the grades most likely
    to be contaminated, and would do so on the cohort boundary where nobody looks.
    """
    grades = list(SIDE_GRADES[side])
    x = xref[["fg_minor_id", "mlbam_id"]].dropna().copy()
    x["player_id"] = pd.to_numeric(x["mlbam_id"], errors="coerce").astype("Int64")
    x = x.dropna(subset=["player_id"]).drop_duplicates(subset=["player_id", "fg_minor_id"])

    p = pairs[_KEYS + ["debut_cohort"]].copy()
    p["player_id_num"] = pd.to_numeric(p["player_id"], errors="coerce").astype("Int64")
    j = p.merge(x[["player_id", "fg_minor_id"]], left_on="player_id_num", right_on="player_id",
                how="inner", suffixes=("", "_x"))
    j = j.merge(board[["fg_minor_id", "season", FV_COL] + grades], on="fg_minor_id", how="inner")

    # a prospect has no debut season, so no snapshot can leak
    cutoff = pd.to_numeric(j["debut_cohort"], errors="coerce")
    j = j[cutoff.isna() | (j["season"] < cutoff)]
    j = (j.sort_values("season").groupby(_KEYS, as_index=False).tail(1)
          .rename(columns={"season": "board_season"}))

    out = pairs[_KEYS].merge(
        j[_KEYS + ["board_season", FV_COL] + grades], on=_KEYS, how="left")
    # ⭐ "was this player RANKED at all" is a DIFFERENT signal from "his hit tool is 55", and because
    # grade coverage rises monotonically with promotion propensity, conflating them would credit
    # SELECTION to SCOUTING. `A_flag_only` is the arm that separates them; this is its column.
    out[FLAG_COL] = out["board_season"].notna().astype(float)
    return out


def grade_coverage(ctx: pd.DataFrame, pairs: pd.DataFrame, *, side: str) -> pd.DataFrame:
    """Per-debut-cohort coverage on the LABELLED population, plus whether that cohort's FOLD is active.

    The story prompt requires this be reported BEFORE anything is scored — a slice whose mechanism is
    absent from a third of its evaluation population is a power question first and a modelling question
    second.
    """
    m = pairs[_KEYS + ["debut_cohort", "has_mlb_label"]].merge(ctx, on=_KEYS, how="left")
    lab = m[m["has_mlb_label"].fillna(False).astype(bool) & m["debut_cohort"].notna()]
    primary = GRADE_FOR_METRIC[side][next(iter(GRADE_FOR_METRIC[side]))]
    g = (lab.assign(_graded=lab[primary].notna())
            .groupby("debut_cohort")
            .agg(labelled=("player_id", "size"), graded=("_graded", "sum"))
            .reset_index())
    g["coverage"] = g["graded"] / g["labelled"]
    g["fold_is_active"] = g["debut_cohort"] >= ACTIVE_FOLD_MIN
    return g


def build(side: str, out_dir: Path) -> pd.DataFrame:
    import duckdb
    from deltalake import DeltaTable

    from scripts.utils.delta_lake import storage_options

    pairs_name = ("mle_graduated_pairs_pitchers.parquet" if side == "pitcher"
                  else "mle_graduated_pairs.parquet")
    art = _ABLATION / ("e7_3p_artifacts" if side == "pitcher" else "e7_3_artifacts")
    pairs = pd.read_parquet(art / pairs_name)

    con = duckdb.connect()
    board = load_board_grades(con)
    xref = DeltaTable(f"{MILB}/derived/dim_player_xref",
                      storage_options=storage_options()).to_pyarrow_dataset().to_table().to_pandas()
    ctx = asof_grades(pairs, board, xref, side=side)

    cov = grade_coverage(ctx, pairs, side=side)
    log.info("as-of grade coverage on the labelled population (%s):\n%s", side, cov.to_string(index=False))
    active = cov[cov["fold_is_active"]]
    log.info("ACTIVE folds (>= %d): %d of %d cohorts, coverage %.1f%%; the %d inert cohorts carry %d "
             "labelled rows the mechanism CANNOT reach", ACTIVE_FOLD_MIN, len(active), len(cov),
             100.0 * active["graded"].sum() / max(int(active["labelled"].sum()), 1),
             len(cov) - len(active), int(cov[~cov["fold_is_active"]]["labelled"].sum()))

    suffix = "_pitchers" if side == "pitcher" else ""
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"mle_grade_context{suffix}.parquet"
    ctx.to_parquet(dest, index=False)
    cov.to_csv(out_dir / f"mle_grade_coverage{suffix}.csv", index=False)
    log.info("wrote %s (%d rows, %d graded)", dest, len(ctx), int(ctx[FLAG_COL].sum()))
    return ctx


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="E7.12 slice 4 — build the as-of tool-grade context")
    p.add_argument("--player-type", choices=("batter", "pitcher"), default="batter")
    p.add_argument("--out-dir", default=str(_ABLATION / "e7_12_artifacts"))
    p.add_argument("-v", "--verbose", action="store_true")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")
    build(a.player_type, Path(a.out_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
