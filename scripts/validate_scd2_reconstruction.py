"""
Epic 15, Story 15.9 — Historical CLV reconstruction validation.

Confirms that for 3 game_pks from prediction_snapshots:
  (1) AS-OF SCD-2 queries reproduce the stored feature_snapshot values exactly.
  (2) Loading the stored model artifact and running inference on the stored
      feature_snapshot reproduces the stored prediction within ±0.001.

Usage:
    python scripts/validate_scd2_reconstruction.py

Requires:
    - SNOWFLAKE_* env vars (same as predict_today.py)
    - AWS credentials with s3:GetObject on baseball-betting-ml-artifacts/*
    - pip install ngboost boto3 snowflake-connector-python pandas numpy
"""

import json
import os
import pickle
import io
import sys

import boto3
import numpy as np
import pandas as pd
import snowflake.connector

# ---------------------------------------------------------------------------
# Validation targets
# 3 game_pks predicted at 2026-05-15T14:06:05 UTC, model_version=v2
# ---------------------------------------------------------------------------
GAME_PKS = [823384, 824280, 824360]
PREDICTED_AT = "2026-05-15T14:06:05.028161"
TARGET = "total_runs"
MODEL_VERSION = "v2"
TOLERANCE = 0.001

# ---------------------------------------------------------------------------
# Snowflake connection (uses same env vars as the rest of the project)
# ---------------------------------------------------------------------------
def get_conn():
    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        password=os.environ["SNOWFLAKE_PASSWORD"],
        warehouse=os.environ.get("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH"),
        database="BASEBALL_DATA",
        schema="BETTING",
    )


def fetch_snapshots(conn):
    """Pull stored prediction + feature_snapshot for the 3 game_pks."""
    gks = ", ".join(str(g) for g in GAME_PKS)
    sql = f"""
        select game_pk, prediction, feature_snapshot, model_artifact_s3_uri
        from BASEBALL_DATA.BETTING.PREDICTION_SNAPSHOTS
        where game_pk in ({gks})
          and target = '{TARGET}'
          and model_version = '{MODEL_VERSION}'
        order by game_pk
    """
    cur = conn.cursor()
    cur.execute(sql)
    rows = cur.fetchall()
    return [
        {
            "game_pk": r[0],
            "stored_prediction": r[1],
            "feature_snapshot": json.loads(r[2]) if isinstance(r[2], str) else r[2],
            "model_artifact_s3_uri": r[3],
        }
        for r in rows
    ]


def fetch_asof_values(conn):
    """AS-OF SCD-2 query for weather, public_betting, and park at predicted_at."""
    gks = ", ".join(str(g) for g in GAME_PKS)
    ts = PREDICTED_AT
    sql = f"""
        with snapshots as (
            select game_pk, feature_snapshot
            from BASEBALL_DATA.BETTING.PREDICTION_SNAPSHOTS
            where game_pk in ({gks})
              and target = '{TARGET}'
              and model_version = '{MODEL_VERSION}'
        ),
        game_venues as (
            select game_pk, venue_id, game_year::integer as season
            from BASEBALL_DATA.BETTING.MART_GAME_RESULTS
            where game_pk in ({gks})
        ),
        weather_asof as (
            select w.game_pk, w.wind_component_mph, w.temp_f, w.humidity_pct
            from BASEBALL_DATA.BETTING_FEATURES.FEATURE_PREGAME_WEATHER_STATUS w
            where w.game_pk in ({gks})
              and w.valid_from <= '{ts}'::timestamp_ntz
              and (w.valid_to is null or w.valid_to > '{ts}'::timestamp_ntz)
        ),
        betting_asof as (
            select b.game_pk, b.home_ml_money_pct, b.over_money_pct
            from BASEBALL_DATA.BETTING_FEATURES.FEATURE_PREGAME_PUBLIC_BETTING_STATUS b
            where b.game_pk in ({gks})
              and b.valid_from <= '{ts}'::timestamp_ntz
              and (b.valid_to is null or b.valid_to > '{ts}'::timestamp_ntz)
        ),
        park_asof as (
            select gv.game_pk, p.elevation_ft, p.center_ft
            from game_venues gv
            join BASEBALL_DATA.BETTING_FEATURES.FEATURE_PREGAME_PARK_STATUS p
                on  p.venue_id = gv.venue_id
                and p.valid_from <= '{ts}'::timestamp_ntz
                and (p.valid_to is null or p.valid_to > '{ts}'::timestamp_ntz)
        )
        select
            s.game_pk,
            wa.wind_component_mph,
            s.feature_snapshot['wind_component_mph']::float  as snap_wind,
            wa.temp_f,
            s.feature_snapshot['temp_f']::float              as snap_temp,
            ba.home_ml_money_pct,
            s.feature_snapshot['home_ml_money_pct']::float   as snap_home_ml,
            ba.over_money_pct,
            s.feature_snapshot['over_money_pct']::float      as snap_over,
            pa.elevation_ft,
            s.feature_snapshot['elevation_ft']::float        as snap_elevation,
            pa.center_ft,
            s.feature_snapshot['center_ft']::float           as snap_center
        from snapshots s
        left join weather_asof wa  on wa.game_pk = s.game_pk
        left join betting_asof ba  on ba.game_pk = s.game_pk
        left join park_asof    pa  on pa.game_pk = s.game_pk
        order by s.game_pk
    """
    cur = conn.cursor()
    cur.execute(sql)
    return cur.fetchall()


