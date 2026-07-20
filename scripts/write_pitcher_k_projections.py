"""write_pitcher_k_projections.py — Edge Program Story E5.5 daily K-PROJECTION writer.

Scores today's PROBABLE pitchers with the E5.2 served strikeout model (`strikeout_glm_v1`), joins the
live K-prop book lines (S3 props feed), and writes an honest model-vs-book PROJECTION payload to the
serving S3 prefix that the pitcher player page reads (DynamoDB serving cache → S3 fallback).

🔒 HONEST FRAMING (E5.5 crux): the payload is a PROJECTION + transparency comparison, NEVER a "+EV" /
bet recommendation — E5.4 proved no cashable edge (best_alpha=0). The user-facing prose + the no-bet-rec
posture are baked into `betting_ml.utils.k_projection_serving` (asserted by test_k_projection_serving.py).

TIER = WARN / ALERT-loud-but-continue (E11.7): peripheral, app-cosmetic. Any failure logs a WARNING to
stderr and the script exits 0 — it NEVER blocks predictions or serving. Mirrors the E13.10 zone-overlay
writer (`generate_zone_overlays_today.py`): write ONLY to the S3 serving prefix
  s3://baseball-betting-ml-artifacts/baseball/serving/pitcher_k_projection/as_of=<date>/<pitcher_id>.json
The backend endpoint tries today → yesterday → 2-days-ago, so writing at today's as-of date keeps a
just-played slate reachable without per-date keys.

DATA PATH — ⭐ SNOWFLAKE-FREE READS (E11.20 phase-2a, 2026-07-20). This writer fires from an HOURLY
host cron (capture.crontab, 13-23,0-4 UTC ≈ 15×/day), and every run used to open a Snowflake session
for the pregame frame + the cosmetic name/recent-K lookups. E11.20-COST proved ~80% of the warehouse
bill is WAKE/IDLE, not query compute, so a 24/7 hourly consumer is a top-tier waker regardless of how
cheap its queries are. All four reads now go to DuckDB over the S3 lakehouse:
  * served model bundle: S3 (load_artifact) → local fallback (gitignored .pkl).
  * pregame K feature frame for today's starters: ONE DuckDB query over the S3 lakehouse mirroring the
    E5.2 _FRAME_QUERY (trailing windows as-of the target date + the pregame signal/feature marts),
    concatenated with the cached historical frame so `build_predictors` derives league/EB/log5/framing
    exactly as at fit time.
  * pitcher names/teams/first-pitch + last-3-K context: DuckDB over the same lakehouse.
  * live K-prop lines: DuckDB over the S3 props parquet (mlb/props/market=pitcher_strikeouts/...).
The ONLY residual Snowflake touch is the starter_ip_v1 self-heal FALLBACK (see
_ensure_starter_ip_signal) — it fires only when today's signal is missing from S3, because that
signal store's writer is still a Snowflake MERGE. In the steady state this script opens no Snowflake
session at all.

⚠️ Lakehouse views are registered ONLY through betting_ml.utils.delta_lakehouse.register_lakehouse_views
— never a hardcoded `lakehouse/<t>/**/*.parquet` glob. Phase 1.5 deleted the compat parquet for the
Delta-migrated W1 marts, and a pinned glob is exactly what caused the 2026-07-20 P0 outage.

Usage:
    # daily (Dagster / cron — scores the current US baseball-day slate):
    uv run python scripts/write_pitcher_k_projections.py

    # specific date smoke test (no S3 writes):
    uv run python scripts/write_pitcher_k_projections.py --date 2026-06-27 --dry-run

This is a >1-min job (Snowflake frame + MC scoring) — HAND IT TO THE OPERATOR.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from betting_ml.utils.game_day import current_game_date_iso  # INC-22 — canonical US baseball-day
from betting_ml.utils import k_projection_serving as kps

_S3_BUCKET = "baseball-betting-ml-artifacts"
_S3_PROJECTION_PREFIX = "baseball/serving/pitcher_k_projection"
# Served bundle: S3 (promoted by the operator) → local fallback (gitignored).
_BUNDLE_S3 = f"s3://{_S3_BUCKET}/mlb/models/prop_pricing_v1/strikeout_glm_v1.pkl"
_BUNDLE_LOCAL = PROJECT_ROOT / "betting_ml" / "models" / "sub_models" / "prop_pricing_v1" / "strikeout_glm_v1.pkl"
_PROPS_GLOB = f"s3://{_S3_BUCKET}/mlb/props/market=pitcher_strikeouts/season=*/date={{date}}/data.parquet"
# Serving self-heal: the K projection hard-depends on TODAY's starter_ip_v1 signal, which the daily
# sub-model ops NEVER generate (they score only _recent_completed_dates() = T-2/T-1; today is excluded
# by design as it anchors the completed-game signal history). We regenerate it on demand — see
# _ensure_starter_ip_signal. The generator reads the pre-game feature_pregame_starter_features (present
# for today), so today is scorable despite having no completed pitch data.
_STARTER_IP_GEN = PROJECT_ROOT / "betting_ml" / "scripts" / "starter_v1" / "generate_starter_ip_signals.py"
_STARTER_IP_TABLE = "starter_ip_signals"          # lakehouse (S3) name — the read side
_STARTER_IP_MIRROR = PROJECT_ROOT / "scripts" / "export_w9_signals_to_s3.py"

# E5.2 served calib_80 (the calibration that makes the projection a product) — surfaced for context.
_CALIB_80 = 0.8104
_N_DRAWS = 10_000
_SEED = 7


def _warn(msg: str) -> None:
    """ALERT-loud-but-continue: every skip/failure is a stderr WARNING (never a silent pass)."""
    print(f"[k-projection][WARNING] {msg}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Today's pregame K-feature frame — mirrors fit_prop_pricing._FRAME_QUERY, as-of the target date.
# Trailing career/season counts use ONLY games strictly before the target date (leak-clean); the
# pregame signal/feature marts are joined at the target game_pk (they are pregame by construction).
# ---------------------------------------------------------------------------

# `?` = the target date, bound positionally FOUR times, in the order they appear below.
# NB on types (verified against the real parquet 2026-07-20): probable_pitchers.game_date and
# mart_starting_pitcher_game_log.game_date are real DATE columns (no INC-23 VARCHAR cast needed),
# but starter_ip_signals.GAME_PK is a VARCHAR (the W9 mirror's Snowflake typing) — hence the
# explicit ::bigint on that join key. DuckDB identifiers are case-insensitive, so the UPPERCASE
# column names in the W9/feature mirrors bind fine against the lowercase SQL below.
_TODAY_FRAME_QUERY = """
WITH starters AS (
    SELECT game_pk, game_date, side,
           CASE WHEN side = 'home' THEN TRUE ELSE FALSE END AS is_home_team,
           probable_pitcher_id AS pitcher_id
    FROM stg_statsapi_probable_pitchers
    WHERE game_date = ?::date
      AND probable_pitcher_id IS NOT NULL
),
-- Leak-clean trailing aggregates as-of the target date (strictly prior games only).
hist AS (
    SELECT pitcher_id,
           SUM(strikeouts)    AS k_career,
           SUM(batters_faced) AS bf_career,
           SUM(outs_recorded) AS outs_career
    FROM mart_starting_pitcher_game_log
    WHERE game_date < ?::date
      AND batters_faced >= 1 AND outs_recorded >= 1
    GROUP BY pitcher_id
),
hist_season AS (
    SELECT pitcher_id,
           SUM(strikeouts)    AS k_season,
           SUM(batters_faced) AS bf_season,
           SUM(outs_recorded) AS outs_season
    FROM mart_starting_pitcher_game_log
    WHERE game_date < ?::date
      AND game_year = year(?::date)
      AND batters_faced >= 1 AND outs_recorded >= 1
    GROUP BY pitcher_id
)
SELECT
    s.game_pk, s.game_date, year(s.game_date)::int AS game_year, s.pitcher_id, s.side, s.is_home_team,
    CAST(NULL AS DOUBLE) AS strikeouts, CAST(NULL AS DOUBLE) AS batters_faced,
    CAST(NULL AS DOUBLE) AS outs_recorded,
    h.k_career, h.bf_career, h.outs_career,
    hs.k_season, hs.bf_season, hs.outs_season,
    sig.starter_ip_mu, sig.starter_ip_dispersion,
    lf.avg_k_pct_30d AS opp_lineup_k_pct,
    CASE WHEN s.is_home_team THEN gf.home_catcher_framing_runs
         ELSE gf.away_catcher_framing_runs END AS catcher_framing_runs,
    sf.k_pct_7d, sf.k_pct_30d, sf.whiff_rate_30d, sf.csw_pct_3start,
    sf.velo_delta_3start, sf.fastball_velo_trend
