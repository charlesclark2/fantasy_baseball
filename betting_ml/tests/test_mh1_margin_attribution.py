"""MH1 guards — every §0.5 bake-off report attributes its margin, and no verdict moved doing it.

TWO THINGS MUST HOLD, AND THEY PULL IN OPPOSITE DIRECTIONS:

  1. **EVERY recorded report carries the attribution block** — including the reports where the
     decomposition cannot act, which must carry a NAMED reason. A silent report is
     indistinguishable from one where attribution was checked and came back clean (NF1.7 (a)).

  2. **NOTHING ELSE MOVED.** Attribution is presentational; the promotion question is unchanged. A
     decomposition that would move a verdict is a bug, not a feature — so the migration is pinned
     against a baseline captured at the PRE-MH1 commit, not merely against a re-run of itself.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from betting_ml.scripts import mh1_margin_attribution as mh1  # noqa: E402
from betting_ml.utils import margin_attribution as ma  # noqa: E402

_JSON_DIR = PROJECT_ROOT / "betting_ml/evaluation/feature_selection/bakeoff"
_MLB_ABL = PROJECT_ROOT / "quant_sports_intel_models/baseball/ablation_results"
_EDGE_ABL = PROJECT_ROOT / "quant_sports_intel_models/baseball/edge_program/ablation_results"


# ══════════════════════════════════════════════════════════════════════════════
# 1 — the decomposition itself
# ══════════════════════════════════════════════════════════════════════════════

def _grid(inc_lrn=2.4921, ref=2.4768, lead=2.4714):
    return [
        {"arm": "incumbent::ngboost_normal", "learner": "ngboost_normal", "crps_mean": inc_lrn},
        {"arm": "incumbent::glm_elasticnet", "learner": "glm_elasticnet", "crps_mean": ref},
        {"arm": "plus_both::glm_elasticnet", "learner": "glm_elasticnet", "crps_mean": lead},
    ]


def test_the_components_sum_to_the_reported_margin_exactly():
    """If they do not sum, the split is not a decomposition — it is two unrelated numbers."""
    d = ma.margin_decomposition(_grid(), "incumbent::ngboost_normal", "plus_both::glm_elasticnet",
                                "crps")
    assert d["available"] is True
    assert d["learner_swap"] + d["contract"] == pytest.approx(d["total"], abs=1e-9)
    assert d["total"] == pytest.approx(0.0207, abs=1e-4)
    assert d["learner_swap"] == pytest.approx(0.0153, abs=1e-4)
    assert d["contract"] == pytest.approx(0.0054, abs=1e-4)


def test_a_contract_that_is_worse_holding_the_learner_fixed_is_flagged_as_a_SIGN_FLIP():
    """The loudest reading the raw share cannot give you.

    `learner_share > 1` means the CONTRACT component points the OTHER WAY to the headline: holding
    the learner fixed, the "winning" contract LOST. A report that says the contract won is then not
    over-crediting, it is reporting the wrong DIRECTION — a different claim from ">half was the
    learner", and it must be flagged separately. This is the real total_runs/pre_lineup shape.
    """
    # the real total_runs/pre_lineup numbers: the leader beats the incumbent ARM overall, but
    # LOSES to its own learner on the incumbent CONTRACT.
    rows = [
        {"arm": "incumbent::glm_elasticnet", "learner": "glm_elasticnet", "crps_mean": 2.378137},
        {"arm": "incumbent::ngboost_normal", "learner": "ngboost_normal", "crps_mean": 2.374474},
        {"arm": "reprune::ngboost_normal", "learner": "ngboost_normal", "crps_mean": 2.377415},
    ]
    d = ma.margin_decomposition(rows, "incumbent::glm_elasticnet", "reprune::ngboost_normal",
                                "crps")
    assert d["total"] > 0, "the leader must still look better overall, or there is nothing to flip"
    assert d["contract"] < 0, "holding the learner fixed, the contract is worse"
    assert d["sign_flip"] is True
    assert d["learner_share"] > 1.0


def test_a_clean_contract_win_is_NOT_flagged():
    """A guard that fires on everything is worthless. The instrument must exonerate too."""
    d = ma.margin_decomposition(_grid(inc_lrn=2.4800, ref=2.4790, lead=2.4000),
                                "incumbent::ngboost_normal", "plus_both::glm_elasticnet", "crps")
    assert d["sign_flip"] is False and d["learner_dominates"] is False
    assert d["contract"] > d["learner_swap"]


def test_the_share_is_marked_unreliable_when_its_denominator_is_inside_the_noise_floor():
    """A share is a RATIO. A ratio whose denominator the gate itself calls noise is not a
    proportion — it is noise amplification. Two of E7.9's own three margins are in this state."""
    small = ma.margin_decomposition(_grid(inc_lrn=2.4800, ref=2.4790, lead=2.4770),
                                    "incumbent::ngboost_normal", "plus_both::glm_elasticnet",
                                    "crps", noise_floor=0.02)
    assert abs(small["total"]) < 0.02
    assert small["share_is_meaningful"] is False
    big = ma.margin_decomposition(_grid(), "incumbent::ngboost_normal",
                                 "plus_both::glm_elasticnet", "crps", noise_floor=0.02)
    assert big["share_is_meaningful"] is True, "0.0207 clears a 0.02 floor — must not be suppressed"


