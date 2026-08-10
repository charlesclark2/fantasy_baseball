"""export_track_record_json.py — NF3.2: land the past-season fantasy football TRACK RECORD (our
projection vs that season's preseason ADP vs the realized outcome) as PUBLIC static JSON — the GTM
"receipts" proof asset.

Per season 2019–2025 (never the current LOCKED season — see `LOCKED_SEASON`): our NF1.5 refined-board
projection vs that season's Fantasy Football Calculator ADP vs the realized fantasy finish, one row per
player, built by `benchmark_scorecard.player_track_record_frame` (the per-player materialization behind
NF-D3's aggregate "adp" scorecard numbers — never a parallel re-derivation of that join).

⚖️ HONEST-CLAIM DISCIPLINE (non-negotiable — see CLAUDE.md / `test_nf1_5b_served_board.py`'s denylist,
reused here): the manifest's claim is built ONLY from the freshly-regenerated NF-D3 scorecard's own
numbers (`--scorecard-json`, produced by `run_benchmark_scorecard.py --projection-source nf1_5`) and the
NF-D17 population artifact (`--uncertainty-json`) — never hand-authored. It never claims "every
position", "beats the market", or any superlative the artifacts themselves don't support; `build_claim`
asserts this at build time (`_CLAIM_DENYLIST`), not just in a test.

🗣️ NF-TR1 — TWO-LAYER COPY. The claim ships as a plain-English CONSUMER LEAD (`claim.lead`, also the
manifest's `headline` so every existing consumer inherits it) with the analyst-register sentence, the
named benchmark, the metric, the player count, the seasons and the visible interval preserved beneath
it in `claim.precise` + `claim.disclosures`. The audience is the average fantasy player: jargon in the
lead shrinks the population who will use the product, so the exact sentence was RELOCATED, never
deleted. ⛔ The plain lead may never be the stronger of the two — it carries the same hedges in shorter
words, and `betting_ml/tests/test_nf_tr1_claim_copy.py` holds each one with its own RED-proven clause.

🔒 ENTITLEMENT: this is the PUBLIC half of NF3.2's season-scoped split (past seasons public, the current
season locked behind subscription — enforced in `app/backend/routers/fantasy_public.py`, which reads
what this script writes and NOTHING ELSE). The export is structurally incapable of ever emitting
`LOCKED_SEASON` or later — `_parse_seasons` refuses such a range outright, so a public payload can never
carry the paid product regardless of how this script is invoked.

RUN (LAPTOP, SF-free sports lake) — STAGE LOCALLY, uploads nothing:
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.export_track_record_json \
      --duckdb quant_sports_intel_models/sports_dbt/sports.duckdb --seasons 2019-2025

PUBLISH TO PROD (LAPTOP) — ⚠️ `--publish` ALONE IS NOT ENOUGH; NAME THE BUCKET:
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.export_track_record_json \
      --duckdb quant_sports_intel_models/sports_dbt/sports.duckdb --seasons 2019-2025 \
      --s3-bucket credence-prod-s3-api-cache --publish

`--s3-bucket` defaults to `$CACHE_BUCKET`, which is NOT set in a normal laptop shell — so
`--publish` on its own resolves no bucket and the run refuses (loudly, by design: it would
otherwise look successful while uploading nothing). This has bitten the operator repeatedly,
which is why the full publish invocation is written out above rather than described. Copy it.

Same NF-D12 dry-run/`--publish` guard as `export_draft_board_json.py`: a resolved `--s3-bucket` /
`$CACHE_BUCKET` alone never uploads — pass `--publish` to actually reach the live prod api-cache.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from quant_sports_intel_models.football.nfl.fantasy import benchmark_scorecard as BS  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import player_naming as PN  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy.export_draft_board_json import (  # noqa: E402
    _fnum,
    load_projections_local,
)
from quant_sports_intel_models.football.nfl.fantasy.run_season_projection import (  # noqa: E402
    MARTS_SCHEMA,
    load_realized_season,
)

log = logging.getLogger("nfl.fantasy.export_track_record")

_ARTIFACTS = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/artifacts"
_REPORT_DIR = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/ablation_results"
_STAGING_OUT = _ARTIFACTS / "track_record_json"

# The current/upcoming season — the PAID product. The public export refuses (hard error, not a
# convention) to ever include this season or later. Kept as one named constant so a future season
# rollover is a one-line change, not a re-audit of every call site.
LOCKED_SEASON = 2026

# Copied verbatim from `test_nf1_5b_served_board.py`'s denylist — a headline built from the scorecard's
# own numbers must never drift into one of these overclaims either.
#
# NF-TR1 EXTENDED IT, and the extension is the point of the story rather than housekeeping. Two
# additions, each closing a hole the original set could not see:
#
#   * The GOVERNANCE terms. `betting_ml/governance/gates._DEFAULT_CLAIM_DENYLIST` screens the copy a
#     MODEL PROMOTION publishes; this one screens the copy the TRACK RECORD publishes. They were
#     written apart and each carried terms the other lacked ("beats the market" / "market-beating" /
#     "profitable" here; "all four" / "more accurate" there), so the same sentence could pass one
#     surface and fail the other. This tuple is now a SUPERSET of the gates' set and
#     `test_nf_tr1_claim_copy.py` asserts that mechanically — ⛔ a term may be added to the gates'
#     list, never removed from this one.
#
#   * The PLAIN-ENGLISH forms. NF-TR1 writes a consumer lead in everyday words, and the whole
#     hazard the story exists to prevent is that plainer prose sounds punchier by dropping the
#     hedge. The analyst-register denylist could not see "win your league" or "beats ADP" because
#     no analyst-register sentence would have said them. A denylist screening plain copy needs the
#     plain overclaims in it.
#
# ⚠️ These are SUBSTRING matches over lowercased text, so keep entries short and un-punctuated —
# "beats adp" catches "beats ADP by a mile", but "beats adp." would not.
_CLAIM_DENYLIST = (
    # the original NF3.2 set
    "we beat", "beat the market", "beat consensus", "every position", "all four",
    "our edge", "guaranteed", "more accurate",
    # the governance-gate set (betting_ml/governance/gates._DEFAULT_CLAIM_DENYLIST)
    "beats the market", "outperforms the market", "market-beating", "profitable",
    "edge over the market",
    # the plain-English overclaims NF-TR1's consumer lead could reach for
    "beats adp", "beat adp", "beats ecr", "beat ecr", "win your league", "wins your league",
    "sure thing", "can't miss", "risk-free", "always right", "never wrong",
)

# ── E9.56c: display casing ───────────────────────────────────────────────────────────────────────
# The projection frame carries VETERAN names in SHOUTING CAPS ("JOSH ALLEN") while ROOKIES arrive
# properly cased from the draft-class pipeline ("Ashton Jeanty") — 388 of 563 distinct names across
# 2019–2025 are all-caps. On the public Track Record board that renders as a page where the rookies
# look like the anomaly, which is what the operator reported: the right symptom, on the wrong side —
# it is the veterans that are wrong.
#
# ⚠️ CASING IS NOT RECOVERABLE FROM AN UPPERCASE STRING BY RULE, and this dataset proves it:
# "DEVONTA FREEMAN" is correctly "Devonta Freeman" while "DEVONTA SMITH" is correctly "DeVonta
# Smith" — identical input, two different right answers. So there is a rule pass for the patterns
# that ARE decidable, plus an explicit map keyed on the WHOLE name for the ones that are not.
#
# The map was DERIVED from the live export, not guessed: every all-caps name across all seven
# published seasons was scanned for an internal capital. Nine entries, needing an addition roughly
# once per draft class — and `test_track_record_export.py` asserts no name is ever emitted in
# all-caps, so a miss shows up as a visibly SHOUTING name rather than a silently wrong one.
#
# ⛔ Do NOT "fix" this by joining names from the current draft board: that board renders "Aj Barner"
# and "Dj Moore" (measured against the live API), i.e. it is WORSE than these rules, and it cannot
# cover retired players at all. The real fix is upstream — the projection frame should carry
# nflverse's `player_display_name` — which is a data-pipeline change, not a display fix.
#
# ── E9.61: THE SOURCE ALSO SHIPS NAMES THAT ARE ALREADY CASED AND ALREADY WRONG ─────────────────
#
# The map above only fires on an ALL-CAPS input, because the premise was that a name arriving in
# mixed case came from the clean draft-class pipeline and was therefore right. Measured against the
# SERVED 2026 payload, that premise is false: `Mack Hollins` is published as **"MacK Hollins"** —
# real name, mixed case, an internal capital in the wrong place — so `display_name` returns it
# untouched and the shouting guard scores it healthy.
#
# ⚠️ IT IS NOT OUR RULE PASS DOING IT. There is no `Mac` rule anywhere in this repo (`\bMc([a-z])`
# cannot match "Mack" — M-a-c-k contains no "Mc"), and the value is identical in the raw capture,
# the board and the projections. The defect is CARRIED IN THE DATA, which is precisely the argument
# for the upstream fix noted above: a projection frame on nflverse's `player_display_name` would
# not produce it. Until then the display layer is the only place it can be corrected.
#
# Keyed on the CASEFOLDED whole name and applied to EVERY input, cased or not — a repair, not a
# de-shouting. Deliberately still a whole-name lookup rather than a rule: "MacK" → "Mack" as a
# pattern would also rewrite the legitimately-capitalised "MacKenzie"/"MacKay" family.
#
# ⛔ SCOPE, STATED PLAINLY: this corrects the TRACK RECORD board only. `export_draft_board_json.py`
# — which produces the projections and league boards the live Rankings/Projections/Player Search
# surfaces read — applies no casing pass at all, so "MacK Hollins" is still what those serve. Giving
# it one is a change to the launch artifact that only takes effect on an operator re-export, so it
# is carded with the upstream fix rather than smuggled into a display patch.
# ── E9.61: THE HAND MAP IS DEMOTED TO A BACKSTOP BEHIND A DERIVED AUTHORITY ─────────────────────
#
# Everything above described a nine-entry map, maintained roughly once per draft class, standing in
# for casing that a rule cannot recover. `player_naming.roster_casing_authority` now supplies it from
# the nflverse roster history, keyed on gsis id, covering 95.1% of the 1,664 players across the seven
# published seasons — and it reproduces EIGHT of those nine names exactly (CEEDEE LAMB, DEANDRE
# HOPKINS, DEVANTE PARKER, DEVONTA SMITH, DK METCALF, JUJU SMITH-SCHUSTER, LESEAN MCCOY, SAM LAPORTA).
#
# The ninth is the interesting one and it is why `_REPAIRS` still exists over there: "DEVON ACHANE" ->
# "De'Von Achane" ADDS AN APOSTROPHE, so it is not a pure case change, so the casefold gate that makes
# the authority safe refuses it — correctly, by the same rule that stops the roster overwriting
# "Hollywood Brown" with "Marquise Brown". A repair that changes characters is a different KIND of
# claim from a repair that changes case, and it keeps needing a human.
#
# ⭐ THE EIGHT ARE KEPT, NOT DELETED — as `player_naming._FALLBACK_CASINGS`, consulted only when the
# authority has no row. Deleting them looked clean and was wrong: the authority is a best-effort S3
# read, and without the map an unreachable roster does not merely fail to improve the names, it makes
# these eight WORSE than the pre-authority behaviour ("DEVONTA SMITH" -> "Devonta Smith"). The two
# tests below caught exactly that when the map was first removed — a test that passed before a
# refactor and fails after it is reporting lost coverage, not obstructing the refactor.
#
# ⛔ Do NOT re-add a casing entry here or in `_REPAIRS`. If a name is mis-cased, the authority either
# already knows or the roster row itself is wrong — the second is worth reporting upstream, not
# papering over locally, and a local paper-over is invisible to the other renderer.
def display_name(raw, authority: str | None = None) -> str:
    """A source name rendered for display — delegated to `player_naming.display_name`, the ONE casing
    authority shared with the draft-board export (E9.61 item 4).

    Kept as a thin wrapper rather than an import alias so this module's existing callers and tests
    keep their entry point, and so the docstring above can carry the map's retirement note."""
    return PN.display_name(raw, authority)


