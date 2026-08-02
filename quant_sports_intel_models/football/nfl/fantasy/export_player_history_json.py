"""export_player_history_json.py — NF3.3: extend the shared NF3 `projections.json` player payload
with a per-player HISTORY block (past-season actual finish + past ADP + a weekly injury-report log +
games-missed participation), for the entitled player page's History panel.

🩹 SHARED-EXPORT-FILE DISCIPLINE (this file is `projections.json`, a live serving artifact several
export scripts and concurrent sessions can touch — the NF3.4/NF1.5b near-miss class): this script
NEVER regenerates `projections.json` from scratch. It DOWNLOADS the current live copy (S3 when a
bucket resolves, else the local staged artifact for laptop dev), computes ONLY a `history` value per
player, merges that one key into each player record, and — before writing anything — asserts
BYTE-FOR-BYTE that every other field, on every player and at the top level (incl. `model_version`),
is unchanged from the download. A mismatch means something else touched the file concurrently, and
this script REFUSES to publish over it (see `diff_verify`).

DATA REUSE (never a parallel re-derivation of an existing join):
  * past-season our-rank / ADP / actual finish — `export_track_record_json.build_player_track_record`,
    the SAME function NF3.2's public track-record page is built from. This script does not re-join
    projection-vs-ADP-vs-realized itself.
  * ADP — the SAME `adp_source` / `mfl_adp_source` caches `build_player_track_record` already reads;
    nothing here fetches ADP a second time.
  * injury report + games-missed — genuinely NEW for NF3.3 (`injury_log_source.py`), reading the
    already-ingested `stg_nfl_injuries` (N0.2) and `fct_player_week` (N0.3) — no new capture/fetch.

🔒 ENTITLEMENT: `history` lands inside `projections.json`, which only `/fantasy/nfl/projections`
(gated `require_fantasy_access`) serves — so the History panel is gated AT THE DATA LAYER with zero
extra plumbing, and the public player view (`PublicPlayerView`, `lib/fantasy-track-record.ts`) never
sees it. Past-actual/ADP are a plausible future FREE-tier split (E9.56); ship gated by default until
that story flips it — flipping it later only needs the history block moved to a public sibling
payload, never a UI change.

RUN (LAPTOP, SF-free sports lake):
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.export_player_history_json \
      --duckdb quant_sports_intel_models/sports_dbt/sports.duckdb --seasons 2019-2025 --season 2026

Same NF-D12 dry-run/`--publish` guard as its siblings — a resolved `--s3-bucket`/`$CACHE_BUCKET`
alone never uploads; `--publish` is required. Uploads ONLY the one patched
`fantasy/nfl/<season>/projections.json` key — never `manifest.json`/`board_*.json` in that directory;
this script has no reason to touch them and must not risk them on a publish it wasn't asked to make.
"""
from __future__ import annotations

import argparse
import copy
import json
import logging
import os
import sys
from pathlib import Path

import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from quant_sports_intel_models.football.nfl.fantasy import injury_log_source as IL  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy.export_draft_board_json import (  # noqa: E402
    _STAGING_OUT as _BOARD_STAGING_OUT,
)
from quant_sports_intel_models.football.nfl.fantasy.export_track_record_json import (  # noqa: E402
    build_player_track_record,
)
from quant_sports_intel_models.football.nfl.fantasy.run_season_projection import (  # noqa: E402
    MARTS_SCHEMA,
    load_realized_season,
)

log = logging.getLogger("nfl.fantasy.export_player_history")

_ARTIFACTS = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/artifacts"
_STAGING_OUT = _ARTIFACTS / "player_history_json"


def _fnum(v, nd: int = 1):
    return None if pd.isna(v) else round(float(v), nd)


def _inum(v):
    return None if pd.isna(v) else int(v)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Assembly — reuses `build_player_track_record` (a) + (b) and `injury_log_source` (c); no parallel
# re-derivation of either.
# ══════════════════════════════════════════════════════════════════════════════════════════════
def build_past_seasons(con, seasons: list[int], schema: str) -> dict[str, list[dict]]:
    """{player_id: [{season, ourRank, adp, adpRank, adpSource, actualPoints, actualRank, gamesPlayed,
    isFade, fadeResult}, ...]} across `seasons` — sourced from the SAME `build_player_track_record`
    NF3.2's public receipts page reads. A season with no locally-built NF1.5 refined board is skipped
    (logged), never silently fabricated."""
    out: dict[str, list[dict]] = {}
    for y in sorted(seasons):
        try:
            df = build_player_track_record(con, y, schema)
        except FileNotFoundError:
            log.warning("season %d: no NF1.5 refined board on disk — skipped for the history panel "
                        "(run run_nf1_5.py --projection-season %d if it should be there)", y, y)
            continue
        if df.empty:
            continue
        real = load_realized_season(con, y, schema, include_zero_game=True)[["player_id", "g"]].copy()
        real["player_id"] = real["player_id"].astype(str)
        games = dict(zip(real["player_id"], real["g"]))
        for _, r in df.iterrows():
            pid = str(r["player_id"])
            out.setdefault(pid, []).append({
                "season": y,
                "ourRank": int(r["our_rank"]),
                "adp": _fnum(r["adp"], 1),
                "adpRank": _inum(r["adp_rank"]),
                "adpSource": None if pd.isna(r["adp_source"]) else str(r["adp_source"]),
                "actualPoints": _fnum(r["actual_points"]),
                "actualRank": int(r["actual_rank"]),
                "gamesPlayed": _inum(games.get(pid)),
                "isFade": bool(r["is_fade"]),
                "fadeResult": None if pd.isna(r["fade_result"]) else str(r["fade_result"]),
            })
    for pid in out:
        out[pid].sort(key=lambda rec: rec["season"])
    return out


