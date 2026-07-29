"""build_consensus_assembly.py — MLB Edge-E7.11: consensus-board assembly (pure pandas, no IO).

Everything that decides *what a row of the consensus board means* lives here so it runs in the fast
gate; `build_consensus.py` does the S3 reads and the export. Same split as E8.0's
`board_assembly.py` / `build_prospect_board.py`.

⭐ THE UNION IS THE POINT. The E8.0 board is FanGraphs' universe. MLB Pipeline ranks players
FanGraphs' board does not carry — and *"one source ranks him top-100 and the other does not list
him at all"* is the single loudest disagreement two scouting sources can produce. Those players are
therefore ADDED as rows (`on_fangraphs_board = False`) rather than dropped by an inner join, which
is what a naive merge would silently do.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from betting_ml.scripts.prospect_board.board_assembly import (
    assign_league,
    classify_player_type,
)
from betting_ml.scripts.prospect_board.consensus import (
    PAYWALLED_SOURCES,
    DISAGREEMENT_THRESHOLD,
    RankSource,
)
from betting_ml.scripts.prospect_board.mlb_pipeline import PIPELINE_SOURCE

__all__ = [
    "HOW_TO_READ",
    "build_sources",
    "consensus_column_order",
    "consensus_sheets",
    "merge_pipeline_ranks",
]

# Identity/display fields a Pipeline-only player brings with him (he has no board row to inherit).
#
# ⚠️ `org_current` / `age_current` are AS OF THE FETCH, not as of the snapshot season (a historical
# page returns TODAY's roster and age — see `mlb_pipeline`'s docstring). That is harmless HERE, and
# only here: the consensus board is built from the CURRENT-season snapshot, where "now" and "the
# season" are the same instant. A historical study must read the Delta table directly and respect
# the `_current` suffix; it must not route through this function.
_PIPELINE_IDENTITY = {
    "player_name": "pipeline_player_name",
    "org_resolved": "pipeline_org",
    "position": "pipeline_position",
    "age_current": "pipeline_age",
    "eta": "pipeline_eta",
}
_PIPELINE_ATTR_SOURCES = ("player_name", "org_resolved", "position", "age_current", "eta")


def merge_pipeline_ranks(board: pd.DataFrame,
                         pipeline: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Attach MLB Pipeline's two ranks (Top 100 + org Top 30) to the board; union in its extras.

    Returns `(universe, report)`. The report is the per-source coverage the AC asks for, from the
    Pipeline side: how many of its ranked players the board already had, and how many it did not.
    """
    if pipeline.empty:
        raise ValueError("the MLB Pipeline frame is EMPTY — refusing to build a 'consensus' "
                         "that is one source wearing the word consensus.")

    pipe = pipeline.copy()
    pipe["mlbam_id"] = pipe["mlbam_id"].astype("string")
    pipe = pipe[pipe["mlbam_id"].notna()]
    pipe["rank"] = pd.to_numeric(pipe["rank"], errors="coerce")
    # `org` is point-in-time but exists only on an ORG-list row (a Top-100 entry has no org of its
    # own); `org_current` is roster-derived and always present. Coalesced for display — correct
    # here because this path only ever sees the current-season snapshot (see _PIPELINE_IDENTITY).
    org_current = (pipe["org_current"] if "org_current" in pipe.columns
                   else pd.Series(pd.NA, index=pipe.index, dtype="object"))
    pipe["org_resolved"] = pipe.get("org", org_current).fillna(org_current)

    grade_cols = sorted(c for c in pipe.columns if c.startswith("pipeline_grade_"))
    # One row per player: his Top-100 place (if any) and his org place (if any). `min` collapses
    # the pathological case of a player appearing twice on one list type — it cannot happen in a
    # clean snapshot, and taking the best rank is the only reading that is never worse than
    # arbitrary if it ever does.
    wide = (pipe.assign(_kind=np.where(pipe["list_type"] == "top100",
                                       "pipeline_overall_rank", "pipeline_org_rank"))
            .pivot_table(index="mlbam_id", columns="_kind", values="rank", aggfunc="min")
            .reset_index())
    for col in ("pipeline_overall_rank", "pipeline_org_rank"):
        if col not in wide.columns:
            wide[col] = np.nan
    wide.columns.name = None

    # Identity + grades from the player's DEEPEST list entry (the org list carries the current
    # affiliate; the Top 100 entry is the same person). Deduped so the join can never multiply.
    attrs = (pipe.sort_values(["mlbam_id", "list_type"])
             .groupby("mlbam_id", as_index=False)
             .agg({**{src: "first" for src in _PIPELINE_ATTR_SOURCES if src in pipe.columns},
                   **{c: "first" for c in grade_cols}}))
    attrs = attrs.rename(columns=_PIPELINE_IDENTITY)
    pipe_wide = wide.merge(attrs, on="mlbam_id", how="left")

    base = board.copy()
    base["mlbam_id"] = base["mlbam_id"].astype("string")
    merged = base.merge(pipe_wide, on="mlbam_id", how="left")
    if len(merged) != len(base):
        raise ValueError(
            f"the Pipeline join multiplied rows ({len(base)} → {len(merged)}) — its key is not "
            f"unique per player. A cartesian here would double-count a source in the consensus."
        )

    board_ids = set(base.loc[base["mlbam_id"].notna(), "mlbam_id"])
    extra = pipe_wide[~pipe_wide["mlbam_id"].isin(board_ids)].copy()
    report = {
        "source": PIPELINE_SOURCE,
        "pipeline_rows": int(len(pipe)),
        "pipeline_players": int(pipe_wide["mlbam_id"].nunique()),
        "matched_to_fangraphs_board": int(pipe_wide["mlbam_id"].isin(board_ids).sum()),
        "pipeline_only_players": int(len(extra)),
        "board_players_ranked_by_pipeline": int(merged["pipeline_org_rank"].notna().sum()
                                                + merged["pipeline_overall_rank"].notna().sum()
                                                - (merged["pipeline_org_rank"].notna()
                                                   & merged["pipeline_overall_rank"].notna()).sum()),
    }
    report["match_rate"] = round(
        report["matched_to_fangraphs_board"] / max(report["pipeline_players"], 1), 4)

    if not extra.empty:
        # Pipeline-only rows carry ONLY what Pipeline knows. Every FanGraphs column stays NULL, and
        # `on_fangraphs_board=False` says why — an empty `fv` here means "not on their board", not
        # "ungraded", and the two must never be confusable.
        extra["player_name"] = extra["pipeline_player_name"]
        extra["org"] = extra["pipeline_org"]
        extra["position"] = extra["pipeline_position"]
        extra["age"] = extra["pipeline_age"]
        extra["eta"] = extra["pipeline_eta"]
        extra["player_type"] = extra["position"].map(classify_player_type)
        extra["mlb_league"] = extra["org"].map(assign_league)
        extra["on_fangraphs_board"] = False
        merged = pd.concat([merged, extra], ignore_index=True, sort=False)

    merged["on_fangraphs_board"] = merged["on_fangraphs_board"].fillna(False).astype(bool)
    if merged["mlbam_id"].dropna().duplicated().any():
        raise ValueError("the consensus universe has duplicate mlbam_id values — a player would "
                         "appear twice on the draft board.")
    return merged, report


