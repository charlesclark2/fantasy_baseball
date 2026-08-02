"""E7.15 H1 — guards for the within-player level-translation ladder.

H1's failure mode is NOT "the ladder does nothing". It is "the ladder does something, for a reason that
is not the one claimed, and the number goes down". Four specific ways, one test group each:

  1. **THE CODE PATH ITSELF MOVES THE ANSWER.** The ladder rewrites the model's input feature. If the
     transform perturbs a row even when its maps are the identity, every arm's margin is confounded with
     plumbing and the whole bake-off is uninterpretable. `A_ladder_identity` is the anchor; these tests
     pin that it is a genuine byte no-op, including on the out-of-band values that broke the FIRST
     implementation (it clipped unconditionally, so identity moved 0.1% of rows).
  2. **A LEVEL RE-CENTRING WEARING THE LADDER'S COSTUME.** The E7.3 learner already owns per-level
     intercepts. If the ladder's benefit is really "shift each level's mean", the per-player claim is
     refuted — so `A_ladder_meanshift` must be exactly slope-1, or the foil is not level-ONLY and cannot
     separate the two (NF-D15 g′).
  3. **AN ANCHOR THAT PASSES ON NOTHING.** A missing anchor makes its check vacuously true (NF1.7 (a)),
     and a thin rung that silently returned NaN would drop rows and change the scored population. Both
     must be loud.
  4. **LEAKAGE.** The rung maps must not be fitted on the held-out player's own later-level line, and the
     calendar-purge sensitivity must actually purge.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from betting_ml.scripts.milb_mle.level_ladder import (
    ASC_LEVELS,
    LEVEL_RANK,
    MIN_TRANSITION_PA,
    REFERENCE_LEVEL,
    LadderSpec,
    apply_ladder,
    build_transitions,
    fit_ladder,
    ladder_coverage,
    transition_census,
)
from betting_ml.scripts.milb_mle.milb_mle import (
    MleConfig,
    PartialPoolProjector,
    build_target,
    clone_projector,
)
from betting_ml.scripts.milb_mle.park_context import ContextSpec
from betting_ml.scripts.milb_mle.run_e7_15_h1 import (
    ARMS,
    MIN_DSR,
    MIN_FOLD_WIN_RATE,
    MAX_PBO,
    SHIPPED_CONTEXT,
    H1Arm,
    _judge,
    null_analysis,
    propensity_composition,
    stratified_lift,
)
from betting_ml.scripts.milb_mle.run_e7_12_slice1 import SIDES


# ══════════════════════════════════════════════════════════════════════════════════════
# Fixtures — a synthetic substrate with a KNOWN affine ladder
# ══════════════════════════════════════════════════════════════════════════════════════


def _synthetic_pairs(n_players: int = 400, seed: int = 7,
                     true_slope: float = 0.7, true_shift: float = 0.02) -> pd.DataFrame:
    """A world where the level translation IS `rate_next = shift + slope · rate_here`, exactly.

    Every player appears at every level, so all three adjacent rungs are thick, and the composed
    Single-A → Triple-A map has a known closed form the ladder must recover.
    """
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n_players):
        talent = float(rng.normal(0.140, 0.035))
        rate = talent
        for k, lvl in enumerate(ASC_LEVELS):
            rows.append({
                "player_id": f"p{i}", "player_name": f"P{i}", "level": lvl,
                "league": "L1", "age": 21.0 + k, "minor_pa": 400.0,
                "first_minor_season": 2016 + k, "last_minor_season": 2016 + k,
                "minor_iso": rate,
                "debut_cohort": 2021 + (i % 3) if i % 4 == 0 else np.nan,
                "mlb_pa": 500.0 if i % 4 == 0 else np.nan,
                "mlb_iso": 0.9 * rate + 0.01 if i % 4 == 0 else np.nan,
                "has_mlb_label": bool(i % 4 == 0),
                "is_prospect": not bool(i % 4 == 0),
            })
            rate = true_shift + true_slope * rate
    return pd.DataFrame(rows)


@pytest.fixture()
def pairs() -> pd.DataFrame:
    return _synthetic_pairs()


@pytest.fixture()
def trans(pairs: pd.DataFrame) -> pd.DataFrame:
    return build_transitions(pairs, "iso")


# ══════════════════════════════════════════════════════════════════════════════════════
# 1. The transform is a genuine no-op when it should be
# ══════════════════════════════════════════════════════════════════════════════════════


class TestTheLadderIsANoOpWhenItShouldBe:
    def test_off_mode_leaves_the_feature_byte_identical(self, pairs, trans):
        fit = fit_ladder(trans, LadderSpec(mode="off"), "iso")
        out = apply_ladder(pairs, fit, "iso")
        pd.testing.assert_series_equal(out["minor_iso"], pairs["minor_iso"], check_names=False)
        assert (out["ladder_delta"] == 0).all()

    def test_identity_mode_is_a_byte_no_op(self, pairs, trans):
        """`A_ladder_identity` is the PLUMBING anchor — if it moves anything, every arm's margin is
        confounded with the transform rather than with the ladder."""
        fit = fit_ladder(trans, LadderSpec(mode="identity"), "iso")
        out = apply_ladder(pairs, fit, "iso")
        assert float((out["minor_iso"] - pairs["minor_iso"]).abs().max()) == 0.0
        assert ladder_coverage(out, "iso", fit)["pct_rows_moved"] == 0.0

    def test_identity_is_still_a_no_op_on_OUT_OF_BAND_values(self, pairs, trans):
        """⚠️ THE REGRESSION THIS PINS. The first implementation clipped the ladder output
        unconditionally, so a row whose raw rate sat outside the physical band was moved by the
        IDENTITY arm — 0.1% of the live substrate. It was invisible in the runner only because
        `apply_context` happens to clip to the same bounds first, i.e. the anchor was resting on an
        upstream accident rather than on its own construction."""
        p = pairs.copy()
        p.loc[p.index[:5], "minor_iso"] = 1.5      # far above `_RATE_BOUNDS['iso']` = (0.0, 0.80)
        fit = fit_ladder(build_transitions(p, "iso"), LadderSpec(mode="identity"), "iso")
        out = apply_ladder(p, fit, "iso")
        assert float((out["minor_iso"] - p["minor_iso"]).abs().max()) == 0.0

    def test_a_metric_with_no_transitions_is_inert_not_broken(self, pairs):
        """A metric whose minor feature exists only at the reference level (pitcher `xwoba_against`)
        has NO transitions at all. That must degrade to an honest no-op the runner can report as "the
        mechanism cannot act" (NF1.9), never a crash and never a fabricated map."""
        p = pairs.copy()
        p.loc[p["level"] != REFERENCE_LEVEL, "minor_iso"] = np.nan
        t = build_transitions(p, "iso")
        assert t.empty and transition_census(t).empty
        fit = fit_ladder(t, LadderSpec(mode="chain"), "iso")
        out = apply_ladder(p, fit, "iso")
        assert all(c.source == "identity_thin" for c in fit.rungs.values())
        assert ladder_coverage(out, "iso", fit)["pct_rows_moved"] == 0.0


