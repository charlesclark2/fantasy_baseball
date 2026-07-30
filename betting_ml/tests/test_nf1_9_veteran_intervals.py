"""NF1.9 — guards for the VETERAN 80% band: the 90%-of-the-board interval nobody had measured.

WHAT THIS PROTECTS. The NF1.4 → NF1.7 → NF1.8 arc validated intervals for the ~81 ROOKIES on the draft
board. The ~700 VETERANS carried `point ± 1.2816·season_sd` — a normal approximation off game-to-game
scoring variance — and NO coverage number for it existed in any ablation report. Measured for the first
time in NF1.9 over 13 held-out target seasons (8,398 veteran-seasons) it covers **0.545** of its nominal
0.80, missing on BOTH tails (0.272 below p10, 0.183 above p90). NF1.9 replaced it with a per-player
neighbourhood-quantile band selected on a PROPER interval score under a PER-POSITION coverage floor.

The tests split into the things that can silently break:
  1. **The POINT must not move.** NF1.9 prices uncertainty and nothing else. Structurally the band is
     emitted after every point column is final, so a drift is unreachable — this pins that.
     ⚠️ Asserted `< 1e-9`, NOT byte-equality (the NF1.8 lesson: a polyfit/row-order ULP is not a model
     change and must not be reported as one).
  2. **The POPULATION must stay honest.** The panel LEFT-joins the realized season and scores a
     projected veteran who never played as a real 0. Every other veteran backtest in this program keeps
     `g >= 6`, which is correct for a RANK read and would flatter the interval exactly where it is
     broken. A future edit that "fixes" the join to an inner join silently re-breaks the measurement.
  3. ⭐ **THE SELECTION METRIC MUST STAY ORIENTED**, from both ends — the §0.5 landmine that shipped the
     rookie defect in the first place. Both degenerates must lose, the widen-only knob must be monotone,
     a missing anchor must RAISE, and the peeking oracle must be a floor at MATCHED n.
  4. **The atom at zero must stay understood.** ~26% of veteran-seasons realize exactly 0 PPR, which
     makes coverage structurally non-binding (a bound floored at 0 cannot be missed from below) and pins
     the conformal quantile at exactly 0. Two arms exist to keep that visible; a future session must not
     reintroduce a coverage TARGET on the strength of it.
  5. **The re-validation must actually TRIGGER.** A floor is invisible at serving time, so the standing
     annual check has to exit non-zero on a breach and must not treat an errored population as a pass.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quant_sports_intel_models.football.nfl.fantasy import season_projection as sp
from quant_sports_intel_models.football.nfl.fantasy import (
    run_interval_revalidation as REV,
    run_rookie_interval_ablation as NF17,
    run_rookie_perposition_ablation as NF18,
    run_veteran_interval_ablation as NF19,
)
from quant_sports_intel_models.football.nfl.fantasy.export_draft_board_json import (
    _SHARED_BAND_MIN_POINT_SPREAD,
    _SHARED_BAND_POINT_SPREAD_TOL,
    audit_interval_quality,
)

_REPORT = (Path(__file__).resolve().parents[2]
           / "quant_sports_intel_models/football/nfl/fantasy/ablation_results"
           / "nf1_9_veteran_perposition_floor.md")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Fixtures — a synthetic veteran panel with the real population's defining feature: a mass at ZERO
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _panel(n: int = 1200, seed: int = 7, zero_rate: float = 0.26) -> pd.DataFrame:
    """A synthetic veteran band panel. Deliberately reproduces the two features that drive every
    finding: a RIGHT-SKEWED season total, and a POINT MASS at exactly 0 for the players who never
    play."""
    rng = np.random.default_rng(seed)
    pos = rng.choice(["QB", "RB", "WR", "TE"], size=n, p=[0.15, 0.25, 0.4, 0.2])
    base_games = rng.integers(1, 18, size=n).astype(float)
    point = np.clip(rng.gamma(2.0, 45.0, size=n), 0.5, None)
    season_sd = np.clip(point * rng.uniform(0.25, 0.6, size=n), 1.0, None)
    plays = rng.random(n) > zero_rate
    real = np.where(plays, np.clip(point * rng.gamma(2.0, 0.5, size=n), 0.0, None), 0.0)
    return pd.DataFrame({
        "target_season": rng.integers(2010, 2025, size=n),
        "position": pos, "point": point, "season_sd": season_sd,
        "proj_games": np.clip(base_games + rng.normal(0, 1, n), 1, 17),
        "base_games": base_games,
        "snap_share": rng.uniform(0.05, 0.95, size=n),
        "seasons_missed": (rng.random(n) < 0.05).astype(float),
        "real_fp_ppr": real, "real_games": np.where(plays, base_games, 0.0),
    })


@pytest.fixture(scope="module")
def panel() -> pd.DataFrame:
    return _panel()


@pytest.fixture(scope="module")
def frame(panel) -> pd.DataFrame:
    return NF19._frame(panel)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. The band's input contract, and the train/serve skew it exists to prevent
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_band_input_contract_is_assembled_in_ONE_place(panel, frame):
    """The harness and `project_veterans` must build the design from the SAME helper. NF1.7's first cut
    re-derived the rookie point instead of delegating and was wrong by 3.3 PPR."""
    assert list(frame.columns) == ["position", "point", "season_sd", "proj_games", "base_games",
                                   "snap_share", "seasons_missed"]
    direct = sp.veteran_band_inputs(panel["position"], panel["point"], panel["season_sd"],
                                    proj_games=panel["proj_games"], base_games=panel["base_games"],
                                    snap_share=panel["snap_share"],
                                    seasons_missed=panel["seasons_missed"])
    pd.testing.assert_frame_equal(frame, direct)


def test_a_missing_optional_driver_falls_through_to_a_neutral_value_rather_than_refusing_the_row():
    """The served board must always emit SOME band — a player with no snap-share row is not dropped."""
    f = sp.veteran_band_inputs(["QB", "RB"], [100.0, 50.0], [30.0, 20.0])
    assert list(f["snap_share"]) == [0.0, 0.0]
    assert list(f["seasons_missed"]) == [0.0, 0.0]
    m = sp.VeteranBandModel(form="normal")
    lo, hi = m.band_many(f)
    assert np.isfinite(lo).all() and np.isfinite(hi).all()


def test_the_panel_stores_the_UNROUNDED_season_sd_so_the_fit_matches_the_serve():
    """⚠️ THE TRAIN/SERVE SKEW THE REPRODUCTION PROOF CAUGHT. `project_veterans` emits `fp_ppr_sd`
    rounded to 2dp for display but feeds the band the UNROUNDED value, so a panel storing the rounded
    column would fit the band on a systematically different feature than it is served with. The panel
    must read `fp_ppr_sd_raw`."""
    from quant_sports_intel_models.football.nfl.fantasy import run_season_projection as RS
    src = Path(RS.__file__).read_text()
    body = src.split("def build_veteran_panel_season")[1].split("\ndef ")[0]
    assert '"season_sd": pd.to_numeric(vets["fp_ppr_sd_raw"]' in body, (
        "the veteran band panel must store the UNROUNDED season sd (`fp_ppr_sd_raw`) — the rounded "
        "display column is a train/serve skew in the band's most important feature")


def test_project_veterans_emits_the_unrounded_sd_outside_the_served_schema():
    from quant_sports_intel_models.football.nfl.fantasy.run_season_projection import OUTPUT_COLS
    assert "fp_ppr_sd_raw" not in OUTPUT_COLS, "the raw sd is an internal handoff, not a served column"
    src = Path(sp.__file__).read_text()
    assert 'df["fp_ppr_sd_raw"] = season_sd' in src


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. The POPULATION — the fix that makes the measurement honest
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_panel_LEFT_joins_the_realized_season_and_scores_a_zero_game_veteran_as_a_REAL_ZERO():
    """🚨 THE WHOLE BALLGAME. Every other veteran backtest here uses `how="inner"` + `g >= 6` — right
    for a rank read, and it would DROP exactly the veterans whose season ended in injury/release, i.e.
    the left tail the band exists to price."""
    from quant_sports_intel_models.football.nfl.fantasy import run_season_projection as RS
    body = Path(RS.__file__).read_text().split(
        "def build_veteran_panel_season")[1].split("\ndef ")[0]
    # ⚠️ strip the docstring — it DISCUSSES the `g >= 6` filter it must not perform, and greping the
    #    whole function would flag the explanation as the defect (this test failed on exactly that).
    code = body.split('"""')[-1]
    assert 'how="left"' in code, "the panel join must be a LEFT join"
    assert 'include_zero_game=True' in code, "zero-game veterans must be in the population"
    assert re.search(r'out\["real_fp_ppr"\][^\n]*fillna\(0\.0\)', code), (
        "a projected veteran with no realized row must score a real 0, not NaN")
    assert not re.search(r'\["g"\]\s*>=?\s*6|g\s*>=\s*6\b', code), (
        "a >=6-game survivor filter would flatter the interval exactly where it is broken")