FROM starters s
LEFT JOIN hist        h  ON h.pitcher_id  = s.pitcher_id
LEFT JOIN hist_season hs ON hs.pitcher_id = s.pitcher_id
LEFT JOIN starter_ip_signals sig
    ON sig.game_pk::bigint = s.game_pk AND sig.side = s.side AND sig.model_version = 'starter_ip_v1'
LEFT JOIN feature_pregame_lineup_features lf
    ON lf.game_pk = s.game_pk
   AND lf.side = CASE WHEN s.is_home_team THEN 'away' ELSE 'home' END
LEFT JOIN feature_pregame_game_features gf
    ON gf.game_pk = s.game_pk
LEFT JOIN feature_pregame_starter_features sf
    ON sf.game_pk = s.game_pk AND sf.side = s.side
ORDER BY s.game_pk, s.side
"""

_FRAME_TABLES = [
    "stg_statsapi_probable_pitchers",
    "mart_starting_pitcher_game_log",
    "starter_ip_signals",
    "feature_pregame_lineup_features",
    "feature_pregame_game_features",
    "feature_pregame_starter_features",
]

# Column order the historical cached frame uses — the today-frame is aligned to it before concat.
_FRAME_COLS = [
    "game_pk", "game_date", "game_year", "pitcher_id", "side", "is_home_team",
    "strikeouts", "batters_faced", "outs_recorded",
    "k_career", "bf_career", "outs_career", "k_season", "bf_season", "outs_season",
    "starter_ip_mu", "starter_ip_dispersion", "opp_lineup_k_pct", "catcher_framing_runs",
    "k_pct_7d", "k_pct_30d", "whiff_rate_30d", "csw_pct_3start", "velo_delta_3start", "fastball_velo_trend",
]


def _duck_lakehouse(tables: list[str]):
    """A DuckDB connection with the given lakehouse tables registered as bare-name views, routed
    per storage backend by the phase-1.5 Delta-aware registrar. NEVER build a raw parquet glob
    here — see the module docstring (the 2026-07-20 P0)."""
    from betting_ml.utils.delta_lakehouse import register_lakehouse_views
    from betting_ml.utils.lakehouse_monitor import duck

    conn = duck()
    register_lakehouse_views(conn, tables)
    return conn


def _load_today_frame(target: str) -> pd.DataFrame:
    """One DuckDB/S3 query: today's probable-pitcher pregame K-feature rows (mirrors _FRAME_QUERY)."""
    conn = _duck_lakehouse(_FRAME_TABLES)
    try:
        cur = conn.execute(_TODAY_FRAME_QUERY, [target, target, target, target])
        cols = [c[0].lower() for c in cur.description]
        rows = cur.fetchall()
    finally:
        conn.close()
    df = pd.DataFrame(rows, columns=cols)
    if df.empty:
        return df
    df["game_date"] = pd.to_datetime(df["game_date"], errors="coerce")
    for c in [c for c in df.columns if c not in ("side", "game_date")]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def _pitcher_meta(target: str, pitcher_ids: list[int]) -> dict[int, dict]:
    """Best-effort id → {full_name, team, opponent} for the panel header. Cosmetic — isolated in its
    own try so a column/name mismatch never kills the scoring path (the AC-critical part)."""
    meta: dict[int, dict] = {}
    if not pitcher_ids:
        return meta
    try:
        conn = _duck_lakehouse(["stg_statsapi_probable_pitchers", "stg_statsapi_games"])
        try:
            cur = conn.execute(
                """
                SELECT pp.probable_pitcher_id AS pid, pp.probable_pitcher_name AS nm,
                       pp.side AS side, g.home_team_name AS home_team, g.away_team_name AS away_team,
                       -- INC-23: in the lakehouse, stg_statsapi_games.game_date is an ISO VARCHAR
                       -- ('2026-07-20 23:07:00+00') — the binary-timestamp cure — NOT the Snowflake
                       -- TIMESTAMP_NTZ. Casting the string to a NAIVE ::timestamp drops the +00
                       -- offset and keeps the wall value (23:07), which is exactly the Snowflake NTZ
                       -- semantics this payload has always used: the instant is ALREADY UTC, so we
                       -- format as-is and stamp 'Z'. Do NOT cast to ::timestamptz and re-render —
                       -- that reinterprets it in the session TZ and shifts first pitch (the +7h
                       -- box-PT bug E5.5 already fixed once on the Snowflake side).
                       strftime(g.game_date::timestamp, '%Y-%m-%dT%H:%M:%SZ') AS game_dt
                FROM stg_statsapi_probable_pitchers pp
                LEFT JOIN stg_statsapi_games g ON g.game_pk = pp.game_pk
                WHERE pp.game_date = ?::date AND pp.probable_pitcher_id IS NOT NULL
                """,
                [target],
            )
            for r in cur.fetchall():
                pid, nm, side, home_team, away_team, game_dt = r
                is_home = (side == "home")
                team = home_team if is_home else away_team
                opp = away_team if is_home else home_team
                meta[int(pid)] = {"full_name": nm, "team": team, "opponent": opp,
                                  "game_datetime": str(game_dt) if game_dt else None}
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001 — cosmetic, never fatal
        _warn(f"pitcher meta join skipped (names/teams will be null): {exc}")
    return meta


