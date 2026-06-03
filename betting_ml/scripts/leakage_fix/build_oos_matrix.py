"""
build_oos_matrix.py — Leakage fix Phase 2

Build a leakage-free Layer 3 game-level matrix by taking the production matrix
(load_layer3_features) as the scaffold (targets, game context, contract columns)
and OVERWRITING the 5 floor sub-model signal columns with the walk-forward OOS
values regenerated in Phase 1 (oos_signals_*.parquet). The matchup signal (the
6th, non-floor group) is NOT regenerated, so it is excluded (NaN + available=0)
rather than left at its contaminated production value.

Coverage = intersection of game_pks present in all 5 OOS parquets, restricted to
seasons 2022-2026 (run_env's 2021 data floor + ≥1 prior train season binds the
earliest OOS season to 2022). Every kept game has all 5 floor signals → completeness 1.0.

Returns a game-level DataFrame with the exact Layer 3 feature-column contract,
plus home_win / total_runs / game_year / season / game_date for downstream eval.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(_PROJECT_ROOT / ".env")

from betting_ml.scripts.load_layer3_features import (
    load_layer3_features, _add_completeness, _load_feature_contract,
)

_OOS_DIR = _PROJECT_ROOT / "betting_ml" / "models" / "layer3" / "oos_signals"
_DEFAULT_SEASONS = (2022, 2023, 2024, 2025, 2026)

# Per-side groups: parquet file → {raw signal col : matrix base name}, available base.
_SIDE_GROUPS = {
    "offense": ("oos_signals_offense.parquet", {
        "pred_runs_mu": "pred_runs_mu_v2",
        "pred_runs_dispersion": "pred_runs_dispersion_v2",
        "pred_runs_uncertainty": "pred_runs_uncertainty_v2",
    }, "pred_runs_mu_v2_available"),
    "starter": ("oos_signals_starter.parquet", {
        "starter_suppression_mu": "starter_suppression_mu_v1",
        "starter_suppression_sigma": "starter_suppression_sigma_v1",
        "starter_uncertainty": "starter_uncertainty_v1",
    }, "starter_suppression_mu_v1_available"),
    "starter_ip": ("oos_signals_starter_ip.parquet", {
        "starter_ip_mu": "starter_ip_mu_v1",
        "starter_ip_dispersion": "starter_ip_dispersion_v1",
        "starter_ip_uncertainty": "starter_ip_uncertainty_v1",
    }, "starter_ip_mu_v1_available"),
    "bullpen": ("oos_signals_bullpen.parquet", {
        "bullpen_mu": "bullpen_mu_v2",
        "bullpen_dispersion": "bullpen_dispersion_v2",
        "bullpen_uncertainty": "bullpen_uncertainty_v2",
    }, "bullpen_mu_v2_available"),
}

# run_env: env-level (single value per game, no home_/away_).
_RUN_ENV = ("oos_signals_run_env.parquet", {
    "run_env_mu": "run_env_mu_v4",
    "run_env_dispersion": "run_env_dispersion_v4",
    "run_env_uncertainty": "run_env_mu_v4_uncertainty",
}, "run_env_mu_v4_available")


def _read(name: str) -> pd.DataFrame:
    p = _OOS_DIR / name
    if not p.exists():
        raise FileNotFoundError(f"OOS parquet missing: {p} — run the Phase 1 regenerator first.")
    return pd.read_parquet(p)


def _apply_side(df: pd.DataFrame, parq: pd.DataFrame, raw_to_base: dict, avail_base: str) -> None:
    """Pivot a per-(game_pk,side) parquet to home_/away_ matrix columns; overwrite df in place."""
    piv = parq.pivot_table(index="game_pk", columns="side", values=list(raw_to_base))
    for raw, base in raw_to_base.items():
        for side in ("home", "away"):
            col = f"{side}_{base}"
            df[col] = df["game_pk"].map(piv[(raw, side)])
    df[f"home_{avail_base}"] = 1.0
    df[f"away_{avail_base}"] = 1.0


def build_oos_matrix(env: str = "prod", seasons: tuple = _DEFAULT_SEASONS) -> pd.DataFrame:
    df = load_layer3_features(env=env)

    parqs = {k: _read(v[0]) for k, v in _SIDE_GROUPS.items()}
    run_env = _read(_RUN_ENV[0])

    # Coverage = game_pks present in ALL five OOS parquets, in the requested seasons.
    pk_sets = [set(p["game_pk"]) for p in parqs.values()] + [set(run_env["game_pk"])]
    common = set.intersection(*pk_sets)
    df = df[df["game_pk"].isin(common) & df["game_year"].isin(seasons)].reset_index(drop=True)
    if df.empty:
        raise RuntimeError("No games in the OOS coverage ∩ seasons — check parquets/seasons.")

    # run_env (env-level)
    re_idx = run_env.set_index("game_pk")
    for raw, base in _RUN_ENV[1].items():
        df[base] = df["game_pk"].map(re_idx[raw])
    df[_RUN_ENV[2]] = 1.0

    # per-side groups
    for gname, (_fname, raw_to_base, avail_base) in _SIDE_GROUPS.items():
        _apply_side(df, parqs[gname], raw_to_base, avail_base)

    # Exclude matchup (non-floor, not regenerated → not left contaminated).
    feature_cols = _load_feature_contract()
    for c in feature_cols:
        if "matchup" in c:
            df[c] = 0.0 if c.endswith("_available") else np.nan

    # Recompute completeness from the (now OOS) availability flags → 1.0 for these games.
    df = _add_completeness(df)
    return df


def oos_matrix_summary(df: pd.DataFrame) -> str:
    fc = _load_feature_contract()
    by_season = df.groupby("game_year").agg(
        n=("game_pk", "size"),
        completeness=("signal_completeness_score", "mean"),
        home_win_rate=("home_win", "mean"),
    ).round(3)
    return (f"OOS matrix: {len(df)} games, {len(fc)} contract cols, "
            f"completeness min={df['signal_completeness_score'].min():.2f}\n" + by_season.to_string())


if __name__ == "__main__":
    m = build_oos_matrix()
    print(oos_matrix_summary(m))
