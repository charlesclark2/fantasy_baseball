"""Guards for NF-W1 — the lean weekly per-game distributional projection.

The load-bearing invariants, each independently RED-provable (NF-D17: a guard on `A and B and C`
proves nothing about A unless its fixture satisfies B and C):

  1. the NF-W0a PIT leakage guard is INVOKED at the feature-assembly boundary (runtime spy + a
     comment-stripped source check on the runner — the NF-C0e "wired ≠ invoked" class);
  2. a week whose feature window cannot be proven point-in-time clean is DROPPED fail-closed;
  3. snap features are NULL-bearing end to end — no fillna(0) resurrection of the NF-W0b bug;
  4. provenance clauses (unknown prefix / leaky token / participation-era token) each reject
     independently;
  5. the degenerate all-zero ceiling is scored every run and its loss is a live gate clause;
  6. selection is CRPS, never MAE (the NF-D11/NF-D14 inversion — QB/TE conditional median is 0.0);
  7. CRPS/mixture/fold/ROS arithmetic identities.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quant_sports_intel_models.football.nfl.fantasy import weekly_frame as WF
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP
from quant_sports_intel_models.football.nfl.pit import leakage_guard as LG


# ── synthetic lake ──────────────────────────────────────────────────────────────────────────────
def _synthetic_sources(n_weeks: int = 6, season: int = 2023):
    teams = ["AAA", "BBB", "CCC", "DDD"]
    players = [
        ("P1", "QB", "AAA"), ("P2", "RB", "AAA"), ("P3", "WR", "BBB"),
        ("P4", "TE", "BBB"), ("P5", "WR", "CCC"), ("P6", "RB", "DDD"),
    ]
    sched_rows, ros_rows, stat_rows, snap_rows = [], [], [], []
    day0 = pd.Timestamp("2023-09-07")
    for w in range(1, n_weeks + 1):
        gameday = (day0 + pd.Timedelta(days=7 * (w - 1))).strftime("%Y-%m-%d")
        # week 4: AAA/BBB on bye (no game row) — build_spine constructs the bye rows
        if w != 4:
            sched_rows.append((season, w, "AAA", "BBB", gameday, 1))
        sched_rows.append((season, w, "CCC", "DDD", gameday, 0))
        for pid, pos, team in players:
            status = "INA" if (pid == "P2" and w == 3) else "ACT"
            if team in ("AAA", "BBB") and w == 4:
                continue  # roster feed emits NO row on a bye
            ros_rows.append((season, w, team, pos, status, pid))
            plays = status == "ACT"
            if plays:
                pts = {"P1": 18.0, "P2": 12.0, "P3": 14.0, "P4": 7.0, "P5": 11.0, "P6": 9.0}[pid]
                pts += 0.5 * w
                opp = {"AAA": "BBB", "BBB": "AAA", "CCC": "DDD", "DDD": "CCC"}[team]
                stat_rows.append((season, w, pid, pos, team, opp, pts,
                                  8.0, 5.0, 30.0 if pos == "QB" else 0.0, 4.0,
                                  250.0 if pos == "QB" else 0.0, 40.0, 55.0))
                if pid != "P5":  # P5: NO snap rows at all — must stay NULL, never 0
                    snap_rows.append((season, w, pid, 0.7, 45.0))
    schedule = pd.DataFrame(sched_rows, columns=[
        "season", "week", "home_team", "away_team", "gameday", "div_game"])
    rosters = pd.DataFrame(ros_rows, columns=[
        "season", "week", "team", "position", "status", "gsis_id"])
    stats = pd.DataFrame(stat_rows, columns=[
        "season", "week", "player_id", "position", "team", "opponent_team",
        "fantasy_points_ppr", "carries", "targets", "attempts", "receptions",
        "passing_yards", "rushing_yards", "receiving_yards"])
    snaps = pd.DataFrame(snap_rows, columns=[
        "season", "week", "gsis_id", "offense_pct", "offense_snaps"])
    return rosters, schedule, stats, snaps


def _frame_and_sources():
    rosters, schedule, stats, snaps = _synthetic_sources()
    spine = WF.build_spine(rosters, schedule)
    frame = WF.attach_labels(
        spine, stats, label_version=WP.LABEL_VERSION,
        label_as_of_timestamp="2026-08-06T00:00:00+00:00",
        scoring_system_id="ppr", snaps=snaps)
    return frame, stats, snaps, schedule


# ── 1. the PIT guard is INVOKED, not just imported ──────────────────────────────────────────────
class TestPitGuardIsInvoked:
    def test_assemble_matrix_calls_assert_point_in_time_with_records(self):
        frame, stats, snaps, schedule = _frame_and_sources()
        calls = {"n": 0, "records": 0}

        def spy(records, projection_ts, *, store_index=None, **kw):
            calls["n"] += 1
            records = list(records)
            calls["records"] += len(records)
            return LG.assert_point_in_time(records, projection_ts, store_index=store_index)

        modeled, audit = WP.assemble_matrix(frame, stats, snaps, schedule, guard=spy)
        assert calls["n"] > 0, "the PIT guard was never invoked — the NF-C0e wired-≠-invoked defect"
        assert calls["records"] > 0, "the PIT guard ran on zero records — vacuous (NF1.7 (a))"
        assert audit["weeks_checked"] == calls["n"]
        assert len(modeled) > 0

    def test_the_real_guard_passes_on_the_clean_synthetic_assembly(self):
        frame, stats, snaps, schedule = _frame_and_sources()
        modeled, audit = WP.assemble_matrix(frame, stats, snaps, schedule)
        assert audit["rows_dropped"] == 0
        assert audit["records_checked"] == len(modeled)
        # byes are excluded from the modeled population (deterministic schedule-known zeros)
        assert (modeled["label"] != WF.LABEL_BYE).all()

    def test_runner_source_invokes_the_boundary_in_code_not_prose(self):
        """INC-38: a source guard prose can satisfy is vacuous — strip comment lines first."""
        from pathlib import Path
        src = (Path(WP.__file__).parent / "run_nf_w1_weekly_bakeoff.py").read_text()
        code = "\n".join(
            ln for ln in src.splitlines() if not ln.lstrip().startswith("#")
        )
        assert "WP.assemble_matrix(" in code, "the runner does not call the assembly boundary"
        assert "WP.run_pit_gate(" in code, (
            "the runner's cache-hit path does not re-run the PIT gate — a cached matrix would "
            "only ever be guard-checked on the day the cache was written"
        )

    def test_a_consumed_pit_store_source_without_an_index_refuses(self, monkeypatch):
        frame, stats, snaps, schedule = _frame_and_sources()
        feat = WP.engineer_features(frame, stats, snaps, schedule)
        monkeypatch.setattr(WP, "PIT_STORE_SOURCES_CONSUMED", ("weather",))
        with pytest.raises(NotImplementedError):
            WP.run_pit_gate(feat)


# ── 2. fail-closed on an un-provable window ─────────────────────────────────────────────────────
class TestFailClosedWindow:
    def test_a_week_whose_window_reaches_the_target_is_dropped(self):
        frame, stats, snaps, schedule = _frame_and_sources()
        feat = WP.engineer_features(frame, stats, snaps, schedule)
        # simulate the 2020 rescheduling shape: week 5's prior-window max gameday lands ON its
        # projection day (a prior-week game played after this week's first kickoff)
        wk = (feat["season"] == 2023) & (feat["week"] == 5)
        feat.loc[wk, "_window_end_day"] = feat.loc[wk, "_projection_day"]
        audit = WP.run_pit_gate(feat)
        dropped_weeks = {(d["season"], d["week"]) for d in audit["weeks_dropped"]}
        assert (2023, 5) in dropped_weeks
        kept = feat.loc[audit["kept_index"]]
        assert not ((kept["season"] == 2023) & (kept["week"] == 5)).any()
        # every OTHER week is retained — fail-closed is per-week, not whole-build
        assert audit["weeks_checked"] > len(dropped_weeks)


# ── 3. snap features are NULL-bearing (NF-W0b constraint 9) ─────────────────────────────────────
class TestSnapNullContract:
    def test_a_player_with_no_snap_rows_gets_nan_not_zero(self):
        frame, stats, snaps, schedule = _frame_and_sources()
        feat = WP.engineer_features(frame, stats, snaps, schedule)
        p5 = feat[(feat["gsis_id"] == "P5") & (feat["week"] >= 2)]
        assert len(p5) > 0
        assert p5["snap_share__l1"].isna().all(), (
            "an unmeasured snap week must stay NULL — fillna(0) silently restores the NF-W0b "
            "fabricated-zero bug ('unmeasured ⇒ 0 snaps ⇒ looks like a healthy scratch')"
        )
        assert p5["snap_share__l4_mean"].isna().all()
        assert (p5["snap_share__observed_l4"] == 0.0).all()

    def test_a_player_with_snap_rows_gets_real_values_and_full_observation(self):
        frame, stats, snaps, schedule = _frame_and_sources()
        feat = WP.engineer_features(frame, stats, snaps, schedule)
        p1 = feat[(feat["gsis_id"] == "P1") & (feat["week"].isin([2, 3]))]
        assert np.allclose(p1["snap_share__l1"].astype(float), 0.7)
        assert np.allclose(p1["snap_share__observed_l4"].astype(float), 1.0)


# ── 4. provenance clauses — one isolating fixture per clause (NF-D17) ───────────────────────────
class TestProvenanceClauses:
    def test_the_registered_feature_list_passes(self):
        WP.assert_feature_provenance(WP.FEATURES)

    def test_unknown_prefix_rejects(self):
        # clean of leaky and era tokens, so ONLY the unknown-provenance clause can fire
        with pytest.raises(WF.LeakageError, match="unknown provenance"):
            WP.assert_feature_provenance(["mystery_family__ppr_l4"])

    def test_leaky_token_rejects_on_the_full_engineered_name(self):
        # known family prefix + no era token, so ONLY the leaky clause can fire
        with pytest.raises(WF.LeakageError, match="leaky"):
            WP.assert_feature_provenance(["game_context__game_temp"])

    def test_participation_era_token_rejects(self):
        # known family prefix + no leaky token, so ONLY the era clause can fire
        with pytest.raises(WF.LeakageError, match="era"):
            WP.assert_feature_provenance(["opponent_matchup__pressure_rate_l4"])

    def test_no_registered_feature_carries_an_era_token(self):
        joined = " ".join(WP.FEATURES)
        for tok in WP.ERA_FORBIDDEN_TOKENS:
            assert tok not in joined, (
                f"'{tok}' is a pbp_participation-era leg — the 2023 provider switch (NF-W0c) "
                f"forbids pooling it across the boundary without an era split this slice lacks"
            )


# ── 5 + 6. degenerate ceiling scored + CRPS selects, never MAE ──────────────────────────────────
def _fold_results(n_folds: int, crps_by_arm: dict[str, float], mae_by_arm: dict[str, float] | None = None,
                  pos: str = "RB", jitter: float = 0.01) -> list[dict]:
    """Synthetic fold_results in the runner's exact shape (winner deterministic across folds)."""
    labels = list(WP.REAL_ARMS) + list(WP.FOILS) + list(WP.ANCHORS)
    rng = np.random.default_rng(7)
    out = []
    for i in range(n_folds):
        scores = {}
        for lb in labels:
            c = crps_by_arm.get(lb, 9.0) + float(rng.normal(0, jitter))
            m = (mae_by_arm or {}).get(lb, c)
            row = {"pooled": c, "mae_pooled": m}
            for p in WP.POSITIONS:
                row[p] = c
                row[f"mae_{p}"] = m
            scores[lb] = row
        cov = {lb: {p: {"coverage": 0.81, "n": 500, "nominal": 0.8, "binomial_se": 0.018,
                        "blocking_shortfall": False} for p in WP.POSITIONS}
               for lb in (*WP.REAL_ARMS, *WP.FOILS)}
        out.append({"label": f"f{i}", "scores": scores, "coverage": cov,
                    "n_train": 1000, "n_test": 500})
    return out


