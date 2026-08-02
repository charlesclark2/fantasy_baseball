"""E7.15 H2 — guards for the opponent / competition-quality adjustment.

H2's failure modes are not "the adjustment does nothing". They are, in descending order of danger:

  1. **AN ANCHOR THAT SILENTLY STOPS WORKING.** This is not hypothetical — it HAPPENED in the first cut.
     A column-name mismatch made the non-LOO factor fall back to 1.0, so the SELF-INFLATION anchor became
     byte-identical to the foil and dutifully reported `violated=False`. The single most load-bearing
     check in the slice was passing on NOTHING while the report looked healthy. Guarded two ways now: the
     apply path reads ONE canonical column name, and the shared harness BLOCKS on an anchor that ran but
     moved no rows (NF1.7 (a), extended from "absent" to "inert").
  2. **A FACTOR THAT IS SECRETLY A FEATURE THE MODEL ALREADY HAS.** 19–41% of the level-normalised
     opponent factor is BETWEEN-LEAGUE variance, and E7.3 already fits per-league intercepts, so a lift
     on that form would be unattributable. The headline is league-normalised and the decomposition is
     published as the evidence.
  3. **A SPREAD THAT IS PURE ESTIMATOR NOISE.** A per-player factor averages noisy per-opponent
     estimates, so it has spread even when everyone faced identical competition. The split-half
     reliability is what makes a claim in EITHER direction admissible — and it needs its own positive
     control, because an instrument that only ever reports "no signal" proves nothing.
  4. **A NEUTRAL FACTOR THAT SILENTLY MOVES ROWS ANYWAY** (the H1 clip defect, one mechanism over).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from betting_ml.scripts.milb_mle.build_opponent_context import (
    _window_sum,
    league_variance_decomposition,
)
from betting_ml.scripts.milb_mle.h_harness import Anchor, evaluate_anchors
from betting_ml.scripts.milb_mle.milb_mle import MleConfig, build_target
from betting_ml.scripts.milb_mle.opponent_context import (
    OPP_RATE_PARTS,
    OPPONENT_METRICS,
    OpponentSpec,
    apply_opponent,
    opponent_coverage,
    opponent_spread,
    split_half_reliability,
)
from betting_ml.scripts.milb_mle.run_e7_15_h2 import ARMS, H2_ANCHORS, _context_for


# ══════════════════════════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════════════════════════


def _pairs(n: int = 200, seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "player_id": [f"p{i}" for i in range(n)],
        "level": np.where(np.arange(n) % 2 == 0, "Double-A", "Triple-A"),
        "league": np.where(np.arange(n) % 3 == 0, "IL", "PCL"),
        "minor_pa": 400.0, "age": 22.0,
        "minor_iso": rng.normal(0.150, 0.030, n).clip(0.02, 0.40),
        "mlb_pa": 500.0, "mlb_iso": rng.normal(0.140, 0.030, n),
        "has_mlb_label": True, "debut_cohort": 2020 + (np.arange(n) % 4),
        "first_minor_season": 2017, "last_minor_season": 2019,
    })


def _context(n: int = 200, seed: int = 4, spread: float = 0.05) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    p = _pairs(n)
    out = pd.DataFrame({"player_id": p["player_id"], "level": p["level"]})
    for suffix in ("", "_levelnorm", "_noloo", "_w3"):
        out[f"of_iso_exposure{suffix}"] = rng.normal(1.0, spread, n).clip(0.7, 1.4)
    return out


# ══════════════════════════════════════════════════════════════════════════════════════
# 1. ⭐ The anchor that silently stopped working
# ══════════════════════════════════════════════════════════════════════════════════════


class TestAnAnchorCannotSilentlyStopWorking:
    def test_every_mode_reads_the_canonical_column_so_the_noloo_anchor_actually_acts(self):
        """⚠️ **THE REGRESSION THIS PINS.** `exposure_noloo` used to look up
        `of_<m>_exposure_noloo` while the caller had ALREADY normalised that variant onto the canonical
        name — the lookup missed, the factor fell back to 1.0, and the self-inflation anchor became a
        byte-identical copy of the foil that then reported "it lost"."""
        pairs, ctx = _pairs(), _context()
        noloo_ctx = _context_for(ctx, ("iso",), "_noloo")
        out = apply_opponent(pairs, noloo_ctx, OpponentSpec(mode="exposure_noloo"), "iso")
        assert opponent_coverage(out, "iso")["pct_rows_moved"] > 90.0, \
            "the self-inflation anchor must ACT — an inert anchor passes on nothing"

    def test_the_harness_BLOCKS_on_an_anchor_that_ran_but_moved_nothing(self):
        """An INERT anchor is more dangerous than a MISSING one: the report looks healthy."""
        mae = pd.DataFrame({"L0_foil": [0.04] * 6, "arm": [0.03] * 6, "A_x": [0.05] * 6},
                           index=range(2018, 2024))
        anchors = (Anchor("A_x", "refute", "an anchor", "it means something"),)
        _rep, verdict, reason = evaluate_anchors(
            mae, anchors, "arm", "L0_foil", coverage={"A_x": {"pct_rows_moved": 0.0}})
        assert verdict == "BLOCKED" and "moved" in reason and "NOTHING" in reason

    def test_a_live_anchor_does_not_block(self):
        mae = pd.DataFrame({"L0_foil": [0.04] * 6, "arm": [0.03] * 6, "A_x": [0.05] * 6},
                           index=range(2018, 2024))
        anchors = (Anchor("A_x", "refute", "an anchor", "it means something"),)
        _rep, verdict, _r = evaluate_anchors(
            mae, anchors, "arm", "L0_foil", coverage={"A_x": {"pct_rows_moved": 95.0}})
        assert verdict is None

    def test_a_degenerate_PROJECTOR_anchor_is_exempt_from_must_move(self):
        """It transforms no feature, so requiring it to move rows would block every honest run."""
        mae = pd.DataFrame({"L0_foil": [0.04] * 6, "arm": [0.03] * 6, "A_d": [0.09] * 6},
                           index=range(2018, 2024))
        anchors = (Anchor("A_d", "block", "degenerate", "inverted", must_move=False),)
        _rep, verdict, _r = evaluate_anchors(
            mae, anchors, "arm", "L0_foil", coverage={"A_d": {"pct_rows_moved": 0.0}})
        assert verdict is None

    def test_the_slice_declares_the_self_inflation_anchor_as_must_move(self):
        by = {a.label: a for a in H2_ANCHORS}
        assert by["A_opp_noloo"].must_move and by["A_opp_placebo"].must_move
        assert not by["A_degenerate_mean"].must_move


# ══════════════════════════════════════════════════════════════════════════════════════
# 2. The transform behaves
# ══════════════════════════════════════════════════════════════════════════════════════


class TestTheAdjustmentBehaves:
    def test_off_mode_is_a_byte_no_op(self):
        pairs = _pairs()
        out = apply_opponent(pairs, _context(), OpponentSpec(mode="off"), "iso")
        pd.testing.assert_series_equal(out["minor_iso"], pairs["minor_iso"], check_names=False)
        assert (out["opp_delta"] == 0).all()

    def test_a_neutral_factor_is_a_byte_no_op_even_out_of_band(self):
        """The H1 clip defect, one mechanism over: clipping unconditionally makes a factor of exactly
        1.0 move a row whose rate sits outside the physical band."""
        pairs = _pairs()
        pairs.loc[pairs.index[:4], "minor_iso"] = 1.9      # above `_RATE_BOUNDS['iso']` = (0.0, 0.80)
        ctx = _context()
        for c in ctx.columns:
            if c.startswith("of_"):
                ctx[c] = 1.0
        out = apply_opponent(pairs, ctx, OpponentSpec(mode="exposure"), "iso")
        assert float((out["minor_iso"] - pairs["minor_iso"]).abs().max()) == 0.0

    def test_a_missing_context_is_an_honest_no_op_never_a_fabricated_factor(self):
        out = apply_opponent(_pairs(), pd.DataFrame(columns=["player_id", "level"]),
                             OpponentSpec(mode="exposure"), "iso")
        assert (out["minor_iso_opp_factor"] == 1.0).all()
        assert opponent_coverage(out, "iso")["pct_rows_moved"] == 0.0

    def test_dividing_by_a_weak_opponent_lowers_the_rate(self):
        """Direction check. A factor > 1 means he faced weak opposition, so his line is INFLATED and
        must come DOWN — getting this backwards produces a plausible number that is exactly wrong."""
        pairs = _pairs(20)
        ctx = pd.DataFrame({"player_id": pairs["player_id"], "level": pairs["level"],
                            "of_iso_exposure": 1.10})
        out = apply_opponent(pairs, ctx, OpponentSpec(mode="exposure"), "iso")
        assert (out["minor_iso"] < pairs["minor_iso"]).all()

    def test_as_extra_keeps_the_raw_feature_and_emits_the_delta(self):
        pairs = _pairs()
        out = apply_opponent(pairs, _context(), OpponentSpec(mode="exposure", as_extra=True), "iso")
        pd.testing.assert_series_equal(out["minor_iso"], pairs["minor_iso"], check_names=False)
        assert float(out["opp_delta"].abs().max()) > 0

    def test_the_placebo_permutes_WITHIN_level(self):
        """Shuffling a Triple-A factor onto a Double-A player would test level mixing, not opponents."""
        pairs, ctx = _pairs(), _context()
        out = apply_opponent(pairs, ctx, OpponentSpec(mode="placebo"), "iso")
        real = ctx.set_index("player_id")["of_iso_exposure"]
        got = out.set_index("player_id")[f"minor_iso_opp_factor"]
        for lvl in pairs["level"].unique():
            ids = pairs.loc[pairs["level"] == lvl, "player_id"]
            assert sorted(np.round(got[ids], 9)) == sorted(np.round(real[ids], 9)), \
                "the placebo must preserve each level's own factor distribution"

    @pytest.mark.parametrize("mode", ["off", "exposure", "exposure_noloo", "placebo"])
    def test_no_mode_changes_the_scored_population(self, mode):
        cfg = MleConfig(metric="iso")
        pairs = _pairs()
        base = build_target(pairs, cfg)["has_target"].to_numpy(bool)
        out = apply_opponent(pairs, _context(), OpponentSpec(mode=mode), "iso")
        assert np.array_equal(build_target(out, cfg)["has_target"].to_numpy(bool), base)

    def test_off_mode_refuses_options_that_would_make_it_not_a_foil(self):
        with pytest.raises(ValueError):
            OpponentSpec(mode="off", as_extra=True)
        with pytest.raises(ValueError):
            OpponentSpec(mode="bogus")
        with pytest.raises(ValueError):
            OpponentSpec(mode="exposure", window=0)


# ══════════════════════════════════════════════════════════════════════════════════════
# 3. ⭐ The reliability instrument, and its positive control
# ══════════════════════════════════════════════════════════════════════════════════════


def _fac(n_players: int, n_opp: int, true_sd: float, noise_sd: float, seed: int = 11) -> pd.DataFrame:
    """Per-(player, opponent) factors where each player has a TRUE schedule strength plus per-opponent
    noise. `true_sd=0` is the "everyone faced the same competition" world."""
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n_players):
        true = rng.normal(0.0, true_sd)
        for j in range(n_opp):
            rows.append({"player_id": f"p{i}", "level": "Double-A", "opp_team_id": j,
                         "season": 2019, "pa": 100.0,
                         "of_iso": float(np.exp(true + rng.normal(0.0, noise_sd)))})
    return pd.DataFrame(rows)


class TestTheReliabilityInstrument:
    def test_it_DETECTS_a_planted_signal(self):
        """⭐ THE POSITIVE CONTROL. An instrument that only ever reports "no signal" proves nothing
        (NF1.7 (a)) — it has to be shown reporting a high reliability when one exists."""
        r = split_half_reliability(_fac(400, 12, true_sd=0.05, noise_sd=0.02), ("iso",))
        assert float(r.iloc[0]["reliability_spearman_brown"]) > 0.8

    def test_it_reports_NO_signal_when_there_is_none(self):
        r = split_half_reliability(_fac(400, 12, true_sd=0.0, noise_sd=0.05), ("iso",))
        assert float(r.iloc[0]["reliability_spearman_brown"]) < 0.2

    def test_a_pure_noise_world_still_shows_SPREAD_which_is_why_reliability_is_required(self):
        """The whole reason the instrument exists: an unreliable factor is not a flat one. Without the
        reliability, this spread would read as 'competition varies a lot'."""
        from betting_ml.scripts.milb_mle.opponent_context import exposure_weighted_opponent

        per_player = exposure_weighted_opponent(_fac(400, 12, true_sd=0.0, noise_sd=0.05), ("iso",))
        sd = float(pd.to_numeric(per_player["of_iso_exposure"]).std())
        assert sd > 0.005, "a noise-only world must still LOOK like it has spread"

    def test_spread_reports_what_it_claims(self):
        ctx = pd.DataFrame({"of_iso_exposure": np.concatenate(
            [np.full(50, 0.95), np.full(50, 1.05)])})
        s = opponent_spread(ctx, ("iso",))
        assert s.iloc[0]["p5"] == pytest.approx(0.95, abs=1e-6)
        assert s.iloc[0]["p95"] == pytest.approx(1.05, abs=1e-6)
        assert s.iloc[0]["pct_players_beyond_3pct"] == pytest.approx(100.0)


# ══════════════════════════════════════════════════════════════════════════════════════
# 4. The league confound, and the rolling window
# ══════════════════════════════════════════════════════════════════════════════════════


class TestTheLeagueConfound:
    def test_the_decomposition_finds_a_planted_league_effect(self):
        """E7.3 already fits per-league intercepts, so a factor that is constant within a league is NOT
        new information. The decomposition is the evidence for normalising by league."""
        pairs = _pairs(300)
        ctx = pd.DataFrame({"player_id": pairs["player_id"], "level": pairs["level"]})
        # level-normalised: a big league offset; league-normalised: the offset removed
        offs = np.where(pairs["league"] == "IL", 1.10, 0.90)
        rng = np.random.default_rng(2)
        ctx["of_iso_exposure_levelnorm"] = offs * rng.normal(1.0, 0.005, len(pairs))
        ctx["of_iso_exposure"] = rng.normal(1.0, 0.005, len(pairs))
        dec = league_variance_decomposition(ctx, pairs, ("iso",))
        lvl = dec[dec["variant"] == "level_normalised"].iloc[0]
        lg = dec[dec["variant"].str.startswith("league_normalised")].iloc[0]
        assert lvl["between_league_share_pct"] > 90.0
        assert lg["between_league_share_pct"] < 20.0

    def test_the_headline_arm_is_the_league_normalised_one(self):
        by = {a.label: a for a in ARMS}
        assert by["O1_opp_leaguenorm"].factor_suffix == ""       # canonical = league-normalised
        assert by["O2_opp_levelnorm"].factor_suffix == "_levelnorm"


class TestTheRollingWindow:
    def test_window_3_actually_sums_three_seasons(self):
        """⚠️ **THE REGRESSION THIS PINS.** The first version misaligned the rolling frame's index, left
        every bucket at 0, and a 0-PA bucket has shrink weight 0 — so every factor came out EXACTLY
        1.000. Not a crash, not a NaN: a perfectly plausible neutral factor whose arm then reads as an
        honest null."""
        raw = pd.DataFrame({
            "player_id": ["a"] * 3, "opp_team_id": [1] * 3, "season": [2018, 2019, 2020],
            "pa": [10.0] * 3, "o_pa": [100.0, 200.0, 300.0], "lg_pa": [1.0, 1.0, 1.0],
            "no_pa": [100.0, 200.0, 300.0], "lv_pa": [1.0, 1.0, 1.0]})
        w = _window_sum(raw, 3)
        assert list(w["o_pa"]) == [100.0, 300.0, 600.0]
        assert float(w["o_pa"].std()) > 0, "a constant bucket column is the dead-window fingerprint"

    def test_window_1_is_a_pass_through(self):
        raw = pd.DataFrame({"player_id": ["a"], "opp_team_id": [1], "season": [2019], "pa": [1.0],
                            "o_pa": [5.0], "lg_pa": [1.0]})
        pd.testing.assert_frame_equal(_window_sum(raw, 1), raw)

    def test_separate_opponents_do_not_bleed_into_each_other(self):
        raw = pd.DataFrame({
            "player_id": ["a"] * 4, "opp_team_id": [1, 1, 2, 2], "season": [2018, 2019, 2018, 2019],
            "pa": [1.0] * 4, "o_pa": [10.0, 20.0, 100.0, 200.0], "lg_pa": [1.0] * 4})
        w = _window_sum(raw, 3).sort_values(["opp_team_id", "season"])
        assert list(w["o_pa"]) == [10.0, 30.0, 100.0, 300.0]


# ══════════════════════════════════════════════════════════════════════════════════════
# 5. The arm set honours §0.5
# ══════════════════════════════════════════════════════════════════════════════════════


class TestTheArmSet:
    def test_at_least_three_formulations_plus_a_direct_learned_foil(self):
        assert sum(a.kind == "opponent" for a in ARMS) >= 3
        assert sum(a.kind == "foil" for a in ARMS) == 1
        assert not next(a for a in ARMS if a.label == "L0_foil").selectable

    def test_anchors_are_scored_but_never_selectable(self):
        assert not any(a.selectable for a in ARMS if a.kind == "anchor")
        for required in ("A_opp_placebo", "A_opp_noloo", "A_degenerate_mean"):
            assert required in {a.label for a in ARMS}

    def test_arm_labels_are_unique(self):
        labels = [a.label for a in ARMS]
        assert len(labels) == len(set(labels))

    def test_every_side_metric_has_a_rate_definition(self):
        for side, metrics in OPPONENT_METRICS.items():
            for m in metrics:
                assert m in OPP_RATE_PARTS, f"{side}/{m} has no batter-vocabulary rate definition"

    def test_xwoba_against_is_deliberately_absent(self):
        """Its minor feature IS the AAA-Statcast summary — no box-line bucket can produce a factor, so
        the arm is an honest structural no-op rather than a fabricated 1.0."""
        assert "xwoba_against" not in OPPONENT_METRICS["pitcher"]
        assert "xwoba_against" not in OPP_RATE_PARTS

    def test_context_variant_selection_never_produces_duplicate_columns(self):
        ctx = _context()
        for suffix in ("", "_levelnorm", "_noloo", "_w3"):
            got = _context_for(ctx, ("iso",), suffix)
            assert list(got.columns).count("of_iso_exposure") == 1
