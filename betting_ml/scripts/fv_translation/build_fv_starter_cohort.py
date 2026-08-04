"""build_fv_starter_cohort.py — MLB Edge-E7.10: assemble the debuting-STARTER study matrix ONCE.

Pairs three things that already exist, and adds exactly one new lakehouse read:

  * **the served MLE prior** — E7.3p `mle_projections_pitchers` (`mle_<m>`, leakage-safe: each was fit
    only on strictly-prior debut cohorts) at the pitcher's HIGHEST reached MiLB level, i.e. the row
    `eb_starter_posteriors` actually serves;
  * **the realized debut-window label** — E7.3p `mle_graduated_pairs_pitchers` (`mlb_<m>` over the
    FIRST TWO MLB seasons, with `mlb_pa` / `mlb_bip` / `has_mlb_label` — the E7.5/E7.5p thin-cameo
    floors, reused verbatim rather than re-derived);
  * **the pre-debut FV grade** — THE BOARD (E7.7), routed to MLBAM through the E7.4 xref, at the LATEST
    board season **STRICTLY BEFORE** the pitcher's debut season.

⚠️ **THE BOARD HAS EXACTLY ONE VALID READER** (E7.4 landmines 1+2): `delta_scan` hard-errors on its
`void`-typed `mlbam_id`, and a `read_parquet` glob unions TOMBSTONED files and fabricates a wrong
number. This module calls `player_xref.register_board` and reuses the xref's OWN bridge SQL — one
reader, one bridge, one place to fix.

⭐ **WHY STRICTLY-PRIOR SEASON AND NOT "any snapshot before the debut date".** E7.7 records that
FanGraphs serves the RETAINED past board rather than a true point-in-time snapshot, and stamps every
pre-2026 season `<season>-07-01`. A same-season board can therefore embed a revision made AFTER the
pitcher debuted in April — hindsight, biasing toward finding FV lift. Excluding the debut season removes
that hazard outright, at a cost in coverage that §8 of the report states. The looser rule is available
as `--asof-rule same_season_allowed` and is a declared SENSITIVITY, never the headline.

The DuckDB half is one small read (the board + the two bridge legs, ~10k rows); the JOIN/derive half is
pure pandas so the fast gate exercises it on fixtures. SF-FREE. `best_alpha = 0`.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.scripts.fv_translation.fv_starter_prior import (  # noqa: E402
    MIN_START_SHARE,
    PRIOR_METRICS,
)
from betting_ml.scripts.milb_mle.mle_prior import highest_level_rows  # noqa: E402

log = logging.getLogger("e7_10.cohort")

_ABL = _PROJECT_ROOT / "quant_sports_intel_models/baseball/edge_program/ablation_results"
DEFAULT_PROJ = _ABL / "e7_3p_artifacts/mle_projections_pitchers.parquet"
DEFAULT_PAIRS = _ABL / "e7_3p_artifacts/mle_graduated_pairs_pitchers.parquet"
DEFAULT_OUT = _ABL / "e7_10_artifacts"

ASOF_RULES = ("strictly_prior_season", "same_season_allowed")

#: The E7.3p realized label spans the debut season and the one after it.
LABEL_WINDOW_SEASONS = 2

#: ⭐ **WHY THE DEFAULT CEILING IS "THE LAST COMPLETE MLB SEASON", NOT "THE LAST CLOSED 2-SEASON
#: WINDOW" — and why E7.8's rule deliberately does NOT transfer.**
#:
#: E7.8's `default_season_ceiling` drops any cohort whose outcome window is still open, because ITS
#: target was ACCUMULATED fantasy points over a fixed horizon: truncate that and a good prospect is
#: labelled a bust — a BIASED label, which is fatal. E7.10's target is a **RATE** (TBF-weighted K% /
#: BB% / GB%), and a rate over 1.5 seasons instead of 2 is NOISIER but not biased, so the same
#: reasoning gives the opposite answer. It also keeps the population aligned with **E7.5p's own
#: ablation**, which is the study E7.10 extends and the incumbent it must be compared against on
#: like-for-like rows.
#:
#: So a cohort is kept iff its DEBUT season is complete. The strict 2-season-closed variant is a
#: declared sensitivity (`--strict-label-window`) and its drop count is reported either way — never a
#: silent population change.
#:
#: ⚠️ Fixed 2026-08-03, BEFORE any arm was scored: the first cut used the strict rule and produced 5
#: eval folds against the 6 the pre-registration §3 states. The pre-registration is the authority.
COMPLETE_SEASON_LAG = 1


def board_fv_sql(src=None) -> str:
    """Board → MLBAM → (season, fv, risk, eta, ranks). Reuses the xref's OWN dedupe + both bridge legs
    so this is the SAME resolution E7.4 match-counted on the real lake, never a re-derivation."""
    from betting_ml.scripts.milb_xref import player_xref as px

    src = src or px.s3_sources()
    return f"""
    with board_all as ({px._board_latest_sql(src)}),
         lb as ({px._leaderboard_bridge_sql(src)}),
         fg_mlb as ({px._fg_mlb_bridge_sql(src)})
    select cast(coalesce(l.mlbam_id, g.mlbam_id) as varchar) as player_id,
           cast(b.season as integer)                         as fv_board_season,
           cast(b.as_of_date as varchar)                     as fv_as_of_date,
           cast(b.fv as double)                              as fv,
           cast(b.risk as varchar)                           as risk,
           cast(b.eta as double)                             as eta,
           cast(b.overall_rank as double)                    as overall_rank,
           cast(b.org_rank as double)                        as org_rank
    from board_all b
    left join lb l on b.fg_minor_id = l.fg_minor_id
    left join fg_mlb g on b.fg_player_id = g.fg_mlb_id and regexp_matches(b.fg_player_id, '^[0-9]+$')
    where coalesce(l.mlbam_id, g.mlbam_id) is not null
      and b.fv is not null
    """


def fetch_board_fv() -> pd.DataFrame:
    """The one lakehouse read. Small (~10k rows) — the board is ~1.3k names a season over 9 seasons."""
    from scripts.utils.lakehouse_read import duck_connect

    from betting_ml.scripts.milb_xref import player_xref as px

    conn = duck_connect()
    try:
        try:
            conn.execute("INSTALL delta; LOAD delta")
        except Exception as e:  # noqa: BLE001
            log.warning("delta extension load failed (%s) — the leaderboard bridge will fail", e)
        px.register_board(conn)          # ⚠️ the ONLY valid board reader (E7.4 landmines 1+2)
        df = conn.execute(board_fv_sql()).df()
    finally:
        conn.close()
    log.info("board FV rows resolved to MLBAM: %d over seasons %s",
             len(df), sorted(df["fv_board_season"].dropna().unique().tolist()))
    return df


def attach_pre_debut_fv(pop: pd.DataFrame, board: pd.DataFrame,
                        rule: str = "strictly_prior_season") -> pd.DataFrame:
    """Attach the LATEST admissible board grade to each pitcher. A pitcher with no admissible board row
    keeps NULL FV — he is the MLE-prior FALLBACK population and is COUNTED, never dropped silently.

    `strictly_prior_season` (the headline) admits `fv_board_season < debut_cohort`.
    `same_season_allowed` (the sensitivity) admits `<=`. ⚠️ A true date-level as-of would need the MLB
    debut DATE, which the E7.3p artifacts do not carry — so the looser rule is season-level and its
    hindsight exposure is exactly the one §2 of the pre-registration names. It is never the headline.
    """
    if rule not in ASOF_RULES:
        raise ValueError(f"asof rule {rule!r} not in {ASOF_RULES}")
    b = board.copy()
    b["player_id"] = b["player_id"].astype(str)
    b["fv_board_season"] = pd.to_numeric(b["fv_board_season"], errors="coerce")
    j = pop[["player_id", "debut_cohort"]].merge(b, on="player_id", how="left")
    if rule == "strictly_prior_season":
        ok = j["fv_board_season"] < j["debut_cohort"]
    else:
        ok = j["fv_board_season"] <= j["debut_cohort"]
    j = j[ok.fillna(False)]
    # the CLOSEST admissible board to the debut — the grade a scout would have had in hand
    j = (j.sort_values(["player_id", "fv_board_season"])
           .drop_duplicates("player_id", keep="last")
           .drop(columns=["debut_cohort"]))
    out = pop.merge(j, on="player_id", how="left")
    out["fv_asof_rule"] = rule
    return out


def build_frame(proj: pd.DataFrame, pairs: pd.DataFrame, board: pd.DataFrame, *,
                rule: str = "strictly_prior_season",
                season_ceiling: int | None = None,
                strict_label_window: bool = False) -> tuple[pd.DataFrame, dict]:
    """Projections + pairs + board → the E7.10 study frame (one row per pitcher) + a coverage report.

    Pure pandas so CI exercises it. Every exclusion is COUNTED into the report."""
    report: dict = {"asof_rule": rule, "proj_rows": int(len(proj)), "pairs_rows": int(len(pairs))}
    proj = proj.copy()
    pairs = pairs.copy()
    proj["player_id"] = proj["player_id"].astype(str)
    pairs["player_id"] = pairs["player_id"].astype(str)

    # ── pre-debut MiLB start share, over the WHOLE pre-debut record (all levels) ──────────────────
    # Leakage-safe by construction: `build_graduated_pairs_pitchers` only ever sums MiLB games STRICTLY
    # BEFORE the MLB debut date. This is the PRIMARY population filter and it conditions on nothing
    # that happens after the call-up.
    gs = pairs.groupby("player_id")[["pit_games_started", "pit_games_played"]].sum(min_count=1)
    start_share = (pd.to_numeric(gs["pit_games_started"], errors="coerce")
                   / pd.to_numeric(gs["pit_games_played"], errors="coerce").replace(0, np.nan))

    # ── the SERVED row: highest reached level (what eb_starter_posteriors reads) ──────────────────
    label_cols = ["player_id", "level", "mlb_pa", "mlb_bip", "has_mlb_label"]
    merged = proj.merge(pairs[[c for c in label_cols if c in pairs]], on=["player_id", "level"],
                        how="left")
    pop = highest_level_rows(merged).drop(columns=["_rank"], errors="ignore")
    report["highest_level_rows"] = int(len(pop))

    pop = pop[pd.to_numeric(pop["debut_cohort"], errors="coerce").notna()].copy()
    pop["debut_cohort"] = pd.to_numeric(pop["debut_cohort"], errors="coerce").astype(int)
    report["with_debut_cohort"] = int(len(pop))

    pop["milb_start_share"] = pop["player_id"].map(start_share)
    pop["is_starter"] = (pd.to_numeric(pop["milb_start_share"], errors="coerce").fillna(0.0)
                         >= MIN_START_SHARE)

    # ── cohort ceiling (see COMPLETE_SEASON_LAG — the label is a RATE, so the E7.8 rule is inverted) ──
    if season_ceiling is None:
        from betting_ml.utils.game_day import current_game_date
        lag = LABEL_WINDOW_SEASONS if strict_label_window else COMPLETE_SEASON_LAG
        season_ceiling = int(current_game_date().year) - lag
    before = len(pop)
    pop = pop[pop["debut_cohort"] <= int(season_ceiling)].copy()
    report["season_ceiling"] = int(season_ceiling)
    report["strict_label_window"] = bool(strict_label_window)
    report["dropped_open_label_window"] = int(before - len(pop))

    out = attach_pre_debut_fv(pop, board, rule)

    lab = out["has_mlb_label"].fillna(False).astype(bool)
    has_fv = pd.to_numeric(out["fv"], errors="coerce").notna()

    # ⭐ **THE COVERAGE GATE MUST BE COMPUTED OVER THE COHORTS THE BOARD COULD POSSIBLY HAVE GRADED.**
    # THE BOARD starts in 2018, so a debut cohort at or below the board's first season has NO
    # strictly-prior grade BY CONSTRUCTION — 0% coverage that says nothing about FanGraphs' reach.
    # Pooling those in drags the headline figure from ~74% to ~47% and would be a coverage number for a
    # quietly different population than the one it names (NF1.8's per-group lesson). Both are reported;
    # the ELIGIBLE-cohort figure is the one the report leads with, and the pooled one is labelled.
    board_first = int(pd.to_numeric(board["fv_board_season"], errors="coerce").min())
    first_gradable_cohort = board_first + 1
    gradable = out["debut_cohort"] >= first_gradable_cohort
    ls, lsg = lab & out["is_starter"], lab & out["is_starter"] & gradable
    report.update({
        "board_first_season": board_first,
        "first_gradable_debut_cohort": int(first_gradable_cohort),
        "labelled_starters_in_gradable_cohorts": int(lsg.sum()),
        "fv_coverage_of_gradable_labelled_starters": round(
            float((lsg & has_fv).sum() / max(1, int(lsg.sum()))), 4),
        "fv_coverage_pooled_incl_pre_board_cohorts": round(
            float((ls & has_fv).sum() / max(1, int(ls.sum()))), 4),
    })
    report.update({
        "study_rows": int(len(out)),
        "labelled_rows": int(lab.sum()),
        "labelled_starters": int((lab & out["is_starter"]).sum()),
        "labelled_with_fv": int((lab & has_fv).sum()),
        "labelled_starters_with_fv": int((lab & out["is_starter"] & has_fv).sum()),
        # ⭐ THE COVERAGE GATE (§8): FV can only help where it exists. Ungraded pitchers fall back to
        # the E7.5p MLE prior and are counted here, never dropped silently. ⚠️ This POOLED figure
        # includes pre-board cohorts that are 0% by construction — read
        # `fv_coverage_of_gradable_labelled_starters` instead.
        "fv_coverage_of_labelled_starters": round(
            float((lab & out["is_starter"] & has_fv).sum()
                  / max(1, int((lab & out["is_starter"]).sum()))), 4),
        "fv_coverage_by_cohort": {
            int(c): round(float(g["_fv"].mean()), 4)
            for c, g in out.assign(_fv=has_fv.astype(float))[lab & out["is_starter"]]
            .groupby("debut_cohort")},
        "labelled_starters_by_cohort": {
            int(c): int(len(g)) for c, g in out[lab & out["is_starter"]].groupby("debut_cohort")},
        "metric_label_coverage": {
            m: int((lab & pd.to_numeric(out[f"mlb_{m}"], errors="coerce").notna()
                    & pd.to_numeric(out[f"mle_{m}"], errors="coerce").notna()).sum())
            for m in PRIOR_METRICS},
    })
    return out.reset_index(drop=True), report


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="E7.10 — assemble the debuting-starter FV study matrix")
    p.add_argument("--projections", default=str(DEFAULT_PROJ))
    p.add_argument("--pairs", default=str(DEFAULT_PAIRS))
    p.add_argument("--asof-rule", default="strictly_prior_season", choices=list(ASOF_RULES))
    p.add_argument("--season-ceiling", type=int, default=None,
                   help="latest debut cohort to INCLUDE; defaults to the last COMPLETE MLB season "
                        "(see COMPLETE_SEASON_LAG — the label is a RATE, so a partial window is "
                        "noisier but not biased, and E7.8's accumulate-horizon rule does not transfer)")
    p.add_argument("--strict-label-window", action="store_true",
                   help="declared SENSITIVITY: keep only cohorts whose full 2-season label window has "
                        "closed (one fewer fold)")
    p.add_argument("--out-dir", default=str(DEFAULT_OUT))
    p.add_argument("--board-parquet", default=None,
                   help="skip the lakehouse read and use a cached board-FV parquet (a re-run costs "
                        "seconds; the assembly is otherwise one small S3 read)")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")

    for path, what in ((args.projections, "projections"), (args.pairs, "pairs")):
        if not Path(path).exists():
            p.error(f"{what} parquet not found at {path} — run run_milb_mle_pitchers.py --s3 first")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    board_cache = out_dir / "board_fv_by_season.parquet"
    if args.board_parquet:
        board = pd.read_parquet(args.board_parquet)
        log.info("board FV read from cache %s (%d rows)", args.board_parquet, len(board))
    else:
        board = fetch_board_fv()
        board.to_parquet(board_cache, index=False)
        log.info("cached board FV → %s", board_cache)

    df, report = build_frame(pd.read_parquet(args.projections), pd.read_parquet(args.pairs), board,
                             rule=args.asof_rule, season_ceiling=args.season_ceiling,
                             strict_label_window=args.strict_label_window)
    for k, v in report.items():
        log.info("coverage %-40s %s", k, v)

    tag = args.asof_rule + ("__strict_window" if args.strict_label_window else "")
    dest = out_dir / f"fv_starter_cohort__{tag}.parquet"
    df.to_parquet(dest, index=False)
    (out_dir / f"fv_starter_coverage__{tag}.json").write_text(
        json.dumps(report, indent=2, default=str))
    log.info("wrote %s (%d rows)", dest, len(df))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
