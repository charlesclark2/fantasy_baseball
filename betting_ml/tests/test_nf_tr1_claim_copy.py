"""NF-TR1 — the COPY-GOVERNANCE suite for the fantasy track-record claim.

This is the story's acceptance criteria as executable clauses. NF-TR1 rewrote a claim that a casual
reader could not parse into a plain-English lead — and the whole hazard of doing that is that
plainer prose sounds punchier once the hedges come off. Every hedge therefore gets its own clause,
and every clause is written so that DELETING THE ONE THING IT NAMES turns it red.

⭐ THE AND-COMPOSED-GUARD RULE IS LOAD-BEARING HERE (NF-D17 §7, and it shipped broken in that
story's first cut). Several of these rules are conjunctions — "the lead says the gap is small AND
names a level position AND carries the luck hedge". A fixture that trips two clauses at once tests
NEITHER, because the first refusal hides the second. So each hedge has its OWN fixture in which
every OTHER hedge is satisfied, leaving the named one as the only thing that can flip the result.

RED-PROVEN. Fourteen deliberate defects, each required to turn its NAMED clause red:
`uv run python betting_ml/tests/nf_tr1_red_proof.py` (14/14 RED as of this commit). ⭐ That harness
already earned its keep here — one clause shipped VACUOUS in the first cut and passed with the
source it names deleted outright, because the committed artifact's incidental row ORDER made the
broken code return the right answer anyway. See `test_the_headline_adp_claim_is_not_swapped_for_
the_flattering_source` for the finding and the fix.

Pure/offline (fast gate): reads committed artifacts and source files, no DuckDB/S3/network.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from betting_ml.governance import gates
from quant_sports_intel_models.football.nfl.fantasy import export_track_record_json as ex

_REPO = Path(__file__).resolve().parents[2]
_REPORTS = _REPO / "quant_sports_intel_models/football/nfl/fantasy/ablation_results"
_SCORECARD_JSON = _REPORTS / "nf_d3_benchmark_scorecard_nf1_5.json"
_UNCERTAINTY_JSON = _REPORTS / "nf_d17_track_record_population.json"
_CLAIM_COPY_TS = _REPO / "frontend/lib/fantasy-claim-copy.ts"
_BROWSER_DENYLIST_TS = _REPO / "frontend/e2e/support/claim-denylist.ts"
_TRACK_RECORD_TSX = _REPO / "frontend/components/fantasy/track-record-page.tsx"
_E2E_MANIFEST = _REPO / "frontend/e2e/fixtures/api/fantasy-nfl-track-record-manifest.json"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Fixtures — the SHIPPED claim, plus synthetic shapes for the two-sided clauses
# ══════════════════════════════════════════════════════════════════════════════════════════════
@pytest.fixture(scope="module")
def shipped_claim() -> dict:
    """The claim the export actually produces from the committed artifacts.

    ⭐ NOT A SYNTHETIC. Screening a made-up sentence proves the screen works, not that the SHIPPED
    copy passes it — and the shipped copy is the thing a user reads."""
    return ex.build_claim(
        json.loads(_SCORECARD_JSON.read_text()), json.loads(_UNCERTAINTY_JSON.read_text())
    )


def _scorecard(*, delta=0.022, by_pos=None, us=0.517, them=0.494):
    """A scorecard whose ADP aggregate has exactly the shape a clause needs.

    `by_pos` defaults to the live split (RB at exactly 0.0 = the wash). A clause that wants to prove
    the level-position sentence is DERIVED passes a different split."""
    return {
        "aggregate": {"adp": {
            "n_seasons": 6, "us_rho_pooled": us, "system_rho_pooled": them,
            "delta_rho_pooled": delta,
            "delta_rho_by_pos": {"QB": 0.031, "RB": -0.0, "WR": 0.037, "TE": 0.021}
            if by_pos is None else by_pos,
        }},
        "per_season": [{"season": y, "systems": {"adp": {}}} for y in range(2019, 2025)],
        "seasons_scored": list(range(2019, 2025)),
    }


def _uncertainty(*, delta=0.022, lo=-0.006, hi=0.051, n_seasons=6, evaluated=True):
    return {"results": [{
        "population": "P0_shipped", "source": "adp", "n_seasons": n_seasons,
        "n_mean": 162.0, "n_min": 140, "n_max": 172, "delta_rho_mean": delta,
        "bootstrap": {"evaluated": evaluated, "draws": 1000, "level": 0.9,
                      "lo": lo, "hi": hi, "median": delta,
                      "excludes_zero": not (lo <= 0.0 <= hi)},
    }]}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# AC 1 — the denylist stays active and BOTH layers pass it
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_plain_lead_passes_the_denylist(shipped_claim):
    """The lead is the layer the readability rewrite touched, so it is the layer at risk."""
    lowered = shipped_claim["lead"].lower()
    hits = [t for t in ex._CLAIM_DENYLIST if t in lowered]
    assert not hits, f"the consumer lead makes a forbidden claim {hits}: {shipped_claim['lead']!r}"


def test_the_precise_layer_passes_the_denylist(shipped_claim):
    """Screened SEPARATELY from the lead so a failure names which layer drifted — a single
    combined assertion would report "the copy" and leave the author hunting."""
    lowered = shipped_claim["precise"].lower()
    hits = [t for t in ex._CLAIM_DENYLIST if t in lowered]
    assert not hits, f"the precise layer makes a forbidden claim {hits}: {shipped_claim['precise']!r}"


def test_every_other_published_string_passes_the_denylist(shipped_claim):
    """The disclosures, the method note and the architecture note ship on the same page and are
    read by the same visitor; screening only the two headline layers would leave six paragraphs
    of unscreened prose beneath them."""
    others = {
        "method": shipped_claim["method"],
        "architecture": shipped_claim["architecture"],
        "benchmark": shipped_claim["benchmark"],
        **{f"disclosure[{i}]": d for i, d in enumerate(shipped_claim["disclosures"])},
    }
    for label, text in others.items():
        hits = [t for t in ex._CLAIM_DENYLIST if t in text.lower()]
        assert not hits, f"{label} makes a forbidden claim {hits}: {text!r}"


def test_the_governance_gate_passes_the_shipped_copy(shipped_claim):
    """AC 1 names the gate in `betting_ml/governance/gates.py`, so run the ACTUAL gate over the
    ACTUAL copy — not a re-implementation of its rule with the same word list."""
    texts = [shipped_claim["lead"], shipped_claim["precise"], shipped_claim["method"],
             shipped_claim["architecture"], *shipped_claim["disclosures"]]
    result = gates.track_record_copy_compatible(texts)
    assert result.status == gates.PASS, result.detail


def test_the_governance_gate_can_actually_refuse_this_copy():
    """⚠️ A GATE THAT CANNOT FAIL IS NOT A GATE. The clause above is only evidence if the same call
    goes red on copy that should be refused — otherwise it would pass just as happily against a
    gate whose denylist had been emptied."""
    bad = gates.track_record_copy_compatible(["Our board beats the market every position, guaranteed."])
    assert bad.status == gates.FAIL
    blind = gates.track_record_copy_compatible(None)
    assert blind.status == gates.UNEVALUABLE, "no copy supplied must be UNEVALUABLE, never a pass"


def test_the_export_denylist_is_a_superset_of_the_governance_gate():
    """Two denylists screening the same product must not disagree about what is forbidden.

    They were written apart — the export's for the track-record page, the gate's for promotion
    copy — and each carried terms the other lacked, so one sentence could pass one surface and fail
    the other. ⛔ A term may be ADDED to the gate's list; it may never be dropped from the export's."""
    missing = [t for t in gates._DEFAULT_CLAIM_DENYLIST if t not in ex._CLAIM_DENYLIST]
    assert not missing, (
        f"the governance gate forbids {missing} but the track-record export does not — the export "
        f"would publish copy the promotion gate would refuse"
    )


def test_the_browser_denylist_mirror_matches_the_export():
    """The Playwright suite scans the RENDERED page — which includes every static component string
    the export never sees — against a TypeScript copy of this denylist.

    ⚠️ A MIRROR THAT CAN DRIFT IS WORSE THAN NO MIRROR: it goes on passing while the real list
    grows a term it never learned, and it reads as coverage the whole time. Set EQUALITY, not
    containment — a browser list with EXTRA terms is also a defect, because a phrase the page
    refuses and the export happily publishes is a rule nobody can satisfy."""
    src = _strip_ts_comments(_BROWSER_DENYLIST_TS.read_text())
    # ⚠️ Anchor on `= [`, not on the identifier: the declaration is
    # `CLAIM_DENYLIST: readonly string[] = [`, so splitting on the name and then on the first `]`
    # stops inside the TYPE ANNOTATION and extracts nothing. The vacuity assertion below is what
    # caught that while writing this — which is the whole reason it is here and not implied.
    body = src.split("CLAIM_DENYLIST", 1)[1].split("= [", 1)[1].split("]", 1)[0]
    mirrored = set(re.findall(r'"((?:[^"\\]|\\.)*)"', body))
    assert mirrored, "no terms extracted from the browser denylist — the scan would be vacuous"
    assert mirrored == set(ex._CLAIM_DENYLIST), (
        f"the browser mirror has drifted from the export denylist. "
        f"only in Python: {sorted(set(ex._CLAIM_DENYLIST) - mirrored)}; "
        f"only in TypeScript: {sorted(mirrored - set(ex._CLAIM_DENYLIST))}"
    )


def test_the_plain_english_overclaims_are_specifically_forbidden():
    """The register changed, so the denylist had to. An analyst sentence would never have said
    "win your league" — a plain one might, and it is the single most tempting thing to write on a
    fantasy landing page."""
    for phrase in ("win your league", "beats adp", "guaranteed", "sure thing"):
        assert phrase in ex._CLAIM_DENYLIST, f"{phrase!r} is not screened"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# AC 2 — calibration appears BEFORE the benchmark comparison
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_calibration_leads_the_consumer_lead(shipped_claim):
    """Within the lead sentence itself: what the product gives you, then the comparison.

    Asserted as a POSITION comparison rather than "the lead mentions projections", because the
    failure this guards is an ORDERING one — a lead that opens on the ADP comparison and mentions
    calibration afterwards would satisfy any mere-presence check."""
    lead = shipped_claim["lead"].lower()
    calibration_at = min(
        (lead.index(m) for m in ("range around", "projects a full season") if m in lead),
        default=-1,
    )
    benchmark_at = lead.index("track record")
    assert calibration_at >= 0, f"the lead never states what the product gives you: {lead!r}"
    assert calibration_at < benchmark_at, (
        "the benchmark comparison precedes the calibration hook in the consumer lead — that makes a "
        "gap whose interval includes zero the product's headline promise"
    )


def _strip_ts_comments(src: str) -> str:
    """⚠️ COMMENTS MUST GO BEFORE ANY SOURCE-INSPECTION MATCH (INC-38). This file's own comments
    name both components repeatedly and in the wrong order in places; a raw substring search would
    be satisfied by PROSE and would stay green with the components genuinely swapped."""
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return "\n".join(line for line in src.split("\n") if not line.lstrip().startswith("//"))


def test_the_page_renders_calibration_before_the_benchmark_claim():
    """AC 2 at the RENDER level, which is where a user meets it.

    A build-time ordering rule in the exporter says nothing about where the page puts the blocks —
    the copy could lead with calibration while the component rendered the claim above it."""
    src = _strip_ts_comments(_TRACK_RECORD_TSX.read_text())
    calibration_at = src.index("<CalibrationLead />")
    claim_at = src.index("<ClaimLead ")
    assert calibration_at < claim_at, (
        "<ClaimLead> renders above <CalibrationLead> — the page leads with the benchmark comparison"
    )


def test_the_page_never_promotes_a_legacy_headline_into_the_lead():
    """The deploy-skew direction, and it is the one that can ship silently.

    `frontend/` auto-deploys on merge; the artifact only gains its `claim` block when the operator
    re-publishes. A `claim?.lead ?? headline` fallback looks defensive and would put the OLD
    un-hedged sentence ("we finished ahead", no interval) straight back into the lead position for
    the whole window."""
    src = _strip_ts_comments(_TRACK_RECORD_TSX.read_text())
    for bad in ("claim?.lead ?? manifest.headline", "claim?.lead ?? headline"):
        assert bad not in src, (
            f"found {bad!r}: a pre-NF-TR1 artifact's `headline` is the un-hedged analyst sentence "
            f"and must render as fine print (LegacyClaim), never as the lead"
        )
    assert "<LegacyClaim " in src, "the no-claim branch must still render the legacy string somewhere"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The hedges — one fixture PER clause, every other hedge satisfied
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_lead_says_the_gap_is_small(shipped_claim):
    assert "the gap is small" in shipped_claim["lead"].lower()


def test_the_lead_says_it_varies_by_season_and_position(shipped_claim):
    lead = shipped_claim["lead"].lower()
    assert "year to year" in lead and "position to position" in lead


def test_the_lead_carries_the_luck_hedge_while_zero_is_in_the_interval():
    """The measured interval includes zero, so the lead must say so in words a casual reader parses.

    ⭐ ISOLATING FIXTURE: the gap is positive and a level position exists, so every OTHER hedge is
    satisfiable — the interval is the only thing that can change this assertion's answer."""
    claim = ex.build_claim(_scorecard(), _uncertainty(lo=-0.006, hi=0.051))
    assert claim["ciIncludesZero"] is True
    assert "could just be luck" in claim["lead"].lower()