def _recent_k(target: str, pitcher_ids: list[int]) -> dict[int, list[int]]:
    """{pitcher_id: [K, K, K]} — each pitcher's last 3 starts' strikeouts before the target date
    (most-recent first). Cosmetic matchup context; isolated try so it never breaks scoring."""
    out: dict[int, list[int]] = {}
    if not pitcher_ids:
        return out
    try:
        idlist = ",".join(str(int(p)) for p in pitcher_ids)
        conn = _duck_lakehouse(["mart_starting_pitcher_game_log"])
        try:
            cur = conn.execute(
                f"""
                SELECT pitcher_id, strikeouts FROM (
                    SELECT pitcher_id, strikeouts, game_date,
                           ROW_NUMBER() OVER (PARTITION BY pitcher_id ORDER BY game_date DESC) AS rn
                    FROM mart_starting_pitcher_game_log
                    WHERE game_date < ?::date AND batters_faced >= 1
                      AND pitcher_id IN ({idlist})
                ) WHERE rn <= 3
                ORDER BY pitcher_id, rn
                """,
                [target],
            )
            for pid, k in cur.fetchall():
                out.setdefault(int(pid), []).append(int(k) if k is not None else 0)
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001 — cosmetic, never fatal
        _warn(f"recent-K lookup skipped (last-3 K will be null): {exc}")
    return out


