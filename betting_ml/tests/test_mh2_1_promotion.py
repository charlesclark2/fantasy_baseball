"""Guards for the MH2.1 champion promotion (total_runs / post_lineup, 2026-08-02).

Fast-gate safe: pure stdlib/numpy/sklearn, no Snowflake, no S3, no `pipeline` import.

WHAT THIS PROTECTS
------------------
The promoted champion is a POINT learner served through an NGBoost-shaped API, replacing a
heteroscedastic NGBoost. Three classes of silent breakage are possible and each is pinned here:

1. **API shape** — `predict_today` calls `model.pred_dist(X).params["loc"|"scale"]`. A wrapper that
   loses that surface raises inside a HALT-tier op and costs the whole slate.
2. **Scope** — the story promotes ONE (target, tier). A registry edit that also moved `pre_lineup`,
   `home_win`, or `run_differential` would ship three unvalidated swaps.
3. **Framing** — the margin decomposes into two sub-floor components, only 3 of 8 folds test the
   served contract, and the selection is on PRICING. Those are the claims a future reader will
   inherit; if they rot out of the record the promotion starts reading as an edge result.

`best_alpha = 0` throughout — no edge, win-rate, or ROI claim.
"""
from __future__ import annotations

import json
import pickle
from pathlib import Path

import numpy as np
import pytest
import yaml

from betting_ml.utils.homoscedastic_regressor import FrozenNormal, HomoscedasticNormalRegressor

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REGISTRY = yaml.safe_load((PROJECT_ROOT / "betting_ml/models/model_registry.yaml").read_text())
TOTALS = REGISTRY["total_runs"]


def _fitted_pipeline(n_features: int = 5, n_rows: int = 200):
    from sklearn.linear_model import ElasticNet
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    rng = np.random.default_rng(0)
    X = rng.normal(size=(n_rows, n_features))
    y = X @ rng.normal(size=n_features) + rng.normal(scale=2.0, size=n_rows) + 9.0
    p = make_pipeline(StandardScaler(), ElasticNet(alpha=0.1, l1_ratio=0.5, random_state=42))
    p.fit(X, y)
    return p, X, y


# ── 1. the serving API the HALT-tier path depends on ──────────────────────────────────────────

class TestServingApiShape:
    def test_pred_dist_exposes_exactly_what_predict_today_reads(self):
        """`pred_dist(X).params["loc"|"scale"]` — the literal call at predict_today L2461-2463 and
        backfill_predictions L415-417. A bare sklearn estimator has no `pred_dist` at all, which is
        the AttributeError this wrapper exists to prevent."""
        p, X, y = _fitted_pipeline()
        m = HomoscedasticNormalRegressor(p, 4.45)
        assert not hasattr(p, "pred_dist"), "premise: the raw estimator lacks the NGBoost surface"

        out = m.pred_dist(X)
        assert set(out.params) >= {"loc", "scale"}
        assert out.params["loc"].shape == (len(X),)
        assert out.params["scale"].shape == (len(X),)
        assert np.allclose(out.params["loc"], p.predict(X))

    def test_scale_is_constant_because_the_predictive_is_homoscedastic(self):
        p, X, _ = _fitted_pipeline()
        out = HomoscedasticNormalRegressor(p, 4.45).pred_dist(X)
        assert len(np.unique(out.params["scale"])) == 1
        assert out.params["scale"][0] == pytest.approx(4.45)

    def test_p_over_line_consumes_the_params_dict_unchanged(self):
        """The served P(over) is `p_over_line(dist, {"loc","scale"}, total_line)`. Proving the dict
        flows through unmodified is what makes this a drop-in for the NGBoost it replaces."""
        from betting_ml.models.total_runs_trainer import p_over_line

        p, X, _ = _fitted_pipeline()
        out = HomoscedasticNormalRegressor(p, 4.45).pred_dist(X)
        pv = p_over_line("Normal", out.params, total_line=np.full(len(X), 8.5))
        assert pv.shape == (len(X),)
        assert np.all((pv >= 0) & (pv <= 1))
        assert pv.std() > 0, "P(over) must still discriminate across games via the mean"

    def test_contract_guard_can_read_the_model_width(self):
        """predict_today's CONTRACT-GUARD SKIPS any model whose width it cannot read, so a wrapper
        that hides `n_features_in_` would silently DISABLE the guard rather than trip it — and the
        models score by column POSITION, so an undetected mismatch is a silent wrong answer."""
        p, X, _ = _fitted_pipeline(n_features=7)
        m = HomoscedasticNormalRegressor(p, 4.45)

        def _model_n_features(_m):  # verbatim from predict_today
            for attr in ("n_features", "n_features_in_"):
                v = getattr(_m, attr, None)
                if v is not None:
                    return int(v)
            return None

        assert _model_n_features(m) == 7

    def test_a_wrapper_around_a_widthless_estimator_raises_rather_than_going_quiet(self):
        class _NoWidth:
            def predict(self, X):
                return np.zeros(len(X))

        m = HomoscedasticNormalRegressor(_NoWidth(), 4.45)
        with pytest.raises(AttributeError, match="n_features_in_"):
            _ = m.n_features_in_

    @pytest.mark.parametrize("bad", [0.0, -1.0, float("nan"), float("inf")])
    def test_a_degenerate_sigma_is_rejected_at_construction(self, bad):
        """σ=0 makes scipy's norm.sf a STEP function — every served P(over) becomes 0 or 1 with no
        exception raised anywhere downstream. Rejecting at construction is the only place this is
        loud."""
        p, _, _ = _fitted_pipeline()
        with pytest.raises(ValueError, match="sigma"):
            HomoscedasticNormalRegressor(p, bad)

    def test_frozen_normal_rejects_mismatched_loc_and_scale(self):
        with pytest.raises(ValueError):
            FrozenNormal(np.zeros(5), np.ones(4))

    def test_the_artifact_is_picklable_at_a_stable_import_path(self):
        """The 2026-07-03 pin landmine: a champion pickle must resolve at load time in
        predict_today. A class defined in a script's __main__ would not."""
        assert HomoscedasticNormalRegressor.__module__ == \
            "betting_ml.utils.homoscedastic_regressor"
        p, X, _ = _fitted_pipeline()
        m = HomoscedasticNormalRegressor(p, 4.45)
        rt = pickle.loads(pickle.dumps(m))
        assert np.allclose(rt.pred_dist(X).params["loc"], m.pred_dist(X).params["loc"])
        assert rt.pred_dist(X).params["scale"][0] == pytest.approx(4.45)


