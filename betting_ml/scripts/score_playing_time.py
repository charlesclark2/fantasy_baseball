"""score_playing_time.py — Story 33.1 Task 3a: leakage-free P(start) output table.

Produces the per-(game_pk, side, player_id) START-PROBABILITY table that Story 33.3
(expected-lineup feature family) consumes as Σ P(start)·player_stat. Writes
`baseball_data.betting.mart_player_start_probability`.

LEAKAGE DISCIPLINE (the whole point of Epic 33): 33.3 trains the pre-lineup models
WALK-FORWARD (train <Y, eval Y), so the historical P(start) feature for year Y games must
be produced by a model trained ONLY on <Y. Scoring history with the final all-data model
(train_playing_time_model.py's artifact) would leak the future into 33.3's training. So:
  - HISTORICAL rows: walk-forward — for each year Y, fit on <Y, predict Y. Years without
    >=2 prior training seasons (2015-2016) fall back to the raw `start_rate_50` (a
    leakage-free baseline, flagged p_source='rate50_fallback').
  - The final all-data model (the saved artifact) is for SERVING TODAY only — today is
    after all training data, so no leak. That live path is Task 3b (ships with 33.6,
    needs the scheduled-game candidate extension to build_playing_time_dataset.py).

Runtime: re-fits XGB per season over ~1.1M rows + a bulk Snowflake load → minutes. HAND OFF.

Usage:
    uv run python betting_ml/scripts/score_playing_time.py
    uv run python betting_ml/scripts/score_playing_time.py --no-write   # score + stats only, skip Snowflake
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from betting_ml.scripts.train_playing_time_model import _FEATURES, _XGB_PARAMS, _PANEL, _prep

_TABLE = "baseball_data.betting.mart_player_start_probability"
_SCORED = PROJECT_ROOT / "betting_ml" / "data" / "playing_time_scored_33_1.parquet"
_MIN_TRAIN_SEASONS = 2


def _walk_forward_scores(df: pd.DataFrame) -> pd.DataFrame:
    """Leakage-free P(start) per historical row: year Y scored by a model fit on <Y.
    Earliest years (no >=2 prior seasons) fall back to the raw start_rate_50."""
    from xgboost import XGBClassifier

    years = sorted(df["game_year"].unique())
    parts = []
    for Y in years:
        ev = df[df["game_year"] == Y]
        tr = df[df["game_year"] < Y]
        if tr["game_year"].nunique() < _MIN_TRAIN_SEASONS:
            out = ev[["game_pk", "side", "player_id", "official_date", "game_year", "did_start"]].copy()
            out["start_probability"] = ev["start_rate_50"].to_numpy()
            out["p_source"] = "rate50_fallback"
            parts.append(out)
            print(f"  {Y}: {len(ev):,} rows  (rate50 fallback — <{_MIN_TRAIN_SEASONS} prior seasons)")
            continue
        clf = XGBClassifier(**_XGB_PARAMS)
        clf.fit(tr[_FEATURES], tr["did_start"].astype(int))
        out = ev[["game_pk", "side", "player_id", "official_date", "game_year", "did_start"]].copy()
        out["start_probability"] = clf.predict_proba(ev[_FEATURES])[:, 1]
        out["p_source"] = "walk_forward_model"
        parts.append(out)
        print(f"  {Y}: {len(ev):,} rows  (walk-forward model, trained on {tr['game_year'].nunique()} seasons)")
    return pd.concat(parts, ignore_index=True)


def _write(df: pd.DataFrame) -> None:
    from snowflake.connector.pandas_tools import write_pandas

    from betting_ml.utils.data_loader import get_snowflake_connection
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(f"""
            CREATE OR REPLACE TABLE {_TABLE} (
                game_pk            INTEGER,
                side               VARCHAR(10),
                player_id          INTEGER,
                official_date      VARCHAR(10),    -- ISO 'YYYY-MM-DD'; 33.3 casts ::date.
                                                   -- VARCHAR avoids write_pandas datetime
                                                   -- serialization bugs: DATE failed to cast
                                                   -- the int64-ns parquet value, and TIMESTAMP_NTZ
                                                   -- mis-scaled ns → corrupt timestamps.
                game_year          INTEGER,
                start_probability  FLOAT,
                p_source           VARCHAR(20),
                did_start          INTEGER
            )
        """)
        up = df.copy()
        up["official_date"] = pd.to_datetime(up["official_date"]).dt.strftime("%Y-%m-%d")  # ISO string
        up.columns = [c.upper() for c in up.columns]
        ok, _, nrows, _ = write_pandas(conn, up, table_name="MART_PLAYER_START_PROBABILITY",
                                       database="BASEBALL_DATA", schema="BETTING", quote_identifiers=False)
        conn.commit()
        print(f"  write_pandas ok={ok}, {nrows:,} rows → {_TABLE}")
    finally:
        conn.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-write", action="store_true", help="score + stats only, skip Snowflake write")
    ap.add_argument("--write-only", action="store_true",
                    help="load the cached scored parquet and write to Snowflake (skip re-scoring)")
    args = ap.parse_args()

    if args.write_only:
        print(f"[--write-only] loading cached scores {_SCORED.name}...")
        scored = pd.read_parquet(_SCORED)
        print(f"  {len(scored):,} rows. Writing {_TABLE}...")
        _write(scored)
        print("Done.")
        return

    print(f"Loading panel {_PANEL.name}...")
    df = _prep(pd.read_parquet(_PANEL))
    print(f"  {len(df):,} rows, {df['game_year'].min()}-{df['game_year'].max()}")

    print("Walk-forward scoring (leakage-free historical P(start))...")
    scored = _walk_forward_scores(df)
    _SCORED.parent.mkdir(parents=True, exist_ok=True)
    scored.to_parquet(_SCORED, index=False)  # cache so a write retry skips re-scoring

    # sanity: predicted top-k vs actual starters overall (lineup reconstruction)
    wf = scored[scored["p_source"] == "walk_forward_model"]
    print(f"\n  scored rows={len(scored):,}  walk_forward={len(wf):,}  "
          f"rate50_fallback={len(scored)-len(wf):,}")
    print(f"  P(start): mean={scored['start_probability'].mean():.3f}  "
          f"corr(did_start)={np.corrcoef(scored['start_probability'], scored['did_start'])[0,1]:.3f}")
    hi = scored[scored["start_probability"] >= 0.8]
    print(f"  sanity: P>=0.8 cohort actual start rate={hi['did_start'].mean():.3f} (expect high)")

    if args.no_write:
        print("\n[--no-write] skipping Snowflake write.")
        return
    print(f"\nWriting {_TABLE}...")
    _write(scored)
    print("Done. Story 33.3 consumes this as Σ P(start)·player_stat.")


if __name__ == "__main__":
    main()