def test_the_luck_hedge_is_dropped_when_the_interval_excludes_zero():
    """The other side, and the reason the clause above is evidence rather than a coincidence.

    A hardcoded "could just be luck" would satisfy the previous test forever, including on a day
    the measurement no longer supported it. A hedge that survives its own evidence is decoration."""
    claim = ex.build_claim(_scorecard(delta=0.12), _uncertainty(delta=0.12, lo=0.08, hi=0.16))
    assert claim["ciIncludesZero"] is False
    assert "could just be luck" not in claim["lead"].lower()
    assert "not a promise about next season" in claim["lead"].lower(), (
        "dropping the luck hedge must not leave the lead un-hedged — the no-guarantee clause stays"
    )


def test_the_level_position_is_read_from_the_data_not_asserted():
    """NF-TR1 requires "RB is a wash". Writing that as a literal would make it a CLAIM about the
    data that survives the data changing — so the sentence must follow `delta_rho_by_pos`.

    ⭐ ISOLATING FIXTURE: identical in every respect except which position sits at zero."""
    rb_level = ex.build_claim(_scorecard(), _uncertainty())
    assert "running back" in rb_level["lead"].lower()

    te_level = ex.build_claim(
        _scorecard(by_pos={"QB": 0.031, "RB": 0.030, "WR": 0.037, "TE": 0.0}), _uncertainty()
    )
    assert "tight end" in te_level["lead"].lower()
    assert "running back" not in te_level["lead"].lower(), (
        "the level position is hardcoded — the lead still names running back on a split where "
        "running back is not level"
    )


