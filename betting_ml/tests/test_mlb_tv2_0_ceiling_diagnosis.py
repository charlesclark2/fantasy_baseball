"""MLB-TV2-0 — guards for the totals-ceiling diagnosis.

Every guard here is RED-proven by `betting_ml/tests/mlb_tv2_0_red_proof.py`: the mutation is
asserted to LAND ON DISK, its anchor is asserted UNIQUE (#682 / the byte-identical-tail trap), and
the asserted token is checked ABSENT afterwards (#815) — a break that lands but does not move the
predicate is a false GREEN.

⛔ Fast gate: this file must not import `pipeline` (E11.23) and must not touch the network.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import numpy as np
import pytest

import betting_ml.scripts.mlb_tv2_0_ceiling_diagnosis as M

ROOT = Path(__file__).resolve().parents[2]
SRC = Path(M.__file__).read_text()
PREREG = ROOT / "ablation_results" / "mlb_tv2_0_prereg.md"


def _strip_comments(src: str) -> str:
    """Comment-stripped source — prose must never satisfy a source guard (INC-38).

    ⚠️ TOKENISED, not a regex: a `#` inside a string literal is not a comment, and stripping it
    with `re.sub(r"#.*$", ...)` truncates multi-line f-strings into a SyntaxError — which would
    make every downstream guard error out rather than assert.
    """
    import io
    import tokenize
    out, last = [], (1, 0)
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type == tokenize.COMMENT:
            continue
        (sr, sc), (er, ec) = tok.start, tok.end
        while last[0] < sr:
            out.append("\n")
            last = (last[0] + 1, 0)
        out.append(" " * max(0, sc - last[1]))
        out.append(tok.string)
        last = (er, ec)
    return "".join(out)


def _no_docstrings(src: str) -> str:
    """Source with every docstring removed — a docstring naming a token is not a USE of it."""
    tree = ast.parse(src)
    spans = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            b = node.body
            if b and isinstance(b[0], ast.Expr) and isinstance(b[0].value, ast.Constant) \
                    and isinstance(b[0].value.value, str):
                spans.append((b[0].lineno, b[0].end_lineno))
    lines = src.splitlines()
    keep = [ln for i, ln in enumerate(lines, 1)
            if not any(a <= i <= b for a, b in spans)]
    return "\n".join(keep)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# ⛔ MARKET-BLIND — the story's hardest prohibition
# ══════════════════════════════════════════════════════════════════════════════════════════════

_MARKET_STEMS = ("total_line", "over_prob", "bovada", "odds", "consensus", "devig", "vig",
                 "market_prob", "closing", "book", "moneyline", "juice", "clv")


def _read_tokens(src: str) -> set[str]:
    """Every identifier, attribute and COLUMN-SHAPED string literal in the source.

    ⚠️ A bare substring scan is PROSE-BLIND in the dangerous direction: this module's own honest
    disclaimer ("no edge, win rate, ROI or CLV claim") tripped the first cut, and the cheapest way
    to make that guard pass would have been to DELETE the sentence that makes the record honest
    (the NF-C6P3 negation-blind-scan family). A market column is READ as an identifier, an
    attribute, or a whitespace-free string key — report prose always has spaces. The pull SQL is
    itself whitespace-bearing and is covered by its own guard below.
    """
    tree = ast.parse(src)
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            out.add(node.id.lower())
        elif isinstance(node, ast.Attribute):
            out.add(node.attr.lower())
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value and not any(c.isspace() for c in node.value):
                out.add(node.value.lower())
    return out


def test_the_harness_reads_no_market_column_anywhere():
    """⛔ MARKET-BLIND. The MLB-ODDS1 coverage defects make any market-referenced leg unreliable,
    and none is needed: the serving-relevant probability is read AT THE MODEL'S OWN MEAN."""
    toks = _read_tokens(SRC)
    hits = sorted({f"{st}->{t}" for st in _MARKET_STEMS for t in toks if st in t})
    assert hits == [], f"market stem(s) reached a READ: {hits}"