def _nf1_5_projection(con, season, schema):
    """The NF1.5 refined-board projection for `season` — the SAME served board NF1.5b shipped, read
    from its persisted local artifact. See `run_benchmark_scorecard._nf1_5_projection` (identical, kept
    local here so this script has no CLI-module import)."""
    return load_projections_local(season, source="nf1_5")


def build_player_track_record(con, season, schema) -> pd.DataFrame:
    return BS.player_track_record_frame(
        con, season, schema, project_fn=_nf1_5_projection, load_realized_fn=load_realized_season,
    )


def _inum(v) -> int | None:
    """Null-safe int — `adp_rank` is legitimately missing for a season FFC never archived (e.g. 2025;
    see `player_track_record_frame`'s no-ADP fallback), and `int(pd.NA)` raises."""
    return None if pd.isna(v) else int(v)


def season_records(df: pd.DataFrame, casing: dict[str, str] | None = None) -> list[dict]:
    """The per-player frame -> compact display-ready JSON records for one season.

    `casing` is the nflverse roster's own spelling per gsis id (`player_naming`), used for CASE ONLY.
    Optional so the existing offline callers/tests keep working; omitted, the rule pass still runs."""
    casing = casing or {}
    recs = []
    for _, r in df.iterrows():
        recs.append({
            "season": int(r["season"]),
            "playerId": str(r["player_id"]),
            "playerName": display_name(r["player_name"], casing.get(str(r["player_id"]))),
            "position": str(r["position"]),
            "ourPoints": _fnum(r["our_points"]),
            # The EXPECTED-GAMES figure `ourPoints` is scaled by. ⭐ It is what makes the points
            # column legible: our published total prices in the chance a player misses time, so it
            # sits below an "if he plays every week" projection AND below a healthy player's
            # finished season — and a reader with no games figure beside it reads that as a broken
            # model rather than as the disclosure it is.
            #
            # ⚠️ ADDITIVE, and it has to be: `fantasy_public.py`'s season route ships the records
            # through with no `response_model`, but the FRONTEND deploys on merge while this
            # payload only gains the key when the operator re-runs the export with `--publish`
            # (NF-C0's skew, artifact-side). So the consumer treats a missing/null `projGames` as a
            # normal render, never as an error — and MUST NOT infer one from `ourPoints`.
            "projGames": _fnum(r.get("proj_games"), 1),
            "ourRank": int(r["our_rank"]),
            "adp": _fnum(r["adp"], 1),
            "adpRank": _inum(r["adp_rank"]),
            "actualPoints": _fnum(r["actual_points"]),
            "actualRank": int(r["actual_rank"]),
            "isFade": bool(r["is_fade"]),
            # "hit" | "miss" | "push" | null — whether OUR rank or ADP's rank landed closer to the
            # actual finish (see `_fade_result`). Always null for a non-fade row (nothing to grade)
            # or a season with no ADP at all; never conflate with `isFade` — a fade can be a miss.
            "fadeResult": (None if pd.isna(r["fade_result"]) else str(r["fade_result"])),
            # NF3.2: "ffc" (the primary/established source), "mfl" (MyFantasyLeague — the fallback
            # used ONLY when FFC has no archive for this season, e.g. 2025), or null (neither source
            # had this season at all). Never silently blended — a consumer must be able to tell which
            # real-world draft population backs a given season's ADP column.
            "adpSource": (None if pd.isna(r["adp_source"]) else str(r["adp_source"])),
        })
    return recs


