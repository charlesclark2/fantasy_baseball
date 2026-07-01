"""
ingest_umpire_scorecards.py
---------------------------
Recurring loader for UmpScorecards by-game TENDENCY data via the site's JSON API.

This is the daily/automated counterpart to ``ingest_umpires_historical.py``
(which reads a manually-downloaded CSV). UmpScorecards has no documented bulk
push, but the site itself serves a JSON endpoint we can poll, so the umpire
tendency metrics can finally stay current without a manual export.

It writes rows into ``baseball_data.statsapi.umpire_game_log`` with
``data_source = 'umpscorecards'`` — the SAME shape ``ingest_umpires_historical``
produces — so the trailing-3-year z-scores in ``feature_pregame_umpire_features``
(``ump_run_impact_zscore`` / ``ump_accuracy_zscore`` / ``ump_runs_per_game_zscore``)
recompute correctly. This is the tendency HISTORY the z-scores are built from.

Distinct from ``ingest_umpires.py``, which stamps only TODAY's HP-umpire NAME
from the MLB Stats API (the join key the z-score attaches to). Both feeds are
needed: assignment (name) + tendency (this script). Story 30.5.

API:
    https://umpscorecards.com/api/games?startDate=YYYY-MM-DD&endDate=YYYY-MM-DD&seasonType=R

Per-game JSON fields consumed (verified 2026-06-11):
    game_pk, date, umpire, home_score, away_score, total_run_impact,
    accuracy_above_x (Accuracy Above Expected), correct_calls_above_x
    (Correct Calls Above Expected), favor (Favor (Home)), type ('R').

IDEMPOTENT: deletes existing umpscorecards rows for the fetched game_pks before
re-inserting, so a daily trailing-window run never appends duplicates (unlike the
append-only historical bulk loader, which is run rarely). The dbt staging model
``stg_statsapi_umpire_game_log`` still de-dupes defensively.

Usage:
    # Daily: trailing 7-day window (catches scorecards posted a day or two late)
    uv run python scripts/ingest_umpire_scorecards.py

    # Explicit range (e.g. the Story 30.5 backfill of the 2026-05-02 → present gap)
    uv run python scripts/ingest_umpire_scorecards.py --start 2026-05-02 --end 2026-06-11

    # Inspect without writing
    uv run python scripts/ingest_umpire_scorecards.py --start 2026-06-09 --end 2026-06-11 --dry-run
"""

import argparse
import logging
import os
import sys
from datetime import date, timedelta

import pandas as pd
import requests
import snowflake.connector
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    load_pem_private_key,
)
from dotenv import load_dotenv

# E11.1-W11 Tier-B: leg-gated dual-write (W11_RAW_WRITE_MODE) to lakehouse_raw/umpire_game_log/.
from utils.lakehouse_raw_writer import (  # noqa: E402
    lakehouse_write_legs,
    umpire_mirror_rows,
    w11_write_mode,
    write_raw_rows_s3,
)

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

_LAKEHOUSE_SOURCE = "umpire_game_log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

API_URL = "https://umpscorecards.com/api/games"
TABLE_FQN = "baseball_data.statsapi.umpire_game_log"
# A polite UA — the endpoint is the site's own data API, not a documented public one.
_HEADERS = {"User-Agent": "credence-sports-pipeline/1.0 (umpire tendency loader)"}
_DEFAULT_DAYS_BACK = 7


# ── Snowflake connection (mirrors ingest_umpires_historical.py) ─────────────────

def _load_private_key() -> bytes | None:
    key_path = os.getenv("SNOWFLAKE_PRIVATE_KEY_PATH")
    if not key_path:
        return None
    with open(key_path, "rb") as fh:
        raw = fh.read()
    passphrase = os.getenv("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE")
    key = load_pem_private_key(
        raw, password=passphrase.encode() if passphrase else None, backend=default_backend()
    )
    return key.private_bytes(Encoding.DER, PrivateFormat.PKCS8, NoEncryption())


def get_snowflake_conn():
    kwargs = dict(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        warehouse=os.environ.get("SNOWFLAKE_WAREHOUSE"),
        role=os.environ.get("SNOWFLAKE_ROLE"),
        database="baseball_data",
        schema="statsapi",
    )
    pk = _load_private_key()
    if pk:
        kwargs["private_key"] = pk
    else:
        kwargs["password"] = os.environ["SNOWFLAKE_PASSWORD"]
    return snowflake.connector.connect(**kwargs)


# ── Fetch + map ────────────────────────────────────────────────────────────────

def fetch_scorecards(start: str, end: str) -> list[dict]:
    """Fetch the UmpScorecards per-game JSON for [start, end] (regular season)."""
    params = {"startDate": start, "endDate": end, "seasonType": "R"}
    resp = requests.get(API_URL, params=params, headers=_HEADERS, timeout=30)
    resp.raise_for_status()
    payload = resp.json()
    # The endpoint wraps the games in a {"rows": [...]} envelope (verified
    # 2026-06-11). Fall back to a couple of plausible keys / a bare list so a
    # future shape tweak fails loud rather than silently loading zero rows.
    # NOTE: the date params are camelCase (startDate/endDate); snake_case is
    # IGNORED by the API and returns the entire 2015→present history (~29 MB).
    if isinstance(payload, dict):
        games = payload.get("rows") or payload.get("games") or payload.get("data") or []
    else:
        games = payload
    if not isinstance(games, list):
        raise ValueError(f"Unexpected UmpScorecards payload shape: {type(payload).__name__}")
    return games


