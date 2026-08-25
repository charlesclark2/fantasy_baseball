"""test_nf_inj3b_ship_covariate_feed.py — NF-INJ3b-SHIP node 1 (PM ruling D7: THE COVARIATE FEED).

The certified hurdle is a GLM over `onset_carryover, weeks_since_last_game, prior_games,
log1p_prior_fp, is_qb`, and until this story **three of those existed nowhere in the board build**.
So a flip was impossible: `served_injury_games` refuses (loudly) rather than serving the incumbent
under the fitted arm's stamp. These guards pin the three things that make the feed real:

  1. there is exactly ONE definition of each covariate in the repo — the one the arm was FITTED on
     (`nf_inj3_injury_games.derive_covariates`, extracted verbatim from `build_population`) — and
     the served feed calls it rather than re-deriving (NF-C0e);
  2. the definitions REPRODUCE the study's own values at 1e-9, measured against the committed
     NF-INJ3b artifact rather than asserted from a docstring;
  3. the feed is LEAKAGE-GATED off the served artifact's own `train_seasons`, so the NF1.9 band
     panel and every NF3.2 track-record backtest board keep the incumbent caps.

⭐ (3) is not a nicety. `build_veteran_panel_season` builds target seasons 2019…2025 through the
same function, every one INSIDE the artifact's training window. Feeding those boards would score a
past board with a model that had already read its outcomes.
"""
from __future__ import annotations

import ast
import inspect
import json
import textwrap
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quant_sports_intel_models.football.nfl.fantasy import injury_covariate_feed as FEED
from quant_sports_intel_models.football.nfl.fantasy import injury_games_policy as POLICY
from quant_sports_intel_models.football.nfl.fantasy import injury_games_serving as SERVE
from quant_sports_intel_models.football.nfl.fantasy import nf_inj3_injury_games as IG
from quant_sports_intel_models.football.nfl.fantasy import run_season_projection as RSP

PIN_TOL = 1e-9
_ART = Path(SERVE.ARTIFACT_PATH)
_RSP_SRC = Path(RSP.__file__).read_text()


def _code_only(src: str) -> str:
    """Source with comments + docstrings stripped — prose must neither satisfy nor break a clause
    (INC-38)."""
    tree = ast.parse(textwrap.dedent(src))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if (node.body and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)):
                node.body[0].value.value = ""
    return ast.unparse(tree)


def _prior_frame() -> pd.DataFrame:
    """A frame shaped exactly like `load_prior_features` output joined to the board's `position`."""
    return pd.DataFrame({
        "player_id": ["a", "b", "c", "d"],
        "position": ["QB", "RB", "WR", "qb"],
        "prior_games": [17.0, 3.0, np.nan, 9.0],
        "prior_fp": [310.5, 12.0, np.nan, -4.0],
        "last_week_played": [18.0, 3.0, np.nan, 11.0],
        "prior_season_weeks": [18.0, 18.0, 18.0, 18.0],
        "prior_end_status": ["ACT", "RES", None, "PUP"],
    })


# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestThereIsExactlyOneDefinition:
    def test_the_served_feed_calls_the_bake_offs_own_derivation(self):
        """⛔ The feed must not re-derive. An arm fitted on one definition and served on another is
        not the arm that was certified (NF-C0e)."""
        code = _code_only(inspect.getsource(FEED.build_feed))
        assert "IG.derive_covariates(" in code, (
            "injury_covariate_feed no longer routes through the study's own derivation")

    def test_the_feed_does_not_write_its_own_sql_either(self):
        """The prior-season columns come from the study runner's SQL, for the same reason."""
        code = _code_only(inspect.getsource(FEED.build_feed))
        assert "R3.load_prior_features(" in code
        assert "select" not in code.lower(), (
            "the feed embeds SQL of its own — the study's query is the one owner")

    def test_the_feed_emits_exactly_the_columns_the_served_hurdle_consumes(self):
        assert set(FEED.FEED_COLUMNS) == {"player_id", *SERVE.REQUIRED_COVARIATES}

    def test_a_frame_missing_an_input_RAISES_rather_than_emitting_NaN_columns(self):
        """A silently-NaN covariate NaNs a real player out of the design matrix (NF1.7 (a))."""
        with pytest.raises(ValueError, match="missing"):
            IG.derive_covariates(_prior_frame().drop(columns=["prior_end_status"]))


