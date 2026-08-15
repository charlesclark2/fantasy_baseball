"""E1.13 — pure-logic guards for the seasonnorm-cure retrain-vs-incumbent harness.

Covers the pieces a wrong answer would flow through silently:
  * the cure / pre-cure transforms are exact wrapper semantics, idempotent, and
    reconstruct each other from EITHER store vintage (the harness must run identically
    before or after the operator's --full-refresh rebuild);
  * the store-null mask joins by game_pk (the de-leak swap fills raw bp_eb cells in the
    clean matrix, so a mask read off the post-swap frame under-counts — measured), maps
    an unknown game to UNTOUCHED (never fabricates), and refuses a duplicate game_pk;
  * the verdict derivation is three-way and fails closed (NF-W2e), with an explicit
    INACTIVE state when the cure touches zero eval rows (NF1.9: a mechanism that cannot
    act is a finding, not a null);
  * a non-finite per-row score is REFUSED, never nan-meaned past (NF-W3).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from betting_ml.scripts.e1_13_seasonnorm_cure_revalidation import (
    DSR_BAR,
    _finite_or_refuse,
    apply_cure,
    apply_precure,
    derive_verdict,
    seasonnorm_pairs,
    store_null_masks,
    touched_mask,
)

SN = "home_bp_eb_xwoba_seasonnorm"
RAW = "home_bp_eb_xwoba"


def _raw_frame():
    # game 2's raw is NULL in the STORE (→ fabricated 0.0 pre-cure / NULL post-cure);
    # games 1 and 3 are present.
    return pd.DataFrame({
        "game_pk": [1, 2, 3],
        RAW: [0.320, np.nan, 0.301],
    })


def _matrix(vintage: str):
    # the clean matrix AFTER the de-leak swap: game 2's raw twin has been FILLED by
    # bullpen_v3 (non-null!) — which is exactly why the mask must come from the store
    # frame, not this one. The seasonnorm column carries the store's value per vintage.
    sn_val = {"precure": 0.0, "cured": np.nan}[vintage]
    return pd.DataFrame({
        "game_pk": ["1", "2", "3"],
        RAW: [0.320, 0.315, 0.301],          # post-swap: no NULL anywhere
        SN: [1.2, sn_val, -0.4],
    })


@pytest.fixture()
def masks():
    return store_null_masks(_raw_frame(), [(SN, RAW)])


class TestTransforms:
    def test_cure_nulls_exactly_the_store_null_rows(self, masks):
        out = apply_cure(_matrix("precure"), masks)
        assert np.isnan(out[SN].iloc[1])
        assert out[SN].iloc[0] == 1.2 and out[SN].iloc[2] == -0.4

    def test_precure_fabricates_exactly_the_store_null_rows(self, masks):
        out = apply_precure(_matrix("cured"), masks)
        assert out[SN].iloc[1] == 0.0
        assert out[SN].iloc[0] == 1.2 and out[SN].iloc[2] == -0.4

    @pytest.mark.parametrize("vintage", ["precure", "cured"])
    def test_both_views_are_reachable_from_either_store_vintage(self, masks, vintage):
        # the store-vintage-robustness contract: cure(x) and precure(x) give the SAME
        # pair whether x is the pre-rebuild or post-rebuild store.
        m = _matrix(vintage)
        cured, pre = apply_cure(m, masks), apply_precure(m, masks)
        assert np.isnan(cured[SN].iloc[1]) and pre[SN].iloc[1] == 0.0

    @pytest.mark.parametrize("fn", [apply_cure, apply_precure])
    def test_idempotent(self, masks, fn):
        once = fn(_matrix("precure"), masks)
        twice = fn(once, masks)
        pd.testing.assert_frame_equal(once, twice)

    def test_a_game_absent_from_the_mask_frame_is_left_alone(self, masks):
        m = _matrix("precure")
        m.loc[3] = {"game_pk": "999", RAW: 0.5, SN: 0.7}   # unknown to the store frame
        out = apply_cure(m, masks)
        assert out[SN].iloc[3] == 0.7                       # untouched, never fabricated

    def test_touched_mask_flags_exactly_the_store_null_games(self, masks):
        t = touched_mask(_matrix("cured"), masks)
        assert t.tolist() == [False, True, False]

    def test_duplicate_game_pk_in_the_store_frame_refuses(self):
        dup = pd.concat([_raw_frame(), _raw_frame().iloc[[0]]], ignore_index=True)
        with pytest.raises(SystemExit, match="duplicate game_pk"):
            store_null_masks(dup, [(SN, RAW)])


class TestPairs:
    def test_missing_raw_twin_refuses(self):
        with pytest.raises(SystemExit, match="raw twin"):
            seasonnorm_pairs([SN], {"something_else"})

    def test_contract_without_seasonnorm_refuses(self):
        # this harness exists ONLY for the contract the cure reaches — running it on a
        # seasonnorm-free contract would report a vacuous null.
        with pytest.raises(SystemExit, match="no _seasonnorm"):
            seasonnorm_pairs(["home_elo"], {"home_elo"})


class TestScoresAndVerdict:
    def test_non_finite_score_is_refused(self):
        with pytest.raises(SystemExit, match="non-finite"):
            _finite_or_refuse(np.array([1.0, np.nan]), "refit_cured")

    def test_zero_touched_eval_rows_is_inactive_not_a_null(self):
        v, contest = derive_verdict(margin=0.5, noise_floor=0.02, dsr=0.99,
                                    calibration_ok=True, touched_eval_rows=0)
        assert (v, contest) == ("INCUMBENT_STANDS", "INACTIVE")

    def test_within_floor_is_a_tie_and_a_tie_ships_nothing(self):
        v, contest = derive_verdict(margin=0.01, noise_floor=0.02, dsr=0.999,
                                    calibration_ok=True, touched_eval_rows=50)
        assert (v, contest) == ("INCUMBENT_STANDS", "TIES")

    def test_ship_requires_every_gate(self):
        ok = dict(margin=0.05, noise_floor=0.02, dsr=DSR_BAR, calibration_ok=True,
                  touched_eval_rows=50)
        assert derive_verdict(**ok) == ("SHIP_RETRAIN", "BEATS")
        assert derive_verdict(**{**ok, "dsr": DSR_BAR - 0.01})[0] == "INCUMBENT_STANDS"
        assert derive_verdict(**{**ok, "dsr": None})[0] == "INCUMBENT_STANDS"
        assert derive_verdict(**{**ok, "calibration_ok": False})[0] == "INCUMBENT_STANDS"

    def test_a_loss_is_named_a_loss_not_a_tie(self):
        v, contest = derive_verdict(margin=-0.05, noise_floor=0.02, dsr=0.1,
                                    calibration_ok=True, touched_eval_rows=50)
        assert (v, contest) == ("INCUMBENT_STANDS", "LOSES")
