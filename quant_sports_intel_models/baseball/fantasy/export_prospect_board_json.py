"""export_prospect_board_json.py — E8.1: land the E8.0/E7.13 prospect board as static JSON for the app.

    INPUT   ablation_results/e7_13_artifacts/e7_13_prospect_board_comps.csv   (preferred: board+comps)
            ablation_results/e8_0_artifacts/e8_0_prospect_board.csv           (fallback: no comps)
    OUTPUT  <out>/manifest.json + <out>/board.json
            → s3://$CACHE_BUCKET/fantasy/mlb/<season>/  (only with --publish)

🚦 WHY STATIC JSON AND NOT A REQUEST-TIME READ (the E8.1 Step-0 decision, inherited from NF3).
The board is a DuckDB/Delta lake asset with no request-time serving path, and a wide lakehouse read
from the API Lambda FAILS SILENTLY — `lakehouse_query` catches and returns `[]`, so the surface
renders empty with no error anywhere (E9.26b, which shipped a blank Model-Skill panel for weeks). NF3
rejected the request-time read for exactly that reason and served the NFL boards as static S3 JSON;
this is the baseball analog, same bucket, same shape, same gated-router read.

⚠️ CARRY THE CONSEQUENCE: fantasy serving is a BUILD-TIME artifact. There is no request-time
freshness — a board re-run reaches users only when this exporter re-publishes. "The board is rebuilt"
is NOT "users see it".

🔒 ENTITLEMENT IS AT THE DATA LAYER (E9.56 / NF-C6). The whole current-season board is the PAID
product, so there is no public split to get wrong here: every key this writes is read only by
`/fantasy/mlb/*`, which sits behind `require_fantasy_access` at the ROUTER level. That is the
opposite arrangement from NF3.2's track record (public by construction because its writer structurally
refuses to emit the locked season) — here the guarantee is that nothing unauthenticated can read the
key space at all, and the API Gateway's Cognito authorizer must therefore stay ON for these routes
(NF3.2: an authorizer is per-route console config, outside this repo's IaC — a route set to NONE
would silently un-gate the paid board).

🔒 HONEST FRAME (`best_alpha = 0`). Every claim string this exporter emits is carried IN THE PAYLOAD
rather than written into the frontend, so the wording lives with the model that earned it and cannot
drift out of sync with what was measured (the NF3 convention). Nothing here claims to beat FanGraphs.

🚨 PUBLISH GUARD (NF-D12 + NF1.7). Resolving a bucket does NOT upload — `--publish` does, and
`--publish` with no bucket resolved is a HARD ERROR, never a silent local-staging no-op.

    # LAPTOP — stage locally and inspect (default, touches nothing outward-facing):
    uv run python -m quant_sports_intel_models.baseball.fantasy.export_prospect_board_json

    # LAPTOP — publish to the LIVE prod api-cache (POST-MERGE operator step):
    uv run python -m quant_sports_intel_models.baseball.fantasy.export_prospect_board_json \
        --s3-bucket credence-prod-s3-api-cache --publish
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

log = logging.getLogger("mlb.fantasy.export_prospect_board")

_ABL = _PROJECT_ROOT / "quant_sports_intel_models/baseball/edge_program/ablation_results"
#: Preferred source — the E7.13 comps-augmented board (comp columns AND the comp-aware order).
BOARD_WITH_COMPS = _ABL / "e7_13_artifacts/e7_13_prospect_board_comps.csv"
#: Fallback — the plain E8.0 board. As of E8.1 a fresh `build_prospect_board.py` also carries comps.
BOARD_PLAIN = _ABL / "e8_0_artifacts/e8_0_prospect_board.csv"
DEFAULT_OUT = _PROJECT_ROOT / "quant_sports_intel_models/baseball/fantasy/artifacts/prospect_board"

#: The S3 key space. Mirrors `fantasy/nfl/<season>/` exactly (NF3's resolved serving path).
S3_PREFIX = "fantasy/mlb"

# ── Payload size ceiling ──────────────────────────────────────────────────────────────────────
#
# ⚠️ AN AWS LAMBDA PROXY RESPONSE IS HARD-CAPPED AT 6 MB, and there is no GZip middleware on this
# API (`app/backend/main.py` — deliberately: turning one on would change the encoding of EVERY
# endpoint's response on a Lambda that CI cannot exercise, which is the runtime-gate class of change
# this repo keeps getting bitten by). So the board's size is a real serving constraint, not a
# preference — and it grows every time a column is added to `_COLUMNS`.
#
# The board measures ~2.1 MB at 1,451 players (2026). WARN well before the cliff and REFUSE before
# it, so the failure is "the export told me" rather than a 502 on a paid surface with the cause
# three commits back. Whoever trips this should SPLIT the payload (the long prose columns — `note`,
# `compNote`, `compNames5` — are ~35% of it and are detail-panel content, not table content), never
# just raise the number.
_SIZE_WARN_BYTES = 4 * 1024 * 1024
_SIZE_FAIL_BYTES = 5_500_000


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. The column contract
# ══════════════════════════════════════════════════════════════════════════════════════════════
#
# `(source column, payload key, kind)`. Kinds: "s" string · "n" number · "i" int · "b" bool.
#
# ⚠️ ADDITIVE ONLY (NF-C0). A deployed client reads these keys by name; renaming or dropping one
# gives a 200 with a dead-looking page and no error anywhere. Add keys, never repurpose them.
_COLUMNS: tuple[tuple[str, str, str], ...] = (
    # ── who ──
    ("board_rank", "rank", "i"),
    ("player_name", "name", "s"),
    ("org", "org", "s"),
    # ⭐ Set ONLY on a player whose org was corrected off MLB Pipeline because FanGraphs' editorial
    # `org` had not moved for his trade (`apply_roster_org_correction`). Null — and therefore ABSENT
    # from the payload — for everyone else, so this costs bytes only on the handful who moved.
    # `orgPrior` is the org FanGraphs still lists him under; its presence IS the "he was traded"
    # signal, and it is what lets the UI explain an org that disagrees with the scouting source.
    ("org_prior", "orgPrior", "s"),
    ("org_source", "orgSource", "s"),
    ("mlb_league", "league", "s"),          # ⭐ AL/NL — a REQUIRED filter, not a nicety
    ("position", "pos", "s"),
    ("player_type", "type", "s"),
    ("level", "level", "s"),
    ("age", "age", "n"),
    ("age_vs_level", "ageVsLevel", "n"),
    ("eta", "eta", "i"),
    ("bats", "bats", "s"),
    ("throws", "throws", "s"),
    # ── the scouts ──
    ("fv", "fv", "n"),
    ("risk", "risk", "s"),
    ("overall_rank", "fgOverallRank", "i"),
    ("org_rank", "fgOrgRank", "i"),
    ("fantasy_dynasty_rank", "fgDynastyRank", "i"),
    ("pipeline_overall_rank", "pipelineOverallRank", "i"),
    ("pipeline_org_rank", "pipelineOrgRank", "i"),
    ("on_fangraphs_board", "onFgBoard", "b"),
    ("consensus_rank", "consensusRank", "i"),
    ("consensus_n_sources", "consensusSources", "i"),
    ("consensus_confidence", "consensusConfidence", "s"),
    ("consensus_tier", "consensusTier", "s"),
    # ── the three scores + where they disagree ──
    ("fv_pctile", "fvPctile", "n"),
    ("mle_score", "mleScore", "n"),
    ("age_score", "ageScore", "n"),
    ("model_score", "modelScore", "n"),
    ("blend_score", "blendScore", "n"),
    ("mle_coverage", "mleCoverage", "n"),
    ("disagreement", "disagreement", "n"),
    ("disagreement_label", "disagreementLabel", "s"),
    ("mle_vs_consensus", "mleVsConsensus", "n"),
    ("mle_vs_consensus_label", "mleVsConsensusLabel", "s"),
    ("speed_flag", "speedFlag", "s"),
    ("in_majors", "inMajors", "s"),
    # ── our line — batters (E7.3) ──
    ("mle_level", "mleLevel", "s"),
    ("mle_pa", "mlePa", "i"),
    ("mle_k_pct", "mleK", "n"), ("mle_k_pct_sd", "mleKSd", "n"),
    ("mle_bb_pct", "mleBb", "n"), ("mle_bb_pct_sd", "mleBbSd", "n"),
    ("mle_iso", "mleIso", "n"), ("mle_iso_sd", "mleIsoSd", "n"),
    # ── our line — the stolen-base read (E8.3) ──
    # `mleSbLevel` is carried beside the rate because the SB line has its OWN eligibility floor
    # (it needs stolen-base OPPORTUNITIES, not just PA), so it can be drawn from a different level
    # than the K%/BB%/ISO line. Surfacing it keeps that visible instead of implicit.
    ("mle_sb_rate", "mleSbRate", "n"), ("mle_sb_rate_sd", "mleSbRateSd", "n"),
    ("mle_sb_level", "mleSbLevel", "s"),
    # ── our line — pitchers (E7.3p) ──
    ("mle_p_level", "mlePLevel", "s"),
    ("mle_p_tbf", "mlePTbf", "i"),
    ("mle_p_k_pct", "mlePK", "n"), ("mle_p_k_pct_sd", "mlePKSd", "n"),
    ("mle_p_bb_pct", "mlePBb", "n"), ("mle_p_bb_pct_sd", "mlePBbSd", "n"),
    ("mle_p_gb_pct", "mlePGb", "n"), ("mle_p_gb_pct_sd", "mlePGbSd", "n"),
    # ── E7.13 comps ──
    ("comp_score", "compScore", "n"),
    ("comp_rank_delta", "compRankDelta", "i"),
    ("board_rank_no_comps", "rankNoComps", "i"),
    ("comp_names", "compNames", "s"),
    ("comp_names_5", "compNames5", "s"),
    ("comp_note", "compNote", "s"),
    ("comp_quality", "compQuality", "s"),
    ("comp_k", "compK", "i"),
    ("comp_bust_rate", "compBustRate", "n"),
    ("comp_p_debut", "compPDebut", "n"),
    ("comp_fp_median", "compFpMedian", "n"),
    ("comp_band_lo", "compBandLo", "n"),
    ("comp_band_hi", "compBandHi", "n"),
    ("comp_band_quantiles", "compBandQuantiles", "s"),
    ("comp_n_never_reached", "compNNever", "i"),
    ("comp_n_fringe", "compNFringe", "i"),
    ("comp_n_regular", "compNRegular", "i"),
    ("comp_n_impact", "compNImpact", "i"),
    # ── the blurb + ids ──
    ("scouting_note", "note", "s"),
    ("mlbam_id", "mlbamId", "i"),
    ("fg_minor_id", "fgMinorId", "s"),
)

#: Payload keys that MUST exist on every row for the surface to be usable at all. A missing one is a
#: build defect, not a thin row — the export refuses rather than shipping a board that renders blank.
_REQUIRED_KEYS = ("rank", "name", "league", "type")


def _clean(value, kind: str):
    """One source cell → its JSON value. NaN/NaT/blank → None (never 0, never "nan").

    A blank grade or an absent MLE line is a REAL state on this board ("not scouted" / "no
    minor-league PA yet"), and zero would read as *measured and terrible*.
    """
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if value is pd.NaT or (not isinstance(value, (list, tuple, dict)) and pd.isna(value)):
        return None
    if kind == "b":
        return bool(value)
    if kind == "i":
        try:
            return int(round(float(value)))
        except (TypeError, ValueError):
            return None
    if kind == "n":
        try:
            f = float(value)
        except (TypeError, ValueError):
            return None
        return None if math.isnan(f) else round(f, 4)
    s = str(value).strip()
    return s or None


def build_players(board: pd.DataFrame) -> list[dict]:
    """The board frame → the row payloads, keys omitted when null (a smaller blob, same meaning)."""
    present = [(src, key, kind) for src, key, kind in _COLUMNS if src in board.columns]
    missing_required = [k for k in _REQUIRED_KEYS if k not in {key for _, key, _ in present}]
    if missing_required:
        raise SystemExit(
            f"the board is missing column(s) required by the app surface: {missing_required}. "
            "Re-run `build_prospect_board.py` — refusing to publish a board the UI cannot render."
        )
    rows: list[dict] = []
    for rec in board.to_dict("records"):
        row = {key: _clean(rec.get(src), kind) for src, key, kind in present}
        rows.append({k: v for k, v in row.items() if v is not None})
    return rows


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. The honest frame — carried IN the payload
# ══════════════════════════════════════════════════════════════════════════════════════════════
#
# ⭐ POSITION-DIFFERENTIATED, per E7.8, and that asymmetry IS the product: "we know WHEN to trust the
# scouts". Pitchers lead with FV (it COMPLEMENTS our line: +0.031 on top of our +0.014, gates
# cleared); hitters lead with our MLE + age-relative-to-level (FV SUBSTITUTES: only +0.015 on top of
# our +0.047, no batter stage cleared). Written here, in the export, so the UI renders the verdict
# rather than paraphrasing it.

FRAMING = {
    "headline": "FanGraphs + MLB Pipeline consensus, our independent MLE-translated line, "
                "and where they disagree.",
    "claim": "This board makes no edge or win-rate claim and does not claim to beat FanGraphs. "
             "The blend is a display heuristic for ordering a draft board.",
    "byPosition": {
        "pitcher": "LEAD WITH FV for arms. Scouting grades add real, gate-clearing lift on top of "
                   "our translated line for pitchers (E7.8) — and pitcher stats translate "
                   "materially worse than batter stats (K% out-of-sample corr 0.37 vs 0.64), which "
                   "is exactly the room a scouting grade fills. Our line is the secondary read.",
        "batter": "LEAD WITH OUR LINE for bats. Our translated line plus age-relative-to-level "
                  "carries most of the signal for hitters; FV adds little on top of it (E7.8, no "
                  "batter stage cleared the deflated gates). Read FV as confirmation.",
    },
    "metricConfidence": {
        "mleK": "strong", "mleBb": "strong", "mleIso": "weak", "mleSbRate": "strong",
        "mlePGb": "strong", "mlePK": "weak", "mlePBb": "weak",
    },
    "metricNotes": {
        "mleSbRate": "MLB-equivalent STOLEN-BASE RATE — steals per time reaching first base "
                     "(singles + walks + hit-by-pitch). Out-of-sample translation corr 0.70, the "
                     "strongest thing we translate (E8.3). ⚠️ It is a RATE, not a projected SB "
                     "total: turning it into a season count needs a playing-time projection this "
                     "board does not make. And it measures how often he RUNS, not how often he is "
                     "SAFE — success rate does not translate (corr 0.23, fails our deflation gate), "
                     "so we cannot tell a 30-for-40 runner from a 30-for-32 one.",
        "mleK": "MLB-equivalent strikeout rate. Out-of-sample translation corr 0.64 — the "
                "strongest RATE-of-contact signal we translate. Read it with confidence.",
        "mleBb": "MLB-equivalent walk rate. Translation corr 0.49. Read it with confidence.",
        "mleIso": "MLB-equivalent isolated power. Translation corr 0.43 — WEAK BUT REAL, and "
                  "park- and pitching-quality dependent. Read it as a direction, not a number.",
        "mlePGb": "MLB-equivalent ground-ball rate. Translation corr 0.55 — the strong one on the "
                  "mound.",
        "mlePK": "MLB-equivalent strikeout rate for a pitcher. Translation corr 0.37 — weak but "
                 "real. Pitcher stats translate materially worse than batter stats.",
        "mlePBb": "MLB-equivalent walk rate for a pitcher. Translation corr 0.37 — weak but real.",
    },
    # Absences that are FINDINGS, and must not be quietly re-added by a future surface.
    #
    # ⚠️ The second entry used to read "STOLEN BASES ARE INVISIBLE TO US". E8.3 made that FALSE, and
    # a caveat that under-sells a shipped capability is its own defect — so it was REPLACED, not
    # softened. What remains an absence is the SUCCESS half, which is a measured null in its own
    # right and must not be quietly re-added either.
    "absences": [
        "wOBA is deliberately absent from our hitter line: it carries no translatable signal "
        "(corr 0.22, no better than knowing the player's level). It is a measured null, not an "
        "oversight.",
        "STOLEN-BASE SUCCESS RATE is absent, and that is a measured null: whether a runner is safe "
        "translates at corr 0.23 and fails our deflation gate, so we cannot tell a 30-for-40 runner "
        "from a 30-for-32 one. How OFTEN a prospect runs does translate (corr 0.70) and is in the "
        "score as mleSbRate — it is the efficiency half we decline to guess at.",
    ],
    # What the board GAINED, stated as plainly as what it lacks. A surface that only ever lists its
    # gaps trains its reader to discount it.
    "capabilities": [
        "STOLEN BASES ARE NOW IN OUR SCORE (E8.3, 2026-08-02). We translate stolen-base rate from a "
        "prospect's minor-league record the same way we translate K% and BB%, at an out-of-sample "
        "correlation of 0.70 — the strongest of any metric on this board. Until now every metric we "
        "translated was a per-PA rate and running was invisible to us, so speed-first prospects "
        "were systematically under-rated and roughly a fifth of roto offensive value was being "
        "deferred to the scouts' speed grade. That gap is closed.",
    ],
    "uncertainty": "The *Sd columns are PARAMETER uncertainty on our projection. They rank "
                   "confidence correctly but are TOO TIGHT to read as a calibrated interval. Treat "
                   "a wide band as 'we don't know', never as a priced range.",
    "scoresAreWithinType": "fvPctile, mleScore, ageScore, modelScore, blendScore and compScore are "
                           "percentiles among players of the SAME type. A hitter's 90 and a "
                           "pitcher's 90 each mean 'elite among his own kind', NOT 'equally "
                           "valuable' — cross-type ordering carries no positional-value claim.",
    "disagreement": "How much HIGHER our score is than it usually is for a player with THAT FV, in "
                    "percentile points — a residual fitted within player type, NOT modelScore minus "
                    "fvPctile (that raw gap flags the whole top of the board purely because two "
                    "imperfectly-correlated rankings regress toward each other at the extremes). A "
                    "conversation starter, not a verdict.",
    "comps": "The most similar HISTORICAL prospects and what they ACTUALLY produced in their first "
             "3 seasons — the pool deliberately includes the players who busted, which is why the "
             "bust share is usually the majority. Matched on what each comp looked like THEN; every "
             "comp's outcome window closed before this board's season. The comp read enters the "
             "ordering at 30% of our score (E7.13's measured weight). It is NOT a projection: the "
             "comp distribution is honest about DIFFERENCES between players and optimistic about "
             "absolute LEVELS, so no comp number is quoted as an accuracy figure.",
    "inMajors": "Some players carry a prospect grade while already listed at MLB. Most minor-league "
                "dynasty drafts do not make them draftable — check your league's rules.",

    # ── WHY A TOP PROSPECT CAN HAVE NO LINE FROM US (E8.1 follow-up, 2026-08-02) ───────────────
    #
    # ⚠️ THE ORIGINAL COPY HERE WAS WRONG IN A WAY THAT MATTERED. It said a blank line meant
    # "complex/DSL and just-drafted prospects have an identity but no minor-league record to
    # translate" — true for the DSL/complex half, and FALSE for the case the operator actually hit.
    # Josuar González, Luis Hernández, Dax Kilby and Trey Yesavage are all top-100-type names with
    # blank lines, and all four DO have a Single-A (or higher) record; they are simply UNDER E7.3's
    # `min_minor_pa = 150` floor (26 / 33 / 120 PA, and a pitcher split across four levels). Telling
    # a user "no record" about a player he just watched play is the fastest way to lose him.
    #
    # Two genuinely different causes, so two strings, chosen by the row's own level:
    #   * complex/DSL — the MLE is built for Single-A through Triple-A ONLY. There is no complex or
    #     DSL translation at all, so those rows are 0% covered BY CONSTRUCTION, not by thin sample.
    #   * everywhere else — he has a record, it is just under the 150-PA/TBF floor E7.3 set because
    #     a line thinner than that is too noisy to translate.
    "noLine": {
        "complex": "We don't publish a translated line for complex-league or DSL players at all — "
                   "our minor-league translation is built for Single-A through Triple-A, so this is "
                   "a limit of what we model, not a thin record. He stays on the board on the "
                   "scouts' grade.",
        "thinSample": "He has a professional record, but not yet enough of one for us to translate: "
                      "our line needs at least 150 plate appearances (or batters faced) at a level "
                      "before we'll publish it, because anything thinner is too noisy to mean "
                      "much. This is us declining to guess, not an absence of data — expect a line "
                      "once he accumulates the playing time.",
    },
    "minSample": 150,
    # The LEVELS the translation actually covers. Carried so the UI decides which `noLine` string to
    # show from the exporter's own list rather than hard-coding a level vocabulary of its own.
    "mleLevels": ["A", "A+", "AA", "AAA", "MLB"],
}


def build_manifest(board: pd.DataFrame, season: int, *, source_path: Path,
                   generated_at: str) -> dict:
    """Season meta, the filter vocabularies the UI populates its controls from, and the framing."""
    def _vals(col: str) -> list:
        if col not in board.columns:
            return []
        return sorted({v for v in board[col].dropna().tolist() if str(v).strip()})

    as_of = None
    if "as_of_date" in board.columns:
        seen = board["as_of_date"].dropna()
        as_of = str(seen.max()) if not seen.empty else None

    league_counts = (board["mlb_league"].value_counts().to_dict()
                     if "mlb_league" in board.columns else {})
    return {
        "season": season,
        "generated_at": generated_at,
        "as_of_date": as_of,
        "source": source_path.name,
        "players": int(len(board)),
        "hasComps": "comp_fp_median" in board.columns,
        "counts": {
            "byLeague": {str(k): int(v) for k, v in league_counts.items()},
            "byType": {str(k): int(v) for k, v in
                       board.get("player_type", pd.Series(dtype=object))
                       .value_counts().to_dict().items()},
            "disagreements": int(
                board["disagreement_label"].isin(["WE'RE HIGHER", "SCOUTS HIGHER"]).sum()
            ) if "disagreement_label" in board.columns else 0,
        },
        "filters": {
            "leagues": [lg for lg in ("AL", "NL") if lg in league_counts],
            "orgs": [str(v) for v in _vals("org")],
            "levels": [str(v) for v in _vals("level")],
            "positions": [str(v) for v in _vals("position")],
            "etas": [int(v) for v in _vals("eta")],
        },
        "framing": FRAMING,
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. Runner
# ══════════════════════════════════════════════════════════════════════════════════════════════

def check_response_size(size_bytes: int) -> None:
    """Fail the EXPORT rather than the paid surface when the board outgrows a Lambda response.

    See `_SIZE_FAIL_BYTES`. The remedy is to split the payload (the long prose columns are detail-
    panel content), not to raise the ceiling — the 6 MB cap is AWS's, not ours.
    """
    if size_bytes >= _SIZE_FAIL_BYTES:
        raise SystemExit(
            f"board.json is {size_bytes / 1024 / 1024:.1f} MB, past the "
            f"{_SIZE_FAIL_BYTES / 1024 / 1024:.1f} MB safety bound under AWS Lambda's 6 MB proxy-"
            "response cap — /fantasy/mlb/board would 502 for every subscriber. SPLIT the payload "
            "(move `note` / `compNote` / `compNames5` to a lazily-loaded detail blob); do not raise "
            "the ceiling."
        )
    if size_bytes >= _SIZE_WARN_BYTES:
        log.warning(
            "[ALERT] board.json is %.1f MB — approaching AWS Lambda's 6 MB proxy-response cap. The "
            "next few columns will break /fantasy/mlb/board. Plan the payload split now.",
            size_bytes / 1024 / 1024)


def resolve_board(explicit: str | None) -> Path:
    """Pick the board CSV: an explicit path, else the freshest candidate that carries comps.

    🚨 THE BUG THIS CLOSES (2026-08-03, published a TWO-DAY-OLD board to prod). This used to take
    the FIRST candidate that existed on disk, `BOARD_WITH_COMPS` first — a fixed preference with no
    regard for age. `build_prospect_board.py` writes `BOARD_PLAIN`, and since E8.1 it attaches the
    E7.13 comps NATIVELY, so `BOARD_WITH_COMPS` is the LEGACY second-export path. Any checkout that
    ever ran that legacy export keeps its stale CSV forever, and every subsequent publish silently
    preferred it — so a correct, just-completed build was written to disk and then IGNORED.

    It is invisible in the ordinary output: the run logs a full, healthy build report, the publish
    reports a plausible player count, and nothing anywhere says the two came from different files.
    Live consequence: a rebuild carrying 43 trade-corrected orgs published an Aug-2 board instead,
    moving prod BACKWARDS an hour after a good publish. It reproduced only on a checkout that had
    the legacy artifact — a fresh worktree resolves to `BOARD_PLAIN` and works by accident, which is
    exactly how it got shipped.

    ⭐ THE RULE: prefer a candidate that carries comps, and among those take the NEWEST by mtime —
    never a fixed order. A stale file must not outrank a fresh one just for being listed first.
    """
    if explicit:
        path = Path(explicit)
        if not path.is_file():
            raise SystemExit(f"--board {path} does not exist")
        return path

    present = [c for c in (BOARD_WITH_COMPS, BOARD_PLAIN) if c.is_file()]
    if not present:
        raise SystemExit(
            "no prospect board found. Build one first:\n"
            "  AWS_DEFAULT_REGION=us-east-2 uv run --with openpyxl python -m "
            "betting_ml.scripts.prospect_board.build_prospect_board --prospect-savant"
        )

    # A board without comp columns is a real downgrade (the pre-comp ordering E8.1 exists to
    # prevent), so comps win over freshness; freshness decides among equals.
    with_comps = [c for c in present if _has_comps(c)]
    pool = with_comps or present
    chosen = max(pool, key=lambda p: p.stat().st_mtime)

    for other in present:
        if other == chosen:
            continue
        if other.stat().st_mtime > chosen.stat().st_mtime:
            # Only reachable when the newer file LACKS comps — say so rather than silently
            # publishing the older one, since "why is my rebuild not live?" is unanswerable
            # from the ordinary output.
            log.warning(
                "⚠️ %s is NEWER than the board being published (%s) but carries no comp columns "
                "— publishing the older comps board. Re-run build_prospect_board.py if you "
                "expected the newer one.", other.name, chosen.name)

    log.info("board source: %s (modified %s)", chosen,
             datetime.fromtimestamp(chosen.stat().st_mtime).isoformat(timespec="seconds"))
    return chosen


def _has_comps(path: Path) -> bool:
    """Does this CSV carry E7.13's comp columns? Read the HEADER only — these files are ~2 MB."""
    try:
        with path.open() as fh:
            header = fh.readline()
    except OSError:
        return False
    cols = {c.strip() for c in header.split(",")}
    return "comp_score" in cols and "comp_names" in cols


def export(board_path: Path, out_dir: Path, *, season: int | None = None) -> dict:
    board = pd.read_csv(board_path)
    board = board.loc[board["player_name"].notna()].reset_index(drop=True)
    if board.empty:
        raise SystemExit(f"{board_path} has no rows — refusing to publish an empty board")

    if season is None:
        seasons = pd.to_numeric(board.get("season"), errors="coerce").dropna()
        if seasons.empty:
            raise SystemExit(
                "the board carries no `season` column, so the S3 key would be guessed. Pass "
                "--season explicitly."
            )
        # max, not mode: the ~165 MLB-Pipeline-only rows carry a null season (they are unioned in
        # from a source with no board snapshot of its own), so any other statistic reads as null.
        season = int(seasons.max())

    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    players = build_players(board)
    manifest = build_manifest(board, season, source_path=board_path, generated_at=generated_at)
    if not manifest["hasComps"]:
        # ALERT-tier, not fatal: a pre-E8.1 board is still a usable board, it is just the pre-comp
        # ordering with the comp panel empty. Loud, because it is invisible in the UI.
        log.warning(
            "[ALERT] this board carries NO comp columns — the app's comp panel will be empty and "
            "the ORDER is the pre-comp one. Rebuild with `build_prospect_board.py` (E8.1 applies "
            "E7.13's comps natively) before publishing."
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    board_json = out_dir / "board.json"
    board_json.write_text(
        json.dumps({"season": season, "generated_at": generated_at, "players": players},
                   separators=(",", ":")), encoding="utf-8")

    check_response_size(board_json.stat().st_size)
    size = sum(p.stat().st_size for p in out_dir.glob("*.json"))
    log.info("staged %d players for season %d in %s (%.1f KB)",
             len(players), season, out_dir, size / 1024)
    return {"season": season, "players": len(players), "bytes": size,
            "has_comps": manifest["hasComps"], "source": str(board_path)}


def _maybe_publish(out_dir: Path, bucket: str | None, season: int, publish: bool) -> None:
    """Gate the S3 upload behind an explicit `--publish` (NF-D12 + NF1.7).

    Without `--publish` a resolved bucket only PRINTS what would upload — `$CACHE_BUCKET` is set in
    the operator's normal env, so a pre-guard default silently pushed to prod on every re-export.
    With `--publish` and no bucket this RAISES rather than degrading to a local-stage warning: an
    operator who explicitly asked for an outward-facing action must never get a silent no-op (NF1.7
    lost a real publish to exactly that).
    """
    if not bucket:
        if publish:
            raise SystemExit(
                "--publish was passed but NO BUCKET resolved (--s3-bucket / $CACHE_BUCKET is unset "
                "or empty), so nothing would be uploaded and the run would have looked successful. "
                "Re-run with the bucket named explicitly:\n"
                f"  --season {season} --s3-bucket credence-prod-s3-api-cache --publish"
            )
        log.warning(
            "no --s3-bucket / $CACHE_BUCKET — staged locally only; /fantasy/mlb/* will 404 until "
            "these are uploaded to s3://<bucket>/%s/%d/", S3_PREFIX, season)
        return

    files = sorted(out_dir.glob("*.json"))
    prefix = f"{S3_PREFIX}/{season}"
    if not publish:
        log.info("[DRY-RUN] would upload %d file(s) to s3://%s/%s/ — pass --publish to actually "
                 "reach the LIVE prod api-cache: %s",
                 len(files), bucket, prefix, ", ".join(p.name for p in files))
        return

    log.warning("🚨 PUBLISHING TO LIVE PROD api-cache — s3://%s/%s/ (%d files)",
                bucket, prefix, len(files))
    # Plain (key-less) client — instance-role / AWS_PROFILE safe; NEVER pass
    # aws_access_key_id=os.environ.get(...) (test_boto3_credential_lint.py). The cache bucket lives
    # in us-east-1, so pin the region: a laptop AWS_DEFAULT_REGION=us-east-2 (set for the DuckDB
    # ML-artifacts bucket, and this board's own build needs it) would otherwise misroute the put.
    import boto3

    s3 = boto3.client("s3", region_name="us-east-1")
    for path in files:
        s3.put_object(Bucket=bucket, Key=f"{prefix}/{path.name}",
                      Body=path.read_bytes(), ContentType="application/json",
                      CacheControl="max-age=300")
        log.info("uploaded s3://%s/%s/%s", bucket, prefix, path.name)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--board", default=None,
                   help="board CSV (default: the E7.13 comps board, else the plain E8.0 board)")
    p.add_argument("--out-dir", default=str(DEFAULT_OUT))
    p.add_argument("--season", type=int, default=None,
                   help="override the season the board is published under")
    p.add_argument("--s3-bucket", default=os.getenv("CACHE_BUCKET"),
                   help=f"S3 bucket to upload to (default $CACHE_BUCKET), under {S3_PREFIX}/"
                        "<season>/. Resolving a bucket alone does NOT upload — pass --publish.")
    p.add_argument("--publish", action="store_true",
                   help="actually upload to the LIVE prod api-cache. Without it this is a DRY-RUN "
                        "that stages locally and prints exactly what WOULD upload.")
    p.add_argument("-v", "--verbose", action="store_true")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")

    out_dir = Path(a.out_dir)
    rep = export(resolve_board(a.board), out_dir, season=a.season)
    _maybe_publish(out_dir, a.s3_bucket, rep["season"], a.publish)
    print(json.dumps(rep, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
