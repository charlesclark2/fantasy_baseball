"""build_prospect_comps.py — MLB Edge-E7.13 PHASE 1: attach historical COMPS to the E8.0 board.

Reads three artifacts that already exist on disk, attaches the comp engine's columns to the shipped
prospect board, and writes a comps-augmented CSV/XLSX plus a per-comp audit tab. No S3, no Snowflake,
no dbt — it is a pure re-export of a board that is already built, which is what makes it a
LOW-RISK add on a draft-day clock: it cannot break the board it reads.

    INPUT   ablation_results/e8_0_artifacts/e8_0_prospect_board.csv       (E8.0, the current board)
            ablation_results/e7_8_artifacts/fv_translation_cohort.parquet (E7.8, the COMP POOL)
            ablation_results/e7_3_artifacts/mle_graduated_pairs.parquet   (E7.3, batter MiLB lines)
            ablation_results/e7_3p_artifacts/mle_graduated_pairs_pitchers.parquet   (E7.3p, arms)

    OUTPUT  ablation_results/e7_13_artifacts/e7_13_prospect_board_comps.{csv,xlsx}
            ablation_results/e7_13_artifacts/e7_13_comp_detail.csv     (one row per prospect×comp)
            ablation_results/e7_13_artifacts/e7_13_comps_report.json

⚠️ WHY THE POOL IS E7.8's COHORT AND NOT THE E7.3 PAIRS. The pairs table is keyed on graduation —
its labelled rows are players who reached the majors, and its unlabelled rows are today's prospects
whose outcome is not known yet. Comping against it in either direction is the survivorship failure
`prospect_comps` §1 exists to prevent. E7.8's cohort is one row per (past board, prospect) WITH the
realized 3-season outcome attached and ZERO for the ~61% who never arrived — the busts are in the
pool, which is the whole point. The pairs table is used only for the query side's raw box counts.

🔒 The comp columns are DISPLAY. Whether a comp-derived term may enter the projection is the E7.13
Phase-2 question and is decided by `run_e7_13_comp_validation.py`, not here.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.scripts.prospect_board import prospect_comps as pc  # noqa: E402

log = logging.getLogger("e7_13.comps")

_ABL = _PROJECT_ROOT / "quant_sports_intel_models/baseball/edge_program/ablation_results"
DEFAULT_BOARD = _ABL / "e8_0_artifacts/e8_0_prospect_board.csv"
DEFAULT_POOL = _ABL / "e7_8_artifacts/fv_translation_cohort.parquet"
DEFAULT_PAIRS_BAT = _ABL / "e7_3_artifacts/mle_graduated_pairs.parquet"
DEFAULT_PAIRS_PIT = _ABL / "e7_3p_artifacts/mle_graduated_pairs_pitchers.parquet"
DEFAULT_OUT = _ABL / "e7_13_artifacts"


def _xlsx_engine() -> str | None:
    for eng in ("xlsxwriter", "openpyxl"):
        try:
            __import__(eng)
            return eng
        except ImportError:
            continue
    return None


def run(board_path: Path, pool_path: Path, pairs_bat: Path, pairs_pit: Path,
        out_dir: Path, *, k: int = pc.DEFAULT_K, metric: str = "gower",
        as_of_season: int | None = None, write: bool = True,
        rank_with_comps: bool = True) -> dict:
    board = pd.read_csv(board_path)
    board = board.loc[board["player_name"].notna()].reset_index(drop=True)
    cohort = pd.read_parquet(pool_path)

    season = int(as_of_season if as_of_season is not None
                 else pd.to_numeric(board.get("season"), errors="coerce").dropna().max())
    log.info("board=%d rows  cohort=%d rows  as_of_season=%d", len(board), len(cohort), season)

    report: dict = {"as_of_season": season, "board_rows": int(len(board)),
                    "cohort_rows": int(len(cohort)), "k": int(k), "metric": metric,
                    "by_type": {}}
    scored, details = [], []

    for ptype, pairs_path in (("batter", pairs_bat), ("pitcher", pairs_pit)):
        # two-way players are scored on BOTH sides of the board's own type split; the board itself
        # carries `player_type='two_way'` for 3 rows, which we route to the batter engine (their
        # board position and every populated grade on those rows is a bat).
        mask = board["player_type"].astype(str).isin(
            [ptype] + (["two_way"] if ptype == "batter" else []))
        sub = board.loc[mask].copy()
        if sub.empty:
            continue
        career = pc.collapse_pairs_to_career_line(pd.read_parquet(pairs_path), player_type=ptype)
        query = pc.build_query_profile(sub, career, player_type=ptype, as_of_season=season)
        pool = pc.build_pool(cohort, player_type=ptype)
        cfg = pc.CompConfig(k=k, metric=metric, name=f"comp_{metric}_k{k}")
        out, detail, rep = pc.attach_comps(query, pool, player_type=ptype,
                                           as_of_season=season, cfg=cfg)
        rep["profile_coverage"] = {
            "with_minor_line": float(query["minor_k_pct"].notna().mean())
            if "minor_k_pct" in query else 0.0,
            "with_fv": float(query["fv"].notna().mean()),
            "with_level": float(query["level_rank"].notna().mean()),
        }
        report["by_type"][ptype] = rep
        scored.append(out)
        details.append(detail)
        log.info("%s: %d scored, quality=%s", ptype, len(out), rep.get("comp_quality"))

    full = pd.concat(scored, ignore_index=True) if scored else board
    if "board_rank" in full.columns:
        full = full.sort_values("board_rank", na_position="last").reset_index(drop=True)
    if rank_with_comps:
        # ⭐ the comp read enters `model_score` — the key that actually sorts the board — and the
        # board is re-ranked on E8.0's own lexicographic keys. See prospect_comps §10.
        full = pc.attach_comp_ranking(full)
        moved = full["comp_rank_delta"].abs()
        report["ranking"] = {
            "comp_rank_weight": pc.COMP_RANK_WEIGHT,
            "rows_with_comp_score": int(full["comp_score"].notna().sum()),
            "rows_moved": int((moved > 0).sum()),
            "median_abs_move": float(moved.median()),
            "max_move_up": int(full["comp_rank_delta"].max()),
            "max_move_down": int(full["comp_rank_delta"].min()),
        }
    detail_all = pc.comp_detail_frame(details)

    # comp columns ride directly behind the identity block so they are visible without scrolling
    front = [c for c in ("board_rank", "board_rank_no_comps", "player_name", "org", "mlb_league", "position",
                         "player_type", "level", "age", "eta", "fv") if c in full.columns]
    comps = [c for c in pc.COMP_COLUMNS if c in full.columns]
    full = full[front + comps + [c for c in full.columns if c not in front + comps]]

    report["comp_column_count"] = len(comps)
    report["detail_rows"] = int(len(detail_all))
    report["comp_quality_overall"] = full["comp_quality"].value_counts().to_dict() \
        if "comp_quality" in full else {}

    if write:
        out_dir.mkdir(parents=True, exist_ok=True)
        full.to_csv(out_dir / "e7_13_prospect_board_comps.csv", index=False)
        detail_all.to_csv(out_dir / "e7_13_comp_detail.csv", index=False)
        (out_dir / "e7_13_comps_report.json").write_text(json.dumps(report, indent=2, default=str))
        eng = _xlsx_engine()
        if eng:
            with pd.ExcelWriter(out_dir / "e7_13_prospect_board_comps.xlsx", engine=eng) as xw:
                full.to_excel(xw, sheet_name="Board+Comps", index=False)
                for lg in ("AL", "NL"):
                    if "mlb_league" in full.columns:
                        full.loc[full["mlb_league"] == lg].to_excel(xw, sheet_name=lg, index=False)
                detail_all.to_excel(xw, sheet_name="Comp detail", index=False)
                pd.DataFrame(_readme_rows()).to_excel(xw, sheet_name="How to read", index=False)
        else:
            log.warning("no xlsx engine (xlsxwriter/openpyxl) — CSV only")
    return report


def _readme_rows() -> list[dict]:
    """The 'How to read' tab. A comp column without this tab invites exactly the over-reading the
    honest frame exists to prevent."""
    return [
        {"column": "comp_names", "means": "The 3 most similar HISTORICAL prospects, with the "
         "similarity distance in brackets (0 = identical profile; lower is closer)."},
        {"column": "comp_note", "means": "The honest one-liner: how many comps never reached MLB, "
         "how the rest turned out, and the outcome band."},
        {"column": "comp_quality", "means": "strong / fair / thin. Calibrated against how well "
         "players in this feature space typically match — 'strong' = closer than the median "
         "historical prospect's own comp set. THIN = read the band, not the median."},
        {"column": "comp_bust_rate", "means": "Share of the comps who never reached MLB inside "
         "their 3-season window. This is the downside, and it is usually the majority."},
        {"column": "comp_fp_median / comp_band_lo / comp_band_hi", "means": "Dynasty fantasy points "
         "the comps ACTUALLY accumulated in their first 3 seasons after the board — median and "
         "band. A band starting at 0 means most comparable players produced nothing."},
        {"column": "comp_n_never_reached / fringe / regular / impact", "means": "The comps' outcome "
         "tiers. 'fringe/regular/impact' split the historical DEBUTED population at its own median "
         "and 85th percentile, so each tier's share is a fact about the pool."},
        {"column": "—", "means": "WHAT THIS IS NOT: a projection. Comps are a similarity estimate "
         "with real uncertainty; the pool deliberately INCLUDES the players who busted, and no "
         "comp-derived number feeds the board's ranking or score."},
        {"column": "—", "means": "LEAKAGE: every comp comes from a board season whose entire "
         "3-season outcome window closed before this board's season, matched on what the comp "
         "looked like THEN — never on what he is now."},
    ]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="E7.13 — attach historical comps to the E8.0 board")
    p.add_argument("--board", default=str(DEFAULT_BOARD))
    p.add_argument("--pool", default=str(DEFAULT_POOL))
    p.add_argument("--pairs-batter", default=str(DEFAULT_PAIRS_BAT))
    p.add_argument("--pairs-pitcher", default=str(DEFAULT_PAIRS_PIT))
    p.add_argument("--out-dir", default=str(DEFAULT_OUT))
    p.add_argument("-k", "--k", type=int, default=pc.DEFAULT_K, help="neighbours per prospect")
    p.add_argument("--metric", default="gower", choices=("gower", "mahalanobis"))
    p.add_argument("--as-of-season", type=int, default=None)
    p.add_argument("--no-comp-ranking", action="store_true",
                   help="attach the comp COLUMNS but leave the board order untouched")
    p.add_argument("--dry-run", action="store_true", help="score but write nothing")
    p.add_argument("-v", "--verbose", action="store_true")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")
    rep = run(Path(a.board), Path(a.pool), Path(a.pairs_batter), Path(a.pairs_pitcher),
              Path(a.out_dir), k=a.k, metric=a.metric, as_of_season=a.as_of_season,
              write=not a.dry_run, rank_with_comps=not a.no_comp_ranking)
    print(json.dumps(rep, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