def build_history_map(con, seasons: list[int], schema: str) -> dict[str, dict]:
    """Assemble the full per-player `history` object for every player who has ANY of the three
    pieces. A player with nothing (a rookie with no past season and no report; a DST — never in
    `benchmark_scorecard._POSITIONS`) is simply absent, which `merge_history` reads as `history:
    None` rather than an empty-but-present object."""
    past = build_past_seasons(con, seasons, schema)
    injuries = IL.injury_records(IL.load_injury_reports(con, seasons))
    missed = IL.games_missed_records(IL.load_games_missed(con, seasons, schema))

    out: dict[str, dict] = {}
    for pid in set(past) | set(injuries) | set(missed):
        out[pid] = {
            "pastSeasons": past.get(pid, []),
            "injuries": injuries.get(pid, []),
            "gamesMissedBySeason": missed.get(pid, []),
        }
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The shared-file patch: merge + verify
# ══════════════════════════════════════════════════════════════════════════════════════════════
def merge_history(payload: dict, history_map: dict[str, dict]) -> dict:
    """Return a DEEP-COPIED `payload` with `history` set on every player record (None for a player
    with nothing) — the ONLY mutation this script ever makes to a shared `projections.json`."""
    merged = copy.deepcopy(payload)
    for player in merged.get("players", []):
        player["history"] = history_map.get(str(player.get("id")))
    return merged


def diff_verify(original: dict, merged: dict) -> None:
    """Assert `merged` differs from `original` ONLY in the presence/value of each player's `history`
    key — never any other player field, never a top-level field (incl. `model_version`), never the
    player order or count. Raises with a specific, actionable message otherwise, so this script
    refuses to publish over a file that moved underneath it — the exact near-miss the shared-export-
    file discipline exists to prevent."""
    orig_top = {k: v for k, v in original.items() if k != "players"}
    merged_top = {k: v for k, v in merged.items() if k != "players"}
    if orig_top != merged_top:
        raise ValueError(
            f"top-level fields changed underneath this patch: {orig_top} -> {merged_top} — the live "
            f"projections.json moved since download; re-run against a fresh download rather than "
            f"publishing over it."
        )
    orig_players = original.get("players", [])
    merged_players = merged.get("players", [])
    if len(orig_players) != len(merged_players):
        raise ValueError(
            f"player count changed: {len(orig_players)} -> {len(merged_players)} — the live "
            f"projections.json moved since download; re-run against a fresh download."
        )
    for i, (o, m) in enumerate(zip(orig_players, merged_players)):
        o_rest = {k: v for k, v in o.items() if k != "history"}
        m_rest = {k: v for k, v in m.items() if k != "history"}
        if o_rest != m_rest:
            raise ValueError(
                f"player[{i}] id={o.get('id')!r} changed underneath this patch outside 'history': "
                f"{o_rest} -> {m_rest} — the live projections.json moved since download; re-run "
                f"against a fresh download rather than publishing over it."
            )


# ══════════════════════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _parse_seasons(spec: str) -> list[int]:
    lo_s, _, hi_s = spec.partition("-")
    lo, hi = int(lo_s), int(hi_s or lo_s)
    return list(range(lo, hi + 1))