# ══════════════════════════════════════════════════════════════════════════════════════
# 2. The ladder recovers a translation that is actually there
# ══════════════════════════════════════════════════════════════════════════════════════


class TestTheLadderRecoversAKnownTranslation:
    def test_chain_recovers_the_true_per_rung_affine_map(self, trans):
        fit = fit_ladder(trans, LadderSpec(mode="chain"), "iso")
        for i in range(len(ASC_LEVELS) - 1):
            c = fit.rungs[(ASC_LEVELS[i], ASC_LEVELS[i + 1])]
            assert c.source == "fitted"
            assert c.b == pytest.approx(0.7, abs=1e-6)
            assert c.a == pytest.approx(0.02, abs=1e-6)

    def test_the_composed_map_sends_every_level_to_the_reference_scale(self, pairs, trans):
        fit = fit_ladder(trans, LadderSpec(mode="chain"), "iso")
        out = apply_ladder(pairs, fit, "iso")
        # a player's ladder-expressed rate must be the SAME whichever level row you read it from —
        # that is what "expressed at a common reference level" means
        per_player = out.groupby("player_id")["minor_iso"].agg(lambda s: s.max() - s.min())
        assert float(per_player.max()) < 1e-9

    def test_direct_mode_matches_the_chain_when_the_world_really_is_a_chain(self, trans):
        """The composed-attenuation hazard is a property of NOISY levels. On a noiseless true chain the
        one-step and composed estimates must agree — so a gap between them on live data is evidence
        about the substrate, not an artifact of the two formulations being differently specified."""
        chain = fit_ladder(trans, LadderSpec(mode="chain"), "iso")
        direct = fit_ladder(trans, LadderSpec(mode="direct"), "iso")
        for lv in ASC_LEVELS:
            ca, cb, _ = chain.composed[lv]
            da, db, _ = direct.composed[lv]
            assert cb == pytest.approx(db, abs=1e-6)
            assert ca == pytest.approx(da, abs=1e-6)

    def test_reference_level_rows_are_never_moved(self, pairs, trans):
        fit = fit_ladder(trans, LadderSpec(mode="chain"), "iso")
        out = apply_ladder(pairs, fit, "iso")
        ref = out[out["level"] == REFERENCE_LEVEL]
        assert float(ref["ladder_delta"].abs().max()) == 0.0


# ══════════════════════════════════════════════════════════════════════════════════════
# 3. The anchors are the mechanisms they claim to be
# ══════════════════════════════════════════════════════════════════════════════════════


