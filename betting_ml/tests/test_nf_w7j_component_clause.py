"""NF-W7j guards — the COMPONENT-CLAUSE decision + the served-cell audit.

Every clause here has an ISOLATING fixture (NF-D17: a guard on `A and B and C` only tests A if its
fixture SATISFIES B and C, so a single fixture that trips several clauses proves none of them), and
every one is RED-proved in `red_proof_nf_w7j.py` against deliberately broken source.

⛔ These tests import the runner but never run the bake-off — NF-W7j refits nothing.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from quant_sports_intel_models.football.nfl.fantasy import fp_component_clause as CC
from quant_sports_intel_models.football.nfl.fantasy import (
    run_nf_w7j_component_clause as R,
)

ABL = Path(R.__file__).resolve().parent / "ablation_results"
RECORD = ABL / CC.W7F_RECORD
ARTIFACT = ABL / "nf_w7j_component_clause.json"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Fixtures — each isolates ONE condition by SATISFYING every other (NF-D17)
# ══════════════════════════════════════════════════════════════════════════════════════════════

def _audit(passes: bool) -> dict:
    return {"passes": passes, "seeds": {}, "positive_controls": {}, "reading": ""}


def _per_leg(rel: float = 0.02) -> dict:
    return {"relative_change": rel, "served_crps_sum_priced": 100.0,
            "recalibrated_crps_sum_priced": 100.0 * (1.0 + rel),
            "relative_change_by_arm": {CC.W7F_WINNER: rel}}


def _sel(mean_delta: float = 0.0184, foil_crps: float = 2.5829) -> dict:
    return {"mean_delta": mean_delta, "mean_crps": {CC.W7F_MATCHED_FOIL: foil_crps}}


#: A series that IS demonstrably positive (every fold degraded, tight) — so B is TRUE and any other
#: condition under test is the only thing that can flip the verdict.
DEMONSTRABLE_SERIES = [0.019, 0.020, 0.021, 0.020, 0.019, 0.021, 0.020, 0.020]

#: NF-W7f's REAL series — 5/8 folds, sign-inconsistent, CI spans zero.
W7F_SERIES = [-0.01249, -0.003508, 0.007389, 0.018102, 0.003166, 0.01418, -0.002869, 0.006013]


def _evaluate(series, *, audit_passes=True, rel=0.02, mean_delta=0.0184):
    return R.evaluate_component_clause(
        series=series, per_leg=_per_leg(rel), sel=_sel(mean_delta), audit=_audit(audit_passes))


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. Thresholds are DESIGN quantities (prereg §0.2 / E2.1-r)
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_the_materiality_fraction_is_nf_w7c_s_convention_not_nf_w7f_s_observed_value():
    """NF-W7c's *significant AND ≥1/10 the claimed effect*, named by NF-W7f §12.5b(3) BEFORE this
    story existed. ⛔ Reverse-engineering a bar from the observed +0.3866% is the E2.1-r inversion."""
    assert CC.MATERIALITY_FRACTION == 0.10
    observed = CC.W7F_PINS["per_leg_relative_change"]
    # the bar must not be any simple function of the thing it judges
    assert CC.MATERIALITY_FRACTION != pytest.approx(observed, abs=1e-6)
    assert CC.ALPHA_DEMONSTRABLE == 0.05
    assert CC.ALPHA_DEMONSTRABLE != pytest.approx(observed, abs=1e-6)


def test_the_raw_tolerance_is_retained_so_both_readings_are_always_reported():
    """NF-D20 — a pre-registered anchor that fails is left FAILING and DECOMPOSED, never relabelled."""
    assert CC.RAW_TOLERANCE == 0.0
    out = _evaluate(W7F_SERIES)
    assert out["raw"]["clause"] == CC.RAW_CLAUSE
    assert out["raw"]["refuses"] is True, "NF-W7f's raw clause must still REFUSE, and still say so"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. The clause is a CONJUNCTION — one isolating fixture PER condition
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_condition_B_alone_decides_when_A_C_D_all_hold():
    """B isolated: audit passes, the change is 0.02 (far above any band), the effect is positive —
    so ONLY the significance of the per-fold series can move the verdict."""
    refusing = _evaluate(DEMONSTRABLE_SERIES)["decided"]
    assert refusing["conditions"] == {"A_served_cell_audit_passes": True, "B_demonstrable": True,
                                      "C_material_primary_relative": True,
                                      "D_claimed_effect_well_defined": True}
    assert refusing["refuses"] is True

    not_refusing = _evaluate(W7F_SERIES, rel=0.02)["decided"]
    assert not_refusing["conditions"]["A_served_cell_audit_passes"] is True
    assert not_refusing["conditions"]["C_material_primary_relative"] is True
    assert not_refusing["conditions"]["D_claimed_effect_well_defined"] is True
    assert not_refusing["conditions"]["B_demonstrable"] is False
    assert not_refusing["refuses"] is False, "B alone must be able to stop a refusal"


def test_condition_C_alone_decides_when_A_B_D_all_hold():
    """C isolated: the SAME demonstrable series, only the magnitude changes. A band-sized change
    (1/10 of the claimed effect is 0.000712) vs one an order below it."""
    tiny = [x * 1e-4 for x in DEMONSTRABLE_SERIES]   # ~2e-6, three orders below the band
    out = R.evaluate_component_clause(series=tiny, per_leg=_per_leg(2e-6), sel=_sel(),
                                      audit=_audit(True))["decided"]
    assert out["conditions"]["A_served_cell_audit_passes"] is True
    assert out["conditions"]["B_demonstrable"] is True, "the tiny series is still demonstrable"
    assert out["conditions"]["D_claimed_effect_well_defined"] is True
    assert out["conditions"]["C_material_primary_relative"] is False
    assert out["refuses"] is False, "C alone must be able to stop a refusal"


def test_condition_D_alone_decides_when_A_B_C_all_hold():
    """D isolated: a non-positive claimed effect makes the ratio in C meaningless."""
    out = _evaluate(DEMONSTRABLE_SERIES, mean_delta=0.0)["decided"]
    assert out["conditions"]["A_served_cell_audit_passes"] is True
    assert out["conditions"]["B_demonstrable"] is True
    assert out["conditions"]["D_claimed_effect_well_defined"] is False
    assert out["refuses"] is False


def test_condition_A_FAILS_CLOSED_to_the_raw_clause_never_fail_open():
    """⭐ A isolated, and the direction matters more than the value. With B FALSE (NF-W7f's own
    series) the relaxed clause would NOT refuse — but with the audit failing there is no licence to
    relax, so the RAW verdict must govern and the clause must REFUSE.

    Writing this as `refuses = audit_ok and …` reads like a precondition and is in fact fail-OPEN:
    a broken or expired audit would silently REMOVE the gate. That is the opposite of what condition
    A exists to do (prereg §1.3)."""
    relaxed = _evaluate(W7F_SERIES, audit_passes=True)["decided"]
    assert relaxed["refuses"] is False and relaxed["fails_closed_to_raw"] is False

    closed = _evaluate(W7F_SERIES, audit_passes=False)["decided"]
    assert closed["fails_closed_to_raw"] is True
    assert closed["refuses"] is True, (
        "with the audit failing the clause must revert to the RAW 0.0 tolerance and REFUSE — "
        "returning False here would be fail-OPEN")


def test_fail_closed_still_tracks_the_raw_verdict_when_the_raw_clause_would_pass():
    """Fail-closed means "the raw clause governs", not "always refuse" — an improvement must still
    pass even with the audit down."""
    improved = [-0.01] * 8
    out = R.evaluate_component_clause(series=improved, per_leg=_per_leg(-0.01), sel=_sel(),
                                      audit=_audit(False))["decided"]
    assert out["fails_closed_to_raw"] is True
    assert out["refuses"] is False


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. The band read (prereg §2.2) — the NF-W7i lesson
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_the_band_state_is_three_way_and_never_says_power_limited():
    """⛔ A band decision is not a power verdict. NF-W7i had to hand-correct `cv_power` for exactly
    this, so the states must be the band vocabulary and must never leak `POWER_LIMITED`."""
    assert set(CC.BAND_STATES) == {"MEASURED_IMMATERIAL", "MEASURED_MATERIAL", "UNDECIDED_MAGNITUDE"}
    assert "POWER_LIMITED" not in CC.BAND_STATES
    for series in (W7F_SERIES, DEMONSTRABLE_SERIES):
        md = _evaluate(series)["decided"]["materiality_detail"]
        assert md["band_state"] in CC.BAND_STATES
        assert md["band_state"] != "POWER_LIMITED"


def test_the_band_read_reports_the_ci_in_band_units_on_both_sides():
    md = _evaluate(W7F_SERIES)["decided"]["materiality_detail"]
    lo, hi = md["ci95_in_band_units"]
    assert lo is not None and hi is not None and lo < hi
    assert md["point_estimate_in_band_units"] is not None


def test_a_ci_straddling_the_band_is_undecided_not_immaterial():
    """The dangerous direction: a wide CI must never be read as "we measured it small"."""
    md = _evaluate(W7F_SERIES)["decided"]["materiality_detail"]
    lo, hi = md["ci95_in_band_units"]
    assert lo < 1.0 < hi
    assert md["band_state"] == "UNDECIDED_MAGNITUDE"


def test_both_units_are_reported_and_the_verdict_states_whether_they_agree():
    """prereg §2.1 — declared in advance so a later reader cannot suspect the unit was picked to fit."""
    md = _evaluate(W7F_SERIES)["decided"]["materiality_detail"]
    assert "sensitivity_absolute" in md and "units_agree" in md
    assert md["units_agree"] is True, "on NF-W7f's numbers both units call it material"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4. The significance instrument is the harness's OWN, by identity
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_the_demonstrable_half_uses_the_harness_s_own_paired_test_by_identity():
    """Reusing `beats_foil`'s instrument is what stops a NEW test being chosen to suit the answer."""
    from quant_sports_intel_models.football.nfl.fantasy import nf1_1_model as M14
    import numpy as np
    expected = M14.onesided_paired_pvalue(np.asarray(W7F_SERIES, float))
    assert _evaluate(W7F_SERIES)["decided"]["demonstrable_detail"]["p_one_sided"] == expected


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 5. The served-cell audit is TWO-SIDED and cannot pass vacuously
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_the_audit_raises_when_a_positive_control_comes_back_empty(monkeypatch):
    """⭐ NF1.7 (a). A walker that resolves nothing returns an empty hit set for EVERY seed, so a
    PASS would be indistinguishable from a broken audit."""
    monkeypatch.setattr(CC, "FORBIDDEN_SUBSTRINGS", ("a_substring_that_matches_no_module",))
    with pytest.raises(R.InvalidRun, match="POSITIVE CONTROL EMPTY"):
        R.served_cell_audit()


