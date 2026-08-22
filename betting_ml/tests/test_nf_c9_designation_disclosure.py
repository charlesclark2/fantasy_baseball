"""NF-C9 — DISCLOSING THE WEEKLY GAME-STATUS DESIGNATION: the honesty clauses, executable.

WHAT THIS STORY DOES, AND — more importantly — WHAT IT DELIBERATELY DOES NOT.

NF-C8's finding (`ablation_results/nf_c8_injury_designation_gap.md`) traced a real gap between what
we hold and what we act on. The availability discount has exactly one entry point:
`season_projection.injury_availability_games` caps projected games for a formal ROSTER TRANSACTION
(injured reserve / PUP / non-football-injury / suspension) and returns everyone else unchanged, and
`sleeper_injuries_source.map_injury_status` returns NO OVERRIDE for a weekly game-report tag. So
**Questionable, Doubtful and Out apply a discount of exactly zero.** That is leakage-safe and
working as designed. It is also not what a reader assumes when they meet an "Out" player at a
normal-looking projection.

NF-C9 ships the interim §3 of that write-up recommends: **disclose the designation, model nothing.**
The projection is byte-identical before and after. One string per player reaches the payload, and a
sentence beside the projected-games figure says plainly that the figure does not price it in.

⛔⛔ THE TWO FAILURES THIS SUITE EXISTS TO PREVENT, and they pull in opposite directions:

  1. THE DISCLOSURE QUIETLY BECOMES AN ADJUSTMENT. Not by lying — by hedging. "We take his status
     into account", "reflected in the projection", "factored in": each is ordinary product copy and
     each is FALSE about this channel. `_ADJUSTMENT_CLAIMS` holds that list. And the same failure
     has a CODE form, which is the worse one: the moment anything in the projection path reads this
     field, the copy stops being true and nothing else in the repo would notice.
  2. IT BECOMES A MEDICAL FORECAST. This renders a real designation about a NAMED PERSON, so the
     distance between "a club listed him Questionable for one game" and "he is hurt and will miss
     time" is one careless sentence. NF-C8's `_INJURY_FORECAST_VERBS` is imported VERBATIM rather
     than re-listed — two copies of a safety list drift, and the drifting one is always the one
     nobody is looking at.

⭐ ONE FIXTURE PER CLAUSE (NF-D17 §7), and `nf_c9_red_proof.py` proves each clause goes red on the
one thing it names.

Pure/offline (fast gate): reads source files, no DuckDB/S3/network.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from quant_sports_intel_models.football.nfl.fantasy import export_track_record_json as ex
from quant_sports_intel_models.football.nfl.fantasy import sleeper_injuries_source as SI

# ⭐ IMPORTED, NOT RE-LISTED. NF-C8 owns the injury-forecast boundary; a second copy here would drift
# and the drifted copy is the one nobody re-reads. Importing also means a phrase ADDED there is
# enforced here from the next run, with no edit.
from betting_ml.tests.test_nf_c8_availability_flag_copy import (  # noqa: E402
    _INJURY_FORECAST_VERBS,
    _strip_ts_comments,
    _ts_string_literals,
)

_REPO = Path(__file__).resolve().parents[2]
_CLAIM_COPY_TS = _REPO / "frontend/lib/fantasy-claim-copy.ts"
_SHARED_TSX = _REPO / "frontend/components/fantasy/shared.tsx"
_FANTASY_COMPONENTS = _REPO / "frontend/components/fantasy"
_EXPORTER = _REPO / "quant_sports_intel_models/football/nfl/fantasy/export_draft_board_json.py"
_SEASON_PROJECTION = (
    _REPO / "quant_sports_intel_models/football/nfl/fantasy/season_projection.py"
)

#: The copy constants this story added.
_NF_C9_CONSTANTS = (
    "WEEKLY_DESIGNATION_LABEL",
    "WEEKLY_DESIGNATION_SUMMARY",
    "WEEKLY_DESIGNATION_UNKNOWN_SUMMARY",
    "WEEKLY_DESIGNATION_NOT_MODELLED",
    "WEEKLY_DESIGNATION_NOT_A_DIAGNOSIS",
)

#: ⛔ THE CLAIMS THAT WOULD TURN A DISCLOSURE INTO AN ADJUSTMENT. Every one of these is a phrase a
#: product writer reaches for naturally, none is a lie about the product as a whole, and each is
#: false about THIS field: the projected-games figure does not move on a weekly designation.
#:
#: ⚠️ The scan is ABSOLUTE (negation-blind), for the reason NF-C8 records at length: a negation
#: WINDOW is a real hole, because the claim survives negation ("we do not merely take it into
#: account" still asserts we do). What stops that strictness from making the honest disclaimer the
#: cheapest thing to delete is that the disclaimer is independently REQUIRED by
#: `test_the_definition_says_out_loud_that_the_projection_does_not_price_it_in` below — the two
#: clauses only work as a pair.
_ADJUSTMENT_CLAIMS = (
    "priced in",
    "prices it in",
    "prices this in",
    "factored in",
    "factored into",
    "taken into account",
    "takes this into account",
    "takes it into account",
    "reflected in the projection",
    "reflected in our projection",
    "adjusted for",
    "accounted for",
    "already in the number",
    "built into the number",
    "built into the projection",
)

#: ⛔ A DURATION IS THE ONE QUANTITY A WEEKLY DESIGNATION DOES NOT CARRY. "Out" means out of ONE
#: game; the multi-week absence a news report describes is a NEWS fact, not a status fact — which is
#: precisely why NF-C8's write-up says a per-designation discount is a §0.5 modelling story and not
#: a config change. Copy that implied a length would be inventing exactly that missing quantity.
_DURATION_CLAIMS = (
    "weeks",
    "for the season",
    "rest of the season",
    "multi-week",
    "how long he",
    "several games",
)


def _const(src: str, name: str) -> str:
    """The prose of one exported constant. Anchored on the assignment and terminated at the next
    top-level `export`, so a clause about one constant cannot be satisfied by a neighbour's
    wording."""
    body = src.split(f"export const {name}", 1)
    assert len(body) == 2, f"{name} is not exported from the canonical copy module"
    tail = body[1].split("\nexport const ", 1)[0]
    literals = _ts_string_literals(tail)
    assert literals, f"no prose extracted for {name} — every clause about it would be vacuous"
    return " ".join(literals).lower()


@pytest.fixture(scope="module")
def copy_src() -> str:
    return _CLAIM_COPY_TS.read_text()


def _component(name: str) -> str:
    """One exported component's body from `shared.tsx`, comments stripped."""
    src = _strip_ts_comments(_SHARED_TSX.read_text())
    parts = src.split(f"export function {name}", 1)
    assert len(parts) == 2, f"{name} is not exported from shared.tsx"
    return parts[1].split("\nexport ", 1)[0]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 0. The instruments. An extractor that silently returns nothing makes every clause below
