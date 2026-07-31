"""build_prospect_board.py — MLB Edge-E8.0(+E8.0b) runner: the LEAN dynasty prospect draft board.

Joins the three views of a prospect into ONE ranked, human-legible board the operator can draft off
on 8/3, and exports it as CSV + (if an xlsx engine is importable) a multi-tab workbook.

    THE SCOUTS                             OURS                        THEIRS (optional)
    FanGraphs THE BOARD + MLB Pipeline    E7.3 / E7.3p MiLB→MLB MLE    Prospect Savant expected stats
    FV/rank + Pipeline's Top100/org-30    MLB-equiv K%/BB%/ISO/GB%     xwOBA · EV · whiff · velo
    + a rank CONSENSUS across them        + parameter uncertainty
              └────────────── E7.4 dim_player_xref ──────────────┘
                       (fg_minor_id / MLBAM → MLBAM, no fuzzy leg)

⭐ E8.0b (2026-07-31): folds E7.11's MLB Pipeline source + consensus IN, so this is the single file
the operator opens for the 8/3 draft — not a second, separate consensus export. MLB Pipeline ranks
~165 players FanGraphs' board omits entirely; those are unioned in (`build_consensus_assembly.
fold_pipeline_into_e8_0_board`, reusing E7.11's `merge_pipeline_ranks` + `consensus.attach_consensus`
verbatim) rather than left as draft-relevant blanks. Consensus = EQUAL WEIGHT (mean of the ranks
that exist) — E7.14, the accuracy study that could justify a different weight, has not landed.
`--skip-pipeline-consensus` is an emergency escape hatch back to the plain FanGraphs-only board.

SF-FREE — pure DuckDB over the S3 lake. Not on any serving path: this writes files, nothing else.

🚨 THE BOARD HAS EXACTLY ONE VALID READER. It is read through
`betting_ml.scripts.milb_xref.player_xref.register_board` (a Delta ACID file list). A `delta_scan`
hard-errors on its void-typed column, and a parquet glob silently unions TOMBSTONED ingest
generations — which fabricated an 84.2% match rate where the truth was 99.3% during E7.4. Guarded by
`betting_ml/tests/test_the_board_reader_guard.py`.

🔒 HONEST FRAME (`best_alpha = 0`): this is "FanGraphs + MLB Pipeline consensus + our independent
MLE-translated line + where they disagree". It is NOT a ranking that claims to beat any source. Per
E7.8 the board is POSITION-DIFFERENTIATED — FV leads for arms (it complements our line), our MLE +
age-rel-to-level leads for bats (FV substitutes) — and per E7.3 the K%/BB% columns carry more
confidence than ISO, which is weak-but-real. wOBA is absent and stays absent (a measured null).

⚠️ OPERATOR-RUN (S3 I/O over ~40k xref rows + 26k MLE rows + ~14k Pipeline rows; ~1–3 min).
`--prospect-savant` adds 8 one-time HTTP calls to an UNOFFICIAL hobbyist endpoint (cached to disk;
opt-in on purpose).

    # LAPTOP — the 8/3 board, FanGraphs + MLB Pipeline consensus + our MLE, xlsx + CSV:
    AWS_DEFAULT_REGION=us-east-2 uv run --with openpyxl python -m \
        betting_ml.scripts.prospect_board.build_prospect_board --prospect-savant

    # CSV only (no xlsx engine needed):
    AWS_DEFAULT_REGION=us-east-2 uv run python -m \
        betting_ml.scripts.prospect_board.build_prospect_board

Outputs (default `<out>` = ablation_results/e8_0_artifacts):
  * `<out>/e8_0_prospect_board.csv`            — the full board, FanGraphs ∪ MLB-Pipeline-only,
                                                 with per-source + consensus columns (the 8/3 minimum)
  * `<out>/e8_0_prospect_board_{AL,NL}.csv`    — the single-league splits
  * `<out>/e8_0_prospect_board.xlsx`           — All / AL / NL / Hitters / Pitchers / Minors only /
                                                 By blend / Disagreements / Pipeline-only /
                                                 How to read this  (if openpyxl)
  * `<out>/e8_0_join_report.json`              — the match-rate + pipeline + consensus report
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
from betting_ml.scripts.prospect_board.build_consensus_assembly import (  # noqa: E402
    fold_pipeline_into_e8_0_board,
)
from betting_ml.scripts.prospect_board.consensus import ConsensusError, format_consensus_report  # noqa: E402

log = logging.getLogger("e8_0.board")

_DEFAULT_OUT = (_PROJECT_ROOT / "quant_sports_intel_models/baseball/edge_program/"
                "ablation_results/e8_0_artifacts")

MLE_BATTERS = f"{MILB}/derived/mle_projections"
MLE_PITCHERS = f"{MILB}/derived/mle_projections_pitchers"
XREF = f"{MILB}/derived/dim_player_xref"
# E7.11's MLB Pipeline snapshot — the E8.0b second source. Owned here (not `build_consensus.py`) so
# `build_prospect_board.py` never has to import the E7.11 RUNNER (only its pure `_assembly` module) —
# `build_consensus.py` imports `_connect`/`load_inputs` FROM this module already, so the dependency
# would otherwise be circular.
PIPELINE_TABLE = f"{MILB}/mlb_pipeline_rankings"

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
    # ── E8.0b (2026-07-31): MLB Pipeline folded in as a second source + a consensus across them ──
    ("on_fangraphs_board",
     "FALSE = MLB Pipeline ranks this player but FanGraphs' board does not carry him at all - the "
     "loudest disagreement two sources can produce, so he is ADDED as a row rather than dropped by "
     "the join. His FanGraphs columns (fv, overall_rank, mle_*, blend_score...) are blank because "
     "there is no FanGraphs row and no MLE line was ever joined for him - blank means NOT RANKED "
     "BY THEM / NEVER SCORED, not 'ungraded'. See the 'Pipeline-only' tab."),
    ("pipeline_overall_rank / pipeline_org_rank",
     "MLB Pipeline's own Top 100 place and organizational Top-30 place (E7.11) - free, MLBAM-keyed, "
     "page-read from an allowed path (their JSON API is robots-disallowed and is never called)."),
    ("consensus_rank / consensus_rank_mean / consensus_tier",
     "The mean of the OVERALL ranks that exist for this player across FanGraphs and MLB Pipeline "
     "(EQUAL WEIGHT - averaging one number when only one source ranked him returns that number), "
     "and the board's ordering / tier bucket of those means. A source that only publishes a Top 100 "
     "has said NOTHING about player #340 - unranked is averaged over, never imputed."),
    ("⚠️ consensus_n_sources / consensus_confidence - READ THIS BESIDE EVERY CONSENSUS NUMBER",
     "How many sources actually ranked him. A 1-source 'consensus' is just that source. "
     "consensus_rank_spread (max-min of the contributing ranks) is NULL, not 0.0, for a 1-source "
     "row - 0.0 there would read as 'the sources agree exactly', the opposite of what one opinion "
     "means."),
    ("org_consensus_*",
     "The same aggregation over WITHIN-ORGANIZATION ranks (FanGraphs org_rank + MLB Pipeline's org "
     "Top 30) - much wider coverage than the overall consensus (~900+ players vs ~130). Never "
     "averaged with the overall scope: org rank 1 on a thin farm system is not overall rank 1."),
    ("vs_consensus_fangraphs_overall / vs_consensus_pipeline_overall (+ the _org siblings)",
     "How much HIGHER that one source ranks him than is usual for a player at that consensus level, "
     "in percentile points - a RESIDUAL (board_assembly.residual_vs_fit), not source_rank minus "
     "consensus_rank (two imperfectly-correlated rankings regress toward each other at the "
     "extremes, so the raw gap flags the whole top of the board and is a re-encoding of rank, not a "
     "disagreement). Computed ONLY where consensus_n_sources >= 2 - a source cannot disagree with a "
     "consensus it alone constitutes."),
    ("⭐ mle_vs_consensus",
     "THE DIFFERENTIATED VIEW, extended: how much higher OUR translated line scores him than is "
     "usual for a player the (FanGraphs + Pipeline) consensus places there. Also a residual, fitted "
     "within player type. A conversation starter, not a verdict - same as 'disagreement' above, "
     "just measured against the consensus instead of FV alone."),
    ("pipeline_grade_*",
     "MLB Pipeline's own 20-80 tool grades, parsed BEST-EFFORT from the prose of their scouting "
     "report (not published as fields). Blank means not published or not parsed - never zero. "
     "`grade_*` without the prefix are FanGraphs' grades."),
    ("Pipeline-only tab",
     "The ~165 players MLB Pipeline ranks that the FanGraphs board omits entirely (E7.11/E8.0b) - "
     "the reason this board no longer has draft-relevant blanks where a Pipeline top-100/org-30 "
     "talent used to be invisible. Sorted by pipeline_overall_rank."),
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


def load_pipeline_ranks(conn, *, season: int | None = None,
                        from_dir: Path | None = None) -> pd.DataFrame:
    """The E7.11 MLB Pipeline snapshot — newest `as_of_date` of the newest (or requested) season.

    Owned here (moved from `build_consensus.py` for E8.0b) rather than duplicated: `build_consensus`
    already imports `_connect`/`load_inputs` FROM this module, so this module cannot import back from
    it without a cycle. `build_consensus.py` now imports this function from here instead.

    `from_dir` re-parses the ingest's cached HTML instead of reading the Delta table — lets a run
    prove the join end-to-end before the S3 write exists.
    """
    if from_dir is not None:
        from betting_ml.scripts.prospect_board.mlb_pipeline import (
            ORG_SLUG_TO_ABBREV, TOP100_LIST, parse_rankings_page,
        )
        rows: list[dict] = []
        for list_name in [TOP100_LIST, *sorted(ORG_SLUG_TO_ABBREV)]:
            path = from_dir / f"{season}_{list_name}.html"
            if not path.exists():
                log.warning("cached page missing: %s — that organization will be ABSENT from the "
                            "Pipeline source (its players read as unranked).", path.name)
                continue
            rows.extend(parse_rankings_page(path.read_text(encoding="utf-8"),
                                            season=season, list_name=list_name))
        return pd.DataFrame(rows)

    season_clause = (f"where season = {int(season)}" if season is not None
                     else "where season = (select max(season) from t)")
    return conn.execute(f"""
        with t as (select * from delta_scan('{PIPELINE_TABLE}')),
             s as (select * from t {season_clause}),
             newest as (select max(as_of_date) as as_of_date from s)
        select * from s join newest using (as_of_date)
    """).df()


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
    p.add_argument("--pipeline-season", type=int, default=None,
                   help="MLB Pipeline snapshot season for the E8.0b consensus fold (default: the "
                        "newest ingested)")
    p.add_argument("--pipeline-from-dir", default=None,
                   help="re-parse the E7.11 ingest's cached HTML instead of reading the Delta table")
    p.add_argument("--skip-pipeline-consensus", action="store_true",
                   help="ship the plain FanGraphs-only E8.0 board (no MLB Pipeline union, no "
                        "consensus columns) — an emergency escape hatch only; E8.0b's whole point "
                        "is that this stays OFF for the 8/3 board")
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

    # ── E8.0b: fold MLB Pipeline in as a second source + a consensus across it and FanGraphs ──────
    consensus_rep = None
    if not args.skip_pipeline_consensus:
        pipeline_season = args.pipeline_season or int(board["season"].max())
        pipeline = load_pipeline_ranks(
            conn, season=(pipeline_season if args.pipeline_from_dir else args.pipeline_season),
            from_dir=Path(args.pipeline_from_dir) if args.pipeline_from_dir else None)
        if pipeline.empty:
            raise ConsensusError(
                "the MLB Pipeline snapshot is EMPTY — run `uv run python "
                "scripts/ingest_mlb_pipeline_to_s3.py --season "
                f"{pipeline_season}` first. Refusing to silently ship a FanGraphs-only board when "
                "the 8/3 board requires the consensus folded in — pass --skip-pipeline-consensus "
                "for an emergency FanGraphs-only export instead."
            )
        log.info("loaded pipeline rankings: %d rows, %d distinct players",
                 len(pipeline), pipeline["mlbam_id"].nunique())
        final, fold_report = fold_pipeline_into_e8_0_board(
            final, pipeline, strict_league=not args.allow_unmapped_orgs)
        report["pipeline_join"] = fold_report["pipeline"]
        consensus_rep = fold_report["consensus"]
        report["pipeline_as_of_date"] = (str(pipeline["as_of_date"].max())
                                         if "as_of_date" in pipeline.columns else None)
    report["pipeline_consensus_included"] = not args.skip_pipeline_consensus

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
    if consensus_rep is not None:
        print(format_consensus_report(consensus_rep, extra=[
            "", f"  pipeline snapshot as-of : {report.get('pipeline_as_of_date')}",
            "  ⭐ E8.0b: MLB Pipeline players FanGraphs' board omits are on the 'Pipeline-only' tab.",
        ]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