def test_the_incumbent_arm_is_the_EMITTED_band_not_a_re_derivation(panel):
    """The bake-off's incumbent must be the band the board actually showed, or the story measures a
    straw man. The panel carries `served_p10/p90`; the harness proves the model path reproduces them."""
    from quant_sports_intel_models.football.nfl.fantasy.run_season_projection import VET_PANEL_COLS
    assert "served_p10" in VET_PANEL_COLS and "served_p90" in VET_PANEL_COLS
    src = Path(NF19.__file__).read_text()
    assert "served_band_is_reproduced" in src
    assert "if band_drift > 1e-9" in src, "the reproduction proof must HALT the harness, not warn"


def test_the_reproduction_proof_would_FAIL_on_a_perturbed_band(panel):
    """The proof must be able to fail — a guard that cannot go red is not a guard. (It DID go red for
    real, on the rounded-sd skew above.)"""
    fold = NF19.Fold(
        year=2024, train=panel, test=panel.head(50).reset_index(drop=True),
        train_frame=NF19._frame(panel), test_frame=NF19._frame(panel.head(50)),
        test_pred=panel["point"].head(50).to_numpy(float),
        test_sd=panel["season_sd"].head(50).to_numpy(float),
        test_real=panel["real_fp_ppr"].head(50).to_numpy(float),
        served_lo=np.zeros(50), served_hi=np.full(50, 1e6))
    assert NF19.served_band_is_reproduced(fold) > 1e-9


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. The selection metric, pinned from both ends
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_interval_score_definitions_agree_between_the_served_path_and_the_harness():
    """`normal_scaled` fits its multiplier by minimising the interval score on the SERVED side, so the
    two definitions must not drift. One rule, two homes, one test."""
    rng = np.random.default_rng(3)
    lo, hi, y = rng.uniform(0, 50, 200), rng.uniform(50, 200, 200), rng.uniform(0, 250, 200)
    np.testing.assert_allclose(sp._interval_score(lo, hi, y, 0.20),
                               NF17.interval_score(lo, hi, y, 0.20), rtol=0, atol=0)


