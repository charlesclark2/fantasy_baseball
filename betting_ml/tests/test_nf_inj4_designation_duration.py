"""NF-INJ4 guards — the designation → games-missed duration model.

Every clause here pins a decision the pre-registration made BEFORE scoring, or a defect this
session actually hit. RED-proved by `betting_ml/tests/nf_inj4_red_proof.py`: each guard is verified
to go RED on a deliberately broken source, with a UNIQUE mutation anchor, a landed-on-disk
assertion, a gone-token assertion, and a NOT-SELECTED control.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quant_sports_intel_models.football.nfl.fantasy import (
    nf_inj4_designation_duration as DD,
)

_SRC = Path(DD.__file__)


def _stripped_source() -> str:
    """Source with comment lines removed — a guard that a COMMENT can satisfy is not a guard
    (INC-38: the explanatory comment above a fixed command made the first cut pass on broken
    source)."""
    return "\n".join(ln for ln in _SRC.read_text().splitlines()
                     if not ln.lstrip().startswith("#"))


# ── provenance: the source-admissibility decision ──────────────────────────────────────────────
def test_espn_is_excluded_from_the_admissible_sources():
    """The census measured ESPN's designations one week late, leaving them no PIT-valid week. The
    exclusion is a provenance verdict settled before any arm existed (E2.1-r)."""
    assert "espn" not in DD.ADMISSIBLE_SOURCES
    assert "espn" in DD.EXCLUDED_SOURCES
    assert set(DD.ADMISSIBLE_SOURCES) == {"nfl", "cbs"}


def _store(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def test_a_blank_capture_never_overwrites_an_earlier_designation():
    """⭐ THE LOAD-BEARING RESOLUTION RULE. nfl.com fills its game-status column only on the final
    report, so a blank mid-week capture is "not YET designated". Letting it win on recency would
    erase a real earlier CBS designation — NF-W0's "NULL is not healthy", in the direction that
    costs signal."""
    out = DD.resolve_designations(_store([
        {"week": 5, "gsis_id": "P1", "report_status": "questionable", "practice_status": "limited",
         "capture_timestamp": "2025-10-01T12:00:00+00:00", "source": "cbs"},
        {"week": 5, "gsis_id": "P1", "report_status": None, "practice_status": "full",
         "capture_timestamp": "2025-10-03T12:00:00+00:00", "source": "nfl"},   # LATER, blank
    ]))
    assert len(out) == 1
    assert out.iloc[0]["designation"] == "questionable"


def test_resolution_takes_the_whole_row_not_the_column_wise_last_non_null():
    """A defect this session hit: `groupby(...).last()` is COLUMN-WISE last-non-null, so it takes
    `report_status` from one capture and `practice_status` from another. The winning row's fields
    must travel together."""
    out = DD.resolve_designations(_store([
        {"week": 3, "gsis_id": "P2", "report_status": "questionable", "practice_status": "dnp",
         "capture_timestamp": "2025-09-17T12:00:00+00:00", "source": "cbs"},
        {"week": 3, "gsis_id": "P2", "report_status": "out", "practice_status": None,
         "capture_timestamp": "2025-09-20T12:00:00+00:00", "source": "cbs"},   # LATER, designated
    ]))
    assert out.iloc[0]["designation"] == "out"
    # the later row carried NO practice status; a column-wise last would resurrect "dnp".
    assert out.iloc[0]["practice_level"] == DD.PRACTICE_UNKNOWN


def test_an_unparseable_capture_stamp_rejects_the_build():
    with pytest.raises(ValueError, match="admissibility bound"):
        DD.resolve_designations(_store([
            {"week": 1, "gsis_id": "P3", "report_status": "out", "practice_status": None,
             "capture_timestamp": "not-a-timestamp", "source": "nfl"}]))


def test_an_unrecognised_designation_token_rejects_rather_than_flowing_on():
    """The NF-C0e wrong-key class: an unknown token that flows on as if captured produces a
    confident, silently wrong cell."""
    with pytest.raises(ValueError, match="unrecognised designation"):
        DD.resolve_designations(_store([
            {"week": 1, "gsis_id": "P4", "report_status": "probable", "practice_status": None,
             "capture_timestamp": "2025-09-05T12:00:00+00:00", "source": "nfl"}]))


# ── the outcome ────────────────────────────────────────────────────────────────────────────────
def _grid(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def test_a_team_game_with_no_certified_appearance_is_a_miss():
    """⭐ THE LOAD-BEARING OUTCOME CHOICE. `build_spine` keeps only ACT/INA rows, so a player who
    lands on IR DISAPPEARS from it. Counting only `label == inactive` would systematically
    under-count exactly the LONG spells a duration model exists to price."""
    rosters = pd.DataFrame([{"season": 2025, "week": w, "team": "AAA", "gsis_id": "P5"}
                            for w in range(1, 5)])
    schedule = pd.DataFrame([{"week": w, "home_team": "AAA", "away_team": "BBB"}
                             for w in range(1, 5)])
    # the player is labelled only in week 1; weeks 2-4 he is OFF the spine entirely (IR).
    labels = pd.DataFrame([{"week": 1, "gsis_id": "P5", "label": "played"}])
    g = DD.availability_grid(rosters, schedule, labels, max_week=4)
    assert list(g[g.gsis_id == "P5"].sort_values("week")["missed"]) == [False, True, True, True]


def test_a_bye_is_skipped_never_counted_as_a_miss():
    rosters = pd.DataFrame([{"season": 2025, "week": w, "team": "AAA", "gsis_id": "P6"}
                            for w in range(1, 4)])
    schedule = pd.DataFrame([{"week": 1, "home_team": "AAA", "away_team": "BBB"},
                             {"week": 3, "home_team": "AAA", "away_team": "BBB"}])   # week 2 = bye
    labels = pd.DataFrame([{"week": 1, "gsis_id": "P6", "label": "played"},
                           {"week": 3, "gsis_id": "P6", "label": "played"}])
    g = DD.availability_grid(rosters, schedule, labels, max_week=3).sort_values("week")
    assert list(g["has_game"]) == [True, False, True]
    assert not bool(g["missed"].any())


def test_the_spell_is_consecutive_and_stops_at_the_next_appearance():
    grid = _grid([{"gsis_id": "P7", "week": w, "has_game": True,
                   "missed": w in (2, 3, 6)} for w in range(1, 8)])
    d = DD.attach_spells(pd.DataFrame([{"week": 2, "gsis_id": "P7"}]), grid)
    assert int(d.iloc[0]["spell"]) == 2                 # weeks 2,3 — NOT the later week-6 miss
    assert float(d.iloc[0]["total_missed_rest"]) == 3.0  # the diagnostic sees all three
    assert bool(d.iloc[0]["censored"]) is False


def test_a_spell_running_to_the_season_end_is_flagged_censored():
    grid = _grid([{"gsis_id": "P8", "week": w, "has_game": True, "missed": w >= 15}
                  for w in range(1, 19)])
    d = DD.attach_spells(pd.DataFrame([{"week": 15, "gsis_id": "P8"}]), grid)
    assert bool(d.iloc[0]["censored"]) is True
    assert int(d.iloc[0]["spell"]) == 4


# ── the metric ─────────────────────────────────────────────────────────────────────────────────
def test_crps_is_the_exact_discrete_form_not_a_quantile_grid():
    """A point mass at k, realised at k, is exactly 0; a point mass one game away is exactly 1.
    A coarse quantile grid silently TIES arms whose predictives differ by less than its step (NF-W4)."""
    assert DD.crps_discrete(DD.point_mass([2.0]), np.array([2]))[0] == pytest.approx(0.0)
    assert DD.crps_discrete(DD.point_mass([2.0]), np.array([3]))[0] == pytest.approx(1.0)
    assert DD.crps_discrete(DD.point_mass([0.0]), np.array([3]))[0] == pytest.approx(3.0)


def test_every_predictive_is_truncated_to_the_rows_own_support():
    """A prediction of five missed games where two remain is impossible, and the transformation must
    be identical for every arm — a transformation one arm gets and another does not is not a
    comparison."""
    pmf = np.full((1, DD.SUPPORT_MAX + 1), 1.0 / (DD.SUPPORT_MAX + 1))
    t = DD.truncate_to_support(pmf, np.array([2]))
    assert t[0, 3:].sum() == pytest.approx(0.0)
    assert t[0, :3].sum() == pytest.approx(1.0)


def test_an_empty_cell_raises_rather_than_yielding_a_silent_predictive():
    with pytest.raises(ValueError, match="ZERO observations"):
        DD.empirical_pmf(np.array([], dtype=int))


# ── the declared field ─────────────────────────────────────────────────────────────────────────
def test_the_degenerates_sit_at_opposite_ends_of_the_support():
    """NF1.8: a constraint a degenerate satisfies is fine because the metric eliminates it, but a
    CRITERION a degenerate wins is fatal — so both ends must be scored and both must lose."""
    assert set(DD.DEGENERATE_ARMS) == {"always_zero", "always_max"}
    test = pd.DataFrame({"designation": ["out"], "position": ["WR"],
                         "practice_level": ["dnp"], "games_remaining": [9], "spell": [3]})
    train = pd.DataFrame({"designation": ["out"] * 40, "position": ["WR"] * 40,
                          "practice_level": ["dnp"] * 40, "games_remaining": [9] * 40,
                          "spell": [2] * 40})
    lo = DD.truncate_to_support(DD.fit_predict("always_zero", train, test), np.array([9]))
    hi = DD.truncate_to_support(DD.fit_predict("always_max", train, test), np.array([9]))
    assert DD.expected_games_missed(lo)[0] == pytest.approx(0.0)
    assert DD.expected_games_missed(hi)[0] == pytest.approx(9.0)


def test_the_incumbent_reference_is_itself_a_declared_degenerate():
    """⭐ This is what makes MH2.1 (a) hold BY CONSTRUCTION rather than by a second rule that could
    be forgotten: the lift series is measured against `always_zero`, whose own trial Sharpe is
    identically 0, and it is already excluded from `V` as a degenerate."""
    assert DD.INCUMBENT_ARM in DD.DEGENERATE_ARMS


def test_the_thin_cell_backoff_uses_the_parent_not_a_one_row_distribution():
    """`MIN_CELL_N` is a conventional a-priori floor; a cell below it must back off, never fit."""
    train = pd.DataFrame({
        "designation": ["out"] * 40 + ["doubtful"] * 3,
        "position": ["WR"] * 40 + ["QB"] * 3,
        "practice_level": ["dnp"] * 43,
        "games_remaining": [9] * 43,
        "spell": [1] * 40 + [7, 7, 7]})
    test = pd.DataFrame({"designation": ["doubtful"], "position": ["QB"],
                         "practice_level": ["dnp"], "games_remaining": [9]})
    pmf = DD.fit_predict("desig_x_posgroup", train, test)
    # the 3-row doubtful x QB cell must NOT produce a point mass at 7.
    assert pmf[0][7] < 1.0 - 1e-9


def test_only_shippable_arms_can_be_selected():
    """`fixed_penalty`, the matched foil and the degenerates are ineligible BY REGISTRATION, not by
    outcome (NF-D20)."""
    assert set(DD.SHIPPABLE_ARMS).isdisjoint(DD.NON_SHIPPABLE_BY_REGISTRATION)
    assert set(DD.SHIPPABLE_ARMS) | set(DD.NON_SHIPPABLE_BY_REGISTRATION) == set(DD.ARMS)
    assert DD.MATCHED_FOIL in DD.NON_SHIPPABLE_BY_REGISTRATION
    assert "fixed_penalty" in DD.NON_SHIPPABLE_BY_REGISTRATION


# ── the instrument declarations (PLAT-CVP2) ────────────────────────────────────────────────────
def test_gate_classes_classifies_every_gate_the_study_scores():
    """A PARTIALLY declared partition reintroduces the ambiguity it exists to remove — the
    instrument raises on one, and this pins that the declaration stays complete."""
    from quant_sports_intel_models.football.nfl.fantasy import (
        run_nf_inj4_designation_duration as R,
    )
    frame = pd.DataFrame({
        "designation": (["out"] * 40 + ["questionable"] * 40),
        "position": ["WR"] * 80, "practice_level": ["dnp"] * 80,
        "games_remaining": [9] * 80, "spell": ([2] * 40 + [0] * 40),
        "week": list(range(1, 81)), "gsis_id": [f"P{i}" for i in range(80)],
        "censored": [False] * 80})
    scored = R.gate_table(R.run_folds(frame))
    for arm, gates in scored.items():
        assert set(gates) == set(DD.GATE_CLASSES), f"{arm}: gate table drifted from gate_classes"


def test_pbo_is_never_carried_as_a_per_arm_gate():
    """A FIELD-LEVEL statistic carried per-arm converts "the search was unstable" into "this arm
    failed", which is not a statement PBO makes (the PM convention)."""
    from betting_ml.utils import cv_power as CP
    assert "pbo" not in DD.GATE_CLASSES and "cscv" not in DD.GATE_CLASSES
    assert DD.PBO_APPLICATION == "field"
    assert set(DD.GATE_CLASSES).isdisjoint(CP._FIELD_LEVEL_STATISTICS)