def test_the_market_blind_guard_is_not_vacuous():
    """RED-proof in-line: the guard must FIRE on a real market read, and must NOT fire on prose."""
    assert _read_tokens('x = df["bovada_devig_over_prob"]') & {"bovada_devig_over_prob"}
    prose = 'def f():\n    """no edge, win rate, ROI or CLV claim."""\n    return 1\n'
    toks = _read_tokens(prose)
    assert not any(st in t for st in _MARKET_STEMS for t in toks), \
        "the guard must not fire on an honest disclaimer"


def test_the_sql_reads_only_the_two_market_blind_tables():
    assert M._TABLES == ("daily_model_predictions", "mart_game_results")
    sql = M._PULL_SQL.lower()
    assert "join" in sql and "mart_game_results" in sql
    for st in _MARKET_STEMS:
        assert st not in sql, f"market stem {st!r} in the pull SQL"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The prereg and its code twin may not drift apart
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_prereg_document_matches_the_registered_battery():
    doc = PREREG.read_text()
    for arm in M.ARMS:
        assert arm in doc, f"arm {arm} is not named in the pre-registration"
    for outcome in M.OUTCOMES:
        assert outcome in doc, f"outcome {outcome} is not named in the pre-registration"
    for bar, name in ((M.RULE_MAJORITY, "majority"), (M.RULE_MATERIAL, "in-play")):
        assert f"{bar:.2f}" in doc, \
            f"the {name} bar {bar} is not stated in the pre-registration"
    assert f"{M.CONTROL_SIGMA_CV}" in doc and f"{int(M.CONTROL_SKEW_ALPHA)}" in doc
    assert "AMENDMENT" in doc and "the node-2 redesign" in doc, \
        "the node-2 amendment is missing from the prereg"


def test_every_route_is_registered_and_the_irreducible_route_unholds_the_calibrator():
    assert set(M.ROUTES) == set(M.OUTCOMES)
    assert "TV2-1" in M.ROUTES["FEATURE-BOUND"]
    assert "TV2-2" in M.ROUTES["SHAPE-BOUND"]
    assert "E13.6b" in M.ROUTES["IRREDUCIBLE"]
    # INDETERMINATE must route conservatively — never to a lever the outcomes did not license.
    assert "IRREDUCIBLE" in M.ROUTES["INDETERMINATE"]
    assert "TV2-1" not in M.ROUTES["INDETERMINATE"] and "TV2-2" not in M.ROUTES["INDETERMINATE"]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The oracles must behave like ORACLES
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_the_scale_mixture_oracle_is_inert_when_there_is_no_per_game_scale_signal():
    """⭐ The property that makes it a CEILING rather than a degenerate: given a constant true
    scale, BIC returns K = 1, the posterior scale is CONSTANT and the oracle collapses onto A1.
    A binned clairvoyant manufactures dispersion out of pure noise instead (prereg §12.1)."""
    z = np.random.default_rng(0).normal(size=3000)
    ora = M.ScaleMixtureOracle(z)
    assert ora.K == 1
    sc = ora.scale(z)
    assert float(np.std(sc)) == pytest.approx(0.0, abs=1e-12)


def test_the_scale_mixture_oracle_recovers_a_real_per_game_scale_signal():
    rng = np.random.default_rng(1)
    f = np.exp(0.34 * rng.normal(size=4000) - 0.5 * 0.34 ** 2)
    ora = M.ScaleMixtureOracle(f * rng.normal(size=4000))
    assert ora.K >= 2
    assert float(np.std(ora.scale(f * rng.normal(size=4000)))) > 0.05


