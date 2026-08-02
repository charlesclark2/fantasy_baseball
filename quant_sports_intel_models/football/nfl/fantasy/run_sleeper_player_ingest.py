"""run_sleeper_player_ingest.py — NF-C0c: publish the Sleeper player-name resolution artifact.

Fetches Sleeper's `v1/players/nfl` dump (via `sleeper_players_source`), resolves `gsis_id` (native
first, name+position crosswalk fallback for skill positions only), and stages a SLIM
`{sleeper_player_id: {name, position, team, gsis_id?}}` JSON that the API reads to turn an imported
Sleeper roster's bare player ids into real names (see `app.backend.services.platform_import.
sleeper_players` for the read side — a single memoized load per Lambda instance, never per-import).

⏱️ CADENCE — there is no NFL-fantasy Dagster scheduler (unlike the MLB box pipeline); this is a
manual `run_*.py` product like every other NFL fantasy ingest. Sleeper's own guidance is "fetch this
at most once a day" — the player universe changes slowly (trades, cuts, rookies added around the
draft), so the cheapest correct cadence is: run this ONCE alongside each
`export_draft_board_json.py --publish` session (before or after — order does not matter, they write
different S3 keys), and re-run it standalone if roster names go stale between board publishes (e.g.
right after a trade deadline). Running it more than once a day is simply wasted fetches against
Sleeper's guidance, never a correctness issue.

🔒 PUBLISH GUARD (mirrors `export_draft_board_json.py`'s NF-D12 gate): resolving a bucket
(--s3-bucket / $CACHE_BUCKET) does NOT upload by itself — pass --publish. The default is always a
DRY-RUN that stages the JSON locally and prints exactly what would upload. --publish with no bucket
is a hard error (NF1.7's landmine: a silent no-op that looks like a successful publish).

    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_sleeper_player_ingest \\
      --duckdb quant_sports_intel_models/sports_dbt/sports.duckdb \\
      --s3-bucket credence-prod-s3-api-cache --publish
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from quant_sports_intel_models.football.nfl.fantasy import sleeper_players_source as SP  # noqa: E402

log = logging.getLogger("nfl.fantasy.sleeper_player_ingest")

_S3_KEY = "fantasy/nfl/sleeper/players.json"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="NF-C0c — publish the Sleeper player name-resolution artifact")
    ap.add_argument("--duckdb", default="quant_sports_intel_models/sports_dbt/sports.duckdb")
    ap.add_argument("--schema", default="main_nfl_marts")
    ap.add_argument("--season", type=int, default=None,
                     help="default: current_season() (clock-derived NFL roll-forward season)")
    ap.add_argument("--refresh", action="store_true", help="re-fetch Sleeper even if today's cache exists")
    ap.add_argument("--out-dir", default=None,
                     help="local staging dir for players.json (default: alongside the fetch cache)")
    ap.add_argument("--s3-bucket", default=None,
                     help="S3 bucket to publish to (default $CACHE_BUCKET). A bucket alone does NOT "
                          "upload — pass --publish too (see below).")
    ap.add_argument("--publish", action="store_true",
                     help="actually upload to the live prod api-cache. Without this, the run always "
                          "prints exactly what WOULD upload, even if --s3-bucket / $CACHE_BUCKET "
                          "resolves to the real bucket.")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s")
    if not Path(args.duckdb).exists():
        ap.error(f"DuckDB not found at {args.duckdb} — build the NFL marts first")

    import os

    from quant_sports_intel_models.football.nfl.ingest.sources import current_season

    season = args.season if args.season is not None else current_season()
    bucket = args.s3_bucket or os.getenv("CACHE_BUCKET")

    import duckdb

    con = duckdb.connect(args.duckdb, read_only=True)
    try:
        df = SP.fetch_all_sleeper_players(refresh=args.refresh)
        df = SP.attach_gsis(con, df, season, schema=args.schema)
    finally:
        con.close()

    cov = SP.coverage(df)
    log.info(
        "Sleeper player artifact: season=%s %d total rows, skill overall %d/%d matched (%.1f%%), "
        "skill rookies %d/%d matched (%.1f%%)",
        season, cov["n_rows"],
        cov["skill_overall"]["n_matched"], cov["skill_overall"]["n"], cov["skill_overall"]["pct_matched"],
        cov["skill_rookies"]["n_matched"], cov["skill_rookies"]["n"], cov["skill_rookies"]["pct_matched"],
    )

    artifact = SP.slim_artifact(df)
    out_dir = Path(args.out_dir) if args.out_dir else SP._DEFAULT_CACHE / "staged"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "players.json"
    out_path.write_text(json.dumps(artifact))
    log.info("staged %d players → %s", len(artifact), out_path)

    _maybe_publish(out_path, bucket, args.publish)

    print(json.dumps({"season": season, "n_players": len(artifact), **cov}, indent=2, default=float))
    return 0


def _maybe_publish(out_path: Path, bucket: "str | None", publish: bool) -> None:
    """Gate the S3 upload behind an explicit --publish (mirrors export_draft_board_json.py's NF-D12
    guard). Without a bucket the artifact is only staged locally; with a bucket but no --publish this
    is a dry-run report; --publish with no bucket is a hard error rather than a silent no-op."""
    if not bucket:
        if publish:
            raise SystemExit(
                "--publish was passed but NO BUCKET resolved (--s3-bucket / $CACHE_BUCKET is unset "
                "or empty), so nothing would be uploaded and the run would have looked successful. "
                "Re-run with the bucket named explicitly:\n"
                "  --s3-bucket credence-prod-s3-api-cache --publish"
            )
        log.warning(
            "no --s3-bucket / $CACHE_BUCKET — artifact staged locally only; roster name resolution "
            "will keep showing IDs until it is uploaded to s3://<bucket>/%s", _S3_KEY,
        )
        return
    if not publish:
        log.info(
            "[DRY-RUN] would upload %s to s3://%s/%s — pass --publish to actually reach the LIVE "
            "prod api-cache", out_path.name, bucket, _S3_KEY,
        )
        return
    log.warning("🚨 PUBLISHING TO LIVE PROD api-cache — s3://%s/%s", bucket, _S3_KEY)
    import boto3

    # Plain (key-less) client — instance-role / AWS_PROFILE safe. us-east-1 matches the cache
    # bucket's region (app.backend.services.s3_cache / export_draft_board_json._upload_to_s3) —
    # pinned so a laptop AWS_DEFAULT_REGION=us-east-2 (the ML-artifacts bucket) can't misroute it.
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.put_object(Bucket=bucket, Key=_S3_KEY, Body=out_path.read_bytes(), ContentType="application/json")
    log.info("published → s3://%s/%s", bucket, _S3_KEY)


if __name__ == "__main__":
    raise SystemExit(main())