class TestSelectionAndGate:
    def _base_crps(self):
        return {
            "lgbm_quantile": 4.0, "lgbm_hurdle": 4.4, "enet_residual": 4.6, "knn_quantile": 4.5,
            "foil_flat": 5.0, "foil_matchup": 4.9,
            "nihilist_zero": 8.0, "pos_marginal": 5.5, "oracle_marginal": 4.2,
            "permuted_within": 6.0, "zero_width": 5.4, "max_width": 6.5,
        }

    def test_winner_is_selected_on_crps_even_when_mae_disagrees(self):
        from quant_sports_intel_models.football.nfl.fantasy import run_nf_w1_weekly_bakeoff as R
        crps = self._base_crps()
        mae = dict(crps)
        mae["lgbm_quantile"], mae["knn_quantile"] = 5.0, 2.0  # MAE prefers knn; CRPS must win out
        sel = R.select_position("RB", _fold_results(8, crps, mae), 8)
        assert sel["winner"] == "lgbm_quantile"
        assert WP.SELECTION_METRIC == "crps_q39"

    def test_the_degenerate_ceiling_is_scored_and_its_loss_gates(self):
        from quant_sports_intel_models.football.nfl.fantasy import run_nf_w1_weekly_bakeoff as R
        sel = R.select_position("RB", _fold_results(8, self._base_crps()), 8)
        assert "nihilist_loses" in sel["anchors"], "the all-zero degenerate was not scored"
        gate = R.position_gate(sel, fdr_pass=True)
        assert gate["ship"] is True
        # flip ONLY the nihilist clause — the fixture satisfies every other check, so this is
        # an isolating proof the degenerate check is live (NF-D17)
        sel_bad = {**sel, "anchors": {**sel["anchors"], "nihilist_loses": False}}
        assert R.position_gate(sel_bad, fdr_pass=True)["ship"] is False

    def test_each_gate_clause_blocks_independently(self):
        from quant_sports_intel_models.football.nfl.fantasy import run_nf_w1_weekly_bakeoff as R
        sel = R.select_position("RB", _fold_results(8, self._base_crps()), 8)
        assert R.position_gate(sel, fdr_pass=True)["ship"] is True
        assert R.position_gate(sel, fdr_pass=False)["ship"] is False
        bad_cov = {**sel, "coverage": {**sel["coverage"], "blocking_shortfall": True}}
        assert R.position_gate(bad_cov, fdr_pass=True)["ship"] is False
        bad_perm = {**sel, "anchors": {**sel["anchors"], "permuted_loses": False}}
        assert R.position_gate(bad_perm, fdr_pass=True)["ship"] is False

    def test_a_foil_win_is_a_null_not_a_ship(self):
        from quant_sports_intel_models.football.nfl.fantasy import run_nf_w1_weekly_bakeoff as R
        crps = self._base_crps()
        crps["foil_flat"] = 3.0  # the honest null wins
        sel = R.select_position("RB", _fold_results(8, crps), 8)
        assert sel["beats_foil"] is False
        assert R.position_gate(sel, fdr_pass=True)["ship"] is False
        assert sel["best_foil"] == "foil_flat"