class TestTheAnchorsAreWhatTheyClaim:
    def test_meanshift_is_LEVEL_ONLY_slope_pinned_to_one(self, trans):
        """The matched level-only foil must carry NO per-player content, or it cannot separate "the
        ladder learns how a line compresses" from "the ladder re-centres each level" (NF-D15 g′)."""
        fit = fit_ladder(trans, LadderSpec(mode="meanshift"), "iso")
        for c in fit.rungs.values():
            assert c.b == 1.0 and c.source == "meanshift"
        for lv in ASC_LEVELS:
            assert fit.composed[lv][1] == pytest.approx(1.0, abs=1e-12)

    def test_shuffled_destroys_the_within_player_link(self, trans):
        """Permuting the destination rates leaves both marginals intact and kills only the pairing, so
        the fitted slope must collapse toward 0 while the fitted map still exists."""
        real = fit_ladder(trans, LadderSpec(mode="chain"), "iso")
        shuf = fit_ladder(trans, LadderSpec(mode="shuffled"), "iso")
        for k in real.rungs:
            assert abs(shuf.rungs[k].b) < 0.25 * abs(real.rungs[k].b)

    def test_every_required_anchor_is_registered_in_the_arm_set(self):
        """NF1.7 (a): an anchor that is not in the field cannot fail, and a check that cannot fail is
        not a check. The runner BLOCKS on a missing anchor; this pins that they exist to begin with."""
        labels = {a.label for a in ARMS}
        for required in ("A_ladder_identity", "A_ladder_meanshift", "A_ladder_shuffled",
                         "A_degenerate_mean"):
            assert required in labels
        assert sum(a.kind == "foil" for a in ARMS) == 1
        assert sum(a.kind == "ladder" for a in ARMS) >= 3, \
            "§0.5 requires ≥3 candidate formulations, not one architecture"
        assert len(labels) == len(ARMS), "duplicate arm labels would silently collide in the leaderboard"

    def test_anchors_are_never_selectable(self):
        assert not any(a.selectable for a in ARMS if a.kind == "anchor")
        assert not next(a for a in ARMS if a.label == "L0_foil").selectable


# ══════════════════════════════════════════════════════════════════════════════════════
# 4. Leakage
# ══════════════════════════════════════════════════════════════════════════════════════


class TestLeakage:
    def test_excluding_a_player_removes_his_own_transitions_from_the_fit(self, trans):
        drop = frozenset(trans["player_id"].unique()[:50])
        full = fit_ladder(trans, LadderSpec(mode="chain"), "iso")
        held = fit_ladder(trans, LadderSpec(mode="chain"), "iso", exclude_players=drop)
        assert held.n_transitions_used < full.n_transitions_used
        assert held.n_transitions_used == int((~trans["player_id"].isin(drop)).sum())

    def test_calendar_purge_drops_transitions_that_had_not_finished_yet(self, trans):
        purged = fit_ladder(trans, LadderSpec(mode="chain", calendar_purge=True), "iso",
                            cutoff_season=2018)
        expected = int((pd.to_numeric(trans["known_by_season"]) < 2018).sum())
        assert purged.n_transitions_used == expected
        assert purged.n_transitions_used < len(trans)

    def test_a_demotion_is_not_read_as_a_promotion_translation(self):
        """A rehab assignment sends a Triple-A player back to High-A. The pairs grain carries no order,
        so without the temporal filter that row would be scored as a High-A → Triple-A translation."""
        p = _synthetic_pairs(n_players=80)
        # make one player's Triple-A stint START BEFORE his High-A stint (a demotion)
        m = (p["player_id"] == "p0") & (p["level"] == REFERENCE_LEVEL)
        p.loc[m, ["first_minor_season", "last_minor_season"]] = 2010
        t = build_transitions(p, "iso")
        bad = t[(t["player_id"] == "p0") & (t["level_dst"] == REFERENCE_LEVEL)]
        assert bad.empty

    def test_a_thin_level_line_is_not_a_transition(self):
        p = _synthetic_pairs(n_players=80)
        p.loc[p["level"] == "High-A", "minor_pa"] = MIN_TRANSITION_PA - 1
        t = build_transitions(p, "iso")
        assert not ((t["level_src"] == "High-A") | (t["level_dst"] == "High-A")).any()


# ══════════════════════════════════════════════════════════════════════════════════════
# 5. The population the arms are scored on cannot change
# ══════════════════════════════════════════════════════════════════════════════════════


