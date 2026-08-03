"""build_consensus.py — MLB Edge-E7.11 runner: the MULTI-SOURCE prospect-ranking consensus.

Extends the E8.0 board (FanGraphs FV alone) with independent scouting sources, a consensus across
them, where the sources disagree, and where OUR translated line disagrees with all of them.

    THE SCOUTS (several, independent)          OURS
    FanGraphs THE BOARD  overall + org rank    E7.3/E7.3p MiLB→MLB MLE line
    MLB Pipeline         Top 100 + org Top 30  (+ age-relative-to-level)
    BA / Law / ESPN / BP / Prospects Live      via E8.0's model_score
      └── MANUAL hand-key only, never scraped
              └────────── consensus ──────────┘ ──── mle_vs_consensus ────┘
                     all keyed on MLBAM (E7.4 `dim_player_xref`, no fuzzy leg)

SF-FREE — pure DuckDB over the S3 lake. Not on any serving path: this writes files, nothing else.

🚨 THE BOARD HAS EXACTLY ONE VALID READER (`player_xref.register_board`) — `delta_scan` hard-errors
on its void-typed column and a parquet glob unions TOMBSTONED generations. Inherited via E8.0's
`load_inputs`; do not re-derive it here.

🔒 HONEST FRAME (`best_alpha = 0`): a consensus is a DESCRIPTION. It is not a claim to beat any
source, and a disagreement is not an edge — it is a shortlist for a second look. Paywalled and
robots-restricted sources are labelled `manual` and are hand-keyed by the operator, never scraped.

⚠️ OPERATOR-RUN (S3 I/O over ~40k xref rows + 26k MLE rows; ~1–3 min).

    # LAPTOP — the consensus board (FanGraphs + MLB Pipeline), xlsx + CSV:
    AWS_DEFAULT_REGION=us-east-2 uv run --with openpyxl python -m \
        betting_ml.scripts.prospect_board.build_consensus

    # …plus hand-keyed paywalled second opinions (one --manual per source):
    AWS_DEFAULT_REGION=us-east-2 uv run --with openpyxl python -m \
        betting_ml.scripts.prospect_board.build_consensus \
        --manual baseball_america=~/ba_top100.csv --manual keith_law=~/law_top100.csv

    # Write the hand-key template + the source-access notes, then exit:
    uv run python -m betting_ml.scripts.prospect_board.build_consensus --write-manual-template

Outputs (default `<out>` = ablation_results/e7_11_artifacts):
  * `<out>/e7_11_consensus_board.csv`          — the full universe with every source + consensus
  * `<out>/e7_11_consensus_board_{AL,NL}.csv`  — the single-league splits
  * `<out>/e7_11_consensus_board.xlsx`         — All / Consensus top 100 / Source disagreements /
                                                 Us vs consensus / Pipeline-only / Coverage /
                                                 How to read this  (if openpyxl)
  * `<out>/e7_11_consensus_report.json`        — coverage + disagreement counts
  * `<out>/manual_source_template.csv`         — the hand-key schema (with --write-manual-template)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.scripts.prospect_board.board_assembly import (  # noqa: E402
    ProspectBoardError,
    assemble_board,
)
from betting_ml.scripts.prospect_board.build_consensus_assembly import (  # noqa: E402
    HOW_TO_READ,
    build_sources,
    consensus_column_order,
    consensus_sheets,
    merge_pipeline_ranks,
)
from betting_ml.scripts.prospect_board.consensus import (  # noqa: E402
    MANUAL_CSV_COLUMNS,
    PAYWALLED_SOURCES,
    ConsensusError,
    attach_consensus,
    coverage_table,
    format_consensus_report,
    manual_template_frame,
    resolve_manual_source,
)
from betting_ml.scripts.prospect_board.mlb_pipeline import PIPELINE_SOURCE  # noqa: E402

log = logging.getLogger("e7_11.consensus")

_DEFAULT_OUT = (_PROJECT_ROOT / "quant_sports_intel_models/baseball/edge_program/"
                "ablation_results/e7_11_artifacts")


# ── Inputs ───────────────────────────────────────────────────────────────────────────────────
#
# `load_pipeline_ranks` (+ `PIPELINE_TABLE`) now live in `build_prospect_board.py` (E8.0b,
# 2026-07-31) — E8.0's board runner folds this same MLB Pipeline snapshot + consensus INTO the 8/3
# board, and since this module already imports `_connect`/`load_inputs` FROM `build_prospect_board`,
# the function moved rather than being duplicated (this module importing the other way would cycle).

def load_manual_sources(specs: list[str], universe: pd.DataFrame) -> tuple[list[pd.DataFrame], dict]:
    """`name=path.csv` specs → resolved (mlbam_id, rank_<name>) frames + a per-source report.

    ⛔ Nothing here fetches anything. A manual source EXISTS only as a file the operator hand-keyed
    from a page they have legitimate access to; that is the entire compliance story for the
    paywalled and robots-restricted sources.
    """
    frames: list[pd.DataFrame] = []
    reports: dict = {}
    for spec in specs:
        if "=" not in spec:
            raise ConsensusError(
                f"--manual expects `name=path.csv`, got {spec!r}. Known paywalled/restricted "
                f"source names: {sorted(PAYWALLED_SOURCES)}"
            )
        name, _, path = spec.partition("=")
        name = name.strip()
        frame = pd.read_csv(Path(path).expanduser())
        resolved, report = resolve_manual_source(frame, universe, source_name=name)
        frames.append(resolved)
        reports[name] = report
        log.info("manual source %-22s %d/%d rows resolved to an MLBAM id (%s)",
                 name, report["resolved"], report["rows"], report["by_method"])
        if report["unresolved_rows"]:
            log.warning("  ⚠️ %d row(s) UNRESOLVED — they are NOT in the consensus. Add an "
                        "`mlbam_id` column for these and re-run: %s",
                        report["rows"] - report["resolved"],
                        [r["player_name"] for r in report["unresolved_rows"][:8]])
    return frames, reports


# ── Assembly ─────────────────────────────────────────────────────────────────────────────────

def build(board: pd.DataFrame, xref: pd.DataFrame, mle_bat: pd.DataFrame, mle_pit: pd.DataFrame,
          pipeline: pd.DataFrame, manual_frames: list[pd.DataFrame], manual_names: list[str], *,
          mle_sb: pd.DataFrame | None = None,
          min_pa: float = 100.0, strict_league: bool = True) -> tuple[pd.DataFrame, dict]:
    """E8.0 board + every extra source → the consensus universe + the report."""
    e80, join_report = assemble_board(board, xref, mle_bat, mle_pit, None, mle_sb=mle_sb,
                                      min_pa=min_pa, strict_league=strict_league)
    e80["on_fangraphs_board"] = True
    e80["mlbam_id"] = e80["mlbam_id"].astype("string")

    universe, pipeline_report = merge_pipeline_ranks(e80, pipeline)
    for name, frame in zip(manual_names, manual_frames):
        frame = frame.copy()
        frame["mlbam_id"] = frame["mlbam_id"].astype("string")
        universe = universe.merge(frame.drop(columns=["match_method"], errors="ignore"),
                                  on="mlbam_id", how="left")

    sources = build_sources(universe, manual_names)
    universe, report = attach_consensus(universe, sources)
    report["join"] = join_report
    report["pipeline"] = pipeline_report
    universe = universe.sort_values(
        ["consensus_rank", "org_consensus_rank", "fv"],
        ascending=[True, True, False], na_position="last").reset_index(drop=True)
    universe.insert(0, "consensus_board_rank", np.arange(1, len(universe) + 1))
    return universe[consensus_column_order(universe)], report


# ── Export ───────────────────────────────────────────────────────────────────────────────────

def _xlsx_engine() -> str | None:
    for engine in ("openpyxl", "xlsxwriter"):
        try:
            __import__(engine)
            return engine
        except ImportError:
            continue
    return None


def write_exports(board: pd.DataFrame, out_dir: Path, report: dict, sources,
                  *, stem: str = "e7_11_consensus_board") -> list[Path]:
    """CSV always, xlsx when an engine is importable (the E8.0 contract: a missing optional
    dependency must never be the reason the operator has no board)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    sheets = consensus_sheets(board, coverage_table(board, sources))

    csv_path = out_dir / f"{stem}.csv"
    board.to_csv(csv_path, index=False)
    written.append(csv_path)
    for lg in ("AL", "NL"):
        path = out_dir / f"{stem}_{lg}.csv"
        board[board["mlb_league"] == lg].to_csv(path, index=False)
        written.append(path)

    engine = _xlsx_engine()
    if engine is None:
        log.warning("no xlsx engine installed — wrote CSVs only. Rerun with "
                    "`uv run --with openpyxl python -m "
                    "betting_ml.scripts.prospect_board.build_consensus` for the workbook.")
    else:
        xlsx_path = out_dir / f"{stem}.xlsx"
        legend = pd.DataFrame(HOW_TO_READ, columns=["column / topic", "what it means"])
        with pd.ExcelWriter(xlsx_path, engine=engine) as xl:
            legend.to_excel(xl, sheet_name="How to read this", index=False)
            for name, frame in sheets.items():
                frame.to_excel(xl, sheet_name=name[:31], index=False)
        written.append(xlsx_path)
        log.info("wrote %s (%d tabs, engine=%s)", xlsx_path.name, len(sheets) + 1, engine)

    report_path = out_dir / "e7_11_consensus_report.json"
    report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    written.append(report_path)
    return written