def adp_source_for_season(df: pd.DataFrame) -> str | None:
    """The single `adp_source` value backing every row in a season's frame (uniform per season by
    construction — see `player_track_record_frame`) — None if the season has no ADP at all."""
    if df.empty or "adp_source" not in df.columns:
        return None
    non_null = df["adp_source"].dropna()
    return str(non_null.iloc[0]) if len(non_null) else None


# ── NF-TR1: the two-layer claim ──────────────────────────────────────────────────────────────────
# The audience is the AVERAGE fantasy player, and analyst register in the LEAD shrinks the population
# who will use the product. So the claim ships as TWO layers, both honest and both denylist-screened:
#
#   lead    — plain everyday English, CALIBRATION FIRST (what the product gives you), the benchmark
#             comparison second and hedged in words a casual reader parses.
#   precise — the operator-approved sentence verbatim, plus the named benchmark, the metric, the
#             player count, the seasons and the visible interval.
#
# ⛔ THE PLAIN LEAD MAY NEVER BE THE STRONGER OF THE TWO. It carries the same four hedges as the
# precise layer (small · varies by position and season · a position where it is level · could be
# luck), just in shorter words. Dropping one to sound punchier is the exact failure NF-TR1 exists to
# prevent, and `test_nf_tr1_claim_copy.py` holds each hedge with its own RED-proven clause.
#
# ⭐ EVERY FIGURE IS READ, NEVER TYPED. `us`/`them`/`gap`/the per-position splits come from the NF-D3
# scorecard; the interval and the player count come from the NF-D17 population artifact. The two are
# RECONCILED before either is quoted (`_reconcile`) — an interval computed on a different population
# is not this claim's interval, and pairing them would be the most plausible-looking way to publish a
# wrong CI.

