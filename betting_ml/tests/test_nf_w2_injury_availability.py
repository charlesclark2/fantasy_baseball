"""NF-W2 guards — the availability channel (injury_report family) on the weekly projection.

Each test is independently RED-provable: it fails when the specific contract it names is broken
(verified against deliberately-broken in-process variants during development — the #682
mutation-must-land discipline). Fast-gate rules honored: no `pipeline` import, no network/IO at
import, no module-level state mutation.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quant_sports_intel_models.football.nfl.fantasy import weekly_frame as WF
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection_w2 as W2


# ── helpers ─────────────────────────────────────────────────────────────────────────────────────
def _mini_feat(rows: list[dict]) -> pd.DataFrame:
    base = {
        "label": WF.LABEL_PLAYED,
        "position": "RB",
        "week": 1,
        "gw": 0,
    }
    return pd.DataFrame([{**base, **r} for r in rows])


def _inj(rows: list[dict]) -> pd.DataFrame:
    base = {"report_status": "Out", "practice_status": "Did Not Participate In Practice"}
    return pd.DataFrame([{**base, **r} for r in rows])


GAMEDAY = pd.Timestamp("2024-10-06")  # a Sunday


# ── provenance ──────────────────────────────────────────────────────────────────────────────────
class TestProvenance:
    def test_registered_features_pass(self):
        W2.assert_feature_provenance_w2(W2.FEATURES_W2)

    def test_unknown_family_rejects(self):
        with pytest.raises(WF.LeakageError, match="unknown provenance"):
            W2.assert_feature_provenance_w2(W2.FEATURES_W2 + ("mystery__thing",))

    def test_leaky_token_rejects(self):
        with pytest.raises(WF.LeakageError, match="leaky"):
            W2.assert_feature_provenance_w2(
                W2.FEATURES_W2 + ("injury_report__home_score",))

    def test_era_token_rejects(self):
        with pytest.raises(WF.LeakageError, match="participation-era"):
            W2.assert_feature_provenance_w2(W2.FEATURES_W2 + ("injury_report__route_thing",))

    def test_features_w2_is_exactly_champion_plus_injury_family(self):
        """The matched-pair identity at the feature-list level: every arm is the NF-W1 champion's
        bundle PLUS the injury family — nothing else moved (NF-D10)."""
        assert W2.FEATURES_W2 == WP.FEATURES + W2.INJURY_FEATURES


# ── admissibility (the PIT bound) ───────────────────────────────────────────────────────────────
class TestAdmissibility:
    def test_row_stamped_before_gameday_is_listed(self):
        feat = _mini_feat([{"season": 2024, "gsis_id": "A", "_target_gameday": GAMEDAY}])
        inj = _inj([{"season": 2024, "week": 1, "gsis_id": "A",
                     "date_modified": "2024-10-04 10:00:00-05:00"}])
        out = W2.engineer_injury_features(feat, inj)
        assert out["injury_report__listed"].iloc[0] == 1.0
        assert out["injury_report__status_out"].iloc[0] == 1.0
        assert out["injury_report__practice_dnp"].iloc[0] == 1.0
        assert pd.notna(out["_inj_dm_utc"].iloc[0])

    def test_row_stamped_on_gameday_is_excluded_fail_closed(self):
        """A stamp AT/AFTER gameday 00:00 UTC cannot be proven pre-game → the player-week reads
        as unlisted and NO stamp is consumed (PIT-honesty over completeness)."""
        feat = _mini_feat([{"season": 2024, "gsis_id": "A", "_target_gameday": GAMEDAY}])
        inj = _inj([{"season": 2024, "week": 1, "gsis_id": "A",
                     "date_modified": "2024-10-06 09:00:00+00:00"}])
        out = W2.engineer_injury_features(feat, inj)
        assert out["injury_report__listed"].iloc[0] == 0.0
        assert out["injury_report__status_out"].iloc[0] == 0.0
        assert pd.isna(out["_inj_dm_utc"].iloc[0])

    def test_unlisted_verified_player_reads_semantic_zero(self):
        feat = _mini_feat([{"season": 2024, "gsis_id": "B", "_target_gameday": GAMEDAY}])
        out = W2.engineer_injury_features(feat, _inj([]).reindex(
            columns=["season", "week", "gsis_id", "report_status", "practice_status",
                     "date_modified"]))
        assert out["injury_report__listed"].iloc[0] == 0.0
        assert out["injury_report__observed"].iloc[0] == 1.0

    def test_latest_stamp_wins_the_dedupe(self):
        feat = _mini_feat([{"season": 2024, "gsis_id": "A", "_target_gameday": GAMEDAY}])
        inj = _inj([
            {"season": 2024, "week": 1, "gsis_id": "A", "report_status": "Questionable",
             "date_modified": "2024-10-02 10:00:00-05:00"},
            {"season": 2024, "week": 1, "gsis_id": "A", "report_status": "Out",
             "date_modified": "2024-10-04 10:00:00-05:00"},
        ])
        out = W2.engineer_injury_features(feat, inj)
        assert out["injury_report__status_out"].iloc[0] == 1.0
        assert out["injury_report__status_questionable"].iloc[0] == 0.0


# ── the 2025 shadow era: NULL means unmeasured, never healthy ───────────────────────────────────
class TestShadowEra:
    def test_2025_family_is_nan_not_zero(self):
        """⛔ fillna(0) on this family is the NF-W0b snap bug in a new costume: a NULL means the
        family is UNMEASURED (upstream deleted date_modified), never 'healthy'."""
        feat = _mini_feat([{"season": 2025, "gsis_id": "A",
                            "_target_gameday": pd.Timestamp("2025-10-05")}])
        inj = _inj([{"season": 2025, "week": 1, "gsis_id": "A", "date_modified": None}])
        out = W2.engineer_injury_features(feat, inj)
        assert pd.isna(out["injury_report__listed"].iloc[0])
        assert pd.isna(out["injury_report__status_out"].iloc[0])
        assert out["injury_report__listed"].iloc[0] != 0.0  # the explicit fillna(0) tripwire
        assert out["injury_report__observed"].iloc[0] == 0.0

    def test_shadow_blocks_disjoint_from_gated_and_gated_inside_verified_era(self):
        assert not set(W2.TEST_BLOCKS_W2) & set(W2.SHADOW_BLOCKS_W2)
        assert all(season <= W2.INJURY_VERIFIED_MAX_SEASON for season, _ in W2.TEST_BLOCKS_W2)
        assert all(season > W2.INJURY_VERIFIED_MAX_SEASON for season, _ in W2.SHADOW_BLOCKS_W2)


# ── the matched foil is mechanically the NF-W1 champion ─────────────────────────────────────────
def _fit_frame(n: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    feats = ["prior_week_box__ppr_l4_mean", "snap_share__l4_mean", "game_context__week_index"]
    df = pd.DataFrame(rng.normal(size=(n, len(feats))), columns=feats)
    df["position"] = np.where(rng.random(n) < 0.5, "RB", "WR")
    y = np.maximum(0.0, 5 + 4 * df[feats[0]] + rng.normal(scale=3, size=n))
    y[rng.random(n) < 0.3] = 0.0
    df["fantasy_points"] = y
    return df


class TestFoilIdentity:
    @pytest.mark.slow
    def test_base_hurdle_equals_the_nf_w1_champion_fit(self):
        """`hurdle_parts` + `mix_parts` with both legs on the same features must reproduce
        `WP.fit_lgbm_hurdle` EXACTLY — the incumbent foil is the NF-W1 champion, not a
        re-implementation drifting beside it."""
        train, test = _fit_frame(400, 1), _fit_frame(80, 2)
        feats = ["prior_week_box__ppr_l4_mean", "snap_share__l4_mean", "game_context__week_index"]
        expected = WP.fit_lgbm_hurdle(train, test, feats)
        p0, cond = W2.hurdle_parts(train, test, feats, feats)
        got = W2.mix_parts(p0, cond)
        np.testing.assert_allclose(got, expected, rtol=0, atol=1e-12)


# ── the override device ─────────────────────────────────────────────────────────────────────────
def _override_frames():
    n = W2.OVERRIDE_MIN_N + 50
    train = pd.DataFrame({
        "injury_report__observed": 1.0,
        "injury_report__status_out": [1.0] * n + [0.0] * n,
        "injury_report__status_doubtful": 0.0,
        "fantasy_points": [0.0] * n + [10.0] * n,
    })
    test = pd.DataFrame({
        "injury_report__status_out": [1.0, 0.0, np.nan],
        "injury_report__status_doubtful": [0.0, 0.0, np.nan],
    })
    return train, test


class TestOverride:
    def test_replaces_only_admissible_out_doubtful_rows(self):
        train, test = _override_frames()
        p0 = np.array([0.2, 0.2, 0.2])
        out, meta = W2.override_p0(p0, train, test)
        assert out[0] == pytest.approx(1.0)      # Out row → empirical P(zero|Out∪Dbtf)
        assert out[1] == 0.2                     # untouched
        assert out[2] == 0.2                     # shadow-NaN row → untouched
        assert meta["n_test_overridden"] == 1

    def test_raises_loudly_on_a_thin_cell(self):
        """A device that fails to fit must fail LOUDLY, never silently no-op (NF1.7 (a))."""
        train, test = _override_frames()
        thin = train.iloc[: W2.OVERRIDE_MIN_N - 1]
        with pytest.raises(ValueError, match="too thin"):
            W2.override_p0(np.array([0.2, 0.2, 0.2]), thin, test)


# ── the mixture ─────────────────────────────────────────────────────────────────────────────────
class TestMixture:
    def test_p0_one_is_a_point_mass_at_zero(self):
        cond = np.tile(np.linspace(1, 20, len(WP.Q_LEVELS)), (1, 1))
        q = W2.mix_parts(np.array([1.0]), cond)
        assert np.all(q == 0.0)

    def test_p0_zero_reproduces_the_conditional(self):
        cond = np.tile(np.linspace(1, 20, len(WP.Q_LEVELS)), (1, 1))
        q = W2.mix_parts(np.array([0.0]), cond)
        np.testing.assert_allclose(q[0], np.sort(cond[0]), atol=1e-9)


# ── the permutation anchor ──────────────────────────────────────────────────────────────────────
class TestPermutation:
    def test_preserves_the_within_group_multiset_and_moves_values(self):
        rng = np.random.default_rng(7)
        n = 400
        df = pd.DataFrame({
            "position": np.where(rng.random(n) < 0.5, "RB", "WR"),
            "gw": rng.integers(0, 3, size=n),
        })
        for c in W2.INJURY_FEATURES:
            df[c] = rng.random(n).round(3)
        out = W2.permute_injury_within_pos_week(df)
        moved = False
        for (pos, gw), grp in df.groupby(["position", "gw"]):
            for c in W2.INJURY_FEATURES:
                a = np.sort(grp[c].to_numpy())
                b = np.sort(out.loc[grp.index, c].to_numpy())
                np.testing.assert_array_equal(a, b)
            if not out.loc[grp.index, list(W2.INJURY_FEATURES)].equals(
                    df.loc[grp.index, list(W2.INJURY_FEATURES)]):
                moved = True
        assert moved, "the permutation never moved a value — a vacuous anchor (NF1.7 (a))"

    def test_family_vector_stays_coherent_per_row(self):
        """The columns are permuted JOINTLY: a row keeps a real player's whole family vector."""
        rng = np.random.default_rng(11)
        n = 200
        df = pd.DataFrame({"position": ["RB"] * n, "gw": [0] * n})
        marker = rng.permutation(n).astype(float)
        for c in W2.INJURY_FEATURES:
            df[c] = marker  # all columns identical → any coherent permutation keeps them identical
        out = W2.permute_injury_within_pos_week(df)
        arr = out[list(W2.INJURY_FEATURES)].to_numpy()
        assert (arr == arr[:, :1]).all(), "columns were permuted independently — vector broken"


