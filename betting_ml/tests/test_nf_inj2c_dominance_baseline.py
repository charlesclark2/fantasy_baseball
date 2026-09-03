"""NF-INJ2c nodes 3a/3b/3c — guards for the margin rule, the capture-pin, and the fold ruling.

⛔ These certify no verdict. They pin (a) that the margin CONSTRUCTION RULE was committed and says
what the runner reads, (b) that the D3 capture-pin actually refuses a re-pull rather than warning,
(c) that the dominance verdicts are computed from the rule's bands and never score an unevaluable
measure as a pass, and (d) the node-3c fold ruling and its licensing measurements.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

from quant_sports_intel_models.football.nfl.fantasy import (
    run_nf_inj2c_dominance_baseline as DB,
)

_REPO = Path(__file__).resolve().parents[2]
_ART = _REPO / "quant_sports_intel_models/football/nfl/fantasy/ablation_results"
_RULE = _ART / "nf_inj2c_margin_construction_rule.md"
_FOLD = _ART / "nf_inj2c_fold_fidelity_finding.md"
_SPEC = _REPO / "plan_specs/nfl_fantasy/nf-inj2c.yaml"


def _flat(path: Path) -> str:
    """Whitespace-normalised text. A prose guard that matches a SINGLE-LINE substring goes red the
    moment the sentence it pins is re-wrapped — which is a formatting change, not a meaning change,
    and a guard that fires on one teaches people to weaken it."""
    return re.sub(r"\s+", " ", path.read_text())


# ══════════════════════════════════════════════════════════════════════════════════════════════
# node 3a — the margin construction rule exists, is committed, and OWNS the bands
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_margin_rule_is_committed_before_the_baseline_runner_can_quote_it():
    assert _RULE.exists(), (
        "the margin CONSTRUCTION RULE must be committed BEFORE the re-measure — it is the whole "
        "protection against margins reverse-engineered from the numbers the re-measure shows")


def test_every_band_the_runner_applies_is_named_in_the_rule():
    """⭐ The runner READS bands; it must not define one. A band in code that the rule does not name
    is exactly the margin-set-after-the-fact this sequencing exists to prevent."""
    txt = _flat(_RULE)
    for label, band in (("M3", DB.M3_TIE_BAND), ("M4", DB.M4_TIE_BAND)):
        assert f"| {label} |" in txt, f"{label} is not a declared measure in the rule"
        assert str(band) in txt, (
            f"the runner applies a {label} tie band of {band} that the committed rule does not name")


def test_the_rule_forbids_a_band_derived_from_an_observed_gap():
    txt = _flat(_RULE)
    assert "not a threshold chosen to reach a verdict" in txt
    assert "no band may be derived from an observed arm-vs-incumbent gap" in txt


def test_the_rule_carries_the_pms_null_branch_verbatim():
    """PM ruling 3's branch is what makes it safe to see the arm's numbers before the prereg."""
    assert "that is a NULL, not a margin to adjust" in _flat(_RULE)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# node 3b — the D3 capture-pin REFUSES, and refuses for the right reasons
# ══════════════════════════════════════════════════════════════════════════════════════════════
@pytest.fixture
def staged(tmp_path, monkeypatch):
    served = tmp_path / "served_projections_2026.json"
    served.write_text(json.dumps({"generated_at": "2026-08-31T12:00:00Z",
                                  "players": [{"id": "x", "fpPpr": 10.0, "g": 17.0}]}))
    monkeypatch.setattr(DB, "_SERVED_JSON", served)
    monkeypatch.setattr(DB, "_CAPTURE_STAMP", tmp_path / "nf_inj2c_capture.json")
    # ⭐ RE-ANCHORED 2026-09-01: `capture()` now enforces the MARKET-VINTAGE precondition, so the
    # fixture stages a MATCHING manifest + local vintage. These tests are about the BOARD-BYTES
    # pin, and a fixture that failed the market check would make them pass for the wrong reason —
    # ⛔ the precondition is satisfied here, never disabled (its own two-sided guards live below).
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"adp_as_of": "2026-08-31", "ecr_as_of": "2026-08-31"}))
    monkeypatch.setattr(DB, "_MANIFEST_JSON", manifest)
    from quant_sports_intel_models.football.nfl.fantasy import market_freshness as _MF
    monkeypatch.setattr(_MF, "market_as_of", lambda season, **kw: {
        "adp": {"source": "ffc", "as_of": "2026-08-31"},
        "ecr": {"source": "fantasypros", "as_of": "2026-08-31", "label": "8/31"}})
    return served


def test_a_missing_capture_refuses_and_names_the_staging_command(staged, monkeypatch):
    with pytest.raises(SystemExit) as e:
        DB.assert_capture_intact()
    msg = str(e.value)
    assert "aws s3 cp s3://credence-prod-s3-api-cache" in msg, (
        "a refusal an operator cannot act on is a worse refusal (the NF-INFRA1 cure)")
    assert "--capture" in msg


def test_a_capture_then_an_unchanged_board_passes(staged):
    stamp = DB.capture()
    again = DB.assert_capture_intact()
    assert again["sha256"] == stamp["sha256"] == hashlib.sha256(staged.read_bytes()).hexdigest()


def test_a_REPULLED_board_is_refused_which_is_the_whole_point_of_D3(staged):
    """⭐ The two-sided half. A capture-pin that only ever passes is not a pin (NF1.7 (a))."""
    DB.capture()
    staged.write_text(json.dumps({"generated_at": "2026-08-31T19:00:00Z",
                                  "players": [{"id": "x", "fpPpr": 10.4, "g": 17.0}]}))
    with pytest.raises(SystemExit) as e:
        DB.assert_capture_intact()
    assert "CHANGED since it was captured" in str(e.value)
    assert "40.58" in str(e.value), "the refusal should carry the measurement that motivates it"


def test_recapturing_mid_study_is_refused_without_an_explicit_flag(staged):
    DB.capture()
    with pytest.raises(SystemExit) as e:
        DB.capture()
    assert "--recapture" in str(e.value)
    DB.capture(force=True)          # the explicit start-over path still works


# ══════════════════════════════════════════════════════════════════════════════════════════════
# node 3b — the dominance verdicts
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _arm(*, attributable, worst_over, giveback):
    return {
        "coherence_violating_players_attributable": attributable,
        "coherence_violating_players": attributable,
        "coherence_by_position": {}, "clamp_saturation_high": 0, "clamp_saturation_low": 0,
        "injury_giveback": {"giveback_pct": giveback},
        "worst_violations": ([] if worst_over is None
                             else [{"implied_per_game": worst_over, "max_ever_per_game": 1.0}]),
    }


def test_an_arm_better_on_every_board_measure_reads_IMPROVES():
    app = {"arms": {"incumbent": _arm(attributable=9, worst_over=2.51, giveback=82.70),
                    "stratified": _arm(attributable=7, worst_over=1.85, giveback=27.85)}}
    r = DB.dominance_table(app)["arms"]["stratified"]
    assert (r["M2_verdict"], r["M3_verdict"], r["M4_verdict"]) == ("IMPROVES",) * 3


def test_a_single_regression_is_reported_as_one_and_not_averaged_away():
    """Strict dominance is per-measure: one regression is the verdict, ⛔ not a net score."""
    app = {"arms": {"incumbent": _arm(attributable=9, worst_over=2.51, giveback=82.70),
                    "arm": _arm(attributable=11, worst_over=1.85, giveback=27.85)}}
    r = DB.dominance_table(app)["arms"]["arm"]
    assert r["M2_verdict"] == "REGRESSES"
    assert r["M3_verdict"] == "IMPROVES"       # ⛔ and it does NOT rescue M2


def test_a_measure_with_no_value_is_UNEVALUABLE_and_never_a_pass():
    app = {"arms": {"incumbent": _arm(attributable=9, worst_over=2.51, giveback=82.70),
                    "clean": _arm(attributable=0, worst_over=None, giveback=27.85)}}
    r = DB.dominance_table(app)["arms"]["clean"]
    assert r["M3_verdict"] == "UNEVALUABLE", (
        "an arm with no violation has no worst-breach to compare; scoring that as IMPROVES would "
        "read a missing measurement as a win (NF1.7 (a))")


def test_the_giveback_measure_does_not_reward_over_discounting():
    """M4 = max(pct, 0) — the rule §3(a) judgment, pinned so it cannot drift back to the signed
    value, which would let an arm bank credit for a DIFFERENT defect."""
    assert DB._giveback_measure(-16.31) == 0.0
    assert DB._giveback_measure(27.85) == pytest.approx(27.85)
    app = {"arms": {"incumbent": _arm(attributable=9, worst_over=2.0, giveback=82.70),
                    "over": _arm(attributable=9, worst_over=2.0, giveback=-16.31),
                    "zero": _arm(attributable=9, worst_over=2.0, giveback=0.0)}}
    d = DB.dominance_table(app)["arms"]
    assert d["over"]["M4_giveback_measure"] == d["zero"]["M4_giveback_measure"]
    assert d["over"]["M4_giveback_signed"] == -16.31    # the signed value is still reported


def test_the_fold_measures_are_named_unevaluated_rather_than_omitted():
    app = {"arms": {"incumbent": _arm(attributable=9, worst_over=2.0, giveback=1.0)}}
    r = DB.dominance_table(app)["arms"]["incumbent"]
    assert "UNEVALUATED" in r["M1_M5_M6"], (
        "a dominance table silently missing three of its six measures reads as a complete one")


def test_the_attribution_control_arm_cannot_be_dropped_from_a_run():
    import inspect
    src = inspect.getsource(DB.main)
    assert 'if "incumbent" not in arms or "mvp1_null" not in arms:' in src


# ══════════════════════════════════════════════════════════════════════════════════════════════
# node 3c — the fold ruling and the measurements licensing it
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_fold_finding_is_committed_and_states_the_ruling_either_way():
    assert _FOLD.exists()
    txt = _flat(_FOLD)
    assert "2018 IS NOT ADMITTED" in txt
    assert "state the finding either way" in txt


def test_the_empty_pool_arithmetic_the_finding_rests_on_still_holds():
    """⭐ The finding's first leg is arithmetic on the SHIPPED `base_from`, so it is checkable here
    rather than only in prose — if `build_season_projection`'s window ever changes, this goes red."""
    def base_seasons(projection_season, base_from=2017):
        return [b for b in range(base_from, projection_season - 1) if b + 1 < projection_season]
    assert base_seasons(2018) == [], "a 2018 fold would no longer be empty — re-open the ruling"
    assert base_seasons(2019) == [2017]
    assert base_seasons(2025) == [2017, 2018, 2019, 2020, 2021, 2022, 2023]