def test_the_audit_raises_on_an_unresolvable_seed(monkeypatch):
    """A renamed/moved/mistyped seed yields an EMPTY closure, which has no hits — i.e. it would read
    as a clean PASS. UNEVALUABLE is never a pass."""
    monkeypatch.setattr(CC, "SERVING_PLANE_SEEDS",
                        CC.SERVING_PLANE_SEEDS + ("app.backend.this_module_does_not_exist",))
    with pytest.raises(R.InvalidRun, match="does not resolve"):
        R.served_cell_audit()


def test_the_audit_raises_when_the_repo_root_is_wrong(tmp_path):
    with pytest.raises(R.InvalidRun, match="no 'pyproject.toml'"):
        R.served_cell_audit(root=tmp_path)


def test_the_positive_controls_really_do_consume_the_per_stat_cells():
    """Non-vacuity of the control itself: these must be KNOWN consumers, or the control proves
    nothing about the walker."""
    audit = R.served_cell_audit()
    for seed, detail in audit["positive_controls"].items():
        assert detail["n_hits"] > 0, seed


def test_the_served_plane_does_not_consume_the_per_stat_cells():
    """The measured answer to the question NF-W7f §12.5b(3) left open."""
    audit = R.served_cell_audit()
    assert audit["passes"] is True
    for seed, detail in audit["seeds"].items():
        assert detail["hits"] == [], f"{seed} consumes the per-stat cells: {detail['hits']}"