def build_sources(df: pd.DataFrame, manual_names: list[str]) -> list[RankSource]:
    """The `RankSource` list for whatever columns this universe actually has.

    Sources are declared from the FRAME, not from a static list, so a run without a Pipeline
    snapshot (or without a hand-keyed file) reports honestly as fewer sources instead of carrying
    an all-NULL column that inflates the apparent breadth of the consensus.
    """
    sources: list[RankSource] = []
    if "overall_rank" in df.columns:
        sources.append(RankSource(
            name="fangraphs_overall", rank_col="overall_rank", scope="overall",
            label="FanGraphs (overall)", access="ingested",
            note="THE BOARD's Top-100-style overall rank (E7.7); published for the top tier only."))
    if "org_rank" in df.columns:
        sources.append(RankSource(
            name="fangraphs_org", rank_col="org_rank", scope="org",
            label="FanGraphs (org)", access="ingested",
            note="THE BOARD's within-organization rank — the widest coverage of any source."))
    if "pipeline_overall_rank" in df.columns:
        sources.append(RankSource(
            name="pipeline_overall", rank_col="pipeline_overall_rank", scope="overall",
            label="MLB Pipeline (Top 100)", access="ingested",
            note="MLB.com's Top 100 (E7.11); free, MLBAM-keyed, page-read from an allowed path."))
    if "pipeline_org_rank" in df.columns:
        sources.append(RankSource(
            name="pipeline_org", rank_col="pipeline_org_rank", scope="org",
            label="MLB Pipeline (org 30)", access="ingested",
            note="MLB.com's 30 organizational Top 30s (E7.11)."))
    for name in manual_names:
        col = f"rank_{name}"
        if col in df.columns:
            sources.append(RankSource(
                name=name, rank_col=col, scope="overall",
                label=name.replace("_", " ").title(), access="manual",
                note=PAYWALLED_SOURCES.get(name, "hand-keyed by the operator; never scraped")))
    return sources


