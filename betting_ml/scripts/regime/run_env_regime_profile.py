"""run_env_regime_profile.py — Story E1.6: cross-era run-environment regime profiler.

Distinct from `run_env_regime_monitor.py` (the 2021+ within-series CUSUM shift *detector* that
feeds the promotion gate). THIS profiles every season 2015–2026 on the run-environment axes
that matter for the training-history-extension decision, and emits the per-season
**regime-similarity weight** toward the current regime — the soft weight Story E1.6 uses
instead of a hard year cutoff.

Axes:
  - LEVEL   — mean game total (runs/game).
  - SPREAD  — std of game totals (the totals variance axis; E2's whole problem).
  - CONTACT — league offensive xwOBA (mean of home/away 30d offense xwOBA), the contact→runs
              CONVERSION axis where the 2025 over-bias lived (Story 27.6). Available 2015+.

Output: `ablation_results/run_env_regime_profile.md` + a JSON sidecar with the per-season
profile, distance, and weight toward the latest season's trailing regime. Shows the key
finding plainly: regime is NOT time-ordered (2016/2018 are closer to now than 2019/2023).

Runtime: two Snowflake aggregates — fast, but it queries Snowflake, so run with creds:
    uv run python betting_ml/scripts/regime/run_env_regime_profile.py
    uv run python betting_ml/scripts/regime/run_env_regime_profile.py --target-season 2026 --trailing 2
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from betting_ml.utils.data_loader import get_snowflake_connection
from betting_ml.utils.run_env_regime import (
    DEFAULT_BANDWIDTH, DEFAULT_TRAILING_SEASONS, WEIGHT_DIMS, _standardize, _weight_frame,
    regime_distances, season_regime_weights, trailing_centroid,
)

_REPORT = PROJECT_ROOT / "quant_sports_intel_models" / "baseball" / "ablation_results" / "run_env_regime_profile.md"
_JSON = PROJECT_ROOT / "betting_ml" / "evaluation" / "regime" / "run_env_regime_profile.json"

_LEVEL_SPREAD_Q = """
SELECT YEAR(game_date)                                       AS season,
       COUNT(*)                                              AS n_games,
       AVG(home_final_score + away_final_score)              AS avg_total_runs,
       STDDEV(home_final_score + away_final_score)           AS std_total_runs
FROM baseball_data.betting.mart_game_results
WHERE home_final_score IS NOT NULL AND away_final_score IS NOT NULL
  AND YEAR(game_date) BETWEEN 2015 AND 2026
GROUP BY YEAR(game_date)
ORDER BY season
"""

# League offensive xwOBA per season (contact level) — mean of both sides' 30d offense xwOBA.
_CONTACT_Q = """
SELECT game_year                                             AS season,
       AVG((home_off_xwoba_30d + away_off_xwoba_30d) / 2.0)  AS league_off_xwoba
FROM baseball_data.betting_features.feature_pregame_game_features
WHERE home_off_xwoba_30d IS NOT NULL AND away_off_xwoba_30d IS NOT NULL
  AND game_year BETWEEN 2015 AND 2026
