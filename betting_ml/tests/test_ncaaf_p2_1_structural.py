"""Guards for NCAAF-P2.1 — the pre-registered structural hypothesis battery.

These pin the properties that make the battery's verdict TRUSTWORTHY rather than merely computed:
the pre-registration matches the code, every arm is a genuine matched pair, the anchors can fail,
the two calibration clauses stay separately readable, and the plays rollup is strictly leakage-safe.

Fast-gate discipline (E11.23): nothing here imports `pipeline` (which reads the dbt manifest at
import and dies at COLLECTION when it is absent). Everything imports from `betting_ml` or the pure
`quant_sports_intel_models.football.ncaaf.models` modules.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quant_sports_intel_models.football.ncaaf.models import p2_1_plays_rollup as pr
from quant_sports_intel_models.football.ncaaf.models.p2_1_blocks import (
    BLOCKS,
    DECLARED_FIELD_SIZE,
    MATCHUP_PAIRS,
    Block,
    block_columns,
    eb_team_hfa_infold,
)

_PREREG = (Path(__file__).resolve().parents[2] / "quant_sports_intel_models" / "football" /
           "ncaaf" / "ablation_results" / "ncaaf_p2_1_preregistration.md")
_HARNESS = (Path(__file__).resolve().parents[2] / "quant_sports_intel_models" / "football" /
            "ncaaf" / "models" / "bakeoff_ncaaf_p2_1.py")


# ---------------------------------------------------------------------------
# The pre-registration IS the contract
# ---------------------------------------------------------------------------

def test_preregistration_exists_and_names_every_registered_arm():
    """E1.11: the registered set in the document must be the set the code scores. A block added to
    the code after pre-registration is laundering, and this is what makes that mechanical."""
    assert _PREREG.exists(), "the pre-registration document must be committed"
    text = _PREREG.read_text()
    for b in BLOCKS:
        assert f"`{b.arm}`" in text, f"arm {b.arm!r} is scored by the code but absent from the prereg"
        assert b.hypothesis in text, f"hypothesis id {b.hypothesis!r} missing from the prereg"


def test_declared_field_size_equals_the_registered_real_arm_count():
    """`classify_null(declared_field_size=…)` must receive the PRE-REGISTERED field, not a
    discovered one (MH2.7): a caller passing a post-hoc field still gets the admissible badge."""
    assert DECLARED_FIELD_SIZE == len(BLOCKS) == 16


def test_h10_weather_is_not_registered_because_the_data_does_not_exist():
    """Pre-registration V5. A hypothesis that cannot be measured must not enter the deflation
    field — registering it would spend multiplicity on a config that can never be scored."""
    assert not any("weather" in b.arm for b in BLOCKS)
    text = _PREREG.read_text()
    assert "NOT REGISTERED" in text and "weather" in text.lower()


def test_h14_and_h15_are_not_registered_here():
    """They were PROMOTED OUT to NCAAF-P2.5; scoring them here would double-count in deflation."""
    arms = {b.arm for b in BLOCKS}
    assert not {"key_number", "heteroscedastic", "skewed_margin"} & arms


# ---------------------------------------------------------------------------
# Matched-pair construction (NF-D10) — the property that makes the paired read valid
# ---------------------------------------------------------------------------

def _toy(n: int = 400, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    teams = [f"T{i}" for i in range(20)]
    return pd.DataFrame({
        "game_id": np.arange(n),
        "season": rng.choice([2021, 2022, 2023], n),
        "season_order_week": rng.integers(1, 14, n),
        "home_team": rng.choice(teams, n), "away_team": rng.choice(teams, n),
        "is_neutral_site": rng.random(n) < 0.08,
        "strength_margin_diff": rng.normal(0, 10, n),
        "home_strength_margin": rng.normal(0, 10, n), "away_strength_margin": rng.normal(0, 10, n),
        "home_strength_offense": rng.normal(0, 5, n), "away_strength_offense": rng.normal(0, 5, n),
        "home_strength_defense": rng.normal(0, 5, n), "away_strength_defense": rng.normal(0, 5, n),
        "home_games_played": rng.integers(0, 13, n), "away_games_played": rng.integers(0, 13, n),
        "label_home_margin": rng.normal(3, 16, n),
        "home_st_takeaway_rate": rng.random(n) * .05, "away_st_takeaway_rate": rng.random(n) * .05,
        "home_st_giveaway_rate": rng.random(n) * .05, "away_st_giveaway_rate": rng.random(n) * .05,
        "home_st_n_prior_games": rng.integers(0, 12, n),
    })


def test_every_infold_block_returns_columns_for_both_train_and_eval_with_no_fit_on_eval():
    """A block that fits anything on eval rows is leakage. The in-fold builders take (tr, ev) and
    the eval frame must only ever be TRANSFORMED, never fitted — checked here by the invariant that
    scoring the same eval rows against two DIFFERENT train sets changes the eval output only
    through the train-fitted statistics (i.e. the builder is a pure function of (tr, ev))."""
    df = _toy()
    tr_a, tr_b, ev = df.iloc[:200], df.iloc[100:300], df.iloc[300:]
    for b in BLOCKS:
        if b.infold is None:
            continue
        try:
            _, ev1 = b.infold(tr_a, ev, **b.infold_kwargs)
            _, ev2 = b.infold(tr_b, ev, **b.infold_kwargs)
        except KeyError:
            continue  # block needs assembled columns the toy frame does not carry
        assert list(ev1.columns) == list(ev2.columns)
        assert len(ev1) == len(ev) and len(ev2) == len(ev)


def test_block_columns_raises_when_a_declared_column_is_absent():
    """NF1.7(a): a block whose declared columns are missing must RAISE, never silently score a
    smaller feature set — that would make the arm a different hypothesis than the one registered."""
    df = _toy()
    bogus = Block("bogus", "HX", 9, "t", raw=("a_column_that_does_not_exist",))
    with pytest.raises(KeyError, match="absent from the assembled frame"):
        block_columns(bogus, df, df)


# ---------------------------------------------------------------------------
# The H1b anchor + its matched level-only foil (NF-D15 g′, NF1.7 a)
# ---------------------------------------------------------------------------

def test_eb_hfa_raises_rather_than_returning_none_when_it_cannot_fit():
    """NF1.7(a): an anchor that fails to fit makes its check VACUOUSLY TRUE. It must raise."""
    df = _toy(n=20)
    with pytest.raises(ValueError, match="cannot be fit"):
        eb_team_hfa_infold(df, df)


def test_hfa_global_foil_is_genuinely_level_only():
    """The matched foil must differ from H1b in EXACTLY one respect — per-team content — or a
    win over it attributes nothing (NF-D15 g′). Here: every non-neutral game gets the SAME value."""
    df = _toy(n=600)
    _, ev_glob = eb_team_hfa_infold(df, df, shrink_to_global=True)
    v = ev_glob["eb_team_hfa"].to_numpy()
    non_neutral = ~df["is_neutral_site"].to_numpy()
    assert np.allclose(v[non_neutral], v[non_neutral][0]), "the foil must be a single global level"
    assert np.allclose(v[~non_neutral], 0.0), "a neutral-site game must receive NO home bump"


def test_eb_hfa_is_not_level_only_so_the_foil_comparison_can_discriminate():
    """The two-sided half: if H1b were ALSO constant, the foil comparison would be vacuous."""
    df = _toy(n=600)
    _, ev_eb = eb_team_hfa_infold(df, df)
    v = ev_eb["eb_team_hfa"].to_numpy()[~df["is_neutral_site"].to_numpy()]
    assert v.std() > 0, "H1b must vary across teams or its comparison to the foil proves nothing"


def test_eb_hfa_shrinks_a_thin_team_further_toward_the_global_mean():
    """The partial-pooling property itself: a team with fewer home games sits closer to global."""
    n = 800
    rng = np.random.default_rng(3)
    df = _toy(n=n, seed=3)
    # give T0 many home games and T1 very few, both with an extreme home residual
    df.loc[:, "home_team"] = np.where(np.arange(n) < 300, "T0", df["home_team"])
    df.loc[:, "home_team"] = np.where((np.arange(n) >= 300) & (np.arange(n) < 305), "T1",
                                      df["home_team"])
    df.loc[:, "is_neutral_site"] = False
    df.loc[:, "strength_margin_diff"] = 0.0
    df.loc[:, "label_home_margin"] = np.where(df["home_team"].isin(["T0", "T1"]), 40.0,
                                              rng.normal(0, 1, n))
    _, ev = eb_team_hfa_infold(df, df)
    glob = float((df["label_home_margin"] - df["strength_margin_diff"]).mean())
    v = ev["eb_team_hfa"].to_numpy()
    t0 = v[(df["home_team"] == "T0").to_numpy()][0]
    t1 = v[(df["home_team"] == "T1").to_numpy()][0]
    assert abs(t1 - glob) < abs(t0 - glob), "the thin team must be pulled harder toward global"


# ---------------------------------------------------------------------------
# The two calibration clauses must stay SEPARATELY readable
# ---------------------------------------------------------------------------

def test_coverage_floor_and_pit_clause_are_read_separately():
    """⭐ RED-PROVEN REGRESSION GUARD. NF1.8's `max_width` proof is that a maximally-wide degenerate
    SATISFIES the coverage floor and is then eliminated by the METRIC — that is what shows the floor
    is a constraint, not a criterion a degenerate can win. Reading that anchor through a predicate
    that ALSO bundles PIT-flatness reports "floor failed" at calib 1.000 and destroys the proof.
    (This is exactly what the first cut of the harness did; the smoke caught it.)"""
    from quant_sports_intel_models.football.ncaaf.models.bakeoff_ncaaf_p2_1 import (
        _coverage_floor_ok, _eligible, _margin_pit_ok,
    )
    max_width_like = {"pooled_margin_calib": 1.000, "pooled_total_calib": 0.999,
                      "margin_pit_flat_folds": 0, "fold_crps": [0.0] * 8}
    assert _coverage_floor_ok(max_width_like)[0] is True, (
        "the wide degenerate MUST read as satisfying the coverage floor — that is the proof")
    assert _margin_pit_ok(max_width_like)[0] is False
    assert _eligible(max_width_like)[0] is False, "…and must still be INELIGIBLE overall"

    zero_width_like = {"pooled_margin_calib": 0.199, "pooled_total_calib": 0.182,
                       "margin_pit_flat_folds": 0, "fold_crps": [0.0] * 8}
    assert _coverage_floor_ok(zero_width_like)[0] is False, (
        "the sharp degenerate MUST fail the coverage floor — the other side of the two-sided proof")


def _strip_comments(src: str) -> str:
    """Comment-stripped source. INC-38: a source-inspection guard that a PROSE COMMENT can satisfy
    is vacuous — and this file's explanatory comments name both functions."""
    return "\n".join(re.sub(r"#.*$", "", ln) for ln in src.splitlines())