def test_the_finding_records_that_the_eighth_fold_moves_the_gate_the_WRONG_way():
    txt = _flat(_FOLD)
    assert "2.0101" in txt and "1.6418" in txt
    assert "−0.3682" in txt, "the Sharpe DELTA is the statistic the finding turns on"
    assert "DILUTES" in txt


def test_the_finding_refuses_to_pick_the_declared_field():
    """A field chosen by which one clears is the selection bias DSR exists to deflate (MH2.2)."""
    txt = _flat(_FOLD)
    assert "no per-candidate-family DSR has been computed" in txt


def test_the_spec_carries_the_pm_rescope():
    txt = _flat(_SPEC)
    assert "PM RE-SCOPE RULING 2026-08-31" in txt
    assert "STRICT-DOMINANCE disposition, alone" in txt


def test_the_spec_records_the_field_declaration_and_who_made_it():
    """⭐ RE-ANCHORED (2026-09-01), not deleted. This guard was written to pin the HOLD; the PM has
    since RULED, so it now pins the same invariant on the other side of that ruling — the field
    declaration lives in the SPEC and is attributed to the PM.

    The invariant is unchanged and is the reason the guard exists: a question that lives only in a
    handoff message is one a later session answers by not noticing it, and the thing it would
    answer by accident (which field the deflation gates run over) is precisely the selection bias
    DSR exists to deflate (MH2.2). ⛔ Weakening or deleting a guard because the world moved past
    it is what re-anchoring exists to prevent (MH2.7)."""
    txt = _flat(_SPEC)
    assert "PM ruling (2026-09-01, NF-INJ2c prereg)" in txt, (
        "the field declaration is no longer attributed to the PM in the spec")
    assert "the deflation gates' BINDING field is NF-INJ2c's own coherent family" in txt
    assert "per-candidate-family DSR was computed" in txt, (
        "the record must still state that no per-family DSR preceded the declaration (NF-INJ3b-M)")
    assert "HELD FOR A PM RULING — THE DSR FIELD DECLARATION" not in txt, (
        "a stale HELD marker survives the ruling — the spec would misreport the story's state")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# THE MARKET-VINTAGE PRECONDITION (PM ruling 2026-09-01 (a)) — guarded BOTH ways