def test_the_audit_also_scans_for_artifact_path_readers_not_only_imports():
    """⭐ INC-27, facing the read side. An import closure cannot see a consumer that reads the W6d
    artifact BY FILENAME with no import edge, so the audit carries a second leg."""
    audit = R.served_cell_audit()
    assert "artifact_tokens" in audit and audit["artifact_tokens"]
    for seed, detail in audit["seeds"].items():
        assert "artifact_hits" in detail, seed
        assert detail["artifact_hits"] == [], f"{seed} reads the W6d artifact by path"


def test_the_artifact_scan_has_its_own_positive_control_and_raises_when_vacuous(monkeypatch):
    """A token that matches nothing makes the scan silently clean for every seed — so the leg needs
    its own control, exactly as the import leg does (NF1.7 (a))."""
    assert R.served_cell_audit()["artifact_scan_control"]["n_hits"] > 0
    monkeypatch.setattr(CC, "ARTIFACT_TOKENS", ("a_token_no_module_contains",))
    with pytest.raises(R.InvalidRun, match="ARTIFACT-SCAN CONTROL EMPTY"):
        R.served_cell_audit()


def test_an_artifact_path_reader_on_the_serving_plane_fails_the_audit(monkeypatch):
    """The two-sided half: the artifact leg must be ABLE to fail, or a clean result proves nothing.
    Pointing a token at something the serving plane really does contain must turn the audit FAIL."""
    monkeypatch.setattr(CC, "ARTIFACT_TOKENS", CC.ARTIFACT_TOKENS + ("proj_pass_yds",))
    audit = R.served_cell_audit()
    assert audit["passes"] is False
    assert any(v["artifact_hits"] for v in audit["seeds"].values())