GROUP BY game_year
ORDER BY season
"""


def _load_profile() -> pd.DataFrame:
    conn = get_snowflake_connection()
    try:
        ls = pd.read_sql(_LEVEL_SPREAD_Q, conn)
        try:
            ct = pd.read_sql(_CONTACT_Q, conn)
        except Exception as exc:  # contact axis is best-effort
            print(f"  [warn] contact axis unavailable ({exc}); profiling on level+spread only.")
            ct = None
    finally:
        conn.close()
    ls.columns = [c.lower() for c in ls.columns]
    prof = ls.set_index("season")[["avg_total_runs", "std_total_runs"]].astype(float)
    if ct is not None and len(ct):
        ct.columns = [c.lower() for c in ct.columns]
        prof = prof.join(ct.set_index("season")["league_off_xwoba"].astype(float).rename("avg_league_off_xwoba"))
    prof.index = prof.index.astype(int)
    return prof.dropna().sort_index()


def run(target_season: int | None, trailing: int, bandwidth: float) -> dict:
    prof = _load_profile()
    if target_season is None:
        target_season = int(prof.index.max())
    # Distance + weight use LEVEL + SPREAD only (contact is informational; see WEIGHT_DIMS).
    zw = _standardize(_weight_frame(prof, WEIGHT_DIMS))
    centroid = trailing_centroid(zw, target_season, trailing=trailing)
    dist = regime_distances(zw, centroid)
    weights = season_regime_weights(prof, target_season, trailing=trailing, bandwidth=bandwidth)

    trailing_used = [int(s) for s in prof.index if s < target_season][-trailing:]
    rows = []
    for s in prof.index:
        rows.append({
            "season": int(s),
            **{k: round(float(prof.loc[s, k]), 4) for k in prof.columns},
            "regime_dist": round(float(dist[s]), 3),
            "regime_weight": round(float(weights[s]), 3),
        })
    payload = {"target_season": target_season, "trailing_seasons": trailing,
               "trailing_centroid_seasons": trailing_used, "bandwidth": bandwidth,
               "dims": list(prof.columns), "seasons": rows}
    _write_report(payload)
    return payload


def _band(w: float) -> str:
    return "✅ on-regime" if w >= 0.7 else ("🟡 partial" if w >= 0.35 else "🔴 off-regime")


def _write_report(payload: dict) -> None:
    _REPORT.parent.mkdir(parents=True, exist_ok=True)
    _JSON.parent.mkdir(parents=True, exist_ok=True)
    _JSON.write_text(json.dumps(payload, indent=2))
    rows = sorted(payload["seasons"], key=lambda r: -r["regime_weight"])
    ty = payload["target_season"]
    has_contact = "avg_league_off_xwoba" in payload["dims"]
    lines = [
        f"# Cross-Era Run-Environment Regime Profile (Story E1.6)",
        "",
        f"- Target (current) regime: **{ty}** · trailing centroid = seasons "
        f"{payload['trailing_centroid_seasons']} · Gaussian bandwidth {payload['bandwidth']}",
        f"- Distance/weight axes: scoring **level** + game-total **spread**"
        + ("; league offensive **xwOBA** shown as *informational only* (the contact→runs "
           "conversion regime is corrected at the feature level by season-normalization, Story 27.7 — "
           "including it here would double-count and destabilize the centroid)" if has_contact else ""),
        "",
        "**Regime is NOT time-ordered** — the `regime_weight` is the soft `sample_weight` Story E1.6 "
        "uses to extend training history without a hard year cutoff. Older on-regime seasons keep "
        "~full weight; off-regime seasons (e.g. 2019 peak juiced ball) are down-weighted even though "
        "recent seasons like 2023 may sit further from the current regime.",
        "",
        "| season | R/G | spread | " + ("league xwOBA *(info)* | " if has_contact else "") + "regime dist | weight | band |",
        "|---|---|---|" + ("---|" if has_contact else "") + "---|---|---|",
    ]
    for r in rows:
        contact = f"{r.get('avg_league_off_xwoba', float('nan')):.3f} | " if has_contact else ""
        lines.append(f"| {r['season']} | {r['avg_total_runs']:.2f} | {r['std_total_runs']:.2f} | "
                     f"{contact}{r['regime_dist']:.2f} | {r['regime_weight']:.3f} | {_band(r['regime_weight'])} |")
    lines += ["",
              "## How to use (E1.6)",
              "Pass `--regime-weight --min-year 2016` to `promotion_gate_eval.py` (with an E1.3 slim "
              "contract via `--challenger-contract`): each fold weights its training games by regime "
              "similarity to that fold's eval season, multiplied with the E1.2 uniqueness weight. The "
              "question it answers: *does regime-aware extra history (2016+) make the slim model more "
              "accurate/robust than the 2021-only version, and does it cut the 2025 over-bias?*",
              "",
              f"_JSON: `{_JSON.relative_to(PROJECT_ROOT)}`_"]
    _REPORT.write_text("\n".join(lines))
    print(f"\nWrote {_REPORT}")
    print(f"Wrote {_JSON}")
    print(f"\nRegime weights toward {ty} (trailing {payload['trailing_centroid_seasons']}):")
    for r in rows:
        print(f"  {r['season']}: weight={r['regime_weight']:.3f}  dist={r['regime_dist']:.2f}  {_band(r['regime_weight'])}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target-season", type=int, default=None,
                    help="Season whose regime to anchor to (default = latest available).")
    ap.add_argument("--trailing", type=int, default=DEFAULT_TRAILING_SEASONS,
                    help=f"Seasons before the target that define the 'current' regime centroid "
                         f"(default {DEFAULT_TRAILING_SEASONS}).")
    ap.add_argument("--bandwidth", type=float, default=DEFAULT_BANDWIDTH,
                    help=f"Gaussian kernel width in standardized-distance units "
                         f"(default {DEFAULT_BANDWIDTH}, shared with the gate via run_env_regime.DEFAULT_BANDWIDTH).")
    args = ap.parse_args()
    run(args.target_season, args.trailing, args.bandwidth)


if __name__ == "__main__":
    main()