#
# Node 3b run 1 burned a full >2-min build and returned VOID because the local ECR cache was six
# days older than the served board's. The precondition converts that into an up-front refusal. A
# guard that only proved it REFUSES would be half a guard: a check that refuses everything is as
# useless as one that refuses nothing, so the matched case is asserted to PASS just as hard.
# ══════════════════════════════════════════════════════════════════════════════════════════════
import json as _json  # noqa: E402
import sys as _sys  # noqa: E402

import pytest as _pytest  # noqa: E402

_sys.path.insert(0, str(_REPO))
from quant_sports_intel_models.football.nfl.fantasy import (  # noqa: E402
    run_nf_inj2c_dominance_baseline as _B,
)


def _stage_manifest(tmp_path, adp: str | None, ecr: str | None, monkeypatch) -> None:
    """Point the module at a manifest declaring the SERVED vintage, without touching real files."""
    man = tmp_path / "manifest.json"
    payload: dict = {"generated_at": "2026-08-31T14:18:54Z"}
    if adp is not None:
        payload["adp_as_of"] = adp
    if ecr is not None:
        payload["ecr_as_of"] = ecr
    man.write_text(_json.dumps(payload))
    monkeypatch.setattr(_B, "_MANIFEST_JSON", man)


def _stub_local(monkeypatch, adp: str | None, ecr: str | None) -> None:
    """Stub the LOCAL cache vintages that `market_as_of` reads off disk."""
    from quant_sports_intel_models.football.nfl.fantasy import market_freshness as MF

    def _fake(season, **kw):
        return {
            "adp": None if adp is None else {"source": "ffc", "as_of": adp},
            "ecr": None if ecr is None else {"source": "fantasypros", "as_of": ecr, "label": "x"},
        }

    monkeypatch.setattr(MF, "market_as_of", _fake)


