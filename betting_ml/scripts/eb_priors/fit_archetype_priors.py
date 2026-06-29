"""
fit_archetype_priors.py — Dirichlet prior fitting over archetype membership (Epic 7A.1)

Fits one symmetric Dirichlet(α) concentration vector per population × age band,
where α is proportional to the empirical cluster fraction in that band scaled by
a band-level total concentration hyperparameter:

    Population:  batters  (5 clusters: groundball_speed, high_whiff, contact_spray,
                                        patient_obp, power_pull)
                 pitchers (5 clusters: changeup_deceptive, multi_pitch_mix,
                                        power_swing_and_miss, contact_sinker_ball,
                                        soft_command)

    Age bands (player age at the START of the target season):
        u24 : < 24   → total_alpha = 5   (widest prior — high rookie uncertainty)
        a24 : 24–27  → total_alpha = 15  (moderate)
        a28 : 28+    → total_alpha = 30  (strong prior toward established cluster)

    Peaked variant (for players with confirmed prior-season label):
        The known cluster's α_k = 0.8 × total_alpha; remaining 20% split uniformly.

Output is written to:
    betting_ml/models/eb_priors/archetype_priors.json

Usage:
    uv run python betting_ml/scripts/eb_priors/fit_archetype_priors.py
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime
from pathlib import Path

import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.utils.data_loader import get_snowflake_connection

# ── Constants ─────────────────────────────────────────────────────────────────

_FIRST_SEASON = 2015

_AGE_BANDS = [
    ("u24", None, 23),   # age < 24
    ("a24", 24,   27),   # 24 ≤ age ≤ 27
    ("a28", 28,  999),   # age ≥ 28
]

_TOTAL_ALPHA = {"u24": 5, "a24": 15, "a28": 30}

_BATTER_CLUSTERS = [
    "groundball_speed",
    "high_whiff",
    "contact_spray",
    "patient_obp",
    "power_pull",
]

_PITCHER_CLUSTERS = [
    "changeup_deceptive",
    "multi_pitch_mix",
    "power_swing_and_miss",
    "contact_sinker_ball",
    "soft_command",
]

_MIN_CELL_PLAYERS = 20  # fallback threshold

_OUTPUT_PATH = _PROJECT_ROOT / "betting_ml" / "models" / "eb_priors" / "archetype_priors.json"


# ── E11.1-W7a lakehouse: read-on-DuckDB ───────────────────────────────────────
# `--s3` repoints the cluster + player-profile reads at S3 parquet via DuckDB so the prior fit
# runs off-Snowflake. There is no Snowflake write (output is the local JSON), so --s3 is a pure
# read-side swap.
_S3_BUCKET = "baseball-betting-ml-artifacts"
_LAKEHOUSE = f"s3://{_S3_BUCKET}/baseball/lakehouse"

_S3_SOURCE_TABLES = [
    "batter_clusters",
    "pitcher_clusters",
    "stg_statsapi_player_profiles",
]


def _get_duckdb():
    import duckdb
    duck = duckdb.connect()
    duck.execute("INSTALL httpfs; LOAD httpfs")
    duck.execute(
        "CREATE OR REPLACE SECRET baseball_s3 "
        "(TYPE S3, PROVIDER credential_chain, REGION 'us-east-2')"
    )
    for _p in ("SET http_timeout=600000", "SET http_retries=8",
               "SET preserve_insertion_order=false"):
        try:
            duck.execute(_p)
        except Exception:
            pass
    return duck


def _register_s3_views(duck) -> None:
    for name in _S3_SOURCE_TABLES:
        glob = f"{_LAKEHOUSE}/{name}/**/*.parquet"
        duck.execute(
            f"CREATE OR REPLACE VIEW {name} AS "
            f"SELECT * FROM read_parquet('{glob}', union_by_name=true)"
        )


def _duck_sql_for(sql: str) -> str:
    """Rewrite the cluster/profile Snowflake source queries for DuckDB: bare-name views.
    The %(first_season)s param is substituted as a literal int by the caller. No date logic
    crosses an engine boundary here (season is INT), so no game_date casts are needed."""
    s = sql
    s = s.replace("baseball_data.statsapi.batter_clusters", "batter_clusters")
    s = s.replace("baseball_data.statsapi.pitcher_clusters", "pitcher_clusters")
    s = s.replace("baseball_data.betting.stg_statsapi_player_profiles", "stg_statsapi_player_profiles")
    return s


def _fetch_rows(conn, sql: str, params: dict, duck=None) -> list[dict]:
    # E11.1-W7a: --s3 reads from S3 parquet via DuckDB (named param substituted as literal int).
    if duck is not None:
        s = _duck_sql_for(sql).replace("%(first_season)s", str(int(params["first_season"])))
        cur = duck.execute(s)
        cols = [d[0].lower() for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    cur = conn.cursor()
    cur.execute(sql, params)
    cols = [d[0].lower() for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    cur.close()
    return rows


# ── Age band helpers ──────────────────────────────────────────────────────────

def _age_at_season_start(birth_date_val, season: int) -> int | None:
    if not birth_date_val:
        return None
    try:
        if isinstance(birth_date_val, date):
            bd = birth_date_val
        else:
            bd = datetime.strptime(str(birth_date_val)[:10], "%Y-%m-%d").date()
        season_start = date(season, 4, 1)  # approximate: Opening Day is early April
        return (season_start - bd).days // 365
    except (ValueError, TypeError):
        return None


def _age_band(age: int | None) -> str | None:
    if age is None:
        return None
    for label, lo, hi in _AGE_BANDS:
        lo_ok = (lo is None) or (age >= lo)
        hi_ok = age <= hi
        if lo_ok and hi_ok:
            return label
    return "a28"


# ── Data loading ──────────────────────────────────────────────────────────────

_BATTER_ROWS_SQL = """
        SELECT
            bc.batter_id   AS player_id,
            bc.season,
            bc.cluster_label,
            pp.birth_date
        FROM baseball_data.statsapi.batter_clusters bc
        LEFT JOIN baseball_data.betting.stg_statsapi_player_profiles pp
            ON pp.player_id = bc.batter_id
        WHERE bc.season >= %(first_season)s
        ORDER BY bc.season, bc.batter_id
        """

_PITCHER_ROWS_SQL = """
        SELECT
            pc.pitcher_id  AS player_id,
            pc.season,
            pc.cluster_label,
            pp.birth_date
        FROM baseball_data.statsapi.pitcher_clusters pc
        LEFT JOIN baseball_data.betting.stg_statsapi_player_profiles pp
            ON pp.player_id = pc.pitcher_id
        WHERE pc.season >= %(first_season)s
        ORDER BY pc.season, pc.pitcher_id
        """


def _load_batter_rows(conn, duck=None) -> list[dict]:
    rows = _fetch_rows(conn, _BATTER_ROWS_SQL, {"first_season": _FIRST_SEASON}, duck=duck)
    for r in rows:
        age = _age_at_season_start(r.get("birth_date"), int(r["season"]))
        r["age"] = age
        r["age_band"] = _age_band(age)
    return rows


def _load_pitcher_rows(conn, duck=None) -> list[dict]:
    rows = _fetch_rows(conn, _PITCHER_ROWS_SQL, {"first_season": _FIRST_SEASON}, duck=duck)
    for r in rows:
        age = _age_at_season_start(r.get("birth_date"), int(r["season"]))
        r["age"] = age
        r["age_band"] = _age_band(age)
    return rows


# ── Prior fitting ─────────────────────────────────────────────────────────────

def _fit_dirichlet_prior(
    rows: list[dict],
    cluster_labels: list[str],
    band: str,
) -> dict:
    """
    Fit a symmetric Dirichlet(α) for a given population × age band.

    alpha_k = total_alpha × (empirical fraction of cluster k in this band).

    Returns a dict with:
        alpha       : {cluster_label: alpha_k, ...}
        total_alpha : sum of all alpha_k
        n_players   : number of player-seasons in this cell
        fallback    : True if cell was too small (used pooled fractions)
    """
    total_alpha = _TOTAL_ALPHA[band]
    band_rows = [r for r in rows if r.get("age_band") == band]
    n = len(band_rows)

    if n >= _MIN_CELL_PLAYERS:
        fracs = _empirical_fractions(band_rows, cluster_labels)
        fallback = False
    else:
        # Fall back to pooled fractions across all age bands
        fracs = _empirical_fractions(rows, cluster_labels)
        fallback = True

    alpha = {k: round(total_alpha * fracs[k], 4) for k in cluster_labels}
    return {
        "alpha": alpha,
        "total_alpha": total_alpha,
        "n_players": n,
        "fallback": fallback,
    }


def _empirical_fractions(rows: list[dict], cluster_labels: list[str]) -> dict[str, float]:
    counts = {k: 0 for k in cluster_labels}
    total = 0
    for r in rows:
        label = r.get("cluster_label")
        if label in counts:
            counts[label] += 1
            total += 1
    if total == 0:
        uniform = 1.0 / len(cluster_labels)
        return {k: uniform for k in cluster_labels}
    return {k: counts[k] / total for k in cluster_labels}


def _fit_peaked_dirichlet(
    base_prior: dict,
    confirmed_cluster: str,
    cluster_labels: list[str],
    total_alpha: int,
) -> dict:
    """
    Peaked Dirichlet for a player with a confirmed prior-season cluster label.
    Confirmed cluster gets 80% of total_alpha; remaining 20% split uniformly.

    Returns alpha dict only (caller wraps it).
    """
    k = len(cluster_labels)
    peak = 0.8 * total_alpha
    remaining = 0.2 * total_alpha
    uniform_share = remaining / max(k - 1, 1)
    alpha = {}
    for label in cluster_labels:
        if label == confirmed_cluster:
            alpha[label] = round(peak, 4)
        else:
            alpha[label] = round(uniform_share, 4)
    return alpha


def _build_population_priors(
    rows: list[dict],
    cluster_labels: list[str],
    population: str,
) -> dict:
    """
    Build the full prior structure for one population (batters or pitchers).
    Returns:
        base_prior  : {age_band: {alpha, total_alpha, n_players, fallback}}
        peaked_rule : description of peaked Dirichlet rule for runtime use
    """
    base: dict = {}
    for band_label, _, _ in _AGE_BANDS:
        prior = _fit_dirichlet_prior(rows, cluster_labels, band_label)
        base[band_label] = prior
        fb_str = " [FALLBACK]" if prior["fallback"] else ""
        print(
            f"  {population:8s}  {band_label:4s}  n={prior['n_players']:4d}  "
            f"total_α={prior['total_alpha']:2d}  "
            + "  ".join(f"{k}={v:.3f}" for k, v in prior["alpha"].items())
            + fb_str
        )

    # Peaked rule: stored as a parameterized template (applied at runtime in 7A.2)
    peaked_rule = {
        "description": (
            "For players with a confirmed prior-season cluster label (≥ 100 PA/starts): "
            "confirmed cluster α_k = 0.8 × total_alpha; remaining 20% split uniformly. "
            "Apply _fit_peaked_dirichlet() at runtime in compute_archetype_posteriors.py."
        ),
        "peak_fraction": 0.8,
        "uniform_fraction": 0.2,
        "example": {
            band_label: {
                "confirmed_cluster": cluster_labels[0],
                "alpha": _fit_peaked_dirichlet(
                    base[band_label],
                    cluster_labels[0],
                    cluster_labels,
                    _TOTAL_ALPHA[band_label],
                ),
            }
            for band_label, _, _ in _AGE_BANDS
        },
    }
    return {"base_prior": base, "peaked_rule": peaked_rule}


# ── Sanity checks ─────────────────────────────────────────────────────────────

def _sanity_check_population(pop_priors: dict, population: str) -> None:
    """
    Verify:
    1. All alpha vectors sum to total_alpha (within floating-point tolerance).
    2. u24 total_alpha < a24 total_alpha < a28 total_alpha (concentration ordering).
    3. Peaked examples sum to total_alpha.
    """
    base = pop_priors["base_prior"]
    peaked_rule = pop_priors["peaked_rule"]

    # 1. Alpha sum check
    for band, cell in base.items():
        alpha_sum = sum(cell["alpha"].values())
        expected = cell["total_alpha"]
        diff = abs(alpha_sum - expected)
        if diff > 0.01:
            print(
                f"  WARNING [{population} {band}]: alpha sum {alpha_sum:.4f} ≠ "
                f"total_alpha {expected}"
            )
        else:
            print(f"  OK [{population} {band}]: alpha sum = {alpha_sum:.4f}")

    # 2. Concentration ordering
    ta = {b: base[b]["total_alpha"] for b, _, _ in _AGE_BANDS}
    bands = [b for b, _, _ in _AGE_BANDS]
    for i in range(len(bands) - 1):
        if ta[bands[i]] >= ta[bands[i + 1]]:
            print(
                f"  WARNING [{population}]: total_alpha ordering violated: "
                f"{bands[i]}={ta[bands[i]]} ≥ {bands[i+1]}={ta[bands[i+1]]}"
            )

    # 3. Peaked example sum
    for band, ex in peaked_rule["example"].items():
        peaked_sum = sum(ex["alpha"].values())
        expected = _TOTAL_ALPHA[band]
        diff = abs(peaked_sum - expected)
        if diff > 0.01:
            print(
                f"  WARNING [{population} {band} peaked]: alpha sum "
                f"{peaked_sum:.4f} ≠ {expected}"
            )


# ── Output ────────────────────────────────────────────────────────────────────

def _write_json(payload: dict) -> None:
    _OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    _OUTPUT_PATH.write_text(json.dumps(payload, indent=2))
    print(f"\nWritten → {_OUTPUT_PATH.relative_to(_PROJECT_ROOT)}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Fit Dirichlet archetype priors (Epic 7A.1)")
    parser.add_argument("--s3", action="store_true",
                        help="E11.1-W7a: read cluster + player-profile tables from S3 parquet "
                             "via DuckDB (no Snowflake). Output JSON path is unchanged.")
    args = parser.parse_args()

    conn = None
    duck = None
    if args.s3:
        print("[--s3] Reading cluster/profile tables from S3 lakehouse via DuckDB...")
        duck = _get_duckdb()
        _register_s3_views(duck)
    else:
        conn = get_snowflake_connection()
    try:
        print(f"Loading batter cluster assignments ({_FIRST_SEASON}+)...")
        batter_rows = _load_batter_rows(conn, duck=duck)
        print(f"  {len(batter_rows)} batter-season rows loaded")

        print(f"\nLoading pitcher cluster assignments ({_FIRST_SEASON}+)...")
        pitcher_rows = _load_pitcher_rows(conn, duck=duck)
        print(f"  {len(pitcher_rows)} pitcher-season rows loaded")

        missing_age = sum(1 for r in batter_rows if r["age_band"] is None)
        if missing_age:
            print(
                f"\n  NOTE: {missing_age} batter-season rows have no birth_date "
                f"in player_profiles — excluded from age-band cells (contribute to "
                f"pooled fallback fractions only)"
            )
        missing_age_p = sum(1 for r in pitcher_rows if r["age_band"] is None)
        if missing_age_p:
            print(
                f"  NOTE: {missing_age_p} pitcher-season rows have no birth_date — "
                f"excluded from age-band cells"
            )

        print("\n── Fitting batter priors ────────────────────────────────────")
        batter_priors = _build_population_priors(batter_rows, _BATTER_CLUSTERS, "batter")

        print("\n── Fitting pitcher priors ───────────────────────────────────")
        pitcher_priors = _build_population_priors(pitcher_rows, _PITCHER_CLUSTERS, "pitcher")

        print("\n── Sanity checks ────────────────────────────────────────────")
        _sanity_check_population(batter_priors, "batter")
        _sanity_check_population(pitcher_priors, "pitcher")

        payload = {
            "fit_date": date.today().isoformat(),
            "first_season": _FIRST_SEASON,
            "age_bands": {
                label: {"lo": lo, "hi": hi}
                for label, lo, hi in _AGE_BANDS
            },
            "total_alpha_by_band": _TOTAL_ALPHA,
            "batter_clusters": _BATTER_CLUSTERS,
            "pitcher_clusters": _PITCHER_CLUSTERS,
            "batters": batter_priors,
            "pitchers": pitcher_priors,
        }
        _write_json(payload)

    finally:
        if conn is not None:
            conn.close()
        if duck is not None:
            duck.close()


if __name__ == "__main__":
    main()