# ── 7. arithmetic identities ────────────────────────────────────────────────────────────────────
class TestCrpsIdentities:
    def test_point_mass_at_zero_scores_the_absolute_outcome(self):
        y = np.array([0.0, 4.0, 10.0, -2.0])
        q = np.zeros((4, len(WP.Q_LEVELS)))
        crps = WP.crps_from_quantiles(q, y)
        # symmetric grid ⇒ 2·|y|·mean(levels) == |y| exactly
        assert np.allclose(crps, np.abs(y), atol=1e-9)

    def test_perfect_forecast_scores_zero(self):
        y = np.array([3.0, 7.0])
        q = np.repeat(y[:, None], len(WP.Q_LEVELS), axis=1)
        assert np.allclose(WP.crps_from_quantiles(q, y), 0.0, atol=1e-9)

    def test_centered_beats_offset(self):
        rng = np.random.default_rng(3)
        y = rng.normal(10, 3, 400)
        base = np.quantile(rng.normal(10, 3, 4000), WP.Q_LEVELS)
        good = np.repeat(base[None, :], 400, axis=0)
        bad = good + 5.0
        assert WP.crps_from_quantiles(good, y).mean() < WP.crps_from_quantiles(bad, y).mean()


class TestMixtureQuantiles:
    def test_zero_atom_occupies_its_mass(self):
        cond = np.quantile(np.abs(np.random.default_rng(0).normal(10, 3, 2000)), WP.Q_LEVELS)
        q = WP._mixture_quantiles(0.4, cond)
        levels = WP.Q_LEVELS
        assert np.all(q[levels <= 0.4] == 0.0)
        assert np.all(q[levels > 0.45] > 0.0)
        assert np.all(np.diff(q) >= 0)

    def test_negative_conditional_tail_sits_below_the_atom(self):
        cond = np.linspace(-2.0, 20.0, len(WP.Q_LEVELS))
        q = WP._mixture_quantiles(0.3, cond)
        assert q[0] < 0.0
        assert np.all(np.diff(q) >= 0)