# ---------------------------------------------------------------------------
# Live K-prop book lines — DuckDB over the S3 props parquet (latest snapshot per book×player).
# ---------------------------------------------------------------------------

def _load_book_lines(target: str) -> dict[str, list[dict]]:
    """{normalized_player_name: [{book, line, over_odds, under_odds}, ...]} for the target date.

    Reads the S3 props parquet via DuckDB (credential_chain, us-east-2). Keeps the LATEST snapshot per
    (bookmaker, player). Fail-open: any error → {} (the projection still renders, sans book lines)."""
    from betting_ml.utils.prop_edge import normalize_name
    out: dict[str, list[dict]] = {}
    glob = _PROPS_GLOB.format(date=target)
    try:
        import duckdb
        con = duckdb.connect()
        con.execute("INSTALL httpfs; LOAD httpfs")
        con.execute("CREATE OR REPLACE SECRET s3lines (TYPE S3, PROVIDER credential_chain, REGION 'us-east-2')")
        rows = con.execute(
            f"""
            WITH ranked AS (
                SELECT player_name, bookmaker_key, line, over_price, under_price,
                       ROW_NUMBER() OVER (PARTITION BY bookmaker_key, player_name
                                          ORDER BY snapshot_ts DESC) AS rn
                FROM read_parquet('{glob}', hive_partitioning=1, union_by_name=true)
                WHERE line IS NOT NULL
            )
            SELECT player_name, bookmaker_key, line, over_price, under_price
            FROM ranked WHERE rn = 1
            """
        ).fetchall()
        con.close()
    except Exception as exc:  # noqa: BLE001 — fail-open
        _warn(f"book-line read skipped (fail-open, no lines): {exc}")
        return out
    for player_name, book, line, over_price, under_price in rows:
        key = normalize_name(player_name)
        if not key:
            continue
        out.setdefault(key, []).append({
            "book": book, "line": float(line),
            "over_odds": over_price, "under_odds": under_price,
        })
    return out