#    vacuously true (NF1.7 (a)). Checked first, on purpose.
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_copy_extractor_actually_finds_every_nf_c9_constant(copy_src):
    for name in _NF_C9_CONSTANTS:
        prose = _const(copy_src, name)
        assert len(prose) > 20, f"{name} extracted as {prose!r} — clauses about it would be vacuous"


def test_the_component_extractor_finds_a_real_body():
    body = _component("WeeklyDesignation")
    assert "InfoTip" in body and len(body) > 200, (
        "the WeeklyDesignation extractor returned no usable body — every component clause below "
        "would pass on nothing"
    )


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. ⛔⛔ THE DISCLOSURE IS NOT AN ADJUSTMENT — the story's whole reason to exist
# ══════════════════════════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("name", _NF_C9_CONSTANTS)
def test_the_designation_copy_never_claims_the_projection_prices_it_in(name, copy_src):
    """⭐ THE CLAUSE THE STORY IS FOR. The designation applies a discount of EXACTLY ZERO, so any
    wording implying otherwise is false — and it is false in the flattering direction, which is the
    one that survives review.

    ⚠️ The one constant allowed to contain the negated form is `WEEKLY_DESIGNATION_NOT_MODELLED`,
    which says "does not take this into account" — and it is exempted BY NAME below rather than by a
    negation window, because a window would wave through the un-negated claim too."""
    prose = _const(copy_src, name)
    banned = _ADJUSTMENT_CLAIMS
    if name == "WEEKLY_DESIGNATION_NOT_MODELLED":
        # The disclaimer's own phrasing. It is the sentence that REFUSES the claim, and it is
        # separately required to be present by its own clause below.
        banned = tuple(c for c in banned if c != "taken into account")
        prose = prose.replace("does not take this into account", "")
    hits = [c for c in banned if c in prose]
    assert not hits, (
        f"{name} implies the projection acts on the weekly designation {hits} — it does not: "
        f"`injury_availability_games` moves only on a roster transaction, so the discount here is "
        f"exactly zero"
    )