# ── 2. the fit reproduces the arm that was actually scored ────────────────────────────────────

class TestTheFitIsTheValidatedObject:
    def test_sigma_matches_PointNormalSpec_verbatim(self):
        """The bake-off scored `Normal(pred, σ̂)` with σ̂ = the TRAINING residual std (ddof=0). If
        the finalize script estimated σ̂ any other way it would serve a predictive no gate scored —
        and MH2.1's whole case is a calibration case, so σ̂ is the load-bearing quantity."""
        from betting_ml.scripts.finalize_mh2_1_champion import train_residual_sigma

        p, X, y = _fitted_pipeline()
        expected = float(np.std(np.asarray(y, float) - np.asarray(p.predict(X), float)))
        assert train_residual_sigma(p, X, y) == pytest.approx(expected)

    def test_the_learner_is_the_bakeoff_glm_elasticnet_config(self):
        from betting_ml.scripts.finalize_mh2_1_champion import GLM, build_estimator

        assert GLM == {"alpha": 0.1, "l1_ratio": 0.5, "random_state": 42}
        est = build_estimator()
        names = [s[0] for s in est.steps]
        assert names == ["standardscaler", "elasticnet"]

    def test_plus_eb_is_exactly_the_harness_block(self):
        """Drift guard: the promoted contract's extra columns must be the SAME block the bake-off
        scored. A silently different set would make the recorded gates describe another arm."""
        from betting_ml.scripts.e7_9_train_serve_consistency import MLE_AFFECTED_COLS
        from betting_ml.scripts.finalize_mh2_1_champion import PLUS_EB_COLS

        assert set(PLUS_EB_COLS) == set(MLE_AFFECTED_COLS)
        assert len(PLUS_EB_COLS) == 10

    def test_the_finalize_script_defaults_to_snowflake_free(self):
        import inspect

        from betting_ml.scripts import finalize_mh2_1_champion as f

        src = inspect.getsource(f.main)
        assert "refresh_cache=args.refresh_cache" in src
        assert '"--refresh-cache", action="store_true"' in src, "the pull must be OPT-IN"


# ── 3. the contract on disk matches the model that will load it ───────────────────────────────

