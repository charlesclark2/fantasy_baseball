"""Guards for MH2.2 — the E7.15-H3 trajectory family re-run as its OWN pre-registered field.

⭐ **WHAT THESE GUARD, AND WHY EACH ONE EXISTS.** MH2.2's whole contribution is that its field is
DECLARED rather than discovered. A story like that is worth exactly as much as the mechanical
enforcement of its own locks — a lock stated only in prose is the repo's documented-but-never-set
class (cf. `W7B_LAKEHOUSE_S3`) in a research costume.

🪤 **NF-D17: A GUARD ON AN `and`-COMPOSED RULE IS VACUOUS UNLESS ITS FIXTURE SATISFIES EVERY *OTHER*
CLAUSE.** `_assert_declared_field` checks two independent things (the arm SET, and the DSR trial
COUNT). A fixture that trips both proves neither, so each clause gets its OWN fixture that satisfies
the other — and each was RED-proven by deleting its clause from the source and watching only that
test fail.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from betting_ml.scripts.milb_mle.run_mh2_2 import (
    INACTIVE_METRICS,
    MH2_2_ANCHORS,
    MH2_2_ARMS,
    RETIRED_POSTHOC_FIELD,
    TRAJECTORY_FAMILY,
    _assert_declared_field,
    _series_moments,
    check_reproduction,
    posthoc_sensitivity,
    preregistered_bar,
)

_ART = (Path(__file__).resolve().parents[2]
        / "quant_sports_intel_models/baseball/edge_program/ablation_results")

_PLAYER_STRUCTURE_ARMS = ("P1_dedup", "P2_dedup_sqrt", "P3_player_re", "P4_re_dedup")


def _result(selectable: tuple[str, ...], n_trials: int | None):
    """A minimal `H3Result` stand-in — `_assert_declared_field` reads only these two surfaces."""
    lb = pd.DataFrame({
        "arm": ["L0_foil", *selectable, "A_traj_shuffled"],
        "selectable": [False, *[True] * len(selectable), False],
    })
    return SimpleNamespace(leaderboard=lb, dsr={"eligible": {"n_trials": n_trials}})


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 🔒 LOCK 1 — no arm is dropped for losing
# ══════════════════════════════════════════════════════════════════════════════════════════════════


def test_t3_tenure_is_in_the_declared_family_because_it_lost():
    """The single most important line in the story. `T3_tenure` is the arm E7.15-H3's post-hoc 2-arm
    reading dropped, and dropping an arm BECAUSE IT LOST is the second layer of the selection bias
    DSR exists to deflate. If a future edit removes it, this fails."""
    assert "T3_tenure" in TRAJECTORY_FAMILY
    assert set(TRAJECTORY_FAMILY) == {"T1_traj_ladder", "T2_traj_raw", "T3_tenure"}


def test_the_declared_family_strictly_contains_the_retired_posthoc_field():
    """The retired field must be a PROPER SUBSET of the declared one — that relation is the whole
    claim ("they dropped an arm"). If the two ever became equal, the story's premise would be false
    and the report would still happily render a `decompose_field_size` table of nothing."""
    assert set(RETIRED_POSTHOC_FIELD) < set(TRAJECTORY_FAMILY)
    assert sorted(set(TRAJECTORY_FAMILY) - set(RETIRED_POSTHOC_FIELD)) == ["T3_tenure"]


def test_a_missing_arm_raises_even_when_the_trial_count_is_right():
    """🪤 NF-D17 ISOLATING FIXTURE #1 — the ARM-SET clause, with the trial-COUNT clause SATISFIED.

    `n_trials` is set to 2, which correctly matches the 2-arm field being passed, so the second
    clause cannot fire. Only the arm-set clause can, which is what makes this test about that clause.
    """
    r = _result(RETIRED_POSTHOC_FIELD, n_trials=len(RETIRED_POSTHOC_FIELD))
    with pytest.raises(AssertionError, match="not the DECLARED family"):
        _assert_declared_field(r, "bb_pct")


def test_an_anchor_joining_the_trial_field_raises_even_when_the_arm_set_is_right():
    """🪤 NF-D17 ISOLATING FIXTURE #2 — the TRIAL-COUNT clause, with the ARM-SET clause SATISFIED.

    ⭐ MH2.1 (a): a diagnostic anchor is NEVER a trial. An anchor is far from the winner BY
    CONSTRUCTION, so letting one into the DSR field inflates the cross-trial dispersion `V` and the
    anchor that exists to POLICE the metric silently SETS the gate's own bar — exactly how MH2.1's
    `oracle_floor` made DSR unclearable for a purely arithmetic reason.
    """
    r = _result(TRAJECTORY_FAMILY, n_trials=len(TRAJECTORY_FAMILY) + 1)
    with pytest.raises(AssertionError, match="diagnostic\nanchor is NEVER a trial|NEVER a trial"):
        _assert_declared_field(r, "bb_pct")


def test_the_declared_field_passes_both_clauses():
    """The two-sided half: a correct field must NOT raise, or the guard is just a tripwire."""
    _assert_declared_field(_result(TRAJECTORY_FAMILY, n_trials=len(TRAJECTORY_FAMILY)), "bb_pct")


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 🔒 LOCK 2 — the mechanism split
# ══════════════════════════════════════════════════════════════════════════════════════════════════


def test_no_player_structure_arm_is_in_the_trajectory_field():
    """The pitcher side's largest H3 lift (`k_pct` +1.713%) is `P4_re_dedup` — PLAYER STRUCTURE, not
    trajectory. Letting one of those arms into this field would credit trajectory with another
    mechanism's result, which is the mis-attribution lock 2 exists to prevent."""
    scored = {a.label for a in MH2_2_ARMS}
    assert scored.isdisjoint(_PLAYER_STRUCTURE_ARMS)
    assert set(TRAJECTORY_FAMILY).isdisjoint(_PLAYER_STRUCTURE_ARMS)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 🔒 LOCK 4 — INACTIVE is declared, not discovered
