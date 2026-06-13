"""
run_env_regime_monitor.py — Story 27.6, Task 1.

Detect (NOT predict) structural shifts in the league run-scoring environment and emit a
`run_env_regime_state` series + a `regime_shift_flag`. This is MONITORING: after enough
games, has the league-wide environment structurally moved? That is an easier, achievable
problem than the (settled-failed) in-season per-game regime PREDICTION — and its value is
operational: it feeds the promotion gate's current-season-corroboration criterion and gives
the ~Oct `delta_2026` totals re-eval a programmatic trigger.

DESIGN (grounded 2026-06-12 on 2021–2026 league run env, via MCP):
  - The league weekly run rate has std ≈ 0.5 runs and a STRONG, REPEATABLE within-season arc
    (April cold/low → summer warm/high, ~0.7–0.9 amplitude). That arc is SEASONALITY, not a
    regime — so we DESEASONALIZE (subtract the level-free within-season shape, averaged across
    seasons) before detecting. Otherwise the detector fires every April.
  - On the deseasonalized LEVEL we run a two-sided CUSUM. Real structural shifts (the +0.65
    2022→2023 rule-change step; an anomalous season) are SUSTAINED, so CUSUM accumulates them
    while zero-mean weekly noise cancels — separating signal from the 0.5-run weekly noise.
  - NOTE (Story 27.6 grounding): this league-LEVEL monitor does NOT explain the totals model's
    2025 over-bias (that is a feature→runs RELATIONSHIP shift, league rate was flat) — see the
    separate diagnostic task. This monitor serves the PROMOTION GATE + real league shifts.

Outputs (written next to this script's eval dir): the weekly state series + detected shifts +
a validation report (does it catch the known 2022→2023 step? detection lag in weeks? within-
season false-alarm rate?).

Runtime: one Snowflake aggregate + in-memory CUSUM — fast, but it queries Snowflake, so run it
with creds:
    uv run python betting_ml/scripts/regime/run_env_regime_monitor.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from betting_ml.utils.data_loader import get_snowflake_connection

_OUT_DIR = PROJECT_ROOT / "betting_ml" / "evaluation" / "regime"

# ── Detector parameters (calibrated to the 0.5-run weekly noise; see grounding) ──
_MIN_GAMES_PER_WEEK = 15        # drop thin weeks (early Mar / late Oct) from the series
_CUSUM_SLACK_K = 0.25           # runs: half the ~0.5 minimum shift we care to detect (CUSUM slack)
_CUSUM_THRESH_H = 1.50          # runs·weeks: fire when |cumulative deviation| exceeds this
_EWMA_HALFLIFE_WEEKS = 4.0      # smoothing for the reported regime-state level

# The one KNOWN structural shift to validate detection against (rule-change regime).
_KNOWN_SHIFT_SEASON_BOUNDARY = (2022, 2023)


_QUERY = """
SELECT game_date,
       home_final_score + away_final_score AS total_runs
FROM baseball_data.betting.mart_game_results
WHERE home_final_score IS NOT NULL AND away_final_score IS NOT NULL
  AND YEAR(game_date) >= 2021
