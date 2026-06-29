"""
parity_check_w5b.py   (E11.1-W5b archetype mini-wave — TOLERANCE parity)
------------------------------------------------------------------------
The archetype chain is the program's ONLY tolerance-class wave: the posteriors are
Bayesian (Gaussian likelihood over k-means centroids), so the rolling-stat SQL's
float precision (Snowflake vs DuckDB) propagates through exp(-dist²) into cluster_probs
at ~1e-4, and the mart's adj_woba/adj_xwoba carry that into the 3rd decimal. Parity is
therefore TOLERANCE-based (bands + distribution + label-agreement), NOT row-exact — do
NOT reuse the W1–W5 row-exact MD5 gate here.

⚠️ RUN ORDER — run BEFORE flipping the W5b mart to a view (else tautological).

Two targets:
  --target mart        (default) mart_batter_archetype_vs_pitcher_cluster: DuckDB/S3 vs
                       Snowflake CTAS. If the S3 posteriors were SEEDED (one-time copy of
                       the Snowflake posteriors), the mart is near-EXACT (the soft-weight +
                       shrinkage SQL is deterministic over identical posteriors → the round(,3)
                       absorbs float wisps). If the posteriors were REBUILT on DuckDB
                       (compute_archetype_posteriors.py --s3), expect ~3rd-decimal drift.
  --target posteriors  mart_player_archetype_posteriors: the DuckDB --s3 build vs Snowflake.
                       Checks row count, MAP-cluster (argmax) agreement rate, and the entropy
                       / confidence distributions within bands.

Tolerance gates (mart):
  • row count: DuckDB >= Snowflake on completed dates (S3 pitch substrate ⊇ Snowflake = freshness).
  • grid: both expose the same set of (batter_cluster_label, pitcher_cluster_label) pairs.
  • joined-key value drift: for keys present in BOTH (by definition non-freshness),
      mean|Δadj_woba| <= 0.005  AND  fraction within 0.01 >= 0.99   (likewise adj_xwoba).
  • distribution: |Δ mean(adj_woba)| <= 0.003.

Run:
  uv run python scripts/run_w1_lakehouse.py --archetype      # writes the mart parquet to S3
  uv run python scripts/parity_check_w5b.py                  # mart tolerance parity
  uv run python scripts/parity_check_w5b.py --target posteriors
"""

import argparse
import os
import sys

import duckdb
import pandas as pd
import snowflake.connector
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    load_pem_private_key,
)
from dotenv import load_dotenv

load_dotenv()

_S3 = "s3://baseball-betting-ml-artifacts/baseball/lakehouse"
_SF = "BASEBALL_DATA.BETTING"

# Tolerance bands
_TOL_MEAN_ABS   = 0.005   # mean |Δ| on joined adj_woba / adj_xwoba
_TOL_WITHIN     = 0.01    # per-row band
_TOL_WITHIN_FRAC = 0.99   # fraction of joined rows that must fall within _TOL_WITHIN
_TOL_DIST_MEAN  = 0.003   # |Δ mean(adj_woba)| across the full marts
_TOL_MAP_AGREE  = 0.98    # posteriors MAP-cluster agreement rate


def _load_private_key():
    kp = os.getenv("SNOWFLAKE_PRIVATE_KEY_PATH")
    if not kp:
        return None
    raw = open(kp, "rb").read()
    ph = os.getenv("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE")
    k = load_pem_private_key(raw, password=ph.encode() if ph else None, backend=default_backend())
    return k.private_bytes(Encoding.DER, PrivateFormat.PKCS8, NoEncryption())


def get_sf():
    kw = dict(account=os.environ["SNOWFLAKE_ACCOUNT"], user=os.environ["SNOWFLAKE_USER"],
              warehouse=os.environ.get("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH"),
              role=os.environ.get("SNOWFLAKE_ROLE"), database="baseball_data", schema="betting")
    pk = _load_private_key()
    if pk:
        kw["private_key"] = pk
    else:
        kw["password"] = os.environ["SNOWFLAKE_PASSWORD"]
    return snowflake.connector.connect(**kw)


def get_duck():
    c = duckdb.connect()
    c.execute("INSTALL httpfs; LOAD httpfs")
    c.execute("CREATE OR REPLACE SECRET baseball_s3 (TYPE S3, PROVIDER credential_chain, REGION 'us-east-2')")
    for p in ("SET http_timeout=600000", "SET http_retries=8", "SET preserve_insertion_order=false"):
        try:
            c.execute(p)
        except Exception:
            pass
    return c


def _sf_df(sf, sql) -> pd.DataFrame:
    cur = sf.cursor()
    cur.execute(sql)
    df = pd.DataFrame(cur.fetchall(), columns=[d[0].lower() for d in cur.description])
    cur.close()
    return df


# ── Mart tolerance parity ─────────────────────────────────────────────────────