def test_the_definition_says_out_loud_that_the_projection_does_not_price_it_in(copy_src):
    """The other half of the pair above. Screening the false claim is not enough — a chip beside a
    games figure reads as an adjustment by POSITION alone, whatever the words omit, so the words
    have to refuse it explicitly. This is the clause that would go quietly missing in a copy trim,
    and its absence would be invisible: the chip renders perfectly well without it."""
    prose = _const(copy_src, "WEEKLY_DESIGNATION_NOT_MODELLED")
    assert "does not" in prose, (
        "WEEKLY_DESIGNATION_NOT_MODELLED no longer states in the negative that the projected-games "
        "figure is unaffected — without it the chip reads as an adjustment we made"
    )
    assert "projected-games" in prose or "projected games" in prose, (
        "the disclaimer no longer names the projected-games figure, so a reader cannot tell WHICH "
        "number is unaffected"
    )


def test_the_disclaimer_names_what_the_projection_does_move_on(copy_src):
    """A bare "we do not price this in" invites the reading that we price nothing in. The honest
    version names the channel that DOES move the number — a formal roster move — which is both true
    and the thing that makes the boundary legible instead of arbitrary."""
    prose = _const(copy_src, "WEEKLY_DESIGNATION_NOT_MODELLED")
    assert "roster move" in prose, (
        "the disclaimer no longer names the roster transaction the availability discount actually "
        "moves on, so the boundary reads as arbitrary rather than as a scope limit"
    )


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. ⛔⛔ IT IS NOT A MEDICAL FORECAST, AND IT CARRIES NO DURATION
# ══════════════════════════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("name", _NF_C9_CONSTANTS)
def test_the_designation_copy_never_forecasts_an_injury(name, copy_src):
    """NF-C8's boundary, on the surface where it is closest. Same list, imported not re-listed."""
    prose = _const(copy_src, name)
    hits = [v for v in _INJURY_FORECAST_VERBS if v in prose]
    assert not hits, f"{name} forecasts an injury {hits}"


@pytest.mark.parametrize("name", _NF_C9_CONSTANTS)
def test_the_designation_copy_never_implies_a_duration(name, copy_src):
    """A weekly designation covers ONE game and says nothing about length. Implying a duration
    would invent the exact quantity whose absence is why this is a disclosure rather than a
    model."""
    prose = _const(copy_src, name)
    hits = [c for c in _DURATION_CLAIMS if c in prose]
    assert not hits, (
        f"{name} implies a length {hits} — a weekly designation carries no duration, and inventing "
        f"one is the failure NF-C8's write-up names as the reason this is not a ticket"
    )


def test_the_definition_says_out_loud_that_it_is_not_a_diagnosis(copy_src):
    """A designation chip beside a player's name reads as a medical claim unless the words refuse
    it. Required explicitly, so a rewrite that merely avoids the banned verbs still has to keep the
    refusal — the NF-C8 pairing, which is what stops the strict scan making the hedge deletable."""
    prose = _const(copy_src, "WEEKLY_DESIGNATION_NOT_A_DIAGNOSIS")
    assert "not a diagnosis" in prose, (
        "the designation definition no longer states it is not a diagnosis"
    )


