"""run_nf_inj4b_counterfactual.py — NF-INJ4b ship path: what the certified discount would do to the
PUBLISHED board, and the operator packet.

⛔ **DEPLOY-HELD. This runner CHANGES NOTHING.** It reads the published boards and the landed
designation feed, computes a counterfactual, and writes a report. It does not rebuild, publish, or
touch the served artifact, and the publish decision is the operator's.

────────────────────────────────────────────────────────────────────────────────────────────────
⚠️ THE SCOPE RULE, AND WHY THIS IS EXPECTED TO MOVE NOTHING TODAY
────────────────────────────────────────────────────────────────────────────────────────────────
The fitted population is **2025 REGULAR-SEASON weeks 1–18**. A PRESEASON tag is a different animal:
the game-status report only publishes Out/Doubtful once the season starts, so a preseason feed is
almost all `Questionable` and applying an in-season fit to it is an out-of-population read. The
pre-registration REFUSES that rather than quietly extending, and predicted forward that a
counterfactual built before Week 1 **may move almost nothing**.

⭐ That prediction is MEASURED here, not asserted — the regular-season start comes from the
schedule and the designation census from the landed feed. An INACTIVE counterfactual is
UNINFORMATIVE, and it is reported as such: ⛔ never as a passed check (NF1.7 (a) / NF-D20).

⭐ **AND THE LEG IS EXERCISED ANYWAY, AS A LABELLED OUT-OF-SCOPE REHEARSAL.** A scope gate that
refuses every row leaves the board arithmetic, the join and the renderer NEVER RUN — so the
operator's Week-1 invocation would be this code's first-ever execution against real producer
output, which is exactly the failure the rehearsal discipline exists to stop. The rehearsal applies
the discount to today's preseason tags to prove the leg executes and to show the packet's shape.
⛔ Its numbers are NOT a result and are labelled on every surface that carries them.

⚠️ **THIS IS A READ ON THE PUBLISHED BOARD, NOT A CAPTURE-PINNED REBUILD.** The registered ship
path's step 1 is a full rebuild against a pinned baseline with matched market vintages (NF-INJ2c:
a pin whose market inputs are a different day is not a pin). That is an OPERATOR step, listed in
the closeout, and it is what produces the publish-candidate board. What this runner gives is the
decision-relevant magnitude beforehand.

RUN (LAPTOP — reads S3 read-only, writes one local report; MEASURED ~25 s):

    AWS_DEFAULT_REGION=us-east-2 uv run python -m \
      quant_sports_intel_models.football.nfl.fantasy.run_nf_inj4b_counterfactual
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    nf_inj4_designation_duration as DD,
    nf_inj4b_designation_duration as B,
    export_draft_board_json as EX,
    sleeper_injuries_source as SI,
)

log = logging.getLogger("nfl.fantasy.nf_inj4b.counterfactual")

_HERE = Path(__file__).resolve().parent
_REPORT_DIR = _HERE / "ablation_results"
_FRAME = _HERE / "artifacts" / "nf_inj4_designation_frame_2025.parquet"
SEASON = 2026
TOP_N = 25


# ══════════════════════════════════════════════════════════════════════════════════════════════
def magnitude_table(frame: pd.DataFrame, arm: str) -> dict:
    """The per-designation discount, fitted on the FULL frame (a serving read, not a fold).

    ⚠️ The LIVE feed carries no practice-participation column, so the certified `desig_x_practice`
    arm resolves every live row at `practice = unknown` and BACKS OFF to its designation-only
    parent. That is the backoff doing exactly what it was registered to do, and it is stated here
    rather than left for a reader to infer from a table that looks position-invariant.
    """
    rows = []
    for desig in DD.DESIGNATION_LEVELS:
        probe = pd.DataFrame([{"designation": desig, "position": "RB",
                               "practice_level": DD.PRACTICE_UNKNOWN,
                               "games_remaining": int(DD.SUPPORT_MAX), "spell": 0}])
        pmf = DD.fit_predict(arm, frame, probe)
        pmf = DD.truncate_to_support(pmf, probe["games_remaining"].to_numpy())
        missed = float(DD.expected_games_missed(pmf)[0])
        rows.append({"designation": desig,
                     "expected_games_missed": round(missed, 4),
                     "rate_multiplier": round((DD.SEASON_GAMES - missed) / DD.SEASON_GAMES, 4)})
    return {"arm": arm, "fitted_on": "the FULL frame (a serving read, not a fold)",
            "practice_level": DD.PRACTICE_UNKNOWN,
            "backoff_note": "the live feed carries no practice column, so every live row resolves "
                            "at practice=unknown and BACKS OFF to the designation-only parent",
            "rows": rows}


#: ⭐ The live feed's DISPLAY labels ("Questionable") onto the model's registered LEVELS
#: ("questionable"). Derived from the feed's own vocabulary rather than hardcoded, and ASSERTED at
#: import, so a designation added upstream fails loudly here instead of silently pricing at 1.0.
_MODEL_LEVEL: dict[str, str] = {
    label: label.strip().lower() for label in SI.WEEKLY_DESIGNATIONS.values()}
_missing = sorted(v for v in _MODEL_LEVEL.values() if v not in DD.DESIGNATION_LEVELS)
if _missing:
    raise ImportError(
        f"the live feed emits designation(s) {_missing} that the fitted model has no level for "
        f"(levels: {list(DD.DESIGNATION_LEVELS)}). ⛔ A counterfactual that priced them at 1.0 "
        f"would report 'the discount moves nothing' for a designation it simply could not read.")


def live_designations(season: int) -> dict:
    """The landed feed, read exactly as the board reads it — including the id normalisation.

    ⛔ NF-C9's id lesson: zero-padded Sleeper ids silently dropped real players from an id-keyed
    join, and an id-keyed check cannot see an id defect. The board's OWN normaliser is reused rather
    than re-implemented, so this join cannot drift from the one the board performs.
    """
    from quant_sports_intel_models.football.nfl.ingest import s3io
    uri = s3io.table_uri("nfl", "sleeper_injuries", tier="raw")
    con = s3io.duckdb_lake_connection()
    try:
        df = con.sql(f"select player_id, injury_status, ingested_at from delta_scan('{uri}') "
                     f"where season = {int(season)} and player_id is not null").df()
    finally:
        con.close()
    out: dict[str, str] = {}
    unrecognised: dict[str, int] = {}
    for pid, status in zip(df["player_id"], df["injury_status"]):
        disclose, label = SI.disclosable_designation(status)
        if not disclose:
            continue
        if label is None:
            unrecognised[str(status).strip().upper()] = unrecognised.get(
                str(status).strip().upper(), 0) + 1
            continue
        out[EX._norm_player_id(pid)] = _MODEL_LEVEL[label]
    census = {k: int(v) for k, v in
              df["injury_status"].value_counts(dropna=False).items()}
    return {"rows_fed": int(len(df)),
            "designated": out,
            "census_raw": {str(k): v for k, v in census.items()},
            "by_designation": {d: sum(1 for v in out.values() if v == d)
                               for d in sorted(set(out.values()))},
            "label_crosswalk_feed_to_model_level": dict(_MODEL_LEVEL),
            "unrecognised_status_labels": unrecognised,
            "newest_ingested_at": (str(df["ingested_at"].max()) if len(df) else None)}


def regular_season_start(season: int) -> str:
    """MEASURED from the schedule, never assumed — the scope gate turns on this date."""
    from quant_sports_intel_models.football.nfl.ingest.query_lake import delta, q
    df = q(f"select min(gameday) as first_game from {delta('schedules')} "
           f"where season = {int(season)} and game_type = 'REG'")
    return str(df["first_game"].iloc[0])


def board_moves(boards: pd.DataFrame, designated: dict, mult: dict) -> dict:
    """Re-derive VOR and the whole-board ranks per config under the discount.

    ⛔ FIRST-ORDER AND SAID SO: the rate cap scales a player's counting line, hence his league
    points, by the multiplier; VOR is then `points − replacement` at the board's OWN per-position
    replacement level. That is what the discount does to the published board. It is NOT a rebuild —
    a rebuild re-fits replacement levels against the moved field, and it is the operator's step.
    """
    out: dict = {}
    # ⛔ THE BOARD KEY IS (config_name, n_teams), NOT config_name. Each config publishes a 10-team
    #    AND a 12-team board with DIFFERENT replacement levels, so grouping on the config alone
    #    concatenates two boards, ranks 1,716 rows against each other and fabricates a rank move for
    #    almost every player. Measured: the first cut of this function reported 1,715 of 1,716 rows
    #    moving under an EMPTY designation map — which is what caught it (see `no_op_control`).
    for (cfg, n_teams), g in boards.groupby(["config_name", "n_teams"]):
        key = f"{cfg}__{int(n_teams)}team"
        g = g.copy()
        g["cf_pid"] = g["player_id"].map(EX._norm_player_id)
        g["cf_desig"] = g["cf_pid"].map(designated)
        # ⛔ **AN UNMAPPED DESIGNATION MUST RAISE, NEVER SILENTLY MEAN "NO DISCOUNT".**
        #    The live feed emits TITLE-CASE labels ("Questionable") and the model's levels are
        #    lower-case ("questionable"), so the first cut of this line mapped every designated row
        #    to NaN and `fillna(1.0)` turned the whole discount into a NO-OP — 89 designated players
        #    on the board, a 3.7% cut registered against each of them, and ZERO ranks moved. It
        #    raised no error and the id-join coverage read a healthy 89, because a join-coverage
        #    check cannot see a LABEL-KEY defect any more than an id-keyed check can see an id one
        #    (NF-C0e / NF-C9). The out-of-scope rehearsal is the only reason it was caught before it
        #    became a wrong answer in an operator packet.
        unmapped = sorted(set(g["cf_desig"].dropna()) - set(mult))
        if unmapped:
            raise SystemExit(
                f"designation label(s) {unmapped} on board {key} have no fitted multiplier "
                f"(model levels: {sorted(mult)}). ⛔ Refusing rather than defaulting to 1.0 — a "
                f"silent no-discount is indistinguishable from a correctly-applied one that "
                f"happened to move nothing.")
        g["cf_mult"] = g["cf_desig"].map(mult).astype(float).fillna(1.0)
        g["cf_points"] = g["league_points"].astype(float) * g["cf_mult"]
        g["cf_vor"] = g["cf_points"] - g["replacement_points"].astype(float)
        # ⭐ BOTH ranks are derived the SAME WAY, so a zero discount gives exactly zero moves BY
        #    CONSTRUCTION. Comparing a re-derived rank against the PUBLISHED one would fold every
        #    difference in ordering convention into the "move" column.
        g["cf_base_rank"] = g["vor"].astype(float).rank(ascending=False, method="first").astype(int)
        g["cf_rank"] = g["cf_vor"].rank(ascending=False, method="first").astype(int)
        g["cf_move"] = g["cf_base_rank"] - g["cf_rank"]
        # ⭐ …and the re-derivation is CHECKED against the publisher's own ordering, so "this reads
        #    the published board" is a measurement rather than a claim.
        agree = float((g["cf_base_rank"] == g["overall_rank"].astype(int)).mean())
        moved = g[g["cf_move"] != 0]
        touched = g[g["cf_desig"].notna()]
        top = (g.assign(cf_abs=g["cf_move"].abs()).sort_values(["cf_abs", "cf_base_rank"],
                                                           ascending=[False, True]).head(TOP_N))
        out[key] = {
            "rows": int(len(g)),
            "recomputed_baseline_rank_agrees_with_published": round(agree, 4),
            "designated_rows_on_board": int(len(touched)),
            "rows_whose_rank_moved": int(len(moved)),
            "max_abs_rank_move": int(g["cf_move"].abs().max()) if len(g) else 0,
            "top_moves": [
                {"player": r.player_name, "position": r.position,
                 "designation": (None if pd.isna(r.cf_desig) else r.cf_desig),
                 "rank_before": int(r.cf_base_rank), "rank_after": int(r.cf_rank),
                 "published_overall_rank": int(r.overall_rank),
                 "rank_move": int(r.cf_move),
                 "proj_games": round(float(r.proj_games), 2),
                 "league_points_before": round(float(r.league_points), 2),
                 "league_points_after": round(float(r.cf_points), 2)}
                for r in top.itertuples() if int(r.cf_move) != 0][:TOP_N],
        }
    return out


def render(s: dict) -> str:
    sc, mag, live = s["scope"], s["magnitude_table"], s["live_feed"]
    live_leg = s["counterfactual_under_the_scope_rule"]
    reh = (s["out_of_scope_rehearsal"] or {}).get("moves")
    L = [f"# NF-INJ4b — operator packet: what the certified designation discount would do",
         "",
         f"**Generated {s['generated_at']} · season {s['season']} · as-of {s['as_of']}.** "
         f"`best_alpha = 0`. ⛔ **DEPLOY-HELD — this run changes nothing.** The served "
         f"Questionable / Doubtful / Out discount is EXACTLY ZERO, no production caller passes the "
         f"designation channel, and the publish decision is the operator's.", "",
         "---", "",
         "## 1. ⚠️ The scope verdict — measured, not assumed", "",
         f"The 2026 regular season starts **{s['regular_season_start_measured']}** (read from the "
         f"schedule, not assumed) and this run is as of **{s['as_of']}** — "
         f"**{sc['days_to_regular_season']} days before Week 1**.", "",
         f"The registered scope rule admits REGULAR-SEASON designations only. The live feed carries "
         f"**{live['by_designation']}** — the preseason shape (the game-status report only publishes "
         f"Out/Doubtful once the season starts), so the rule **refuses all "
         f"{sc['designations_refused_by_the_scope_rule']}** of them.", "",
         sc["reading"], "",
         "---", "",
         "## 2. The per-designation magnitude — the number the operator is deciding about", "",
         f"Arm `{mag['arm']}`, fitted on the full frame. ⚠️ {mag['backoff_note']}.", "",
         "| designation | E[games missed] | rate multiplier on projected games |", "|---|---|---|"]
    for r in mag["rows"]:
        L.append(f"| `{r['designation']}` | {r['expected_games_missed']:.4f} | "
                 f"×{r['rate_multiplier']:.4f} |")
    L += ["",
          "---", "",
          "## 3. ⭐ The no-op control — why any number below can be trusted at all", "",
          f"With an EMPTY designation map the counterfactual must move **exactly zero** ranks on "
          f"every board, and the re-derived baseline rank must agree with the PUBLISHED "
          f"`overall_rank` exactly. Measured across **{s['no_op_control']['boards_checked']} "
          f"boards**: "
          f"{'✅ PASS' if s['no_op_control']['passes'] else '⛔ FAIL'} — "
          f"{max(s['no_op_control']['rank_moves_under_an_empty_designation_map'].values())} max "
          f"rank moves, agreement "
          f"{min(s['no_op_control']['recomputed_baseline_agrees_with_published_rank'].values()):.4f}.",
          "",
          "⚠️ This control is not decoration. Its first run reported **1,715 of 1,716 rows moving "
          "under an empty map**, because the board's key is `(config_name, n_teams)` and not "
          "`config_name` — every config publishes a 10-team AND a 12-team board with different "
          "replacement levels. Grouping on the config alone concatenated two boards and fabricated "
          "a rank move for almost every player.", ""]
    if reh:
        L += ["---", "",
              "## 4. ⛔ OUT-OF-SCOPE REHEARSAL — NOT A RESULT", "",
              "The discount applied to the PRESEASON tags the registered scope rule REFUSES. Its "
              "purpose is to prove the board arithmetic, the id join, the label crosswalk and the "
              "renderer all execute against real producer output BEFORE the operator's Week-1 run — "
              "otherwise that run would be this code's first-ever execution. ⛔ **These numbers are "
              "not a counterfactual and must never be quoted as one.**", "",
              "⚠️ It earned its place: with the rehearsal reporting a plausible ZERO, the label "
              "crosswalk was found to be silently broken (the feed emits `Questionable`, the model's "
              "levels are lower-case, so every multiplier resolved to NaN and defaulted to 1.0 — "
              "89 designated players on the board and no discount applied, with no error). An "
              "unmapped label now REFUSES instead of defaulting.", "",
              "| board | designated rows | ranks moved | max abs move |", "|---|---|---|---|"]
        for k in sorted(reh):
            v = reh[k]
            L.append(f"| `{k}` | {v['designated_rows_on_board']} | {v['rows_whose_rank_moved']} | "
                     f"{v['max_abs_rank_move']} |")
        sf = reh.get("superflex__12team") or next(iter(reh.values()))
        L += ["", f"**Top {min(TOP_N, len(sf['top_moves']))} moves, `superflex__12team`** (a "
                  "per-position level change is NOT shielded in superflex — NF-TR2b):", "",
              "| player | pos | designation | rank before | rank after | move | games |",
              "|---|---|---|---|---|---|---|"]
        for m in sf["top_moves"][:TOP_N]:
            L.append(f"| {m['player']} | {m['position']} | `{m['designation']}` | "
                     f"{m['rank_before']} | {m['rank_after']} | {m['rank_move']:+d} | "
                     f"{m['proj_games']} |")
        L += ["", "⚠️ Read the SHAPE, not the values: a ×0.9629 `questionable` cut moves mid-board "
                  "players 20–37 ranks because that region is dense. A real Week-1 report carries "
                  "`out` at ×0.8639 — roughly four times the cut — so the in-scope effect will be "
                  "materially larger than this rehearsal.", ""]
    else:
        L += ["---", "",
              "## 4. The in-scope counterfactual", "",
              "| board | designated rows | ranks moved | max abs move |", "|---|---|---|---|"]
        for k in sorted(live_leg):
            v = live_leg[k]
            L.append(f"| `{k}` | {v['designated_rows_on_board']} | {v['rows_whose_rank_moved']} | "
                     f"{v['max_abs_rank_move']} |")
        L += [""]
    L += ["---", "",
          "## 5. What this is NOT", "",
          "- ⛔ **Not a capture-pinned rebuild.** The registered ship path's step 1 rebuilds the "
          "board against a pinned baseline with matched market vintages (NF-INJ2c: a pin whose "
          "market inputs are a different day is not a pin). That is an OPERATOR step and it is what "
          "produces the publish-candidate board. This is a READ on the published board — it gives "
          "the decision-relevant magnitude beforehand.",
          "- ⛔ **Not a publish.** Nothing here writes a served artifact.",
          "- ⛔ **Not evidence the discount is small.** Today's zero is the SCOPE RULE refusing "
          "every row, which is uninformative — never a passed check (NF1.7 (a) / NF-D20).", ""]
    return "\n".join(L)


# ══════════════════════════════════════════════════════════════════════════════════════════════
def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="NF-INJ4b counterfactual + operator packet")
    ap.add_argument("--season", type=int, default=SEASON)
    ap.add_argument("--as-of", default=None,
                    help="ISO date the scope gate is evaluated at (default: today, UTC)")
    ap.add_argument("--out", default="nf_inj4b_counterfactual")
    args = ap.parse_args(argv)
    t0 = time.time()

    if not _FRAME.exists():
        raise SystemExit(f"{_FRAME} is absent — run `run_nf_inj4b_substrate` first.")
    frame = pd.read_parquet(_FRAME)

    # ⭐ THE CERTIFIED WINNER, read out of the decisive run rather than named here — the magnitude
    #   table must price what NF-INJ4b actually certified, and a second declaration of the arm is a
    #   second place for it to drift (the first cut of this file priced `PRIMARY_ARM`, which is the
    #   REGISTERED arm, not the WINNING one, and produced an `out` multiplier of 0.8682 against the
    #   certified 0.8639).
    decisive = _REPORT_DIR / "nf_inj4b_designation_duration.json"
    if not decisive.exists():
        raise SystemExit(f"{decisive.name} is absent — run the decisive bake-off first; a "
                         f"counterfactual must price the arm that was CERTIFIED, and refusing is "
                         f"the only alternative to guessing one (NF1.7 (a)).")
    winner = json.loads(decisive.read_text())["winner"]
    mag = magnitude_table(frame, winner)
    mult = {r["designation"]: r["rate_multiplier"] for r in mag["rows"]}
    live = live_designations(args.season)
    reg_start = regular_season_start(args.season)
    as_of = args.as_of or datetime.now(timezone.utc).date().isoformat()
    in_scope = bool(as_of >= reg_start)

    boards = EX.load_boards_lake(args.season)
    # ⭐ The SCOPE-GATED read: the registered rule refuses a preseason tag outright, so the applied
    #   designation map is EMPTY out of season and the counterfactual is exactly a no-op.
    scoped = live["designated"] if in_scope else {}
    scoped_moves = board_moves(boards, scoped, mult)
    # ⭐⭐ THE NO-OP CONTROL, and it is not decoration: with an EMPTY designation map the
    #    counterfactual MUST move exactly zero rows, on every board. The first cut of `board_moves`
    #    grouped on `config_name` alone — concatenating each config's 10- and 12-team boards — and
    #    reported 1,715 of 1,716 rows moving under that empty map. Every "rank move" in the operator
    #    packet would have been an artifact of the grouping. A two-sided control is what separates a
    #    counterfactual from a fabrication (NF1.7 (a)).
    empty_moves = board_moves(boards, {}, mult)
    no_op_control = {
        "boards_checked": len(empty_moves),
        "rank_moves_under_an_empty_designation_map":
            {k: v["rows_whose_rank_moved"] for k, v in empty_moves.items()},
        "recomputed_baseline_agrees_with_published_rank":
            {k: v["recomputed_baseline_rank_agrees_with_published"]
             for k, v in empty_moves.items()},
        "passes": all(v["rows_whose_rank_moved"] == 0 for v in empty_moves.values())
                  and all(v["recomputed_baseline_rank_agrees_with_published"] == 1.0
                          for v in empty_moves.values()),
    }
    if not no_op_control["passes"]:
        raise SystemExit(
            "⛔ THE NO-OP CONTROL FAILED: applying NO discount moves ranks, or the re-derived "
            "baseline rank disagrees with the published one. The counterfactual arithmetic is not "
            "measuring the published board, and every figure it would produce is an artifact. "
            f"{json.dumps(no_op_control, indent=2)}")
    # ⭐ The REHEARSAL: the same leg driven with the designations the scope rule refused, so the
    #   arithmetic, the id join and the renderer are all EXERCISED against real producer output.
    #   ⛔ NOT A RESULT.
    rehearsal = board_moves(boards, live["designated"], mult) if not in_scope else None

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "story": "NF-INJ4b", "node": "4-ship-path/counterfactual",
        "deploy_held": True, "best_alpha": 0, "changes_nothing": True,
        "season": args.season, "as_of": as_of,
        "regular_season_start_measured": reg_start,
        "scope": {
            "rule": "REGULAR-SEASON weekly designations only (pre-registration §7). A PRESEASON tag "
                    "is out-of-population and gets NOTHING.",
            "in_scope": in_scope,
            "days_to_regular_season": (date.fromisoformat(reg_start)
                                       - date.fromisoformat(as_of)).days,
            "designations_refused_by_the_scope_rule":
                0 if in_scope else len(live["designated"]),
            "reading": (
                "IN SCOPE — the counterfactual below is a real read."
                if in_scope else
                "⚠️ OUT OF SCOPE — every live designation is a PRESEASON tag, so the registered "
                "scope rule refuses all of them and the counterfactual is EXACTLY a no-op. This is "
                "INACTIVE, therefore UNINFORMATIVE: ⛔ it is NOT evidence the discount is small, "
                "and it is NOT a passed check (NF1.7 (a) / NF-D20). The pre-registration predicted "
                "this forward; it is measured here rather than assumed."),
        },
        "live_feed": {k: v for k, v in live.items() if k != "designated"},
        "magnitude_table": mag,
        "no_op_control": no_op_control,
        "counterfactual_under_the_scope_rule": scoped_moves,
        "out_of_scope_rehearsal": (
            {"⛔ NOT A RESULT": "the discount applied to PRESEASON tags the registered scope rule "
                               "REFUSES, purely to prove the board arithmetic, the id join and the "
                               "renderer execute against real producer output before the operator's "
                               "Week-1 run. ⛔ Never quote these numbers as a counterfactual.",
             "moves": rehearsal} if rehearsal is not None else None),
        "elapsed_s": round(time.time() - t0, 2),
    }
    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (_REPORT_DIR / f"{args.out}.json").write_text(json.dumps(summary, indent=2, default=str))
    (_REPORT_DIR / f"{args.out}.md").write_text(render(summary))
    print(json.dumps({
        "in_scope": in_scope, "regular_season_start": reg_start, "as_of": as_of,
        "live_by_designation": live["by_designation"],
        "refused_by_scope": summary["scope"]["designations_refused_by_the_scope_rule"],
        "magnitudes": {r["designation"]: r["rate_multiplier"] for r in mag["rows"]},
        "no_op_control_passes": no_op_control["passes"],
        "scoped_rank_moves": {c: v["rows_whose_rank_moved"] for c, v in scoped_moves.items()},
        "rehearsal_rank_moves": ({c: v["rows_whose_rank_moved"] for c, v in rehearsal.items()}
                                 if rehearsal else None),
        "elapsed_s": summary["elapsed_s"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
