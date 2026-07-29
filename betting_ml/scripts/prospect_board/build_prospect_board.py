"""build_prospect_board.py — MLB Edge-E8.0 runner: the LEAN dynasty prospect draft board.

Joins the three views of a prospect into ONE ranked, human-legible board the operator can draft off
on 8/3, and exports it as CSV + (if an xlsx engine is importable) a multi-tab workbook.

    THE SCOUTS            OURS                              THEIRS (optional)
    FanGraphs THE BOARD   E7.3 / E7.3p MiLB→MLB MLE line    Prospect Savant expected stats
    FV · rank · ETA       MLB-equiv K% / BB% / ISO / GB%     xwOBA · EV · whiff · velo
    · tool grades         + parameter uncertainty
              └────────────── E7.4 dim_player_xref ──────────────┘
                       (fg_minor_id → MLBAM, 99.3%, no fuzzy leg)

SF-FREE — pure DuckDB over the S3 lake. Not on any serving path: this writes files, nothing else.

🚨 THE BOARD HAS EXACTLY ONE VALID READER. It is read through
`betting_ml.scripts.milb_xref.player_xref.register_board` (a Delta ACID file list). A `delta_scan`
hard-errors on its void-typed column, and a parquet glob silently unions TOMBSTONED ingest
generations — which fabricated an 84.2% match rate where the truth was 99.3% during E7.4. Guarded by
`betting_ml/tests/test_the_board_reader_guard.py`.

🔒 HONEST FRAME (`best_alpha = 0`): this is "FanGraphs consensus + our independent MLE-translated
line + where they disagree". It is NOT a ranking that claims to beat FanGraphs. Per E7.8 the board
is POSITION-DIFFERENTIATED — FV leads for arms (it complements our line), our MLE + age-rel-to-level
leads for bats (FV substitutes) — and per E7.3 the K%/BB% columns carry more confidence than ISO,
which is weak-but-real. wOBA is absent and stays absent (a measured null).

⚠️ OPERATOR-RUN (S3 I/O over ~40k xref rows + 26k MLE rows; ~1–3 min). `--prospect-savant` adds 8
one-time HTTP calls to an UNOFFICIAL hobbyist endpoint (cached to disk; opt-in on purpose).

    # LAPTOP — the 8/3 board, all three views, xlsx + CSV:
    AWS_DEFAULT_REGION=us-east-2 uv run --with openpyxl python -m \
        betting_ml.scripts.prospect_board.build_prospect_board --prospect-savant

    # CSV only (no xlsx engine needed):
    AWS_DEFAULT_REGION=us-east-2 uv run python -m \
        betting_ml.scripts.prospect_board.build_prospect_board

Outputs (default `<out>` = ablation_results/e8_0_artifacts):
  * `<out>/e8_0_prospect_board.csv`            — the full board (the 8/3 minimum)
  * `<out>/e8_0_prospect_board_{AL,NL}.csv`    — the single-league splits
  * `<out>/e8_0_prospect_board.xlsx`           — All / AL / NL / Hitters / Pitchers / By blend /
                                                 Disagreements / How to read this  (if openpyxl)
  * `<out>/e8_0_join_report.json`              — the match-rate report
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.scripts.milb_xref.player_xref import (  # noqa: E402
    MILB,
    _board_latest_sql,          # the board dedupe is load-bearing — reuse it, never re-derive it
    XrefSources,
    register_board,
)
from betting_ml.scripts.prospect_board.board_assembly import (  # noqa: E402
    ProspectBoardError,
    assemble_board,
    format_report,
    split_sheets,
)

log = logging.getLogger("e8_0.board")

_DEFAULT_OUT = (_PROJECT_ROOT / "quant_sports_intel_models/baseball/edge_program/"
                "ablation_results/e8_0_artifacts")

MLE_BATTERS = f"{MILB}/derived/mle_projections"
MLE_PITCHERS = f"{MILB}/derived/mle_projections_pitchers"
XREF = f"{MILB}/derived/dim_player_xref"

# The legend sheet. A board handed to a human without this is a board whose numbers get over-read —
# and over-reading is the specific failure mode the honest frame exists to prevent.
HOW_TO_READ = [
    ("WHAT THIS IS",
     "Three INDEPENDENT reads on every current FanGraphs Board prospect, side by side: the scouts "
     "(FanGraphs FV/rank/grades), US (our MiLB->MLB translated line), and optionally Prospect "
     "Savant's MiLB-Statcast expected stats. Plus where they disagree."),
    ("WHAT THIS IS NOT",
     "Not a ranking that claims to beat FanGraphs. No edge/win-rate claim is made or implied. "
     "The blend is a DISPLAY heuristic for ordering a draft board."),
    ("mlb_league",
     "AL/NL of the parent org. Dynasty leagues are single-league - filter on this first."),
    ("fv / overall_rank / org_rank",
     "FanGraphs THE BOARD, newest snapshot. The scouts' view, unmodified."),
    ("mle_k_pct / mle_bb_pct / mle_iso",
     "OUR MLB-EQUIVALENT projection for a batter, translated from his minor-league record "
     "(E7.3). Read K% and BB% with CONFIDENCE (out-of-sample translation corr 0.64 and 0.49); "
     "read ISO with CAUTION (0.43, weak-but-real - park- and pitching-quality dependent). "
     "wOBA is deliberately ABSENT: it carries no translatable signal (0.22, no better than "
     "knowing the player's level)."),
    ("mle_p_k_pct / mle_p_bb_pct / mle_p_gb_pct",
     "OUR MLB-equivalent projection for a pitcher (E7.3p). GB% is the STRONG one (0.55); K% and "
     "BB% are weak-but-real (~0.37) - pitcher stats translate materially worse than batter stats, "
     "which is exactly why FV leads the ordering for arms."),
    ("*_sd columns",
     "PARAMETER uncertainty on our projection. It ranks confidence correctly but is TOO TIGHT to "
     "read as a calibrated interval. Treat a wide sd as 'we don't know', never as a priced band."),
    ("mle_level / mle_pa",
     "Which level our line was computed at, and the sample behind it. A small mle_pa is a thin "
     "projection - the number and its sample always travel together."),
    ("mle_score",
     "Percentile (0-100, within player type) of our translated line. Each metric is weighted by "
     "its MEASURED translation strength, so a weakly-translating metric cannot dominate. Missing "
     "metrics are renormalized away, not scored as zero; mle_coverage says how complete it was."),
    ("age_vs_level / age_score",
     "Age minus the median age of board prospects AT THAT LEVEL. Negative = young for the level = "
     "good. This is the single most reliable prospect signal there is and it is part of the null "
     "E7.8 tested FV against."),
    ("model_score",
     "Our view: 75% translated line + 25% age-relative-to-level."),
    ("blend_score",
     "DISPLAY ordering. Pitchers 70% FV / 30% us; hitters 35% FV / 65% us. That split is the E7.8 "
     "verdict: FV adds real, gate-clearing lift on top of our line for ARMS (complements), but is "
     "largely redundant with our line for BATS (substitutes). The honest claim is that we know "
     "WHEN to trust the scouts - not that we beat them."),
    ("⚠️ scores are WITHIN player type",
     "fv_pctile, mle_score, age_score, model_score and blend_score are all percentiles among "
     "players of the SAME type - a hitter is ranked against hitters, a pitcher against pitchers. "
     "So a hitter's 90 and a pitcher's 90 each mean 'elite among his own kind', NOT 'equally "
     "valuable'. Cross-type ordering on the All / By blend tabs carries no positional-value claim; "
     "for that, use the Hitters and Pitchers tabs and apply your own league's scarcity."),
    ("disagreement",
     "How much HIGHER our score is than it usually is for a player with THAT FV, in percentile "
     "points (a residual, fit within player type). Positive = we like him more than his grade "
     "would predict. It is NOT model_score minus fv_pctile: that raw gap flags the whole top of "
     "the board as 'scouts higher' purely because two imperfectly-correlated rankings regress "
     "toward each other at the extremes. This column is a conversation starter, not a verdict."),
    ("in_majors",
     "This prospect is currently listed AT MLB (graduated, but still carries a Board grade). Most "
     "minor-league dynasty drafts do not make these players draftable - check your league's "
     "rules. The 'Minors only' tab is the board with them removed."),
    ("speed_flag",
     "STOLEN BASES ARE INVISIBLE TO OUR MLE - every target is a per-PA rate and SB is not in the "
     "substrate. Flagged from the scouts' own future-speed grade (60+). If your league scores SB, "
     "our score UNDER-RATES these players and you should say so out loud at the table."),
    ("ps_* columns",
     "PROSPECT SAVANT's numbers, not ours - their MiLB-Statcast expected stats, from an "
     "unofficial hobbyist API, captured as a one-time snapshot. A third orthogonal opinion. Never "
     "quote these as our model's output."),
    ("ps_xwoba / ps_ev / ps_barrel_pct / ps_hardhit_pct / ps_velo",
     "BATTED-BALL AND VELOCITY TRACKING IS TRIPLE-A ONLY. Below AAA these come back blank because "
     "there is no Hawk-Eye there - blank means NOT MEASURED, never zero. The plate-discipline "
     "rates (ps_whiff_pct, ps_chase_pct, ps_k_pct, ps_bb_pct, ps_gb_pct) and ps_xfip ARE real at "
     "every level."),
    ("blank MLE columns",
     "EXPECTED, not a bug. Complex/DSL/just-drafted prospects have an identity but no "
     "minor-league PA projection yet. Those players stay on the board on FV alone rather than "
     "being silently dropped."),
]


def _connect():
    """DuckDB with the S3 credential chain + the Delta extension (every input here is Delta)."""
    from scripts.utils.lakehouse_read import duck_connect

    conn = duck_connect()
    conn.execute("INSTALL delta; LOAD delta")   # LOUD on failure — a silent fallback is INC-31
    return conn


def load_inputs(conn, *, board_season: int | None = None) -> tuple[pd.DataFrame, ...]:
    """Read the four lake inputs. The board goes through `register_board` — the only valid reader."""
    register_board(conn)
    src = XrefSources(board="board_src", leaderboards="", milb_game_logs="",
                      mlb_player_profiles="", fg_mlb_hitting_raw="", fg_mlb_pitching_raw="")
    conn.execute(f"create or replace temp view _board_latest as {_board_latest_sql(src)}")
    season_clause = ""
    if board_season is not None:
        season_clause = f"where season = {int(board_season)}"
    else:
        season_clause = "where season = (select max(season) from _board_latest)"
    board = conn.execute(f"select * from _board_latest {season_clause}").df()

    xref = conn.execute(
        f"select fg_minor_id, mlbam_id from delta_scan('{XREF}') "
        "where fg_minor_id is not null and mlbam_id is not null"
    ).df()
    mle_bat = conn.execute(f"select * from delta_scan('{MLE_BATTERS}')").df()
    mle_pit = conn.execute(f"select * from delta_scan('{MLE_PITCHERS}')").df()
    log.info("loaded board=%d  xref=%d  mle_batters=%d  mle_pitchers=%d",
             len(board), len(xref), len(mle_bat), len(mle_pit))
    return board, xref, mle_bat, mle_pit


def _xlsx_engine() -> str | None:
    for engine in ("openpyxl", "xlsxwriter"):
        try:
            __import__(engine)
            return engine
        except ImportError:
            continue
    return None


def write_exports(board: pd.DataFrame, out_dir: Path, report: dict, *,
                  stem: str = "e8_0_prospect_board") -> list[Path]:
    """CSV always (the 8/3 guarantee), xlsx when an engine is importable.

    The CSVs come first and unconditionally: a missing optional dependency must never be the reason
    the operator has no board on draft day.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    sheets = split_sheets(board)

    csv_path = out_dir / f"{stem}.csv"
    board.to_csv(csv_path, index=False)
    written.append(csv_path)
    for lg in ("AL", "NL"):
        p = out_dir / f"{stem}_{lg}.csv"
        sheets[lg].to_csv(p, index=False)
        written.append(p)

    engine = _xlsx_engine()
    if engine is None:
        log.warning("no xlsx engine installed — wrote CSVs only. For the multi-tab workbook rerun "
                    "with:  uv run --with openpyxl python -m "
                    "betting_ml.scripts.prospect_board.build_prospect_board")
    else:
        xlsx_path = out_dir / f"{stem}.xlsx"
        legend = pd.DataFrame(HOW_TO_READ, columns=["column / topic", "what it means"])
        with pd.ExcelWriter(xlsx_path, engine=engine) as xl:
            legend.to_excel(xl, sheet_name="How to read this", index=False)
            for name, frame in sheets.items():
                frame.to_excel(xl, sheet_name=name[:31], index=False)
        written.append(xlsx_path)
        log.info("wrote %s (%d tabs, engine=%s)", xlsx_path.name, len(sheets) + 1, engine)

    report_path = out_dir / "e8_0_join_report.json"
    report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    written.append(report_path)
    return written


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="E8.0 — build the LEAN dynasty prospect draft board (export-first)")
    p.add_argument("--out-dir", default=str(_DEFAULT_OUT))
    p.add_argument("--board-season", type=int, default=None,
                   help="board snapshot season (default: the newest on the lake)")
    p.add_argument("--min-mle-pa", type=float, default=100.0,
                   help="minimum PA/TBF for a level's MLE line to be preferred over a lower level "
                        "(default 100; below it the largest-sample level is used instead)")
    p.add_argument("--prospect-savant", action="store_true",
                   help="also fetch Prospect Savant expected stats (UNOFFICIAL hobbyist endpoint; "
                        "one-time cached snapshot, 8 polite requests)")
    p.add_argument("--ps-refresh", action="store_true", help="ignore the Prospect Savant cache")
    p.add_argument("--ps-probe", action="store_true",
                   help="probe the Prospect Savant route shape and exit (no board is built)")
    p.add_argument("--ps-season", type=int, default=None,
                   help="Prospect Savant season (default: the board season)")
    p.add_argument("--allow-unmapped-orgs", action="store_true",
                   help="warn instead of failing when an org has no AL/NL mapping (NOT advised: "
                        "the league filter is what a single-league dynasty draft runs on)")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")
    os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-2")

    from betting_ml.scripts.prospect_board import prospect_savant as ps

    if args.ps_probe:
        season = args.ps_season or args.board_season or pd.Timestamp.utcnow().year
        print(json.dumps(ps.probe(season), indent=2))
        return 0

    out_dir = Path(args.out_dir)
    conn = _connect()
    board, xref, mle_bat, mle_pit = load_inputs(conn, board_season=args.board_season)
    if board.empty:
        raise ProspectBoardError(
            "the board snapshot is EMPTY — re-run the E7.7 ingest "
            "(`scripts/ingest_fangraphs_prospects_to_s3.py`) before building the draft board."
        )

    savant = None
    if args.prospect_savant:
        season = args.ps_season or int(board["season"].max())
        savant = ps.fetch_snapshot(season, out_dir / "prospect_savant_cache",
                                   refresh=args.ps_refresh)
        log.info("prospect-savant snapshot: %d players", len(savant))

    final, report = assemble_board(board, xref, mle_bat, mle_pit, savant,
                                   min_pa=args.min_mle_pa,
                                   strict_league=not args.allow_unmapped_orgs)
    report["board_season"] = int(board["season"].max())
    report["board_as_of_date"] = str(board["as_of_date"].max())
    report["min_mle_pa"] = args.min_mle_pa
    report["prospect_savant_included"] = bool(args.prospect_savant)

    written = write_exports(final, out_dir, report)
    print(format_report(report, extra=[
        "", f"  board snapshot as-of : {report['board_as_of_date']} "
            f"(season {report['board_season']})",
        "  ORDERING: default sort is FV, then our line. `blend_score` is the "
        "position-differentiated",
        "            display heuristic (E7.8: FV leads for ARMS, our MLE + age-rel-to-level "
        "leads for BATS).",
        "  🔒 best_alpha = 0 — no edge or win-rate claim. See the 'How to read this' tab.",
        "", "  WROTE:", *[f"    {w}" for w in written],
    ]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