class TestTheScoredPopulationIsInvariant:
    @pytest.mark.parametrize("mode", ["off", "chain", "direct", "meanshift", "identity", "shuffled"])
    def test_no_formulation_changes_has_target(self, pairs, trans, mode):
        cfg = MleConfig(metric="iso")
        base = build_target(pairs, cfg)["has_target"].to_numpy(bool)
        fit = fit_ladder(trans, LadderSpec(mode=mode), "iso")
        got = build_target(apply_ladder(pairs, fit, "iso"), cfg)["has_target"].to_numpy(bool)
        assert np.array_equal(base, got), \
            "an arm that changes the labelled population is scored on different players, not a ladder"

    def test_as_extra_leaves_the_raw_feature_untouched(self, pairs, trans):
        """The NESTING arm must keep the foil's feature verbatim and add ONLY the delta — otherwise it
        does not contain the foil at coefficient 0 and a win is no longer attributable."""
        fit = fit_ladder(trans, LadderSpec(mode="chain", as_extra=True), "iso")
        out = apply_ladder(pairs, fit, "iso")
        pd.testing.assert_series_equal(out["minor_iso"], pairs["minor_iso"], check_names=False)
        assert float(out.loc[out["level"] != REFERENCE_LEVEL, "ladder_delta"].abs().max()) > 0

    def test_the_pooled_learner_carries_ladder_delta_through_a_clone(self):
        """🪤 The E7.12-S5 lesson, applied to this story's new consumer: `clone_projector` is what
        `emit_projections` uses to refit per cohort. A field it drops means the EMISSION silently serves
        the incumbent under the winning arm's name."""
        c = PartialPoolProjector(prior_scale=4.0, extra_cols=("ladder_delta",), weight_col="mlb_pa")
        assert clone_projector(c).extra_cols == ("ladder_delta",)
        assert clone_projector(c).weight_col == "mlb_pa"


# ══════════════════════════════════════════════════════════════════════════════════════
# 6. The verdict logic — every BLOCK/DROP path must actually fire
# ══════════════════════════════════════════════════════════════════════════════════════


def _mae_frame(cols: dict[str, list[float]]) -> pd.DataFrame:
    return pd.DataFrame(cols, index=[2018, 2019, 2020, 2021, 2022, 2023])


def _leaderboard(mae: pd.DataFrame, arms: tuple[H1Arm, ...],
                 active: set[str] | None = None) -> pd.DataFrame:
    foil = mae["L0_foil"]
    rows = []
    for a in arms:
        d = (foil - mae[a.label]).to_numpy(float)
        rows.append({
            "arm": a.label, "kind": a.kind, "selectable": a.selectable,
            "active": a.label in (active or set(mae.columns)),
            "oos_mae": float(mae[a.label].mean()),
            "mae_lift_vs_foil": float(np.mean(d)),
            "pct_lift_vs_foil": 100.0 * float(np.mean(d)) / float(foil.mean()),
            "fold_win_rate": float(np.mean(d > 0)), "p_one_sided": 0.01,
            "pct_rows_moved": 50.0, "mean_abs_delta_feat": 0.01, "note": "",
        })
    return pd.DataFrame(rows).sort_values("oos_mae").reset_index(drop=True)


_ARMS4 = tuple(a for a in ARMS if a.label in (
    "L0_foil", "L1_chain_ols", "A_ladder_identity", "A_ladder_meanshift", "A_ladder_shuffled",
    "A_degenerate_mean"))
_CLEAN_DEFL = {"pbo": 0.0, "os_gap_pct": 0.0}
_CLEAN_DSR = {"eligible": {"dsr": 0.99, "passes": True, "n_trials": 1}}


def _clean_mae(winner: float = 0.030) -> pd.DataFrame:
    """A world where the ladder wins on every fold and every anchor loses cleanly."""
    n = 6
    return _mae_frame({
        "L0_foil": [0.040] * n,
        "A_ladder_identity": [0.040] * n,
        "L1_chain_ols": [winner] * n,
        "A_ladder_meanshift": [0.045] * n,
        "A_ladder_shuffled": [0.060] * n,
        "A_degenerate_mean": [0.070] * n,
    })


def _judge_args(mae, rows=None, defl=None, dsr=None, oracle=True, side="batter", metric="iso"):
    """Returns `(anchors, stratified_all, stratified_moved, verdict, winner, reasons)`."""
    lb = _leaderboard(mae, _ARMS4)
    return _judge(metric, SIDES[side], mae, lb,
                  rows if rows is not None else pd.DataFrame(),
                  defl if defl is not None else _CLEAN_DEFL,
                  dsr if dsr is not None else _CLEAN_DSR, oracle, [])


