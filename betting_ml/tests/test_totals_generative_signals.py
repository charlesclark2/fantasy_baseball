"""Tests for E2.5 — generate_totals_generative_signals.py.

Covers the scoring contract (serve-time matrix parity, per-side calibrated dispersion, OOS tagging)
and — the AC — the LEAKAGE-SAFE walk-forward backfill invariant: no season is scored in-sample.

The backfill test runs a genuine end-to-end walk-forward over a synthetic multi-season frame (a
minimal feature set → tiny LightGBM fits, fast), so it exercises the real PurgedWalkForwardSplit +
per-fold as-of fit path, not a mock. All IO (Snowflake/S3) is avoided; the champion artifact is the
committed local pkl.
"""
from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest

import betting_ml.scripts.totals_generative.generate_totals_generative_signals as g
from betting_ml.utils.market_blind import find_market_columns

_ARTIFACT = Path(g._ARTIFACT_LOCAL)
_R_HOME, _R_AWAY = 4.0645, 3.3977

pytestmark = pytest.mark.skipif(
    not _ARTIFACT.exists(),
    reason="totals_perside_v1.pkl not present locally (operator produces it via train_perside_negbin.py)",
)


@pytest.fixture(scope="module")
def artifact() -> dict:
    return joblib.load(str(_ARTIFACT))


def _perside_frame(years) -> pd.DataFrame:
    rows = []
    for i, yr in enumerate(years):
        for side in ("home", "away"):
            rows.append({"game_pk": f"{yr}{i:03d}", "side": side,
                         "game_date": f"{yr}-05-0{(i % 8) + 1}", "game_year": yr})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Scoring contract
# ---------------------------------------------------------------------------

def test_prepare_score_matrix_width_matches_artifact(artifact):
    df = _perside_frame([2025, 2026])
    X = g._prepare_score_matrix(df, artifact)
    assert X.shape == (len(df), len(artifact["feature_names"]))
    assert np.isfinite(X).all()  # every missing feature imputed to a finite train mean / 0-OHE


def test_compute_signals_perside_dispersion_and_columns(artifact):
    df = _perside_frame([2026, 2026])
    mu = np.array([4.5, 3.9, 5.1, 4.2])
    out = g.compute_signals(df, mu, _R_HOME, _R_AWAY, is_oos=True, train_through=2025)
    # per-side r: home rows get r_home, away rows r_away
    for _, row in out.iterrows():
        expected = _R_HOME if row["side"] == "home" else _R_AWAY
        assert row["totals_perside_dispersion"] == pytest.approx(expected)
    assert (out["uncertainty"] > 0).all()
    assert (out["totals_perside_raw"] == out["totals_perside_mu"]).all()  # raw is the mu alias
    for col in ("totals_perside_mu", "totals_perside_dispersion", "totals_perside_raw",
                "uncertainty", "is_oos", "train_through_season"):
        assert col in out.columns


def test_min_mu_floor_is_applied(artifact):
    df = _perside_frame([2026])
    out = g.compute_signals(df, np.array([-1.0, 0.0]), _R_HOME, _R_AWAY, is_oos=True, train_through=2025)
    assert (out["totals_perside_mu"] >= g._MIN_MU).all()


def test_score_with_champion_oos_flag(artifact):
    # champion trained through _CHAMPION_TRAIN_THROUGH (2025): 2025 = in-sample, 2026 = OOS.
    df = _perside_frame([2025, 2026])
    out = g.score_with_champion(df, artifact, _R_HOME, _R_AWAY)
    by_year = out.groupby("game_year")["is_oos"].first()
    assert by_year.loc[2025] == False  # noqa: E712 — in-sample
    assert by_year.loc[2026] == True   # noqa: E712 — OOS (champion never saw the partial season)
    assert (out["train_through_season"] == g._CHAMPION_TRAIN_THROUGH).all()


