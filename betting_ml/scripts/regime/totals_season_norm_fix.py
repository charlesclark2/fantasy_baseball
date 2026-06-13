"""
totals_season_norm_fix.py — Story 27.6, Task 2 → fix validation.

The 2025 totals over-bias (+0.67) is driven by the CONTACT-QUALITY feature family (xwOBA /
hard-hit / barrel) shifting up ~0.5–0.7 SD in 2025 — a REAL change (hard-hit% +1.6 pts, K%
down; confirmed in mart_bullpen_effectiveness), NOT an artifact. But actual 2025 runs stayed at
the training-period average (~8.85): the contact→runs CONVERSION dropped (a ball-carry/drag
regime). So the bias is purely the inflated feature LEVEL — and SEASON-NORMALIZING the
contact-quality features (z-score within season) should realign an average matchup to the
training base and remove it.

This validates that fix OFFLINE before productionizing it (in dbt). It re-runs the 2025 fold
(and 2024 as a control) with vs without season-normalization and reports the bias change.

⚠ LEAKAGE NOTE: this prototype z-scores using each season's FULL mean/std (incl. eval-season
2025) — valid to test the MECHANISM, but live serving cannot know the season mean early. The
production version uses a rolling/expanding league baseline (Task 1's monitor) — see Story 27.6.

Runs >1 min (Snowflake + NGBoost). Hand off:
    uv run python betting_ml/scripts/regime/totals_season_norm_fix.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from betting_ml.scripts.ablation_identifier_features import _impute
from betting_ml.scripts.promotion_gate_eval import _challenger_ngb, _contract_cols
from betting_ml.utils.data_loader import load_features

_CONTRACT = "betting_ml/models/total_runs/feature_columns_ngboost_tuned_2026.json"
_TUNING = "betting_ml/evaluation/tuning_results_ngboost_total_runs.json"
_TARGET = "total_runs"
_TRAIN = [2021, 2022, 2023, 2024]

# The contact-quality family whose ABSOLUTE level inflated with the 2025 contact change. These
# carry relative skill fine but their cross-season LEVEL tracks the ball/conversion regime, so
# we season-normalize them; counts/rates not tied to contact-quality (K%, BB%) are left alone.
_CONTACT_RE = re.compile(r"(xwoba|hard_hit|barrel|exit_velo|launch|xslg|xba|xobp)", re.I)


def _fit_ngb(Xtr, ytr):
    from ngboost import NGBRegressor
    from ngboost.distns import Normal
    hn = _challenger_ngb(_TUNING)
    m = NGBRegressor(n_estimators=hn["n_estimators"], Dist=Normal, verbose=False)
    m.fit(Xtr.values, ytr)
    return m


def _season_normalize(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Z-score each contact-quality column WITHIN each season (game_year). Removes the
    cross-season absolute-level shift while preserving within-season relative quality."""
    out = df.copy()
    targets = [c for c in cols if _CONTACT_RE.search(c)]
    g = out.groupby("game_year")
    for c in targets:
        mu = g[c].transform("mean")
        sd = g[c].transform("std").replace(0, np.nan)
        out[c] = ((out[c] - mu) / sd).fillna(0.0)
    return out, targets


def _fold_bias(df: pd.DataFrame, cols: list[str], eval_season: int) -> float:
    tr = df[df["game_year"].isin([s for s in _TRAIN if s < eval_season] or _TRAIN)]
    ev = df[df["game_year"] == eval_season]
    Xtr, Xev = _impute(tr[cols], ev[cols])
    m = _fit_ngb(Xtr, tr[_TARGET].values)
    pred = np.asarray(m.predict(Xev.values), float)
    return float(pred.mean() - ev[_TARGET].values.mean())


def run() -> None:
    print("Loading features from Snowflake...")
    df = load_features().reset_index(drop=True)
    cols = _contract_cols(_CONTRACT, df)
    df_norm, normed = _season_normalize(df, cols)
    print(f"Totals market-blind contract: {len(cols)} features")
    print(f"Season-normalized {len(normed)} contact-quality features: {normed[:8]}"
          + (" ..." if len(normed) > 8 else ""))

    print(f"\n{'fold':>6}{'bias_raw':>12}{'bias_seasonnorm':>18}{'improvement':>13}")
    for ev in (2024, 2025):
        b_raw = _fold_bias(df, cols, ev)
        b_norm = _fold_bias(df_norm, cols, ev)
        print(f"{ev:>6}{b_raw:>+12.3f}{b_norm:>+18.3f}{(abs(b_raw) - abs(b_norm)):>+13.3f}")

    print("\nRead: season-normalization should pull the 2025 bias from ~+0.67 toward ~0 while "
          "NOT inflating 2024 (control). If 2025 |bias| drops sharply and 2024 stays small, the "
          "fix is validated → productionize the within-season z-score in dbt (rolling baseline "
          "for live, per Story 27.6 / Task 1 monitor) and re-run the calibration gate.")


if __name__ == "__main__":
    run()