@pytest.mark.parametrize("form", ["normal", "normal_scaled", "normal_cov", "ratio_q",
                                  "ratio_q_floor", "knn_pos", "knn_norm", "qreg", "qreg_sqrt"])
def test_every_pre_registered_form_emits_a_coherent_band(panel, frame, form):
    """Every form: non-negative, brackets its own point. A displayed interval that excludes its own
    point estimate is incoherent — the symptom NF3 surfaced on the rookie leg."""
    m = sp.fit_veteran_band_model(panel, form=form, k=200, qreg_alpha=0.01)
    assert m is not None, f"{form} refused to fit on 1200 rows"
    lo, hi = m.band_many(frame)
    ok = np.isfinite(lo) & np.isfinite(hi)
    assert ok.sum() > 0
    pt = frame["point"].to_numpy(float)
    assert (lo[ok] >= -1e-9).all(), "a fantasy season cannot be negative"
    assert (lo[ok] <= pt[ok] + 1e-9).all() and (hi[ok] >= pt[ok] - 1e-9).all()


def test_BOTH_degenerates_lose_to_an_honest_band(panel, frame):
    """⭐ The two-sided anchor. `zero_width` is maximally SHARP (a naive sharpness metric crowns it) and
    `max_width` has coverage ≈ 1 (a coverage TARGET loves it). A metric either can win cannot select an
    interval."""
    y = panel["real_fp_ppr"].to_numpy(float)
    pt = frame["point"].to_numpy(float)
    m = sp.fit_veteran_band_model(panel, form="knn_norm", k=200)
    lo, hi = NF17._finish(*m.band_many(frame), pt)
    honest = float(np.mean(NF17.interval_score(lo, hi, y)))
    zw = float(np.mean(NF17.interval_score(*NF17._finish(pt, pt, pt), y)))
    mx = np.full_like(pt, float(np.max(y)) * 1.2)
    mw = float(np.mean(NF17.interval_score(*NF17._finish(np.zeros_like(pt), mx, pt), y)))
    assert honest < zw, "the zero-width degenerate must LOSE — sharpness must be paid for"
    assert honest < mw, "the max-width degenerate must LOSE — this is not a coverage exercise"


