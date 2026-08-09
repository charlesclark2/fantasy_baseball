"""NF-W2b guards — the injury family re-registered against a marginal-rate-carrying foil.

Each test is independently RED-provable: it fails when the specific contract it names is broken
(the #682 mutation-must-land discipline — gate-composition clauses are flipped ONE at a time on
a fixture that satisfies every OTHER clause, per NF-D17). Fast-gate rules honored: no `pipeline`
import, no network/IO at import, no module-level state mutation.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quant_sports_intel_models.football.nfl.fantasy import weekly_frame as WF
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection_w2 as W2
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection_w2b as W2B


THU = pd.Timestamp("2024-10-03")   # a Thursday gameday
SUN = pd.Timestamp("2024-10-06")   # the same week's Sunday


def _rate_feat() -> pd.DataFrame:
    """4 RBs in one (season, week, position): A+C play Thursday, B+D play Sunday.
    A consumed a Wednesday-stamped Out report; B a Friday-stamped Questionable report
    (admissible for B's own Sunday game, but stamped AFTER Thursday 00:00 UTC)."""
    rows = [
        dict(gsis_id="A", _target_gameday=THU,
             _inj_dm_utc=pd.Timestamp("2024-10-02 15:00:00", tz="UTC"),
             listed=1.0, out=1.0, dbtf=0.0, ques=0.0, dnp=1.0, lim=0.0),
        dict(gsis_id="C", _target_gameday=THU, _inj_dm_utc=pd.NaT,
             listed=0.0, out=0.0, dbtf=0.0, ques=0.0, dnp=0.0, lim=0.0),
        dict(gsis_id="B", _target_gameday=SUN,
             _inj_dm_utc=pd.Timestamp("2024-10-04 20:00:00", tz="UTC"),
             listed=1.0, out=0.0, dbtf=0.0, ques=1.0, dnp=0.0, lim=1.0),
        dict(gsis_id="D", _target_gameday=SUN, _inj_dm_utc=pd.NaT,
             listed=0.0, out=0.0, dbtf=0.0, ques=0.0, dnp=0.0, lim=0.0),
    ]
    df = pd.DataFrame([{
        "label": WF.LABEL_PLAYED, "season": 2024, "week": 5, "position": "RB", "gw": 100,
        "gsis_id": r["gsis_id"], "_target_gameday": r["_target_gameday"],
        "_inj_dm_utc": r["_inj_dm_utc"],
        "injury_report__listed": r["listed"],
        "injury_report__status_out": r["out"],
        "injury_report__status_doubtful": r["dbtf"],
        "injury_report__status_questionable": r["ques"],
        "injury_report__practice_dnp": r["dnp"],
        "injury_report__practice_limited": r["lim"],
        "injury_report__observed": 1.0,
    } for r in rows])
    return df


# ── provenance + the matched-pair identity at the feature-list level ────────────────────────────
class TestProvenance:
    def test_registered_features_pass(self):
        W2B.assert_feature_provenance_w2b(W2B.FEATURES_W2B)

    def test_unknown_family_rejects(self):
        with pytest.raises(WF.LeakageError, match="unknown provenance"):
            W2B.assert_feature_provenance_w2b(W2B.FEATURES_W2B + ("mystery__thing",))

    def test_injury_rate_is_a_certified_contract_family(self):
        """The rate family must live in the audited contract, not ride on an alias — an
        unaudited family has no as-of rule by definition (NF-W0 §13)."""
        assert "injury_rate" in {s.name for s in WF.ALLOWED_FEATURE_CONTRACT}

    def test_foil_bundle_carries_no_player_level_injury_columns(self):
        """Attribution integrity: `base_rate` is the champion + GROUP rates ONLY. A player-level
        injury column in the foil would let the foil absorb the very content the matched pair
        exists to isolate."""
        assert not set(W2B.FEATURES_BASE_RATE) & set(W2.INJURY_FEATURES)

    def test_matched_pair_identity(self):
        """Every arm is the foil's bundle PLUS the player injury family — nothing else moved
        (NF-D10)."""
        assert W2B.FEATURES_BASE_RATE == WP.FEATURES + W2B.RATE_FEATURES
        assert W2B.FEATURES_W2B == W2B.FEATURES_BASE_RATE + W2.INJURY_FEATURES

    def test_rate_columns_mirror_the_player_family(self):
        got = set(W2B.RATE_OF_PLAYER_COL.values())
        assert got == set(W2.INJURY_FEATURES) - {"injury_report__observed"}


# ── the rate family: group-level, per-instant PIT-honest, era-honest ────────────────────────────
class TestRateEngineering:
    def test_rates_are_constant_within_position_week_gameday(self):
        """NO player linkage — mechanically: the rate columns are CONSTANT within
        (season, week, position, gameday)."""
        out = W2B.engineer_injury_rate_features(_rate_feat())
        for _, grp in out.groupby(["season", "week", "position", "_target_gameday"]):
            for c in W2B.RATE_FEATURES:
                assert grp[c].nunique(dropna=False) == 1

    def test_thursday_rows_exclude_the_friday_stamp(self):
        """⭐ THE per-instant honesty core: a whole-week rate would leak B's Friday stamp into
        A's Thursday game. The rate for a row aggregates ONLY stamps strictly before ITS OWN
        gameday 00:00 UTC."""
        out = W2B.engineer_injury_rate_features(_rate_feat()).set_index("gsis_id")
        # Thursday rows see only A's Wednesday stamp: 1 of 4 listed, 0 questionable
        assert out.loc["A", "injury_rate__listed"] == pytest.approx(0.25)
        assert out.loc["A", "injury_rate__status_questionable"] == pytest.approx(0.0)
        assert out.loc["A", "injury_rate__status_out"] == pytest.approx(0.25)
        # Sunday rows see A + B: 2 of 4 listed, 1 questionable, 1 limited
        assert out.loc["B", "injury_rate__listed"] == pytest.approx(0.5)
        assert out.loc["B", "injury_rate__status_questionable"] == pytest.approx(0.25)
        assert out.loc["B", "injury_rate__practice_limited"] == pytest.approx(0.25)

    def test_max_consumed_stamp_is_true_and_strictly_before_the_instant(self):
        """`_rate_max_stamp_utc` must be the REAL max stamp the aggregation consumed — it is
        the guard record's source_timestamp, so a `<`→`≤`/wrong-instant bug must land here."""
        out = W2B.engineer_injury_rate_features(_rate_feat()).set_index("gsis_id")
        assert out.loc["A", "_rate_max_stamp_utc"] == pd.Timestamp("2024-10-02 15:00:00", tz="UTC")
        assert out.loc["B", "_rate_max_stamp_utc"] == pd.Timestamp("2024-10-04 20:00:00", tz="UTC")
        assert out.loc["A", "_rate_max_stamp_utc"] < pd.Timestamp(THU, tz="UTC")
        assert out.loc["B", "_rate_max_stamp_utc"] < pd.Timestamp(SUN, tz="UTC")

    def test_stamp_exactly_at_the_instant_is_not_counted(self):
        """The bound is STRICT: a stamp AT gameday 00:00 UTC cannot be proven pre-game."""
        feat = _rate_feat()
        feat.loc[feat["gsis_id"] == "A", "_inj_dm_utc"] = pd.Timestamp(THU, tz="UTC")
        out = W2B.engineer_injury_rate_features(feat).set_index("gsis_id")
        assert out.loc["A", "injury_rate__listed"] == pytest.approx(0.0)
        assert pd.isna(out.loc["A", "_rate_max_stamp_utc"])
        # …but Sunday still counts it (midnight Thursday < midnight Sunday)
        assert out.loc["B", "injury_rate__listed"] == pytest.approx(0.5)

    def test_2025_family_is_nan_not_zero(self):
        """⛔ fillna(0) on this family is the NF-W0b snap bug in a new costume: NULL means
        UNMEASURED (no date_modified upstream), never 'no one is listed'."""
        feat = _rate_feat()
        feat["season"] = 2025
        out = W2B.engineer_injury_rate_features(feat)
        assert out["injury_rate__listed"].isna().all()
        assert not (out["injury_rate__listed"] == 0.0).any()  # the explicit fillna(0) tripwire
        assert (out["injury_rate__observed"] == 0.0).all()

    def test_denominator_is_the_whole_position_week(self):
        """Unlisted players count in the denominator — the rate is a population share, not a
        share of the listed."""
        out = W2B.engineer_injury_rate_features(_rate_feat()).set_index("gsis_id")
        # 4 modeled RBs; Sunday numerator = 2 listed → 0.5 (not 2/2 = 1.0)
        assert out.loc["D", "injury_rate__listed"] == pytest.approx(0.5)


# ── the PIT gate has teeth on the rate records (the INC-39 real-leg discipline) ─────────────────
def _pit_feat(rate_stamp_offset_hours: int) -> pd.DataFrame:
    rows = []
    for i, gsis in enumerate(("A", "B")):
        rows.append({
            "label": WF.LABEL_PLAYED, "season": 2024, "week": 1, "gsis_id": gsis,
            "position": "RB", "gw": 0,
            "_target_gameday": SUN,
            "_window_end_day": SUN - pd.Timedelta(days=7),
            "_inj_dm_utc": pd.NaT,
            "_rate_max_stamp_utc": (
                pd.Timestamp(SUN, tz="UTC") + pd.Timedelta(hours=rate_stamp_offset_hours)
                if i == 0 else pd.NaT
            ),
        })
    return pd.DataFrame(rows)


class TestPitGate:
    def test_clean_group_is_kept_and_rate_records_counted(self):
        audit = W2B.run_pit_gate_w2b(_pit_feat(rate_stamp_offset_hours=-30))
        assert audit["rows_dropped"] == 0
        assert audit["rate_records_checked"] == 1
        assert len(audit["kept_index"]) == 2

    def test_late_rate_stamp_drops_the_whole_game_group_fail_closed(self):
        """A rate aggregation that consumed a post-instant stamp is a leak even when every
        player-level record is clean — the gate must reject on the RATE record alone."""
        audit = W2B.run_pit_gate_w2b(_pit_feat(rate_stamp_offset_hours=+9))
        assert audit["rows_dropped"] == 2
        assert audit["groups_dropped"], "the guard passed a post-projection rate stamp"
        reasons = audit["groups_dropped"][0]["reasons"]
        assert any("AFTER_PROJECTION" in r for r in reasons)


# ── the permutation anchor must not touch the foil's rate columns ───────────────────────────────
class TestPermutation:
    def test_rate_columns_are_untouched_and_player_columns_move(self):
        """The permuted arm destroys PLAYER linkage only. Permuting the rate columns would
        (a) mutate the foil's own features and (b) re-introduce the marginal channel the foil
        exists to absorb — the anchor would stop measuring content."""
        rng = np.random.default_rng(3)
        n = 300
        df = pd.DataFrame({
            "position": np.where(rng.random(n) < 0.5, "RB", "WR"),
            "gw": rng.integers(0, 3, size=n),
        })
        for c in W2.INJURY_FEATURES:
            df[c] = rng.random(n).round(3)
        for c in W2B.RATE_FEATURES:
            df[c] = rng.random(n).round(3)
        out = W2.permute_injury_within_pos_week(df)
        for c in W2B.RATE_FEATURES:
            pd.testing.assert_series_equal(out[c], df[c])
        moved = any(
            not out.loc[grp.index, list(W2.INJURY_FEATURES)].equals(
                df.loc[grp.index, list(W2.INJURY_FEATURES)])
            for _, grp in df.groupby(["position", "gw"])
        )
        assert moved, "the permutation never moved a player-level value (NF1.7 (a))"


# ── gate composition: every clause independently RED-provable (NF-D17) ──────────────────────────
def _passing_sel() -> dict:
    return {
        "beats_foil": True, "beats_production": True,
        "fold_clause": {"passes": True},
        "pbo": 0.0, "dsr": 1.0,
        "anchors": {
            "nihilist_loses": True, "pos_marginal_loses": True,
            "winner_beats_permuted": True, "permuted_lift_not_significant": True,
            "no_arm_beats_own_oracle": True, "foil_respects_oracle": True,
        },
        "coverage": {"blocking_shortfall": False},
    }


def _break(sel: dict, path: str) -> dict:
    parts = path.split(".")
    node = sel
    for k in parts[:-1]:
        node = node[k]
    leaf = parts[-1]
    node[leaf] = {"pbo": 0.9, "dsr": 0.1}.get(leaf, not node[leaf])
    return sel


class TestGateComposition:
    def test_all_clauses_green_ships(self):
        gate = W2B.position_gate_w2b(_passing_sel(), fdr_pass=True)
        assert gate["ship"] and all(gate["checks"].values())

    @pytest.mark.parametrize("path,check", [
        ("beats_foil", "beats_foil"),
        ("beats_production", "beats_production"),
        ("fold_clause.passes", "fold_consistency"),
        ("pbo", "pbo_ok"),
        ("dsr", "dsr_ok"),
        ("anchors.nihilist_loses", "degenerates_lose"),
        ("anchors.pos_marginal_loses", "degenerates_lose"),
        ("anchors.winner_beats_permuted", "permutation_behaves"),
        ("anchors.permuted_lift_not_significant", "permutation_behaves"),
        ("anchors.no_arm_beats_own_oracle", "oracle_floors_respected"),
        ("coverage.blocking_shortfall", "coverage_floor_ok"),
    ])
    def test_each_clause_flips_the_gate_alone(self, path, check):
        """The NF-D17 discipline: the fixture satisfies every OTHER clause, so only the broken
        one can flip the verdict — and the mutation is asserted to have landed."""
        sel = _break(_passing_sel(), path)
        assert sel != _passing_sel(), "the mutation did not land (#682)"
        gate = W2B.position_gate_w2b(sel, fdr_pass=True)
        assert not gate["ship"]
        assert not gate["checks"][check]
        others = {k: v for k, v in gate["checks"].items() if k != check}
        assert all(others.values()), f"the {path} flip tripped an unrelated clause: {others}"

    def test_fdr_clause_flips_the_gate_alone(self):
        gate = W2B.position_gate_w2b(_passing_sel(), fdr_pass=False)
        assert not gate["ship"] and not gate["checks"]["fdr_ok"]

    def test_none_pbo_dsr_never_pass(self):
        """UNDEFINED is never a pass (NF1.7 (a)): a stat that could not be computed blocks."""
        for field in ("pbo", "dsr"):
            sel = _passing_sel()
            sel[field] = None
            gate = W2B.position_gate_w2b(sel, fdr_pass=True)
            assert not gate["ship"]


# ── the hand null-classifier (the NF-D18/MH2.7 classify_null gap, hit twice) ────────────────────
class TestHandClassifier:
    def _checks(self, **overrides) -> dict:
        base = {c: True for c in W2B.STATISTICAL_CHECKS + W2B.ANCHOR_CHECKS}
        base.update(overrides)
        return base

    def test_pure_anchor_refusal_is_constraint_refused_with_no_retest_trigger(self):
        out = W2B.hand_classify_refusal(self._checks(permutation_behaves=False))
        assert out is not None
        assert out["state"] == "CONSTRAINT_REFUSED"
        assert out["retest_trigger"] is None, (
            "⛔ a p≈0 registration refusal must never publish a sample-size re-test trigger")

    def test_oracle_refusal_is_also_constraint_refused(self):
        out = W2B.hand_classify_refusal(self._checks(oracle_floors_respected=False))
        assert out is not None and out["state"] == "CONSTRAINT_REFUSED"

    def test_statistical_failure_defers_to_classify_null(self):
        """A null with ANY statistical component is the instrument's to classify — the hand
        rule covers ONLY the state the instrument lacks."""
        assert W2B.hand_classify_refusal(
            self._checks(permutation_behaves=False, dsr_ok=False)) is None
        assert W2B.hand_classify_refusal(self._checks(beats_foil=False)) is None
        assert W2B.hand_classify_refusal(self._checks(beats_production=False)) is None

    def test_no_failure_returns_none(self):
        assert W2B.hand_classify_refusal(self._checks()) is None

    def test_check_partition_matches_the_gate(self):
        """Every gate check is claimed by exactly one side of the hand rule — an unclaimed
        check would silently fall out of the classification (the NF-C0e wired-≠-invoked shape)."""
        gate = W2B.position_gate_w2b(_passing_sel(), fdr_pass=True)
        assert set(gate["checks"]) == set(W2B.STATISTICAL_CHECKS) | set(W2B.ANCHOR_CHECKS)


# ── fold/anchor registration invariants ─────────────────────────────────────────────────────────
class TestRegistration:
    def test_folds_inherited_unchanged_from_nf_w2(self):
        assert W2B.TEST_BLOCKS_W2B == W2.TEST_BLOCKS_W2
        assert W2B.SHADOW_BLOCKS_W2B == W2.SHADOW_BLOCKS_W2

    def test_dsr_trial_field_is_the_declared_family_only(self):
        """The MH2.5 landmine: a degenerate/anchor in the trial field inflates V. The trial
        field is the 3 real arms; every anchor (incl. both degenerates and the production
        incumbent) is outside it."""
        assert len(W2B.REAL_ARMS_W2B) == 3
        assert not set(W2B.REAL_ARMS_W2B) & set(W2B.ANCHORS_W2B)
        assert W2B.FOIL_W2B not in W2B.REAL_ARMS_W2B
        for must_be_anchor in ("nihilist_zero", "pos_marginal", "base_noRate", "inj_permuted"):
            assert must_be_anchor in W2B.ANCHORS_W2B

    def test_every_arm_and_foil_has_an_own_form_oracle(self):
        assert set(W2B.ORACLE_OF_FORM_W2B) == set(W2B.REAL_ARMS_W2B) | {W2B.FOIL_W2B}