#: A per-position gap this small is not distinguishable from level at ANY reading, so the copy calls
#: it even rather than claiming a direction. Scale: the measured across-season SD is ~0.040 over 6
#: seasons ⇒ a season-level standard error near 0.016, so this band sits an order of magnitude below
#: the noise. It is a DISPLAY threshold — it decides which word is printed, never which number is.
_LEVEL_BAND = 0.005

#: How each context benchmark is named for a reader who has never heard of it. These are carried so
#: the page cannot be accused of reporting only the comparison that flatters us — every one of them
#: currently orders BETTER than we do, and the copy says so.
_CONTEXT_BENCHMARKS = {
    "ecr": "FantasyPros expert consensus (ECR)",
    "espn": "ESPN's rankings",
    "sleeper": "Sleeper's rankings",
}


def _pos_word(pos: str) -> str:
    return {"QB": "quarterback", "RB": "running back", "WR": "wide receiver",
            "TE": "tight end", "K": "kicker", "DST": "defense"}.get(pos, pos)


def _verdict(delta: float) -> str:
    """"ahead" / "behind" / "even" for a measured gap — the ONLY place a direction word is chosen."""
    if delta > _LEVEL_BAND:
        return "ahead"
    if delta < -_LEVEL_BAND:
        return "behind"
    return "even"


def _join(words: list[str]) -> str:
    if not words:
        return ""
    if len(words) == 1:
        return words[0]
    return ", ".join(words[:-1]) + " and " + words[-1]


def _screen(label: str, text: str) -> str:
    """Raise if `text` trips the overclaim denylist. Applied to EVERY string the claim publishes.

    Defense in depth against a future edit to the templates below, not just a test — the test can
    only screen the shapes it thinks to construct, whereas this runs over whatever the live artifacts
    actually produce at export time."""
    lowered = text.lower()
    for banned in _CLAIM_DENYLIST:
        if banned in lowered:
            raise ValueError(
                f"generated claim copy ({label}) contains a banned overclaim phrase {banned!r}: {text!r}"
            )
    return text


def _adp_aggregate(scorecard: dict) -> dict:
    agg = (scorecard.get("aggregate") or {}).get("adp")
    if not agg:
        raise ValueError(
            "scorecard JSON has no 'aggregate.adp' — cannot build an honest headline without it. Run "
            "run_benchmark_scorecard.py --projection-source nf1_5 first."
        )
    return agg


def _adp_span(scorecard: dict) -> tuple[list[int], str]:
    """The seasons that actually carry an `adp` system, and their span as display text.

    `seasons_scored` is EVERY scored season across ALL systems (ecr/espn/sleeper included) — NOT the
    ADP-specific set `agg['n_seasons']` counts. FFC has no archive for some seasons (2025 confirmed
    live), so using `seasons_scored` here would print a self-contradicting span like
    "6 past seasons (2019-2025)"."""
    seasons = sorted(
        row["season"] for row in (scorecard.get("per_season") or [])
        if "adp" in (row.get("systems") or {})
    )
    return seasons, (f"{seasons[0]}–{seasons[-1]}" if seasons else "the scored seasons")


def shipped_uncertainty(uncertainty: dict) -> dict:
    """The NF-D17 reading the PUBLIC claim is about — P0_shipped × `adp`, with its bootstrap.

    ⚠️ NF-D17 scored 57 population × source cells and several of them read far higher than the
    shipped one (MFL over its own deeper population is +0.173). Selecting a cell by its value is the
    inversion that memo exists to prevent, so the population and source are PINNED here as literals
    and a missing cell RAISES rather than falling back to whatever else is in the file."""
    for row in uncertainty.get("results") or []:
        if row.get("population") == "P0_shipped" and row.get("source") == "adp":
            boot = row.get("bootstrap") or {}
            if not boot.get("evaluated"):
                raise ValueError(
                    "the NF-D17 P0_shipped×adp row carries no EVALUATED bootstrap — the claim's "
                    "interval is a required disclosure, and an interval that was never computed "
                    "cannot be published as one."
                )
            return row
    raise ValueError(
        "uncertainty JSON has no P0_shipped × 'adp' result — that is the population the public claim "
        "is about. Re-run run_nf_d17_population_sensitivity.py; do NOT substitute another cell."
    )


def _reconcile(agg: dict, unc: dict, adp_seasons: list[int]) -> None:
    """The interval must belong to the number it is published beside.

    The scorecard and the NF-D17 artifact are regenerated by DIFFERENT scripts on different days.
    Quoting one's Δρ next to the other's interval would look completely normal and be wrong, and no
    downstream reader could detect it — so the agreement is asserted here, at the only point where
    both are in hand."""
    got, want = float(unc["delta_rho_mean"]), float(agg["delta_rho_pooled"])
    if abs(got - want) > 0.001:
        raise ValueError(
            f"the NF-D17 interval describes a Δρ of {got:+.3f} but the scorecard reports "
            f"{want:+.3f} — these are different readings and their numbers must not be mixed. "
            f"Regenerate both from the same board."
        )
    if int(unc["n_seasons"]) != len(adp_seasons):
        raise ValueError(
            f"the NF-D17 interval covers {unc['n_seasons']} season(s) but the scorecard's ADP span "
            f"is {len(adp_seasons)} ({adp_seasons}) — the interval is for a different span."
        )