class TestContractIntegrity:
    def test_served_sidecar_is_the_contract_plus_the_two_imputer_indicators(self):
        contract = json.loads((PROJECT_ROOT / TOTALS["feature_columns_path"].replace(
            "_served.json", ".json")).read_text())["feature_cols"]
        served = json.loads(
            (PROJECT_ROOT / TOTALS["feature_columns_path"]).read_text())["feature_cols"]
        assert set(served) - set(contract) == {"has_starter_platoon_data", "is_new_venue"}
        assert len(served) == len(contract) + 2

    def test_registry_feature_count_matches_the_sidecar(self):
        """The serve-time CONTRACT-GUARD compares the MODEL's width to the SIDECAR's length; if the
        registry's advertised `features` disagrees with the file, the record lies about what ships."""
        served = json.loads(
            (PROJECT_ROOT / TOTALS["feature_columns_path"]).read_text())["feature_cols"]
        assert int(TOTALS["features"]) == len(served) == 25

    def test_the_contract_carries_the_incumbent_base_plus_the_full_eb_block(self):
        from betting_ml.scripts.finalize_mh2_1_champion import PLUS_EB_COLS

        contract = json.loads((PROJECT_ROOT / TOTALS["feature_columns_path"].replace(
            "_served.json", ".json")).read_text())["feature_cols"]
        base = json.loads((
            PROJECT_ROOT
            / "betting_ml/models/total_runs/feature_columns_ngboost_pruned_clustered_deleaked_2026.json"
        ).read_text())["feature_cols"]
        assert set(base).issubset(set(contract)), "the incumbent contract must be a SUBSET"
        assert set(PLUS_EB_COLS).issubset(set(contract))
        assert len(contract) == 23


# ── 4. SCOPE — one target, one tier ───────────────────────────────────────────────────────────

class TestPromotionScope:
    def test_post_lineup_points_at_the_mh2_1_champion(self):
        assert TOTALS["artifact_path"].endswith("glm_elasticnet_plus_eb_mh2_1_post_lineup_2026.pkl")
        assert TOTALS["feature_columns_path"].endswith(
            "feature_columns_mh2_1_total_runs_post_lineup_served.json")
        assert TOTALS["model_version"] == "mh2_1"
        assert TOTALS["model_class"] == "glm_elasticnet"
        assert TOTALS["homoscedastic"] is True
        assert TOTALS["dist"] == "Normal", "p_over_line still reads this"

    def test_pre_lineup_is_UNTOUCHED(self):
        """The story promotes post_lineup ONLY. The morning tier keeps the v6 NGBoost — MH2.1 never
        scored a pre_lineup arm, so moving it would ship an unvalidated model."""
        assert TOTALS["pre_lineup"].endswith("ngboost_normal_deleaked_v6_pre_lineup_2026.pkl")
        assert TOTALS["pre_lineup_model_version"] == "v6"

    def test_the_other_two_targets_are_UNTOUCHED(self):
        assert REGISTRY["home_win"]["model_version"] == "v6"
        assert REGISTRY["run_differential"]["model_version"] == "v6"
        assert "ngboost_normal_deleaked_v6" in REGISTRY["run_differential"]["artifact_path"]

    def test_rollback_targets_the_model_actually_being_replaced(self):
        """`prev_artifact_path` is the rollback. It must name the v6 NGBoost this swap retires —
        not the older v5 it replaced two promotions ago."""
        assert TOTALS["prev_artifact_path"].endswith(
            "ngboost_normal_deleaked_v6_post_lineup_2026.pkl")
        assert TOTALS["prev_feature_columns_path"].endswith(
            "feature_columns_v6_total_runs_post_lineup_served.json")

    def test_bets_stay_paused(self):
        """best_alpha=0 and this is a pricing change. A promotion must not quietly un-pause betting."""
        assert TOTALS["bet_paused"] is True
        assert REGISTRY["total_runs"]["mh2_1_promotion"]["best_alpha"] == 0


# ── 5. the E13.6b calibrator trigger actually fired ───────────────────────────────────────────

def test_the_totals_calibrator_refit_trigger_is_recorded_as_fired():
    """`total_runs_model_rebuild` is a pre-registered refit trigger on the E13.6b isotonic candidate.
    This promotion IS that rebuild, and the candidate was fit on the RETIRED model's served P(over)
    — which came from the very σ this promotion replaces. Wiring it as-is would bake the retired
    model's miscalibration into the new one."""
    cal = TOTALS["totals_serving_calibration"]
    fired = cal["refit_trigger_fired"]
    assert fired["trigger"] == "total_runs_model_rebuild"
    assert "STALE" in fired["status"]
    assert cal["status"].startswith("CANDIDATE"), "it was never live, so holding regresses nothing"


# ── 5b. the CLV scorecard must NOT be re-pinned (the same coin as the invisible stamp) ────────