# ══════════════════════════════════════════════════════════════════════════════════════════════════


def test_xwoba_against_is_declared_inactive_with_a_stated_mechanism():
    """A Triple-A-only Statcast feature gives the trajectory delta ZERO within-player transitions.
    Declaring it up front is what stops a later reader treating a structural scope limit as either a
    power problem or a defect to hunt (MH2 §8 / NF1.9)."""
    reason = INACTIVE_METRICS["pitcher"]["xwoba_against"]
    assert "Triple-A" in reason or "TRIPLE-A" in reason
    assert "batter" not in INACTIVE_METRICS or "xwoba_against" not in INACTIVE_METRICS.get("batter", {})


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 🔒 LOCK 5 — anchors, present and correctly scoped
# ══════════════════════════════════════════════════════════════════════════════════════════════════


def test_a_re_shuffled_is_absent_because_its_defender_left_the_field():
    """`A_re_shuffled` is a matched foil for `P3_player_re`, which lock 2 removed. An anchor without
    its defender can neither pass nor fail meaningfully (NF1.7 (a)), and re-pointing it at whatever
    is currently winning would veto an innocent arm for another mechanism's sin (NF-D16 g‴)."""
    assert "A_re_shuffled" not in {a.label for a in MH2_2_ANCHORS}
    assert "A_re_shuffled" not in {a.label for a in MH2_2_ARMS}


def test_every_declared_anchor_is_actually_scored():
    """🪤 NF1.7 (a): an anchor that did not RUN is not an anchor that passed. `evaluate_anchors`
    BLOCKS on a missing anchor, so a mismatch between the anchor tuple and the arm tuple would make
    every MH2.2 verdict BLOCKED — this catches that at import rather than after a run."""
    scored = {a.label for a in MH2_2_ARMS}
    missing = [a.label for a in MH2_2_ANCHORS if a.label not in scored]
    assert not missing, f"declared anchors absent from the scored arms: {missing}"