def test_the_serving_plane_seed_set_covers_producer_exporter_api_and_scorer():
    """A seed set that omits the thing that PRODUCES the stat line would audit the wrong plane."""
    seeds = " ".join(CC.SERVING_PLANE_SEEDS)
    for required in ("export_draft_board_json", "season_projection", "app.backend.main",
                     "app.backend.routers.fantasy", "fantasy_engine.scoring"):
        assert required in seeds


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 6. The reproduction pin (prereg §3)
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_the_pin_reproduces_nf_w7f_exactly():
    pinned = R.load_and_pin(RECORD)
    assert pinned["sel"]["winner"] == CC.W7F_WINNER
    assert sorted(k for k, v in pinned["gates"].items() if not v) == sorted(CC.W7F_FAILING_CLAUSES)


@pytest.mark.parametrize("mutate,expect", [
    (lambda d: d.__setitem__("smoke", True), "SMOKE"),
    (lambda d: d.__setitem__("n_folds", 7), "n_folds"),
    (lambda d: d["selections"]["QB"].__setitem__("winner", "zm_over"), "winner/foil"),
    (lambda d: d["selections"]["QB"]["per_leg_detail"].__setitem__("relative_change", 0.5),
     "reproduction pin"),
    (lambda d: d["gates"]["QB"]["checks"].__setitem__("pbo_ok", False), "failing clauses"),
])
def test_the_pin_raises_on_any_drift_from_the_object_nf_w7f_scored(tmp_path, mutate, expect):
    doc = json.loads(RECORD.read_text())
    mutate(doc)
    p = tmp_path / "mutated.json"
    p.write_text(json.dumps(doc))
    with pytest.raises(R.InvalidRun, match=expect):
        R.load_and_pin(p)


def test_the_pin_distinguishes_the_pooled_ratio_from_the_mean_of_fold_ratios():
    """⭐ They are NOT the same statistic (NF1.8): +0.3866% is a ratio of SUMS, +0.3748% is the mean
    of per-fold ratios. Pinning the series against the pooled figure is what surfaced it."""
    assert CC.W7F_PINS["per_leg_relative_change"] != CC.W7F_PINS[
        "per_leg_relative_change_winner_by_fold_mean"]
    pinned = R.load_and_pin(RECORD)
    import numpy as np
    assert float(np.mean(pinned["series"])) == pytest.approx(
        CC.W7F_PINS["per_leg_relative_change_winner_by_fold_mean"], abs=1e-6)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 7. The re-scored gate + the certification bar (prereg §4)
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_certification_requires_the_FULL_gate_the_bar_wr_and_te_actually_cleared():
    """⛔ A *PIT + component + beats incumbent* reading omits `dsr_ok`; adopting it after seeing
    `dsr_ok` fail is the E2.1-r inversion and would certify QB on a bar WR/TE were never held to."""
    assert CC.CERTIFICATION_REQUIRES_FULL_GATE is True
    pinned = R.load_and_pin(RECORD)
    clause = R.evaluate_component_clause(series=pinned["series"], per_leg=pinned["per_leg"],
                                         sel=pinned["sel"], audit=R.served_cell_audit())
    out = R.rescore(pinned, clause)
    assert out["failing_clauses"] == ["dsr_ok"]
    assert out["full_gate_green"] is False
    assert out["certified_for_nf_w8"] is False, (
        "QB clears PIT 8/8, beats the incumbent, and passes the decided component clause — and is "
        "still NOT certified, because `dsr_ok` is an independent refusal")