def test_the_renderer_refuses_to_print_a_percentage_it_has_just_called_unreliable():
    """Computing the caveat and then printing the percentage anyway would be the whole defect."""
    d = ma.margin_decomposition(_grid(inc_lrn=2.4800, ref=2.4790, lead=2.4770),
                                "incumbent::ngboost_normal", "plus_both::glm_elasticnet", "crps",
                                noise_floor=0.02)
    md = "\n".join(ma.render_margin_attribution_md(
        d, metric="crps", leader_arm="plus_both::glm_elasticnet",
        incumbent_arm="incumbent::ngboost_normal"))
    assert "noise floor" in md and "not a reliable proportion" in md
    assert "%" not in md.split("| **learner swap**")[1].split("\n")[0], (
        "a percentage was printed for a share the same block calls unreliable")


def test_an_unavailable_decomposition_always_names_its_reason():
    """A bare `available: False` is indistinguishable from a check that never ran (NF1.7 (a))."""
    no_ref = ma.margin_decomposition(
        [{"arm": "incumbent::ngboost_normal", "learner": "ngboost_normal", "crps_mean": 2.49},
         {"arm": "plus_gb::catboost", "learner": "catboost", "crps_mean": 2.48}],
        "incumbent::ngboost_normal", "plus_gb::catboost", "crps")
    assert no_ref["available"] is False and no_ref["reason"]
    assert "total" in no_ref, "E7.9's contract: the undecomposed margin still surfaces"
    missing = ma.margin_decomposition(_grid(), "incumbent::nope", "plus_both::glm_elasticnet",
                                      "crps")
    assert missing["available"] is False and "incumbent::nope" in missing["reason"]


def test_a_higher_is_better_metric_does_not_silently_invert_the_split():
    """The adoption hazard: a vertical scoring a HIGHER-is-better metric reusing this would get
    every sign backwards, and the components would still sum, so nothing would look wrong."""
    rows = {"incumbent::a": 0.50, "incumbent::b": 0.55, "variant::b": 0.60}
    hi = ma.margin_decomposition(rows, "incumbent::a", "variant::b", "score",
                                 lower_is_better=False)
    assert hi["total"] == pytest.approx(0.10, abs=1e-9), "leader is better ⇒ positive"
    assert hi["learner_swap"] == pytest.approx(0.05, abs=1e-9)
    assert hi["contract"] == pytest.approx(0.05, abs=1e-9)
    lo = ma.margin_decomposition(rows, "incumbent::a", "variant::b", "score")
    assert lo["total"] == pytest.approx(-0.10, abs=1e-9), "same data, opposite convention"


def test_the_shared_owner_reproduces_every_recorded_E7_9_block_byte_for_byte():
    """MH1 replaced E7.9's local implementation with a delegation. If the shared owner disagrees on
    even one legacy key, the recorded reports are quoting a number the code no longer computes."""
    stems = sorted(_JSON_DIR.glob("e7_9_retrain_*.json"))
    assert stems, "no recorded E7.9 results — this guard would pass on nothing"
    for path in stems:
        d = json.loads(path.read_text())
        got = ma.margin_decomposition(d["table"], d["incumbent_arm"], d["leader_arm"], d["metric"],
                                      noise_floor=d.get("noise_floor"))
        for k in mh1.LEGACY_DECOMP_KEYS:
            assert d["margin_decomposition"][k] == got[k], f"{path.name}: {k} moved"