# ---------------------------------------------------------------------------
# Scoring — the E5.2 served bundle's serve recipe (mu → Poisson → scale_spread).
# ---------------------------------------------------------------------------

def _score_samples(bundle: dict, elig: pd.DataFrame, rng: np.random.Generator) -> np.ndarray:
    """(n_pitchers, n_draws) K-count samples via the served bundle recipe.

    serve: mu = clip(glm.predict(scaler.transform(impute(X[features]))), 0.3, None);
           K ~ Poisson(mu); scale_spread(K, spread_scale)."""
    from betting_ml.scripts.prop_pricing.bakeoff_strikeouts import _learned_matrix
    from betting_ml.utils.prop_pricing import scale_spread
    X, _ = _learned_matrix(elig, elig.index, bundle["impute"])
    mu = np.clip(bundle["model"].predict(bundle["scaler"].transform(X)), 0.3, None)
    n_draws = int(bundle.get("n_draws", _N_DRAWS))
    samp = rng.poisson(mu[:, None], size=(len(mu), n_draws)).astype(float)
    return scale_spread(samp, float(bundle["spread_scale"]))


def _load_bundle() -> dict | None:
    from betting_ml.utils.artifact_store import load_artifact
    for src in (_BUNDLE_S3, _BUNDLE_LOCAL):
        try:
            bundle = load_artifact(src)
            print(f"[k-projection] loaded served bundle from {src}")
            return bundle
        except Exception as exc:  # noqa: BLE001
            _warn(f"bundle load failed from {src}: {exc}")
    return None


def _s3_put(key: str, body: bytes) -> None:
    from scripts.utils.lakehouse_raw_writer import make_s3_client
    make_s3_client().put_object(Bucket=_S3_BUCKET, Key=key, Body=body, ContentType="application/json")


# DynamoDB serving cache = the PRIMARY read path (S3 is the fallback). Schema + region resolution
# mirror app/backend/services/serving_cache.py EXACTLY so the backend's get_cache_latest finds it.
# NB: the serving cache lives in AWS_REGION (default us-east-1) — NOT the S3 bucket's us-east-2.
_SERVING_CACHE_TABLE = os.getenv("SERVING_CACHE_TABLE", "credence-prod-serving-cache")
_SERVING_CACHE_REGION = os.getenv("AWS_REGION", "us-east-1")


def _ddb_put(pitcher_id: int, target: str, payload: dict) -> None:
    """Write the projection to the DynamoDB serving cache (primary path). Date-scoped (not permanent);
    the backend's get_cache_latest picks the newest by updated_at. Instance-role credential chain."""
    import boto3
    tbl = boto3.resource("dynamodb", region_name=_SERVING_CACHE_REGION).Table(_SERVING_CACHE_TABLE)
    tbl.put_item(Item={
        "pk": "pitcher_k_projection",
        "sk": f"{pitcher_id}#{target}",
        "value": json.dumps(payload, default=float),
        "is_permanent": False,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "cache_date": target,
    })