def test_every_refute_anchor_defends_an_arm_that_is_actually_in_the_field():
    """A `refute` anchor with an explicit defender is a matched foil for ONE named mechanism. If its
    defender is not scored, the anchor is vacuous — the precise reason `A_re_shuffled` was dropped,
    enforced generally so a future anchor cannot re-introduce the shape."""
    scored = {a.label for a in MH2_2_ARMS}
    for a in MH2_2_ANCHORS:
        if a.kind == "refute" and a.defender:
            assert a.defender in scored, (
                f"anchor {a.label} defends {a.defender}, which is not in the field — a matched foil "
                f"without its mechanism is a pass on nothing (NF1.7 (a))")


def test_the_foil_is_present_and_is_not_selectable():
    """Every lift, every skill series and the whole DSR construction is relative to `L0_foil`."""
    foil = [a for a in MH2_2_ARMS if a.label == "L0_foil"]
    assert len(foil) == 1 and not foil[0].selectable


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# Moments — "same moments everywhere, or nowhere"
# ══════════════════════════════════════════════════════════════════════════════════════════════════


def test_series_moments_match_deflated_sharpe_exactly():
    """⚠️ `cv_power` warns TWICE that the empirical moments must be threaded through, because a
    classifier answering about a normal-moment world while the GATE used the real ones will disagree
    with it about whether a metric is DSR-reachable — and that disagreement IS the verdict. This pins
    `_series_moments` to `deflated_sharpe`'s own internal computation."""
    from betting_ml.utils.overfitting import deflated_sharpe

    rng = np.random.default_rng(7)
    for series in (rng.normal(0.3, 1.0, 11), rng.gamma(2.0, 1.0, 11) - 2.0):
        sr, skew, kurt = _series_moments(series)
        res = deflated_sharpe(series, n_trials=3, trial_sharpes=[0.1, 0.2, 0.3])
        assert sr == pytest.approx(res.observed_sr, rel=1e-9, abs=1e-12)
        rc, sd0 = series - series.mean(), float(np.std(series, ddof=0))
        assert skew == pytest.approx(float((rc ** 3).mean() / sd0 ** 3), rel=1e-9)
        assert kurt == pytest.approx(float((rc ** 4).mean() / sd0 ** 4), rel=1e-9)


def test_series_moments_degrades_safely_on_a_too_short_series():
    """Fewer than 3 observations cannot support a Sharpe; returning normal-ish defaults is the
    documented degradation, and it must not raise inside a report render."""
    assert _series_moments(np.array([1.0, 2.0])) == (0.0, 0.0, 3.0)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# The reproduction anchor — it must be able to FAIL, and must never pass vacuously
# ══════════════════════════════════════════════════════════════════════════════════════════════════


def _fake_side(tmp: Path):
    return SimpleNamespace(reduced=SimpleNamespace(artifact_suffix="_nonexistent_side"))


def test_reproduction_is_UNVERIFIED_not_OK_when_the_h3_artifact_is_absent(tmp_path):
    """🪤 NF1.7 (a) — a check that did not run is not a check that passed. An absent baseline must
    never be scored healthy."""
    out = check_reproduction({}, _fake_side(tmp_path))
    assert out["status"] == "UNVERIFIED"