def write_manual_template(out_dir: Path) -> Path:
    """The hand-key schema + a README naming which sources are manual and why."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "manual_source_template.csv"
    manual_template_frame().to_csv(path, index=False)
    notes = out_dir / "manual_source_ACCESS.md"
    lines = [
        "# E7.11 — MANUAL (hand-keyed) ranking sources",
        "",
        "These sources are **never scraped**. Each is behind a paywall or a robots restriction, so",
        "the only compliant way to include one is for a person with legitimate access to hand-key",
        "the publicly-listed ranking into a CSV.",
        "",
        f"## Schema (`{path.name}`)",
        "",
        "| column | required | notes |",
        "|---|---|---|",
        "| `rank` | ✅ | 1 = best. The source's own published number. |",
        "| `player_name` | ✅ | As the source spells it; accents/suffixes are normalized. |",
        "| `org` | recommended | Team abbreviation — disambiguates same-name players. |",
        "| `mlbam_id` | **preferred** | If supplied, the row joins deterministically and no name "
        "matching happens at all. |",
        "",
        "Rows that resolve to no MLBAM id are **reported and excluded**, never guessed at — a "
        "hand-keyed Top 100 with 4 unmatched rows is a 96-player source and says so.",
        "",
        "## The sources",
        "",
    ]
    for name, note in PAYWALLED_SOURCES.items():
        lines.append(f"* **`{name}`** — {note}")
    lines += [
        "",
        "## Use",
        "",
        "```bash",
        "AWS_DEFAULT_REGION=us-east-2 uv run --with openpyxl python -m \\",
        "    betting_ml.scripts.prospect_board.build_consensus \\",
        "    --manual baseball_america=~/ba_top100.csv \\",
        "    --manual keith_law=~/law_top100.csv",
        "```",
        "",
        f"Expected columns: `{', '.join(MANUAL_CSV_COLUMNS)}`.",
    ]
    notes.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log.info("wrote %s and %s", path, notes)
    return path


# ── Main ─────────────────────────────────────────────────────────────────────────────────────

def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="E7.11 — multi-source prospect-ranking consensus (FanGraphs + MLB Pipeline "
                    "+ hand-keyed second opinions)")
    p.add_argument("--out-dir", default=str(_DEFAULT_OUT))
    p.add_argument("--board-season", type=int, default=None,
                   help="board snapshot season (default: the newest on the lake)")
    p.add_argument("--pipeline-season", type=int, default=None,
                   help="MLB Pipeline snapshot season (default: the newest ingested)")
    p.add_argument("--pipeline-from-dir", default=None,
                   help="re-parse the ingest's cached HTML (--cache-dir) instead of reading the "
                        "Delta table — lets the consensus be built before the S3 write")
    p.add_argument("--manual", action="append", default=[], metavar="NAME=PATH.csv",
                   help="a hand-keyed ranking file (repeatable). NEVER scraped — see "
                        "--write-manual-template.")
    p.add_argument("--write-manual-template", action="store_true",
                   help="write the hand-key CSV template + the source-access notes, then exit")
    p.add_argument("--min-mle-pa", type=float, default=100.0)
    p.add_argument("--allow-unmapped-orgs", action="store_true")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")
    os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-2")
    out_dir = Path(args.out_dir)

    if args.write_manual_template:
        write_manual_template(out_dir)
        return 0

    from betting_ml.scripts.prospect_board.build_prospect_board import (
        _connect, load_inputs, load_pipeline_ranks,
    )

    conn = _connect()
    board, xref, mle_bat, mle_pit, mle_sb = load_inputs(conn, board_season=args.board_season)
    if board.empty:
        raise ProspectBoardError(
            "the board snapshot is EMPTY — re-run the E7.7 ingest "
            "(`scripts/ingest_fangraphs_prospects_to_s3.py`) before building the consensus.")

    pipeline_season = args.pipeline_season or int(board["season"].max())
    pipeline = load_pipeline_ranks(
        conn, season=(pipeline_season if args.pipeline_from_dir else args.pipeline_season),
        from_dir=Path(args.pipeline_from_dir) if args.pipeline_from_dir else None)
    if pipeline.empty:
        raise ConsensusError(
            "the MLB Pipeline snapshot is EMPTY — run `uv run python "
            "scripts/ingest_mlb_pipeline_to_s3.py --season "
            f"{pipeline_season}` first. Refusing to call a one-source table a consensus.")
    log.info("loaded pipeline rankings: %d rows, %d distinct players",
             len(pipeline), pipeline["mlbam_id"].nunique())

    # The manual-name universe is the FanGraphs board itself (name+org), so a hand-keyed row is
    # resolved against prospects we already know — never against the full MLB player universe,
    # where name equality produced E7.4's false positive.
    universe_for_names = pd.DataFrame({
        "player_name": board["player_name"],
        "org": board["org"],
        "mlbam_id": board["fg_minor_id"].map(
            xref.set_index("fg_minor_id")["mlbam_id"].astype(str).to_dict()),
    })
    manual_frames, manual_reports = load_manual_sources(args.manual, universe_for_names)
    manual_names = [spec.split("=", 1)[0].strip() for spec in args.manual]

    final, report = build(board, xref, mle_bat, mle_pit, pipeline, manual_frames, manual_names,
                          mle_sb=mle_sb,
                          min_pa=args.min_mle_pa, strict_league=not args.allow_unmapped_orgs)
    report["manual_sources"] = manual_reports
    report["board_season"] = int(board["season"].max())
    report["board_as_of_date"] = str(board["as_of_date"].max())
    report["pipeline_as_of_date"] = (str(pipeline["as_of_date"].max())
                                     if "as_of_date" in pipeline.columns else None)

    sources = build_sources(final, manual_names)
    written = write_exports(final, out_dir, report, sources)
    print(format_consensus_report(report, extra=[
        "", f"  board snapshot as-of    : {report['board_as_of_date']} "
            f"(season {report['board_season']})",
        f"  pipeline snapshot as-of : {report['pipeline_as_of_date']}",
        "", "  WROTE:", *[f"    {w}" for w in written],
    ]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