# ── Export shape ─────────────────────────────────────────────────────────────────────────────

def consensus_column_order(df: pd.DataFrame) -> list[str]:
    """WHO → the consensus → each source's own rank → where they disagree → us → the detail."""
    order = [
        "consensus_board_rank", "player_name", "org", "mlb_league", "position", "player_type",
        "level", "age", "age_vs_level", "eta", "on_fangraphs_board",
        # the consensus
        "consensus_rank", "consensus_tier", "consensus_rank_mean", "consensus_n_sources",
        "consensus_confidence", "consensus_sources", "consensus_rank_spread", "consensus_pctile",
        "org_consensus_rank", "org_consensus_rank_mean", "org_consensus_n_sources",
        "org_consensus_confidence", "org_consensus_rank_spread", "org_consensus_pctile",
        # each source, unmodified
        "fv", "overall_rank", "org_rank", "fantasy_dynasty_rank",
        "pipeline_overall_rank", "pipeline_org_rank",
        # ours, and the two comparisons
        "model_score", "mle_score", "age_score", "fv_pctile",
        "mle_vs_consensus", "mle_vs_consensus_label", "disagreement", "disagreement_label",
        "speed_flag", "in_majors",
    ]
    order += [c for c in df.columns if c.startswith("vs_consensus_")]
    order += [c for c in df.columns if c.startswith("pctile_")]
    order += [
        # our line
        "mle_level", "mle_pa", "mle_k_pct", "mle_bb_pct", "mle_iso",
        "mle_p_level", "mle_p_tbf", "mle_p_k_pct", "mle_p_bb_pct", "mle_p_gb_pct", "mle_coverage",
        # grades — FanGraphs' and MLB Pipeline's, side by side (E7.12 substrate)
        "grade_hit", "grade_game_pwr", "grade_raw_pwr", "grade_spd", "grade_fld",
        "grade_fb", "grade_sl", "grade_cb", "grade_ch", "grade_cmd",
    ]
    order += sorted(c for c in df.columns if c.startswith("pipeline_grade_"))
    order += ["mlbam_id", "fg_minor_id", "board_season", "board_as_of_date", "scouting_note"]

    seen: list[str] = []
    for col in order:
        if col in df.columns and col not in seen:
            seen.append(col)
    drop = {"raw_json", "tldr", "summary", "pipeline_player_name", "pipeline_org",
            "pipeline_position", "pipeline_age", "pipeline_eta"}
    return seen + [c for c in df.columns if c not in seen and c not in drop]