def test_e7_9_delegates_rather_than_keeping_a_second_implementation():
    """One policy, one owner. A copy here is the repo's recurring N-implementations tax on the very
    machinery that exists to keep a report honest."""
    src = (PROJECT_ROOT / "betting_ml/scripts/e7_9_train_serve_consistency.py").read_text()
    body = src.split("def margin_decomposition(", 1)[1].split("\ndef ", 1)[0]
    assert "_shared_margin_decomposition(" in body, "E7.9 no longer delegates to the shared owner"
    assert "scores.get(same_learner_ref)" not in body, "a second implementation is back"


# ══════════════════════════════════════════════════════════════════════════════
# 2 — every report emits it
# ══════════════════════════════════════════════════════════════════════════════

_ATTRIBUTION_HEADING = "Margin attribution"


def test_every_recorded_bakeoff_report_carries_the_attribution_block():
    stems = [p.stem for p in _JSON_DIR.glob("bakeoff_*.json") if "smoke" not in p.stem]
    assert stems, "no recorded bake-off results found — this guard would pass on nothing"
    for stem in stems:
        md = (_MLB_ABL / f"{stem}.md").read_text()
        assert _ATTRIBUTION_HEADING in md, f"{stem}: attribution section missing"
        result = json.loads((_JSON_DIR / f"{stem}.json").read_text())
        att = result.get("margin_attribution")
        assert att is not None, f"{stem}: stored result carries no attribution block"
        decomp = att["decomposition"]
        assert decomp.get("available") is True or decomp.get("reason"), (
            f"{stem}: unavailable with no reason — silence and 'checked, clean' look identical")


def test_a_report_that_cannot_decompose_says_so_in_words_a_reader_will_see():
    """The single-contract runs are the majority. If they render an empty section, a reader learns
    nothing and may assume the margin IS a feature effect."""
    stem = "bakeoff_run_diff_post_lineup"
    md = (_MLB_ABL / f"{stem}.md").read_text()
    assert "Not available" in md and "NO contract axis" in md


def test_every_recorded_E7_9_report_still_carries_its_attribution_after_the_migration():
    stems = [p.stem for p in _JSON_DIR.glob("e7_9_retrain_*.json") if "smoke" not in p.stem]
    assert stems, "no recorded E7.9 results — this guard would pass on nothing"
    for stem in stems:
        md = (_EDGE_ABL / f"{stem}.md").read_text()
        assert _ATTRIBUTION_HEADING in md and "holding the LEARNER FIXED" in md


def test_the_paired_runs_are_the_ones_the_decomposition_actually_acts_on():
    """Names the ACTIVE set, so a future change that quietly stops pairing them is visible.

    ⚠️ NF-D20: an inactive check is not a passed one. Counting the active pairs is the difference
    between 'attribution held everywhere' and 'attribution ran nowhere'.
    """
    active = []
    for path in _JSON_DIR.glob("bakeoff_*.json"):
        att = json.loads(path.read_text()).get("margin_attribution") or {}
        if (att.get("decomposition") or {}).get("available"):
            active.append(path.stem)
    assert sorted(active) == sorted([
        "bakeoff_home_win_post_lineup_home_win_post_reprune_glm",
        "bakeoff_home_win_pre_lineup_pre_lineup_home_win_reprune_glm",
        "bakeoff_total_runs_pre_lineup_pre_lineup_total_runs_reprune_ngb",
    ]), "the set of runs the decomposition can act on changed"


def test_the_harness_still_pairs_a_variant_run_with_its_incumbent_run_LIVE():
    """⚠️ Every other pairing guard reads the RECORDED corpus, so a source regression that stopped
    pairing would stay green until something re-emitted — which is precisely how a defect survives
    a green suite. This one calls the harness."""
    from betting_ml.scripts import model_bakeoff as mb
    stored = json.loads((_JSON_DIR /
                         "bakeoff_total_runs_pre_lineup_pre_lineup_total_runs_reprune_ngb.json"
                         ).read_text())
    att = mb.attribution_for_run(stored)
    assert att["decomposition"]["available"] is True, (
        "the harness no longer pairs this variant run with its incumbent-contract counterpart")
    assert att["incumbent_arm"] == "incumbent::glm_elasticnet"
    assert att["leader_arm"] == "pre_lineup_total_runs_reprune_ngb::ngboost_normal"