def test_the_copy_attributes_the_designation_to_its_source_not_to_us(copy_src):
    """⭐ THE SUBJECT IS THE FILING, NEVER THE PLAYER. "A club filed this about one game" is a fact
    about a document we read; "he is banged up" is a claim about a person we have no standing to
    make, and the two are one noun apart."""
    for name in ("WEEKLY_DESIGNATION_SUMMARY", "WEEKLY_DESIGNATION_UNKNOWN_SUMMARY"):
        prose = _const(copy_src, name)
        assert "feed" in prose or "report" in prose, (
            f"{name} states the designation without naming the third-party source it came from — "
            f"unattributed, it reads as our own assessment of the player"
        )


@pytest.mark.parametrize("name", _NF_C9_CONSTANTS)
def test_the_designation_copy_passes_the_track_record_denylist(name, copy_src):
    """These strings ship on the free, public, unauthenticated boards, so they answer to the same
    screen as the track record's generated claim."""
    prose = _const(copy_src, name)
    hits = [t for t in ex._CLAIM_DENYLIST if t in prose]
    assert not hits, f"{name} makes a forbidden claim {hits}"


def test_no_designation_is_typed_into_the_copy(copy_src):
    """⛔ The head of the copy module's rule, applied to a designation instead of a figure: a status
    typed here cannot be reconciled against the feed it came from. The vocabulary lives in
    `sleeper_injuries_source.WEEKLY_DESIGNATIONS`, where it was MEASURED against a real snapshot."""
    prose = _const(copy_src, "WEEKLY_DESIGNATION_SUMMARY")
    assert "{status}" in prose, (
        "WEEKLY_DESIGNATION_SUMMARY no longer interpolates the served designation — it is either "
        "typed in or gone, and a summary with no status still renders perfectly well"
    )
    for label in SI.WEEKLY_DESIGNATIONS.values():
        assert label.lower() not in prose, (
            f"WEEKLY_DESIGNATION_SUMMARY types the designation {label!r} rather than reading it "
            f"from the payload"
        )


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. THE MODEL BOUNDARY — the code half of clause 1
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_a_modelled_roster_status_never_reaches_the_disclosure_channel():
    """⭐ THE DISCLAIMER IS TRUE BY CONSTRUCTION, NOT BY A CALLER REMEMBERING TO FILTER. For an
    IR/PUP/NFI/SUS row the sentence "our projected-games figure does not take this into account" is
    FALSE — the projection caps those at 4.0/7.0 games. `disclosable_designation` withholds them at
    the source, so no surface can render the disclaimer over a status it does not apply to."""
    for status in ("IR", "Reserve", "Injured Reserve", "PUP", "NFI", "Sus", "Suspended"):
        assert SI.map_injury_status(status) is not None, (
            f"{status!r} is no longer a MODELLED status — this fixture has stopped testing the "
            f"boundary it names"
        )
        assert SI.disclosable_designation(status) == (False, None), (
            f"{status!r} reaches the un-modelled disclosure channel, where the copy would tell a "
            f"reader we do not price it in — we do"
        )


def test_a_weekly_designation_is_disclosed_with_its_label():
    """The positive half. Without it, a `disclosable_designation` that returned `(False, None)` for
    everything would pass every clause above — the vacuous implementation that looks safest."""
    for raw, label in (("Out", "Out"), ("out", "Out"), ("Doubtful", "Doubtful"),
                       ("Questionable", "Questionable"), ("  Questionable ", "Questionable")):
        assert SI.disclosable_designation(raw) == (True, label), (
            f"{raw!r} is not disclosed as {label!r} — the weekly designations are the only thing "
            f"this channel exists to carry"
        )


def test_an_uninterpretable_value_is_disclosed_as_an_explicit_unknown():
    """NF1.7 (a) at the source. `NA` and `DNR` are REAL values on the live feed (measured
    2026-08-22: 13 and 2 rows on the season-2026 snapshot, one of them on a genuinely draftable
    receiver), so this branch is production behaviour rather than a hypothetical. Collapsing it into
    "no designation" would let a value we could not read render as a clean bill of health."""
    for raw in ("NA", "DNR", "COV", "some-tag-sleeper-adds-next-year"):
        assert SI.disclosable_designation(raw) == (True, None), (
            f"{raw!r} is silently dropped rather than disclosed as unknown — an unreadable status "
            f"would render as though the player carried none"
        )