def to_dataframe(games: list[dict]) -> pd.DataFrame:
    """Map the API JSON to the umpire_game_log column shape (umpscorecards rows)."""
    rows = []
    for g in games:
        # Regular season only (the query is R-scoped, but guard anyway).
        if str(g.get("type", "R")).upper() not in ("R", ""):
            continue
        gpk = g.get("game_pk")
        ump = (g.get("umpire") or "").strip()
        if gpk is None or not ump:
            continue
        d = pd.to_datetime(g["date"]).date()
        home = g.get("home_score")
        away = g.get("away_score")
        total_runs = None
        if home is not None and away is not None:
            total_runs = int(home) + int(away)
        rows.append({
            "game_pk": int(gpk),
            "game_date": d.isoformat(),
            "season": d.year,
            "umpire_name": ump,
            "umpire_id": None,
            "k_pct": None,
            "bb_pct": None,
            "total_runs": total_runs,
            "called_strikes_above_avg": g.get("correct_calls_above_x"),
            "run_expectancy_delta": g.get("favor"),
            "total_run_impact": g.get("total_run_impact"),
            "accuracy_above_expected": g.get("accuracy_above_x"),
            "data_source": "umpscorecards",
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.drop_duplicates(subset=["game_pk"], keep="last").reset_index(drop=True)
    return df


# ── Write (idempotent: delete-then-insert for the fetched game_pks) ─────────────

_WP_COLS = [
    "game_pk", "game_date", "season", "umpire_name", "umpire_id", "k_pct", "bb_pct",
    "total_runs", "called_strikes_above_avg", "run_expectancy_delta",
    "total_run_impact", "accuracy_above_expected", "data_source",
]


def write_idempotent(conn, df: pd.DataFrame) -> int:
    from snowflake.connector.pandas_tools import write_pandas

    game_pks = [int(x) for x in df["game_pk"].tolist()]
    pk_list = ", ".join(str(pk) for pk in game_pks)
    load_df = df[_WP_COLS].rename(columns={c: c.upper() for c in _WP_COLS})

    with conn.cursor() as cur:
        # Replace existing UmpScorecards rows for just these games so a daily
        # trailing-window run is idempotent (no append bloat). Scoped to the
        # umpscorecards source — never touches the statsapi assignment rows.
        cur.execute(
            f"DELETE FROM {TABLE_FQN} "
            f"WHERE data_source = 'umpscorecards' AND game_pk IN ({pk_list})"
        )
        deleted = cur.rowcount

    success, _, nrows, _ = write_pandas(
        conn, load_df, "UMPIRE_GAME_LOG",
        database="BASEBALL_DATA", schema="STATSAPI",
        overwrite=False, quote_identifiers=False,
    )
    if not success:
        raise RuntimeError("write_pandas reported failure")
    log.info("Replaced %d existing + inserted %d umpscorecards row(s).", deleted, nrows)
    return nrows


# ── CLI ─────────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="Load UmpScorecards by-game tendency data via the JSON API")
    ap.add_argument("--start", help="start date YYYY-MM-DD (default: today - --days-back)")
    ap.add_argument("--end", help="end date YYYY-MM-DD (default: today)")
    ap.add_argument("--days-back", type=int, default=_DEFAULT_DAYS_BACK,
                    help=f"trailing window size when --start omitted (default {_DEFAULT_DAYS_BACK})")
    ap.add_argument("--dry-run", action="store_true", help="fetch + map only; no Snowflake write")
    args = ap.parse_args()

    end = args.end or date.today().isoformat()
    start = args.start or (date.fromisoformat(end) - timedelta(days=args.days_back)).isoformat()
    log.info("Fetching UmpScorecards games %s → %s", start, end)

    games = fetch_scorecards(start, end)
    df = to_dataframe(games)
    log.info("Fetched %d game(s); %d row(s) with a usable umpire + game_pk.", len(games), len(df))

    if df.empty:
        log.warning("No usable rows in range — nothing to load (scorecards may not be posted yet).")
        return

    if args.dry_run:
        n_with_impact = int(df["total_run_impact"].notna().sum())
        print("\n--- DRY RUN ---")
        print(f"rows={len(df)}  with_tendency={n_with_impact}  "
              f"dates={df['game_date'].min()}..{df['game_date'].max()}")
        print(df.head(3).to_dict("records"))
        return

    do_sf, do_s3 = lakehouse_write_legs(w11_write_mode())

    if do_sf:
        conn = get_snowflake_conn()
        try:
            n = write_idempotent(conn, df)
        finally:
            conn.close()
        log.info("Done — loaded %d umpscorecards tendency row(s) into %s.", n, TABLE_FQN)

    if do_s3:
        # df already carries data_source='umpscorecards'; stamp loaded_at + fill the full column set.
        mirror_rows = umpire_mirror_rows(df.to_dict("records"), data_source="umpscorecards")
        n_s3 = write_raw_rows_s3(_LAKEHOUSE_SOURCE, mirror_rows, mode="append")
        log.info("mirrored %d row(s) → S3 lakehouse_raw/%s/", n_s3, _LAKEHOUSE_SOURCE)


if __name__ == "__main__":
    main()