def test_the_deflation_and_invariant_declarations_agree_with_the_partition():
    assert DD.DEFLATION_GATES == tuple(g for g, c in DD.GATE_CLASSES.items() if c == "deflation")
    for g in DD.INVARIANT_GATES:
        assert DD.GATE_CLASSES[g] == "invariant"
    assert DD.DECLARED_FIELD_SIZE == len(DD.ARMS)


def test_the_bh_family_is_declared_as_a_single_hypothesis():
    assert DD.BH_FAMILY_SIZE == 1
    assert DD.BH_CUTOFF_BINDING == 0.05
    assert DD.BH_CUTOFF_CONSERVATIVE == pytest.approx(0.05 / DD.DECLARED_FIELD_SIZE)


def test_the_fold_count_is_sign_certifiable_under_both_declared_bh_readings():
    """PLAT-CVP2: a fold-sign floor ABOVE the cutoff makes a multiplicity clause structurally
    unpassable, and that must be refused at REGISTRATION time, not discovered after."""
    from betting_ml.utils import cv_power as CP
    for cut in (DD.BH_CUTOFF_BINDING, DD.BH_CUTOFF_CONSERVATIVE):
        rep = CP.validate_sign_certifiability(n_folds=DD.N_FOLDS, bh_cutoff=cut, strict=False)
        assert rep.certifiable, f"{DD.N_FOLDS} folds cannot certify against {cut}"
        assert rep.headroom <= 0.5, "the margin rule is not met"