def test_a_fully_green_gate_would_certify_so_the_bar_is_not_unreachable():
    """The two-sided half: the certification path must be REACHABLE, or the test above passes on
    nothing (NF1.7 (a))."""
    pinned = copy.deepcopy(R.load_and_pin(RECORD))
    pinned["gates"]["dsr_ok"] = True
    clause = R.evaluate_component_clause(series=pinned["series"], per_leg=pinned["per_leg"],
                                         sel=pinned["sel"], audit=R.served_cell_audit())
    out = R.rescore(pinned, clause)
    assert out["full_gate_green"] is True
    assert out["certified_for_nf_w8"] is True and out["verdict"] == "QB_CERTIFIED"


def test_a_remaining_anchor_failure_stays_constraint_refused_with_no_data_trigger():
    """NF-D18 — an anchor half is not rescuable by data, so it BINDS and publishes no trigger."""
    pinned = copy.deepcopy(R.load_and_pin(RECORD))
    pinned["gates"]["cap_was_lifted"] = False
    clause = R.evaluate_component_clause(series=pinned["series"], per_leg=pinned["per_leg"],
                                         sel=pinned["sel"], audit=R.served_cell_audit())
    out = R.rescore(pinned, clause)
    assert out["null_state"]["state"] == "CONSTRAINT_REFUSED"
    assert out["null_state"]["binding_half"] == "anchor"
    assert out["null_state"]["retest_trigger"] is None


def test_the_purely_statistical_refusal_is_classified_at_the_declared_field_size():
    """MH2.7 — `declared_field_size` is what stops the instrument prescribing the retired post-hoc
    field, and the machine flag is what a caller reads, never the prose."""
    assert CC.W7F_DECLARED_FIELD_SIZE == 4
    pinned = R.load_and_pin(RECORD)
    clause = R.evaluate_component_clause(series=pinned["series"], per_leg=pinned["per_leg"],
                                         sel=pinned["sel"], audit=R.served_cell_audit())
    ns = R.rescore(pinned, clause)["null_state"]
    assert ns["state"] == "DSR_UNREACHABLE"
    assert "field_remedy_admissible" in ns
    assert ns["field_remedy_admissible"] is None, (
        "None means field size is NO LEVER AT ALL here — not 'unset'")
    assert ns["field_shrink_flag"]["status"].startswith("SUSPECT")


def test_the_null_state_publishes_no_more_seasons_trigger():
    """⛔ NF-D18 / MH2 — the misleading direction. `n` enters DSR only through `sqrt(n-1)`."""
    pinned = R.load_and_pin(RECORD)
    clause = R.evaluate_component_clause(series=pinned["series"], per_leg=pinned["per_leg"],
                                         sel=pinned["sel"], audit=R.served_cell_audit())
    trigger = (R.rescore(pinned, clause)["null_state"].get("retest_trigger") or "")
    assert "more seasons" not in trigger.lower()
    assert "field size is NOT a lever" in trigger


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 8. The committed artifact
# ══════════════════════════════════════════════════════════════════════════════════════════════

@pytest.mark.skipif(not ARTIFACT.exists(), reason="artifact not built")
def test_the_committed_artifact_records_the_decision_and_its_deploy_hold():
    doc = json.loads(ARTIFACT.read_text())
    assert doc["story"] == "NF-W7j"
    assert doc["best_alpha"] == 0 and doc["deploy_held"] is True and doc["refits_nothing"] is True
    assert doc["served_cell_audit"]["passes"] is True
    assert doc["component_clause"]["raw"]["refuses"] is True
    assert doc["component_clause"]["decided"]["refuses"] is False
    assert doc["rescored"]["failing_clauses"] == ["dsr_ok"]
    assert doc["rescored"]["certified_for_nf_w8"] is False
    assert doc["rescored"]["null_state"]["state"] == "DSR_UNREACHABLE"


@pytest.mark.skipif(not ARTIFACT.exists(), reason="artifact not built")
def test_the_report_states_that_the_decision_cannot_certify_qb_on_its_own():
    md = (ABL / "nf_w7j_component_clause.md").read_text()
    assert "cannot certify QB on its own" in md
    assert "dsr_ok" in md
    # the raw clause must remain visible beside the decided one (NF-D20)
    assert CC.RAW_CLAUSE in md and CC.DECIDED_CLAUSE.split("_not_")[0] in md