def load_model_from_s3(s3_uri):
    """Load a pickle from s3://bucket/key."""
    # s3://baseball-betting-ml-artifacts/total_runs/ngboost_tuned_v2.pkl
    s3_uri = s3_uri.replace("s3://", "")
    bucket, key = s3_uri.split("/", 1)
    s3 = boto3.client("s3")
    obj = s3.get_object(Bucket=bucket, Key=key)
    return pickle.loads(obj["Body"].read())


def load_feature_columns():
    here = os.path.dirname(__file__)
    fc_path = os.path.join(here, "..", "model_artifacts", "feature_columns.json")
    with open(fc_path) as f:
        return json.load(f)


def build_feature_row(feature_snapshot, feature_columns):
    """Build a 1-row DataFrame in the exact column order the model expects."""
    row = {col: feature_snapshot.get(col, np.nan) for col in feature_columns}
    return pd.DataFrame([row])[feature_columns]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("=" * 60)
    print("Epic 15.9 — SCD-2 reconstruction validation")
    print("=" * 60)

    conn = get_conn()

    # ── Part 1: AS-OF feature comparison ───────────────────────────────────
    print("\n[1] AS-OF SCD-2 vs feature_snapshot comparison")
    print(f"    Predicted_at: {PREDICTED_AT}")
    print(f"    Game_pks:     {GAME_PKS}")

    rows = fetch_asof_values(conn)
    fields = [
        ("wind_component_mph", 0, 1),
        ("temp_f",             2, 3),
        ("home_ml_money_pct",  4, 5),
        ("over_money_pct",     6, 7),
        ("elevation_ft",       8, 9),
        ("center_ft",          10, 11),
    ]
    all_pass = True
    for row in rows:
        gk = row[0]
        for fname, scd2_idx, snap_idx in fields:
            scd2_val = row[scd2_idx + 1]
            snap_val = row[snap_idx + 1]
            match = (scd2_val is None and snap_val is None) or (
                scd2_val is not None
                and snap_val is not None
                and abs(float(scd2_val) - float(snap_val)) < 1e-6
            )
            status = "✓" if match else "✗"
            if not match:
                all_pass = False
            print(f"  game_pk={gk} {fname:30s} scd2={scd2_val} snap={snap_val} {status}")

    print(f"\n  Feature comparison: {'ALL PASS' if all_pass else 'FAILURES DETECTED'}")

    # ── Part 2: Prediction reconstruction ──────────────────────────────────
    print("\n[2] Model artifact prediction reconstruction (±0.001 tolerance)")

    snapshots = fetch_snapshots(conn)
    feature_columns = load_feature_columns()

    model = load_model_from_s3(snapshots[0]["model_artifact_s3_uri"])
    print(f"    Loaded model: {snapshots[0]['model_artifact_s3_uri']}")

    pred_pass = True
    for row in snapshots:
        X = build_feature_row(row["feature_snapshot"], feature_columns)
        # NGBoost dist.loc gives the predicted mean
        dist = model.pred_dist(X)
        reconstructed = float(dist.loc[0])
        stored = row["stored_prediction"]
        delta = abs(reconstructed - stored)
        match = delta <= TOLERANCE
        if not match:
            pred_pass = False
        status = "✓" if match else "✗"
        print(
            f"  game_pk={row['game_pk']}  stored={stored:.6f}  "
            f"reconstructed={reconstructed:.6f}  Δ={delta:.6f}  {status}"
        )

    print(f"\n  Prediction reconstruction: {'ALL PASS' if pred_pass else 'FAILURES DETECTED'}")

    conn.close()
    overall = all_pass and pred_pass
    print("\n" + ("=" * 60))
    print(f"OVERALL: {'PASS ✓' if overall else 'FAIL ✗'}")
    sys.exit(0 if overall else 1)


if __name__ == "__main__":
    main()