def test_no_designation_at_all_says_nothing():
    """The normal state for ~93% of players (measured: 2,338 of 2,501 fed rows). Saying anything
    here would be a fabricated status on almost every row of every board."""
    for raw in (None, "", "   "):
        assert SI.disclosable_designation(raw) == (False, None), (
            f"{raw!r} produces a disclosure — a player the feed says nothing about must render "
            f"nothing, never an invented clean status"
        )


def test_the_disclosure_map_carries_no_games_number_or_weight():
    """⛔ THE ONE WAY THIS STORY COULD TURN INTO THE MODELLING STORY IT IS EXPLICITLY NOT. A weekly
    designation carries no duration, so any number attached to this map would be a hand-picked
    constant wearing a projection's clothing — the thing NF-C8's write-up says has to be an
    empirical designation → games-missed distribution fit on history, i.e. a §0.5 bake-off."""
    assert all(isinstance(v, str) for v in SI.WEEKLY_DESIGNATIONS.values()), (
        "WEEKLY_DESIGNATIONS has grown a non-string value — if that is a games penalty or a weight, "
        "this stopped being a disclosure and became an unbaked-off model"
    )


def test_the_projection_path_never_reads_the_disclosure_channel():
    """⭐ THE CODE FORM OF THE COPY CLAUSE, and the more durable one: the copy is only true while
    nothing in the availability path consumes this field. A future edit that wired `gameStatus` or
    `disclosable_designation` into `season_projection` would make every sentence above a lie without
    touching a single string."""
    src = _SEASON_PROJECTION.read_text()
    for token in ("disclosable_designation", "WEEKLY_DESIGNATIONS", "gameStatus"):
        assert token not in src, (
            f"season_projection.py reads {token} — the weekly designation has become a projection "
            f"input, and NF-C9's copy ('our projected-games figure does not take this into "
            f"account') is now false everywhere it renders"
        )


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4. THE EXPORTER — three states, and the one that must never be sprayed across a board
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_exporter_omits_the_key_where_there_is_nothing_to_disclose():
    """`_attach_designations` sets `gameStatus` only on the rows the feed has something to say
    about. A `gameStatus: null` on every row would render "unknown" under every player — the
    scary-word-everywhere failure NF-C8's freshness doc names, at board scale."""
    from quant_sports_intel_models.football.nfl.fantasy import export_draft_board_json as E

    recs = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
    n = E._attach_designations(recs, {"a": "Out", "b": None})
    assert n == 2
    assert recs[0]["gameStatus"] == "Out"
    assert recs[1]["gameStatus"] is None, (
        "an uninterpretable value is not carried through as an explicit null — it would render as "
        "no designation at all"
    )
    assert "gameStatus" not in recs[2], (
        "a player the feed says nothing about was given a `gameStatus` key — absent and null are "
        "different facts on this field, and null renders 'unknown'"
    )


def test_an_unreadable_feed_leaves_every_record_untouched():
    """The whole-map None case. A read failure must cost the DISCLOSURE only — never the boards,
    which are the draft-critical output, and never an invented status on a single row."""
    from quant_sports_intel_models.football.nfl.fantasy import export_draft_board_json as E

    recs = [{"id": "a"}, {"id": "b"}]
    assert E._attach_designations(recs, None) == 0
    assert E._attach_designations(recs, {}) == 0
    # ⚠️ AND THE ROWS THEMSELVES, not just the count — the red proof's "helpfully" default a missing
    # feed to an unknown-for-everyone map returns a nonzero count AND writes a key on every row, so
    # a count-only clause would have waved it through.
    assert all("gameStatus" not in r for r in recs), (
        "an unreadable designation feed still wrote a `gameStatus` key — every board row would "
        "render 'unknown' during a routine ingest gap"
    )