def test_the_max_width_degenerate_SATISFIES_every_coverage_floor_and_that_is_WHY_coverage_cannot_select():
    """The NF1.8 reading, re-verified on the veteran floors: a CONSTRAINT a degenerate satisfies is
    fine (the metric eliminates it); a CRITERION a degenerate wins is fatal."""
    rec = {"coverage_80": 1.0, "n_QB": 1100, "cov_QB": 1.0, "n_WR": 3100, "cov_WR": 1.0}
    floors = NF18.position_floors(rec, ["QB", "WR"], tier=1, min_n=NF19._POS_FLOOR_MIN_N,
                                  tier2_positions=NF19._TIER2_POSITIONS, nominal=NF19._NOMINAL)
    assert floors == {"QB": 0.80, "WR": 0.80}
    assert NF18.floor_misses(rec, floors) == []


def test_the_sd_gain_widener_is_STRICTLY_widen_only(panel, frame):
    """⭐ ANCHOR GUARD 4 (NF1.7 lesson 4). A two-sided version would SHARPEN half the field off a
    parameter-uncertainty z — buying interval score by narrowing bands, the exact trade the coverage
    floor forbids. It cost the rookie band 0.808 → 0.773 coverage when it was two-sided."""
    base = sp.fit_veteran_band_model(panel, form="knn_norm", k=200, sd_gain=0.0)
    wide = sp.fit_veteran_band_model(panel, form="knn_norm", k=200, sd_gain=0.20)
    lo0, hi0 = base.band_many(frame)
    lo1, hi1 = wide.band_many(frame)
    ok = np.isfinite(lo0) & np.isfinite(lo1)
    w0, w1 = (hi0 - lo0)[ok], (hi1 - lo1)[ok]
    assert (w1 >= w0 - 1e-9).all(), "the widener SHARPENED at least one band — it must be monotone"
    assert (w1 > w0 + 1e-9).any(), "the widener did nothing at all"


def test_the_param_uncertainty_driver_is_the_small_sample_one_not_an_outcome():
    """`1/√base_games` — a player whose per-game rate rests on 4 games is genuinely less certain than
    one with 17, and no neighbourhood of OUTCOMES can see it. If this ever became outcome-derived it
    would be leakage."""
    f = sp.veteran_band_inputs(["RB", "RB"], [100.0, 100.0], [30.0, 30.0], base_games=[4.0, 16.0])
    pu = sp._vet_param_uncertainty(f)
    assert pu[0] > pu[1], "fewer base-season games must mean MORE parameter uncertainty"
    np.testing.assert_allclose(pu, [0.5, 0.25])


def test_a_missing_anchor_RAISES_rather_than_passing_vacuously():
    """⭐ ANCHOR GUARD 1. An absent anchor makes its own check vacuously true. This fired for real on
    the first full NF1.9 run (the oracle refused a fit for a thin position), which is why the oracle now
    degrades to the normal band exactly as a candidate does."""
    with pytest.raises(SystemExit, match="did not fit"):
        NF18.require_anchors({"zero_width": 1.0}, NF19._REQUIRED_ANCHORS)
    assert "matched_n_candidate" in NF19._REQUIRED_ANCHORS
    assert "permuted_alt" in NF19._REQUIRED_ANCHORS
    assert "oracle_own_family" in NF19._REQUIRED_ANCHORS


