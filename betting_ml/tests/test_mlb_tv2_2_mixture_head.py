"""MLB-TV2-2 guards — the code twin is pinned to `ablation_results/mlb_tv2_2_prereg.md`.

Every clause here is RED-proven by `betting_ml/tests/mlb_tv2_2_red_proof.py`: each is driven by a
deliberate mutation with a UNIQUE anchor, and a clause that stays green on a broken source is a
vacuous guard, not a guard (NF1.7 (a) / INC-38 / NF-D17).

Fast gate: imports only `betting_ml`, never `pipeline` (E11.23).
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC_PATH = ROOT / "betting_ml" / "scripts" / "mlb_tv2_2_mixture_head.py"
PREREG_PATH = ROOT / "ablation_results" / "mlb_tv2_2_prereg.md"
SRC = SRC_PATH.read_text()
PREREG = PREREG_PATH.read_text()


def _no_comments(text: str) -> str:
    """Strip `#` comments AND docstrings — prose must never satisfy a source guard (INC-38)."""
    tree = ast.parse(text)
    docs = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            d = ast.get_docstring(node, clean=False)
            if d:
                docs.add(d)
    out = "\n".join(l.split("#")[0] if not l.strip().startswith("#") else ""
                    for l in text.splitlines())
    for d in docs:
        out = out.replace(d, "")
    return out


CODE = _no_comments(SRC)


@pytest.fixture(scope="module")
def M():
    import sys
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from betting_ml.scripts import mlb_tv2_2_mixture_head as mod
    return mod


# ── the code twin ──────────────────────────────────────────────────────────────────────────────

def test_prereg_document_exists_and_carries_the_four_epic_obligations():
    for phrase in ("LONGER-WINDOW REPLICATION", "TIE-WITH-FOIL", "DISAMBIGUATION", "SCOPE"):
        assert phrase in PREREG, f"prereg is missing epic obligation marker {phrase!r}"


def test_registered_constants_are_the_code_twin_of_the_prereg(M):
    assert M.DECLARED_FIELD_SIZE == len(M.TRIAL_ARMS) == 4
    assert M.N_BLOCKS == 8 and "N_BLOCKS = 8" in PREREG
    assert M.DSR_GATE == 0.95 and M.PBO_GATE == 0.20
    assert M.PBO_APPLICATION == "field"
    assert M.CHAMPION_FIT_DATE in PREREG and M.FULL_ERA_END in PREREG


def test_the_study_is_market_blind_and_reads_no_odds_column():
    banned = ("odds", "moneyline", "total_line", "consensus", "vig", "closing", "book")
    sql = re.search(r'_PULL_SQL = f"""(.*?)"""', SRC, re.S).group(1).lower()
    for tok in banned:
        assert not re.search(rf"\b{tok}\w*\b", sql), f"market-blind violated: {tok!r} in the pull SQL"


def test_best_alpha_is_zero_and_nothing_ships_to_a_registry(M):
    assert M.BEST_ALPHA == 0
    assert "sub_model_registry" not in SRC, "this study must not touch the model registry (MH2.1)"
    for invocation in ("subprocess", "os.system", "infrastructure/lambda"):
        assert invocation not in CODE, f"nothing here may invoke {invocation!r} — DEPLOY-HELD"
    assert "DEPLOY-HELD" in SRC


# ── §2.1 served-ness is the LAG, not the flag ──────────────────────────────────────────────────

def test_pull_refuses_a_population_whose_insertion_lag_says_backtest(M, tmp_path, monkeypatch):
    import pandas as pd
    cache = tmp_path / "backtest.parquet"
    pd.DataFrame({"insert_lag_days": [981.0] * 5, "mu": [8.0] * 5}).to_parquet(cache)
    with pytest.raises(ValueError, match="NOT served"):
        M.pull(cache=cache)


def test_pull_accepts_a_genuinely_served_population(M, tmp_path):
    import pandas as pd
    cache = tmp_path / "served.parquet"
    pd.DataFrame({"insert_lag_days": [0.0] * 5, "mu": [8.0] * 5}).to_parquet(cache)
    assert len(M.pull(cache=cache)) == 5


# ── §6 the TIE-WITH-FOIL guard ─────────────────────────────────────────────────────────────────

def test_initialization_is_staggered_so_no_component_starts_at_a_common_point(M):
    z = np.random.default_rng(0).standard_normal(400)
    for K in (2, 3):
        w, m, s = M._staggered_init(z, K)
        assert len(np.unique(np.round(m, 9))) == K, "component locations must start DISTINCT"
        assert len(np.unique(np.round(w, 9))) == K, "starting weights must be UNEQUAL"


def test_the_collapse_detector_fires_on_each_of_its_three_registered_conditions(M):
    z = np.random.default_rng(7).standard_normal(500)
    z = (z - z.mean()) / z.std(ddof=1)

    law = M.fit_mix(z, 2)
    mu1, sd1 = law._k1
    law.w, law.m, law.s = np.array([0.5, 0.5]), np.array([mu1, mu1]), np.array([sd1, sd1])
    assert law._detect_collapse()[0], "sup-norm condition must fire on an exact foil collapse"

    law2 = M.fit_mix(z, 2)
    law2.w = np.array([M.COLLAPSE_MIN_WEIGHT / 2, 1 - M.COLLAPSE_MIN_WEIGHT / 2])
    fired, why = law2._detect_collapse()
    assert fired and any("weight" in r for r in why), "min-weight condition must fire"

    law3 = M.fit_mix(z, 2)
    law3.m = np.array([0.0, M.COLLAPSE_LOC_TOL / 2])
    law3.s = np.array([1.0, 1.0])
    fired, why = law3._detect_collapse()
    assert fired and any("coincide" in r for r in why), "coincident-component condition must fire"


def test_a_mixture_recovers_a_planted_skew_and_does_not_on_a_normal_sample(M):
    from scipy.stats import skewnorm
    zs = skewnorm.rvs(4.0, size=700, random_state=1)
    zs = (zs - zs.mean()) / zs.std(ddof=1)
    assert M.fit_mix(zs, 2).skewness > 0.3, "the fitter must FIND a planted skew (§6.3)"
    zn = np.random.default_rng(3).standard_normal(700)
    zn = (zn - zn.mean()) / zn.std(ddof=1)
    assert abs(M.fit_mix(zn, 2).skewness) < 0.3, "a Normal sample must not produce a skew finding"


# ── §5.3 V-membership, §14.2 the field-level PBO ───────────────────────────────────────────────

def test_v_excludes_the_reference_the_foil_and_the_degenerates(M):
    assert set(M.V_ARMS) == set(M.TRIAL_ARMS)
    for excluded in (M.REFERENCE_ARM, M.FOIL_ARM, *M.DEGENERATE_ARMS):
        assert excluded not in M.V_ARMS, f"{excluded} must be OUT of V (MH2.1(a)/DSR-CONV)"
    for kept in (M.REFERENCE_ARM, M.FOIL_ARM, *M.DEGENERATE_ARMS):
        assert kept in M.N_TRIALS_ARMS, f"{kept} must stay in n_trials — multiplicity in full"


def test_c7_carries_dsr_only_and_never_pbo_as_a_per_arm_veto():
    body = re.search(r"def ship_verdict\(.*?\n(?=\ndef )", CODE, re.S).group(0)
    assert "dsr_pass" in body, "C7 must read the DSR gate"
    assert "pbo_pass" not in body, (
        "PBO is a FIELD-LEVEL statistic and must NEVER be a per-arm ship veto "
        "(PM convention 2026-08-28; prereg §5.5/§14.2)")


# ── §15 the registered series and statistics ───────────────────────────────────────────────────

def test_the_per_fold_series_is_crps_and_the_deflation_reads_it():
    body = re.search(r"def fold_series\(.*?\n(?=\ndef )", CODE, re.S).group(0)
    assert '"crps"' in body, "the registered per-fold series is the per-ROW CRPS improvement (§15.1)"
    defl = re.search(r"def deflation\(.*?\n(?=\ndef )", CODE, re.S).group(0)
    assert "fold_series(" in defl and "_per_group_brier_lift(" not in defl


def test_c8_corrects_the_statistic_that_carries_the_claim(M):
    body = re.search(r"def score_arms\(.*?\n(?=def _fold_clause)", CODE, re.S).group(0)
    bh_block = body[body.index("pvals = []"):body.index("bh_cut, bh_pass")]
    assert "p_over_stated" in bh_block, "C8 must correct C2's OWN movement p-value (§15.2)"
    assert "wilcoxon" not in bh_block, "the per-fold signed-rank is REPORTED, never binding (§15.2)"


def test_c10_tie_band_is_derived_from_n_and_not_a_hardcoded_constant():
    body = re.search(r"def score_arms\(.*?\n(?=def _fold_clause)", CODE, re.S).group(0)
    assert "tie_band = float(np.sqrt(0.25 / max(len(y), 1)))" in body, (
        "the C10 tie band must be ONE SE of the primary statistic at this n (§15.3)")
    assert "abs(orc - octl) > tie_band" in body


def test_there_is_one_oracle_per_form_because_the_forms_nest(M):
    for form in M.TRIAL_ARMS:
        assert f'oracle_{form}' in SRC and f'oraclectrl_{form}' in SRC or "oracle_{form}" in SRC
    body = re.search(r"def build_arms\(.*?\n(?=\ndef )", CODE, re.S).group(0)
    assert 'f"oracle_{form}"' in body and 'f"oraclectrl_{form}"' in body, (
        "one ceiling PER FORM plus its matched-n control (NF-D16 g‴ / NF1.9 (f))")


# ── §7.2 the shape-matched null is for VARIANCE statistics ONLY ────────────────────────────────

def test_the_variance_statistic_uses_a_shape_matched_null_and_pit_does_not():
    body = re.search(r"def shape_matched_null\(.*?\n(?=\ndef )", CODE, re.S).group(0)
    assert "z.std(ddof=1)" in body and "z.mean()" in body, (
        "the shape-matched null rescales the OBSERVED residuals to variance exactly 1 (MH2.10)")
    # ⭐ WIRED != INVOKED (NF-C0e): the rescaling existing is not the rescaled residuals being
    #    DRAWN. The first cut asserted only the former and stayed GREEN when the draw was swapped
    #    for a Normal one — found by the RED proof, not by 21 green tests.
    assert "z0[rng.integers" in body, (
        "the draw must RESAMPLE the rescaled observed residuals — a Normal-drawn null is exactly "
        "the MH2.10 defect (it is too narrow for a variance statistic on a skewed target)")
    assert "rng.standard_normal" not in body, (
        "a variance statistic must NEVER sit in a Normal-drawn null (MH2.10)")
    sa = re.search(r"def score_arms\(.*?\n(?=def _fold_clause)", CODE, re.S).group(0)
    assert "floors[VARIANCE_STAT] = floor_of({VARIANCE_STAT: var_null}" in sa
    assert "calibrated_null(mu, sigma, block" in sa, "PIT/coverage keep the STANDARD null"


# ── §10 SCOPE — discrimination is read by no gate ──────────────────────────────────────────────

def test_no_gate_reads_a_discrimination_statistic(M):
    body = re.search(r"def score_arms\(.*?\n(?=def _fold_clause)", CODE, re.S).group(0)
    for stat in M.DISCRIMINATION_STATS:
        assert stat not in body, f"{stat} is ARM-INVARIANT and must not gate anything (§10)"
    assert re.search(r"def location_probe\(", CODE), "it is REPORTED, in its own probe"
    lp = re.search(r"def location_probe\(.*?\n(?=\ndef )", CODE, re.S).group(0)
    assert '"read_by_any_gate": False' in lp and '"retest_trigger": None' in lp


def test_mu_is_held_at_the_served_value_for_every_arm(M):
    rng = np.random.default_rng(0)
    n = 320
    mu = 8.6 + 0.5 * rng.standard_normal(n)
    sigma = 4.3 + 0.2 * np.abs(rng.standard_normal(n))
    y = np.round(mu + sigma * rng.standard_normal(n))
    dates = (np.datetime64("2026-06-23") + (np.arange(n) // 8).astype("timedelta64[D]"))
    block = M.date_blocks(dates, k=M.N_BLOCKS)
    arms, _, _ = M.build_arms(y, mu, sigma, block, seed=1)
    for name, arm in arms.items():
        assert np.array_equal(arm.mu, mu), f"{name} moved mu — every arm holds it at the served value"


# ── the classifier is consumed correctly ───────────────────────────────────────────────────────

def test_classify_null_is_passed_the_declared_field_size_and_the_v_convention():
    body = re.search(r"def classify\(.*?\n(?=\ndef )", CODE, re.S).group(0)
    assert "declared_field_size=DECLARED_FIELD_SIZE" in body, (
        "classify_null must be told the DECLARED field size (MH2.7)")
    assert "degenerates_excluded_from_v=DEGENERATES_EXCLUDED_FROM_V" in body
    assert "pbo_application=PBO_APPLICATION" in body


def test_a_hard_constraint_binds_and_publishes_no_data_retest_trigger():
    body = re.search(r"def classify\(.*?\n(?=\ndef )", CODE, re.S).group(0)
    assert '"CONSTRAINT_REFUSED"' in body and 'out["retest_trigger"] = None' in body, (
        "a deterministic-constraint refusal must NOT publish a fold/season trigger (NF-D18)")


def test_the_replication_leg_is_the_stop_gate_and_fresh_cannot_trigger_it():
    body = re.search(r"def replication\(.*?\n(?=\ndef )", CODE, re.S).group(0)
    assert 'out["binding_read"] = "FULL_ERA"' in body
    assert 'out["fresh_can_trigger_stop"] = False' in body, (
        "the 93-row FRESH slice is UNDERPOWERED BY DESIGN and cannot trigger STOP (§3.3)")
    run = re.search(r"def run\(.*?\n(?=\ndef )", CODE, re.S).group(0)
    assert '"STOP_PREMISE_FAILED"' in run and "return out" in run
