"""parity_check_bullpen_deleak.py — Story E1.7 SQL↔Python parity guardrail.

Confirms the DE-LEAKED dbt model `eb_bullpen_team_posteriors` (Path A) is
STRUCTURALLY equivalent to the tested Python `aggregate_team_v3(weight_mode='equal')`
from E2.1b: the same leakage-safe trailing-30d pre-game relief pool, equal
weighting, spined on mart_game_spine.

NOT bit-identical BY CONSTRUCTION — and that is expected:
  * the dbt port reuses each pool reliever's EB as of its MOST-RECENT prior
    appearance (the stored `eb_bullpen_posteriors` value), whereas
  * aggregate_team_v3 RECOMPUTES a fresh as-of-tonight EB from priors + season-to-
    date strictly before the game.
Both are leakage-safe; they differ only by at most one already-public appearance of
season-to-date data. So parity is asserted on the two things that MUST match plus a
tolerance on the freshness-driven value gap:

  (1) POOL MEMBERSHIP  — per (game_pk, team), the reliever-set Jaccard (same pool
      definition) and |n_relievers_dbt − n_relievers_py|. Expect Jaccard ≈ 1.0.
  (2) VALUE AGREEMENT  — corr(team_eb_bullpen_xwoba_dbt, _v3_equal) and mean|Δ|.
      Expect corr ≥ 0.97 and mean|Δ| ≤ ~0.010 xwOBA (the EB-freshness gap).

Operator-run (heavy: per-reliever build + Snowflake). READ-ONLY — writes nothing.

Usage:
    uv run python betting_ml/scripts/eb_priors/parity_check_bullpen_deleak.py \
        --dates 2025-05-01 2025-07-15 2026-04-15
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.utils.data_loader import get_snowflake_connection
from betting_ml.scripts.eb_priors.compute_bullpen_posteriors import (
    _load_normalized_ali_map,
    _load_prior,
)
from betting_ml.scripts.eb_priors.compute_bullpen_v3 import (
    aggregate_team_v3,
    build_per_reliever_frame,
)

# Gates (tunable). Jaccard near 1.0 = identical pool; corr/Δ allow the EB-freshness gap.
_MIN_JACCARD = 0.90
_MIN_CORR = 0.95
_MAX_MEAN_ABS_DIFF = 0.015


def _python_equal(conn, game_date: date) -> pd.DataFrame:
    """aggregate_team_v3(weight_mode='equal') for one date → (game_pk, team) frame."""
    season = game_date.year
    priors = _load_prior(season)
    prior_ali_map = _load_normalized_ali_map(conn, season - 1)
    per_reliever = build_per_reliever_frame(conn, game_date, season, priors, prior_ali_map)
    if per_reliever.empty:
        return pd.DataFrame()
    team = aggregate_team_v3(per_reliever, shrinkage_k=1.0, weight_mode="equal")
    # per-reliever set per (game_pk, team), for the membership check
    sets = (
        per_reliever.assign(game_pk=per_reliever["game_pk"].astype(str))
        .groupby(["game_pk", "team"])["pitcher_id"]
        .apply(lambda s: frozenset(str(x) for x in s))
        .rename("py_pool")
    )
    team = team.assign(game_pk=team["game_pk"].astype(str)).merge(
        sets, on=["game_pk", "team"], how="left"
    )
    return team[["game_pk", "team", "team_eb_bullpen_xwoba_v3", "n_relievers", "py_pool"]].rename(
        columns={"team_eb_bullpen_xwoba_v3": "xwoba_py", "n_relievers": "n_py"}
    )


def _dbt_table(conn, game_dates: list[date]) -> pd.DataFrame:
    """The DE-LEAKED dbt model rows for the given dates + the per-reliever pool set
    reconstructed from eb_bullpen_posteriors (so the membership check is apples-to-apples)."""
    ds = ", ".join(f"'{d.isoformat()}'" for d in game_dates)
    cur = conn.cursor()
    cur.execute(
        f"""
        select game_pk::varchar as game_pk, team,
               team_eb_bullpen_xwoba as xwoba_dbt, n_relievers as n_dbt
        from baseball_data.betting.eb_bullpen_team_posteriors
        where game_date in ({ds})
        """
    )
    tbl = pd.DataFrame(cur.fetchall(), columns=[c[0].lower() for c in cur.description])
    # Reconstruct the dbt pool membership: relievers who appeared for the team in the
    # strictly-prior 30d (mirrors the model's `pool` CTE), keyed to the target game's date.
    cur.execute(
        f"""
        with spine as (
            select game_pk::varchar as game_pk, game_date::date as game_date, home_team, away_team
            from baseball_data.betting.mart_game_spine
            where game_type = 'R' and game_date in ({ds})
        ),
        tg as (
            select game_pk, game_date, home_team as team from spine
            union all
            select game_pk, game_date, away_team as team from spine
        )
        select tg.game_pk, tg.team, re.pitcher_id::varchar as pitcher_id
        from tg
        join baseball_data.betting.eb_bullpen_posteriors re
          on  re.pitching_team = tg.team
          and re.game_date <  tg.game_date
          and re.game_date >= dateadd('day', -30, tg.game_date)
        group by tg.game_pk, tg.team, re.pitcher_id
        """
    )
    pool = pd.DataFrame(cur.fetchall(), columns=[c[0].lower() for c in cur.description])
    cur.close()
    sets = (
        pool.groupby(["game_pk", "team"])["pitcher_id"]
        .apply(frozenset)
        .rename("dbt_pool")
    )
    return tbl.merge(sets, on=["game_pk", "team"], how="left")


def _jaccard(a: frozenset | float, b: frozenset | float) -> float:
    if not isinstance(a, frozenset) or not isinstance(b, frozenset):
        return np.nan
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b) if (a | b) else 1.0


def main() -> None:
    ap = argparse.ArgumentParser(description="E1.7 SQL↔Python de-leak parity check")
    ap.add_argument("--dates", nargs="+", required=True,
                    type=lambda s: datetime.strptime(s, "%Y-%m-%d").date())
    args = ap.parse_args()

    conn = get_snowflake_connection()
    try:
        py = pd.concat([_python_equal(conn, d) for d in args.dates], ignore_index=True)
        dbt = _dbt_table(conn, args.dates)
    finally:
        conn.close()

    if py.empty or dbt.empty:
        print("✗ no overlapping rows (is the de-leaked model built for these dates?)")
        sys.exit(2)

    m = dbt.merge(py, on=["game_pk", "team"], how="inner")
    if m.empty:
        print("✗ no (game_pk, team) overlap between dbt table and Python aggregate.")
        sys.exit(2)

    m["jaccard"] = [_jaccard(a, b) for a, b in zip(m["dbt_pool"], m["py_pool"])]
    valid = m.dropna(subset=["xwoba_dbt", "xwoba_py"])
    corr = float(valid["xwoba_dbt"].corr(valid["xwoba_py"])) if len(valid) > 2 else float("nan")
    mad = float((valid["xwoba_dbt"] - valid["xwoba_py"]).abs().mean())
    jac = float(m["jaccard"].mean())
    n_match = int((m["n_dbt"] == m["n_py"]).sum())

    print("\n══ E1.7 de-leak parity (dbt eb_bullpen_team_posteriors ↔ aggregate_team_v3 equal) ══")
    print(f"  rows compared            : {len(m)}")
    print(f"  pool Jaccard (mean)      : {jac:.4f}   (gate ≥ {_MIN_JACCARD})")
    print(f"  exact n_relievers match  : {n_match}/{len(m)}")
    print(f"  xwoba corr               : {corr:.4f}   (gate ≥ {_MIN_CORR})")
    print(f"  xwoba mean|Δ|            : {mad:.4f}   (gate ≤ {_MAX_MEAN_ABS_DIFF})")
    print("  (value Δ is the EB-freshness gap: last-appearance EB vs fresh as-of-tonight — both leakage-safe.)")

    ok = (jac >= _MIN_JACCARD) and (not np.isnan(corr) and corr >= _MIN_CORR) and (mad <= _MAX_MEAN_ABS_DIFF)
    print(f"\n  VERDICT: {'✅ PARITY' if ok else '❌ DIVERGENCE — investigate pool/weighting before trusting the de-leak'}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