def test_the_exporter_read_is_best_effort_and_never_fails_the_export():
    """A provenance/disclosure enrichment that can raise turns a stale ingest into a missing board.
    Pinned in source because the failure only reproduces against a broken lake."""
    body = _EXPORTER.read_text().split("def weekly_designation_map", 1)
    assert len(body) == 2, "weekly_designation_map is gone from the exporter"
    fn = body[1].split("\ndef ", 1)[0]
    assert "except Exception" in fn and "return None" in fn, (
        "weekly_designation_map no longer swallows a lake-read failure — a stale Sleeper ingest "
        "would fail the whole board export"
    )


def test_an_unrecognised_token_is_reported_to_the_operator():
    """⭐ THE UI SAYS "unknown"; THIS IS WHERE ANYBODY LEARNS WHICH TOKEN. Without the export-time
    warning, adding a genuinely new designation to `WEEKLY_DESIGNATIONS` depends on somebody
    noticing one grey chip on one row of one board — i.e. it never happens, and the honest
    "unknown" quietly becomes permanent."""
    fn = _EXPORTER.read_text().split("def weekly_designation_map", 1)[1].split("\ndef ", 1)[0]
    # ⚠️ ANCHORED ON THE UNRECOGNISED BRANCH, NOT ON "[ALERT] NF-C9" ANYWHERE IN THE FUNCTION — the
    # red proof caught the weaker form: the read-failure banner a few lines up carries the SAME
    # prefix, so a clause scanning the whole function stayed green with this warning deleted
    # outright (INC-38's "a guard a neighbouring line can satisfy cannot fail").
    branch = fn.split("if unrecognised:", 1)
    assert len(branch) == 2, (
        "weekly_designation_map no longer branches on the tokens it could not interpret — nothing "
        "distinguishes 'we read every value' from 'we gave up on some of them'"
    )
    reported = branch[1]
    assert "log.warning" in reported and "WEEKLY_DESIGNATIONS" in reported, (
        "the exporter no longer WARNS about the game-status tokens it could not interpret, or no "
        "longer names the map to add them to — an unreadable designation renders as 'unknown' "
        "forever with nobody told, because the UI deliberately does not print the raw token"
    )


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 5. THE SURFACES — the same registry NF-C8 pins, because it is the same three cells
# ══════════════════════════════════════════════════════════════════════════════════════════════
#: ⭐ DERIVED FROM NF-C8's REGISTRY, not re-listed. The designation belongs exactly where the
#: projected-games figure is rendered — that is the number it is NOT in — so "which surfaces owe the
#: reader this" is by construction the same question NF-C8 already answered and already guards for
#: exhaustiveness. A second hand-written list here could only ever drift out of date silently.
from betting_ml.tests.test_nf_c8_availability_flag_copy import _GAMES_SURFACES  # noqa: E402

#: The player page's availability-tier ternary, by its opening condition and its closing marker.
#: Named here rather than inlined so a JSX reshuffle is one edit and an obvious one.
_PLAYER_PAGE_TIER_BRANCH = "availabilityTier(proj.g) != null ?"
_PLAYER_PAGE_TIER_BRANCH_END = "</InfoTip>\n                    )}"


@pytest.mark.parametrize("filename", _GAMES_SURFACES)
def test_every_games_surface_renders_the_designation(filename):
    """⚠️ THE BINDING, NOT THE IMPORT — a bare `"WeeklyDesignation" in src` is satisfied by the
    import statement alone, so a surface that imports it and renders nothing would pass."""
    src = _strip_ts_comments((_FANTASY_COMPONENTS / filename).read_text())
    assert re.search(r"<WeeklyDesignation\b", src), (
        f"{filename} renders a projected-games figure without the weekly designation beside it — "
        f"the gap NF-C8 found stays invisible on that surface (importing is not rendering)"
    )


@pytest.mark.parametrize("filename", _GAMES_SURFACES)
def test_every_surface_passes_the_served_status_rather_than_a_literal(filename):
    """The chip must read the PAYLOAD. A surface passing a hardcoded status would render a chip that
    looks right on every row and is a fabricated status on all but a few."""
    src = _strip_ts_comments((_FANTASY_COMPONENTS / filename).read_text())
    assert re.search(r"status=\{\s*\w+\.gameStatus\b", src), (
        f"{filename} does not pass the served `gameStatus` into WeeklyDesignation"
    )