def check_mart(duck, sf) -> bool:
    model = "mart_batter_archetype_vs_pitcher_cluster"
    p = f"{_S3}/{model}/data.parquet"
    print(f"\n── {model}  (TOLERANCE parity) ──")
    ok = True

    duck_n = duck.execute(f"select count(*) from read_parquet('{p}')").fetchone()[0]
    sf_n = _sf_df(sf, f"select count(*) n from {_SF}.{model.upper()}")["n"][0]
    fresh_ok = duck_n >= sf_n * 0.999
    print(f"  rows   {'✅' if fresh_ok else '⚠️ '}  Snowflake={sf_n:,}  DuckDB={duck_n:,}  "
          f"(DuckDB ⊇ Snowflake expected — pitch-substrate freshness)")

    # Grid completeness
    duck_pairs = duck.execute(
        f"select count(distinct (batter_cluster_label, pitcher_cluster_label)) "
        f"from read_parquet('{p}')").fetchone()[0]
    sf_pairs = _sf_df(sf, f"select count(distinct batter_cluster_label || '|' || pitcher_cluster_label) n "
                          f"from {_SF}.{model.upper()}")["n"][0]
    grid_ok = duck_pairs == sf_pairs
    print(f"  grid   {'✅' if grid_ok else '❌'}  label-pairs  Snowflake={sf_pairs}  DuckDB={duck_pairs}")
    ok = ok and grid_ok

    # Joined-key value drift (keys in BOTH = non-freshness rows)
    sf_df = _sf_df(sf, f"select batter_cluster_label b, pitcher_cluster_label p, "
                       f"game_date::varchar gd, adj_woba, adj_xwoba from {_SF}.{model.upper()}")
    duck.register("sf_mart", sf_df)
    j = duck.execute(f"""
        select count(*) n,
               avg(abs(d.adj_woba - s.adj_woba))  m_woba,
               max(abs(d.adj_woba - s.adj_woba))  x_woba,
               avg(abs(d.adj_xwoba - s.adj_xwoba)) m_xwoba,
               avg(case when abs(d.adj_woba - s.adj_woba) <= {_TOL_WITHIN} then 1.0 else 0 end) frac_woba
        from read_parquet('{p}') d
        join sf_mart s
          on d.batter_cluster_label=s.b and d.pitcher_cluster_label=s.p and d.game_date::varchar=s.gd
    """).fetchone()
    n, m_woba, x_woba, m_xwoba, frac = j
    val_ok = (m_woba is not None and m_woba <= _TOL_MEAN_ABS and frac >= _TOL_WITHIN_FRAC)
    print(f"  value  {'✅' if val_ok else '❌'}  joined={n:,}  mean|Δadj_woba|={m_woba:.5f} (≤{_TOL_MEAN_ABS}) "
          f"max={x_woba:.5f}  within{_TOL_WITHIN}={frac:.3%} (≥{_TOL_WITHIN_FRAC:.0%})  mean|Δadj_xwoba|={m_xwoba:.5f}")
    ok = ok and val_ok

    # Distribution
    d_mean = duck.execute(f"select avg(adj_woba) from read_parquet('{p}')").fetchone()[0]
    s_mean = _sf_df(sf, f"select avg(adj_woba) m from {_SF}.{model.upper()}")["m"][0]
    dist_ok = abs(float(d_mean) - float(s_mean)) <= _TOL_DIST_MEAN
    print(f"  dist   {'✅' if dist_ok else '❌'}  mean(adj_woba)  Snowflake={float(s_mean):.4f}  "
          f"DuckDB={float(d_mean):.4f}  |Δ|={abs(float(d_mean)-float(s_mean)):.4f} (≤{_TOL_DIST_MEAN})")
    ok = ok and dist_ok
    return ok


# ── Posteriors tolerance parity ───────────────────────────────────────────────

def check_posteriors(duck, sf) -> bool:
    model = "mart_player_archetype_posteriors"
    p = f"{_S3}/{model}/data.parquet"
    print(f"\n── {model}  (TOLERANCE parity) ──")
    ok = True

    duck_n = duck.execute(f"select count(*) from read_parquet('{p}')").fetchone()[0]
    sf_n = _sf_df(sf, f"select count(*) n from {_SF}.{model.upper()}")["n"][0]
    fresh_ok = duck_n >= sf_n * 0.999
    print(f"  rows   {'✅' if fresh_ok else '⚠️ '}  Snowflake={sf_n:,}  DuckDB={duck_n:,}")

    # MAP-cluster agreement on the shared PK (player_id, player_type, season, as_of_date)
    sf_df = _sf_df(sf, f"select player_id, player_type, season, as_of_date::varchar ad, "
                       f"map_cluster, cluster_entropy, assignment_confidence from {_SF}.{model.upper()}")
    duck.register("sf_post", sf_df)
    j = duck.execute(f"""
        select count(*) n,
               avg(case when d.map_cluster = s.map_cluster then 1.0 else 0 end) agree,
               avg(abs(d.cluster_entropy - s.cluster_entropy)) m_ent,
               avg(abs(d.assignment_confidence - s.assignment_confidence)) m_conf
        from read_parquet('{p}') d
        join sf_post s
          on d.player_id=s.player_id and d.player_type=s.player_type
         and d.season=s.season and d.as_of_date::varchar=s.ad
    """).fetchone()
    n, agree, m_ent, m_conf = j
    agree_ok = agree is not None and agree >= _TOL_MAP_AGREE
    print(f"  map    {'✅' if agree_ok else '❌'}  joined={n:,}  MAP-cluster agreement={agree:.3%} "
          f"(≥{_TOL_MAP_AGREE:.0%})  mean|Δentropy|={m_ent:.5f}  mean|Δconfidence|={m_conf:.5f}")
    ok = ok and agree_ok
    return ok


def main():
    ap = argparse.ArgumentParser(description="E11.1-W5b tolerance parity (archetype)")
    ap.add_argument("--target", choices=["mart", "posteriors"], default="mart")
    args = ap.parse_args()

    duck = get_duck()
    sf = get_sf()
    ok = check_mart(duck, sf) if args.target == "mart" else check_posteriors(duck, sf)
    sf.close()
    duck.close()

    print("\n── Summary ──")
    if ok:
        print(f"✅ {args.target} within tolerance — safe to create external table + flip to view.")
    else:
        print(f"❌ {args.target} OUTSIDE tolerance bands — investigate before cutover.")
        sys.exit(1)


if __name__ == "__main__":
    main()