def _ddb_put_index(target: str, payload: dict) -> None:
    """Write the daily index blob to the serving cache (key `pitcher_k_projection/index`), read by the
    /projections list endpoint via get_cache_latest (newest index wins → robust to date rollover)."""
    import boto3
    tbl = boto3.resource("dynamodb", region_name=_SERVING_CACHE_REGION).Table(_SERVING_CACHE_TABLE)
    tbl.put_item(Item={
        "pk": "pitcher_k_projection",
        "sk": f"index#{target}",
        "value": json.dumps(payload, default=float),
        "is_permanent": False,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "cache_date": target,
    })


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _ensure_starter_ip_signal(target: str) -> None:
    """Serving self-heal for the K projection's hard dependency on the ``starter_ip_v1`` signal.

    The daily sub-model signal ops only score ``_recent_completed_dates()`` (T-2/T-1) — today is
    excluded by design (it anchors the *completed-game* signal history), and NOTHING else generates
    today's signal. But the K projection needs today's pre-game ``starter_ip`` to score today's
    starters, so without this the writer skips every day. Generate it on demand when the row count
    for ``target`` is zero (idempotent MERGE; ~1 row/starter). Reads ``feature_pregame_starter_features``,
    which is populated for today, so today is scorable. Covers BOTH the daily op and the hourly host
    cron (both invoke this script). Fail-soft: any error logs + returns so the writer still runs on
    whatever signal rows already exist.

    ⭐ E11.20 phase-2a — this is the ONE place the writer can still touch Snowflake, and ONLY on the
    miss branch. The PRESENCE CHECK now reads the S3 lakehouse mirror (the same parquet
    _load_today_frame joins), so the steady state — signal already present — is fully Snowflake-free.
    The generator itself still MERGEs into the Snowflake signal store (that store has no S3 writer;
    re-implementing MERGE-accumulate on parquet is out of scope), so after a successful regeneration
    we must RE-MIRROR it to S3 or the read below would still see nothing. That is the INC-25 ordering
    rule in miniature: a consumer cut over to an S3 mirror needs the mirror rebuilt downstream of the
    write, in the SAME run.
    """
    try:
        conn = _duck_lakehouse([_STARTER_IP_TABLE])
        try:
            (present,) = conn.execute(
                f"SELECT COUNT(*) FROM {_STARTER_IP_TABLE} "
                f"WHERE game_date = ?::date AND model_version = 'starter_ip_v1'",
                [target],
            ).fetchone()
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001
        _warn(f"[{target}] starter_ip presence check failed ({exc}); attempting generation anyway.")
        present = 0

    if present:
        print(f"[k-projection] starter_ip_v1 signal present for {target} ({present} rows) — no regen needed.")
        return

    # Match the schema the K writer READS (betting_features = prod); TARGET_ENV drives dev isolation.
    env = "prod" if os.getenv("TARGET_ENV") == "prod" else "dev"
    _warn(f"[{target}] starter_ip_v1 signal MISSING from the S3 mirror — falling back to the Snowflake "
          f"self-heal (generate + re-mirror, env={env}). A run that logs this is NOT Snowflake-free.")
    result = subprocess.run(
        [sys.executable, str(_STARTER_IP_GEN), "--date", target, "--env", env, "--s3"],
        capture_output=True, text=True, cwd=str(PROJECT_ROOT),
    )
    if result.returncode != 0:
        _warn(f"[{target}] starter_ip generation failed (exit {result.returncode}); K scoring may skip. "
              f"stderr: {result.stderr[-400:]}")
        return
    print(f"[k-projection] starter_ip_v1 signal generated for {target} — re-mirroring to S3 ...")
    mirror = subprocess.run(
        [sys.executable, str(_STARTER_IP_MIRROR), "--table", _STARTER_IP_TABLE],
        capture_output=True, text=True, cwd=str(PROJECT_ROOT),
    )
    if mirror.returncode != 0:
        _warn(f"[{target}] starter_ip S3 re-mirror failed (exit {mirror.returncode}) — the signal now "
              f"exists in Snowflake but NOT in the parquet this writer reads, so scoring will still "
              f"skip. stderr: {mirror.stderr[-400:]}")
    else:
        print(f"[k-projection] starter_ip_v1 signal mirrored to S3 for {target}.")