def build_claim(scorecard: dict, uncertainty: dict) -> dict:
    """The manifest's two-layer honest claim. Every number is read from the two artifacts.

    Raises rather than degrading if either artifact is missing what the claim must disclose: an
    unpublishable claim is a loud failure, never a quietly weaker one (NF1.7 (a) — a disclosure that
    could not be evaluated is not a disclosure that passed)."""
    agg = _adp_aggregate(scorecard)
    adp_seasons, span = _adp_span(scorecard)
    unc = shipped_uncertainty(uncertainty)
    _reconcile(agg, unc, adp_seasons)

    us, them, gap = agg["us_rho_pooled"], agg["system_rho_pooled"], agg["delta_rho_pooled"]
    boot = unc["bootstrap"]
    ci_lo, ci_hi = float(boot["lo"]), float(boot["hi"])
    ci_level = int(round(float(boot["level"]) * 100))
    could_be_luck = ci_lo <= 0.0 <= ci_hi
    n_mean = int(round(float(unc["n_mean"])))

    by_pos = [
        {"position": pos, "deltaRho": round(float(d), 3), "verdict": _verdict(float(d))}
        for pos, d in sorted((agg.get("delta_rho_by_pos") or {}).items())
    ]
    level_positions = [_pos_word(p["position"]) for p in by_pos if p["verdict"] == "even"]
    behind_positions = [_pos_word(p["position"]) for p in by_pos if p["verdict"] == "behind"]

    others = []
    for key, label in _CONTEXT_BENCHMARKS.items():
        o = (scorecard.get("aggregate") or {}).get(key)
        if not o:
            continue
        others.append({
            "key": key, "label": label,
            "deltaRho": round(float(o["delta_rho_pooled"]), 3),
            "usRho": round(float(o["us_rho_pooled"]), 3),
            "benchmarkRho": round(float(o["system_rho_pooled"]), 3),
            "nSeasons": int(o["n_seasons"]),
            "verdict": _verdict(float(o["delta_rho_pooled"])),
        })

    lead = _screen("lead", _build_lead(
        span=span, n_seasons=agg["n_seasons"], gap=gap, could_be_luck=could_be_luck,
        level_positions=level_positions,
    ))
    precise = _screen("precise", _build_precise(
        span=span, n_seasons=agg["n_seasons"], us=us, them=them, gap=gap,
        n_mean=n_mean, n_min=int(unc["n_min"]), n_max=int(unc["n_max"]),
        ci_lo=ci_lo, ci_hi=ci_hi, ci_level=ci_level, could_be_luck=could_be_luck,
    ))
    disclosures = [
        _screen(f"disclosure[{i}]", d)
        for i, d in enumerate(_build_disclosures(
            level_positions=level_positions, behind_positions=behind_positions, others=others,
            ci_lo=ci_lo, ci_hi=ci_hi, ci_level=ci_level, could_be_luck=could_be_luck,
        ))
    ]

    return {
        "lead": lead,
        "precise": precise,
        "benchmark": "the captured preseason ADP benchmark (Fantasy Football Calculator's "
                     "real-draft consensus, archived for each season before it started)",
        "benchmarkShort": "captured ADP",
        "metric": "pooled within-position rank correlation against the realized PPR finish",
        "seasons": span,
        "nSeasons": int(agg["n_seasons"]),
        "playersPerSeason": n_mean,
        "playersPerSeasonMin": int(unc["n_min"]),
        "playersPerSeasonMax": int(unc["n_max"]),
        "usRho": round(float(us), 3),
        "benchmarkRho": round(float(them), 3),
        "deltaRho": round(float(gap), 3),
        "ciLow": ci_lo,
        "ciHigh": ci_hi,
        "ciLevel": ci_level,
        "ciIncludesZero": could_be_luck,
        "byPosition": by_pos,
        "otherBenchmarks": others,
        "disclosures": disclosures,
        "method": _screen("method", _METHOD_NOTE),
        "architecture": _screen("architecture", _ARCHITECTURE_NOTE),
    }


#: The frozen-board method, in plain words. TRUE OF THE CODE, not aspirational: `run_nf1_5
#: .build_season_projection` trains on `[b for b in range(base_from, base_season) if b + 1 <
#: projection_season]` — strictly the seasons already complete before the projected one — and
#: `benchmark_scorecard.player_track_record_frame` grades that board against the ADP archived for
#: that same season.
_METHOD_NOTE = (
    "How the past seasons are graded: for each season we use the board as it would have stood "
    "before that season kicked off, built only from seasons that had already finished, and compare "
    "it with the draft-day consensus that was actually archived for that season. Nothing is "
    "re-ranked after the fact, and no season's own results are used to build its own board."
)

#: What the served board actually IS, so the copy cannot claim a mechanism it does not have. Mirrors
#: `export_draft_board_json.MARKET_LEAN_NOTE` — the same two-stack fact, said for a casual reader.
#: ⚠️ Both halves matter: the ORDER is not independent of the crowd, and the POINTS are not the
#: thing the ordering model changed. Dropping either half turns an honest re-ORDERING claim into an
#: implied re-pricing one.
_ARCHITECTURE_NOTE = (
    "How the board is built: two models stacked. The projected points and the range around them "
    "come from a model that never looks at the draft market. A second model then decides the ORDER "
    "players are ranked in, and at most positions that ordering blends the market's own consensus "
    "with our model — so our order is not an independent read on the market, and a gap between our "
    "ranking and the market's is a smaller, less independent signal than it looks. What the second "
    "model changes is which player gets which projected point total; it never changes the totals "
    "themselves."
)