def test_the_lead_never_claims_a_direction_the_measurement_does_not_support():
    """Sign-awareness, on the layer where it matters most: plain prose reads as a claim."""
    behind = ex.build_claim(_scorecard(delta=-0.04, us=0.470, them=0.510),
                            _uncertainty(delta=-0.04, lo=-0.08, hi=0.01))
    lead = behind["lead"].lower()
    assert "consensus order held up better than ours" in lead
    assert "closer to how those years actually finished than the draft-day consensus" not in lead


# ══════════════════════════════════════════════════════════════════════════════════════════════
# AC 3 — the precise layer names the benchmark, the metric, the player count and the seasons
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_precise_layer_names_the_benchmark_the_metric_the_count_and_the_seasons(shipped_claim):
    precise = shipped_claim["precise"].lower()
    assert "captured adp benchmark" in precise, "the benchmark is not named"
    assert "rank correlation" in precise, "the metric is not named"
    assert "2019" in precise and "2024" in precise, "the seasons are not stated"
    assert str(shipped_claim["playersPerSeason"]) in precise, "the player count is not stated"


def test_the_precise_layer_shows_the_interval(shipped_claim):
    """"Confidence interval is visible" is a required disclosure — and an interval that only lives
    in a JSON field nobody renders is not visible."""
    precise = shipped_claim["precise"]
    assert f"{shipped_claim['ciLevel']}%" in precise
    assert f"{shipped_claim['ciLow']:+.3f}" in precise and f"{shipped_claim['ciHigh']:+.3f}" in precise
    assert "includes zero" in precise.lower()


