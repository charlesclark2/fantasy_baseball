"""INC-41 (2026-08-06) — two DIFFERENT models must not both be labelled "Proj." on one page.

The incident: game 824664 showed **Proj. 8.5** on the EV tracker and **7.4** on its game-detail
page. Both were correct; they are not the same quantity.

  * EV tracker "Proj. Runs"  = ``daily_model_predictions.pred_total_runs`` — the champion
    total-runs model (the one the pick's p_over is priced off).
  * Game detail, E2.7 panel  = ``mu_home + mu_away`` from ``totals_perside_mu_v1``
    (``feature_pregame_sub_model_signals``) — the per-side NegBin sub-model convolved into a
    game total. A structurally different model of the same real-world quantity.

``write_serving_store`` already has an anti-contradiction guard for exactly this
(``distribution_is_plausible``, whose docstring says the point is that the page "never shows two
contradictory projected totals") — but its threshold is ``PLAUSIBLE_CHAMPION_MAX_DIVERGENCE =
4.0`` while, by that constant's own comment, "the two models agree within ~1.09 runs on average".
So the ~1.1-run gap seen here sits squarely inside the permitted band and always will: it is the
TYPICAL disagreement, not a tail. Suppressing at ~1 run would blank the panel on a large share of
games, so the fix is naming, not a tighter threshold — the panel's number is labelled as THIS
distribution's mean rather than a second "Proj".

⚠️ Deliberately NOT asserted here: that the two numbers are equal. They are different models and
are *supposed* to differ. What must never recur is two unequal numbers under the same word.
"""
from __future__ import annotations

from pathlib import Path

from betting_ml.tests.test_mobile_form_control_guard import _strip_comments

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
DIST_PANEL = FRONTEND / "components" / "totals-distribution.tsx"
EV_TRACKER = FRONTEND / "app" / "ev-tracker" / "page.tsx"


def _code(path: Path) -> str:
    """Source with comments blanked out.

    Load-bearing: the fix DOCUMENTS the defect, and that comment necessarily contains the literal
    word "Proj". A scanner that did not strip comments would read the explanation as a violation
    and fail on the very code that satisfies it (the INC-38 prose-vs-argv lesson, mirrored).
    """
    assert path.exists(), f"missing {path}"
    return _strip_comments(path.read_text())


def test_distribution_panel_does_not_call_its_mean_a_projection():
    """The E2.7 panel renders the per-side sub-model's mean. It must not be labelled "Proj".

    RED-proves: restore ``label="Proj. total"`` or the chart's ``Proj ${meanLine…}`` and this
    fails.
    """
    code = _code(DIST_PANEL)
    assert "Proj" not in code, (
        'totals-distribution.tsx labels a value "Proj" in CODE (not a comment). That word is the '
        "EV tracker's headline pred_total_runs — a DIFFERENT model. Two unequal numbers under one "
        "word is INC-41. Name this one as the distribution's own mean."
    )


def _mean_tile(code: str) -> str:
    """The `Distribution mean` StatTile's own JSX block.

    Scoped deliberately: asserting `"total.mu" in code` over the WHOLE file passes even with the
    tile blanked, because `total.mu` also feeds the chart's reference line — a vacuous check
    (verified: it stayed green when the tile's value was replaced with a dash).
    """
    marker = 'label="Distribution mean"'
    assert marker in code, "the mean tile must carry an explicit, model-naming label"
    start = code.index(marker)
    end = code.index("/>", start)
    return code[start:end]


def test_distribution_panel_still_renders_its_mean():
    """The relabel must not have removed the number — a blank tile is not the fix."""
    assert "total.mu" in _mean_tile(_code(DIST_PANEL)), (
        "the `Distribution mean` tile must still render total.mu; relabelling it must not blank it"
    )


def test_the_panel_tells_the_reader_the_two_numbers_are_different_models():
    """A bare relabel still leaves a user comparing 8.5 and 7.4 with no explanation.

    The hint must say, in the product surface itself, that this is a different model from the
    headline projected total — otherwise the numbers still read as a contradiction.
    """
    code = _code(DIST_PANEL)
    assert "different model" in code.lower(), (
        "the mean tile's hint must state that this is a different model from the headline "
        "projected total, so an unequal pair reads as two models rather than a bug"
    )


def test_ev_tracker_projection_is_still_the_champion_total():
    """Pin the OTHER side of the collision.

    "Proj." on the EV tracker must remain ``pred_total_runs``. If a future change ever repointed
    it at the per-side distribution, the two surfaces would silently swap meaning and this guard's
    premise would be void — so the source of truth is asserted, not assumed.
    """
    code = _code(EV_TRACKER)
    assert "pick.pred_total_runs" in code, (
        "the EV tracker's projected total must remain daily_model_predictions.pred_total_runs"
    )


def test_the_stripper_actually_blanks_a_comment_containing_the_banned_word():
    """Prose must not be able to SATISFY or BREAK this guard.

    Without this, `test_distribution_panel_does_not_call_its_mean_a_projection` could be passing
    only because the stripper is over-eager (blanking real code), or failing only because it is
    under-eager (reading a comment as code). Both make it vacuous.
    """
    sample = '// this comment says Proj on purpose\nconst label = "Distribution mean"\n'
    stripped = _strip_comments(sample)
    assert "Proj" not in stripped, "stripper failed to blank a line comment (guard would false-fail)"
    assert "Distribution mean" in stripped, "stripper ate real code (guard would false-pass)"