def _build_lead(*, span: str, n_seasons: int, gap: float, could_be_luck: bool,
                level_positions: list[str]) -> str:
    """The CONSUMER lead: what the product gives you FIRST, the benchmark comparison second.

    ⭐ SIGN-AWARE AND INTERVAL-AWARE BY CONSTRUCTION. Plain prose reads as a claim in a way the old
    analyst phrasing did not ("is 0.517, against ADP's 0.494" asserted no direction and stayed true
    either way; "did a little better" does not). So a negative gap must produce a DIFFERENT sentence
    rather than a quietly false one, and the "could just be luck" hedge is printed only while the
    measured interval actually includes zero — a hedge that survives its own evidence is decoration,
    and one that is dropped by hand is the failure this story exists to prevent."""
    hook = (
        "Credence projects a full season of fantasy points for every player, scored the way YOUR "
        "league scores — with a range around each number so you can see how confident we are, and "
        "the inputs behind it laid out rather than hidden."
    )
    if gap > 0:
        size = "a little" if gap < 0.05 else "clearly" if gap < 0.15 else "much"
        record = (
            f"As for the track record: across the {n_seasons} seasons from {span}, our preseason "
            f"order within each position turned out {size} closer to how those years actually "
            f"finished than the draft-day consensus did."
        )
    elif gap < 0:
        record = (
            f"As for the track record: across the {n_seasons} seasons from {span}, the draft-day "
            f"consensus order held up better than ours did."
        )
    else:
        record = (
            f"As for the track record: across the {n_seasons} seasons from {span}, our preseason "
            f"order and the draft-day consensus finished level."
        )
    caveats = ["the gap is small", "it swings a lot from year to year and from position to position"]
    if level_positions:
        caveats.append(f"and at {_join(level_positions)} it is basically even")
    hedge = f"But {', '.join(caveats[:-1])}, {caveats[-1]}." if len(caveats) > 1 else f"But {caveats[0]}."
    if could_be_luck:
        hedge += " It is small enough that it could just be luck — we are not promising it repeats."
    else:
        hedge += " It is a record of what already happened, not a promise about next season."
    # ⛔ THE BLOCK MUST NOT END ON THE CAVEAT (NF-TR1 AC 5). The hedges are non-negotiable and every
    # one of them is above this line — but a paragraph that STOPS on "it could just be luck" leaves
    # a reader with a disclaimer as the last thing they read, and this page's job is to earn trust,
    # not to apologise. So it closes by pointing at the evidence that makes the caveats meaningful:
    # the per-season and per-position detail, and the disagreement view that is the genuinely
    # interesting use of a draft-market comparison. That is a CLOSE, not a walk-back — it adds no
    # claim and softens none of the four hedges above it.
    close = (
        "The season-by-season and position-by-position detail is below, along with the players we "
        "ranked furthest from where the crowd was drafting them."
    )
    return " ".join([hook, record, hedge, close])


def _build_precise(*, span: str, n_seasons: int, us: float, them: float, gap: float,
                   n_mean: int, n_min: int, n_max: int, ci_lo: float, ci_hi: float,
                   ci_level: int, could_be_luck: bool) -> str:
    """The PRECISE layer — the operator-approved sentence, then the numbers that back it.

    ⚠️ The approved wording ("modestly outperformed … and the confidence interval includes zero")
    is only TRUE while the measurement has that shape. It is emitted verbatim when it does and
    replaced when it does not, so this function can never print an approved-but-false sentence."""
    if gap > 0 and could_be_luck:
        approved = (
            "Credence's served-style board modestly outperformed the captured ADP benchmark on "
            "pooled within-position rank correlation from {span}. Results vary by position and "
            "season, and the confidence interval includes zero."
        ).format(span=span)
    elif gap > 0:
        approved = (
            f"Credence's served-style board outperformed the captured ADP benchmark on pooled "
            f"within-position rank correlation from {span}. Results vary by position and season."
        )
    elif gap < 0:
        approved = (
            f"Credence's served-style board did NOT lead the captured ADP benchmark on pooled "
            f"within-position rank correlation from {span}. Results vary by position and season."
        )
    else:
        approved = (
            f"Credence's served-style board was level with the captured ADP benchmark on pooled "
            f"within-position rank correlation from {span}. Results vary by position and season."
        )
    measured = (
        f"Measured: pooled within-position Spearman rank correlation against the realized PPR "
        f"finish, {us:.3f} for our board against {them:.3f} for the benchmark (a gap of "
        f"{gap:+.3f}), over {n_seasons} seasons ({span}) and about {n_mean} ranked players per "
        f"season (range {n_min}–{n_max}). The {ci_level}% paired player-level bootstrap interval "
        f"around that gap runs from {ci_lo:+.3f} to {ci_hi:+.3f}"
    )
    measured += (", which includes zero." if could_be_luck else ".")
    return approved + " " + measured