class TestTheVerdictLogicFires:
    def test_a_clean_win_ADDs(self):
        _a, _s, _sm, verdict, winner, _r = _judge_args(_clean_mae())
        assert verdict == "ADD" and winner == "L1_chain_ols"

    def test_a_missing_anchor_BLOCKS_rather_than_passing_vacuously(self):
        mae = _clean_mae().drop(columns=["A_ladder_shuffled"])
        lb = _leaderboard(mae, tuple(a for a in _ARMS4 if a.label != "A_ladder_shuffled"))
        _a, _s, _sm, verdict, _w, reasons = _judge("iso", SIDES["batter"], mae, lb, pd.DataFrame(),
                                                   _CLEAN_DEFL, _CLEAN_DSR, True, [])
        assert verdict == "BLOCKED"
        assert any("ABSENT" in r for r in reasons)

    def test_a_non_noop_identity_anchor_BLOCKS(self):
        mae = _clean_mae()
        mae.loc[2019, "A_ladder_identity"] = 0.0401
        _a, _s, _sm, verdict, _w, reasons = _judge_args(mae)
        assert verdict == "BLOCKED"
        assert any("byte no-op" in r for r in reasons)

    def test_the_degenerate_ceiling_winning_BLOCKS_as_an_inverted_metric(self):
        mae = _clean_mae()
        mae["A_degenerate_mean"] = 0.010
        _a, _s, _sm, verdict, _w, reasons = _judge_args(mae)
        assert verdict == "BLOCKED"
        assert any("DEGENERATE CEILING" in r for r in reasons)

    def test_the_level_only_foil_winning_REFUTES_the_mechanism(self):
        mae = _clean_mae()
        mae["A_ladder_meanshift"] = 0.025      # beats the fitted ladder on every fold
        _a, _s, _sm, verdict, winner, reasons = _judge_args(mae)
        assert verdict == "DROP" and winner == "L0_foil"
        assert any("MECHANISM REFUTED" in r and "level-only" in r.lower() for r in reasons)

    def test_the_shuffled_link_anchor_winning_REFUTES_the_mechanism(self):
        mae = _clean_mae()
        mae["A_ladder_shuffled"] = 0.025
        _a, _s, _sm, verdict, _w, reasons = _judge_args(mae)
        assert verdict == "DROP"
        assert any("LINK anchor" in r for r in reasons)

    def test_an_inconsistent_win_DROPs(self):
        """A win on a minority of folds is noise, whatever the mean says."""
        mae = _clean_mae()
        mae["L1_chain_ols"] = [0.020, 0.045, 0.045, 0.045, 0.045, 0.045]
        _a, _s, _sm, verdict, _w, _r = _judge_args(mae)
        assert verdict == "DROP"

    def test_a_high_PBO_DROPs(self):
        _a, _s, _sm, verdict, _w, reasons = _judge_args(_clean_mae(), defl={"pbo": MAX_PBO + 0.01})
        assert verdict == "DROP" and any("PBO" in r for r in reasons)

    def test_a_failing_DSR_DROPs(self):
        _a, _s, _sm, verdict, _w, reasons = _judge_args(
            _clean_mae(), dsr={"eligible": {"dsr": MIN_DSR - 0.1, "passes": False, "n_trials": 6}})
        assert verdict == "DROP" and any("DSR" in r for r in reasons)

    def test_an_inactive_ladder_cannot_be_selected(self):
        """A ladder that moved nothing is the foil in disguise; selecting it would report the incumbent
        as a win (the repo's silent-empty class)."""
        mae = _clean_mae()
        lb = _leaderboard(mae, _ARMS4, active={"L0_foil", "A_ladder_identity", "A_ladder_meanshift",
                                               "A_ladder_shuffled", "A_degenerate_mean"})
        _a, _s, _sm, verdict, winner, reasons = _judge("iso", SIDES["batter"], mae, lb, pd.DataFrame(),
                                                       _CLEAN_DEFL, _CLEAN_DSR, True, [])
        assert verdict == "DROP" and winner == "L0_foil"
        assert any("INACTIVE" in r or "no ELIGIBLE arm" in r for r in reasons)


class TestTheLowPropensityTercileGate:
    @staticmethod
    def _rows(low_lift: float) -> pd.DataFrame:
        """Per-row errors where the foil and the ladder differ ONLY inside stratum 0."""
        out = []
        for s in (0, 1, 2):
            for i in range(40):
                base = 0.040
                out.append({"fold": 2019, "arm": "L0_foil", "player_id": f"x{s}_{i}",
                            "level": "Double-A", "abs_err": base, "stratum": s})
                delta = base * low_lift / 100.0 if s == 0 else base * 0.02
                out.append({"fold": 2019, "arm": "L1_chain_ols", "player_id": f"x{s}_{i}",
                            "level": "Double-A", "abs_err": base - delta, "stratum": s})
        return pd.DataFrame(out)

    def test_a_board_metric_helping_only_the_HIGH_tercile_is_downgraded(self):
        """H5: the board serves un-promoted prospects. An arm that improves the players we do NOT serve
        is not a board improvement, whatever the pooled MAE says."""
        rows = self._rows(low_lift=-3.0)
        _a, strat, _sm, verdict, winner, reasons = _judge_args(_clean_mae(), rows=rows, metric="iso")
        assert not strat.empty
        assert verdict == "DROP" and winner == "L0_foil"
        assert any("LOW-TERCILE DOWNGRADE" in r for r in reasons)

    def test_a_positive_low_tercile_still_ADDs(self):
        rows = self._rows(low_lift=+3.0)
        _a, _s, _sm, verdict, winner, _r = _judge_args(_clean_mae(), rows=rows, metric="iso")
        assert verdict == "ADD" and winner == "L1_chain_ols"

    def test_a_COSMETIC_metric_is_reported_not_downgraded(self):
        """`woba` is not on the E8.0 board, so a low-tercile miss there cannot change a draft ranking —
        it is stated, not used to block."""
        assert "woba" not in SIDES["batter"].board_metrics
        rows = self._rows(low_lift=-3.0)
        _a, _s, _sm, verdict, _w, reasons = _judge_args(_clean_mae(), rows=rows, metric="woba")
        assert verdict == "ADD"
        assert any("cosmetic metric" in r for r in reasons)

    def test_stratified_lift_is_computed_against_the_foil(self):
        s = stratified_lift(self._rows(low_lift=5.0))
        low = s[(s["arm"] == "L1_chain_ols") & (s["stratum"] == 0)]["pct_lift_vs_foil"].iloc[0]
        assert low == pytest.approx(5.0, abs=1e-6)