class TestFoldsAndRos:
    def test_folds_are_expanding_purged_and_disjoint(self):
        n = 400
        feat = pd.DataFrame({
            "season": np.repeat([2021, 2022, 2023, 2024, 2025], n // 5),
            "week": np.tile(np.repeat(np.arange(1, 11), n // 50), 5),
        })
        sw = feat[["season", "week"]].drop_duplicates().sort_values(["season", "week"])
        sw["gw"] = np.arange(len(sw))
        feat = feat.merge(sw, on=["season", "week"])
        folds = WP.build_folds(feat)
        assert len(folds) > 0
        for f in folds:
            train_gw = feat.loc[f.train_idx, "gw"]
            test_gw = feat.loc[f.test_idx, "gw"]
            assert train_gw.max() <= test_gw.min() - 1 - WP.PURGE_WEEKS
            assert set(f.train_idx).isdisjoint(f.test_idx)

    def test_ros_sums_remaining_weeks_and_widens_by_sqrt(self):
        weekly = pd.DataFrame({
            "gsis_id": ["A"] * 4, "position": ["RB"] * 4, "week": [10, 11, 12, 13],
            "mean": [10.0, 10.0, 10.0, 10.0], "q16": [6.0] * 4, "q84": [14.0] * 4,
        })
        ros = WP.ros_projection(weekly)
        assert len(ros) == 1
        assert ros["ros_mean"].iloc[0] == pytest.approx(40.0)
        sigma_week = (14.0 - 6.0) / 2.0
        want = 1.2815515655446004 * np.sqrt(4 * sigma_week ** 2)
        assert ros["ros_q90"].iloc[0] == pytest.approx(40.0 + want)

    def test_matrix_key_moves_with_the_feature_schema(self):
        assert WP.matrix_key((2016, 2025)) != WP.matrix_key((2016, 2024))
        assert WP.matrix_key((2016, 2025)) != WP.matrix_key(
            (2016, 2025), feature_names=WP.FEATURES[:-1])


class TestFoilForm:
    def test_foil_point_is_eb_shrunk_ppg_times_clipped_matchup(self):
        df = pd.DataFrame({
            "position": ["RB", "RB"],
            "prior_season_priors__ppg_prior": [10.0, np.nan],
            "prior_season_priors__games_prior": [16.0, np.nan],
            "prior_week_box__ppr_sum_s2d": [40.0, 0.0],
            "prior_week_box__games_s2d": [4.0, 0.0],
            "opponent_matchup__dvp_ppr_index_l8": [2.0, np.nan],  # clips to 1.25 / defaults to 1.0
        })
        pos_mean = {"QB": 0.0, "RB": 8.0, "WR": 0.0, "TE": 0.0}
        flat = WP.foil_point(df, pos_mean, matchup=False)
        # veteran: (160 + 40 + 4·8) / (16 + 4 + 4) = 232/24
        assert flat[0] == pytest.approx(232.0 / 24.0)
        # no-history rookie: κ·pos_mean / κ = the position mean
        assert flat[1] == pytest.approx(8.0)
        tilted = WP.foil_point(df, pos_mean, matchup=True)
        assert tilted[0] == pytest.approx(flat[0] * 1.25)  # clip binds
        assert tilted[1] == pytest.approx(flat[1])         # missing index ⇒ neutral 1.0