def _build_disclosures(*, level_positions: list[str], behind_positions: list[str],
                       others: list[dict], ci_lo: float, ci_hi: float, ci_level: int,
                       could_be_luck: bool) -> list[str]:
    """The six required disclosures, in plain words, every one derived from the measurement.

    ⚠️ DERIVED, NOT ASSERTED. NF-TR1 requires "RB is a wash" — but writing that as a literal string
    would make it a claim about the data rather than a reading of it, and it would survive unchanged
    the day the data stopped saying it. The positions named below come from `delta_rho_by_pos`, so
    if a future re-export moves running back off level the sentence moves with it."""
    out: list[str] = []
    if level_positions:
        out.append(
            f"At {_join(level_positions)} it is a wash. Our order there was no better than the "
            f"draft-day consensus, and we do not claim it was."
        )
    else:
        out.append(
            "No position measured level this run; the position-by-position table below is the full "
            "split, including any position where we trail."
        )
    if others:
        note = (
            f"We are also measured against {_join([o['label'] for o in others])}. Those are "
            f"reported separately in the table below, and they are NOT part of the claim above."
        )
        # ⚠️ Named individually, never rolled up into "all of them". A future run where only SOME
        # trail must print only those — a blanket sentence would be false the first time one flipped,
        # and false in the direction that flatters us.
        trailing = [o["label"] for o in others if o["verdict"] == "behind"]
        if len(trailing) == len(others):
            note += " We do not lead any of them — every one orders better than we do."
        elif trailing:
            note += f" We do not lead {_join(trailing)} — those order better than we do."
        out.append(note)
    else:
        out.append(
            "The comparisons against expert consensus, ESPN and Sleeper are reported separately "
            "and are not part of this claim."
        )
    out.append(
        "Our draft order is not independent of the crowd: at most positions the ranking blends the "
        "market's own consensus with our model, so a gap between our order and the market's is a "
        "smaller and less independent signal than it looks."
    )
    out.append(
        "This is a record of what already happened over a handful of past seasons. It is not a "
        "guarantee, and nothing here says what any single player or any single season will do."
    )
    out.append(
        f"The uncertainty is shown, not hidden: the {ci_level}% range around the measured gap runs "
        f"from {ci_lo:+.3f} to {ci_hi:+.3f}"
        + (", which includes zero — meaning a gap of exactly nothing is still consistent with what "
           "we measured." if could_be_luck else ".")
    )
    out.append(_METHOD_NOTE)
    return out


def build_headline(scorecard: dict, uncertainty: dict) -> str:
    """The manifest's `headline` — now the CONSUMER LEAD (NF-TR1), not the analyst sentence.

    ⭐ THE FIELD KEPT ITS NAME ON PURPOSE. `headline` is quoted verbatim by the locked-surface
    upgrade banner and the player page, neither of which this branch changes, and by whatever future
    surface reuses it (E9.46's home hero). Renaming it would have left every one of those quoting a
    field that no longer exists; repointing it means they ALL inherit the plainer, better-hedged
    lead the moment the artifact is republished, with no client change and no deploy-order hazard.
    The analyst sentence is not lost — it moved to `claim.precise`."""
    return build_claim(scorecard, uncertainty)["lead"]