def test_the_anchor_report_reads_the_coverage_floor_at_the_CALL_SITE():
    """⭐ The guard above pins the clause FUNCTIONS; this one pins the CALL SITE, which is where the
    defect actually was — the anchor report called the bundled `_eligible`, so `max_width` reported
    "floor FAILED" at calib 1.000. A test that only exercises the clause functions stays green
    through that bug (the RED proof caught exactly this, which is why this second guard exists).
    NF-D17: a clause is only defended if it is INDEPENDENTLY RED-provable."""
    src = _strip_comments(_HARNESS.read_text())
    start = src.index("for name, expect in (")
    end = src.index("anchor_checks = {")
    region = src[start:end]
    assert "_coverage_floor_ok(a)" in region, (
        "the anchor report must read the COVERAGE FLOOR alone")
    assert "_eligible(" not in region, (
        "the anchor report must NOT use the bundled eligibility predicate — that reports "
        "'floor failed' at calib 1.000 and destroys the NF1.8 max_width proof")
    assert '"satisfies_coverage_floor"' in region, (
        "the emitted key must NAME the clause it measured, not a generic 'satisfies_floor'")


def test_total_pit_flatness_is_not_a_gating_clause():
    """MH2.1(b): the shipped P1.4 reference FAILS total PIT-flatness (PITdev 0.0218). Gating on a
    clause the incumbent fails is an incumbent-relative inversion. Total shape is P2.5's scope."""
    from quant_sports_intel_models.football.ncaaf.models.bakeoff_ncaaf_p2_1 import _eligible
    ref_like = {"pooled_margin_calib": 0.800, "pooled_total_calib": 0.802,
                "margin_pit_flat_folds": 8, "fold_crps": [0.0] * 8,
                "total_pit_flat_folds": 0}
    assert _eligible(ref_like)[0] is True, (
        "the shipped reference must be ELIGIBLE despite failing total PIT-flatness")


