"""NF-INJ2c — the reproduction pin must be evaluable at the PUBLISHED artifact's own resolution.

🧨 THE DEFECT (2026-09-03, box re-measure). The pin's registered bar is `worst <= 0.05` — half the
published board's 0.1 quantum, so 0.05 is the largest difference a CORRECTLY reproducing rebuild can
exhibit, and the operator (`<=`) already intends it to PASS. But 0.05 is a DECIMAL bar evaluated in
BINARY: `proj_games` is quantised on a 0.05 grid, so a `.x5` value against its 1-decimal publication
(16.55 vs 16.6) differs by `0.05000000000000071` — ONE ULP over the bar. The box run reproduced the
served board with ZERO rows differing by any amount the artifact can express, and the pin still
reported VOID.

A gate that cannot pass on correct work is the unachievable-gate family the pin's own
`tolerance_note` already names one step coarser (E9.61: "a 1e-9 bar against a 1dp artifact is
UNACHIEVABLE, not strict"), and this program refuses those as firmly as it refuses loosened ones.

⛔ WHAT THIS IS NOT. The registered bar, its population and its binding condition are UNCHANGED —
this suite pins that too. The epsilon is a REPRESENTATION allowance, eight orders of magnitude below
the artifact's own quantum; a row wrong by any amount a 1-decimal artifact can express still
REFUSES, and both directions are asserted below.

PM ruling, NF-INJ2c decision request #5.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from quant_sports_intel_models.football.nfl.fantasy import run_nf_inj2b_rate_ordering as RB

_SRC = Path(RB.__file__)

#: the published artifact's resolution: `projections.json` serves `fpPpr`/`g` to ONE decimal.
_ARTIFACT_QUANTUM = 0.1

#: the six rows the box re-measure landed on, verbatim: `proj_games` on the 0.05 grid against the
#: 1-decimal publication. Five distinct (published, rebuilt) pairs, all TE.
_MEASURED_BOUNDARY_TIES: tuple[tuple[float, float], ...] = (
    (16.6, 16.55),   # Trey McBride
    (16.6, 16.55),   # Tyler Warren
    (16.2, 16.25),   # Harold Fannin Jr.
    (16.6, 16.55),   # Travis Kelce
    (15.1, 15.05),   # Brock Bowers
)

#: the box run's measured extremes. `proj_fp_ppr` never reached the bar at all; `proj_games`
#: excluding the structural ties came in comfortably under it.
_MEASURED_POINTS_WORST = 0.04999904302528435
_MEASURED_GAMES_WORST_EXCLUDING_TIES = 0.04995620116650201
_MEASURED_WORST_OVERALL = 0.05000000000000071


def _strip_comments(src: str) -> str:
    """INC-38: a source-inspection guard that prose can satisfy is not a guard."""
    return "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("#"))


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Direction 1 — a CORRECT reproduction must PASS
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestACorrectReproductionPasses:

    def test_the_exact_measured_worst_passes(self):
        """The number the box run produced. This is the case the whole ruling is about."""
        assert RB.reproduces_at_published_resolution(_MEASURED_WORST_OVERALL)

    @pytest.mark.parametrize("published,rebuilt", _MEASURED_BOUNDARY_TIES)
    def test_each_measured_boundary_tie_passes(self, published, rebuilt):
        assert RB.reproduces_at_published_resolution(abs(published - rebuilt))

    def test_the_same_structural_tie_falls_on_BOTH_sides_of_the_bar_in_binary(self):
        """⭐ THE ARGUMENT IN ONE ASSERTION, and the reason this is a comparison defect.

        Every pair here is the identical situation — a `.x5` value against its 1-decimal
        publication — yet raw binary `<=` REFUSES some and ACCEPTS others: 16.6-16.55 is
        0.05000000000000071 (over), 15.1-15.05 is 0.049999999999998934 (under). A gate whose verdict
        turns on which side of a ULP the representation happens to land is not deciding on the data.

        This also keeps the parametrized case above non-vacuous: at least one pair must genuinely
        exceed the bar, or that test asserts nothing about the defect (NF1.7(a))."""
        diffs = [abs(p - r) for p, r in _MEASURED_BOUNDARY_TIES]
        over = [d for d in diffs if d > RB.PUBLISHED_ROUNDING_TOL]
        under = [d for d in diffs if d <= RB.PUBLISHED_ROUNDING_TOL]
        assert over, "no measured tie exceeds the bar in binary — the fixture no longer bites"
        assert under, "no measured tie falls under the bar — the arbitrariness claim is unproven"
        assert all(RB.reproduces_at_published_resolution(d) for d in diffs)

    def test_the_boundary_tie_is_structural_across_the_games_grid(self):
        """⭐ NOT five lucky rows: `proj_games` sits on a 0.05 grid, so EVERY `.x5` value ties.

        This is what makes the pre-fix pin structurally incapable of passing, on every future
        board — not a near-miss on one slate."""
        ties_over_the_bar = 0
        for half_units in range(1, 400):                     # 0.05 .. 19.95 on the 0.05 grid
            rebuilt = round(half_units * 0.05, 10)
            if abs(rebuilt * 10 - round(rebuilt * 10)) < 1e-9:
                continue                                     # already a 1dp value — no tie
            published = round(rebuilt, 1)
            diff = abs(published - rebuilt)
            if diff > RB.PUBLISHED_ROUNDING_TOL:
                ties_over_the_bar += 1
            assert RB.reproduces_at_published_resolution(diff), (
                f"{rebuilt} against its publication {published} differs by {diff!r} and is refused")
        assert ties_over_the_bar > 0, (
            "no `.x5` value on the grid exceeded the bar in binary — this test would then be "
            "asserting nothing about the defect")

    def test_the_measured_non_tie_extremes_pass(self):
        assert RB.reproduces_at_published_resolution(_MEASURED_POINTS_WORST)
        assert RB.reproduces_at_published_resolution(_MEASURED_GAMES_WORST_EXCLUDING_TIES)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Direction 2 — a GENUINELY WRONG row must still REFUSE
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestAWrongRowStillRefuses:

    def test_one_full_quantum_refuses(self):
        """The smallest error the 1-decimal artifact can EXPRESS: off by one decimal place."""
        assert not RB.reproduces_at_published_resolution(_ARTIFACT_QUANTUM)

    def test_a_row_that_rounds_to_a_different_published_decimal_refuses(self):
        # 16.66 publishes as 16.7, so a rebuild of 16.6 is wrong by 0.06 — over the bar, and not
        # a representation artifact.
        assert not RB.reproduces_at_published_resolution(0.06)

    @pytest.mark.parametrize("excess", [1e-6, 1e-5, 1e-4, 1e-3, 0.01])
    def test_the_epsilon_is_not_slack_at_any_material_scale(self, excess):
        """⛔ 1e-9 admits ONE ULP, not a margin: anything materially past the bar still refuses."""
        assert not RB.reproduces_at_published_resolution(RB.PUBLISHED_ROUNDING_TOL + excess)

    def test_an_unevaluable_worst_refuses(self):
        """NF1.7(a): an empty join compared NOTHING — that is never a pass.

        `-inf` is the case that makes the explicit finiteness branch load-bearing: `nan`/`inf` would
        refuse under a bare `<=` anyway, but `-inf <= tol` is TRUE, so a nonsense input would sail
        through as a reproduction."""
        assert not RB.reproduces_at_published_resolution(float("nan"))
        assert not RB.reproduces_at_published_resolution(float("inf"))
        assert not RB.reproduces_at_published_resolution(float("-inf"))


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The bar itself is UNCHANGED — this is a comparison fix, not a threshold move (E2.1-r)
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestTheRegisteredBarIsUnchanged:

    def test_the_tolerance_is_still_half_the_published_quantum(self):
        assert RB.PUBLISHED_ROUNDING_TOL == pytest.approx(_ARTIFACT_QUANTUM / 2, abs=0)

    def test_the_epsilon_is_orders_of_magnitude_below_the_quantum(self):
        """A representation allowance, not a bar. Eight orders below the artifact's own resolution."""
        assert 0 < RB.PUBLISHED_TOL_REPR_EPS <= _ARTIFACT_QUANTUM / 1e6
        assert RB.PUBLISHED_TOL_REPR_EPS == 1e-9

    def test_the_epsilon_brackets_the_representation_error_without_reaching_the_data(self):
        """Two-sided: comfortably ABOVE the observed float error, far BELOW anything material.

        The measured excess is ~7.1e-16 (about one ULP at the bar). 1e-9 clears that by six orders
        of magnitude — so accumulated float error across a longer arithmetic chain is still covered
        — while sitting eight orders BELOW the artifact's own 0.1 quantum, so no difference the
        published board can express fits inside it."""
        measured_excess = _MEASURED_WORST_OVERALL - RB.PUBLISHED_ROUNDING_TOL
        assert 0 < measured_excess < 1e-12, f"unexpected excess {measured_excess!r}"
        assert RB.PUBLISHED_TOL_REPR_EPS > measured_excess * 1e3, (
            "the epsilon barely covers the error it exists for — a slightly longer arithmetic "
            "chain would re-open the defect")
        assert RB.PUBLISHED_TOL_REPR_EPS < _ARTIFACT_QUANTUM / 1e6, (
            "the epsilon is approaching the scale of a difference the artifact can express — that "
            "is slack, not representation")

    def test_the_source_documents_the_epsilon_as_representation_not_slack(self):
        src = _strip_comments(_SRC.read_text())
        fn = src.split("def reproduces_at_published_resolution", 1)
        assert len(fn) == 2, "the helper is gone — the comparison is no longer a named, testable unit"
        body = fn[1].split("\ndef ", 1)[0]
        assert "NOT slack" in body or "never slack" in body, (
            "the comparison site must say what the epsilon means; a reader who mistakes it for "
            "slack will widen it")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Wired AND invoked — the pin must actually call it (NF-C0e)
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestThePinUsesIt:

    def test_the_pin_calls_the_helper_rather_than_comparing_raw(self):
        src = _strip_comments(_SRC.read_text())
        assert "reproduces_at_published_resolution(worst)" in src, (
            "the pin no longer routes through the helper — a raw `<=` here is the defect")
        assert not re.search(r'"reproduces":\s*bool\(\s*worst\s*<=', src), (
            "the pin compares raw again")

    def test_the_pin_reports_the_bar_and_the_epsilon_SEPARATELY(self):
        """A reader must be able to see that the bar did not move."""
        src = _strip_comments(_SRC.read_text())
        block = src.split('out["reproduction_pin"] = {', 1)[1].split("\n        }", 1)[0]
        assert '"tolerance": PUBLISHED_ROUNDING_TOL' in block
        assert '"representation_epsilon": PUBLISHED_TOL_REPR_EPS' in block
