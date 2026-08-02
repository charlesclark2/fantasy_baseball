"""export_track_record_json.py — NF3.2: land the past-season fantasy football TRACK RECORD (our
projection vs that season's preseason ADP vs the realized outcome) as PUBLIC static JSON — the GTM
"receipts" proof asset.

Per season 2019–2025 (never the current LOCKED season — see `LOCKED_SEASON`): our NF1.5 refined-board
projection vs that season's Fantasy Football Calculator ADP vs the realized fantasy finish, one row per
player, built by `benchmark_scorecard.player_track_record_frame` (the per-player materialization behind
NF-D3's aggregate "adp" scorecard numbers — never a parallel re-derivation of that join).

⚖️ HONEST-CLAIM DISCIPLINE (non-negotiable — see CLAUDE.md / `test_nf1_5b_served_board.py`'s denylist,
reused here): the manifest's headline is built ONLY from the freshly-regenerated NF-D3 scorecard's own
numbers (`--scorecard-json`, produced by `run_benchmark_scorecard.py --projection-source nf1_5`) — never
hand-authored. It never claims "every position", "beats the market", or any superlative the scorecard
itself doesn't support; `build_headline` asserts this at build time (`_CLAIM_DENYLIST`), not just in a
test.

🔒 ENTITLEMENT: this is the PUBLIC half of NF3.2's season-scoped split (past seasons public, the current
season locked behind subscription — enforced in `app/backend/routers/fantasy_public.py`, which reads
what this script writes and NOTHING ELSE). The export is structurally incapable of ever emitting
`LOCKED_SEASON` or later — `_parse_seasons` refuses such a range outright, so a public payload can never
carry the paid product regardless of how this script is invoked.

RUN (LAPTOP, SF-free sports lake):
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.export_track_record_json \
      --duckdb quant_sports_intel_models/sports_dbt/sports.duckdb --seasons 2019-2025

Same NF-D12 dry-run/`--publish` guard as `export_draft_board_json.py`: a resolved `--s3-bucket` /
`$CACHE_BUCKET` alone never uploads — pass `--publish` to actually reach the live prod api-cache.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from quant_sports_intel_models.football.nfl.fantasy import benchmark_scorecard as BS  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy.export_draft_board_json import (  # noqa: E402
    _fnum,
    load_projections_local,
)
from quant_sports_intel_models.football.nfl.fantasy.run_season_projection import (  # noqa: E402
    MARTS_SCHEMA,
    load_realized_season,
)

log = logging.getLogger("nfl.fantasy.export_track_record")

_ARTIFACTS = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/artifacts"
_REPORT_DIR = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy/ablation_results"
_STAGING_OUT = _ARTIFACTS / "track_record_json"

# The current/upcoming season — the PAID product. The public export refuses (hard error, not a
# convention) to ever include this season or later. Kept as one named constant so a future season
# rollover is a one-line change, not a re-audit of every call site.
LOCKED_SEASON = 2026

# Copied verbatim from `test_nf1_5b_served_board.py`'s denylist — a headline built from the scorecard's
# own numbers must never drift into one of these overclaims either.
_CLAIM_DENYLIST = (
    "we beat", "beat the market", "beat consensus", "every position", "all four",
    "our edge", "guaranteed", "more accurate",
)


def _nf1_5_projection(con, season, schema):
    """The NF1.5 refined-board projection for `season` — the SAME served board NF1.5b shipped, read
    from its persisted local artifact. See `run_benchmark_scorecard._nf1_5_projection` (identical, kept
    local here so this script has no CLI-module import)."""
    return load_projections_local(season, source="nf1_5")


def build_player_track_record(con, season, schema) -> pd.DataFrame:
    return BS.player_track_record_frame(
        con, season, schema, project_fn=_nf1_5_projection, load_realized_fn=load_realized_season,
    )


def _inum(v) -> int | None:
    """Null-safe int — `adp_rank` is legitimately missing for a season FFC never archived (e.g. 2025;
    see `player_track_record_frame`'s no-ADP fallback), and `int(pd.NA)` raises."""
    return None if pd.isna(v) else int(v)


def season_records(df: pd.DataFrame) -> list[dict]:
    """The per-player frame -> compact display-ready JSON records for one season."""
    recs = []
    for _, r in df.iterrows():
        recs.append({
            "season": int(r["season"]),
            "playerId": str(r["player_id"]),
            "playerName": str(r["player_name"]),
            "position": str(r["position"]),
            "ourPoints": _fnum(r["our_points"]),
            "ourRank": int(r["our_rank"]),
            "adp": _fnum(r["adp"], 1),
            "adpRank": _inum(r["adp_rank"]),
            "actualPoints": _fnum(r["actual_points"]),
            "actualRank": int(r["actual_rank"]),
            "isFade": bool(r["is_fade"]),
        })
    return recs


def build_headline(scorecard: dict) -> str:
    """The manifest's honest headline — built ONLY from the scorecard JSON's own "adp" aggregate
    numbers, never hand-authored. Raises if the scorecard has no ADP aggregate (nothing honest to say
    yet) or if the templated text somehow trips the overclaim denylist (defense in depth against a
    future edit to this function, not just a test)."""
    agg = (scorecard.get("aggregate") or {}).get("adp")
    if not agg:
        raise ValueError(
            "scorecard JSON has no 'aggregate.adp' — cannot build an honest headline without it. Run "
            "run_benchmark_scorecard.py --projection-source nf1_5 first."
        )
    # `seasons_scored` is EVERY scored season across ALL systems (ecr/espn/sleeper included) — NOT the
    # ADP-specific set `agg['n_seasons']` counts. FFC has no archive for some seasons (2025 confirmed
    # live), so using `seasons_scored` here would print a self-contradicting headline like "6 past
    # seasons (2019-2025)". Derive the span from the seasons that actually carry an 'adp' system.
    adp_seasons = sorted(
        row["season"] for row in (scorecard.get("per_season") or []) if "adp" in (row.get("systems") or {})
    )
    span = f"{adp_seasons[0]}–{adp_seasons[-1]}" if adp_seasons else "the scored seasons"
    parts = [
        f"On average across {agg['n_seasons']} past seasons ({span}), our within-position ordering "
        f"correlation vs realized outcomes is {agg['us_rho_pooled']:.3f}, against ADP's "
        f"{agg['system_rho_pooled']:.3f} (Δρ {agg['delta_rho_pooled']:+.3f})."
    ]
    if agg.get("disagreement_us") is not None and agg.get("disagreement_system") is not None:
        parts.append(
            f"The margin is strongest in our highest-conviction disagreements with ADP: "
            f"{agg['disagreement_us']:.3f} vs ADP's {agg['disagreement_system']:.3f} on those players."
        )
    parts.append(
        "This is a multi-season average, not a promise for any single position or season — see "
        "the per-season, per-position detail below."
    )
    headline = " ".join(parts)
    lowered = headline.lower()
    for banned in _CLAIM_DENYLIST:
        if banned in lowered:
            raise ValueError(f"generated headline contains a banned overclaim phrase {banned!r}: {headline!r}")
    return headline


def _parse_seasons(spec: str) -> list[int]:
    lo_s, _, hi_s = spec.partition("-")
    lo, hi = int(lo_s), int(hi_s or lo_s)
    seasons = list(range(lo, hi + 1))
    locked = [y for y in seasons if y >= LOCKED_SEASON]
    if locked:
        raise SystemExit(
            f"--seasons {spec!r} includes {locked} — the public track-record export refuses to "
            f"ever emit season >= {LOCKED_SEASON} (the current LOCKED, subscriber-only season). Pass a "
            f"range strictly below {LOCKED_SEASON}."
        )
    return seasons


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--duckdb", default="quant_sports_intel_models/sports_dbt/sports.duckdb")
    ap.add_argument("--schema", default=MARTS_SCHEMA)
    ap.add_argument("--seasons", default="2019-2025",
                    help="inclusive season range, e.g. 2019-2025 (default). Every season in the range "
                         "must already have a built nf1_5_season_projections_<year>.parquet — see "
                         "run_nf1_5.py --mode build --projection-season <year>.")
    ap.add_argument("--scorecard-json", type=Path,
                    default=_REPORT_DIR / "nf_d3_benchmark_scorecard_nf1_5.json",
                    help="the FRESH NF-D3 scorecard (nf1_5 projection source) — the single source "
                         "of truth for the manifest's honest headline numbers.")
    ap.add_argument("--out", type=Path, default=None, help="override the local staging output dir")
    ap.add_argument("--s3-bucket", default=os.getenv("CACHE_BUCKET"),
                    help="S3 bucket to upload to (default $CACHE_BUCKET). Uploaded under "
                         "fantasy/nfl/track_record/ where the PUBLIC /fantasy/nfl/track-record/* API "
                         "reads it. Resolving a bucket alone does NOT upload — pass --publish too.")
    ap.add_argument("--publish", action="store_true",
                    help="NF-D12 PUBLISH GUARD: actually upload to the LIVE prod api-cache bucket. "
                         "Without this flag the exporter always DRY-RUNS.")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    seasons = _parse_seasons(args.seasons)

    if not args.scorecard_json.is_file():
        raise SystemExit(
            f"no scorecard JSON at {args.scorecard_json} — run:\n"
            f"  uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_benchmark_scorecard "
            f"--from {seasons[0]} --to {seasons[-1]} --projection-source nf1_5"
        )
    scorecard = json.loads(args.scorecard_json.read_text())
    headline = build_headline(scorecard)
    seasons_with_adp = sorted(
        row["season"] for row in (scorecard.get("per_season") or []) if "adp" in (row.get("systems") or {})
    )

    if not Path(args.duckdb).exists():
        raise SystemExit(f"DuckDB not found at {args.duckdb} — build the NFL marts first")

    out_dir = args.out or _STAGING_OUT
    out_dir.mkdir(parents=True, exist_ok=True)

    import duckdb

    con = duckdb.connect(args.duckdb, read_only=True)
    seasons_written: list[int] = []
    try:
        for y in seasons:
            try:
                df = build_player_track_record(con, y, args.schema)
            except FileNotFoundError as e:
                raise SystemExit(
                    f"season {y}: {e}\nEvery season in --seasons must already have a built NF1.5 "
                    f"refined board — the export never silently drops a season, which would "
                    f"shrink the receipts universe with no error."
                ) from e
            if df.empty:
                log.warning("season %d: 0 scored players (thin ADP/realized overlap) — writing an "
                            "empty season file rather than silently skipping it", y)
            recs = season_records(df)
            path = out_dir / f"season_{y}.json"
            path.write_text(json.dumps(recs, separators=(",", ":")))
            seasons_written.append(y)
            log.info("wrote %s (%d players, %d fades)", path.name, len(recs),
                     sum(1 for r in recs if r["isFade"]))
    finally:
        con.close()

    manifest = {
        "seasons": seasons_written,
        # Seasons whose per-player rows carry a real `adp`/`adpRank` (FFC has no archive for some
        # seasons — 2025 confirmed live — so this can be a strict subset of `seasons`; the frontend
        # uses it to render an honest "ADP unavailable" note rather than a blank/misleading column).
        "seasonsWithAdp": [y for y in seasons_with_adp if y in seasons_written],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "headline": headline,
        "lockedSeason": LOCKED_SEASON,
        "scorecardGeneratedAt": datetime.fromtimestamp(
            args.scorecard_json.stat().st_mtime, tz=timezone.utc
        ).isoformat(),
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    log.info("wrote manifest.json — seasons %s", seasons_written)
    log.info("track-record JSON staged in %s", out_dir)

    _maybe_publish(out_dir, args.s3_bucket, args.publish)
    return 0


def _maybe_publish(out_dir: Path, bucket: str | None, publish: bool) -> None:
    """The same 4-branch NF-D12 publish guard as `export_draft_board_json._maybe_publish` (no
    bucket+no publish=warn; no bucket+publish=SystemExit; bucket+no publish=dry-run report;
    bucket+publish=upload) — kept local rather than cross-imported so this script stays
    self-contained like its template."""
    prefix = "fantasy/nfl/track_record"
    if not bucket:
        if publish:
            raise SystemExit(
                "--publish was passed but NO BUCKET resolved (--s3-bucket / $CACHE_BUCKET is unset "
                "or empty), so nothing would be uploaded and the run would have looked successful. "
                "Re-run with the bucket named explicitly:\n"
                "  --s3-bucket credence-prod-s3-api-cache --publish"
            )
        log.warning(
            "no --s3-bucket / $CACHE_BUCKET — track-record JSON staged locally only; the public "
            "API will 404 until it is uploaded to s3://<bucket>/%s/", prefix,
        )
        return
    files = sorted(out_dir.glob("*.json"))
    if not publish:
        log.info(
            "[DRY-RUN] would upload %d file(s) to s3://%s/%s/ — pass --publish to actually reach "
            "the LIVE prod api-cache: %s",
            len(files), bucket, prefix, ", ".join(p.name for p in files),
        )
        return
    log.warning("\U0001f6a8 PUBLISHING TO LIVE PROD api-cache — s3://%s/%s/ (%d files)",
                bucket, prefix, len(files))
    import boto3

    s3 = boto3.client("s3", region_name="us-east-1")
    for path in files:
        s3.put_object(
            Bucket=bucket, Key=f"{prefix}/{path.name}", Body=path.read_bytes(),
            ContentType="application/json",
        )
    log.info("uploaded %d track-record files to s3://%s/%s/", len(files), bucket, prefix)


if __name__ == "__main__":
    raise SystemExit(main())