def test_the_permutation_oracle_LOSES_to_the_same_arm_fitted_on_the_TRUTH(panel, frame):
    """⭐ ANCHOR GUARD 2, the well-posed form: same family, same rows, same resolution — only the
    INFORMATION moves. Knowing the answer must score better than not knowing it, and unlike a peeking
    fitted oracle this holds at ANY sample size."""
    y = panel["real_fp_ppr"].to_numpy(float)
    pt = frame["point"].to_numpy(float)
    rng = np.random.default_rng(11)
    truth = sp.fit_veteran_band_model(panel, form="knn_norm", k=200)
    shuf = sp.fit_veteran_band_model(
        panel.assign(real_fp_ppr=rng.permutation(y)), form="knn_norm", k=200)
    s_t = float(np.mean(NF17.interval_score(*NF17._finish(*truth.band_many(frame), pt), y)))
    s_s = float(np.mean(NF17.interval_score(*NF17._finish(*shuf.band_many(frame), pt), y)))
    assert s_t < s_s, "a band fitted on SHUFFLED outcomes scored as well as one fitted on the truth"


def test_the_gate_leans_on_the_MATCHED_n_oracle_not_the_unmatched_one():
    """NF1.7 lesson 2: a peeking fit is a valid floor only at EQUAL family AND EQUAL resolution. The
    veteran oracle can only be fitted on ~650 held-out rows while a candidate trains on ~6,500, so the
    UNMATCHED comparison is orientation and the MATCHED one gates. Pinned so a future edit cannot
    quietly promote the wrong one (or drop the gate)."""
    src = Path(NF19.__file__).read_text()
    gate = src.split("# ⚠️ THE GATE.")[1].split("raise SystemExit")[0]
    assert 'checks["oracle_respected_at_matched_n"]' in gate
    assert 'checks["permutation_respected"]' in gate
    assert 'checks["per_position_floor_met"]' in gate
    assert 'checks["served_band_reproduced"]' in gate
    assert 'not checks["oracle_respected"]' not in gate, (
        "the UNMATCHED-n oracle must not gate — it is orientation only")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4. The atom at zero — why coverage is structurally non-binding here
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_conformal_quantile_is_PINNED_at_zero_by_the_atom(panel):
    """⭐ THE E2.1-r LANDMINE IN A NEW POPULATION. ~26% of veteran-seasons realize exactly 0 PPR, and a
    band floored at 0 scores a conformity of EXACTLY 0 on such a row. So a large mass of conformity
    scores sits at 0, the (1−α) quantile lands inside it, and the Mondrian adjustment is 0 — all four
    CQR arms were byte-identical to their base. This is a FINDING, recorded so a future session does not
    read the no-op as a bug and 'fix' it into a coverage target."""
    m = sp.fit_veteran_band_model(panel, form="qreg_sqrt", qreg_alpha=0.01, cqr_mode="pos")
    assert m is not None and m.conformal, "the conformal layer did not fit at all"
    lo, hi = m.band_many(NF19._frame(panel))
    y = panel["real_fp_ppr"].to_numpy(float)
    e = np.maximum(lo - y, y - hi)
    assert float(np.mean(e == 0.0)) > 0.15, (
        "the atom at zero should put a large mass of conformity scores at EXACTLY 0")
    assert set(m.conformal) == {"add", "width"}, (
        "one cross-conformal pass must produce BOTH scalings — a second pass re-fits identical models")


def test_the_conformal_adjustment_is_a_per_GROUP_scalar_so_it_cannot_narrow_a_chosen_player(panel):
    """Carried from NF1.8: the layer moves every member of a group together, so it can never buy
    sharpness by narrowing selected players."""
    m = sp.fit_veteran_band_model(panel, form="qreg", qreg_alpha=0.01, cqr_mode="pos")
    f = NF19._frame(panel)
    import dataclasses
    off = dataclasses.replace(m, cqr_mode="")
    lo0, hi0 = off.band_many(f)
    lo1, hi1 = m.band_many(f)
    pos = f["position"].to_numpy()
    for p in np.unique(pos):
        sel = (pos == p) & np.isfinite(lo0) & np.isfinite(lo1)
        if sel.sum() < 5:
            continue
        d = np.round((hi1 - hi0)[sel], 9)
        assert len(set(d.tolist())) == 1, f"{p}: the adjustment is not a single per-group scalar"