def test_the_approved_sentence_is_emitted_verbatim():
    """The operator approved this exact wording. It was RELOCATED below a plain lead, never
    reworded — so it must appear byte-for-byte, not paraphrased into the same meaning."""
    claim = ex.build_claim(_scorecard(), _uncertainty())
    assert (
        "Credence's served-style board modestly outperformed the captured ADP benchmark on pooled "
        "within-position rank correlation from 2019–2024. Results vary by position and season, and "
        "the confidence interval includes zero."
    ) in claim["precise"]


def test_the_approved_sentence_is_withdrawn_when_the_shape_changes():
    """An approved sentence is approved for a MEASUREMENT, not forever.

    "modestly outperformed … and the confidence interval includes zero" is a factual claim about
    both the sign and the interval. Emitting it unconditionally would publish a false statement the
    first time either moved — and it would look approved while doing it."""
    behind = ex.build_claim(_scorecard(delta=-0.04, us=0.470, them=0.510),
                            _uncertainty(delta=-0.04, lo=-0.08, hi=0.01))
    assert "modestly outperformed" not in behind["precise"]
    assert "did NOT lead the captured ADP benchmark" in behind["precise"]

    clean = ex.build_claim(_scorecard(delta=0.12), _uncertainty(delta=0.12, lo=0.08, hi=0.16))
    assert "the confidence interval includes zero" not in clean["precise"]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# AC 4 — a position-level table is available, and AC's six disclosures are all present
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_a_level_position_is_labelled_even_rather_than_ahead(shipped_claim):
    """The measured RB gap is -0.0. A table that rounded that to "ahead" — or omitted the verdict
    and left a reader to interpret "-0.000" — would bury the disclosure the story requires."""
    rb = next(r for r in shipped_claim["byPosition"] if r["position"] == "RB")
    assert rb["verdict"] == "even", rb
    assert {r["position"] for r in shipped_claim["byPosition"]} == {"QB", "RB", "WR", "TE"}


