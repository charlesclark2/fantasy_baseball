"""test_model_governance.py — NF-G0: the shared model/publish governance shape.

Every acceptance criterion in the story is pinned by a test whose NAME is the criterion, so a future
reader can map the suite onto the AC list without reading the bodies.

⚠️ ONE ISOLATING FIXTURE PER CLAUSE (NF-D17's lesson). A guard on an AND-composed rule is VACUOUS
unless its fixture SATISFIES every other clause — otherwise deleting the clause under test leaves
the suite green because a different clause was already refusing the fixture. The gate tests below
each build an otherwise-clean input and break exactly one thing.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from betting_ml.governance import gates as G
from betting_ml.governance import publish as P
from betting_ml.governance import registry as R
from betting_ml.scripts import model_governance as CLI
from betting_ml.scripts import sub_model_registry as SUB


# ══════════════════════════════════════════════════════════════════════════════════════════════
# AC: "fantasy and baseball model families share ONE governance shape"
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_baseball_registry_shares_this_exact_state_machine():
    """The identity — not equality — is what makes "one shape" mechanical rather than aspirational.

    If someone re-declares the transitions in `sub_model_registry`, this fails immediately, which is
    the whole point: the brief forbade a parallel fantasy registry, and prose cannot enforce that."""
    assert SUB._VALID_STATUSES is R.PROMOTION_STATES
    assert SUB._VALID_TRANSITIONS is R.VALID_TRANSITIONS


def test_the_shared_state_machine_still_has_the_baseball_semantics():
    """The lift must not have silently changed what the baseball registry already relied on."""
    assert R.PROMOTION_STATES == {"pending", "challenger", "champion", "deprecated"}
    assert R.VALID_TRANSITIONS["pending"] == {"challenger", "deprecated"}
    assert R.VALID_TRANSITIONS["challenger"] == {"champion", "deprecated"}
    assert R.VALID_TRANSITIONS["champion"] == {"deprecated"}
    assert R.VALID_TRANSITIONS["deprecated"] == frozenset()
    assert R.SERVED_STATUS == "champion" and R.STAGED_STATUS == "challenger"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# AC: "registry supports composite model lineage"
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _lineage(**over) -> dict:
    base = {
        "served_version": "fam_v2",
        "level_model_version": "level_v1",
        "ordering_model_version": "order_v2",
        "rookie_model_version": "rookie_v1",
        "rookie_selection_status": "PM_JUDGMENT",
        "interval_model_version": {"rookie": "nf1_8", "veteran": "nf1_9", "kdst": "nf1_6"},
        "scoring_contract_version": "nf_c0e",
        "artifact_uri": "file:///tmp/x",
        "promotion_status": "challenger",
        "model_family": "fam", "target": "tgt",
    }
    base.update(over)
    return base


def test_the_registry_carries_every_composite_lineage_member(tmp_path):
    reg = tmp_path / "r.yaml"
    R.register("fam", "tgt", _lineage(), path=reg)
    e = R.get_entry("fam", "tgt", "fam_v2", reg)
    for f in R.LINEAGE_FIELDS:
        assert f in e, f"lineage field {f} did not survive a round-trip"
    assert e["interval_model_version"] == {"rookie": "nf1_8", "veteran": "nf1_9", "kdst": "nf1_6"}


def test_the_interval_family_must_be_a_mapping_not_a_scalar(tmp_path):
    """Flattening the 3-way band family to one string makes one of its members unrepresentable."""
    with pytest.raises(ValueError, match="interval_model_version must be a mapping"):
        R.register("fam", "tgt", _lineage(interval_model_version="nf1_8"), path=tmp_path / "r.yaml")


def test_an_unknown_interval_member_is_refused(tmp_path):
    with pytest.raises(ValueError, match="unknown member"):
        R.register("fam", "tgt", _lineage(interval_model_version={"kicker": "x"}),
                   path=tmp_path / "r.yaml")


def test_the_registry_key_includes_the_version_so_a_challenger_cannot_clobber_the_champion(tmp_path):
    """⭐ The defect this test exists for is real and was found mid-story: keyed on (family, target)
    alone, staging a challenger OVERWRITES the champion — destroying the `fallback_artifact_uri`
    that makes the promotion reversible, at the exact moment the flow claims to wire rollback."""
    reg = tmp_path / "r.yaml"
    R.register("fam", "tgt", _lineage(served_version="fam_v1", promotion_status="champion",
                                      fallback_artifact_uri="file:///tmp/prev",
                                      validation_report="genesis"), path=reg)
    R.register("fam", "tgt", _lineage(served_version="fam_v2"), path=reg)
    assert R.get_entry("fam", "tgt", "fam_v1", reg)["fallback_artifact_uri"] == "file:///tmp/prev"
    assert R.get_entry("fam", "tgt", "fam_v2", reg)["promotion_status"] == "challenger"
    assert R.served_entry("fam", "tgt", reg)["served_version"] == "fam_v1"


def test_promoting_a_challenger_deprecates_the_prior_champion(tmp_path):
    reg = tmp_path / "r.yaml"
    R.register("fam", "tgt", _lineage(served_version="fam_v1", promotion_status="champion",
                                      fallback_artifact_uri="f", validation_report="g"), path=reg)
    R.register("fam", "tgt", _lineage(served_version="fam_v2", fallback_artifact_uri="f",
                                      validation_report="v"), path=reg)
    R.promote("fam", "tgt", "fam_v2", new_status="champion", path=reg)
    assert R.get_entry("fam", "tgt", "fam_v1", reg)["promotion_status"] == "deprecated"
    assert R.served_entry("fam", "tgt", reg)["served_version"] == "fam_v2"


def test_an_illegal_transition_is_refused(tmp_path):
    reg = tmp_path / "r.yaml"
    R.register("fam", "tgt", _lineage(promotion_status="pending"), path=reg)
    with pytest.raises(ValueError, match="invalid transition"):
        R.promote("fam", "tgt", "fam_v2", new_status="champion", path=reg)


def test_a_served_entry_must_be_rollbackable_and_must_name_its_validation(tmp_path):
    """Isolating fixtures — one clause each, every OTHER clause satisfied (NF-D17)."""
    reg = tmp_path / "r.yaml"
    with pytest.raises(ValueError, match="no fallback_artifact_uri"):
        R.register("fam", "tgt", _lineage(promotion_status="champion", validation_report="v"),
                   path=reg)
    with pytest.raises(ValueError, match="no validation_report"):
        R.register("fam", "tgt", _lineage(promotion_status="champion", fallback_artifact_uri="f"),
                   path=reg)
    # …and with BOTH satisfied it lands, proving neither message came from a third clause
    R.register("fam", "tgt", _lineage(promotion_status="champion", fallback_artifact_uri="f",
                                      validation_report="v"), path=reg)


def test_a_staged_challenger_does_not_need_a_published_at(tmp_path):
    """The rollback/validation requirement binds at `champion` ONLY. Requiring it at stage time
    would make staging impossible — the exact build/publish conflation this package removes."""
    R.register("fam", "tgt", _lineage(), path=tmp_path / "r.yaml")


def test_the_rookie_selection_status_vocabulary_can_express_a_judgment_call(tmp_path):
    """A status field that could only say "selected" would force a PM judgment to be RECORDED as a
    statistical selection — the E2.1-r laundering NF-D20 forbade, committed into the system of
    record."""
    assert "PM_JUDGMENT" in R.ROOKIE_SELECTION_STATUSES
    with pytest.raises(ValueError, match="rookie_selection_status"):
        R.register("fam", "tgt", _lineage(rookie_selection_status="looks_good_to_me"),
                   path=tmp_path / "r.yaml")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# AC: "build and publish are separate operations" + "publish defaults to no-op/dry-run"
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _seeded(tmp_path):
    reg = tmp_path / "r.yaml"
    prev, staged, live = tmp_path / "prev", tmp_path / "staged", tmp_path / "live"
    prev.mkdir(); staged.mkdir()
    (prev / "a.json").write_text('{"v":1}')
    (staged / "a.json").write_text('{"v":2}')
    R.register("fam", "tgt", _lineage(served_version="fam_v1", promotion_status="champion",
                                      artifact_uri=str(prev), fallback_artifact_uri=str(prev),
                                      validation_report="genesis"), path=reg)
    return reg, prev, staged, live


def test_stage_publishes_nothing_and_wires_the_rollback_target(tmp_path):
    reg, prev, staged, live = _seeded(tmp_path)
    st = P.stage(model_family="fam", target="tgt", lineage=_lineage(artifact_uri=str(staged)),
                 artifact_uri=str(staged), staged_digest=P.digest_tree(staged), registry_path=reg)
    assert st.entry["promotion_status"] == R.STAGED_STATUS
    assert st.entry["fallback_artifact_uri"] == str(prev)
    assert st.entry["previous_served_version"] == "fam_v1"
    assert not live.exists(), "stage() must not move a single byte"


def test_publish_defaults_to_a_dry_run_and_moves_nothing(tmp_path):
    reg, prev, staged, live = _seeded(tmp_path)
    P.stage(model_family="fam", target="tgt", lineage=_lineage(), artifact_uri=str(staged),
            registry_path=reg)
    R.register("fam", "tgt", {"validation_report": "v"}, served_version="fam_v2", path=reg)
    R.promote("fam", "tgt", "fam_v2", new_status="champion", path=reg)
    plan = P.publish(model_family="fam", target="tgt", served_version="fam_v2", source=staged,
                     destination=str(live), registry_path=reg)
    assert plan.executed is False
    assert not live.exists(), "the DEFAULT publish moved bytes — it must be a no-op"


def test_publishing_an_unpromoted_entry_raises_rather_than_silently_skipping(tmp_path):
    """A silent skip on an outward-facing action is the ALERT-tier violation this repo has been
    bitten by repeatedly — the caller must be told, not quietly obeyed."""
    reg, prev, staged, live = _seeded(tmp_path)
    P.stage(model_family="fam", target="tgt", lineage=_lineage(), artifact_uri=str(staged),
            registry_path=reg)
    with pytest.raises(ValueError, match="not 'champion'|promotion_status"):
        P.publish(model_family="fam", target="tgt", served_version="fam_v2", source=staged,
                  destination=str(live), execute=True, uploader=P.copy_tree_uploader,
                  registry_path=reg)


def test_execute_without_an_uploader_refuses_rather_than_claiming_a_publish(tmp_path):
    reg, prev, staged, live = _seeded(tmp_path)
    P.stage(model_family="fam", target="tgt", lineage=_lineage(), artifact_uri=str(staged),
            registry_path=reg)
    R.register("fam", "tgt", {"validation_report": "v"}, served_version="fam_v2", path=reg)
    R.promote("fam", "tgt", "fam_v2", new_status="champion", path=reg)
    with pytest.raises(ValueError, match="no uploader"):
        P.publish(model_family="fam", target="tgt", served_version="fam_v2", source=staged,
                  destination=str(live), execute=True, registry_path=reg)


def test_promotion_is_refused_when_the_gates_did_not_clear():
    bad = {"ready_to_promote": False, "gates": [{"gate": "interval_floors", "status": G.FAIL}]}
    with pytest.raises(ValueError, match="refusing to promote"):
        P.promote(model_family="fam", target="tgt", served_version="fam_v2", validation=bad,
                  validation_report="r", reviewed_by="someone")


def test_promotion_requires_a_named_reviewer(tmp_path):
    """The flow has a human review step; an unattributed review is not one."""
    reg, prev, staged, live = _seeded(tmp_path)
    P.stage(model_family="fam", target="tgt", lineage=_lineage(), artifact_uri=str(staged),
            registry_path=reg)
    good = {"ready_to_promote": True, "gates": []}
    with pytest.raises(ValueError, match="named reviewer"):
        P.promote(model_family="fam", target="tgt", served_version="fam_v2", validation=good,
                  validation_report="r", reviewed_by="", registry_path=reg)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# AC: "rollback is ONE documented operator action"
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_rollback_defaults_to_a_dry_run(tmp_path):
    reg, prev, staged, live = _seeded(tmp_path)
    P.copy_tree_uploader(staged, str(live))
    rec = P.rollback(model_family="fam", target="tgt", destination=str(live), registry_path=reg)
    assert rec["executed"] is False
    assert P.digest_tree(live) == P.digest_tree(staged), "the dry run restored something"


def test_rollback_is_one_call_and_restores_byte_for_byte(tmp_path):
    reg, prev, staged, live = _seeded(tmp_path)
    P.copy_tree_uploader(staged, str(live))
    assert P.digest_tree(live) != P.digest_tree(prev)
    P.rollback(model_family="fam", target="tgt", execute=True, restorer=P.copy_tree_restorer,
               destination=str(live), registry_path=reg)
    assert P.digest_tree(live) == P.digest_tree(prev)


def test_rollback_refuses_when_no_predecessor_was_preserved(tmp_path):
    reg = tmp_path / "r.yaml"
    R.register("fam", "tgt", _lineage(served_version="fam_v1", promotion_status="champion",
                                      fallback_artifact_uri="f", validation_report="g"), path=reg)
    # strip the fallback the way a hand-edit would, then confirm rollback REFUSES rather than
    # silently doing nothing (a rollback that no-ops during an incident is worse than an error)
    raw = R.load_registry(reg)
    raw["fam__tgt__fam_v1"].pop("fallback_artifact_uri")
    R._write(raw, reg)
    with pytest.raises(ValueError, match="no fallback_artifact_uri"):
        P.rollback(model_family="fam", target="tgt", registry_path=reg)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The ten gates — one isolating fixture per gate
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_all_ten_required_gates_are_wired_into_run_gates():
    names = [r.name for r in G.run_gates(entry=_lineage())]
    assert names == list(G.REQUIRED_GATE_NAMES)
    assert len(G.REQUIRED_GATE_NAMES) == 10


def test_an_unevaluable_gate_is_not_a_pass():
    """NF1.7 (a): a check that could not see its subject has examined NOTHING. Scoring that green is
    how a governance layer becomes decoration."""
    # ⚠️ ISOLATING FIXTURE (NF-D17). `fallback_artifact_uri` is present ON PURPOSE: without it
    # `rollback_artifact_exists` returns FAIL, and that single FAIL would make `all_passed` False no
    # matter how UNEVALUABLE is handled — so the test would pass while the clause under test was
    # deleted. Verified: with this fixture EVERY gate is UNEVALUABLE, so only the UNEVALUABLE rule
    # can decide the result.
    entry = _lineage(fallback_artifact_uri="s3://prev/")
    results = G.run_gates(entry=entry)
    assert all(r.status == G.UNEVALUABLE for r in results), (
        f"fixture is not isolating — {[(r.name, r.status) for r in results if r.status != G.UNEVALUABLE]}")
    assert G.all_passed(results) is False, "UNEVALUABLE was counted as a pass"


def test_only_the_named_post_publish_gates_may_be_unevaluable_at_promote_time():
    results = G.run_gates(entry=_lineage())
    assert G.all_passed(results, allow_unevaluable=G.POST_PUBLISH_GATE_NAMES) is False, (
        "the exemption must not wave through the EIGHT gates that are evaluable pre-publish")
    assert set(G.POST_PUBLISH_GATE_NAMES) == {"live_payload_matches_staged",
                                              "clients_agree_on_version"}


def test_model_stamp_mismatch_fails_and_the_registry_wins():
    e = _lineage()
    stamp = {k: e[k] for k in ("served_version", "level_model_version", "ordering_model_version")}
    assert G.model_stamp_consistency(e, stamp).passed
    stamp["ordering_model_version"] = "drifted"
    r = G.model_stamp_consistency(e, stamp)
    assert r.status == G.FAIL and "registry is the authority" in r.detail


def test_a_stamp_sharing_no_field_with_the_registry_is_unevaluable_not_a_pass():
    """An empty intersection is not agreement — this is the vacuous-anchor failure mode."""
    assert G.model_stamp_consistency(_lineage(), {"unrelated": "x"}).status == G.UNEVALUABLE


def test_universe_count_catches_the_nf1_5b_vanishing_players_defect():
    """NF1.5b's first cut carried 716 players against the shipped 784 — 68 veterans would have
    vanished from the draft board on the flip."""
    assert G.universe_count(784, 784).passed
    r = G.universe_count(716, 784)
    assert r.status == G.FAIL and "68" not in r.detail  # message reports the counts + the drift
    assert G.universe_count(None, 784).status == G.UNEVALUABLE


def test_rookie_coverage_fails_when_a_level_change_adds_or_drops_rookies():
    assert G.rookie_coverage(81, 81).passed
    assert G.rookie_coverage(80, 81).status == G.FAIL
    assert G.rookie_coverage(0, 0).status == G.FAIL          # a board with no rookies at all
    assert G.rookie_coverage(None, 81).status == G.UNEVALUABLE


def test_interval_floors_fails_on_a_breach_and_has_no_tolerance_knob():
    assert G.interval_floors({"pass": True}).passed
    r = G.interval_floors({"pass": False, "rookies": {"misses": ["RB 0.7905<0.800"]}})
    assert r.status == G.FAIL and "do NOT move the floor" in r.detail
    assert G.interval_floors(None).status == G.UNEVALUABLE, (
        "a level shift moves the band CENTRE — an absent re-validation must never read as a pass")
    import inspect
    assert "tol" not in inspect.signature(G.interval_floors).parameters


def test_scoring_parity_fails_on_a_line_that_does_not_score_to_its_point():
    assert G.scoring_parity(0.0, n_compared=81).passed
    assert G.scoring_parity(0.5, n_compared=81).status == G.FAIL
    assert G.scoring_parity(0.0, n_compared=0).status == G.UNEVALUABLE, (
        "a parity check that compared ZERO rows is not a pass")


def test_track_record_copy_screening_blocks_a_market_beating_claim():
    assert G.track_record_copy_compatible(["a board-blind conservative recalibration"]).passed
    assert G.track_record_copy_compatible(["we beat the market every position"]).status == G.FAIL
    assert G.track_record_copy_compatible(None).status == G.UNEVALUABLE


def test_rollback_artifact_gate_distinguishes_absent_from_unknown():
    """Three outcomes, and conflating the last two is the vacuous-anchor bug: 'no URI named' is a
    FAIL, 'could not check' is UNEVALUABLE, and only a confirmed present artifact passes."""
    assert G.rollback_artifact_exists({"fallback_artifact_uri": "s3://x"}, True).passed
    assert G.rollback_artifact_exists({"fallback_artifact_uri": "s3://x"}, False).status == G.FAIL
    assert G.rollback_artifact_exists({}, True).status == G.FAIL
    assert G.rollback_artifact_exists({"fallback_artifact_uri": "s3://x"},
                                      None).status == G.UNEVALUABLE


def test_live_payload_gate_cannot_pass_before_a_publish():
    assert G.live_payload_matches_staged("abc", "abc").passed
    assert G.live_payload_matches_staged("abc", "def").status == G.FAIL
    assert G.live_payload_matches_staged("abc", None).status == G.UNEVALUABLE


def test_a_one_sided_client_read_cannot_prove_the_two_clients_agree():
    """The deploy-skew gate (NF-C0): `frontend/` auto-deploys while the API Lambda needs a manual
    `deploy.sh`, so reading ONE side and calling it agreement is exactly the blind spot."""
    e = _lineage(served_version="fam_v2")
    assert G.clients_agree_on_version(e, "fam_v2", "fam_v2").passed
    assert G.clients_agree_on_version(e, "fam_v2", "stale").status == G.FAIL
    assert G.clients_agree_on_version(e, "fam_v2", None).status == G.UNEVALUABLE


# ══════════════════════════════════════════════════════════════════════════════════════════════
# AC: "prove the pipeline with a dry-run / synthetic promotion"
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_synthetic_promotion_exercises_the_whole_flow_and_every_refusal(tmp_path):
    rec = CLI.synthetic_promotion(tmp_path)
    assert rec["pass"] is True
    steps = {s["step"] for s in rec["steps"]}
    assert {"genesis", "stage", "publish_before_promote", "promote_on_failed_gates", "validate",
            "promote", "publish_dry_run", "publish", "live_readback",
            "rollback"} <= steps
    rb = next(s for s in rec["steps"] if s["step"] == "rollback")
    assert rb["byte_identical"] is True


# ══════════════════════════════════════════════════════════════════════════════════════════════
# AC: "live readback verifies version AND rookie policy"
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _served(tmp_path):
    reg = tmp_path / "r.yaml"
    R.register("fam", "tgt", _lineage(
        served_version="fam_v2", promotion_status="champion", fallback_artifact_uri="f",
        validation_report="v", rookie_shrink_lambda=0.5, rookie_statistically_selected=False,
        staged_digest="D"), path=reg)
    return reg


def test_live_readback_checks_the_rookie_policy_not_only_the_version(tmp_path):
    """⭐ A publish can carry the right version string and the WRONG rookie treatment — the
    recalibration silently off, or on at a different shrink. A version-only readback calls that a
    success, which is precisely why the policy fields are read back too."""
    reg = _served(tmp_path)
    ok = P.live_readback(
        model_family="fam", target="tgt",
        live_payload={"model_version": "fam_v2",
                      "rookie_policy": {"selection_status": "PM_JUDGMENT", "shrink_lambda": 0.5,
                                        "statistically_selected": False}},
        live_digest="D", backend_version="fam_v2", frontend_version="fam_v2", registry_path=reg)
    assert ok["pass"] is True

    wrong_lambda = P.live_readback(
        model_family="fam", target="tgt",
        live_payload={"model_version": "fam_v2",
                      "rookie_policy": {"selection_status": "PM_JUDGMENT", "shrink_lambda": 1.0,
                                        "statistically_selected": False}},
        live_digest="D", backend_version="fam_v2", frontend_version="fam_v2", registry_path=reg)
    assert wrong_lambda["pass"] is False, "a wrong shrink λ passed a readback that checks the version"


def test_live_readback_treats_a_missing_policy_block_as_unevaluable_not_a_pass(tmp_path):
    reg = _served(tmp_path)
    rec = P.live_readback(model_family="fam", target="tgt",
                          live_payload={"model_version": "fam_v2"}, live_digest="D",
                          backend_version="fam_v2", frontend_version="fam_v2", registry_path=reg)
    assert rec["pass"] is False
    assert any(c["status"] == G.UNEVALUABLE for c in rec["checks"])


# ══════════════════════════════════════════════════════════════════════════════════════════════
# AC: "the registry is the NAMED AUTHORITY for model status"
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_shipped_nfl_fantasy_entry_is_present_valid_and_says_what_is_served():
    entry = R.served_entry("nfl_fantasy", "season_projection")
    assert entry is not None, "the NFL fantasy family must have a served entry — that is the AC"
    R.validate_entry("shipped", entry)
    assert entry["served_version"] == entry["ordering_model_version"]
    assert entry["interval_model_version"] == {"rookie": "nf1_8", "veteran": "nf1_9",
                                               "kdst": "nf1_6"}


def test_the_shipped_registry_agrees_with_the_rookie_publish_policy_it_describes():
    """⭐ THE RECONCILIATION THE REGISTRY EXISTS FOR, pointed at itself. NF-D21's serving flip is
    HELD, so the registry must say `incumbent` / λ 0.0. If someone flips `SERVING_ENABLED` without
    promoting through the pipeline, these disagree and this test fails — which is exactly the drift
    the `model_stamp_consistency` gate catches in production."""
    from quant_sports_intel_models.football.nfl.fantasy import rookie_publish_policy as RP
    entry = R.served_entry("nfl_fantasy", "season_projection")
    served_lambda = RP.serving_lambda()
    assert entry["rookie_shrink_lambda"] == served_lambda
    assert entry["rookie_selection_status"] == (RP.SELECTION_STATUS if served_lambda
                                                else "incumbent")


def test_the_registry_file_is_edited_through_the_api_so_it_always_validates():
    for key, entry in R.load_registry().items():
        R.validate_entry(key, entry)


def test_the_cli_exposes_every_verb_in_the_promotion_flow():
    ap = CLI.build_arg_parser()
    verbs = {a for act in ap._subparsers._group_actions for a in act.choices}
    assert {"show", "list", "selftest", "stage", "publish", "rollback"} <= verbs


def test_the_governance_package_never_imports_pipeline_or_boto3():
    """E11.23: a fast-gate test that imports `pipeline` dies at COLLECTION (the dbt manifest is
    gitignored). And a governance layer that opened a boto3 client could not be exercised in CI at
    all, since CI mocks every IO."""
    import re
    root = Path(R.__file__).parent
    # ⚠️ match a real IMPORT/CALL form, not the bare word: these modules DISCUSS boto3 in their
    # docstrings (explaining why they don't use it), and a substring match would fail on the very
    # comment that documents the invariant — the mirror of INC-38's "prose must not SATISFY a
    # source-inspection guard", here "prose must not BREAK one".
    bad = re.compile(r"^\s*(import|from)\s+(pipeline|boto3)\b|boto3\.(client|resource|Session)\(",
                     re.MULTILINE)
    for py in sorted(root.glob("*.py")):
        hits = bad.findall(py.read_text())
        assert not hits, f"{py.name} imports {hits} — keep pipeline/IO out of the governance layer"
