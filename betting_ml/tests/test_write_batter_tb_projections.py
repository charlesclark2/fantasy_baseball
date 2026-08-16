"""test_write_batter_tb_projections.py — E5.9 daily batter-TB writer + champion fit guards.

Three concern groups:
  1. TRAIN/SERVE CONSISTENCY at the unit level: the fit script's champion is byte-equivalent to
     the Phase-2 harness arm (same GLM config, same design state, same NB2 pmf), and the bundle's
     stored design state reconstructs the fit-time standardization exactly.
  2. The E7.9 comparator (`compare_feature_frames`) is RED-provable: it fails on a perturbed
     column, a one-sided NaN, a missing column, and an EMPTY comparison (a check that compares
     nothing must not pass — NF1.7 (a)).
  3. Source-inspection guards on the writer: lakehouse reads go through register_lakehouse_views
     (no hardcoded lakehouse glob — the phase-1.5 P0), the substrate's OWN name-folding and
     hand-collapse are IMPORTED (not re-implemented), and no market/price column ever appears
     (market-blind).

All pure/synthetic — no network, no S3 (fast gate).
"""

from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from betting_ml.scripts.batter_props_phase2_bakeoff import (
    NUMERIC_FEATURES,
    Design,
    build_design,
    nb_pmf_grid,
)
from betting_ml.scripts.prop_pricing.fit_batter_tb import MARKET, fit_bundle

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WRITER = _REPO_ROOT / "scripts" / "write_batter_tb_projections.py"


# ---------------------------------------------------------------------------
# synthetic substrate
# ---------------------------------------------------------------------------