def test_the_designation_is_not_nested_inside_the_availability_flag():
    """⭐⭐ THE CLAUSE THAT PROTECTS THE MOTIVATING CASE, and the mistake this story nearly made.

    The two disclosures are INDEPENDENT: the availability flag fires on OUR projection (a materially
    low `g`), this fires on a THIRD PARTY'S filing. Jordyn Tyson — the row that produced NF-C8's
    finding — sat at 13.6 projected games, ABOVE `LIMITED_AVAILABILITY_GAMES`, so he carries a
    designation and NO flag. A disclosure rendered from inside `AvailabilityFlag`, or from inside
    the player page's availability-tier branch, would therefore never have rendered for the player
    it was written for — and every other clause in this file would still have been green.

    ⚠️ THE PLAYER-PAGE HALF IS ANCHORED ON THE TERNARY'S OWN CLOSING MARKER, not on the first `)}`
    in the region. The red proof caught the crude form: a `<WeeklyDesignation>` buried in the
    ternary's ELSE arm sailed through it."""
    flag_body = _component("AvailabilityFlag")
    assert "WeeklyDesignation" not in flag_body, (
        "the designation renders from inside AvailabilityFlag — it would then appear only on rows "
        "whose projection is already discounted, which is precisely the population that does NOT "
        "need telling, and would skip the row that prompted the story"
    )
    page = _strip_ts_comments((_FANTASY_COMPONENTS / "player-page.tsx").read_text())
    start = page.find(_PLAYER_PAGE_TIER_BRANCH)
    assert start >= 0, "the player page's availability branch has moved — re-anchor this clause"
    end = page.find(_PLAYER_PAGE_TIER_BRANCH_END, start)
    assert end > start, "the player page's availability branch no longer closes as expected"
    inside = page[start:end]
    assert "WeeklyDesignation" not in inside, (
        "the player page renders the designation inside its availability-tier branch, so a "
        "designated player at a normal projected-games figure would show nothing — which is the "
        "shape of the row that produced the finding this story discloses"
    )
    assert "WeeklyDesignation" in page[end:], (
        "the player page does not render the designation outside the availability branch at all"
    )


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 6. THE COMPONENT — absent vs null vs value, and a tappable definition
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_an_absent_status_renders_nothing_and_a_null_one_renders_unknown():
    """⚠️ NF-FRESH2's rule, and BOTH directions are load-bearing here:
      • ABSENT (`undefined`) → render nothing. The key is absent when there is nothing to disclose —
        no designation, a roster move already priced, or no feed at all — and inventing "unknown"
        for those would put a scary word on ~93% of every board.
      • NULL → render "unknown". The feed said something the build could not read; dropping it
        silently would let an unreadable value pass as a clean bill of health (NF1.7 (a))."""
    body = _component("WeeklyDesignation")
    assert re.search(r"if\s*\(\s*status\s*===\s*undefined\s*\)\s*return\s+null", body), (
        "WeeklyDesignation does not distinguish an ABSENT status from a NULL one — either it "
        "renders 'unknown' on every undesignated row, or it drops an unreadable value silently"
    )
    # ⚠️ A WHOLE-TOKEN MATCH, and the red proof is why. `WEEKLY_DESIGNATION_UNKNOWN` is a PREFIX of
    # `WEEKLY_DESIGNATION_UNKNOWN_SUMMARY`, which the component renders two lines away — so a plain
    # substring clause stayed GREEN with both real uses of the unknown LABEL deleted.
    assert re.search(r"WEEKLY_DESIGNATION_UNKNOWN(?!_)", body), (
        "a null status no longer renders as unknown — an unreadable value is being dropped, which "
        "reads to a reader as a player carrying no designation at all"
    )


def test_the_component_never_invents_a_clean_status():
    """⛔ The one output here that would be worse than the gap this story closes. Silence is the
    correct rendering of "we were told nothing"; "Active"/"Healthy"/"Available" would be a
    fabricated medical claim on a named person, on the highest-traffic surface in the product."""
    body = _component("WeeklyDesignation").lower()
    for invented in ("active", "healthy", "available", "no injury", "cleared", "full go"):
        assert invented not in body, (
            f"WeeklyDesignation renders a fabricated clean status ({invented!r}) for a player the "
            f"feed says nothing about"
        )


