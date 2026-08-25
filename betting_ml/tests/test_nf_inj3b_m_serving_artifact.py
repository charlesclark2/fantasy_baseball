"""test_nf_inj3b_m_serving_artifact.py — NF-INJ3b-M node 2 (PM ruling D2 = A).

NF-INJ3b's certified winner is a FITTED GLM hurdle, not four constants, so "ship the caps" means
shipping a fitted object. MH2.1: **serve the object that was validated, never a re-derivation.**
These guards pin the three things that makes true:

  1. the persisted coefficients REPRODUCE the bake-off's own arm (pin 1e-9, never `round(...,6)`);
  2. nothing on the serving path FITS — a re-fit is the failure MH2.1 names;
  3. the PM BOUNDARY holds: only RES/PUP get the fitted arm; SUS/NFI keep the incumbent constants.

Plus the loader fails LOUD on every malformed input (NF1.7 (a): a serving loader that degrades to a
default is how a board silently serves something nobody validated), and the flip stays DEPLOY-HELD.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quant_sports_intel_models.football.nfl.fantasy import injury_games_policy as POLICY
from quant_sports_intel_models.football.nfl.fantasy import injury_games_serving as SERVE
from quant_sports_intel_models.football.nfl.fantasy import nf_inj3_injury_games as IG

PIN_TOL = 1e-9
_SERVE_SRC = Path(SERVE.__file__).read_text()


def _frame(n_rows: int = 60, seed: int = 7) -> pd.DataFrame:
    """A board-shaped frame carrying every design covariate and a mix of all four statuses."""
    rng = np.random.default_rng(seed)
    st = np.array((["RES"] * 5 + ["PUP"] * 3 + ["SUS"] * 2)
                  * (n_rows // 10 + 1), dtype=object)[:n_rows]
    return pd.DataFrame({
        "proj_status": st,
        "onset_carryover": rng.integers(0, 2, n_rows).astype(float),
        "weeks_since_last_game": rng.integers(1, 18, n_rows).astype(float),
        "prior_games": rng.integers(0, 18, n_rows).astype(float),
        "log1p_prior_fp": rng.uniform(0, 6, n_rows),
        "is_qb": (rng.random(n_rows) < 0.15).astype(float),
        "realized_games": rng.integers(0, 18, n_rows).astype(float),
        "eg": rng.uniform(0, 17, n_rows),
        "proj_games": rng.uniform(0, 17, n_rows),
    })


def _artifact_from_fit(fit: dict, n: int) -> dict:
    return {"model_version": POLICY.MODEL_VERSION, "contract_version": SERVE.CONTRACT_VERSION,
            "arm": POLICY.ARM, "columns": list(SERVE.design_columns()), "n_games": int(n),
            "b_play": [float(x) for x in fit["b_play"]],
            "b_cond": ([float(x) for x in fit["b_cond"]] if fit["b_cond"] is not None else None),
            "cond_pooled": float(fit["cond_pooled"]),
            "train_seasons": [2016, 2025], "n_train_rows": 418, "fit_at": "2026-08-23T00:00:00Z"}


# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestTheServedObjectISTheValidatedObject:
    def test_the_persisted_coefficients_reproduce_the_bake_offs_own_arm_at_1e_9(self):
        """⭐ THE LOAD-BEARING GUARD. Serving reads a coefficient table; the bake-off scored a fitted
        object. If those two ever disagree, everything NF-INJ3b certified is about a different
        model."""
        n = IG.season_game_count(2026)
        train, ev = _frame(120, seed=1), _frame(40, seed=2)
        fit = IG.fit_hurdle(train, n)
        validated = IG.predict_hurdle(fit, ev, n)
        served = SERVE.predict_games(_artifact_from_fit(fit, n), ev)
        assert len(validated) == len(ev) > 0, "empty comparison — this guard would pass on NOTHING"
        assert float(np.max(np.abs(served - validated))) < PIN_TOL

    def test_the_committed_artifact_records_its_own_reproduction_at_1e_9(self):
        """The artifact SHIPPED with a verification file; a serving object whose provenance is a
        claim rather than a measurement is not provenance."""
        v = SERVE.ARTIFACT_DIR / "nfl_fantasy_injury_games_hurdle_v1.verification.json"
        assert v.exists(), "no verification record beside the committed artifact"
        rec = json.loads(v.read_text())
        assert rec["n_serving_rows"] > 0, "verified on ZERO rows — vacuous"
        assert rec["tolerance"] == PIN_TOL
        assert rec["max_abs_difference_vs_validated_arm"] < PIN_TOL
        assert rec["reproduces_validated_arm"] is True

    def test_nothing_on_the_serving_path_FITS(self):
        """⛔ MH2.1's actual failure mode: a serving path that re-derives the object. An AST check,
        not a grep — the module DISCUSSES fitting at length in its docstring (INC-38)."""
        tree = ast.parse(_SERVE_SRC)
        called = {ast.unparse(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
        assert called, "no calls found — this guard would pass on NOTHING"
        banned = [c for c in called
                  if any(t in c for t in ("fit_hurdle", "fit_glm_mean", "fit_status_levels",
                                          "fit_blend", "fit_shared_phi", "minimize"))]
        assert not banned, f"the serving path FITS: {banned}"

    def test_the_design_contract_is_DERIVED_from_the_bake_off_module(self):
        """A restated column list is a second source of truth that can drift silently."""
        assert SERVE.design_columns()[4:] == IG.TIMING_FEATURES + IG.BASE_FEATURES
        assert SERVE.design_columns()[:4] == ("intercept", "is_PUP", "is_NFI", "is_SUS")


class TestTheLoaderFailsLoud:
    """NF1.7 (a) — a serving loader must never degrade to a default."""

    def test_a_missing_artifact_RAISES_rather_than_falling_back(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            SERVE.load_artifact(tmp_path / "absent.json")

    @pytest.mark.parametrize("mutate,exc", [
        (lambda a: a.__setitem__("columns", list(reversed(a["columns"]))), ValueError),
        (lambda a: a.__setitem__("contract_version", 999), ValueError),
        (lambda a: a.__setitem__("model_version", "something_else"), ValueError),
        (lambda a: a.__setitem__("arm", "fitted_status"), ValueError),
        (lambda a: a.__setitem__("b_play", [0.0]), ValueError),
        (lambda a: a.pop("cond_pooled"), ValueError),
    ], ids=["reordered-design", "contract-version", "model-version", "wrong-arm",
            "short-b_play", "missing-key"])
    def test_a_malformed_artifact_RAISES(self, tmp_path, mutate, exc):
        a = json.loads(SERVE.ARTIFACT_PATH.read_text())
        mutate(a)
        p = tmp_path / "bad.json"
        p.write_text(json.dumps(a))
        with pytest.raises(exc):
            SERVE.load_artifact(p)

    def test_the_committed_artifact_LOADS(self):
        a = SERVE.load_artifact()
        assert a["arm"] == POLICY.ARM
        assert a["model_version"] == POLICY.MODEL_VERSION


class TestThePMBoundary:
    """⭐ PM ruling D2, verbatim: the certified population is RES/PUP; SUS and NFI RETAIN the
    incumbent constants until a live row exists and a registered read covers them."""

    def test_res_and_pup_are_certified_sus_and_nfi_are_not(self):
        assert set(POLICY.CERTIFIED_STATUSES) == {"RES", "PUP"}
        assert set(POLICY.INCUMBENT_STATUSES) == {"SUS", "NFI"}
        assert not set(POLICY.CERTIFIED_STATUSES) & set(POLICY.INCUMBENT_STATUSES)

    def test_with_serving_ON_only_the_certified_statuses_move(self, monkeypatch):
        monkeypatch.setattr(POLICY, "SERVING_ENABLED", True)
        ev = _frame(60, seed=3)
        a = SERVE.load_artifact()
        got, prov = SERVE.served_injury_games(ev, artifact=a)
        inc = IG.incumbent_games(ev["proj_status"], ev["proj_games"].to_numpy())

        cert = ev["proj_status"].isin(POLICY.CERTIFIED_STATUSES).to_numpy()
        assert cert.any() and (~cert).any(), "fixture lacks BOTH classes — vacuous"
        # the non-certified rows are byte-identical to the incumbent …
        assert np.array_equal(got[~cert], inc[~cert])
        # … and the certified rows actually MOVED (else the boundary test proves nothing)
        assert float(np.max(np.abs(got[cert] - inc[cert]))) > 1e-6
        assert prov["path"] == "fitted_hurdle"
        assert prov["n_incumbent"] == int((~cert).sum())

    def test_with_serving_OFF_the_board_is_the_incumbent_byte_for_byte(self, monkeypatch):
        """⭐ RE-ANCHORED by NF-INJ3b-SHIP: the ambient-flag assertion described the deploy-held
        world and would now fail on the recorded D5=A flip for a reason unrelated to the property.
        The property — serving OFF is the incumbent path byte-for-byte, i.e. the rollback — is
        driven explicitly instead, which makes it hold in either flag state."""
        monkeypatch.setattr(POLICY, "SERVING_ENABLED", False)
        ev = _frame(40, seed=4)
        got, prov = SERVE.served_injury_games(ev)
        inc = IG.incumbent_games(ev["proj_status"], ev["proj_games"].to_numpy())
        assert np.array_equal(got, inc)
        assert prov["path"] == "incumbent"
        assert prov["model_version"] == POLICY.INCUMBENT_MODEL_VERSION


class TestThePolicyRefusesAnIncoherentFlip:
    def test_the_refused_arm_is_recorded_so_it_cannot_be_resurrected(self):
        assert "fitted_status" in POLICY.REFUSED_ARMS
        why = POLICY.REFUSED_ARMS["fitted_status"]
        assert "4 of 7" in why and "0.1265" in why

    def test_serving_a_REFUSED_arm_is_refused_at_import(self, monkeypatch):
        monkeypatch.setattr(POLICY, "ARM", "fitted_status")
        with pytest.raises(RuntimeError, match="REFUSED_ARMS"):
            POLICY.assert_coherent()

    def test_a_flip_contradicting_the_recorded_disposition_is_refused(self, monkeypatch):
        monkeypatch.setattr(POLICY, "SERVING_ENABLED", True)
        monkeypatch.setattr(POLICY, "DISPOSITION", "POWER_LIMITED")
        with pytest.raises(RuntimeError, match="disposition"):
            POLICY.assert_coherent()

    def test_the_stamp_carries_a_model_version_in_BOTH_states(self, monkeypatch):
        """BOTH states, driven explicitly — the name always promised two and the body only ever
        exercised whichever one the ambient flag happened to be in (NF-INJ3b-SHIP)."""
        monkeypatch.setattr(POLICY, "SERVING_ENABLED", False)
        off = POLICY.stamp()
        assert off["injury_games_model_version"] == POLICY.INCUMBENT_MODEL_VERSION
        assert off["injury_games_status"] == "incumbent"
        monkeypatch.setattr(POLICY, "SERVING_ENABLED", True)
        on = POLICY.stamp()
        assert on["injury_games_model_version"] == POLICY.MODEL_VERSION
        assert on["injury_games_status"] == "fitted_hurdle"


class TestTheArtifactIsCommittedNotGitignored:
    def test_the_artifact_lives_outside_the_gitignored_artifacts_tree(self):
        """⛔ NF-INFRA1: a serving artifact under a gitignored path is deploy-ephemeral — absent
        from the image, wiped by a deploy, and its reader then fails or silently degrades."""
        assert SERVE.ARTIFACT_PATH.exists()
        assert "served_artifacts" in str(SERVE.ARTIFACT_PATH)
        assert SERVE.ARTIFACT_DIR.name != "artifacts"