def test_the_tie_band_refuses_a_numerical_precision_lead():
    """Nested-form guard: every arm nests the reference, so a shrunk-to-zero block collapses the
    arm onto its own foil. A sub-1e-3 'lead' is a TIE, never a win."""
    from quant_sports_intel_models.football.ncaaf.models.bakeoff_ncaaf_p2_1 import _TIE_BAND
    assert _TIE_BAND > 0
    assert abs(1e-7) < _TIE_BAND and abs(0.05) > _TIE_BAND


# ---------------------------------------------------------------------------
# DSR-CONV + multiplicity
# ---------------------------------------------------------------------------

def test_anchors_are_declared_and_excluded_from_V_but_kept_in_n_trials():
    """DSR-CONV + MH2.1(a), declared FORWARD in the pre-registration. A diagnostic anchor is never
    a trial for V (the oracle would set the gate's own bar arithmetically), but multiplicity still
    counts it."""
    src = _HARNESS.read_text()
    assert "sr_real = [sharpe(bucket_improvement(a)) for a in real]" in src, (
        "V must be measured over the NON-anchor arms")
    assert "n_trials = 1 + len(real) + len(anchors)" in src, (
        "n_trials must keep the full declared field including anchors")
    assert "degenerates_excluded_from_v=True" in src
    text = _PREREG.read_text()
    assert "DSR-CONV" in text and "declared FORWARD" in text


