"""Guards for NCAAF-P2.1 S1 — `pace` under a lower-variance GATE design (fresh §0.5 registration).

What these pin: the pre-registration matches the code (arms, field size, primary, anchors); every S1
arm is a STRICT SUBSET of the P2.1 pace block (S1 changes the gate design, NOT the feature); the two
return series are genuinely different objects (per-FOLD for DSR, per-BUCKET for PBO) and the BINDING
DSR figure is computed on the FOLD series at the CALL SITE (P2.1's own lesson: a guard on the clause
functions alone is vacuous when the defect lives at the call site); `V` excludes the anchors but
`n_trials` keeps them; `classify_null` receives the DECLARED field; a per-fold DSR below 3 folds is
UNDEFINED, never a pass.

Fast-gate discipline (E11.23): nothing here imports `pipeline`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quant_sports_intel_models.football.ncaaf.models import p2_1_s1_pace as s1
from quant_sports_intel_models.football.ncaaf.models.p2_1_blocks import BLOCK_BY_ARM, block_columns

_ROOT = Path(__file__).resolve().parents[2]
_NCAAF = _ROOT / "quant_sports_intel_models" / "football" / "ncaaf"
_PREREG = _NCAAF / "ablation_results" / "ncaaf_p2_1_s1_preregistration.md"
_HARNESS = _NCAAF / "models" / "p2_1_s1_pace.py"
_P21_HARNESS = _NCAAF / "models" / "bakeoff_ncaaf_p2_1.py"


def _strip_comments(src: str) -> str:
    return "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))


# ---------------------------------------------------------------------------
# The pre-registration IS the contract
# ---------------------------------------------------------------------------

def test_preregistration_exists_and_names_every_registered_arm_and_the_primary():
    assert _PREREG.exists(), "the S1 pre-registration must be committed"
    text = _PREREG.read_text()
    for b in s1.S1_BLOCKS:
        assert f"`{b.arm}`" in text, f"arm {b.arm!r} is scored by the code but absent from the prereg"
        assert b.hypothesis in text, f"hypothesis id {b.hypothesis!r} missing from the prereg"
    assert f"`{s1.PRIMARY}`" in text
    # the primary is fixed as the P2.1 arm, and the prereg says only it can ship
    assert s1.PRIMARY == "pace"
    assert re.search(r"ship candidate is FIXED as `pace`", text)


def test_declared_field_size_is_the_registered_real_arm_count():
    assert s1.DECLARED_FIELD_SIZE_S1 == len(s1.S1_BLOCKS) == 3
    assert "Declared field size = 3 real arms" in _PREREG.read_text()


def test_n_trials_is_reference_plus_field_plus_anchors():
    """MH2: `n_trials` = the FULL declared field (real arms + anchors); the prereg says 8."""
    assert s1.n_trials_declared() == 1 + 3 + 4 == 8
    assert "**8**" in _PREREG.read_text()


def test_the_anchors_are_the_four_generic_ones_and_not_the_h1b_foil():
    assert set(s1.S1_ANCHORS) == {"oracle_peek", "permute", "zero_width", "max_width"}
    assert "hfa_global" not in s1.S1_ANCHORS


# ---------------------------------------------------------------------------
# NO NEW FEATURE — every S1 arm is a strict subset of the P2.1 pace block
# ---------------------------------------------------------------------------

def test_every_s1_arm_is_a_subset_of_the_p21_pace_block_and_the_primary_is_verbatim():
    p21_pace = set(BLOCK_BY_ARM["pace"].raw)
    for b in s1.S1_BLOCKS:
        assert b.infold is None, f"{b.arm}: S1 arms are RAW — no in-fold builder, nothing target-encoded"
        assert set(b.raw) <= p21_pace, f"{b.arm} introduces columns outside the P2.1 pace block: {set(b.raw) - p21_pace}"
    assert tuple(s1.S1_BLOCK_BY_ARM["pace"].raw) == tuple(BLOCK_BY_ARM["pace"].raw), \
        "the primary must be the P2.1 H9 block VERBATIM"
    assert set(s1.S1_BLOCK_BY_ARM["pace_axis"].raw) == {"pace_sum", "pace_diff"}
    assert set(s1.S1_BLOCK_BY_ARM["pace_total_axis"].raw) == {"pace_sum"}


def test_s1_blocks_materialise_only_their_declared_columns():
    n = 30
    rng = np.random.default_rng(0)
    cols = list(BLOCK_BY_ARM["pace"].raw)
    tr = pd.DataFrame({c: rng.normal(size=n) for c in cols})
    ev = pd.DataFrame({c: rng.normal(size=n) for c in cols})
    for b in s1.S1_BLOCKS:
        a, e, names = block_columns(b, tr, ev)
        assert list(a.columns) == list(b.raw) == names
        assert a.shape == (n, len(b.raw)) and e.shape == (n, len(b.raw))


# ---------------------------------------------------------------------------
# The two series are different objects — and the fold series is the DSR series
# ---------------------------------------------------------------------------

def _fake_arm(fold_crps, buckets):
    return {"fold_crps": list(fold_crps), "buckets": list(buckets)}


def test_fold_series_and_bucket_series_read_different_fields():
    ref = _fake_arm([10, 10, 10], [10] * 12)
    arm = _fake_arm([9, 9.5, 8], [9] * 12)
    f = s1.fold_series(ref, arm)
    b = s1.bucket_series(ref, arm)
    assert len(f) == 3 and len(b) == 12
    assert np.allclose(f, [1.0, 0.5, 2.0])
    assert np.allclose(b, 1.0)


def test_binding_dsr_is_computed_on_the_FOLD_series_at_the_call_site():
    """P2.1's own lesson (NF-D17): guard the CALL SITE, not just the helper. The binding figure must
    be built from `fold_series(...)`, and the per-bucket figure must be labelled REPORTED ONLY."""
    src = _strip_comments(_HARNESS.read_text())
    m = re.search(r'"per_fold_declared_field_degenerate_excluded":\s*_dsr\((\w+),', src)
    assert m, "the binding DSR entry must exist"
    var = m.group(1)
    assert re.search(rf"{var}\s*=\s*fold_series\(", src), \
        f"the binding DSR series `{var}` must be built by fold_series(...), not bucket_series"
    m2 = re.search(r'"per_bucket_p21_series_REPORTED_ONLY":\s*_dsr\((\w+),', src)
    assert m2 and re.search(rf"{m2.group(1)}\s*=\s*bucket_series\(", src)
    assert re.search(r'"binding":\s*"per_fold_declared_field_degenerate_excluded"', src)
    # and the VERDICT reads the binding value, not the bucket one
    assert re.search(r'dsr_binding\s*=\s*dsr\.get\("per_fold_declared_field_degenerate_excluded"', src)


def test_pbo_stays_on_the_bucket_series():
    src = _strip_comments(_HARNESS.read_text())
    assert re.search(r'perf\s*=\s*np\.array\(\[arms\[a\]\["buckets"\]', src), \
        "PBO must be computed over the per-BUCKET series (P2.1's series, unchanged)"


def test_V_is_measured_over_the_real_arms_but_n_trials_keeps_the_anchors():
    """DSR-CONV / MH2.1(a), declared forward: `V` over the 3 real arms' per-FOLD Sharpes; the anchors
    stay in `n_trials`."""
    src = _strip_comments(_HARNESS.read_text())
    assert re.search(r"sr_fold_real\s*=\s*\[sharpe\(fold_series\(ref, arms\[a\]\)\)\s*for a in real\]", src)
    assert re.search(r"V_clean\s*=\s*float\(np\.var\(sr_fold_real", src)
    assert re.search(r"n_trials\s*=\s*1\s*\+\s*len\(real\)\s*\+\s*len\(anchors\)", src)


def test_classify_null_receives_the_declared_field_and_the_fold_sharpe():
    src = _strip_comments(_HARNESS.read_text())
    call = src[src.index("cv_power.classify_null("):]
    call = call[:call.index(")\n")]
    assert "declared_field_size=DECLARED_FIELD_SIZE_S1" in call
    assert "degenerates_excluded_from_v=True" in call
    assert 'observed_sr=r["sharpe_per_fold"]' in call, "the null state is classified on the DECLARED series"


def test_a_per_fold_dsr_below_three_folds_is_UNDEFINED_not_a_pass():
    """MH2: 'not computable' is a state — a 2-fold smoke must report UNDEFINED and can never SHIP."""
    src = _strip_comments(_HARNESS.read_text())
    assert re.search(r"if len\(series\) < 3:\s*\n\s*return \{\"dsr\": None", src)
    # and the SHIP rule requires a FINITE binding DSR
    assert re.search(r"dsr_ok\s*=\s*bool\(np\.isfinite\(dsr_binding\)\s*and\s*dsr_binding\s*>=\s*_DSR_GATE\)", src)


def test_verdict_requires_reproduction_and_anchors_and_every_gate():
    src = _strip_comments(_HARNESS.read_text())
    assert re.search(r"interpretable\s*=\s*bool\(anchors_ok and repro\[\"holds\"\]\)", src)
    assert re.search(r'verdict\s*=\s*"SHIP" if \(interpretable and arm_gates and pbo_ok and dsr_ok\)', src)


def test_reproduction_check_compares_reference_and_primary_against_the_p21_record(tmp_path, monkeypatch):
    p21 = _NCAAF / "ablation_results" / "ncaaf_p2_1_battery_scores.json"
    assert p21.exists(), "the P2.1 record is the reproduction target and must be present"
    doc = json.loads(p21.read_text())["arms"]
    arms = {"reference": {"fold_crps": doc["reference"]["fold_crps"]},
            "pace": {"fold_crps": doc["pace"]["fold_crps"]}}
    r = s1.reproduction_check(arms)
    assert r["holds"] and r["max_abs_dev"] == 0.0
    # a drifted harness is caught
    drift = {"reference": arms["reference"],
             "pace": {"fold_crps": [x + 5e-4 for x in arms["pace"]["fold_crps"]]}}
    r2 = s1.reproduction_check(drift)
    assert not r2["holds"] and "drifted" in r2["reason"]
    # a fold-count mismatch (e.g. a smoke) is NOT a pass
    short = {"reference": arms["reference"], "pace": {"fold_crps": arms["pace"]["fold_crps"][:2]}}
    assert not s1.reproduction_check(short)["holds"]


# ---------------------------------------------------------------------------
# The P2.1 harness injection point is backwards-compatible (P2.1's registry stays the default)
# ---------------------------------------------------------------------------

def test_p21_harness_defaults_to_its_own_registry():
    import inspect
    from quant_sports_intel_models.football.ncaaf.models import bakeoff_ncaaf_p2_1 as p21
    sig = inspect.signature(p21.score_arm_fold)
    assert sig.parameters["blocks"].default is p21.BLOCKS
    sig2 = inspect.signature(p21._arm_columns)
    assert sig2.parameters["blocks"].default is p21.BLOCKS
    src = _strip_comments(_P21_HARNESS.read_text())
    assert re.search(r"blk = next\(bb for bb in blocks if bb\.arm == arm\)", src), \
        "the arm lookup must resolve against the INJECTED registry, not the module global"


def test_sharpe_helper_is_zero_on_a_degenerate_series():
    assert s1.sharpe(np.array([1.0])) == 0.0
    assert s1.sharpe(np.array([2.0, 2.0, 2.0])) == 0.0
    assert s1.sharpe(np.array([1.0, 3.0])) == pytest.approx(2.0 / np.std([1.0, 3.0], ddof=1))