def test_the_clv_scorecard_pin_stays_v6_and_that_is_correct():
    """⚠️ E7.9 step 7's documented landmine: `mart_clv_labeled_games.sql` HARDCODES
    `model_version = 'v6'`, and "the day a new champion is promoted that mart returns ZERO rows and
    the app's model-vs-market scorecard goes blank — no error, no HALT".

    For MH2.1 it does NOT, and the reason is worth pinning because it is counter-intuitive: the
    stamped `model_version` is derived from **home_win**, which this promotion does not touch, so
    served rows keep reading 'v6' and the mart keeps matching them. The very bundle-stamp coupling
    that made this swap invisible in the app (and that `totals_model_version` exists to work around)
    is ALSO what keeps the scorecard alive here.

    ⇒ Re-pinning this mart to 'mh2_1' would be the actual outage: it would match NOTHING. This test
    exists so a future reader following the step-7 checklist mechanically does not "helpfully"
    update a pin that must not move for a totals-only promotion.
    """
    sql = (PROJECT_ROOT / "dbt/models/mart/mart_clv_labeled_games.sql").read_text()
    assert "model_version = 'v6'" in sql
    assert "model_version = 'mh2_1'" not in sql, (
        "the CLV pin must track the HOME_WIN-derived stamp, which MH2.1 does not change; pinning it "
        "to the totals lineage would match zero rows and blank the scorecard"
    )
    assert REGISTRY["home_win"]["model_version"] == "v6", "premise: the stamp source is unchanged"


# ── 6. FRAMING LOCKS — the claims a future reader inherits ────────────────────────────────────

class TestFramingLocks:
    def test_the_margin_decomposition_is_on_the_record(self):
        """"plus_eb won" is the wrong headline: 59% of the margin is the LEARNER SWAP and NEITHER
        component clears the 0.02 noise floor alone."""
        d = TOTALS["mh2_1_promotion"]["margin_decomposition"]
        assert d["learner_swap"] == 0.0175
        assert d["plus_eb_block"] == 0.0122
        assert d["learner_swap"] + d["plus_eb_block"] == pytest.approx(0.0297, abs=1e-6)
        assert d["learner_swap"] < 0.02 and d["plus_eb_block"] < 0.02
        assert "NEITHER" in d["note"]

    def test_the_three_of_eight_folds_caveat_is_on_the_record(self):
        c = TOTALS["mh2_1_promotion"]["caveats"]["folds_testing_served_contract"]
        assert c.startswith("3 of 8")

    def test_the_e2_1r_reselection_caveat_is_on_the_record(self):
        c = TOTALS["mh2_1_promotion"]["caveats"]["selection_basis"]
        assert "RE-SELECT" in c and "PRICING" in c

    def test_the_sigma_collapse_is_disclosed_not_hidden(self):
        assert "sigma_is_constant" in TOTALS["mh2_1_promotion"]["caveats"]
        assert TOTALS["sigma_served"] == pytest.approx(4.4521, abs=1e-4)

    def test_the_bullpen_v3_seam_is_disclosed(self):
        """The champion trains on 2016+ while bullpen_v3 de-leak caches exist only for 2021+, so two
        contract columns span two measurement conventions. Disclosed, not silently inherited."""
        assert "bullpen_v3_seam" in TOTALS["mh2_1_promotion"]["caveats"]
        assert TOTALS["training_cutoff"] == "2016+"

    def test_the_record_disclaims_edge_rather_than_claiming_it(self):
        """⚠️ A naive "the word 'roi' must not appear" check FAILS on the DISCLAIMER itself ("no
        edge, win-rate, or ROI claim") — it cannot tell an assertion from its negation. So test the
        two things that actually matter: the disclaimer is present, and no AFFIRMATIVE performance
        figure is recorded (a `roi:`/`win_rate:` KEY, or a % claim), since a number is what would
        turn a pricing record into an edge record."""
        promo = TOTALS["mh2_1_promotion"]
        blob = yaml.safe_dump(promo).lower()

        assert "no edge, win-rate, or roi claim" in blob, "the disclaimer must be explicit"
        assert promo["best_alpha"] == 0
        assert "pricing/calibration only" in promo["claim"].lower()

        def _keys(node):
            if isinstance(node, dict):
                for k, v in node.items():
                    yield str(k).lower()
                    yield from _keys(v)
            elif isinstance(node, list):
                for v in node:
                    yield from _keys(v)

        for k in _keys(promo):
            assert not any(bad in k for bad in ("roi", "win_rate", "winrate", "profit", "payout")), \
                f"promotion record carries an affirmative performance key: {k!r}"
        # every recorded gate is a distributional/selection statistic, never a money statistic
        assert set(promo["gates"]) == {
            "crps_margin", "crps_margin_ex_2020", "pbo", "dsr", "fold_consistency", "oracle_floor"}