def test_served_dispersion_is_e23_heldout_not_artifact_trainfit(artifact, monkeypatch):
    # The whole point: we serve the E2.3 calibrated held-out per-side r, NOT the artifact's train-fit
    # negbin_r (7.449, under-dispersed). Guard against a regression that reads the artifact r.
    # Force the committed local JSON (the S3 copy is promoted by the operator at deploy).
    monkeypatch.setattr(g, "_artifacts_from_s3", lambda: False)
    assert artifact["negbin_r"] > 6.0  # the known under-dispersed train-fit value
    r_home, r_away = g._load_dispersion()
    assert r_home == pytest.approx(4.0645, abs=1e-3)
    assert r_away == pytest.approx(3.3977, abs=1e-3)
    assert r_home < artifact["negbin_r"] and r_away < artifact["negbin_r"]


def test_write_signals_dry_run_row_shape(artifact):
    df = _perside_frame([2026])
    out = g.score_with_champion(df, artifact, _R_HOME, _R_AWAY)
    # dry-run returns zero counts and must not raise on the 11-column tuple build
    assert g.write_signals(None, out, "db.sch.tbl", dry_run=True) == {"inserted": 0, "updated": 0}


def test_feature_matrix_is_market_blind(artifact):
    # E2.1–E2.5 market-blind constraint: no odds/line/consensus columns in the served matrix.
    assert find_market_columns(artifact["feature_names"]) == []


# ---------------------------------------------------------------------------
# THE AC — leakage-safe walk-forward backfill invariant
# ---------------------------------------------------------------------------

def _synthetic_wide(seasons, games_per_season=14) -> pd.DataFrame:
    """A minimal wide per-game frame build_perside_frame accepts: id cols + both finals. With no
    feature bases present, build_perside_frame yields just the synthesized `is_home` numeric feature
    — enough for a genuine (tiny, fast) LightGBM walk-forward that exercises the real code path."""
    rng = np.random.default_rng(0)
    rows = []
    gid = 0
    for yr in seasons:
        for _ in range(games_per_season):
            gid += 1
            rows.append({
                "game_pk": str(gid),
                "game_date": f"{yr}-0{rng.integers(4, 9)}-{rng.integers(10, 28)}",
                "game_year": yr,
                "home_final_score": int(rng.integers(0, 12)),
                "away_final_score": int(rng.integers(0, 12)),
            })
    return pd.DataFrame(rows)


def test_backfill_leakage_safe_invariant(artifact):
    """AC: no season is scored in-sample. Every is_oos row's scoring model trained strictly before
    that season; is_oos ⟺ train_through_season < game_year; each (game_pk, side) emitted once."""
    wide = _synthetic_wide([2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025])
    out = g.backfill_leakage_safe(wide, artifact, _R_HOME, _R_AWAY)

    # one row per (game_pk, side)
    assert not out.duplicated(subset=["game_pk", "side"]).any()
    assert len(out) == len(wide) * 2

    # the core leakage invariant, on EVERY row
    inv = out["is_oos"] == (out["train_through_season"] < out["game_year"])
    assert inv.all(), out.loc[~inv, ["game_year", "is_oos", "train_through_season"]]

    # every honest-OOS row was scored by a model that did NOT see its season
    oos = out[out["is_oos"]]
    assert (oos["train_through_season"] < oos["game_year"]).all()

    # walk-forward fold seasons (>= 2021 given min_train_seasons=3 over 2018-2020) are honest-OOS
    fold_rows = out[out["game_year"] >= 2021]
    assert fold_rows["is_oos"].all()
    assert (fold_rows["train_through_season"] == fold_rows["game_year"] - 1).all()

    # warm-up seasons (never an eval fold) are champion-scored + honestly tagged in-sample
    warmup = out[out["game_year"] < 2021]
    assert not warmup.empty
    assert (~warmup["is_oos"]).all()

    # served dispersion is the calibrated per-side r everywhere
    assert set(np.round(out["totals_perside_dispersion"].unique(), 4)) == {round(_R_HOME, 4), round(_R_AWAY, 4)}