# ══════════════════════════════════════════════════════════════════════════════════════
# 7. The foil is the thing that actually ships
# ══════════════════════════════════════════════════════════════════════════════════════


class TestTheFoilIsTheShippedConfiguration:
    """⭐ The margin must be measured against what is LIVE, not against a re-derivation of it.

    Slice 1 shipped a per-metric `ContextSpec`; if this map drifts from that report the ladder is being
    compared to a baseline nobody is serving, and the reported lift is meaningless in either direction.
    Pinned as literals for the same reason slice 1 pins `E73_WINNER_PRIOR_SCALE`.
    """

    def test_batter_shipped_specs_match_the_slice1_report(self):
        got = {m: s.label for m, s in SHIPPED_CONTEXT["batter"].items()}
        assert got == {
            "woba": "levelenv",
            "k_pct": "park:exposure+levelenv+rel:0.5k",
            "bb_pct": "park:exposure+levelenv+rel:2k",
            "iso": "park:exposure+levelenv+rel:2k",
        }

    def test_pitcher_shipped_specs_match_the_slice1p_report(self):
        got = {m: s.label for m, s in SHIPPED_CONTEXT["pitcher"].items()}
        assert got == {
            # k_pct / gb_pct / xwoba_against were DROPPED on the pitcher side, so their shipped
            # configuration IS the bare incumbent — a `baseline` here is the report, not an omission.
            "k_pct": "baseline",
            "bb_pct": "park:exposure+levelenv+rel:1k+w:mlb_pa",
            "hr_rate": "park:exposure+levelenv+rel:1k+w:mlb_pa",
            "gb_pct": "baseline",
            "xwoba_against": "baseline",
        }

    def test_every_side_metric_has_a_shipped_spec(self):
        for name, side in SIDES.items():
            for m in side.metrics:
                assert m in SHIPPED_CONTEXT[name], \
                    f"{name}/{m} has no pinned foil — it would silently fall back to a bare incumbent"

    def test_the_shipped_weight_col_is_carried_into_every_arm(self):
        """E7.9: hold the learner fixed. The pitcher side ships `weight_col='mlb_pa'` on two metrics; an
        arm that dropped it would be measuring the ladder PLUS a de-weighting."""
        assert SHIPPED_CONTEXT["pitcher"]["bb_pct"].weight_col == "mlb_pa"
        assert SHIPPED_CONTEXT["batter"]["iso"].weight_col is None


# ══════════════════════════════════════════════════════════════════════════════════════
# 8. Bookkeeping the report depends on
# ══════════════════════════════════════════════════════════════════════════════════════


class TestCensusAndCoverage:
    def test_the_census_reports_every_ordered_pair_and_the_never_mlb_share(self, trans):
        c = transition_census(trans)
        assert len(c) == 6                                  # C(4,2) ordered level pairs
        assert set(c.columns) >= {"rung", "n_transitions", "pct_never_mlb", "adjacent",
                                  "to_reference"}
        assert c["n_transitions"].min() > 0
        assert (c["pct_never_mlb"] > 0).any(), \
            "the never-MLB share is H1's whole premise — a census that cannot show it is useless"

    def test_a_thin_rung_falls_back_to_identity_and_SAYS_SO(self):
        """Silently returning NaN would drop rows and change the scored population; silently returning a
        wild slope would compound through the composition. The honest degradation is identity + a note."""
        p = _synthetic_pairs(n_players=20)      # every rung is far below MIN_RUNG_N
        fit = fit_ladder(build_transitions(p, "iso"), LadderSpec(mode="chain"), "iso")
        assert all(c.source == "identity_thin" for c in fit.rungs.values())
        assert fit.fallbacks and all("identity_thin" in f for f in fit.fallbacks)
        out = apply_ladder(p, fit, "iso")
        assert out["minor_iso"].notna().sum() == p["minor_iso"].notna().sum()

    def test_coverage_reports_the_composed_map_per_level(self, pairs, trans):
        fit = fit_ladder(trans, LadderSpec(mode="chain"), "iso")
        cov = ladder_coverage(apply_ladder(pairs, fit, "iso"), "iso", fit)
        assert set(cov["composed"]) == set(ASC_LEVELS)
        assert cov["composed"][REFERENCE_LEVEL]["b"] == 1.0
        assert cov["pct_rows_moved"] > 0

    def test_level_rank_is_ascending_toward_the_reference(self):
        """A silently reversed ladder maps everyone DOWN and still produces plausible numbers."""
        assert LEVEL_RANK[REFERENCE_LEVEL] == max(LEVEL_RANK.values())
        assert ASC_LEVELS[0] == "Single-A" and ASC_LEVELS[-1] == REFERENCE_LEVEL