def test_the_coverage_floor_is_a_FLOOR_and_the_coverage_TARGET_arm_exists_to_prove_the_cost(panel):
    """The pre-registered pair. `normal_scaled` fits its multiplier on the PROPER SCORE, `normal_cov`
    fits the identical machinery to a COVERAGE TARGET. On the real panel the coverage-fitted arm hits
    nominal and pays ~7% of interval score; here we only pin that the two fits genuinely DIFFER, so the
    foil can never silently become a duplicate of the arm it is meant to contrast with."""
    a = sp.fit_veteran_band_model(panel, form="normal_scaled")
    b = sp.fit_veteran_band_model(panel, form="normal_cov")
    assert a.sd_scale and b.sd_scale
    assert a.sd_scale != b.sd_scale, (
        "the score-fitted and coverage-fitted dispersion multipliers must not coincide — the foil "
        "would then be measuring nothing")


def test_unknown_conformal_settings_raise_rather_than_silently_doing_nothing():
    with pytest.raises(ValueError, match="unknown conformal setting"):
        sp.fit_veteran_band_model(_panel(300), form="qreg", cqr_mode="mondrian")


def test_a_thin_fit_DEGRADES_to_the_served_normal_band_rather_than_fabricating_an_interval():
    assert sp.fit_veteran_band_model(_panel(50), form="knn_norm") is None
    src = Path(NF19.__file__).read_text()
    assert "_normal_band(fold, idx)" in src, (
        "a row the fit cannot speak to must fall back to the served normal band, as production does")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 5. The POINT must not move
# ══════════════════════════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("form", ["normal", "knn_norm", "qreg_sqrt", "ratio_q"])
def test_the_band_configuration_cannot_reach_the_point_projection(panel, frame, form):
    """Structural, not incidental: `band_model` is referenced ONLY inside the interval block of
    `project_veterans`, after every point column is final. Verified by source inspection (a runtime
    assertion could only test the configs it happened to run) plus the board-level `< 1e-9` check the
    session ran on the real 2026 board (measured 8.5e-13, ULP noise from a warmed cache).

    ⚠️ `< 1e-9`, NOT byte-equality — the NF1.8 lesson."""
    src = Path(sp.__file__).read_text()
    # slice project_veterans precisely — its own section, not "everything up to the next top-level def"
    # (which swallowed the RookieSlotCurve dataclass and its unrelated `band_model` field; this test
    # failed on exactly that).
    body = src.split("def project_veterans(")[1].split("# Rookie projection")[0]
    head, band_block = body.split("# ── the 80% veteran interval.")

    def _code(text: str) -> str:
        """Executable lines only — the docstring and the comments DISCUSS `band_model`, and greping
        prose for the invariant is how the first cut of this test failed."""
        out, in_doc = [], False
        for ln in text.split("\n"):
            if ln.strip().startswith('"""') or ln.strip().endswith('"""'):
                in_doc = not in_doc
                continue
            if in_doc or ln.strip().startswith("#"):
                continue
            out.append(ln.split("  #")[0])
        return "\n".join(out)

    head_code, band_code = _code(head), _code(band_block)
    assert head_code.count("band_model") == 1, (
        "band_model must appear in the executable code BEFORE the interval block exactly once — as the "
        f"signature parameter. A second reference means the band can reach the point projection. "
        f"(found {head_code.count('band_model')})")
    assert 'band_model: "VeteranBandModel | None" = None' in head_code
    assert "band_model" in band_code
    for col in ("proj_fp_ppr", "proj_games", "proj_rush_yds", "proj_rec", "proj_pass_yds"):
        assert f'df["{col}"] =' not in band_block, (
            f"the interval block assigns {col} — the band must only write the interval")
    # every column the interval block DOES write
    written = set(re.findall(r'df\["([a-z0-9_]+)"\]\s*=', band_block))
    assert written <= {"fp_ppr_p10", "fp_ppr_p90", "uncertainty_type", "is_rookie", "draft_overall",
                       "source", "projection_season", "confidence", "fp_ppr_sd", "fp_ppr_sd_raw",
                       "fp_ppr_l5"}, f"the interval block writes unexpected columns: {written}"