def test_the_harness_refuses_to_pair_two_runs_that_are_not_a_controlled_contrast():
    """Differencing a smoke run against a full one would credit a DESIGN difference to the contract.
    The refusal must NAME the mismatch, not just decline."""
    from betting_ml.scripts import model_bakeoff as mb
    stored = json.loads((_JSON_DIR /
                         "bakeoff_total_runs_pre_lineup_pre_lineup_total_runs_reprune_ngb.json"
                         ).read_text())
    att = mb.attribution_for_run({**stored, "seed": stored["seed"] + 1})
    assert att["decomposition"]["available"] is False
    assert "seed" in att["decomposition"]["reason"]


def test_the_recorded_sign_flip_is_on_the_record():
    """total_runs/pre_lineup: holding the learner fixed, the 14-col re-pruned contract is WORSE
    than the 87-col incumbent. The headline margin says the opposite. This is MH1's finding and it
    must not silently disappear from the record."""
    d = json.loads((_JSON_DIR /
                    "bakeoff_total_runs_pre_lineup_pre_lineup_total_runs_reprune_ngb.json"
                    ).read_text())["margin_attribution"]["decomposition"]
    assert d["available"] and d["sign_flip"] is True
    assert d["contract"] < 0 < d["total"]
    assert d["share_is_meaningful"] is False, "and the margin is sub-noise, which must also be said"
    md = (_MLB_ABL /
          "bakeoff_total_runs_pre_lineup_pre_lineup_total_runs_reprune_ngb.md").read_text()
    assert "SIGN FLIP" in md


# ══════════════════════════════════════════════════════════════════════════════
# 3 — and nothing else moved
# ══════════════════════════════════════════════════════════════════════════════

def test_no_verdict_gate_or_selection_moved_across_the_whole_migration():
    """⭐ THE VERDICT-SAFETY PROOF.

    The baseline is fingerprinted at the PRE-MH1 commit and committed as a fixture, so this pins
    the MIGRATION — not merely that re-running the rewrite is idempotent with itself. The
    fingerprint is a hash of EVERY field except the attribution block, so a field added to the
    harness later is covered without editing this test.
    """
    baseline = json.loads(mh1.BASELINE_PATH.read_text())
    assert baseline["results"], "empty baseline — this guard would pass on nothing"
    assert len(baseline["results"]) == 12, "the affected corpus changed size"
    assert mh1.check(baseline) == []


def test_the_rewrite_is_idempotent_on_decision_fields():
    """Re-emitting must be a fixed point. A rewrite that drifts on a second pass is recomputing
    something, and the only thing it is allowed to compute is the attribution."""
    before = {p.name: mh1.decision_fingerprint(json.loads(p.read_text()))
              for p in _JSON_DIR.glob("bakeoff_*.json")}
    assert before, "no results to re-emit — this guard would pass on nothing"
    from betting_ml.scripts import model_bakeoff as mb
    mb.rewrite_reports()
    after = {p.name: mh1.decision_fingerprint(json.loads(p.read_text()))
             for p in _JSON_DIR.glob("bakeoff_*.json")}
    assert after == before


def test_the_baseline_covers_every_affected_result_and_is_not_hand_written():
    """A fixture derived from already-changed files could not detect the change it exists to catch,
    so the capture reads git blobs at a ref. Pin that the generator is the committed one."""
    baseline = json.loads(mh1.BASELINE_PATH.read_text())
    assert set(baseline["results"]) == set(mh1.affected_names())
    src = (PROJECT_ROOT / "betting_ml/scripts/mh1_margin_attribution.py").read_text()
    assert '"git", "show"' in src, "the baseline must be captured from git, not the working tree"


def test_attribution_is_presentational_and_recomputes_no_gate():
    """The shared owner must not compute a gate — checked on the AST, not on the text.

    ⚠️ A substring scan over source is satisfied — and, as this guard's own first cut proved,
    VIOLATED — by PROSE: the module's docstring explains what a verdict is, and a text scan called
    that a gate reference. Only executable names count (INC-38, the other way round).
    """
    import ast
    tree = ast.parse((PROJECT_ROOT / "betting_ml/utils/margin_attribution.py").read_text())
    referenced = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    referenced |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    referenced |= {a.name for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))
                   for a in n.names}
    assert referenced, "AST scan found no names — it would pass on nothing"
    banned = {"pbo_cscv", "deflated_sharpe", "dsr_gate", "verdict", "promote", "NOISE_FLOOR"}
    assert not (referenced & banned), (
        f"the attribution owner executes a gate concept: {sorted(referenced & banned)}")
    imported = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) if n.module}
    assert not any("promotion_gate" in m or "overfitting" in m for m in imported), (
        "the attribution owner imports gate machinery")