def test_off_mode_refuses_options_that_would_make_it_not_a_foil():
    """`L0_foil` must be the byte-exact shipped configuration. A `mode='off'` spec carrying a ladder
    option would be a foil in name only."""
    with pytest.raises(ValueError):
        LadderSpec(mode="off", as_extra=True)
    with pytest.raises(ValueError):
        LadderSpec(mode="bogus")


def test_the_context_spec_used_as_the_foil_is_a_real_slice1_spec():
    for side_specs in SHIPPED_CONTEXT.values():
        for spec in side_specs.values():
            assert isinstance(spec, ContextSpec)


class TestTheHighPBOReadingIsClassifiedNotDelegated:
    """A high PBO means two different things and the verdict is DROP for both — but the RECORD differs.

    E2.1-r: with a TIED field a high PBO is the NULL ("no candidate robustly beats the incumbent ⇒ the
    incumbent is now proven"), while a high PBO over a WIDE spread is genuine instability. NF1.8's lesson
    is that a rank statistic cannot tell those apart on its own, so the harness must read the contender
    spread and SAY which it is rather than asking the report's reader to do it by hand.
    """

    @staticmethod
    def _defl(spread: float) -> dict:
        return {"pbo": 0.7, "contender_spread_pct": spread,
                "flips": [{"config": "L1_chain_ols", "share": 0.51, "pct_vs_best": 0.0},
                          {"config": "L0_foil", "share": 0.30, "pct_vs_best": 0.05}]}

    def test_a_tight_contender_spread_is_recorded_as_a_TIE(self):
        _a, _s, _sm, verdict, _w, reasons = _judge_args(_clean_mae(), defl=self._defl(0.06))
        assert verdict == "DROP"
        assert any("TIE" in r and "PROVEN" in r for r in reasons)

    def test_a_wide_contender_spread_is_recorded_as_INSTABILITY(self):
        _a, _s, _sm, verdict, _w, reasons = _judge_args(_clean_mae(), defl=self._defl(12.0))
        assert verdict == "DROP"
        assert any("instability" in r and "not a tie" in r for r in reasons)


# ══════════════════════════════════════════════════════════════════════════════════════
# 9. Reading a null honestly, and reading the tercile for what it is
# ══════════════════════════════════════════════════════════════════════════════════════


class TestTheTercileReadIsNotDilutedByRowsTheLadderCannotMove:
    """⚠️ **THE DEFECT THE LIVE RUN EXPOSED.** A Triple-A row is the ladder's REFERENCE level, so its
    delta is identically 0 and it contributes exactly zero lift by construction. On the scored
    population only 48.1% of the LOW-propensity tercile's rows are movable against 61.2% of the high
    tercile, so an all-rows read dilutes the low end HARDEST — the exact end the H5 gate is about, and
    the NF1.8 "a per-group constraint evaluated on a quietly different population than the one it
    names" lesson one mechanism over.
    """

    @staticmethod
    def _rows(movable_lift: float, n_unmovable: int) -> pd.DataFrame:
        out = []
        for i in range(20):
            out += [{"fold": 2019, "arm": "L0_foil", "player_id": f"m{i}", "level": "High-A",
                     "abs_err": 0.040, "stratum": 0, "moved": True},
                    {"fold": 2019, "arm": "L1_chain_ols", "player_id": f"m{i}", "level": "High-A",
                     "abs_err": 0.040 * (1 - movable_lift / 100.0), "stratum": 0, "moved": True}]
        for i in range(n_unmovable):
            out += [{"fold": 2019, "arm": "L0_foil", "player_id": f"u{i}", "level": "Triple-A",
                     "abs_err": 0.040, "stratum": 0, "moved": False},
                    {"fold": 2019, "arm": "L1_chain_ols", "player_id": f"u{i}", "level": "Triple-A",
                     "abs_err": 0.040, "stratum": 0, "moved": False}]
        return pd.DataFrame(out)

    def test_unmovable_rows_DILUTE_the_all_rows_reading(self):
        rows = self._rows(movable_lift=6.0, n_unmovable=60)
        all_rows = stratified_lift(rows)
        moved = stratified_lift(rows, moved_only=True)
        a = all_rows[(all_rows.arm == "L1_chain_ols") & (all_rows.stratum == 0)].iloc[0]
        m = moved[(moved.arm == "L1_chain_ols") & (moved.stratum == 0)].iloc[0]
        assert m["pct_lift_vs_foil"] == pytest.approx(6.0, abs=1e-6)
        assert a["pct_lift_vs_foil"] == pytest.approx(1.5, abs=1e-6)   # 20/(20+60) of the real effect
        assert a["n"] == 80 and m["n"] == 20

    def test_the_gate_reads_the_MOVED_view(self):
        """A board metric whose movable rows are HURT must be downgraded even when the diluted all-rows
        number looks harmless."""
        rows = self._rows(movable_lift=-8.0, n_unmovable=200)
        _a, _s, _sm, verdict, winner, reasons = _judge_args(_clean_mae(), rows=rows, metric="iso")
        assert verdict == "DROP" and winner == "L0_foil"
        assert any("LOW-TERCILE DOWNGRADE" in r for r in reasons)

    def test_the_composition_table_exposes_the_level_mix(self):
        comp = propensity_composition(self._rows(movable_lift=1.0, n_unmovable=60))
        row = comp[comp["stratum"] == 0].iloc[0]
        assert row["Triple-A"] == pytest.approx(75.0, abs=0.1)
        assert row["pct_rows_the_mechanism_can_move"] == pytest.approx(25.0, abs=0.1)