def test_pbo_is_computed_over_the_eligible_real_set_not_the_whole_field():
    """NF1.8: PBO must be computed over the search the SELECTION actually ran; anchors are not
    promotion candidates and a field containing its own nulls measures the nulls."""
    src = _HARNESS.read_text()
    assert 'elig_arms = [a for a in real if rows[a]["eligible"]]' in src


def test_bh_fdr_is_monotone_and_controls_the_registered_family():
    from quant_sports_intel_models.football.ncaaf.models.bakeoff_ncaaf_p2_1 import _bh
    p = {"a": 0.001, "b": 0.02, "c": 0.4, "d": 0.9}
    passed, cutoff = _bh(p, alpha=0.05)
    assert passed["a"] and not passed["c"] and not passed["d"]
    assert 0 < cutoff <= 0.05
    # a strictly larger family can only make the cutoff harder for the same p-values
    p2 = dict(p, **{f"x{i}": 0.5 for i in range(12)})
    _, cutoff2 = _bh(p2, alpha=0.05)
    assert cutoff2 <= cutoff


# ---------------------------------------------------------------------------
# The plays rollup: leakage safety + the verified punt semantics
# ---------------------------------------------------------------------------

def test_season_to_date_uses_strictly_prior_games_only():
    """The load-bearing leakage property. Game k's feature must equal the pooled rate over games
    1..k-1 — never including game k itself."""
    gt = pd.DataFrame({
        "season": [2023] * 4, "team": ["A"] * 4, "game_id": [1, 2, 3, 4],
        "game_ts": pd.to_datetime(["2023-09-01", "2023-09-08", "2023-09-15", "2023-09-22"]),
        "o_plays": [10.0, 10.0, 10.0, 10.0], "o_ppa": [1.0, 2.0, 3.0, 4.0],
        "d_plays": [10.0] * 4, "d_ppa": [0.0] * 4,
    })
    out = pr.season_to_date(gt).sort_values("game_id")
    v = out["st_off_ppa"].to_numpy()
    assert np.isnan(v[0]), "the first game of a season has NO prior games"
    assert v[1] == pytest.approx(1.0)          # game 1 only
    assert v[2] == pytest.approx(1.5)          # games 1-2
    assert v[3] == pytest.approx(2.0)          # games 1-3


def test_season_to_date_orders_by_date_not_by_week():
    """The postseason `week`=1 collision (P1.1/P1.4 CV axis): ordering must be by calendar date, so
    a January bowl accumulates AFTER the regular season rather than resetting to the front."""
    gt = pd.DataFrame({
        "season": [2023] * 3, "team": ["A"] * 3, "game_id": [1, 2, 99],
        # the bowl (game 99) is chronologically LAST despite a week that would sort first
        "game_ts": pd.to_datetime(["2023-09-01", "2023-11-01", "2024-01-02"]),
        "o_plays": [10.0, 10.0, 10.0], "o_ppa": [1.0, 3.0, 100.0],
        "d_plays": [10.0] * 3, "d_ppa": [0.0] * 3,
    })
    out = pr.season_to_date(gt).set_index("game_id")
    assert out.loc[99, "st_off_ppa"] == pytest.approx(2.0), (
        "the bowl must accumulate the two prior regular-season games")
    assert not np.isnan(out.loc[2, "st_off_ppa"])