# ── 7. the swap is VISIBLE in the app ─────────────────────────────────────────────────────────

class TestInAppVisibility:
    def test_predict_today_stamps_a_per_target_totals_version(self):
        """`model_version` is derived from home_win ALONE, so a totals-only swap does not move it —
        measured, not assumed. Without a per-target stamp the champion change is invisible in
        daily_model_predictions and therefore in Admin → Model Freshness."""
        src = (PROJECT_ROOT / "scripts/predict_today.py").read_text()
        assert 'MODEL_VERSION = _registry["home_win"]["model_version"]' in src, \
            "premise: the bundle stamp reads home_win only"
        assert 'TOTALS_MODEL_VERSION = str(_registry["total_runs"].get("model_version")' in src
        assert '"totals_model_version":   TOTALS_MODEL_VERSION' in src
        assert '("totals_model_version", "VARCHAR(20)")' in src, "additive column migration"
        assert "%(totals_model_version)s" in src, "must be bound in the INSERT"

    def test_the_backfill_stamps_the_same_column(self):
        src = (PROJECT_ROOT / "betting_ml/scripts/backfill_predictions.py").read_text()
        assert "totals_model_version" in src
        assert "ADD COLUMN IF NOT EXISTS totals_model_version" in src
        assert "%(totals_model_version)s" in src

    def test_admin_freshness_resolves_the_totals_row_per_target(self):
        """Comparing the home_win-derived BUNDLE stamp against a per-target ledger row would report
        `ledger_behind` on totals forever — a permanent false 'watch' on a correctly recorded
        promotion (the E11.30 alarm-fatigue failure)."""
        import inspect

        from app.backend.routers import admin

        src = inspect.getsource(admin._live_served_versions)
        assert "totals_model_version" in src
        assert not hasattr(admin, "_live_served_version"), "old bundle-only helper must be gone"
        fresh = inspect.getsource(admin.model_freshness)
        assert "live_versions.get(target_key)" in fresh

    def test_the_totals_version_is_compared_verbatim_not_via_the_vN_regex(self):
        """`mh2_1` contains no `vN`. A regex-normalised comparison would silently read it as 'no
        live version' and fall back to the ledger, defeating the panel's whole purpose."""
        import re as _re

        assert _re.search(r"v(\d+)", "mh2_1") is None
        assert TOTALS["model_version"] == "mh2_1"

    def test_the_backtest_backfill_cannot_collide_with_the_previous_champion(self):
        """⚠️ The backfill's idempotency key is (game_pk, model_version, retrain_tag). `model_version`
        is the home_win BUNDLE stamp, which a totals-only swap does NOT move — so with `retrain_tag`
        hardcoded, an MH2.1 backtest matches the E13.11-era rows on BOTH key parts, skips every game
        as "already backfilled", writes NOTHING, and reports success. Parameterising the tag is what
        makes the run possible at all; it also LABELS the rows as this champion's backtest."""
        import inspect

        from betting_ml.scripts import backfill_predictions as b

        assert "retrain_tag" in inspect.signature(b._get_existing_game_pks).parameters
        assert "retrain_tag" in inspect.signature(b._build_rows).parameters
        assert "retrain_tag" in inspect.signature(b._write_rows).parameters
        src = (PROJECT_ROOT / "betting_ml/scripts/backfill_predictions.py").read_text()
        assert '"--retrain-tag", default=_RETRAIN_TAG' in src, "default preserves prior behaviour"
        assert "_get_existing_game_pks(model_version, args.retrain_tag)" in src

    def test_backfilled_rows_are_labelled_a_backtest_not_a_live_record(self):
        """E7.9 step 7: the historical rows are a BACKTEST. Three independent stamps say so —
        prediction_type, is_backfill, and the retrain_tag — so no single column read can mistake
        them for real-time predictions."""
        from betting_ml.scripts import backfill_predictions as b

        assert b._PREDICTION_TYPE == "backfill"
        src = (PROJECT_ROOT / "betting_ml/scripts/backfill_predictions.py").read_text()
        assert "is_backfill" in src and "BACKTEST, never a real-time record" in src

    def test_finalize_records_the_champion_lineage_row(self):
        """Without a lineage row the Admin panel keeps naming the RETIRED v6 as totals champion."""
        import inspect

        from betting_ml.scripts import finalize_mh2_1_champion as f

        src = inspect.getsource(f.main)
        assert "record_promotion(" in src
        assert 'new_version="mh2_1"' in src
        assert 'cv_metric_name="crps_margin_vs_incumbent"' in src, \
            "stamping the v6-era MAE would record a metric this promotion was never judged by"