def test_the_position_verdict_threshold_is_two_sided():
    """The level band must catch a gap that is small in EITHER direction — a one-sided test would
    label a tiny negative gap "behind" and read as a stronger disclosure than the data supports."""
    assert ex._verdict(0.0) == "even"
    assert ex._verdict(-0.004) == "even"
    assert ex._verdict(0.004) == "even"
    assert ex._verdict(0.031) == "ahead"
    assert ex._verdict(-0.031) == "behind"


def test_the_position_table_reaches_the_rendered_page():
    """AC 4 says the table is AVAILABLE — a `byPosition` array nothing renders is not."""
    src = _strip_ts_comments(_TRACK_RECORD_TSX.read_text())
    assert "<PositionTable rows={manifest.claim.byPosition} />" in src
    assert "<details" not in src.split("function PositionTable")[1].split("function ")[0], (
        "the position table is inside a collapsed <details> — the running-back wash is the "
        "disclosure that costs us something, so it renders unconditionally"
    )


def test_all_six_required_disclosures_are_present(shipped_claim):
    """NF-TR1's six, checked by their DISTINGUISHING content rather than by count — a count would
    pass against six copies of the same sentence."""
    joined = " ".join(shipped_claim["disclosures"]).lower()
    required = {
        "RB is a wash": "wash",
        "ECR/ESPN/Sleeper reported separately": "reported separately",
        "served ordering uses market consensus": "blends the market",
        "not a guarantee": "not a guarantee",
        "interval is visible": "range around the measured gap",
        "frozen-board method explained": "before that season kicked off",
    }
    missing = [name for name, marker in required.items() if marker not in joined]
    assert not missing, f"required disclosure(s) absent from the published copy: {missing}"


def test_the_context_benchmarks_are_reported_and_we_say_we_trail_them(shipped_claim):
    """We currently trail ECR, ESPN and Sleeper. Reporting only the comparison we lead would be
    selecting evidence — so both the numbers AND the plain-English admission must ship."""
    keys = {o["key"] for o in shipped_claim["otherBenchmarks"]}
    assert keys == {"ecr", "espn", "sleeper"}, keys
    assert all(o["verdict"] == "behind" for o in shipped_claim["otherBenchmarks"])
    joined = " ".join(shipped_claim["disclosures"]).lower()
    assert "we do not lead any of them" in joined