def _synthetic_substrate(n: int = 12_000, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({c: rng.normal(size=n) for c in NUMERIC_FEATURES})
    df["batting_slot"] = rng.integers(1, 10, size=n).astype(float)
    df["batter_hand"] = rng.choice(["L", "R", "S"], size=n)
    # a real signal so the GLM has something to fit
    mu = np.exp(0.3 + 0.25 * df["eb_woba"].to_numpy() + 0.15 * df["prev_slg_30d"].to_numpy())
    df["y_actual"] = rng.poisson(np.clip(mu, 0.05, 8.0)).astype(float)
    df["market_key"] = MARKET
    df["game_date"] = pd.to_datetime("2024-04-01") + pd.to_timedelta(
        rng.integers(0, 700, size=n), unit="D")
    # sprinkle NaNs so the median-impute path is exercised
    df.loc[df.sample(frac=0.05, random_state=1).index, "eb_woba"] = np.nan
    df.loc[df.sample(frac=0.05, random_state=2).index, "prev_woba_30d"] = np.nan
    return df


# ---------------------------------------------------------------------------
# 1 — fit ↔ harness ↔ serve equivalence
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def bundle_and_data():
    df = _synthetic_substrate()
    return fit_bundle(df, "synthetic://test"), df


def test_bundle_shape_and_version_stamp(bundle_and_data):
    bundle, _ = bundle_and_data
    assert bundle["model_version"] == "batter_tb_glm_nb_v1"
    assert bundle["market"] == MARKET
    assert bundle["grid_cap"] == 24
    assert bundle["features"] == list(NUMERIC_FEATURES)
    assert bundle["nb_alpha"] > 0
    assert bundle["best_alpha"] == 0
    f = bundle["fit"]
    assert f["n_rows"] == 12_000 and f["fit_date"] and f["fitted_at"]
    assert "refit_cadence_days" in bundle and "stale_after_days" in bundle


def test_fit_matches_harness_arm(bundle_and_data):
    """The persisted champion's mean model must be the harness `_fit_poisson_mu` config exactly
    (a hyperparameter drift between research and serving goes red here)."""
    from betting_ml.scripts.batter_props_phase2_bakeoff import _fit_poisson_mu
    bundle, df = bundle_and_data
    d = df[(df["market_key"] == MARKET) & df["y_actual"].notna()]
    X, _ = build_design(d)
    y = d["y_actual"].to_numpy(float)
    np.random.seed(20260814)
    _, mu_harness = _fit_poisson_mu(X, y, X)
    mu_bundle = bundle["model"].predict(X)
    np.testing.assert_allclose(mu_bundle, mu_harness, rtol=1e-8, atol=1e-10)


def test_design_state_round_trips_through_the_bundle(bundle_and_data):
    """Reconstructing Design from the bundle's plain values must reproduce the fit-time matrix
    (the E7.9 standardization-state contract the serving writer depends on)."""
    bundle, df = bundle_and_data
    d = df[(df["market_key"] == MARKET) & df["y_actual"].notna()]
    X_fit, design_fit = build_design(d)
    b = bundle["design"]
    design_rt = Design(medians=pd.Series(b["medians"], dtype=float),
                       mean=np.asarray(b["mean"], float), std=np.asarray(b["std"], float))
    X_rt, _ = build_design(d, design_rt)
    np.testing.assert_allclose(X_rt, X_fit, rtol=1e-12, atol=1e-12)
    # and it applies to UNSEEN rows without refitting state
    X_new, _ = build_design(d.head(50), design_rt)
    np.testing.assert_allclose(X_new, X_rt[:50], rtol=1e-12, atol=1e-12)


def test_serve_pmf_is_the_harness_pmf(bundle_and_data):
    """The serving path's predictive (nb_pmf_grid(model.predict, alpha, cap)) is EXACTLY the
    harness glm_nb arm's predictive for the same inputs — rows sum to 1, tail folded."""
    bundle, df = bundle_and_data
    d = df.head(200)
    b = bundle["design"]
    design = Design(medians=pd.Series(b["medians"], dtype=float),
                    mean=np.asarray(b["mean"], float), std=np.asarray(b["std"], float))
    X, _ = build_design(d, design)
    mu = np.clip(bundle["model"].predict(X), 1e-4, None)
    pmf = nb_pmf_grid(mu, bundle["nb_alpha"], bundle["grid_cap"])
    assert pmf.shape == (200, 25)
    np.testing.assert_allclose(pmf.sum(axis=1), 1.0, atol=1e-9)


def test_fit_refuses_partial_substrate():
    df = _synthetic_substrate(n=500)
    with pytest.raises(RuntimeError, match="partial substrate"):
        fit_bundle(df, "synthetic://tiny")


# ---------------------------------------------------------------------------
# 2 — the E7.9 comparator is RED-provable
# ---------------------------------------------------------------------------

def _merged_frames(n: int = 100, seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    base = pd.DataFrame({c: rng.normal(size=n) for c in NUMERIC_FEATURES})
    merged = pd.concat(
        [base.add_suffix("_sub"), base.add_suffix("_srv")], axis=1)
    return merged


def test_comparator_passes_on_identical_frames():
    from scripts.write_batter_tb_projections import compare_feature_frames
    failures, report = compare_feature_frames(_merged_frames())
    assert failures == []
    assert len(report) == len(NUMERIC_FEATURES)


def test_comparator_fails_on_perturbed_column():
    from scripts.write_batter_tb_projections import compare_feature_frames
    merged = _merged_frames()
    merged.loc[merged.index[:5], "prev_woba_30d_srv"] += 1.0  # 5% of 100 rows off
    failures, _ = compare_feature_frames(merged, min_match_rate=0.98)
    assert any(f.startswith("prev_woba_30d") for f in failures)


def test_comparator_both_nan_matches_one_sided_nan_fails():
    from scripts.write_batter_tb_projections import compare_feature_frames
    merged = _merged_frames()
    merged.loc[:, "eb_woba_sub"] = np.nan
    merged.loc[:, "eb_woba_srv"] = np.nan          # both NaN — a match
    failures, _ = compare_feature_frames(merged)
    assert not any(f.startswith("eb_woba:") for f in failures)
    merged.loc[merged.index[:10], "eb_iso_srv"] = np.nan  # one-sided NaN — a mismatch
    failures, _ = compare_feature_frames(merged, min_match_rate=0.98)
    assert any(f.startswith("eb_iso") for f in failures)


def test_comparator_fails_on_missing_column():
    from scripts.write_batter_tb_projections import compare_feature_frames
    merged = _merged_frames().drop(columns=["batting_slot_srv"])
    failures, _ = compare_feature_frames(merged)
    assert any("batting_slot" in f and "missing" in f for f in failures)


def test_comparator_refuses_empty_comparison():
    """A comparison over ZERO rows must FAIL, never pass — NF1.7 (a): an anchor that compares
    nothing is vacuously true and worth nothing."""
    from scripts.write_batter_tb_projections import compare_feature_frames
    failures, _ = compare_feature_frames(_merged_frames(n=0))
    assert failures  # every column fails on an empty frame


# ---------------------------------------------------------------------------
# 3 — writer source-inspection guards (AST-based, never prose-matchable — INC-38)
# ---------------------------------------------------------------------------

def _writer_imports() -> set[tuple[str, str]]:
    tree = ast.parse(_WRITER.read_text(encoding="utf-8"))
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                out.add((node.module, alias.name))
    return out


def test_writer_reuses_substrate_semantics_by_import():
    """The hand-collapse and the quote-folded name keys must be IMPORTED from the substrate
    builder — a re-implementation could silently diverge from the training semantics."""
    imports = _writer_imports()
    assert ("scripts.build_batter_prop_substrate", "build_rolling_features") in imports
    assert ("scripts.build_batter_prop_substrate", "_name_key") in imports
    assert ("scripts.build_batter_tb_substrate", "_name_key") not in imports  # anti-typo
    assert ("scripts.build_batter_prop_substrate", "_li_key") in imports


def test_writer_scores_through_the_harness():
    imports = _writer_imports()
    assert ("betting_ml.scripts.batter_props_phase2_bakeoff", "build_design") in imports
    assert ("betting_ml.scripts.batter_props_phase2_bakeoff", "nb_pmf_grid") in imports
    assert ("betting_ml.scripts.batter_props_phase2_bakeoff", "NUMERIC_FEATURES") in imports


def test_writer_has_no_hardcoded_lakehouse_glob():
    """Lakehouse reads must route through register_lakehouse_views (the phase-1.5 P0 rule) —
    a `lakehouse/<table>/**` glob in this writer is a regression."""
    src = _WRITER.read_text(encoding="utf-8")
    # strip comments/docstrings so prose can't trip (or satisfy) the guard
    tree = ast.parse(src)
    strings = [n.value for n in ast.walk(tree)
               if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    offenders = [s for s in strings if "baseball/lakehouse/" in s and "*" in s]
    assert not offenders, f"hardcoded lakehouse glob(s) in writer: {offenders}"
    assert "register_lakehouse_views" in src


def test_writer_is_market_blind():
    """No price/benchmark column may appear anywhere in the writer's CODE (market-blind §5):
    prices are joined for the transparency comparison AFTER scoring, keyed only as book-line
    payload fields — never as substrate column names."""
    tree = ast.parse(_WRITER.read_text(encoding="utf-8"))
    strings = {n.value for n in ast.walk(tree)
               if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    forbidden = {"line_consensus", "p_over_consensus", "p_over_std", "n_books_two_sided"}
    hits = {f for f in forbidden
            if f in names or any(f in s for s in strings if len(s) < 500)}
    assert not hits, f"market/price columns referenced in the serving writer: {hits}"


# ---------------------------------------------------------------------------
# E5.10 — population members whose SIDE is unknown must never be served
#
# The writer's population is the posted lineup UNION the EB posterior build. EB carries no
# team/home_away column (verified against the live table), so an EB-only batter has no
# determinable side and would render as "Unknown matchup" — a group header with neither team
# named. Observed live on 2026-08-15. These cannot be exercised by a real run (the live slate
# has EB and lineups landing together), which is exactly why they are unit tests.
# ---------------------------------------------------------------------------

def _load_side_helper():
    """Import `pairs_with_a_known_side` by path — the writer is a script, not a package
    module, and importing it wholesale would pull heavy deps into the fast gate."""
    src = _WRITER.read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(n for n in tree.body
              if isinstance(n, ast.FunctionDef) and n.name == "pairs_with_a_known_side")
    ns: dict = {}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), str(_WRITER), "exec"), ns)
    return ns["pairs_with_a_known_side"]


def test_a_batter_in_the_lineup_is_servable():
    keep, drop = _load_side_helper()(
        {(1, 100), (1, 101)},
        {1: {100: {"is_home": True}, 101: {"is_home": False}}},
    )
    assert keep == {(1, 100), (1, 101)}
    assert drop == []


def test_an_eb_only_batter_is_dropped_because_the_card_would_say_unknown_matchup():
    """The RED-provable core: batter 202 is in the population (EB) but not in any lineup, so
    team/opponent are unknowable. Deleting the filter makes this assertion fail."""
    keep, drop = _load_side_helper()(
        {(2, 200), (2, 202)},
        {2: {200: {"is_home": True}}},
    )
    assert keep == {(2, 200)}, "an EB-only batter must not be served"
    assert drop == [(2, 202)]


def test_a_game_with_no_posted_lineup_at_all_is_dropped_whole():
    """EB built before any lineup posted (the two 2026-08-15 late games): no batter in that
    game has a side, so the whole game is withheld rather than shipped unnamed."""
    keep, drop = _load_side_helper()(
        {(3, 300), (3, 301), (4, 400)},
        {4: {400: {"is_home": True}}},
    )
    assert keep == {(4, 400)}
    assert drop == [(3, 300), (3, 301)]


def test_the_filter_is_not_vacuous_on_an_empty_population():
    """An empty population must yield an empty result, not silently pass everything through
    (NF1.7 (a) — a check that filters nothing has not been exercised)."""
    keep, drop = _load_side_helper()(set(), {1: {100: {"is_home": True}}})
    assert keep == set()
    assert drop == []


# ---------------------------------------------------------------------------
# E5.10 — display-name picking. The posted-lineup feed carries one row per slot per game, so
# one batter_id can arrive with several spellings; the served name must be deterministic (a
# re-run flipping a name is a user-visible change with no cause). Both cases below are REAL
# spellings observed on the 2026-08-15 slate.
# ---------------------------------------------------------------------------

def _load_name_picker():
    src = _WRITER.read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(n for n in tree.body
              if isinstance(n, ast.FunctionDef) and n.name == "pick_display_name")
    ns: dict = {"Sequence": list}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), str(_WRITER), "exec"), ns)
    return ns["pick_display_name"]


def test_a_suffix_spelling_wins_over_the_bare_name():
    """`George Lombard Jr.` / `George Lombard` — the suffix is the more precise identity."""
    assert _load_name_picker()(["George Lombard", "George Lombard Jr."]) == "George Lombard Jr."


def test_internal_double_spacing_collapses_to_one_name():
    """`Hao-Yu  Lee` (double space) and `Hao-Yu Lee` are ONE player, not two spellings."""
    assert _load_name_picker()(["Hao-Yu  Lee", "Hao-Yu Lee"]) == "Hao-Yu Lee"


def test_the_pick_is_order_independent():
    """Feed order is an accident of the slot union — it must not decide the served name."""
    pick = _load_name_picker()
    assert pick(["George Lombard", "George Lombard Jr."]) == pick(
        ["George Lombard Jr.", "George Lombard"])


def test_blank_and_missing_spellings_yield_no_name_rather_than_an_empty_string():
    """An empty string would serve a nameless card; the caller must see None and skip."""
    pick = _load_name_picker()
    assert pick([]) is None
    assert pick(["", "   ", None]) is None
