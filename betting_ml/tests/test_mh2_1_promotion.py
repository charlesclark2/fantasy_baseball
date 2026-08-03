"""Guards for the MH2.1 champion promotion — PROMOTED AND ROLLED BACK 2026-08-02.

Fast-gate safe: pure stdlib/numpy/sklearn, no Snowflake, no S3, no `pipeline` import.

🔴 READ FIRST — `total_runs` / `post_lineup` serves the **v6 NGBoost**, not the MH2.1 challenger.
The promotion was argued on conditional calibration; that evidence did not reproduce on the served
population and reversed in every window measurable, so it was reverted the same day. The defect was
an UNVALIDATED STRATIFIER — a conditional-calibration result is a property of its stratifier, and
one that does not demonstrably separate realized dispersion measures nothing. Full record:
`ablation_results/mh2_1_rollback.md`.

WHAT THIS PROTECTS
------------------
1. **The rollback is COMPLETE** — a half-reverted registry (v6 artifact, 25-col sidecar, or a
   dangling `serving_wrapper`/`sigma_served`) fails the serve-time width guard inside a HALT-tier
   op and costs the slate. `TestPromotionScope` pins every serving key together.
2. **The challenger is RETAINED, not deleted** — `HomoscedasticNormalRegressor`, the fit script,
   the 25-col sidecar and the artifact stay addressable under the registry's `mh2_1_*` keys so a
   re-promotion is a registry edit. The API-shape and contract guards therefore still point at the
   CHALLENGER on purpose: a retained artifact whose guards were deleted is how a rollback rots into
   unshippable dead code.
3. **Framing** — the CRPS margin decomposes into two sub-floor components, only 3 of 8 folds test
   the served contract, and the selection was on PRICING. Those claims survive the rollback and
   must stay on the record; if they rot out, a future re-promotion starts reading as an edge result.
4. **The kept improvements** — `daily_model_predictions.totals_model_version` (the bundle
   `model_version` is home_win-only, so a totals swap was invisible in served rows) and the three
   pre-existing `backfill_predictions.py` breaks this work fixed. Both are champion-independent.

`best_alpha = 0` throughout — no edge, win-rate, or ROI claim was made, and none is retracted.
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

# MH2.1 was promoted and ROLLED BACK the same day (its deciding conditional-calibration evidence
# was a stratifier artifact — see total_runs.mh2_1_promotion). So `feature_columns_path` is the v6
# NGBoost's sidecar again, and the CHALLENGER's contract lives under the retained `mh2_1_*` keys.
# The contract/serving-shape guards below still point at the challenger on purpose: the machinery
# is deliberately retained so a re-promotion is a registry edit, and a retained artifact whose
# guards were deleted is exactly how a rollback rots into unshippable dead code.
MH2_1_SERVED_SIDECAR = TOTALS["mh2_1_feature_columns_path"]


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
    """Guards the RETAINED MH2.1 challenger contract (rolled back, not deleted)."""

    def test_served_sidecar_is_the_contract_plus_the_two_imputer_indicators(self):
        contract = json.loads((PROJECT_ROOT / MH2_1_SERVED_SIDECAR.replace(
            "_served.json", ".json")).read_text())["feature_cols"]
        served = json.loads(
            (PROJECT_ROOT / MH2_1_SERVED_SIDECAR).read_text())["feature_cols"]
        assert set(served) - set(contract) == {"has_starter_platoon_data", "is_new_venue"}
        assert len(served) == len(contract) + 2

    def test_registry_feature_count_matches_the_sidecar(self):
        """The serve-time CONTRACT-GUARD compares the MODEL's width to the SIDECAR's length; if the
        registry's advertised `features` disagrees with the file, the record lies about what ships.
        Post-rollback the SERVED pair is v6/15; the challenger's own pair must still be coherent."""
        served_now = json.loads(
            (PROJECT_ROOT / TOTALS["feature_columns_path"]).read_text())["feature_cols"]
        assert int(TOTALS["features"]) == len(served_now) == 15, "served = the v6 NGBoost"
        challenger = json.loads(
            (PROJECT_ROOT / MH2_1_SERVED_SIDECAR).read_text())["feature_cols"]
        assert len(challenger) == 25, "the retained challenger contract must stay intact"

    def test_the_contract_carries_the_incumbent_base_plus_the_full_eb_block(self):
        from betting_ml.scripts.finalize_mh2_1_champion import PLUS_EB_COLS

        contract = json.loads((PROJECT_ROOT / MH2_1_SERVED_SIDECAR.replace(
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
    def test_post_lineup_is_ROLLED_BACK_to_the_v6_ngboost(self):
        """MH2.1's deciding evidence (conditional calibration) did not reproduce and reversed on the
        served population, so the swap was reverted. Every serving key must name the v6 NGBoost —
        a half-reverted registry (v6 artifact, 25-col sidecar) fails the serve-time width guard
        inside a HALT-tier op and costs the slate."""
        assert TOTALS["artifact_path"].endswith("ngboost_normal_deleaked_v6_post_lineup_2026.pkl")
        assert TOTALS["feature_columns_path"].endswith(
            "feature_columns_v6_total_runs_post_lineup_served.json")
        assert TOTALS["model_version"] == "v6"
        assert TOTALS["homoscedastic"] is False, "the v6 NGBoost's per-game sigma VARIES again"
        assert TOTALS["dist"] == "Normal", "p_over_line still reads this"
        # the challenger's own architecture keys must be GONE, not left dangling on a v6 artifact
        for orphan in ("serving_wrapper", "sigma_served", "model_class"):
            assert orphan not in TOTALS, (
                f"`{orphan}` is an MH2.1 key; left behind it would describe the wrong artifact"
            )

    def test_the_rolled_back_challenger_is_RETAINED_not_deleted(self):
        """A re-promotion must be a registry edit, not a re-fit. The artifact + contract stay
        addressable under mh2_1_* keys, and the fit script + wrapper stay on disk."""
        assert TOTALS["mh2_1_artifact_path"].endswith(
            "glm_elasticnet_plus_eb_mh2_1_post_lineup_2026.pkl")
        assert (PROJECT_ROOT / MH2_1_SERVED_SIDECAR).exists()
        assert (PROJECT_ROOT / "betting_ml/utils/homoscedastic_regressor.py").exists()
        assert (PROJECT_ROOT / "betting_ml/scripts/finalize_mh2_1_champion.py").exists()

    def test_pre_lineup_is_UNTOUCHED(self):
        """The story promoted post_lineup ONLY, so the rollback has nothing to undo here. The
        morning tier kept the v6 NGBoost throughout — MH2.1 never scored a pre_lineup arm."""
        assert TOTALS["pre_lineup"].endswith("ngboost_normal_deleaked_v6_pre_lineup_2026.pkl")
        assert TOTALS["pre_lineup_model_version"] == "v6"

    def test_the_other_two_targets_are_UNTOUCHED(self):
        assert REGISTRY["home_win"]["model_version"] == "v6"
        assert REGISTRY["run_differential"]["model_version"] == "v6"
        assert "ngboost_normal_deleaked_v6" in REGISTRY["run_differential"]["artifact_path"]

    def test_rollback_targets_the_model_actually_being_replaced(self):
        """`prev_artifact_path` is the rollback target for whatever is CURRENTLY served. With v6
        restored, that is the v5 seasonnorm again — leaving it pointing at v6 would make the
        rollback of a rollback a no-op that looks like it worked."""
        assert TOTALS["prev_artifact_path"].endswith("ngboost_tuned_seasonnorm_2026.pkl")
        assert TOTALS["prev_feature_columns_path"].endswith(
            "feature_columns_ngboost_tuned_seasonnorm_2026.json")
        assert TOTALS["prev_artifact_path"] != TOTALS["artifact_path"]

    def test_bets_stay_paused(self):
        """best_alpha=0 on both sides of this. Neither the promotion nor its reversal touches bets."""
        assert TOTALS["bet_paused"] is True
        assert REGISTRY["total_runs"]["mh2_1_promotion"]["best_alpha"] == 0


# ── 5. the E13.6b calibrator trigger actually fired ───────────────────────────────────────────

def test_the_totals_calibrator_refit_trigger_is_stood_down_with_the_rollback():
    """`total_runs_model_rebuild` is a pre-registered refit trigger on the E13.6b isotonic candidate.
    The promotion FIRED it (the candidate was fit on the then-retired v6's served P(over)); the
    rollback restores that same v6 as the served model, so the candidate's INPUT PREDICTIVE is
    unchanged and it is not stale. Leaving a stale flag set against a model that is serving again
    would hold a valid candidate forever for a reason that no longer exists."""
    cal = TOTALS["totals_serving_calibration"]
    fired = cal["refit_trigger_fired"]
    assert fired["trigger"] == "total_runs_model_rebuild", "the trigger stays armed"
    assert fired["status"].startswith("STOOD_DOWN")
    assert "STALE" not in fired["status"]
    assert fired["stood_down_at"] == fired["fired_at"], "fired and reverted the same day"
    assert cal["status"].startswith("CANDIDATE"), "it was never live, so nothing regressed either way"
    # premise: the candidate's input predictive is the model that is served again
    assert TOTALS["model_version"] == "v6"


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

    def test_the_sigma_collapse_is_undone_by_the_rollback(self):
        """The promotion made `pred_total_runs_scale` constant, which switched off the σ dimension of
        Story 22.4's totals gate. The rollback restores a VARYING σ, so that caveat must no longer
        be advertised as current — and `sigma_served` must be gone, not left describing an artifact
        that is not being served."""
        assert TOTALS["homoscedastic"] is False
        assert "sigma_served" not in TOTALS
        assert "sigma_is_constant" not in TOTALS["mh2_1_promotion"]["caveats"]

    def test_the_bullpen_v3_seam_is_disclosed(self):
        """The CHALLENGER trains on 2016+ while bullpen_v3 de-leak caches exist only for 2021+, so
        two contract columns span two measurement conventions. That seam belongs to the retained
        challenger and must stay on its record for a re-promotion; the SERVED v6 is 2021+ and does
        not carry it."""
        assert "bullpen_v3_seam" in TOTALS["mh2_1_promotion"]["caveats"]
        assert TOTALS["training_cutoff"] == "2021+", "served = v6's narrow window again"

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
        """A totals champion need not be `vN` — MH2.1's was `mh2_1`, which the `v(\\d+)` normaliser
        reads as 'no live version', silently falling back to the ledger and defeating the panel.
        The rollback restores a vN value, so the CURRENT registry no longer exercises this; the
        guard is on the CODE, which must stay verbatim for the next non-vN lineage."""
        import inspect
        import re as _re

        from app.backend.routers import admin

        assert _re.search(r"v(\d+)", "mh2_1") is None, "the shape that would break a regex compare"
        src = inspect.getsource(admin.model_freshness)
        assert "live_versions.get(target_key)" in src
        assert 'r"v(\\d+)"' not in src.split("live_versions.get(target_key)")[1][:400], (
            "the totals comparison must stay verbatim — a vN normaliser drops a non-vN lineage"
        )

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


# ── 8. the backfill's sidecar reader (a PRE-EXISTING break, surfaced by this promotion) ───────

class TestBackfillSidecarUnwrap:
    """⚠️ NOT an MH2.1 regression — `backfill_predictions.feat_cols` returned the parsed JSON
    unconditionally, so once sidecars gained `_provenance` (E13.11, 2026-06-23) it handed back the
    DICT. `len()` was 2 and `reindex(columns=<dict>)` built a matrix out of the KEY NAMES, so every
    target raised a feature-count error. It broke home_win and run_differential too — targets this
    promotion never touched — which is how we know it predates MH2.1. `predict_today._load_cols`
    has carried the unwrap all along; this script was simply left behind.
    """

    def test_both_sidecar_shapes_resolve_to_the_column_list(self, tmp_path, monkeypatch):
        import json as _json

        from betting_ml.scripts import backfill_predictions as b

        src = (PROJECT_ROOT / "betting_ml/scripts/backfill_predictions.py").read_text()
        assert 'raw["feature_cols"] if isinstance(raw, dict) else raw' in src, (
            "feat_cols must unwrap the modern {'feature_cols': [...], '_provenance': {...}} shape"
        )
        # the two shapes, resolved by the same expression the script uses — checked on BOTH the
        # served v6 sidecar and the retained MH2.1 one, since the unwrap is width-independent
        for path, expected_n in ((TOTALS["feature_columns_path"], 15),
                                 (MH2_1_SERVED_SIDECAR, 25)):
            modern = _json.loads((PROJECT_ROOT / path).read_text())
            legacy = modern["feature_cols"]
            for raw in (modern, legacy):
                cols = raw["feature_cols"] if isinstance(raw, dict) else raw
                assert len(cols) == expected_n
                assert "_provenance" not in cols, "the provenance KEY must never become a feature"
        assert b is not None

    def test_a_resolved_width_mismatch_fails_loudly_before_sklearn(self):
        """The original failure surfaced ~20 frames deep in sklearn's `_check_n_features` as
        'X has 2 features, but StandardScaler is expecting 21' — which names neither the sidecar nor
        the target. The script now checks the resolved width against the registry's advertised
        `features` and says which file drifted."""
        src = (PROJECT_ROOT / "betting_ml/scripts/backfill_predictions.py").read_text()
        assert "registry[_tgt].get(\"features\")" in src
        assert "the sidecar unwrap regressed" in src

    def test_the_imputer_indicators_are_not_silently_dropped(self):
        """`_AddIndicators` APPENDS has_starter_platoon_data + is_new_venue, both of which are in
        every served sidecar. Re-wrapping the transform as `pd.DataFrame(t, columns=numeric_cols)`
        SELECTS rather than renames, dropping them — and the later `fill_value=0.0` reindex then
        asserted 'no platoon data / not a new venue' for every game in the backfill. A wrong VALUE,
        not a crash: it would have scored a whole history quietly."""
        src = (PROJECT_ROOT / "betting_ml/scripts/backfill_predictions.py").read_text()
        assert "isinstance(_transformed, pd.DataFrame)" in src
        assert "_transformed.set_index(df.index)" in src
        assert "imputer indicator" in src, "an absent indicator must warn, not pass silently"

    def test_every_model_input_is_built_from_the_IMPUTED_frame(self):
        """⚠️ Class guard, not a line guard — this was the THIRD pre-existing break found in this
        script, all three dating to the E13.11 champion swap.

        `X_hw` was built from the RAW frame with `fill_value=np.nan`, under a comment claiming the
        classifier had its own internal imputer. The previous home_win champion was XGBoost, which
        consumes NaN natively; E13.11 swapped it for
        `PlattCalibratedLinearClassifier(Pipeline(StandardScaler, LogisticRegression))`, which
        rejects NaN outright. The raw-frame path was silently invalidated by that swap.

        Pinning "X_hw uses df_t" would only stop THIS line regressing. Asserting that NO model input
        is built from the raw frame stops the whole class — including a fourth target added later.
        `predict_today` builds all three from its imputed matrix; that is the reference.
        """
        src = (PROJECT_ROOT / "betting_ml/scripts/backfill_predictions.py").read_text()
        import re as _re

        inputs = _re.findall(r"^\s*(X_\w+)\s*=\s*(df_t|df)\.reindex", src, _re.M)
        assert inputs, "expected to find the model-input construction lines"
        raw = [name for name, frame in inputs if frame == "df"]
        assert not raw, (
            f"model input(s) {raw} are built from the RAW frame. Every served estimator now expects "
            f"the imputed matrix — build from df_t, as predict_today does."
        )
        assert {"X_hw", "X_tot", "X_diff"} <= {n for n, _ in inputs}, \
            "all three target inputs must be present and covered by this guard"

    def test_a_surviving_nan_fails_with_the_offending_column_named(self):
        src = (PROJECT_ROOT / "betting_ml/scripts/backfill_predictions.py").read_text()
        assert "np.isfinite(X_hw).all()" in src
        assert "naming neither the column nor the target" in src


# ── 9. the two follow-up hardenings (silent no-op; apples-to-apples baseline) ──────────────────

class TestBackfillNoOpGuard:
    """A 100%-skip run used to print 'Nothing to backfill.' and exit 0 — indistinguishable from
    success. That is the exact shape of this script's most likely failure: reusing a `retrain_tag`
    after a PER-TARGET promotion, where `model_version` (home_win-derived) does not move either, so
    both halves of the idempotency key match the previous champion's rows."""

    def test_a_total_noop_raises_instead_of_exiting_zero(self):
        src = (PROJECT_ROOT / "betting_ml/scripts/backfill_predictions.py").read_text()
        assert "if df.empty and not args.allow_noop:" in src
        assert "EVERY game was skipped as already-present" in src
        assert "raise SystemExit(" in src

    def test_the_error_names_the_LIKELY_CAUSE_not_just_the_symptom(self):
        """'nothing to write' is the symptom; the actionable content is WHY — the bundle stamp not
        moving on a per-target promotion — and the fix (a distinct --retrain-tag)."""
        src = (PROJECT_ROOT / "betting_ml/scripts/backfill_predictions.py").read_text()
        assert "derived from home_win ALONE" in src
        assert "DISTINCT --retrain-tag" in src

    def test_a_deliberate_rerun_has_an_escape_hatch(self):
        """State cannot separate 'deliberate re-run' from 'silent no-op', so the default fails and
        the operator declares intent. The asymmetry is deliberate: a needless --allow-noop costs one
        retry; a silent no-op costs a whole believed-complete backfill."""
        src = (PROJECT_ROOT / "betting_ml/scripts/backfill_predictions.py").read_text()
        assert '"--allow-noop", action="store_true"' in src

    def test_exiting_nonzero_is_safe_because_nothing_automated_calls_this(self):
        """A non-zero exit would be a regression if a Dagster op/cron ran this. Verified it does not
        — this assertion re-checks that premise rather than trusting the original grep."""
        import subprocess

        hits = subprocess.run(
            ["grep", "-rIl", "backfill_predictions.py", "pipeline", "services", ".github"],
            cwd=PROJECT_ROOT, capture_output=True, text=True,
        ).stdout.split()
        assert not hits, (
            f"backfill_predictions.py is now invoked by {hits} — a non-zero exit on no-op may "
            f"break an automated caller. Re-evaluate the guard's default."
        )


class TestPreviousChampionBaseline:
    """Every row written before 2026-08-02 carries the dropped-imputer-indicator defect (present
    since the script's first commit, 2026-05-12). So the pre-existing rows for a previous champion
    are NOT a valid baseline for a new one — a new-vs-old comparison would confound the champion
    swap with an input fix. `--totals-artifact prev` re-scores the previous champion on fixed code."""

    def test_prev_scores_the_replaced_artifact_and_contract_together(self):
        """⚠️ This assertion was VACUOUS in its first form. It matched the bare string
        `"prev_feature_columns_path"`, which also appears in the `--totals-artifact` help text and
        in the missing-key check — so it passed with the contract resolution reverted to always use
        the prod path (verified: the deliberate break stayed GREEN). A source-inspection guard that
        prose can satisfy is not a guard (the INC-38 lesson). It now matches the RESOLUTION
        EXPRESSION itself, and was re-verified to go RED on that same break.
        """
        src = (PROJECT_ROOT / "betting_ml/scripts/backfill_predictions.py").read_text()
        assert '"--totals-artifact", choices=["prod", "prev"]' in src
        assert '"prev_artifact_path" if _tot_is_prev else "prod"' in src
        # the contract must be selected by the SAME condition as the artifact
        assert 'if (target == "total_runs" and _tot_is_prev) else "feature_columns_path"' in src, (
            "the PREV contract must travel with the PREV artifact — a prod contract (25 cols) "
            "against the prev model (15) either raises or, worse, silently scores misaligned columns"
        )

    def test_only_total_runs_varies(self):
        """home_win and run_differential are unchanged by a totals-only promotion. Varying them too
        would add a second difference and destroy the contrast the flag exists to create."""
        src = (PROJECT_ROOT / "betting_ml/scripts/backfill_predictions.py").read_text()
        assert 'load_model("home_win", "prod")' in src
        assert 'load_model("run_differential", "prod")' in src

    def test_the_row_is_stamped_with_the_model_that_actually_scored_it(self):
        src = (PROJECT_ROOT / "betting_ml/scripts/backfill_predictions.py").read_text()
        assert "totals_model_version = str(" in src and "prev_model_version" in src

    def test_an_absent_previous_champion_fails_rather_than_falling_back_to_prod(self):
        """A silent fallback to the CURRENT champion would produce a 'baseline' identical to the
        thing being compared — the comparison would read as 'no change' and be entirely fictional."""
        src = (PROJECT_ROOT / "betting_ml/scripts/backfill_predictions.py").read_text()
        assert "requires" in src and "There is no recorded previous champion to score." in src

    def test_the_version_label_is_provisional_when_it_cannot_be_known(self):
        from betting_ml.scripts.backfill_predictions import _infer_prev_version

        assert _infer_prev_version(
            "s3://b/total_runs/ngboost_normal_deleaked_v6_post_lineup_2026.pkl") == "v6"
        # no vN token → must be OBVIOUSLY approximate, never a clean guess that could collide
        # with a real champion label in a group-by
        odd = _infer_prev_version("s3://b/total_runs/some_legacy_artifact.pkl")
        assert odd.startswith("prev:")

    def test_the_registry_width_check_is_skipped_for_the_prev_artifact(self):
        """`features` in the registry names the CURRENT champion (25 for MH2.1). Checking the prev
        contract (15) against it would false-fail every prev run."""
        src = (PROJECT_ROOT / "betting_ml/scripts/backfill_predictions.py").read_text()
        assert '_advertised = (None if (_tgt == "total_runs" and _tot_is_prev)' in src