class TestTheNullAnalysis:
    """NF-D15 (g″): an honest null proves it does not rest on the author's own gate choice, and states
    its margin in the unit that GROWS — never in p-decimals."""

    @staticmethod
    def _result(metric: str, lift: float, p: float | None):
        from betting_ml.scripts.milb_mle.run_e7_15_h1 import H1Result

        n = 11
        mae = pd.DataFrame({"L0_foil": [0.040] * n,
                            "L1_chain_ols": [0.040 - 0.040 * lift / 100.0] * n},
                           index=range(2015, 2015 + n))
        # Give the skill series variance WITHOUT moving its mean — a one-sided nudge would swamp a
        # sub-0.1% effect and flip the arm's sign, which is how a "power" fixture silently becomes an
        # "absence" fixture.
        jitter = np.linspace(-1.0, 1.0, n) * 0.0004
        mae["L1_chain_ols"] = mae["L1_chain_ols"].to_numpy(float) + jitter
        lb = pd.DataFrame([
            {"arm": "L0_foil", "kind": "foil", "selectable": False, "active": True,
             "oos_mae": float(mae["L0_foil"].mean()), "pct_lift_vs_foil": 0.0, "fold_win_rate": 0.0},
            {"arm": "L1_chain_ols", "kind": "ladder", "selectable": True, "active": True,
             "oos_mae": float(mae["L1_chain_ols"].mean()), "pct_lift_vs_foil": lift,
             "fold_win_rate": 1.0 if lift > 0 else 0.0}])
        return H1Result(metric=metric, prior_scale=2.0, shipped_spec=ContextSpec(), leaderboard=lb,
                        mae_by_fold=mae, fold_cohorts=list(mae.index), census=pd.DataFrame(),
                        per_fold_transitions=pd.DataFrame(), coverage={},
                        deflation={"pbo": 0.9}, dsr={"eligible": {"dsr": 0.1, "passes": False}},
                        anchors={}, stratified=pd.DataFrame(), stratified_moved=pd.DataFrame(),
                        composition=pd.DataFrame(), verdict="DROP", winner="L0_foil")

    def test_it_reports_that_removing_the_deflation_gates_changes_nothing(self):
        res = {"iso": self._result("iso", lift=+0.05, p=0.30)}
        out = null_analysis(res, {"iso": 0.30})
        assert out["survivors_with_PBO_and_DSR_gates_REMOVED"] == []
        assert "BH-FDR multiplicity" in out["binding_constraint"]

    def test_it_admits_when_the_deflation_gates_ARE_what_binds(self):
        """The check has to be able to come out the other way, or it is not a check (NF1.7 (a))."""
        res = {"iso": self._result("iso", lift=+2.0, p=0.001)}
        out = null_analysis(res, {"iso": 0.001})
        assert out["survivors_with_PBO_and_DSR_gates_REMOVED"] == ["iso"]
        assert "deflation gates" in out["binding_constraint"]

    def test_a_negative_effect_is_a_GENUINE_ABSENCE_not_an_underpowered_one(self):
        out = null_analysis({"iso": self._result("iso", lift=-0.5, p=0.9)}, {"iso": 0.9})
        row = out["per_metric"][0]
        assert row["kind"].startswith("genuine absence")
        assert row["extra_seasons_needed"] is None, \
            "no sample size rescues a negative point estimate — quoting a season count would be a lie"

    def test_an_underpowered_effect_gets_a_SEASON_COUNT_not_a_p_decimal(self):
        out = null_analysis({"iso": self._result("iso", lift=+0.05, p=0.30)}, {"iso": 0.30})
        row = out["per_metric"][0]
        assert row["kind"] == "underpowered"
        assert row["folds_have"] == 11
        assert isinstance(row["extra_seasons_needed"], int) and row["extra_seasons_needed"] > 0