class TestTheDefinitionsThemselves:
    def test_log1p_prior_fp_clips_a_NEGATIVE_ppr_season_rather_than_NaN_ing_the_player(self):
        """PPR goes negative (a QB with interceptions and no yardage) and `log1p(x < -1)` is NaN."""
        out = IG.derive_covariates(_prior_frame())
        assert out.loc[3, "log1p_prior_fp"] == 0.0
        assert np.isfinite(out["log1p_prior_fp"]).all()

    def test_a_player_with_no_prior_season_row_takes_the_LONGEST_absence(self):
        out = IG.derive_covariates(_prior_frame())
        assert out.loc[2, "weeks_since_last_game"] == 18.0
        assert out.loc[2, "prior_games"] == 0.0

    def test_onset_carryover_reads_the_DECLARED_status_set_and_is_null_safe(self):
        out = IG.derive_covariates(_prior_frame())
        assert list(out["onset_carryover"]) == [0.0, 1.0, 0.0, 1.0]
        assert set(IG.ONSET_CARRYOVER_STATUSES) == {"RES", "PUP", "NFI", "SUS", "INA"}

    def test_is_qb_is_case_insensitive(self):
        out = IG.derive_covariates(_prior_frame())
        assert list(out["is_qb"]) == [1.0, 0.0, 0.0, 1.0]

    def test_the_weeks_sentinel_is_invariant_to_which_SUBSET_of_a_season_is_passed(self):
        """⭐ THE PROPERTY THAT MAKES ONE OWNER POSSIBLE. `build_population` derives over the FLAGGED
        VETERANS of one season; the served feed derives over the WHOLE BOARD. They agree only
        because `weeks.max()` reads `prior_season_weeks`, which the study's SQL emits as a per-SEASON
        constant. If that ever became per-player, the two callers would silently diverge."""
        full = _prior_frame()
        sub = full.iloc[[1, 2]].copy()
        a = IG.derive_covariates(full).set_index("player_id")["weeks_since_last_game"]
        b = IG.derive_covariates(sub).set_index("player_id")["weeks_since_last_game"]
        for pid in ("b", "c"):
            assert abs(float(a[pid]) - float(b[pid])) < PIN_TOL


class TestTheLeakageGate:
    def test_the_bound_is_READ_OFF_THE_ARTIFACT_not_declared_here(self):
        art = json.loads(_ART.read_text())
        assert FEED.leakage_bound(art) == int(art["train_seasons"][1])
        code = _code_only(inspect.getsource(FEED.leakage_bound))
        assert "2025" not in code and "2026" not in code, (
            "a hardcoded season goes stale the first time the hurdle is re-fitted on a wider "
            "window, and it goes stale in the UNSAFE direction")

    def test_a_missing_train_window_RAISES_rather_than_defaulting(self):
        with pytest.raises(ValueError, match="train_seasons"):
            FEED.leakage_bound({"train_seasons": None})

    @pytest.mark.parametrize("season", [2019, 2022, 2025])
    def test_every_season_inside_the_training_window_is_REFUSED(self, season):
        """⭐ These are exactly the NF1.9 band-panel target seasons and the NF3.2 track-record
        backtest boards. A feed here would score a past board with a model that read its future."""
        art = json.loads(_ART.read_text())
        ok, why = FEED.season_is_admissible(art, season)
        assert ok is False and "REFUSED" in why

    @pytest.mark.parametrize("season", [2026, 2027])
    def test_a_season_after_the_training_window_is_admitted(self, season):
        art = json.loads(_ART.read_text())
        ok, _ = FEED.season_is_admissible(art, season)
        assert ok is True

    def test_the_boundary_season_ITSELF_is_refused_not_admitted(self):
        """Equality is the leak, not a boundary case: a 2025 board built from a model that saw
        2025's outcomes has read its own answers."""
        art = json.loads(_ART.read_text())
        assert FEED.season_is_admissible(art, int(art["train_seasons"][1]))[0] is False

    def test_with_the_policy_OFF_no_feed_is_built_at_all(self, monkeypatch):
        """The rollback state must not pay for a warehouse read it will not use."""
        monkeypatch.setattr(POLICY, "SERVING_ENABLED", False)
        feed, prov = FEED.feed_for_board(object(), pd.DataFrame(), 2026)
        assert feed is None and prov["supplied"] is False
        assert "SERVING_ENABLED" in prov["reason"]

    def test_a_refusal_is_RECORDED_never_silent(self, monkeypatch):
        monkeypatch.setattr(POLICY, "SERVING_ENABLED", True)
        feed, prov = FEED.feed_for_board(object(), pd.DataFrame(), 2020)
        assert feed is None
        assert prov["supplied"] is False and "REFUSED" in prov["reason"]
        assert prov["train_seasons"] == list(json.loads(_ART.read_text())["train_seasons"])