def test_a_matched_market_vintage_PASSES(tmp_path, monkeypatch) -> None:
    """⭐ The half that is easy to leave untested. A precondition that refuses everything blocks the
    study exactly as effectively as the defect it replaced."""
    _stage_manifest(tmp_path, adp="2026-08-31", ecr="2026-08-31", monkeypatch=monkeypatch)
    _stub_local(monkeypatch, adp="2026-08-31", ecr="2026-08-31")
    got = _B.assert_market_vintage_matches()
    assert got["ecr"]["served_as_of"] == got["ecr"]["local_as_of"] == "2026-08-31"


def test_the_run_1_mismatch_REFUSES_and_names_input_both_vintages_and_the_fix(
        tmp_path, monkeypatch) -> None:
    """The exact shape that cost run 1: ADP matched, ECR six days stale."""
    _stage_manifest(tmp_path, adp="2026-08-31", ecr="2026-08-31", monkeypatch=monkeypatch)
    _stub_local(monkeypatch, adp="2026-08-31", ecr="2026-08-25")
    with _pytest.raises(SystemExit) as ei:
        _B.assert_market_vintage_matches()
    msg = str(ei.value)
    assert "ECR" in msg, "the refusal must NAME the mismatched input"
    assert "2026-08-31" in msg and "2026-08-25" in msg, "it must carry BOTH vintages"
    assert "run_ecr_ingest" in msg and "--refresh" in msg, (
        "a refusal that does not name its own remedy has converted nothing — that is the whole "
        "point of the precondition (PM ruling 2026-09-01 (a))")
    assert "ADP" not in msg.split("WHY:")[0], (
        "ADP matched here and must NOT be reported as a problem — a refusal that blames every "
        "input tells the operator nothing about which one to fix")