def test_the_headline_adp_claim_is_not_swapped_for_the_flattering_source():
    """⛔ NF-D17 §4: MFL reads +0.173 on its own deeper population, and quoting that without the
    depth confound is the exact substitution that memo exists to prevent. The public claim is the
    FFC captured-ADP reading, and no cell may be promoted into it by being larger.

    ⭐ THE ROW ORDER IS THE WHOLE TEST, AND THE FIRST VERSION OF IT WAS VACUOUS. Asserted against
    the real artifact alone, this clause stayed GREEN with the population pin deleted outright —
    because `P0_shipped × adp` happens to be the FIRST row in that file, so "take whatever comes
    first" returns the right answer by luck. The 57-cell artifact NF-D17 produces has no guaranteed
    order and the flattering cell could lead it after any re-run. So the selection is exercised
    against a list where a WRONG row comes first and a RIGHT row is buried behind it — the only
    arrangement in which a real pin and no pin at all give different answers.
    (Sibling of the E9.59 finding: when a red-proof case goes green, suspect the ordering.)"""
    unc = json.loads(_UNCERTAINTY_JSON.read_text())
    row = ex.shipped_uncertainty(unc)
    assert row["population"] == "P0_shipped" and row["source"] == "adp"
    assert abs(row["delta_rho_mean"] - 0.022) < 1e-9, row["delta_rho_mean"]

    def cell(population, source, delta):
        return {"population": population, "source": source, "n_seasons": 6, "n_mean": 162.0,
                "n_min": 140, "n_max": 172, "delta_rho_mean": delta,
                "bootstrap": {"evaluated": True, "level": 0.9, "lo": delta - 0.03,
                              "hi": delta + 0.03}}

    adversarial = {"results": [
        cell("P0_shipped", "mfl_adp", 0.173),               # the flattering source, FIRST
        cell("P2_depth100_by_source", "adp", 0.058),        # the inadmissible one-sided depth cell
        cell("P0_shipped", "adp", 0.022),                   # the real claim, buried
    ]}
    picked = ex.shipped_uncertainty(adversarial)
    assert picked["source"] == "adp" and picked["population"] == "P0_shipped", picked
    assert abs(picked["delta_rho_mean"] - 0.022) < 1e-9, (
        f"a larger cell earlier in the file was selected ({picked['delta_rho_mean']:+.3f}) — the "
        f"public claim would silently become a different, better-looking measurement"
    )


# ══════════════════════════════════════════════════════════════════════════════════════════════
# AC 5 — the copy matches the served two-stack architecture
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_architecture_note_describes_both_stacks_and_the_market_ordering(shipped_claim):
    """A claim must not describe a mechanism the board does not have. The served board is a LEVEL
    model (market-blind) with an ORDERING model on top whose ranking blends market consensus — and
    the ordering changes WHICH player gets which point total, never the totals."""
    note = shipped_claim["architecture"].lower()
    assert "never looks at the draft market" in note, "the market-blind level model is not described"
    assert "order" in note and "blends the market" in note, "the market-aware ordering is not described"
    assert "never changes the totals" in note, (
        "the copy does not say the ordering is a re-ORDERING rather than a re-pricing — without "
        "that, it reads as a claim to price players better than the market"
    )


def test_the_frozen_board_method_is_explained(shipped_claim):
    method = shipped_claim["method"].lower()
    assert "before that season kicked off" in method
    assert "only from seasons that had already finished" in method
    assert "nothing is re-ranked after the fact" in method


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Refusals — an unevaluable disclosure is NOT a disclosure that passed (NF1.7 (a))
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_an_interval_from_a_different_reading_is_refused():
    """The scorecard and the NF-D17 artifact are regenerated by different scripts on different
    days. Pairing one's gap with the other's interval would look entirely normal and be wrong."""
    with pytest.raises(ValueError, match="different readings"):
        ex.build_claim(_scorecard(delta=0.022), _uncertainty(delta=0.173))


def test_an_interval_covering_a_different_span_is_refused():
    with pytest.raises(ValueError, match="different span"):
        ex.build_claim(_scorecard(), _uncertainty(n_seasons=7))