class TestTheFeedIsWiredIntoTheBoardBUILD:
    def test_the_board_build_builds_the_feed_itself(self):
        """⭐ WIRED **AND INVOKED** (NF-C0e). The feed used to ride on a `--injury-covariates`
        parquet one CLI happened to pass; `run_nf1_5.refined_board` — which builds the board that
        actually publishes — never passed it. It is built where `base` exists, so every caller of
        `build_veteran_projection` gets it."""
        code = _code_only(inspect.getsource(RSP.build_veteran_projection))
        assert "_IGF.feed_for_board(" in code, (
            "the board build no longer builds its own injury covariate feed — a flip would serve "
            "the incumbent under the fitted arm's stamp")

    def test_an_explicitly_supplied_feed_still_wins(self):
        """The NF-INJ3b-M counterfactual supplies its own; auto-building over it would silently
        change what that measurement measured."""
        code = _code_only(inspect.getsource(RSP.build_veteran_projection))
        assert "if injury_covariates is None:" in code

    def test_the_feed_is_built_BEFORE_the_frame_that_consumes_it(self):
        """INC-25, in one function: a feed built after `project_veterans` is called cannot reach the
        availability chain at all."""
        code = _code_only(inspect.getsource(RSP.build_veteran_projection))
        assert code.index("_IGF.feed_for_board(") < code.index("project_veterans("), (
            "the covariate feed must be built before the veteran projection consumes it")

    def test_project_veterans_declares_the_feed_to_the_serving_module(self):
        """`feed_supplied` is what separates 'this call site is not the served board' (NF1.5's
        internal research frame — RECORDED incumbent) from 'the fitted arm is intended' (covariates
        REQUIRED). It must be derived from the feed, never hardcoded."""
        from quant_sports_intel_models.football.nfl.fantasy import season_projection as SP
        code = _code_only(inspect.getsource(SP.project_veterans)).replace(" ", "")
        assert "feed_supplied=injury_covariatesisnotNone" in code


class TestTheSERVEDValuesReproduceTheSTUDY:
    def test_the_serving_path_reproduces_the_studys_own_predictions_at_1e_9(self):
        """⭐ THE PIN. Covariates derived through the SERVED feed's owner, pushed through the
        PERSISTED artifact, must equal the bake-off's own `predict_hurdle` on the same rows to 1e-9
        — measured, never asserted from a docstring. A drift in either half (the derivation or the
        coefficients) breaks this and nothing else would."""
        art = json.loads(_ART.read_text())
        frame = IG.derive_covariates(_prior_frame())
        # `_design` emits the status dummies, so the frame needs a status column; the covariates
        # under test are the other five.
        frame["proj_status"] = ["RES", "PUP", "RES", "PUP"]
        served = SERVE.predict_games(art, frame)
        want = IG.predict_hurdle(
            {"b_play": np.asarray(art["b_play"], dtype=float),
             "b_cond": np.asarray(art["b_cond"], dtype=float),
             "cond_pooled": float(art["cond_pooled"]),
             "features": IG.TIMING_FEATURES + IG.BASE_FEATURES},
            frame, int(art["n_games"]))
        assert np.allclose(served, want, rtol=0, atol=PIN_TOL)

    def test_the_committed_artifacts_recorded_covariates_are_the_ones_the_feed_emits(self):
        """A feed emitting a DIFFERENT column set from the one the artifact was fitted over would
        be caught by `load_artifact`'s contract check — this pins the other direction, that the feed
        supplies every column that contract demands."""
        art = json.loads(_ART.read_text())
        for c in SERVE.REQUIRED_COVARIATES:
            assert c in art["columns"]
            assert c in FEED.FEED_COLUMNS