def test_an_unreadable_local_vintage_REFUSES_rather_than_passing(tmp_path, monkeypatch) -> None:
    """NF1.7 (a): a check that cannot be evaluated is never scored as a pass."""
    _stage_manifest(tmp_path, adp="2026-08-31", ecr="2026-08-31", monkeypatch=monkeypatch)
    _stub_local(monkeypatch, adp="2026-08-31", ecr=None)
    with _pytest.raises(SystemExit) as ei:
        _B.assert_market_vintage_matches()
    assert "UNREADABLE OR ABSENT" in str(ei.value)


def test_a_manifest_without_the_vintage_REFUSES_rather_than_passing(
        tmp_path, monkeypatch) -> None:
    """A served board that does not state its vintage makes the precondition UNEVALUABLE, which is
    a refusal — ⛔ never a silent pass on a board whose inputs are unknown."""
    _stage_manifest(tmp_path, adp="2026-08-31", ecr=None, monkeypatch=monkeypatch)
    _stub_local(monkeypatch, adp="2026-08-31", ecr="2026-08-31")
    with _pytest.raises(SystemExit) as ei:
        _B.assert_market_vintage_matches()
    assert "CANNOT be evaluated" in str(ei.value)


def test_a_missing_manifest_REFUSES_with_the_staging_command(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(_B, "_MANIFEST_JSON", tmp_path / "absent.json")
    with _pytest.raises(SystemExit) as ei:
        _B.market_vintage()
    assert "aws s3 cp" in str(ei.value) and "manifest.json" in str(ei.value)


def test_capture_enforces_the_precondition_so_it_cannot_be_bypassed() -> None:
    """A precondition the capture path does not CALL is documentation, not a gate (NF-C0e:
    wired is not invoked)."""
    import inspect

    src = inspect.getsource(_B.capture)
    # RE-ANCHORED at D3 (2026-09-03): the precondition widened from the market DAY check to every
    # vintage the manifest publishes. `assert_vintages_match` CALLS the market check, so this is
    # strictly stronger than the clause it replaces (MH2.7 — re-anchor, never weaken).
    assert "assert_vintages_match(" in src, (
        "`capture` no longer enforces the vintage precondition — it would stamp a capture that "
        "cannot be pinned")


def test_the_run_path_rechecks_that_the_caches_did_not_move_after_the_capture() -> None:
    """⭐ The caches are ordinary files a later refresh can move underneath a VALID capture. The
    board's sha256 does not constrain them, so an unchanged board is NOT evidence the ordering
    inputs are unchanged."""
    import inspect

    src = inspect.getsource(_B.assert_capture_intact)
    assert "assert_vintages_match(" in src            # RE-ANCHORED at D3; see `capture` above
    assert "market_vintage" in src and "--recapture" in src


def test_every_declared_market_input_carries_a_real_refresh_command() -> None:
    """The registry is the refusal's remedy. An entry naming a command that does not exist would
    send an operator at a script that is not there."""
    assert _B._MARKET_INPUTS, "the market-input registry is empty — the precondition checks nothing"
    for name, manifest_key, cmd in _B._MARKET_INPUTS:
        assert manifest_key.endswith("_as_of"), f"{name}: not a manifest vintage key"
        mod = cmd.split("run_")[1].split(" ")[0]
        assert (_REPO / "quant_sports_intel_models" / "football" / "nfl" / "fantasy"
                / f"run_{mod}.py").exists(), f"{name}: refresh command names a missing module"
        assert "--refresh" in cmd, f"{name}: the command would not actually refresh anything"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# D3 (PM ruling 2026-09-03) — the precondition covers EVERY vintage the manifest publishes
# ══════════════════════════════════════════════════════════════════════════════════════════════
# The market DAY check caught NF-INJ2c run 1 and was structurally blind to runs 3 and 4 (the marts
# two days stale; the feature pool missing 5 registered columns) — each found only after a full
# build. These guards are two-sided by construction: a MATCHED surface must PASS, or a refusal
# that fires on everything would block the study rather than protect it.

_FULL_FRESHNESS = {
    "adp": {"source": "ffc", "format": "ppr", "teams": 12, "as_of": "2026-08-31",
            "window_start": "2026-08-24", "window_end": "2026-08-31", "drafts": 8161},
    "ecr": {"source": "fantasypros", "scoring": "PPR", "as_of": "2026-08-31",
            "label": "8/31", "experts": 99},
    "input_vintage": {"depth_chart_as_of": "2026-08-31 14:44:50",
                      "sleeper_status_as_of": "2026-08-31T13:30:16.880706+00:00"},
}
#: 05:36:35Z on 2026-08-31 — BEFORE the board's `generated_at`, i.e. a consensus it could have read.
_ECR_TS_BEFORE_BOARD = 1788154595


@pytest.fixture()
def full_surface(tmp_path, monkeypatch):
    """A manifest publishing the WHOLE freshness surface, with local inputs that match it."""
    art = tmp_path / "artifacts"
    (art / "adp_cache").mkdir(parents=True)
    (art / "ecr_cache").mkdir(parents=True)
    (art / "adp_cache" / "ffc_ppr_12_2026.json").write_text(json.dumps(
        {"meta": {"total_drafts": 8161, "start_date": "2026-08-24", "end_date": "2026-08-31"}}))
    (art / "ecr_cache" / "fp_ecr_PPR_2026.json").write_text(json.dumps(
        {"total_experts": 99, "last_updated": "8/31", "last_updated_ts": _ECR_TS_BEFORE_BOARD}))
    monkeypatch.setattr(DB.RB, "_ART", art)

    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"generated_at": "2026-08-31T12:00:00+00:00",
                                    "adp_as_of": "2026-08-31", "ecr_as_of": "2026-08-31",
                                    "freshness": json.loads(json.dumps(_FULL_FRESHNESS))}))
    monkeypatch.setattr(DB, "_MANIFEST_JSON", manifest)

    from quant_sports_intel_models.football.nfl.fantasy import market_freshness as _MF
    monkeypatch.setattr(_MF, "market_as_of", lambda season, **kw: {
        "adp": {"source": "ffc", "as_of": "2026-08-31"},
        "ecr": {"source": "fantasypros", "as_of": "2026-08-31", "label": "8/31"}})
    monkeypatch.setattr(DB.N15, "read_input_vintage",
                        lambda con, season, schema: dict(_FULL_FRESHNESS["input_vintage"]))
    return manifest