def test_the_definition_travels_through_infotip_and_not_a_hover_only_tooltip():
    """E9.63/NF3's touch lesson. Radix's Tooltip closes on pointerdown by design and a `title=`
    attribute is hover-only, so on a phone — where most of these boards are read — the reader would
    meet a chip saying "OUT" with no way to reach the sentence saying we did not price it in. That
    is strictly worse than not rendering the chip."""
    body = _component("WeeklyDesignation")
    assert "<InfoTip" in body, (
        "the designation's definition no longer travels through InfoTip — it is unreachable on a "
        "touch device, leaving a bare status chip with no disclaimer behind it"
    )
    assert "title=" not in body, "the designation's definition is on a hover-only `title` attribute"


def test_the_component_prose_is_the_canonical_constants_and_not_retyped():
    """Retyping the wording would put the sentence that must not become an adjustment — or a medical
    forecast — outside every clause in this file and outside `test_nf_tr1_claim_copy.py`'s
    whole-module screen."""
    body = _component("WeeklyDesignation")
    for name in _NF_C9_CONSTANTS:
        assert name in body, f"WeeklyDesignation does not render {name}; its prose has been re-typed"


def test_the_disclaimer_renders_on_the_unknown_branch_too():
    """An unrecognised value is exactly as un-modelled as a recognised one. If the disclaimer sat
    only on the known branch, a reader meeting "unknown" would have no way to tell whether it moved
    the projection — and "unknown" plus silence reads more like a model input than a designation
    does."""
    body = _component("WeeklyDesignation")
    assert "WEEKLY_DESIGNATION_UNKNOWN_SUMMARY" in body, "the unknown branch is gone"
    # ⚠️ THE DISCLAIMER MUST BE RENDERED UNCONDITIONALLY, not merely be present LATER IN THE SOURCE
    # than the unknown branch — the red proof caught exactly that weaker form, which stayed green
    # against a `{known != null && <p>…</p>}` that hides the sentence on the one branch where a
    # reader has least to go on.
    m = re.search(
        r'(\S)\s*<p className="[^"]*">\{WEEKLY_DESIGNATION_NOT_MODELLED\}</p>', body
    )
    assert m, "the un-modelled disclaimer paragraph has moved or is gone from the component"
    # ⭐ THE PRECEDING NON-SPACE CHARACTER IS THE WHOLE ASSERTION, and it is stated as a REFUSAL of
    # the three JSX conditional operators rather than as a whitelist of sibling shapes. A guarded
    # disclaimer is preceded by `&` (`{known != null && …}`) or by `?`/`:` (a ternary); a direct
    # child is preceded by a sibling's `>` or by the `}` a stripped JSX comment leaves behind. The
    # red proof caught the weaker form — a regex for the `<p>` alone matches just as happily INSIDE
    # a conditional wrapper, so it stayed green against exactly the defect it names.
    assert m.group(1) not in "&?:", (
        f"the un-modelled disclaimer is rendered CONDITIONALLY (preceded by {m.group(1)!r}) — a "
        f"player showing 'unknown' would carry a status with no statement about whether we priced "
        f"it, and 'unknown' with no disclaimer reads more like a model input than a designation "
        f"does"
    )


def test_an_unknown_designation_label_renders_verbatim_rather_than_as_unknown():
    """⭐ NF-C0 DEPLOY SKEW, on the response side. `frontend/` auto-deploys on merge while the board
    artifact only gains a new designation when the operator re-runs the exporter — and the reverse
    skew is just as real. A NEWER exporter serving a label this client has not learned is not an
    unknown: the server told us the word. Falling back to "unknown" there would report our own
    staleness as the feed's."""
    body = _component("WeeklyDesignation")
    assert re.search(r"WEEKLY_DESIGNATION_CODE\[\s*known\s*\]\s*\?\?\s*known", body), (
        "an unrecognised designation LABEL no longer falls back to rendering the served word — a "
        "newer exporter's designation would show as 'unknown' on a client that was simply behind"
    )