def test_reproduction_detects_a_real_mismatch(monkeypatch, tmp_path):
    """The two-sided proof: perturb ONE cell and the anchor must go MISMATCH. A reproduction check
    that cannot fail is worse than none — it launders a different run as the same evidence."""
    import betting_ml.scripts.milb_mle.run_mh2_2 as mod

    folds = [2016, 2017, 2018]
    good = pd.DataFrame({"L0_foil": [0.1, 0.2, 0.3], "T1_traj_ladder": [0.11, 0.19, 0.31]},
                        index=folds)
    art = tmp_path / "e7_15_artifacts"
    art.mkdir()
    (art / "e7_15_h3_summary.json").write_text(json.dumps(
        {"per_metric": {"bb_pct": {"mae_by_fold": good.to_dict()}}}))
    monkeypatch.setattr(mod, "_H3_ART", art)
    side = SimpleNamespace(reduced=SimpleNamespace(artifact_suffix=""))

    same = check_reproduction({"bb_pct": SimpleNamespace(mae_by_fold=good.copy())}, side)
    assert same["status"] == "OK" and same["per_metric"][0]["n_cells_compared"] == 6

    drifted = good.copy()
    drifted.loc[2017, "T1_traj_ladder"] += 1e-6
    bad = check_reproduction({"bb_pct": SimpleNamespace(mae_by_fold=drifted)}, side)
    assert bad["status"] == "MISMATCH"


def test_reproduction_survives_the_json_string_index_and_actually_compares_cells(monkeypatch,
                                                                                tmp_path):
    """⭐ THE ANTI-VACUITY GUARD, and it is not hypothetical — the first cut of this check failed it.

    JSON dict keys are STRINGS, so a recorded matrix round-trips indexed by "2016" while the fresh
    one is indexed by the int 2016. Left un-coerced, `reindex` aligns NOTHING, every gap is NaN, and
    a perfect reproduction reports MISMATCH. `n_cells_compared > 0` is what makes 'OK' mean
    something rather than 'nothing was looked at'.
    """
    import betting_ml.scripts.milb_mle.run_mh2_2 as mod

    good = pd.DataFrame({"L0_foil": [0.1, 0.2], "T1_traj_ladder": [0.11, 0.19]}, index=[2016, 2017])
    art = tmp_path / "e7_15_artifacts"
    art.mkdir()
    # round-trip through JSON exactly as the real artifact does — this is what stringifies the index
    (art / "e7_15_h3_summary.json").write_text(json.dumps(
        {"per_metric": {"bb_pct": {"mae_by_fold": good.to_dict()}}}))
    monkeypatch.setattr(mod, "_H3_ART", art)
    out = check_reproduction({"bb_pct": SimpleNamespace(mae_by_fold=good.copy())},
                             SimpleNamespace(reduced=SimpleNamespace(artifact_suffix="")))
    assert out["status"] == "OK"
    assert out["per_metric"][0]["n_cells_compared"] == 4, "the fold index did not align"


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# The recorded result — the null this story exists to put on file
# ══════════════════════════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("suffix,expected", [
    ("", {"woba": "GENUINE_ABSENCE", "k_pct": "POWER_LIMITED",
          "bb_pct": "POWER_LIMITED", "iso": "POWER_LIMITED"}),
    ("_pitchers", {"k_pct": "GENUINE_ABSENCE", "bb_pct": "GENUINE_ABSENCE",
                   "hr_rate": "DSR_UNREACHABLE", "gb_pct": "POWER_LIMITED",
                   "xwoba_against": "INACTIVE"}),
])
def test_the_recorded_null_states_are_what_the_preregistration_predicted(suffix, expected):
    """All nine states were written down in `mh2_2_preregistration.md` §7 BEFORE the run and all nine
    reproduced. Pinned so a later re-run that silently changes a state has to say so."""
    path = _ART / f"mh2_2_artifacts/mh2_2_trajectory_family{suffix}_summary.json"
    if not path.exists():
        pytest.skip(f"{path.name} not generated in this checkout")
    got = {m: c["state"] for m, c in json.loads(path.read_text())["null_classification"].items()}
    assert got == expected