ORDER BY game_date
"""


def _load_weekly_series() -> pd.DataFrame:
    """Weekly league run rate: one row per (season, week-of-season) with game-weighted mean."""
    conn = get_snowflake_connection()
    try:
        df = pd.read_sql(_QUERY, conn)
    finally:
        conn.close()
    df.columns = [c.lower() for c in df.columns]
    df["game_date"] = pd.to_datetime(df["game_date"])
    df["season"] = df["game_date"].dt.year
    # Week-of-season = ISO-week minus the season's first ISO-week, so weeks align across years
    # regardless of which calendar week opening day fell on.
    iso = df["game_date"].dt.isocalendar()
    df["iso_week"] = iso["week"].astype(int)
    first_week = df.groupby("season")["iso_week"].transform("min")
    df["week_of_season"] = df["iso_week"] - first_week

    wk = (df.groupby(["season", "week_of_season"])
            .agg(games=("total_runs", "size"), avg_total=("total_runs", "mean"))
            .reset_index())
    wk = wk[wk["games"] >= _MIN_GAMES_PER_WEEK].reset_index(drop=True)
    return wk


def _deseasonalize(wk: pd.DataFrame) -> pd.DataFrame:
    """Remove the level-free within-season arc so the detector sees STRUCTURAL level only.

    within_season_shape[w] = mean over seasons of (weekly_rate − that season's mean).
    deseason_level = weekly_rate − within_season_shape[week_of_season].
    """
    season_mean = wk.groupby("season")["avg_total"].transform("mean")
    wk = wk.assign(within_season_dev=wk["avg_total"] - season_mean)
    shape = (wk.groupby("week_of_season")["within_season_dev"].mean()
               .rename("season_shape").reset_index())
    wk = wk.merge(shape, on="week_of_season", how="left")
    wk["deseason_level"] = wk["avg_total"] - wk["season_shape"]
    return wk


def _cusum(x: np.ndarray, baseline: float, k: float, h: float, reanchor_window: int = 6):
    """Two-sided CUSUM with ADAPTIVE re-anchoring. Detects shifts relative to the CURRENT
    regime, not a frozen initial baseline: on each fire it (a) records the direction, (b)
    re-anchors the baseline to the mean of the last `reanchor_window` weeks (the new level),
    and (c) resets the accumulators — so the next shift is measured from the new regime.
    Without re-anchoring, a single anomalous reference season (e.g. high-2021) makes every
    later season read as drift in one direction. Returns (s_pos, s_neg, flag, direction, base).
    """
    n = len(x)
    s_pos = np.zeros(n); s_neg = np.zeros(n); flag = np.zeros(n, dtype=bool)
    direction = np.array([""] * n, dtype=object); base = np.zeros(n)
    sp = sn = 0.0; b = float(baseline)
    for i in range(n):
        base[i] = b
        d = x[i] - b
        sp = max(0.0, sp + d - k)
        sn = min(0.0, sn + d + k)
        s_pos[i], s_neg[i] = sp, sn
        if sp > h or sn < -h:
            flag[i] = True
            direction[i] = "UP" if sp > h else "DOWN"
            lo = max(0, i - reanchor_window + 1)
            b = float(np.mean(x[lo:i + 1]))   # re-anchor to the new regime level
            sp = sn = 0.0
    return s_pos, s_neg, flag, direction, base


def run() -> None:
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("Loading league run-environment series from Snowflake...")
    wk = _load_weekly_series()
    wk = _deseasonalize(wk)
    wk = wk.sort_values(["season", "week_of_season"]).reset_index(drop=True)

    # Initial baseline = the FIRST season's deseasonalized level (the CUSUM then re-anchors as
    # regimes shift, so this is only the starting reference, not a frozen one).
    baseline = float(wk.loc[wk["season"] == wk["season"].min(), "deseason_level"].mean())
    x = wk["deseason_level"].to_numpy()
    s_pos, s_neg, flag, direction, base = _cusum(x, baseline, _CUSUM_SLACK_K, _CUSUM_THRESH_H)
    wk["cusum_pos"], wk["cusum_neg"], wk["regime_shift_flag"] = s_pos, s_neg, flag
    wk["shift_direction"], wk["cusum_baseline"] = direction, base

    # Reported regime-state level = EWMA of the deseasonalized level.
    alpha = 1.0 - 0.5 ** (1.0 / _EWMA_HALFLIFE_WEEKS)
    wk["run_env_regime_state"] = wk["deseason_level"].ewm(alpha=alpha, adjust=False).mean()

    # ── Validation ────────────────────────────────────────────────────────────
    deseason_std = float(wk["deseason_level"].std())
    fires = wk[wk["regime_shift_flag"]]
    print(f"\nDeseasonalized weekly-level noise: std={deseason_std:.3f} runs "
          f"(raw weekly std was ~0.50 — seasonality removed)")
    print(f"Baseline (≤2021) deseasonalized level: {baseline:.3f}")
    print(f"\nDetected {len(fires)} regime-shift fire(s) "
          f"(CUSUM k={_CUSUM_SLACK_K}, h={_CUSUM_THRESH_H}, adaptive baseline):")
    for _, r in fires.iterrows():
        print(f"  season {int(r['season'])} week+{int(r['week_of_season']):2d}  "
              f"level={r['deseason_level']:.2f}  baseline={r['cusum_baseline']:.2f}  "
              f"state={r['run_env_regime_state']:.2f}  [{r['shift_direction']}]")

    # Did we catch the known 2022→2023 rule-change step? It is an UP shift (+~0.65), so require
    # an UP-direction fire near the 2023 season open — a DOWN fire is the 2022-low regime, not this.
    s_from, s_to = _KNOWN_SHIFT_SEASON_BOUNDARY
    up_2023 = wk[(wk["season"] == s_to) & (wk["shift_direction"] == "UP")]
    print(f"\nKNOWN SHIFT {s_from}→{s_to} (rule changes, +~0.65 runs UP):")
    if len(up_2023):
        lag = int(up_2023.iloc[0]["week_of_season"])
        print(f"  ✓ DETECTED (UP) at {s_to} week+{lag} → detection lag ≈ {lag} weeks into the new regime")
    else:
        print(f"  ✗ UP shift NOT detected in {s_to} — loosen h/k or check re-anchoring")

    # Within-season false alarms: fires in 2024/2025 (stable seasons, no known structural shift).
    stable = wk[wk["season"].isin([2024, 2025]) & wk["regime_shift_flag"]]
    print(f"\nFalse-alarm check (stable 2024+2025, no known shift): {len(stable)} fire(s) "
          f"{'— bounded ✓' if len(stable) <= 2 else '— TOO MANY, raise h'}")

    out = _OUT_DIR / "run_env_regime_state.csv"
    wk.to_csv(out, index=False)
    print(f"\nWrote {out}  ({len(wk)} weekly rows)")
    print("Columns: season, week_of_season, games, avg_total, deseason_level, "
          "run_env_regime_state, regime_shift_flag")


if __name__ == "__main__":
    run()