def _run_for_date(target: str, args, bundle: dict, hist: pd.DataFrame, build_predictors, rng) -> None:
    """Score + write the K-projection payloads for ONE target date. Fail-soft (WARN, returns) at
    every step so a bad date in a backfill loop never aborts the rest."""
    print(f"[k-projection] target date = {target}")

    # 0) Serving self-heal: today's starter_ip_v1 signal is never produced by the daily ops, so make
    #    sure it exists before the join in _load_today_frame. Skipped in dry-run (read-only).
    if not args.dry_run:
        _ensure_starter_ip_signal(target)

    # 1) Today's pregame feature rows.
    try:
        today = _load_today_frame(target)
    except Exception as exc:  # noqa: BLE001
        _warn(f"[{target}] today-frame query failed — skipped: {exc}")
        return
    if today.empty:
        _warn(f"[{target}] no probable pitchers (lineups not posted?) — skipped.")
        return
    print(f"[k-projection] {len(today)} probable starters for {target}")

    # 2) Concatenate with the cached historical frame so build_predictors derives league/EB/log5/framing
    #    exactly as at fit time (league_k_rate needs the prior completed season in the frame).
    try:
        frame = pd.concat([hist[_FRAME_COLS], today[_FRAME_COLS]], ignore_index=True)
        pred = build_predictors(frame, rate_mode="recency_blend")
    except Exception as exc:  # noqa: BLE001
        _warn(f"[{target}] feature derivation failed — skipped: {exc}")
        return

    # 3) The today rows (identified by null strikeouts) that have the workload signal needed to score.
    today_mask = pred["strikeouts"].isna() & pred["game_pk"].isin(today["game_pk"].tolist())
    elig = pred[today_mask].dropna(subset=["starter_ip_mu", "starter_ip_dispersion"]).reset_index(drop=True)
    if elig.empty:
        _warn(f"[{target}] no scorable starters (starter_ip_v1 signal missing) — skipped.")
        return

    samples = _score_samples(bundle, elig, rng)  # (n, n_draws)

    # 4) Live book lines + per-pitcher metadata + recent-form context.
    pids = elig["pitcher_id"].astype(int).tolist()
    book_lines_by_name = _load_book_lines(target)
    meta = _pitcher_meta(target, pids)
    last3_by_pid = _recent_k(target, pids)

    from betting_ml.utils.prop_edge import normalize_name
    from betting_ml.utils.totals_distribution import DEFAULT_QUANTILES, quantile_grid

    grids = quantile_grid(samples, DEFAULT_QUANTILES)  # (n, n_quantiles)
    written = 0
    index_rows: list[dict] = []
    for i in range(len(elig)):
        pid = int(elig["pitcher_id"].iloc[i])
        m = meta.get(pid, {})
        name = m.get("full_name")
        samp_i = samples[i]
        mean_i, std_i = float(samp_i.mean()), float(samp_i.std())
        lines = book_lines_by_name.get(normalize_name(name), []) if name else []
        comparisons = kps.comparison_from_samples(samp_i, lines, model_mean=mean_i)
        payload = kps.build_k_projection_payload(
            pitcher_id=pid, full_name=name, team=m.get("team"),
            game_pk=int(elig["game_pk"].iloc[i]),
            game_date=target, opponent=m.get("opponent"),
            game_datetime=m.get("game_datetime"), last3_k=last3_by_pid.get(pid),
            quantile_levels=DEFAULT_QUANTILES, k_quantile_grid=grids[i],
            mean=mean_i, std=std_i, calib_80=_CALIB_80,
            book_comparisons=comparisons, generated_at=f"{target}T00:00:00Z",
        )
        index_rows.append(kps.index_row(payload))
        if args.dry_run:
            print(f"  [dry-run] {pid} {name}: mean={mean_i:.2f} lines={len(lines)} "
                  f"primary={payload['primary_line']}")
            continue
        body = json.dumps(payload, default=float).encode()
        # PRIMARY: DynamoDB serving cache (non-fatal — S3 is the fallback the endpoint also reads).
        try:
            _ddb_put(pid, target, payload)
        except Exception as exc:  # noqa: BLE001
            _warn(f"DynamoDB write failed for pitcher {pid} (S3 fallback still covers): {exc}")
        # FALLBACK: S3 serving prefix.
        key = f"{_S3_PROJECTION_PREFIX}/as_of={target}/{pid}.json"
        try:
            _s3_put(key, body)
            written += 1
        except Exception as exc:  # noqa: BLE001
            _warn(f"S3 write failed for pitcher {pid}: {exc}")

    # Daily index blob — powers the /projections list page (one fetch for the whole slate).
    index_payload = kps.build_index_payload(index_rows, game_date=target,
                                            generated_at=f"{target}T00:00:00Z")
    if args.dry_run:
        print(f"[k-projection] dry-run complete — {len(elig)} starters scored, "
              f"index would list {index_payload['count']} (no writes).")
    else:
        index_body = json.dumps(index_payload, default=float).encode()
        try:
            _ddb_put_index(target, index_payload)
        except Exception as exc:  # noqa: BLE001
            _warn(f"DynamoDB index write failed (S3 fallback still covers): {exc}")
        try:
            _s3_put(f"{_S3_PROJECTION_PREFIX}/as_of={target}/index.json", index_body)
        except Exception as exc:  # noqa: BLE001
            _warn(f"S3 index write failed: {exc}")
        print(f"[k-projection] wrote {written}/{len(elig)} projections + index ({index_payload['count']}) → "
              f"s3://{_S3_BUCKET}/{_S3_PROJECTION_PREFIX}/as_of={target}/")