def _parse_seasons(spec: str) -> list[int]:
    lo_s, _, hi_s = spec.partition("-")
    lo, hi = int(lo_s), int(hi_s or lo_s)
    seasons = list(range(lo, hi + 1))
    locked = [y for y in seasons if y >= LOCKED_SEASON]
    if locked:
        raise SystemExit(
            f"--seasons {spec!r} includes {locked} — the public track-record export refuses to "
            f"ever emit season >= {LOCKED_SEASON} (the current LOCKED, subscriber-only season). Pass a "
            f"range strictly below {LOCKED_SEASON}."
        )
    return seasons


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--duckdb", default="quant_sports_intel_models/sports_dbt/sports.duckdb")
    ap.add_argument("--schema", default=MARTS_SCHEMA)
    ap.add_argument("--seasons", default="2019-2025",
                    help="inclusive season range, e.g. 2019-2025 (default). Every season in the range "
                         "must already have a built nf1_5_season_projections_<year>.parquet — see "
                         "run_nf1_5.py --mode build --projection-season <year>.")
    ap.add_argument("--scorecard-json", type=Path,
                    default=_REPORT_DIR / "nf_d3_benchmark_scorecard_nf1_5.json",
                    help="the FRESH NF-D3 scorecard (nf1_5 projection source) — the single source "
                         "of truth for the manifest's honest headline numbers.")
    ap.add_argument("--uncertainty-json", type=Path,
                    default=_REPORT_DIR / "nf_d17_track_record_population.json",
                    help="the NF-D17 population-sensitivity artifact — the source of truth for the "
                         "claim's PLAYER COUNT and its bootstrap INTERVAL. Required: the interval "
                         "is a disclosure NF-TR1 mandates, and an export that could not read one "
                         "must fail loudly rather than publish a claim with the uncertainty "
                         "quietly missing.")
    ap.add_argument("--out", type=Path, default=None, help="override the local staging output dir")
    ap.add_argument("--s3-bucket", default=os.getenv("CACHE_BUCKET"),
                    help="S3 bucket to upload to (default $CACHE_BUCKET). Uploaded under "
                         "fantasy/nfl/track_record/ where the PUBLIC /fantasy/nfl/track-record/* API "
                         "reads it. Resolving a bucket alone does NOT upload — pass --publish too.")
    ap.add_argument("--publish", action="store_true",
                    help="NF-D12 PUBLISH GUARD: actually upload to the LIVE prod api-cache bucket. "
                         "Without this flag the exporter always DRY-RUNS.")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    seasons = _parse_seasons(args.seasons)

    if not args.scorecard_json.is_file():
        raise SystemExit(
            f"no scorecard JSON at {args.scorecard_json} — run:\n"
            f"  uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_benchmark_scorecard "
            f"--from {seasons[0]} --to {seasons[-1]} --projection-source nf1_5"
        )
    if not args.uncertainty_json.is_file():
        raise SystemExit(
            f"no NF-D17 uncertainty JSON at {args.uncertainty_json} — the claim's interval and "
            f"player count are REQUIRED disclosures (NF-TR1), so the export refuses rather than "
            f"publishing a claim with the uncertainty silently absent. Run:\n"
            f"  uv run python -m quant_sports_intel_models.football.nfl.fantasy."
            f"run_nf_d17_population_sensitivity"
        )
    scorecard = json.loads(args.scorecard_json.read_text())
    uncertainty = json.loads(args.uncertainty_json.read_text())
    claim = build_claim(scorecard, uncertainty)

    if not Path(args.duckdb).exists():
        raise SystemExit(f"DuckDB not found at {args.duckdb} — build the NFL marts first")

    out_dir = args.out or _STAGING_OUT
    out_dir.mkdir(parents=True, exist_ok=True)

    import duckdb

    con = duckdb.connect(args.duckdb, read_only=True)
    seasons_written: list[int] = []
    adp_source_by_season: dict[str, str] = {}
    # E9.61: shared with the board export — the roster's own casing, for CASE ONLY. Resolved once
    # for every season (it is keyed on gsis id and takes each player's LATEST roster row, so a
    # retired player still resolves; that is what makes it usable for a seven-season back-catalogue).
    casing = PN.roster_casing_authority()
    log.info("name-casing authority: %d roster names", len(casing))
    try:
        for y in seasons:
            try:
                df = build_player_track_record(con, y, args.schema)
            except FileNotFoundError as e:
                raise SystemExit(
                    f"season {y}: {e}\nEvery season in --seasons must already have a built NF1.5 "
                    f"refined board — the export never silently drops a season, which would "
                    f"shrink the receipts universe with no error."
                ) from e
            if df.empty:
                log.warning("season %d: 0 scored players (thin ADP/realized overlap) — writing an "
                            "empty season file rather than silently skipping it", y)
            recs = season_records(df, casing)
            path = out_dir / f"season_{y}.json"
            path.write_text(json.dumps(recs, separators=(",", ":")))
            seasons_written.append(y)
            src = adp_source_for_season(df)
            if src:
                adp_source_by_season[str(y)] = src
            log.info("wrote %s (%d players, %d fades, adp_source=%s)", path.name, len(recs),
                     sum(1 for r in recs if r["isFade"]), src)
    finally:
        con.close()

    manifest = {
        "seasons": seasons_written,
        # NF3.2: which ADP source backs each season — "ffc" (primary) or "mfl" (MyFantasyLeague,
        # fallback used ONLY when FFC has no archive at all, e.g. 2025). A season absent from this
        # dict has no ADP from either source. The frontend uses this to label a fallback season
        # honestly rather than presenting it as an unlabeled "ADP" identical to every other season.
        "adpSourceBySeason": adp_source_by_season,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        # NF-TR1: `headline` IS the consumer lead. Kept under its original key so the surfaces that
        # already quote it verbatim (the locked-surface upgrade banner, the player page, and E9.46's
        # home hero when it lands) inherit the plainer, better-hedged wording with no client change —
        # ADDITIVE, per the NF-C0 deploy-skew rule. The analyst sentence lives on in `claim.precise`.
        "headline": claim["lead"],
        "claim": claim,
        "lockedSeason": LOCKED_SEASON,
        "scorecardGeneratedAt": datetime.fromtimestamp(
            args.scorecard_json.stat().st_mtime, tz=timezone.utc
        ).isoformat(),
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    log.info("wrote manifest.json — seasons %s", seasons_written)
    log.info("track-record JSON staged in %s", out_dir)

    _maybe_publish(out_dir, args.s3_bucket, args.publish)
    return 0


def _maybe_publish(out_dir: Path, bucket: str | None, publish: bool) -> None:
    """The same 4-branch NF-D12 publish guard as `export_draft_board_json._maybe_publish` (no
    bucket+no publish=warn; no bucket+publish=SystemExit; bucket+no publish=dry-run report;
    bucket+publish=upload) — kept local rather than cross-imported so this script stays
    self-contained like its template."""
    prefix = "fantasy/nfl/track_record"
    if not bucket:
        if publish:
            raise SystemExit(
                "--publish was passed but NO BUCKET resolved (--s3-bucket / $CACHE_BUCKET is unset "
                "or empty), so nothing would be uploaded and the run would have looked successful. "
                "Re-run with the bucket named explicitly:\n"
                "  --s3-bucket credence-prod-s3-api-cache --publish"
            )
        log.warning(
            "no --s3-bucket / $CACHE_BUCKET — track-record JSON staged locally only; the public "
            "API will 404 until it is uploaded to s3://<bucket>/%s/", prefix,
        )
        return
    files = sorted(out_dir.glob("*.json"))
    if not publish:
        log.info(
            "[DRY-RUN] would upload %d file(s) to s3://%s/%s/ — pass --publish to actually reach "
            "the LIVE prod api-cache: %s",
            len(files), bucket, prefix, ", ".join(p.name for p in files),
        )
        return
    log.warning("\U0001f6a8 PUBLISHING TO LIVE PROD api-cache — s3://%s/%s/ (%d files)",
                bucket, prefix, len(files))
    import boto3

    s3 = boto3.client("s3", region_name="us-east-1")
    for path in files:
        s3.put_object(
            Bucket=bucket, Key=f"{prefix}/{path.name}", Body=path.read_bytes(),
            ContentType="application/json",
        )
    log.info("uploaded %d track-record files to s3://%s/%s/", len(files), bucket, prefix)


if __name__ == "__main__":
    raise SystemExit(main())