def _edit_manifest(manifest, **freshness_patch):
    doc = json.loads(manifest.read_text())
    for section, patch in freshness_patch.items():
        doc["freshness"][section].update(patch)
    manifest.write_text(json.dumps(doc))


def test_a_matched_full_vintage_surface_PASSES(full_surface):
    """The two-sided half: a refusal that fires on a MATCHED surface blocks the study."""
    out = DB.assert_vintages_match(con=object())
    assert out["input_vintage"]["depth_chart_as_of"]["served"] == "2026-08-31 14:44:50"
    assert out["fingerprint"]["adp"]["drafts"]["served"] == 8161


def test_a_moved_adp_window_REFUSES_even_though_the_DAY_still_matches(full_surface):
    """`as_of` alone cannot separate two same-day pulls; the window and draft count can."""
    _edit_manifest(full_surface, adp={"drafts": 8400, "window_start": "2026-08-25"})
    with pytest.raises(SystemExit) as e:
        DB.assert_vintages_match(con=object())
    msg = str(e.value)
    assert "ADP.drafts: served 8400, local 8161" in msg
    assert "ADP.window_start: served 2026-08-25, local 2026-08-24" in msg
    assert "run_adp_ingest" in msg, "a refusal must carry its own remedy"


def test_a_changed_ecr_expert_count_REFUSES_even_though_the_DAY_still_matches(full_surface):
    _edit_manifest(full_surface, ecr={"experts": 101})
    with pytest.raises(SystemExit) as e:
        DB.assert_vintages_match(con=object())
    msg = str(e.value)
    assert "ECR.experts: served 101, local 99" in msg
    assert "run_ecr_ingest" in msg