# ── application semantics ──────────────────────────────────────────────────────────────────────
def test_a_player_with_both_a_news_cap_and_a_designation_takes_ONE_of_them():
    """⭐ THE DISJOINTNESS INVARIANT, on a CONSTRUCTED both-channels row. The NEWS-1 rule's purpose
    is no double-discounting; a third channel that does not announce itself would stack silently."""
    current = 14.0
    desig = DD.remaining_season_rate_cap(current, 2.3145)
    news = DD.remaining_season_rate_cap(current, 6.0)
    applied, owner = DD.compose_availability_caps(
        current, designation_games=desig, news_games=news)
    assert owner == DD.CHANNEL_NEWS
    assert applied == pytest.approx(min(desig, news))
    stacked = DD.remaining_season_rate_cap(desig, 6.0)
    assert applied > stacked + 1e-9, "the composition must not be the stacked value"


def test_the_formal_status_cap_wins_when_it_is_the_harshest():
    applied, owner = DD.compose_availability_caps(
        14.0, formal_games=4.0, designation_games=12.0, news_games=9.0)
    assert (applied, owner) == (4.0, DD.CHANNEL_FORMAL)


def test_no_channel_leaves_the_projection_untouched():
    assert DD.compose_availability_caps(11.5) == (11.5, DD.CHANNEL_NONE)


def test_the_cap_is_monotone_and_never_raises_a_projection():
    for missed in (0.0, 0.5, 3.0, 17.0):
        assert DD.remaining_season_rate_cap(10.0, missed) <= 10.0 + 1e-12


def test_the_designation_model_is_not_wired_into_the_serving_availability_owner():
    """⛔ DEPLOY-HELD. The bake-off returned CONSTRAINT_REFUSED, so the shipped availability owner
    must carry NO branch that reads this model — wiring an uncertified path into the serving module
    is the "wired ≠ invoked" hazard for a model that is not authorised to serve."""
    sp = Path(
        DD.__file__).parent / "season_projection.py"
    src = "\n".join(ln for ln in sp.read_text().splitlines()
                    if not ln.lstrip().startswith("#"))
    assert "nf_inj4" not in src
    assert not re.search(r"\bcompose_availability_caps\s*\(", src)
