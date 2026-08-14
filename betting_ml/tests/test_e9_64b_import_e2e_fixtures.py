"""E9.64b — the E2E import fixtures are the SHIPPING adapters' own output, and stay that way.

`frontend/e2e/specs/fantasy-import-{espn,yahoo}.spec.ts` drive the two real import paths against
these files. A captured or generated fixture is a SNAPSHOT and goes stale SILENTLY — the suite keeps
passing against a payload shape the server no longer produces, which is the most convincing form of
"covered" there is. This file is what turns that into a red build, and it is the same discipline
`test_e9_59_public_pricing.py` applies to the pricing capture and
`test_nf_tr1_claim_copy.py::test_the_e2e_fixture_claim_is_the_shipping_builders_own_output` applies
to the track-record claim.

Three things are pinned, in descending order of how badly they bite:

1. **EVERY COMMITTED FIXTURE EQUALS WHAT THE ADAPTER PRODUCES TODAY.** If `espn.py` or `yahoo.py`
   grows, renames or drops a response field, this fails and the fixture is regenerated — rather than
   the browser suite continuing to render a shape no caller receives.

2. ⭐ **THE TWO ESPN LEAGUES STAY INDEPENDENTLY SOURCED.** NF-C0e's whole lesson is that a fixture
   derived from the FIRST payload cannot disconfirm a wrong key-map: the outage (ESPN yardage mapped
   onto Sleeper's `pass_yd` instead of the canonical `pass_yds`, so every ESPN league scored zero
   yardage from the day import shipped) survived 56 tests over one live-verified league and was
   found by a second real account. So the story's "≥2 independently-sourced real payloads" is only
   worth anything while the two remain genuinely different — if they ever converge, the second has
   stopped buying coverage and this says so.

3. **THE E2E'S PREMISE IS NON-VACUOUS.** The browser spec asserts that the canonical yardage terms
   render in the coverage panel's APPLIED column — the DOM-observable form of the NF-C0e outage. That
   assertion means nothing if the fixture carries no yardage term at all, so the presence and the
   canonical spelling are pinned HERE, where they are checked against the adapter rather than
   against the fixture's own bytes.

⚠️ SCOPE. This does NOT re-check that an adapter's targets are real canonical keys — that guard is
mechanical, covers every adapter at once, and already lives in `test_nf_c0e_captured_terms.py`.
Duplicating it here would be a second spelling of the same rule.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO / "frontend/e2e/fixtures/api"
BUILDER = REPO / "frontend/e2e/fixtures/build-import-previews.py"


def _builder():
    """Load the generator by PATH — its filename is not an importable module name, and renaming it
    to one would break the `npm`-adjacent naming every other fixture builder in that directory
    follows."""
    sys.path.insert(0, str(REPO / "betting_ml" / "tests"))
    spec = importlib.util.spec_from_file_location("e9_64b_build_import_previews", BUILDER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = pytest.importorskip("app.backend.services.platform_import") and _builder()

ESPN_FIXTURES = (
    "fantasy-import-espn-preview-998005-2026.json",
    "fantasy-import-espn-preview-642070-2026.json",
    "fantasy-import-espn-preview-642070-2025.json",
)

#: The canonical keys the ENGINE reads, spelled here as the CONTRACT rather than read back out of
#: the adapter. ⭐ This is the NF-C0e lesson stated as code: a test that reads a value back under the
#: key the code wrote can never catch a wrong key, because it is a restatement of the code. These
#: four are the exact ones the outage got wrong (`pass_yd`/`rush_yd`/`rec_yd`/`fum_lost`).
CANONICAL_YARDAGE = ("pass_yds", "rush_yds", "rec_yds", "fumbles_lost")


@pytest.mark.parametrize("name", [*ESPN_FIXTURES, "fantasy-import-yahoo-preview.json",
                                  "fantasy-import-yahoo-leagues.json"])
def test_the_committed_fixture_is_the_shipping_adapters_own_output(name):
    """A fixture that has drifted from its adapter is a suite testing a shape nobody receives."""
    built = builder.all_fixtures()
    assert name in built, f"{name} is committed but the builder no longer produces it"
    on_disk = (FIXTURE_DIR / name).read_text()
    assert on_disk == builder.serialize(built[name]), (
        f"{name} no longer matches what the shipping adapter produces. Regenerate it:\n"
        "  uv run python frontend/e2e/fixtures/build-import-previews.py\n"
        "and re-read the E2E specs that assert on it — a field that moved may have moved a claim."
    )


def test_every_fixture_the_builder_produces_is_committed():
    """The other direction, so a new fixture cannot be added and left unpinned."""
    missing = [n for n in builder.all_fixtures() if not (FIXTURE_DIR / n).exists()]
    assert not missing, f"the builder produces fixtures that are not committed: {missing}"


class TestTheTwoEspnLeaguesStayIndependent:
    """⭐ The justification for carrying two real ESPN payloads, asserted rather than claimed."""

    def _preview(self, name):
        return json.loads((FIXTURE_DIR / name).read_text())

    def test_they_are_different_leagues_on_different_settings(self):
        one = self._preview("fantasy-import-espn-preview-998005-2026.json")
        two = self._preview("fantasy-import-espn-preview-642070-2026.json")
        assert one["source_league_id"] != two["source_league_id"]
        # Different SIZE and different FORMAT, which is what makes the browser spec's per-payload
        # assertions discriminating: a component that hardcoded either would pass on one and fail on
        # the other. (Measured: 12-team full-PPR vs 10-team half-PPR.)
        assert one["config"]["n_teams"] != two["config"]["n_teams"]
        assert one["config"]["ppr"] != two["config"]["ppr"]

    def test_each_league_scores_rules_the_other_does_not_have_at_all(self):
        """If these ever converge, the second fixture has stopped buying coverage and a genuinely
        different third league should replace it — the same clause the adapter-level suite carries
        for the raw captures, restated on the payload the BROWSER actually renders."""
        one = set(self._preview("fantasy-import-espn-preview-998005-2026.json")["config"]["scoring"]["per_stat"])
        two = set(self._preview("fantasy-import-espn-preview-642070-2026.json")["config"]["scoring"]["per_stat"])
        assert one - two, "league 998005 no longer contributes any unique scoring rule"
        assert two - one, "league 642070 no longer contributes any unique scoring rule"

    def test_exactly_one_of_them_carries_a_warning_and_one_carries_none(self):
        """Both halves of the disclosure contract need a payload to be reachable at all.

        `import-warnings-suppressed` proves the warning list is rendered; nothing proved the box is
        ABSENT on a league we read cleanly — a component that always rendered the header would pass
        the first and be wrong for most users. These two payloads are what make both testable, so if
        a regeneration ever leaves them on the same side of that line, the negative case has quietly
        become unreachable.
        """
        warned = self._preview("fantasy-import-espn-preview-998005-2026.json")["warnings"]
        clean = self._preview("fantasy-import-espn-preview-642070-2026.json")["warnings"]
        assert warned, "no ESPN fixture carries a warning — the disclosure case is unreachable"
        assert not clean, "no ESPN fixture is warning-free — the 'no false alarm' case is unreachable"


class TestTheBrowserAssertionsPremise:
    """The E2E's premise, pinned where it can be checked against the CONTRACT."""

    @pytest.mark.parametrize("name", ESPN_FIXTURES)
    def test_the_espn_previews_carry_the_canonical_yardage_keys(self, name):
        """⭐ THE NF-C0e OUTAGE, one level up from the browser.

        The spec asserts these render under APPLIED. That is only meaningful while the payload
        actually contains them under the canonical spelling — under the outage's spelling
        (`pass_yd`) the resolver reports CAPTURED, which is the amber "saved but NOT applied" card,
        and is exactly what the browser then sees.
        """
        per_stat = json.loads((FIXTURE_DIR / name).read_text())["config"]["scoring"]["per_stat"]
        missing = [k for k in CANONICAL_YARDAGE if k not in per_stat]
        assert not missing, (
            f"{name} does not score {missing} under the canonical key. If the adapter's target "
            "changed, that is the NF-C0e outage recurring — not a fixture to regenerate."
        )
        # Non-zero, because a term worth 0.0 is a non-statement: it would render "applied" while
        # scoring nothing, and the browser could not tell that from a working import.
        assert all(per_stat[k] != 0 for k in ("pass_yds", "rush_yds", "rec_yds"))

    def test_the_yahoo_preview_marks_exactly_one_team_as_the_callers_own(self):
        """Yahoo is the ONE platform that tells us which team is the user's (`is_current_login`),
        and `applyPreview` pre-selects it. The browser spec asserts that pre-selection; without a
        flagged team in the payload it would be asserting on a state the fixture cannot produce."""
        teams = json.loads((FIXTURE_DIR / "fantasy-import-yahoo-preview.json").read_text())["teams"]
        owned = [t for t in teams if t["is_owner"]]
        assert len(owned) == 1, f"expected exactly one owner-flagged Yahoo team, got {len(owned)}"
        # And at least one team that is NOT the caller's, or "only mine is marked" is untestable.
        assert len(teams) > 1

    def test_the_espn_previews_flag_no_owner_which_is_why_the_user_must_pick(self):
        """The mirror of the Yahoo case, and the reason the review screen has a team picker at all.
        ESPN's response does not identify the caller, so a fixture that flagged one would make the
        'this platform cannot tell us, so pick yours' branch unreachable."""
        for name in ESPN_FIXTURES:
            teams = json.loads((FIXTURE_DIR / name).read_text())["teams"]
            assert not [t for t in teams if t["is_owner"]], f"{name} flags an owner; ESPN cannot"
