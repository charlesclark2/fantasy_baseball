"""write_batter_tb_projections.py — Edge Program Story E5.9 daily batter TOTAL-BASES writer.

Scores today's market-quoted batters with the Phase-2 TB champion (`batter_tb_glm_nb_v1` —
Poisson-GLM mean + fitted NB2 dispersion; see ablation_results/mlb_batter_props_phase2_readout.md)
and writes the per-batter-game TB distribution + a model-vs-book transparency comparison to the
serving store (DynamoDB serving cache primary, S3 fallback) that the /props page reads. The
batter-side analog of E5.5's write_pitcher_k_projections.py.

🔒 HONEST FRAMING (E5.9 crux, best_alpha=0): a PROJECTION + calibration/transparency surface,
NEVER a bet recommendation. The strongest allowed claim is per-row calibration vs the de-vigged
closing consensus (6/6 folds on Brier); no edge/EV/win-rate framing anywhere. Market-blind: book
prices never enter the model — the design matrix is built ONLY through the Phase-2 harness's
`build_design` on the pre-registered feature contract.

⭐ TRAIN/SERVE CONSISTENCY (the E7.9 class — where this story's 🟥 runtime gate lives):
the Phase-2 substrate is a one-shot research artifact; this writer rebuilds the SAME feature
contract daily from the live marts. Every semantic is either IMPORTED from the substrate
builder (`build_rolling_features` — the switch-hitter hand-collapse; the `_name_key`/`_li_key`
quote-folded name keys) or from the Phase-2 harness (`build_design`, `nb_pmf_grid`), and
`--consistency-check --date <historical>` proves the live-mart feature path reproduces the
substrate's features row-for-row (run it on the box/laptop as the runtime-gate evidence).

Serving semantics vs training (documented deltas — see also the consistency check's output):
  * prev_* rolling features = the batter's LATEST completed game strictly BEFORE the target
    date (the mart's windows are inclusive-of-that-game, so its last completed row IS the
    lag-one value). KNOWN GAP: for game 2 of a doubleheader, training's lag saw game 1 of the
    same day; the daily mart cannot (it rebuilds nightly), so a DH game 2 serves the same
    features as game 1 (~1-2% of rows). The consistency check excludes same-date DH rows.
  * batter_hand = the latest completed game's collapsed hand (training used the labelled
    game's realized hand; identical except for switch-hitters mid-game — reported, not fatal).
  * REGULAR SEASON ONLY: non-'R' games are skipped loudly (the model is a regular-season fit;
    a postseason slate is an extrapolation and is not served).

Population: batters with a live TB book line for the target date (the market-selected
population the model was TRAINED on), resolved name→id via the substrate's two-tier keys and
arbitrated pregame by lineup membership (stg_statsapi_lineups_wide) or EB-posterior presence —
the appearance arbitration the substrate used is impossible pregame, so an ambiguous name with
no lineup yet is HELD for the next hourly run, never guessed.

TIER = WARN / ALERT-loud-but-continue (E11.7): peripheral, app-cosmetic. Any failure logs a
WARNING to stderr and exits 0 — it NEVER blocks predictions or serving.

DATA PATH — Snowflake-free: every read is DuckDB over S3. Lakehouse views are registered ONLY
through betting_ml.utils.delta_lakehouse.register_lakehouse_views (never a hardcoded
`lakehouse/<t>/**/*.parquet` glob — the phase-1.5 P0); the live TB lines come from the
mlb/props S3 feed (the hourly `--mode live` capture, see capture.crontab).

Usage:
    # daily (Dagster op / hourly host cron — scores the current US baseball-day slate):
    uv run python scripts/write_batter_tb_projections.py

    # specific date smoke (no writes):
    uv run python scripts/write_batter_tb_projections.py --date 2026-08-13 --dry-run

    # E7.9 train/serve consistency check against the research substrate (runtime gate):
    uv run python scripts/write_batter_tb_projections.py --consistency-check --date 2026-08-05
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date as _date
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from betting_ml.utils.game_day import current_game_date_iso  # noqa: E402 — INC-22 canonical day
from betting_ml.utils import tb_projection_serving as tbs  # noqa: E402
from betting_ml.scripts.batter_props_phase2_bakeoff import (  # noqa: E402
    NUMERIC_FEATURES,
    Design,
    build_design,
    nb_pmf_grid,
)
from scripts.build_batter_prop_substrate import (  # noqa: E402 — the substrate's own folding
    FIRST_PITCH_TOLERANCE_MIN,
    _li_key,
    _name_key,
    build_rolling_features,
)

_S3_BUCKET = "baseball-betting-ml-artifacts"
_S3_PROJECTION_PREFIX = "baseball/serving/batter_tb_projection"
_BUNDLE_S3 = f"s3://{_S3_BUCKET}/mlb/models/prop_pricing_v1/{tbs.MODEL_VERSION}.pkl"
_BUNDLE_LOCAL = (PROJECT_ROOT / "betting_ml" / "models" / "sub_models" / "prop_pricing_v1"
                 / f"{tbs.MODEL_VERSION}.pkl")
_PROPS_GLOB = f"s3://{_S3_BUCKET}/mlb/props/market=batter_total_bases/season=*/date={{date}}/data.parquet"
_SUBSTRATE_DEFAULT = (f"s3://{_S3_BUCKET}/baseball/research/batter_prop_substrate/"
                      "batter_prop_substrate_v1.parquet")

_QUANTILES = tuple(round(q, 2) for q in np.arange(0.05, 0.96, 0.05))  # P05..P95, 19 levels

_LAKEHOUSE_TABLES = [
    "stg_statsapi_games",
    "dim_team_name_lookup",
    "stg_ref_players",
    "stg_statsapi_lineups_wide",
    "eb_batter_posteriors_raw",
    "mart_batter_rolling_stats",
    "mart_park_factors_granular",
]


def _warn(msg: str) -> None:
    """ALERT-loud-but-continue: every skip/failure is a stderr WARNING (never a silent pass)."""
    print(f"[tb-projection][WARNING] {msg}", file=sys.stderr)


def _duck_lakehouse(tables: list[str]):
    """DuckDB connection with lakehouse tables as bare-name views, routed per storage backend.
    NEVER a raw parquet glob here — the phase-1.5 rule (see module docstring)."""
    from betting_ml.utils.delta_lakehouse import register_lakehouse_views
    from betting_ml.utils.lakehouse_monitor import duck

    conn = duck()
    register_lakehouse_views(conn, tables)
    return conn


# ---------------------------------------------------------------------------
# Bundle
# ---------------------------------------------------------------------------

def _load_bundle(target: str) -> tuple[dict, Design] | None:
    """Load the served TB bundle (S3 → local fallback) and reconstruct the fit-time Design.

    The Design (train medians / mean / std) is the fit-time standardization state — rebuilding
    it from anything else is the E7.9 train/serve-mismatch class, so it ships IN the bundle."""
    from betting_ml.utils.artifact_store import load_artifact
    bundle = None
    for src in (_BUNDLE_S3, str(_BUNDLE_LOCAL)):
        try:
            bundle = load_artifact(src)
            print(f"[tb-projection] loaded served bundle from {src}")
            break
        except Exception as exc:  # noqa: BLE001
            _warn(f"bundle load failed from {src}: {exc}")
    if bundle is None:
        return None
    if bundle.get("model_version") != tbs.MODEL_VERSION:
        _warn(f"bundle model_version {bundle.get('model_version')!r} != expected "
              f"{tbs.MODEL_VERSION!r} — refusing to serve a mismatched champion.")
        return None
    d = bundle["design"]
    design = Design(medians=pd.Series(d["medians"], dtype=float),
                    mean=np.asarray(d["mean"], float), std=np.asarray(d["std"], float))
    # Refit-cadence staleness (decided at ship: monthly refit, 45d slack) — loud, never fatal.
    try:
        fit_date = _date.fromisoformat(bundle["fit"]["fit_date"])
        age = (_date.fromisoformat(target) - fit_date).days
        if age > int(bundle.get("stale_after_days", 45)):
            _warn(f"served bundle is {age} days old (fit {fit_date}) — the monthly refit "
                  f"cadence has lapsed; rebuild the substrate + refit "
                  f"(betting_ml/scripts/prop_pricing/fit_batter_tb.py).")
    except Exception as exc:  # noqa: BLE001
        _warn(f"bundle fit-date staleness check failed: {exc}")
    return bundle, design


# ---------------------------------------------------------------------------
# Live TB book lines (S3 props feed)
# ---------------------------------------------------------------------------

def _load_book_lines(target: str) -> pd.DataFrame:
    """Latest PREGAME snapshot per (event, book, player) for the target date.

    Columns: event_id, home_team, away_team, commence_ts, player_name, book, line,
    over_odds, under_odds. Fail-open: any error → empty frame (nothing to serve yet)."""
    glob = _PROPS_GLOB.format(date=target)
    try:
        import duckdb
        con = duckdb.connect()
        con.execute("INSTALL httpfs; LOAD httpfs")
        con.execute("CREATE OR REPLACE SECRET s3tb (TYPE S3, PROVIDER credential_chain, "
                    "REGION 'us-east-2')")
        df = con.execute(
            f"""
            WITH ranked AS (
                SELECT event_id, home_team, away_team,
                       commence_time::TIMESTAMP AS commence_ts,
                       player_name, bookmaker_key AS book,
                       line::DOUBLE AS line, over_price, under_price,
                       ROW_NUMBER() OVER (PARTITION BY event_id, bookmaker_key, player_name
                                          ORDER BY snapshot_ts DESC) AS rn
                FROM read_parquet('{glob}', hive_partitioning=1, union_by_name=true)
                WHERE line IS NOT NULL
                  AND snapshot_ts < commence_time      -- pregame only (leakage gate)
            )
            SELECT * EXCLUDE (rn) FROM ranked WHERE rn = 1
            """
        ).fetchdf()
        con.close()
        return df
    except Exception as exc:  # noqa: BLE001 — fail-open
        _warn(f"TB book-line read skipped (fail-open, nothing to serve): {exc}")
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# Slate + event → game_pk + name → batter_id resolution (pregame)
# ---------------------------------------------------------------------------

def _load_slate(conn, target: str) -> pd.DataFrame:
    """Target-date games from the spine. Postponed excluded (stale first pitch; MLB reuses the
    gamePk); non-regular-season games are returned flagged so the caller can skip them loudly.

    INC-23: stg_statsapi_games.game_date is an ISO VARCHAR in the lakehouse — cast ::TIMESTAMP
    (naive keeps the UTC wall value, the payload convention E5.5 already uses)."""
    return conn.execute(
        """
        SELECT game_pk::BIGINT AS game_pk,
               home_team_name, away_team_name,
               game_date::TIMESTAMP AS first_pitch,
               strftime(game_date::TIMESTAMP, '%Y-%m-%dT%H:%M:%SZ') AS game_datetime,
               venue_id::BIGINT AS venue_id,
               season::INTEGER AS season,
               game_type
        FROM stg_statsapi_games
        WHERE official_date::DATE = ?::date
          AND coalesce(detailed_state, '') <> 'Postponed'
        """,
        [target],
    ).fetchdf()


def _resolve_events(conn, lines: pd.DataFrame, slate: pd.DataFrame) -> dict[str, int]:
    """event_id → game_pk via team-name folding + scheduled-first-pitch matching (the
    substrate's fallback resolver — ~97% standalone; both name sides fold THROUGH
    dim_team_name_lookup, never lookup.team_id = spine ids, the phase-1 zero-rows landmine)."""
    if lines.empty or slate.empty:
        return {}
    events = lines[["event_id", "home_team", "away_team", "commence_ts"]].drop_duplicates()
    conn.register("tb_events_df", events)
    conn.register("tb_slate_df", slate)
    rows = conn.execute(
        f"""
        WITH lk AS (SELECT name_lower, team_id FROM dim_team_name_lookup),
        cand AS (
            SELECT pe.event_id, sp.game_pk,
                   abs(date_diff('minute', pe.commence_ts, sp.first_pitch)) AS delta_min
            FROM tb_events_df pe
            JOIN lk ph ON ph.name_lower = lower(regexp_replace(trim(pe.home_team), '^G[12] ', ''))
            JOIN lk pa ON pa.name_lower = lower(regexp_replace(trim(pe.away_team), '^G[12] ', ''))
            JOIN tb_slate_df sp
              ON abs(date_diff('minute', pe.commence_ts, sp.first_pitch))
                 <= {FIRST_PITCH_TOLERANCE_MIN}
            JOIN lk sh ON sh.name_lower = lower(trim(sp.home_team_name)) AND sh.team_id = ph.team_id
            JOIN lk sa ON sa.name_lower = lower(trim(sp.away_team_name)) AND sa.team_id = pa.team_id
        )
        SELECT event_id, game_pk FROM (
            SELECT *, row_number() OVER (PARTITION BY event_id
                                         ORDER BY delta_min, game_pk) AS rn
            FROM cand
        ) WHERE rn = 1
        """
    ).fetchall()
    return {str(e): int(g) for e, g in rows}


def _name_candidates(conn, names: list[str]) -> dict[str, set[int]]:
    """player_name → candidate batter_ids via the SUBSTRATE'S two-tier keys (exact normalised
    key first; last-initial fallback ONLY when the exact key matches no reference player).
    Uses the substrate's local quote-folding (`_name_key`/`_li_key`) — NOT the raw
    prop_edge.normalize_name (the curly-apostrophe divergence, phase-1 finding)."""
    if not names:
        return {}
    from betting_ml.utils.prop_edge import ref_display_name
    ref = conn.execute(
        """
        SELECT mlb_bam_id::BIGINT AS batter_id, first_name, last_name
        FROM stg_ref_players WHERE mlb_bam_id IS NOT NULL
        """
    ).fetchdf()
    ref["display"] = [ref_display_name(f, l) for f, l in zip(ref.first_name, ref.last_name)]
    ref["name_key"] = [_name_key(d) for d in ref.display]
    ref["li_key"] = [_li_key(d) for d in ref.display]
    by_exact: dict[str, set[int]] = {}
    by_li: dict[str, set[int]] = {}
    for bid, nk, lk in zip(ref.batter_id, ref.name_key, ref.li_key):
        by_exact.setdefault(nk, set()).add(int(bid))
        by_li.setdefault(lk, set()).add(int(bid))
    out: dict[str, set[int]] = {}
    for nm in names:
        nk = _name_key(nm)
        if nk in by_exact:
            out[nm] = set(by_exact[nk])
        else:
            out[nm] = set(by_li.get(_li_key(nm), set()))
    return out


def _batter_display_names(conn, batter_ids: list[int]) -> dict[int, str]:
    """batter_id -> canonical display name (stg_ref_players), for population members with no
    matched book-line row to borrow a name from (E5.10 — see `_run_for_date`'s population
    change: a batter with no live line still needs a `full_name` for the served card)."""
    if not batter_ids:
        return {}
    from betting_ml.utils.prop_edge import ref_display_name
    id_list = ",".join(str(int(b)) for b in batter_ids)
    rows = conn.execute(
        f"""
        SELECT mlb_bam_id::BIGINT AS batter_id, first_name, last_name
        FROM stg_ref_players WHERE mlb_bam_id IN ({id_list})
        """
    ).fetchall()
    return {int(bid): ref_display_name(fn, ln) for bid, fn, ln in rows}


def _lineup_members(conn, game_pks: list[int]) -> dict[int, dict[int, dict]]:
    """{game_pk: {batter_id: {side, team_is_home}}} from the posted lineups (may be partial or
    absent pregame — callers treat absence as 'not posted yet', never as 'not playing')."""
    out: dict[int, dict[int, dict]] = {}
    if not game_pks:
        return out
    pk_list = ",".join(str(int(g)) for g in game_pks)
    slot_ids = ", ".join(f"slot_{i}_player_id" for i in range(1, 10))
    rows = conn.execute(
        f"""
        SELECT game_pk::BIGINT AS game_pk, home_away, {slot_ids}
        FROM stg_statsapi_lineups_wide
        WHERE game_pk::BIGINT IN ({pk_list})
        """
    ).fetchdf()
    for _, r in rows.iterrows():
        gp = int(r["game_pk"])
        is_home = str(r["home_away"]).lower() == "home"
        for i in range(1, 10):
            pid = r.get(f"slot_{i}_player_id")
            if pd.notna(pid):
                out.setdefault(gp, {})[int(pid)] = {"is_home": is_home}
    return out


def _eb_rows(conn, game_pks: list[int]) -> pd.DataFrame:
    """EB posterior rows (pregame confirmed-lineup build) for the slate. game_pk/batter_id are
    VARCHAR in this table — cast explicitly (the substrate does the same)."""
    if not game_pks:
        return pd.DataFrame()
    pk_list = ",".join(str(int(g)) for g in game_pks)
    return conn.execute(
        f"""
        SELECT game_pk::BIGINT AS game_pk, batter_id::BIGINT AS batter_id,
               batting_slot::INTEGER AS batting_slot,
               eb_woba, eb_k_pct, eb_bb_pct, eb_iso, eb_woba_uncertainty
        FROM eb_batter_posteriors_raw
        WHERE game_pk::BIGINT IN ({pk_list})
        """
    ).fetchdf()


# ---------------------------------------------------------------------------
# Serving feature frame — the live-mart reproduction of the substrate's contract
# ---------------------------------------------------------------------------

def build_serving_frame(conn, target: str, pairs: pd.DataFrame) -> pd.DataFrame:
    """Pregame features for the given (game_pk, batter_id, venue_id, season) pairs, as-of the
    target date, reproducing the substrate's semantics from the live marts.

    * rolling: the substrate's OWN hand-collapse (`build_rolling_features`, imported) over the
      target + prior season, then each batter's LATEST completed row strictly before the
      target date = the lag-one `prev_*` value (the mart's windows are inclusive).
    * EB posteriors + batting_slot: eb_batter_posteriors_raw at the target game_pk (pregame).
    * park factors: PRIOR season (apply_season = row season), from mart_park_factors_granular.
    * batter_hand: the latest completed game's collapsed hand.
    """
    year = int(target[:4])
    build_rolling_features(conn, f"""(
        SELECT * FROM mart_batter_rolling_stats
        WHERE game_year IN ({year - 1}, {year}))""")
    prev = conn.execute(
        """
        SELECT batter_id, batter_hand,
               pa_count_7d AS prev_pa_count_7d, pa_count_30d AS prev_pa_count_30d,
               games_30d AS prev_games_30d,
               avg_30d AS prev_avg_30d, obp_30d AS prev_obp_30d,
               slg_30d AS prev_slg_30d, ops_30d AS prev_ops_30d,
               woba_30d AS prev_woba_30d, xwoba_30d AS prev_xwoba_30d,
               xba_30d AS prev_xba_30d, xslg_30d AS prev_xslg_30d,
               k_pct_30d AS prev_k_pct_30d, bb_pct_30d AS prev_bb_pct_30d,
               hard_hit_pct_30d AS prev_hard_hit_pct_30d,
               barrel_pct_30d AS prev_barrel_pct_30d,
               woba_7d AS prev_woba_7d, slg_7d AS prev_slg_7d, k_pct_7d AS prev_k_pct_7d,
               woba_std AS prev_woba_std, slg_std AS prev_slg_std,
               iso_std AS prev_iso_std, k_pct_std AS prev_k_pct_std
        FROM rolling_by_game
        WHERE game_date < ?::date
        QUALIFY row_number() OVER (PARTITION BY batter_id
                                   ORDER BY game_date DESC, game_pk DESC) = 1
        """,
        [target],
    ).fetchdf()

    eb = _eb_rows(conn, pairs["game_pk"].astype(int).unique().tolist())
    park = conn.execute(
        f"""
        SELECT venue_id::BIGINT AS venue_id,
               (season + 1)::INTEGER AS apply_season,
               eb_hr_factor, eb_singles_factor, eb_doubles_triples_factor,
               eb_woba_factor, eb_so_factor, eb_bb_factor
        FROM mart_park_factors_granular
        WHERE (season + 1) = {int(target[:4])}
        """
    ).fetchdf()

    frame = pairs.copy()
    frame["game_pk"] = frame["game_pk"].astype(int)
    frame["batter_id"] = frame["batter_id"].astype(int)
    frame = frame.merge(prev, on="batter_id", how="left")
    if not eb.empty:
        frame = frame.merge(eb, on=["game_pk", "batter_id"], how="left")
    else:
        for c in ("batting_slot", "eb_woba", "eb_k_pct", "eb_bb_pct", "eb_iso",
                  "eb_woba_uncertainty"):
            frame[c] = np.nan
    if not park.empty:
        frame = frame.merge(park.drop(columns=["apply_season"]), on="venue_id", how="left")
    else:
        for c in ("eb_hr_factor", "eb_singles_factor", "eb_doubles_triples_factor",
                  "eb_woba_factor", "eb_so_factor", "eb_bb_factor"):
            frame[c] = np.nan
    for c in NUMERIC_FEATURES:
        if c not in frame.columns:
            frame[c] = np.nan
    if "batter_hand" not in frame.columns:
        frame["batter_hand"] = None
    return frame


# ---------------------------------------------------------------------------
# E7.9 train/serve consistency check (the runtime-gate evidence)
# ---------------------------------------------------------------------------

def compare_feature_frames(merged: pd.DataFrame,
                           min_match_rate: float = 0.98) -> tuple[list[str], list[str]]:
    """Pure comparator for the E7.9 check: per pre-registered feature column, the share of rows
    where the substrate (`_sub`) and serving (`_srv`) values agree (both-NaN counts as a match;
    one-sided NaN is a MISMATCH). Returns (failures, report_lines). Unit-tested."""
    failures: list[str] = []
    report: list[str] = []
    for col in NUMERIC_FEATURES:
        if f"{col}_sub" not in merged.columns or f"{col}_srv" not in merged.columns:
            failures.append(f"{col}: missing on one side")
            report.append(f"  [FAIL] {col:<28} missing on one side")
            continue
        a = pd.to_numeric(merged[f"{col}_sub"], errors="coerce")
        b = pd.to_numeric(merged[f"{col}_srv"], errors="coerce")
        both_nan = a.isna() & b.isna()
        close = np.isclose(a.to_numpy(float), b.to_numpy(float),
                           rtol=1e-6, atol=1e-9, equal_nan=False)
        match = float((both_nan | pd.Series(close, index=a.index)).mean())
        # NB: gate on `ok`, never on `match < rate` — an EMPTY comparison yields match=NaN,
        # and NaN fails BOTH comparisons, which would silently PASS a check that compared
        # nothing (NF1.7 (a); this module's own RED-proof caught exactly that).
        ok = bool(match >= min_match_rate)
        report.append(f"  [{'OK ' if ok else 'FAIL'}] {col:<28} match={match:.4f}")
        if not ok:
            failures.append(f"{col}: {match:.4f}")
    return failures, report


def run_consistency_check(target: str, substrate_path: str,
                          min_match_rate: float = 0.98) -> int:
    """Prove the live-mart serving feature path reproduces the substrate's features for a
    historical date, per column, on the intersection of (game_pk, batter_id) keys.

    Excluded from the rolling-column comparison: batters with 2+ completed games on the
    target date (the documented doubleheader lag gap). Exit 0 iff every pre-registered
    numeric feature matches on ≥ min_match_rate of compared rows."""
    print(f"[tb-consistency] target={target} substrate={substrate_path}")
    sub = pd.read_parquet(substrate_path)
    sub = sub[(sub["market_key"] == "batter_total_bases")
              & (pd.to_datetime(sub["game_date"]).dt.date.astype(str) == target)].copy()
    if sub.empty:
        _warn(f"substrate has no TB rows for {target} — pick a date inside the substrate "
              "window (2023-05-03 .. its build date).")
        return 1
    print(f"[tb-consistency] {len(sub)} substrate rows for {target}")

    conn = _duck_lakehouse(_LAKEHOUSE_TABLES)
    try:
        slate = _load_slate(conn, target)
        pairs = sub[["game_pk", "batter_id", "season"]].drop_duplicates().merge(
            slate[["game_pk", "venue_id"]], on="game_pk", how="left")
        served = build_serving_frame(conn, target, pairs)
        # DH exclusion: batters with >1 completed game on the target date (rolling_by_game
        # was just built by build_serving_frame on this connection).
        dh = conn.execute(
            "SELECT batter_id FROM rolling_by_game WHERE game_date = ?::date "
            "GROUP BY batter_id HAVING count(*) > 1",
            [target],
        ).fetchdf()
    finally:
        conn.close()
    dh_ids = set(dh["batter_id"].astype(int)) if not dh.empty else set()

    merged = sub.merge(served, on=["game_pk", "batter_id"], how="inner",
                       suffixes=("_sub", "_srv"))
    n_dh = int(merged["batter_id"].isin(dh_ids).sum())
    merged = merged[~merged["batter_id"].isin(dh_ids)]
    print(f"[tb-consistency] comparing {len(merged)} rows "
          f"(substrate {len(sub)}, DH-excluded {n_dh})")
    if len(merged) < 20:
        _warn("fewer than 20 comparable rows — the check is not meaningful for this date.")
        return 1

    failures, report = compare_feature_frames(merged, min_match_rate)
    for line in report:
        print(line)
    # hand agreement — reported, not gated (realized-hand vs latest-hand, documented delta)
    if "batter_hand_sub" in merged and "batter_hand_srv" in merged:
        hand = (merged["batter_hand_sub"].fillna("?") == merged["batter_hand_srv"].fillna("?")).mean()
        print(f"  [info] batter_hand agreement = {hand:.4f} (not gated — realized vs latest)")

    if failures:
        _warn(f"consistency check FAILED on {len(failures)} column(s): {failures}")
        return 1
    print(f"[tb-consistency] PASS — every pre-registered feature matches the substrate on "
          f">= {min_match_rate:.0%} of {len(merged)} rows.")
    return 0


# ---------------------------------------------------------------------------
# Serving writes (DynamoDB serving cache primary; S3 fallback — mirrors E5.5)
# ---------------------------------------------------------------------------

_SERVING_CACHE_TABLE = os.getenv("SERVING_CACHE_TABLE", "credence-prod-serving-cache")
_SERVING_CACHE_REGION = os.getenv("AWS_REGION", "us-east-1")


def _ddb_put(sk: str, target: str, payload: dict) -> None:
    import boto3
    tbl = boto3.resource("dynamodb", region_name=_SERVING_CACHE_REGION).Table(_SERVING_CACHE_TABLE)
    tbl.put_item(Item={
        "pk": "batter_tb_projection",
        "sk": sk,
        "value": json.dumps(payload, default=float),
        "is_permanent": False,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "cache_date": target,
    })


def _s3_put(key: str, body: bytes) -> None:
    from scripts.utils.lakehouse_raw_writer import make_s3_client
    make_s3_client().put_object(Bucket=_S3_BUCKET, Key=key, Body=body,
                                ContentType="application/json")


# ---------------------------------------------------------------------------
# Main scoring path
# ---------------------------------------------------------------------------

def _run_for_date(target: str, args, bundle: dict, design: Design) -> None:
    conn = _duck_lakehouse(_LAKEHOUSE_TABLES)
    try:
        slate = _load_slate(conn, target)
        if slate.empty:
            _warn(f"[{target}] no games on the spine for this date — skipped.")
            return
        non_r = slate[slate["game_type"] != "R"]
        if len(non_r):
            _warn(f"[{target}] skipping {len(non_r)} non-regular-season game(s) — the TB model "
                  "is a regular-season fit; postseason serving would be extrapolation.")
        slate = slate[slate["game_type"] == "R"]
        if slate.empty:
            _warn(f"[{target}] no regular-season games — nothing served (by design).")
            return

        # E5.10 — POPULATION comes from today's posted lineups (falling back to EB-posterior
        # presence), never from the live props feed. Previously the whole slate was driven
        # top-down from `lines`, so a batter/game with no CURRENTLY-captured book line was
        # excluded outright — and because the hourly `--mode live` capture OVERWRITES the
        # day's snapshot (never accumulates), a game that had a perfectly good pregame price an
        # hour ago would silently vanish from the served list the moment it started and dropped
        # out of the "live" pull. Mirrors write_pitcher_k_projections.py's probable-pitcher
        # population (schedule-derived, never gated on a book price). Book lines below are now
        # OPTIONAL enrichment: a batter with no matched line still gets a projection card, with
        # `book_comparisons: []` (tb_projection_serving already renders that as no line/no
        # books rather than excluding the row — see index_row's None/[] fallbacks).
        game_pks = sorted(slate["game_pk"].astype(int).unique())
        members = _lineup_members(conn, game_pks)
        eb = _eb_rows(conn, game_pks)
        eb_ids = {int(g): set(grp["batter_id"].astype(int))
                  for g, grp in eb.groupby("game_pk")} if not eb.empty else {}

        pop_pairs: set[tuple[int, int]] = set()
        for gp, batters in members.items():
            pop_pairs.update((gp, bid) for bid in batters)
        for gp, bids in eb_ids.items():
            pop_pairs.update((gp, bid) for bid in bids)
        no_lineup = [gp for gp in game_pks if gp not in members and gp not in eb_ids]
        if no_lineup:
            _warn(f"[{target}] {len(no_lineup)} game(s) have no posted lineup or EB posterior "
                  "yet — their batters aren't listed this run (retried hourly once posted).")
        if not pop_pairs:
            _warn(f"[{target}] no lineups posted / EB posteriors built yet — nothing to serve.")
            return
        print(f"[tb-projection] {len(pop_pairs)} batters across "
              f"{len({gp for gp, _ in pop_pairs})} game(s) with a posted lineup/EB build for "
              f"{target}")

        # Book lines: OPTIONAL match onto the population above, never population-defining.
        lines = _load_book_lines(target)
        resolved: dict[tuple[int, str], int] = {}
        if not lines.empty:
            event_map = _resolve_events(conn, lines, slate)
            n_unres = lines["event_id"].nunique() - len(event_map)
            if n_unres:
                _warn(f"[{target}] {n_unres} prop event(s) unresolved to a game_pk (first-pitch "
                      "resolver) — their batters get no book comparison this run.")
            lines = lines[lines["event_id"].astype(str).isin(event_map)].copy()
        if not lines.empty:
            lines["game_pk"] = lines["event_id"].astype(str).map(event_map)
            cands = _name_candidates(conn, sorted(lines["player_name"].dropna().unique()))

            # Pregame arbitration: exact/li candidates ∩ posted lineup (or EB build) for THAT
            # game.
            held = 0
            for (gp, nm), _grp in lines.groupby(["game_pk", "player_name"]):
                ids = cands.get(nm, set())
                gp = int(gp)
                allowed = set(members.get(gp, {})) or eb_ids.get(gp, set())
                pick = ids & allowed if allowed else ids
                if len(pick) == 1:
                    resolved[(gp, nm)] = next(iter(pick))
                elif len(ids) == 1 and not allowed:
                    resolved[(gp, nm)] = next(iter(ids))
                else:
                    held += 1
            if held:
                _warn(f"[{target}] {held} quoted batter-game name(s) held (ambiguous or not in "
                      "the posted lineup yet) — retried on the next run.")
        else:
            print(f"[tb-projection] no live TB book lines yet for {target} — serving "
                  "projections without a book comparison this run.")

        # Fallback display names for population members no live line matched to (E5.10).
        unmatched_ids = sorted({bid for _, bid in pop_pairs} - set(resolved.values()))
        ref_names = _batter_display_names(conn, unmatched_ids)

        # A population member resolvable to neither a book-quoted name nor a stg_ref_players
        # row (a very recent call-up the reference table hasn't caught up to yet, observed
        # live) can't be served with a usable card — skip it loudly rather than shipping a
        # nameless row; self-heals once the reference table catches up.
        nameless = [bid for bid in unmatched_ids if bid not in ref_names]
        if nameless:
            _warn(f"[{target}] {len(nameless)} batter(s) have no resolvable name (no book "
                  f"match, not yet in stg_ref_players) — skipped: {nameless}")
            pop_pairs = {(gp, bid) for gp, bid in pop_pairs if bid not in nameless}

        pairs = pd.DataFrame(
            [{"game_pk": gp, "batter_id": bid} for gp, bid in pop_pairs]
        ).drop_duplicates().merge(
            slate[["game_pk", "venue_id", "season", "home_team_name", "away_team_name",
                   "game_datetime"]],
            on="game_pk", how="inner")
        frame = build_serving_frame(conn, target, pairs)
    finally:
        conn.close()

    # Score through the harness design + champion (market-blind by construction — the frame
    # never carries a price column, and build_design would raise if the contract gained one).
    X, _ = build_design(frame, design)
    mu = np.clip(bundle["model"].predict(X), 1e-4, None)
    pmfs = nb_pmf_grid(mu, float(bundle["nb_alpha"]), int(bundle["grid_cap"]))

    # Per-batter book lines keyed by (game_pk, resolved batter_id). E5.10 — `names_by_id` now
    # has two sources: the book-quoted spelling for a matched batter (kept, existing
    # behavior), falling back to the canonical ref name (`ref_names`) for a population member
    # no line matched to this run.
    by_key: dict[tuple[int, int], list[dict]] = {}
    names_by_id: dict[int, str] = dict(ref_names)
    for (gp, nm), bid in resolved.items():
        names_by_id.setdefault(int(bid), str(nm))
        sub = lines[(lines["game_pk"] == gp) & (lines["player_name"] == nm)]
        rows = by_key.setdefault((int(gp), int(bid)), [])
        for _, r in sub.iterrows():
            rows.append({"book": r["book"], "line": float(r["line"]),
                         "over_odds": r["over_price"], "under_odds": r["under_price"]})

    fit_date = (bundle.get("fit") or {}).get("fit_date")
    gen_at = f"{target}T00:00:00Z"
    written = 0
    index_rows: list[dict] = []
    members_all = members
    for i in range(len(frame)):
        gp = int(frame["game_pk"].iloc[i])
        bid = int(frame["batter_id"].iloc[i])
        mem = (members_all.get(gp) or {}).get(bid)
        is_home = mem["is_home"] if mem else None
        home = frame["home_team_name"].iloc[i]
        away = frame["away_team_name"].iloc[i]
        team = (home if is_home else away) if is_home is not None else None
        opp = (away if is_home else home) if is_home is not None else None
        slot = frame["batting_slot"].iloc[i]
        payload = tbs.build_tb_projection_payload(
            batter_id=bid,
            full_name=names_by_id.get(bid),
            team=team, opponent=opp, game_pk=gp, game_date=target,
            game_datetime=str(frame["game_datetime"].iloc[i]) if pd.notna(
                frame["game_datetime"].iloc[i]) else None,
            batting_slot=int(slot) if pd.notna(slot) else None,
            quantile_levels=_QUANTILES,
            pmf=pmfs[i],
            book_comparisons=tbs.comparisons_from_pmf(
                pmfs[i], by_key.get((gp, bid), []),
                model_mean=float(np.sum(np.arange(pmfs.shape[1]) * pmfs[i]))),
            model_fit_date=fit_date,
            generated_at=gen_at,
        )
        index_rows.append(tbs.index_row(payload))
        if args.dry_run:
            d = payload["distribution"]
            print(f"  [dry-run] {bid} {payload['full_name']}: mean={d['mean']:.2f} "
                  f"P(TB>=2)={d['p_ge']['2']} line={payload['primary_line']} "
                  f"books={len(payload['book_comparisons'])}")
            continue
        body = json.dumps(payload, default=float).encode()
        try:
            _ddb_put(f"{bid}#{target}", target, payload)
        except Exception as exc:  # noqa: BLE001
            _warn(f"DynamoDB write failed for batter {bid} (S3 fallback still covers): {exc}")
        try:
            _s3_put(f"{_S3_PROJECTION_PREFIX}/as_of={target}/{bid}.json", body)
            written += 1
        except Exception as exc:  # noqa: BLE001
            _warn(f"S3 write failed for batter {bid}: {exc}")

    index_payload = tbs.build_index_payload(index_rows, game_date=target,
                                            generated_at=gen_at, model_fit_date=fit_date)
    if args.dry_run:
        print(f"[tb-projection] dry-run complete — {len(index_rows)} batters scored, "
              f"index would list {index_payload['count']} (no writes).")
        return
    body = json.dumps(index_payload, default=float).encode()
    try:
        _ddb_put(f"index#{target}", target, index_payload)
    except Exception as exc:  # noqa: BLE001
        _warn(f"DynamoDB index write failed (S3 fallback still covers): {exc}")
    try:
        _s3_put(f"{_S3_PROJECTION_PREFIX}/as_of={target}/index.json", body)
    except Exception as exc:  # noqa: BLE001
        _warn(f"S3 index write failed: {exc}")
    print(f"[tb-projection] wrote {written}/{len(index_rows)} projections + index "
          f"({index_payload['count']}) → s3://{_S3_BUCKET}/{_S3_PROJECTION_PREFIX}/"
          f"as_of={target}/  [model {tbs.MODEL_VERSION}, fit {fit_date}]")


def main() -> int:
    ap = argparse.ArgumentParser(description="E5.9 — daily batter TB-projection serving writer")
    ap.add_argument("--date", default=None, help="Target US baseball-day (YYYY-MM-DD); default today.")
    ap.add_argument("--dry-run", action="store_true", help="Score + print; no S3/DynamoDB writes.")
    ap.add_argument("--consistency-check", action="store_true",
                    help="E7.9 train/serve consistency: rebuild the serving features for a "
                         "HISTORICAL --date and diff them against the research substrate. "
                         "Exits non-zero on a contract mismatch (runtime-gate evidence).")
    ap.add_argument("--substrate", default=_SUBSTRATE_DEFAULT,
                    help="Substrate parquet for --consistency-check.")
    args = ap.parse_args()

    target = args.date or current_game_date_iso()
    if args.consistency_check:
        return run_consistency_check(target, args.substrate)

    loaded = _load_bundle(target)
    if loaded is None:
        _warn("no served TB bundle available — nothing written (fit + promote "
              f"{tbs.MODEL_VERSION} first: betting_ml/scripts/prop_pricing/fit_batter_tb.py).")
        return 0
    bundle, design = loaded
    _run_for_date(target, args, bundle, design)
    return 0


if __name__ == "__main__":
    if "--consistency-check" in sys.argv:
        sys.exit(main())  # the check must be able to FAIL loudly (it gates the runtime gate)
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 — WARN-tier: never block the pipeline.
        _warn(f"unhandled error — exiting 0 (peripheral writer): {exc}")
        sys.exit(0)