def test_the_band_only_writes_the_interval_columns(panel, frame):
    m = sp.fit_veteran_band_model(panel, form="knn_norm", k=200)
    lo, hi = m.band_many(frame)
    pd.testing.assert_frame_equal(frame, NF19._frame(panel), check_like=False)
    assert len(lo) == len(hi) == len(frame)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 6. The shipped constants, and the report they claim to come from
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_shipped_form_is_pre_registered():
    assert sp._VET_BAND_FORM in sp._VET_BAND_FORMS
    assert sp._VET_BAND_CQR_MODE in sp._VET_BAND_CQR_MODES
    assert sp._VET_BAND_CQR_SCALE in sp._VET_BAND_CQR_SCALES
    assert sp._VET_BAND_SD_GAIN >= 0.0


@pytest.mark.skipif(not _REPORT.exists(), reason="NF1.9 report not generated in this checkout")
def test_the_shipped_constants_match_the_NF1_9_ablation_report():
    """The drift guard: the shipped constants must be the ones the bake-off actually selected. A drifted
    default is an unselected model in production with a report that says otherwise."""
    text = _REPORT.read_text()
    m = re.search(r"\*\*SHIPPED: `([^`]+)`\*\*", text)
    assert m, "the report does not state a SHIPPED config"
    label = m.group(1)
    assert sp._VET_BAND_FORM in label, f"shipped form {sp._VET_BAND_FORM!r} not in report label {label!r}"
    if sp._VET_BAND_FORM.startswith("knn"):
        assert f"k{sp._VET_BAND_K}" in label, f"shipped k={sp._VET_BAND_K} not in {label!r}"
    assert f"sdgain {sp._VET_BAND_SD_GAIN:g}" in label


@pytest.mark.skipif(not _REPORT.exists(), reason="NF1.9 report not generated in this checkout")
def test_the_report_states_the_defect_the_population_fix_and_the_atom():
    text = _REPORT.read_text()
    for needle in ("NON-BINDING", "LEFT-join", "zero-game", "PERMUTATION", "max_width",
                   "STANDING ANNUAL RE-VALIDATION", "Bailey", "FLIP DISTRIBUTION"):
        assert needle.lower() in text.lower(), f"the report never mentions {needle!r}"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 7. The export guard's new materiality floor
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_NF17_class_level_defect_still_trips_the_export_guard():
    """The materiality floor must not silence the defect the guard exists for: the pre-NF1.7 rookie band
    shared 26.5–277.0 across points spanning 25.1→268.3 = 243 PPR, which clears a 17-PPR floor by 14×."""
    recs = [{"name": f"rk{i}", "fpP10": 26.5, "fpP90": 277.0, "fpPpr": p}
            for i, p in enumerate([25.1, 268.3, 120.0])]
    findings = audit_interval_quality(recs)
    assert any("CLASS-LEVEL" in f for f in findings)


def test_a_deep_bench_rounding_collision_does_NOT_trip_the_export_guard():
    """⚠️ THE SECOND FALSE-POSITIVE MODE. A scale-FREE ratio has no traction when the scale is tiny: 6
    deep-bench veterans sharing 0.0–3.2 span 1.27 PPR = 40% of the band, which is 0.08 PPR/game — no
    drafter can act on it. A guard that can never go green is a guard nobody reads."""
    recs = [{"name": f"v{i}", "fpP10": 0.0, "fpP90": 3.2, "fpPpr": p}
            for i, p in enumerate([0.7, 1.0, 1.3, 1.6, 1.8, 2.0])]
    assert audit_interval_quality(recs) == []