# ── the PIT gate has teeth (real guard, real records — the INC-39 real-leg discipline) ──────────
def _pit_feat(dm_offset_hours: int, gameday: pd.Timestamp = GAMEDAY) -> pd.DataFrame:
    rows = []
    for i, gsis in enumerate(("A", "B")):
        rows.append({
            "label": WF.LABEL_PLAYED, "season": 2024, "week": 1, "gsis_id": gsis,
            "position": "RB", "gw": 0,
            "_target_gameday": gameday,
            "_window_end_day": gameday - pd.Timedelta(days=7),
            "_inj_dm_utc": (
                pd.Timestamp(gameday, tz="UTC") + pd.Timedelta(hours=dm_offset_hours)
                if i == 0 else pd.NaT
            ),
        })
    return pd.DataFrame(rows)


class TestPitGate:
    def test_clean_group_is_kept(self):
        feat = _pit_feat(dm_offset_hours=-30)  # stamped the day before gameday
        audit = W2.run_pit_gate_w2(feat)
        assert audit["rows_dropped"] == 0
        assert audit["injury_records_checked"] == 1
        assert len(audit["kept_index"]) == 2

    def test_late_injury_stamp_drops_the_whole_game_group_fail_closed(self):
        feat = _pit_feat(dm_offset_hours=+9)  # stamped ON gameday, after 00:00 UTC
        audit = W2.run_pit_gate_w2(feat)
        assert audit["rows_dropped"] == 2
        assert audit["groups_dropped"], "the guard passed a post-projection injury stamp"
        reasons = audit["groups_dropped"][0]["reasons"]
        assert any("AFTER_PROJECTION" in r for r in reasons)