def test_the_symmetry_gate_closes_on_skew_and_opens_on_a_real_scale_mixture():
    """⭐ A genuine per-game scale mixture is SYMMETRIC; skew is not. Without this gate a skewed
    but homoscedastic sample opened a peek the oracle profited from (prereg §12.1, 20% of draws)."""
    from scipy.stats import skewnorm
    rng = np.random.default_rng(2)
    a = 6.0
    d = a / np.sqrt(1 + a * a)
    sk = (skewnorm.rvs(a, size=6000, random_state=rng) - d * np.sqrt(2 / np.pi)) \
        / np.sqrt(1 - 2 * d * d / np.pi)
    gated = M.ScaleMixtureOracle(sk)
    assert gated.K == 1, "the symmetry gate must close on a pure skew defect"
    assert min(gated.K_sides) < 2, "one side must fail to prefer K >= 2 under skew"

    f = np.exp(0.4 * rng.normal(size=6000) - 0.08)
    mix = M.ScaleMixtureOracle(f * rng.normal(size=6000))
    assert mix.K >= 2, "the gate must OPEN on a real symmetric scale mixture"
    assert min(mix.K_sides) >= 2


def test_every_arm_holds_mu_exactly_at_the_served_value():
    """The whole battery's separation rests on this: only the SCALE and the SHAPE ever change."""
    rng = np.random.default_rng(3)
    n = 400
    mu = 8.9 + 0.5 * rng.normal(size=n)
    sigma = np.full(n, 4.3)
    y = np.round(mu + sigma * rng.normal(size=n))
    block = np.repeat(np.arange(M.N_BLOCKS), n // M.N_BLOCKS)
    arms, _ = M.build_arms(y, mu, sigma, block, np.random.default_rng(4))
    for name, arm in arms.items():
        assert np.array_equal(arm.mu, mu), f"{name} moved mu"


def test_the_row_blind_control_shares_the_oracle_machinery():
    """A closure bought by CAPACITY rather than by information shows up here (NF-W7f)."""
    src = _no_docstrings(_strip_comments(SRC))
    assert "A_ctrl_permuted" in src
    assert "z_perm" in src and "rng.permutation" in src


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The instruments
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_the_randomized_pit_is_exactly_uniform_under_a_correct_predictive():
    """`round(Normal)` + a continuity-corrected randomized PIT is EXACTLY uniform at any scale —
    which is what makes the calibrated-null floor also the distribution-free construction floor."""
    from scipy.stats import kstest
    rng = np.random.default_rng(5)
    n = 20000
    mu = 9.0 + rng.normal(size=n)
    sigma = np.full(n, 4.4)
    y = np.round(rng.normal(mu, sigma))
    arm = M.Arm("i", mu, sigma, [M.NormalLaw()], np.zeros(n, int))
    u = M.randomized_pit(y, arm, rng)
    assert kstest(u, "uniform").pvalue > 0.01


def test_the_pit_uniforms_are_shared_across_arms_so_the_comparison_is_paired():
    """Independent randomisation per arm injects noise into the DIFFERENCE that has nothing to do
    with the arms — it inflated the paired CI and cost real detection power."""
    src = _no_docstrings(_strip_comments(SRC))
    assert "u_shared" in src, "score() must draw ONE uniform vector for every arm"
    assert re.search(r"arm_stats\(y,\s*arms\[a\],\s*None,\s*u=u_shared\)", src)
    assert re.search(r"arm_rows\(y,\s*arms\[a\],\s*u=u_shared\)", src)


def test_the_crps_grid_reproduces_the_normal_closed_form():
    rng = np.random.default_rng(6)
    n = 2000
    mu = 9.0 + rng.normal(size=n)
    sigma = 4.2 + 0.2 * rng.normal(size=n)
    y = np.round(rng.normal(mu, sigma))
    arm = M.Arm("i", mu, sigma, [M.NormalLaw()], np.zeros(n, int))
    assert abs(M.crps_grid(y, arm) - M.crps_normal_closed(y, mu, sigma)) < M.CRPS_VALIDATION_TOL


def test_the_empirical_law_is_a_monotone_invertible_quantile_function():
    rng = np.random.default_rng(7)
    law = M.EmpiricalLaw(rng.normal(size=1500))
    # ⚠️ The grid MUST reach outside `[p_lo, p_hi]` or the Gaussian tail extension is never
    # exercised and the guard passes on the body alone — the CRPS grid reads levels this extreme.
    assert 1e-4 < law.p_lo and law.p_hi < 1 - 1e-4, "the fixture must straddle the tails"
    p = np.concatenate([np.linspace(1e-5, 0.999995, 600), [1e-6, 1 - 1e-6]])
    p.sort()
    q = law.ppf(p)
    assert np.all(np.diff(q) > 0), "the quantile function must be strictly increasing"
    assert np.allclose(law.cdf(q), p, atol=5e-3)


def test_date_blocks_never_split_a_slate_across_two_blocks():
    """⚠️ The slate sizes must be RAGGED and must not divide the block edges evenly, or the blocks
    align with day boundaries by arithmetic accident and the guard passes on nothing."""
    sizes = [7, 13, 11, 9, 15, 8, 12, 14, 10, 6, 16, 9, 13, 7, 11, 12, 8, 15, 10, 9]
    days = np.concatenate([np.full(n, np.datetime64("2026-07-01") + np.timedelta64(i, "D"))
                           for i, n in enumerate(sizes)])
    block = M.date_blocks(days)
    assert len(set(block)) == M.N_BLOCKS, "the fixture must actually produce every block"
    for day in np.unique(days):
        assert len(set(block[days == day])) == 1, f"slate {day} straddles two blocks"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The rule
# ══════════════════════════════════════════════════════════════════════════════════════════════

def _dec(**kw):
    """A decision built from explicit lever readings — one isolating fixture PER clause (NF-D17)."""
    stats = {a: {k: 1.0 for k in M.REPORT_STATS} for a in M.ARMS}
    for a in M.ARMS:
        stats[a]["p_over_gap"] = 0.0
        stats[a]["p_over_stated"] = 0.5
    return stats


def test_the_rule_refuses_to_run_on_a_non_defect():
    """⛔ PRECONDITION. A closure share computed against a `gap` that is itself noise is the
    NF1.7 (a) vacuous anchor."""
    src = _no_docstrings(_strip_comments(SRC))
    assert 'outcome = "NO_MEASURABLE_DEFECT"' in src
    assert "joint_material" in src and "any_failure" in src


def test_the_feature_lever_is_inadmissible_on_the_asymmetry_statistic():
    """A SYMMETRIC scale deficit cannot move the asymmetry, so scoring the feature lever there
    would register a gate the arm cannot move (NF-MARGIN2)."""
    assert M.LEVER_STATS["feature"] == (M.CRPS_STAT,)
    assert M.ASYM_STAT not in M.LEVER_STATS["feature"]
    assert M.ASYM_STAT in M.LEVER_STATS["shape"] and M.CRPS_STAT in M.LEVER_STATS["shape"]


def test_the_fidelity_statistic_is_not_a_lever_statistic():
    """`pit_ks` is moved by BOTH mechanisms, so it cannot separate them — it is a safeguard only."""
    for lever, stats in M.LEVER_STATS.items():
        assert M.FIDELITY_STAT not in stats, f"{lever} may not be scored on {M.FIDELITY_STAT}"


def test_the_asymmetry_channel_requires_the_incumbent_gap_to_be_materially_non_zero():
    """Without it the channel credits a shape law for FITTING SAMPLE SKEW: under a pure symmetric
    scale deficit the finite-sample z has a nonzero skew that drives BOTH the realized over-rate
    and the fitted median, so they agree in sign ~90% of the time (prereg §12.2.3)."""
    src = _no_docstrings(_strip_comments(SRC))
    assert "gap_material" in src
    assert re.search(r"in_play\s*=\s*bool\(gap_material\s+and\s+mv\[.material.\]\s+and\s+toward_zero\)", src)


def test_the_decomposition_is_hierarchical_and_conservative_toward_the_expensive_lever():
    """The feature lever — the one that needs a whole new data product — must prove it adds BEYOND
    the best marginal shape. Shared credit goes to the CHEAPER mechanism."""
    src = _no_docstrings(_strip_comments(SRC))
    assert '"shape": ("B2_shape_empirical", "A1_sigma_level")' in src
    assert '"feature": ("C1_combined", "B2_shape_empirical")' in src


def test_a_lever_counts_only_on_a_paired_ci_that_excludes_zero():
    lo_hi = M.paired_lift_ci.__doc__
    assert "PAIRED" in lo_hi
    src = _no_docstrings(_strip_comments(SRC))
    assert re.search(r'r\["in_play"\]\s*=\s*bool\(r\["material"\]\s+and\s+r\["point"\]\s*>\s*0\)', src)


def test_the_control_bars_are_design_quantities_fixed_in_the_prereg():
    doc = PREREG.read_text()
    for bar in (M.CONTROL_ROUTE_BAR, M.CONTROL_WRONG_LEVER_BAR, M.CONTROL_CLEAN_BAR):
        assert any(f"**{op} {v}**" in doc for op in ("≥", "≤")
                   for v in (f"{bar}", f"{bar:.2f}")), f"bar {bar} not stated in §12.3"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# ⭐ The reproduction pin
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_the_whole_battery_reproduces_to_1e_9_on_the_committed_fixture():
    fx = json.loads(M._FIXTURE.read_text())
    got = M.fixture_run(fx)
    for k, want in fx["expected"].items():
        if isinstance(want, float):
            assert abs(want - got[k]) <= 1e-9, f"{k}: {want} vs {got[k]}"
        else:
            assert want == got[k], f"{k}: {want} vs {got[k]}"


def test_the_fixture_is_not_vacuous():
    """A pin on a frame with nothing to find would pass whatever the battery did."""
    fx = json.loads(M._FIXTURE.read_text())
    assert len(fx["y"]) >= 300
    assert fx["expected"]["outcome"] in M.OUTCOMES
    assert fx["expected"]["outcome"] != "NO_MEASURABLE_DEFECT"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The flagged binding clause
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_std_pred_is_reported_under_both_readings_and_never_enters_the_rule():
    """⚠️ The spec's `std_pred` names two statistics. The 0.773-vs-2.0 figure it cites is the
    MEAN-SPREAD one — a property of mu, which every arm holds fixed — so it is ARM-INVARIANT and
    reporting it as a leg outcome would ship a gate that is décor (NF-MARGIN2)."""
    rng = np.random.default_rng(8)
    mu = 9.0 + 0.6 * rng.normal(size=500)
    sigma = np.full(500, 4.4)
    lp = M.location_probe(np.round(rng.normal(mu, sigma)), mu, sigma)
    assert "std_pred_meanspread" in lp and "std_pred_predictive_sd" in lp
    assert lp["std_pred_meanspread_v2_gate"] == 2.0
    assert lp["arm_invariant_by_construction"] is True
    assert lp["null_state_hand_recorded"] == "INACTIVE (structural)"
    src = _no_docstrings(_strip_comments(SRC))
    rule = src[src.index("def decide("):src.index("def score(")]
    assert "std_pred" not in rule, "std_pred must never enter the decision rule"


def test_an_inactive_lever_null_publishes_no_retest_trigger():
    """⛔ NF-D18: the remedy for an INACTIVE null is a different POPULATION, never more games."""
    d = {"levers": {n: {"in_play": False, "share": 0.0} for n in ("feature", "shape")}}
    out = M.classify_levers(d, {"A3_all_blocks_single_component": True})
    assert out["feature"]["state"] == "INACTIVE"
    # An INACTIVE remedy names a different POPULATION. It must never name folds, seasons or games:
    # that is the actively-misleading re-test trigger NF-D18 warns about.
    trig = (out["feature"]["retest_trigger"] or "").lower()
    assert not any(w in trig for w in ("fold", "season", "more game", "more served")), trig
    assert out["std_pred_meanspread"]["state"] == "INACTIVE"
    assert out["std_pred_meanspread"]["hand_recorded"] is True
    assert out["std_pred_meanspread"]["retest_trigger"] is None