def _load_live_projections(season: int, bucket: str | None, override: Path | None) -> tuple[dict, str]:
    """The "download-fresh" half of the discipline. `override` is a dev/test escape hatch that skips
    the download — never use it for a real `--publish`."""
    if override is not None:
        log.warning("--projections-json %s: patching THIS file instead of downloading fresh — "
                    "dev/test override only; never combine with a real --publish", override)
        return json.loads(override.read_text()), f"local override {override}"
    if bucket:
        import boto3

        s3 = boto3.client("s3", region_name="us-east-1")
        key = f"fantasy/nfl/{season}/projections.json"
        resp = s3.get_object(Bucket=bucket, Key=key)
        return json.loads(resp["Body"].read().decode("utf-8")), f"s3://{bucket}/{key}"
    local = _BOARD_STAGING_OUT / str(season) / "projections.json"
    if not local.is_file():
        raise SystemExit(
            f"no --s3-bucket/$CACHE_BUCKET resolved and no local staged projections.json at {local} "
            f"— nothing to patch. Run export_draft_board_json.py first, or pass --s3-bucket."
        )
    log.warning(
        "no --s3-bucket/$CACHE_BUCKET — patching the LOCAL staged copy at %s, which may be stale vs "
        "the live prod payload. Fine for local dev; a real publish needs a bucket so this downloads "
        "the CURRENT live file (the shared-export-file discipline).", local,
    )
    return json.loads(local.read_text()), str(local)


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--duckdb", default="quant_sports_intel_models/sports_dbt/sports.duckdb")
    ap.add_argument("--schema", default=MARTS_SCHEMA)
    ap.add_argument("--season", type=int, default=2026,
                    help="the served season directory to patch — fantasy/nfl/<season>/projections.json")
    ap.add_argument("--seasons", default="2019-2025",
                    help="past-season range (inclusive) to assemble the history block from, e.g. "
                         "2019-2025 (default). Every season needs its NF1.5 refined board already "
                         "built locally (run_nf1_5.py) for the actual/ADP piece — a missing one is "
                         "skipped, not fabricated.")
    ap.add_argument("--projections-json", type=Path, default=None,
                    help="dev/test override: patch THIS local projections.json instead of "
                         "downloading fresh. Never use with a real --publish.")
    ap.add_argument("--out", type=Path, default=None, help="override the local staging output dir")
    ap.add_argument("--s3-bucket", default=os.getenv("CACHE_BUCKET"),
                    help="S3 bucket the live projections.json lives in / gets patched in (default "
                         "$CACHE_BUCKET). Resolving a bucket alone does NOT upload — pass --publish.")
    ap.add_argument("--publish", action="store_true",
                    help="NF-D12 PUBLISH GUARD: actually upload the patched projections.json to the "
                         "LIVE prod api-cache. Without this flag the exporter always DRY-RUNS.")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    seasons = _parse_seasons(args.seasons)

    if not Path(args.duckdb).exists():
        raise SystemExit(f"DuckDB not found at {args.duckdb} — build the NFL marts first")

    original, source_desc = _load_live_projections(args.season, args.s3_bucket, args.projections_json)
    log.info("loaded live base from %s (%d players)", source_desc, len(original.get("players", [])))

    import duckdb

    con = duckdb.connect(args.duckdb, read_only=True)
    try:
        history_map = build_history_map(con, seasons, args.schema)
    finally:
        con.close()

    n_past = sum(1 for h in history_map.values() if h["pastSeasons"])
    n_inj = sum(1 for h in history_map.values() if h["injuries"])
    n_missed = sum(1 for h in history_map.values() if h["gamesMissedBySeason"])
    log.info("assembled history for %d players (%d with past-season track record, %d with an injury "
             "report entry, %d with a games-missed count)", len(history_map), n_past, n_inj, n_missed)

    merged = merge_history(original, history_map)
    diff_verify(original, merged)
    log.info("diff-verify OK — the merged payload differs from the live download ONLY in 'history'")

    out_dir = args.out or (_STAGING_OUT / str(args.season))
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "projections.json"
    out_path.write_text(json.dumps(merged, separators=(",", ":")))
    log.info("wrote patched projections.json to %s", out_path)

    _maybe_publish(out_path, args.s3_bucket, args.season, args.publish)
    return 0


def _maybe_publish(patched_path: Path, bucket: str | None, season: int, publish: bool) -> None:
    """NF-D12 guard, single-key variant: uploads ONLY `fantasy/nfl/<season>/projections.json` — never
    the rest of that directory. This script never touches `manifest.json`/`board_*.json` and must not
    risk them on a publish it wasn't asked to make (see the module docstring)."""
    key = f"fantasy/nfl/{season}/projections.json"
    if not bucket:
        if publish:
            raise SystemExit(
                "--publish was passed but NO BUCKET resolved (--s3-bucket / $CACHE_BUCKET is unset "
                "or empty), so nothing would be uploaded and the run would have looked successful. "
                "Re-run with the bucket named explicitly:\n"
                f"  --season {season} --s3-bucket credence-prod-s3-api-cache --publish"
            )
        log.warning(
            "no --s3-bucket / $CACHE_BUCKET — patched projections.json staged locally only at %s; "
            "the History panel stays absent from the live payload until it is uploaded to "
            "s3://<bucket>/%s", patched_path, key,
        )
        return
    if not publish:
        log.info(
            "[DRY-RUN] would upload %s to s3://%s/%s — pass --publish to actually reach the LIVE "
            "prod api-cache", patched_path, bucket, key,
        )
        return
    log.warning("\U0001f6a8 PUBLISHING TO LIVE PROD api-cache — s3://%s/%s (single key, patched)",
                bucket, key)
    import boto3

    s3 = boto3.client("s3", region_name="us-east-1")
    s3.put_object(Bucket=bucket, Key=key, Body=patched_path.read_bytes(), ContentType="application/json")
    log.info("uploaded patched projections.json to s3://%s/%s", bucket, key)


if __name__ == "__main__":
    raise SystemExit(main())