def test_an_uncomputed_bootstrap_is_refused_rather_than_silently_dropped():
    """The interval is a REQUIRED disclosure. An export that quietly published the claim without
    one would look successful and would be missing the single most important hedge."""
    with pytest.raises(ValueError, match="never computed"):
        ex.build_claim(_scorecard(), _uncertainty(evaluated=False))


def test_a_missing_shipped_population_is_refused_rather_than_substituted():
    with pytest.raises(ValueError, match="P0_shipped"):
        ex.build_claim(_scorecard(), {"results": [
            {"population": "P1_cross_source_matched", "source": "adp", "n_seasons": 6,
             "n_mean": 161.0, "n_min": 140, "n_max": 172, "delta_rho_mean": 0.022,
             "bootstrap": {"evaluated": True, "level": 0.9, "lo": -0.008, "hi": 0.048}},
        ]})


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The frontend copy module + the e2e fixture
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _ts_string_literals(src: str) -> list[str]:
    """Every double-quoted string literal in a TS source, comments stripped first.

    Crude on purpose: this is a screening pass over prose constants, not a parser. It is checked by
    `test_the_copy_module_scan_actually_finds_strings` — an extractor that silently returned nothing
    would make every screening clause below vacuously true (NF1.7 (a))."""
    return re.findall(r'"((?:[^"\\]|\\.)*)"', _strip_ts_comments(src))


def test_the_copy_module_scan_actually_finds_strings():
    literals = _ts_string_literals(_CLAIM_COPY_TS.read_text())
    assert len(literals) >= 10, (
        f"only {len(literals)} string literal(s) extracted from the canonical copy module — the "
        f"screening below would be passing on nothing"
    )
    assert any("80% range" in s for s in literals), "the calibration hook's copy was not extracted"


def test_the_frontend_canonical_copy_passes_the_denylist():
    """The exporter screens what it GENERATES; this screens what the frontend SHIPS statically.

    Without it, the calibration hook and the CTA labels — real, user-visible claim-adjacent copy —
    would be the only strings on the page no denylist had ever looked at."""
    literals = _ts_string_literals(_CLAIM_COPY_TS.read_text())
    for s in literals:
        hits = [t for t in ex._CLAIM_DENYLIST if t in s.lower()]
        assert not hits, f"canonical frontend copy makes a forbidden claim {hits}: {s!r}"
    result = gates.track_record_copy_compatible(literals)
    assert result.status == gates.PASS, result.detail


def test_the_canonical_copy_module_carries_no_measured_figure():
    """⛔ E9.56b/NF-D3: a number typed into a component cannot be reconciled against the measurement
    it came from, and drifts silently the first time the model is re-scored. Every figure belongs to
    the served artifact's `claim` block."""
    literals = _ts_string_literals(_CLAIM_COPY_TS.read_text())
    for s in literals:
        # 0.517 / +0.022 / -0.006 — a decimal with 2+ places is a measurement, not prose.
        assert not re.search(r"\d\.\d{2,}", s), (
            f"the canonical copy module hardcodes what looks like a measured figure: {s!r}"
        )


def test_the_e2e_fixture_claim_is_the_shipping_builders_own_output():
    """The e2e fixture's `claim` block is GENERATED (the block does not exist in prod until the
    post-merge `--publish`, so there is nothing to capture — E9.59's pricing fixture had the same
    one-day shape). This is what keeps "generated" from decaying into "hand-written": it must equal
    what the shipping builder produces from the same committed artifacts, byte for byte."""
    fixture = json.loads(_E2E_MANIFEST.read_text())
    assert "claim" in fixture, (
        "the track-record manifest fixture has no `claim` block — regenerate it:\n"
        "  uv run python frontend/e2e/fixtures/build-track-record-claim.py"
    )
    expected = ex.build_claim(
        json.loads(_SCORECARD_JSON.read_text()), json.loads(_UNCERTAINTY_JSON.read_text())
    )
    assert fixture["claim"] == expected, (
        "the e2e fixture's claim block has drifted from the builder — the Playwright specs are "
        "asserting against copy that is no longer what the export produces. Regenerate it:\n"
        "  uv run python frontend/e2e/fixtures/build-track-record-claim.py"
    )
    assert fixture["headline"] == expected["lead"], (
        "the fixture's `headline` is not the consumer lead — every surface that quotes `headline` "
        "(the upgrade banner, the player page) would be exercised against the wrong layer"
    )