def test_an_ecr_consensus_published_AFTER_the_board_REFUSES(full_surface, tmp_path, monkeypatch):
    """One-sided by necessity: the manifest publishes no `last_updated_ts`, so there is no served
    twin to equate. What is sound — and what settled the real ECR question — is that a consensus
    stamped after the board was built cannot be the one the board read."""
    ecr = tmp_path / "artifacts" / "ecr_cache" / "fp_ecr_PPR_2026.json"
    ecr.write_text(json.dumps({"total_experts": 99, "last_updated": "8/31",
                               "last_updated_ts": _ECR_TS_BEFORE_BOARD + 86_400}))
    with pytest.raises(SystemExit) as e:
        DB.assert_vintages_match(con=object())
    assert "AFTER the board was built" in str(e.value)


def test_a_mismatched_input_vintage_REFUSES_and_names_the_mart_rebuild(full_surface, monkeypatch):
    """Run 3's defect: the marts two days stale ⇒ 644 rows of wrong `proj_games`, found only
    after a full build."""
    monkeypatch.setattr(DB.N15, "read_input_vintage", lambda con, season, schema: {
        "depth_chart_as_of": "2026-08-29 12:56:08",
        "sleeper_status_as_of": "2026-08-31T13:30:16.880706+00:00"})
    with pytest.raises(SystemExit) as e:
        DB.assert_vintages_match(con=object())
    msg = str(e.value)
    assert "depth_chart_as_of: served 2026-08-31 14:44:50, local 2026-08-29 12:56:08" in msg
    assert "SPORTS_DUCKDB_PATH" in msg, (
        "the remedy must name the resolved-path export — an unset one silently builds a parallel "
        "database and exits 0")


def test_a_published_input_vintage_with_NO_marts_connection_REFUSES(full_surface):
    """NF1.7(a): a check that could not be evaluated is never scored as a pass."""
    with pytest.raises(SystemExit) as e:
        DB.assert_vintages_match(con=None)
    assert "COULD NOT BE CHECKED" in str(e.value)
    assert "--duckdb" in str(e.value)


def test_the_input_vintage_leg_is_TABLE_DRIVEN_over_the_manifests_own_keys(full_surface,
                                                                          monkeypatch):
    """⭐ The anti-drift property the ruling asked for: an input the BOARD starts publishing joins
    the check with no edit here and no new ruling."""
    doc = json.loads(full_surface.read_text())
    doc["freshness"]["input_vintage"]["a_future_input_as_of"] = "2026-09-01 00:00:00"
    full_surface.write_text(json.dumps(doc))
    monkeypatch.setattr(DB.N15, "read_input_vintage", lambda con, season, schema: {
        **_FULL_FRESHNESS["input_vintage"], "a_future_input_as_of": "2026-08-15 00:00:00"})
    with pytest.raises(SystemExit) as e:
        DB.assert_vintages_match(con=object())
    assert "a_future_input_as_of: served 2026-09-01 00:00:00, local 2026-08-15" in str(e.value)


def test_the_fingerprint_tables_are_not_empty():
    """A table-driven check over an empty table checks nothing."""
    assert DB._ADP_WINDOW_FIELDS and DB._ECR_FINGERPRINT_FIELDS
    assert {"window_start", "window_end", "drafts"} == {k for k, _ in DB._ADP_WINDOW_FIELDS}