def main() -> int:
    ap = argparse.ArgumentParser(description="E5.5 — daily pitcher K-projection serving writer")
    ap.add_argument("--date", default=None, help="Target US baseball-day (YYYY-MM-DD); default = today.")
    ap.add_argument("--days-back", type=int, default=0,
                    help="Also write the N calendar days BEFORE --date (backfill; e.g. --date 2026-06-30 "
                         "--days-back 29 covers Jun 1–30). The history frame is loaded once and reused.")
    ap.add_argument("--min-year", type=int, default=2021, help="History floor for the league/EB context frame.")
    ap.add_argument("--dry-run", action="store_true", help="Score + print; do not write to S3/DynamoDB.")
    args = ap.parse_args()

    target = args.date or current_game_date_iso()
    rng = np.random.default_rng(_SEED)

    bundle = _load_bundle()
    if bundle is None:
        _warn("no served bundle available — nothing written (promote strikeout_glm_v1.pkl to S3).")
        return 0

    # Load the historical league/EB context frame ONCE (reused across every backfill date).
    try:
        from betting_ml.scripts.prop_pricing.fit_prop_pricing import build_predictors, load_frame_cached
        # use_s3: this writer must not open a Snowflake session. The cache is gitignored, so the
        # container starts EMPTY after every deploy — without this the very first hourly run of a
        # new image pulled the whole 2021-present windowed frame from the warehouse.
        hist = load_frame_cached(args.min_year, int(target[:4]), use_s3=True)
    except Exception as exc:  # noqa: BLE001
        _warn(f"history frame load failed — nothing written: {exc}")
        return 0

    base = date.fromisoformat(target)
    dates = [(base - timedelta(days=n)).isoformat() for n in range(max(args.days_back, 0) + 1)]
    if len(dates) > 1:
        print(f"[k-projection] backfill: {dates[-1]} … {dates[0]} ({len(dates)} dates)")
    for d in dates:
        _run_for_date(d, args, bundle, hist, build_predictors, rng)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 — WARN-tier: never block the pipeline.
        _warn(f"unhandled error — exiting 0 (peripheral writer): {exc}")
        sys.exit(0)