def consensus_sheets(board: pd.DataFrame, coverage: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """The workbook's tabs. Each answers one question the operator actually asks on draft day."""
    sheets: dict[str, pd.DataFrame] = {"All": board}
    for lg in ("AL", "NL"):
        sheets[lg] = board[board["mlb_league"] == lg].reset_index(drop=True)

    top = board[board["consensus_rank"].notna()].sort_values("consensus_rank")
    sheets["Consensus top 100"] = top.head(100).reset_index(drop=True)

    # Only MULTI-source rows can disagree: a 1-source "consensus" is that source, and its residual
    # against itself is meaningless. Filtered rather than explained away in a footnote.
    multi = board[board["consensus_n_sources"].fillna(0) >= 2]
    # the numeric residuals only — each also has a `…_label` string sibling
    resid_cols = [c for c in board.columns
                  if c.startswith("vs_consensus_") and not c.endswith("_label")]
    if resid_cols:
        worst = multi.assign(_spread=multi[resid_cols].abs().max(axis=1))
        sheets["Source disagreements"] = (worst[worst["_spread"] >= DISAGREEMENT_THRESHOLD]
                                          .sort_values("_spread", ascending=False)
                                          .drop(columns=["_spread"]).reset_index(drop=True))

    if "mle_vs_consensus" in board.columns:
        ours = board[board["mle_vs_consensus"].abs() >= DISAGREEMENT_THRESHOLD]
        sheets["Us vs consensus"] = ours.sort_values(
            "mle_vs_consensus", ascending=False, na_position="last").reset_index(drop=True)

    only = board[~board["on_fangraphs_board"]]
    if not only.empty:
        sheets["Pipeline-only"] = only.sort_values(
            "pipeline_overall_rank", na_position="last").reset_index(drop=True)

    sheets["Coverage by source"] = coverage
    return sheets


HOW_TO_READ: list[tuple[str, str]] = [
    ("WHAT THIS IS",
     "Several INDEPENDENT scouting rankings of the same prospects, side by side, plus a consensus "
     "across them, plus where they disagree with each other and with OUR translated projection. "
     "It extends the E8.0 board, which ranked off FanGraphs alone."),
    ("WHAT THIS IS NOT",
     "Not a claim that the consensus beats any single source, that we beat the consensus, or that "
     "a disagreement is an edge. Nothing here was tested against realized outcomes. best_alpha = 0."),
    ("WHERE THE SOURCES COME FROM",
     "FanGraphs THE BOARD and MLB Pipeline are INGESTED from free, publicly-readable pages "
     "(MLB.com's /prospects/ path is robots-permitted; its GraphQL API host is not, and is never "
     "called). Baseball America, Keith Law, ESPN/McDaniel, Baseball Prospectus and Prospects Live "
     "are PAYWALLED or robots-restricted: they appear ONLY if the operator hand-keyed them, and "
     "are never scraped."),
    ("consensus_rank / consensus_rank_mean",
     "The mean of the OVERALL ranks that exist for this player, and the board's ordering of those "
     "means. A source that publishes a Top 100 has said NOTHING about player #340 — it has not "
     "ranked him 101st — so unranked is averaged over, never imputed."),
    ("⚠️ consensus_n_sources — READ THIS BESIDE EVERY CONSENSUS NUMBER",
     "How many sources actually ranked him. A 1-source 'consensus' is just that source: averaging "
     "one number returns that number. consensus_confidence says the same thing in words."),
    ("consensus_rank_spread",
     "max minus min of the contributing ranks. Large = the sources genuinely disagree about him; "
     "0/blank = only one source ranked him, which is not agreement."),
    ("org_consensus_*",
     "The same aggregation over WITHIN-ORGANIZATION ranks (FanGraphs org rank + MLB Pipeline's org "
     "Top 30). Much wider coverage (~900+ players vs ~130). An org rank and an overall rank are "
     "different measurements and are never averaged together: org rank 1 on a thin farm system is "
     "not overall rank 1."),
    ("consensus_tier",
     "Bucketed overall consensus. Buckets, not a continuum, because the difference between "
     "consensus 63 and 71 is not one any of these sources would defend."),
    ("vs_consensus_<source>",
     "How much HIGHER that source ranks him than it usually does for a player at that consensus "
     "level, in percentile points. It is a RESIDUAL, not source_rank minus consensus_rank: two "
     "imperfectly-correlated rankings regress toward each other at the extremes, so the raw gap "
     "flags the whole top of the board and is a re-encoding of rank, not a disagreement."),
    ("⭐ mle_vs_consensus",
     "THE DIFFERENTIATED VIEW: how much higher OUR translated MiLB->MLB line scores him than is "
     "usual for a player the scouts place there. Also a residual, fitted within player type "
     "(the FV/consensus-to-us relationship genuinely differs for bats and arms — E7.8). A "
     "conversation starter, not a verdict."),
    ("on_fangraphs_board",
     "FALSE = MLB Pipeline ranks him but FanGraphs' board does not carry him at all. That is the "
     "loudest disagreement two sources can produce, so those players are ADDED rather than dropped "
     "by the join. Their FanGraphs columns are blank because there is no FanGraphs row — blank "
     "means NOT RANKED BY THEM, never 'ungraded'."),
    ("model_score / mle_score / age_score",
     "Unchanged from E8.0: our translated line (E7.3/E7.3p) plus age-relative-to-level, as "
     "percentiles WITHIN player type. Read K%/BB% with confidence and ISO with caution; wOBA is "
     "deliberately absent (it carries no translatable signal)."),
    ("pipeline_grade_*",
     "MLB Pipeline's own 20-80 tool grades, parsed BEST-EFFORT from the prose of their scouting "
     "report (they are not published as fields). Blank means not published or not parsed — never "
     "zero. `grade_*` without the prefix are FanGraphs' grades, which are fields."),
    ("mlb_league",
     "AL/NL of the parent org. Dynasty leagues are single-league — filter on this first."),
]