@pytest.mark.parametrize("suffix", ["", "_pitchers"])
def test_nothing_shipped_and_the_evidence_reproduced(suffix):
    """The deliverable: a recorded NULL over a DECLARED field, on evidence proven identical to
    E7.15-H3's. `best_alpha = 0` — nothing here reaches the served board."""
    path = _ART / f"mh2_2_artifacts/mh2_2_trajectory_family{suffix}_summary.json"
    if not path.exists():
        pytest.skip(f"{path.name} not generated in this checkout")
    d = json.loads(path.read_text())
    assert d["declared_field"] == list(TRAJECTORY_FAMILY)
    assert all(r["verdict"] != "ADD" for r in d["per_metric"].values())
    assert d["reproduction_vs_e7_15_h3"]["status"] == "OK"
    assert d["reproduction_vs_e7_15_h3"]["worst_abs_gap"] == 0.0


def test_the_posthoc_gain_is_bought_by_dispersion_not_multiplicity():
    """⭐ THE FINDING THAT RETIRES THE 0.998. Dropping `T3_tenure` collapses the cross-trial Sharpe
    dispersion by ~20,000× on `bb_pct`, and the dispersion channel ALONE reproduces the whole jump —
    i.e. the recorded 0.998 was bought by deleting a LOSER's spread, not by an honest multiplicity
    reduction. Computed here from the recorded fold matrix rather than trusting the report text."""
    path = _ART / "e7_15_artifacts/e7_15_h3_summary.json"
    if not path.exists():
        pytest.skip("E7.15-H3 artifact not in this checkout")
    mae = pd.DataFrame(json.loads(path.read_text())["per_metric"]["bb_pct"]["mae_by_fold"])
    d = posthoc_sensitivity(mae)
    assert d["dropped_arm"] == ["T3_tenure"]
    assert d["dispersion_collapse_ratio"] > 1000
    # the dispersion channel alone gets at least as far as shrinking the trial count alone
    assert d["dsr_if_only_dispersion_shrank"] >= d["dsr_if_only_trial_count_shrank"]
    assert d["dsr_narrow_field"] > d["dsr_wide_field"]


def test_the_preregistered_bar_is_stated_in_sharpe_and_the_winner_falls_short():
    """🔒 LOCK 3 — "DSR ≥ 0.95" is not a readable bar; the per-fold Sharpe this field demands is. On
    the best metric in the family the winner is short of it, which is the story's whole result."""
    path = _ART / "e7_15_artifacts/e7_15_h3_summary.json"
    if not path.exists():
        pytest.skip("E7.15-H3 artifact not in this checkout")
    mae = pd.DataFrame(json.loads(path.read_text())["per_metric"]["bb_pct"]["mae_by_fold"])
    bar = preregistered_bar(mae, n_folds=11)
    assert bar["observed_sr"] < bar["required_sr_for_dsr_gate"]
    assert bar["sr_shortfall"] > 0
    assert bar["extra_debut_cohorts_needed"] and bar["extra_debut_cohorts_needed"] > 0


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# The H3 parameterization must not have changed H3
# ══════════════════════════════════════════════════════════════════════════════════════════════════


def test_run_h3_defaults_preserve_e7_15_h3_behaviour_exactly():
    """MH2.2 added `anchors=` and `calibrated_fold_clause=` to `run_h3`. Both MUST default to H3's
    own behaviour, or a parameter added for a later story would retroactively re-decide H3's recorded
    verdicts — the thing a diagnostic story must never do."""
    import inspect

    from betting_ml.scripts.milb_mle.run_e7_15_h3 import H3_ANCHORS, run_h3

    sig = inspect.signature(run_h3)
    assert sig.parameters["anchors"].default is H3_ANCHORS
    assert sig.parameters["calibrated_fold_clause"].default is False


def test_the_calibrated_fold_clause_is_weakly_stricter_at_this_fold_count():
    """MH2.2 opts INTO the H8 clause. Adopting it must only ever be able to prevent a false ADD —
    never manufacture one — so it has to be no looser than the legacy bar at 11 folds."""
    from betting_ml.utils.cv_power import fold_consistency_clause

    cl = fold_consistency_clause(11)
    assert cl.attainable and cl.is_stricter_than_legacy
    assert cl.wins_required >= cl.legacy_wins_required
    assert cl.attained_false_fire <= cl.legacy_false_fire