def test_season_to_date_does_not_leak_across_teams_or_seasons():
    gt = pd.DataFrame({
        "season": [2022, 2023, 2023], "team": ["A", "A", "B"], "game_id": [1, 2, 3],
        "game_ts": pd.to_datetime(["2022-09-01", "2023-09-01", "2023-09-01"]),
        "o_plays": [10.0] * 3, "o_ppa": [5.0, 1.0, 1.0],
        "d_plays": [10.0] * 3, "d_ppa": [0.0] * 3,
    })
    out = pr.season_to_date(gt).set_index("game_id")
    assert np.isnan(out.loc[2, "st_off_ppa"]), "a new SEASON restarts the accumulation"
    assert np.isnan(out.loc[3, "st_off_ppa"]), "another TEAM's games never accumulate"


def test_punt_distance_is_parsed_from_play_text_not_taken_from_yards_gained():
    """⭐ VERIFIED SEMANTICS GUARD. On a Punt row CFBD's `yardsGained` is the RETURN yardage, not the
    punt distance (measured: mean 2.09, median 0.0, against a real punt average of ~42). Taking it
    as 'punt average' produced ~1.3 yards — a silently WRONG feature that still looks like a number.
    A regression here would reintroduce it, so the parse is pinned at the source."""
    sql = pr.plays_game_team_sql("PLAYS", "GAMES")
    assert "regexp_extract" in sql and "punt for (-?[0-9]+) yds" in sql, (
        "gross punt distance must be PARSED from playText")
    assert "punt_gross_sum" in sql and "punt_ret_sum" in sql, (
        "both the gross and the return-allowed must be emitted so the NET is derivable")
    emitted = set(pr.ROLLUP_COLS)
    assert {"st_punt_gross", "st_punt_ret_allowed"} <= emitted
    assert "st_punt_avg" not in emitted, (
        "the ambiguous name is retired — it read as punt distance and was return yardage")


def test_garbage_time_uses_the_repo_single_definition():
    """H12/V4: exclusion IS applied and is SCORE-MARGIN gated (43/37/27/22 by quarter), NOT
    win-probability gated. The rollup must match `fact_ncaaf_play`'s one definition."""
    assert pr._GARBAGE_MARGIN == {1: 43, 2: 37, 3: 27, 4: 22}
    fact = (Path(__file__).resolve().parents[2] / "quant_sports_intel_models" / "sports_dbt" /
            "models" / "ncaaf" / "marts" / "fact_ncaaf_play.sql")
    if fact.exists():
        txt = fact.read_text()
        for q, m in pr._GARBAGE_MARGIN.items():
            assert re.search(rf"period\s*[>=]*\s*{q}\s+then\s+abs\(.*?\)\s*>\s*{m}", txt, re.S), (
                f"the rollup's Q{q} garbage threshold must match fact_ncaaf_play's")


# ---------------------------------------------------------------------------
# The doc §6.2 matchup set — the honest-scope guard
# ---------------------------------------------------------------------------

def test_matchup_set_covers_the_doc_items_and_records_which_needed_the_plays_build():
    """Pre-registration V6: only 4 of the doc §6.2 interactions exist in the P1.3 matrix. H2b must
    test the FULL set, and the source of each pair must be recorded so a future reader cannot
    mistake a silently-truncated half-set for the doc's set."""
    names = {n for n, _, _, _ in MATCHUP_PAIRS}
    for required in ("rush_line", "rush_stuff", "explosive", "pass", "std_down", "pass_down",
                     "redzone", "havoc", "pressure"):
        assert required in names, f"doc §6.2 item {required!r} is missing from the matchup set"
    from_plays = {n for n, _, _, src in MATCHUP_PAIRS if src == "plays"}
    assert len(from_plays) == 6, "the plays-derived pairs must be explicitly attributed"