def test_the_materiality_floor_is_a_decision_resolution_quantity_not_a_silencer():
    assert _SHARED_BAND_MIN_POINT_SPREAD == pytest.approx(17.0), (
        "the floor is 1 PPR/game over a 17-game season — a decision-resolution quantity fixed from the "
        "unit, not tuned to the result")
    assert _SHARED_BAND_POINT_SPREAD_TOL == pytest.approx(0.25)
    # BOTH conditions are required — either alone has a false-positive mode
    wide_but_immaterial = [{"name": "a", "fpP10": 0.0, "fpP90": 2.0, "fpPpr": 0.1},
                           {"name": "b", "fpP10": 0.0, "fpP90": 2.0, "fpPpr": 1.9}]
    material_but_centrable = [{"name": "a", "fpP10": 0.0, "fpP90": 400.0, "fpPpr": 190.0},
                              {"name": "b", "fpP10": 0.0, "fpP90": 400.0, "fpPpr": 210.0}]
    assert audit_interval_quality(wide_but_immaterial) == []
    assert not any("CLASS-LEVEL" in f for f in audit_interval_quality(material_but_centrable))


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 8. The standing annual re-validation must actually TRIGGER
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_shipped_configs_are_DERIVED_from_the_served_constants_not_hardcoded():
    """A re-validation that pins a literal keeps validating the band the code USED to serve."""
    r, v = REV.shipped_rookie_cfg(), REV.shipped_veteran_cfg()
    assert r["form"] == sp._ROOKIE_BAND_FORM and r["cqr_mode"] == sp._ROOKIE_BAND_CQR_MODE
    assert v["form"] == sp._VET_BAND_FORM and v["k"] == sp._VET_BAND_K
    src = Path(REV.__file__).read_text()
    assert '"knn_norm"' not in src and '"qreg_sqrt"' not in src, (
        "the re-validation must not hardcode a form — derive it from season_projection")


def test_a_floor_breach_makes_the_revalidation_EXIT_NON_ZERO():
    """⭐ A floor is INVISIBLE at serving time, so the annual check is the only thing that can notice it
    breaking. It must be a TRIGGER, not a log line."""
    src = Path(REV.__file__).read_text()
    assert "return 0 if ok else 1" in src
    ok_block = {"population": "veterans", "pass": True}
    bad_block = {"population": "veterans", "pass": False, "misses": ["QB 0.71<0.800"]}
    assert all(b.get("pass") is True for b in [ok_block])
    assert not all(b.get("pass") is True for b in [ok_block, bad_block])


def test_an_ERRORED_population_is_NOT_counted_as_a_pass():
    """The NF1.7 anchor lesson wearing an ops hat: a check that silently skips a population it could not
    load passes on NOTHING."""
    errored = {"population": "rookies", "error": "no pool"}
    assert errored.get("pass") is not True
    src = Path(REV.__file__).read_text()
    assert 'all(b.get("pass") is True for b in blocks)' in src


def test_the_revalidation_gates_on_the_POOLED_floor_and_only_REPORTS_the_newest_cohort():
    """A single new season/class is far too thin per position to gate: a perfectly-calibrated band fails
    a hard point-estimate floor at nominal ~half the time. The newest cohort is a leading indicator."""
    src = Path(REV.__file__).read_text()
    assert "LEADING INDICATOR" in src
    body = src.split("def revalidate_veterans")[1].split("\ndef ")[0]
    assert '"newest_cohort"' in body
    # the pass/fail comes from the POOLED block, never from newest_cohort
    assert 'newest_cohort' not in src.split("ok = all(")[1].split("\n")[0]


def test_the_veteran_floor_parameters_are_sized_from_the_DESIGN_not_the_answer():
    """`min_n = 400` ⇒ a binomial SE of 0.020 at nominal, so the floor tests a real shortfall rather
    than noise; FB is the structurally-thin position. Both are quantities known before any result."""
    assert NF19._POS_FLOOR_MIN_N == 400
    assert NF19._TIER2_POSITIONS == ("FB",)
    se = float(np.sqrt(0.8 * 0.2 / NF19._POS_FLOOR_MIN_N))
    assert se < 0.021
    # and NF1.8's rookie defaults must be untouched by NF1.9's parameterisation
    assert NF18._POS_FLOOR_MIN_N == 30 and NF18._TIER2_POSITIONS == ("QB",)
    rec = {"n_QB": 81, "cov_QB": 0.74}
    assert NF18.position_floors(rec, ["QB"], tier=1) == {"QB": 0.80}
