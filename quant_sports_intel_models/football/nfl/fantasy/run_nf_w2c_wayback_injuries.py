"""run_nf_w2c_wayback_injuries.py — NF-W2c: reconstruct PIT-clean 2025 injury rows from Wayback.

PIPELINE: CDX enumeration (nfl/espn/cbs injury pages, Aug 2025–Feb 2026) → snapshot crawl
(bytes, disk-cached, ~170 requests at a polite 2s pause — OPERATOR, ~10 min) → parse (nfl
official report: practice + designations + declared week; espn: designations + per-player game
date; cbs: fetched + retained, parser deferred) → crosswalk names → gsis (lake
`stats_player_week` 2025, the adp_source name-normalization) → per-(player, week) admissibility
(capture_ts STRICTLY BEFORE the player's own gameday 00:00 UTC, gamedays from the W2b matrix)
→ the NF-W0a §13 PIT gate over every admissible row (fail-closed) → coverage + lake-agreement
measurement → artifacts. `--land` (separate, operator, after review) appends the rows to the
immutable NF-W0a store (`pit.store.append_captures`, source `wayback_injuries`).

RUN (LAPTOP — network to web.archive.org + the S3 lake read-only):

    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w2c_wayback_injuries --enumerate
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w2c_wayback_injuries --crawl --build
    uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_w2c_wayback_injuries --land
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from quant_sports_intel_models.football.nfl.fantasy import wayback_injury_source as WB  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy import adp_source as ADP  # noqa: E402
from quant_sports_intel_models.football.nfl.pit import leakage_guard as LG  # noqa: E402

log = logging.getLogger("nfl.fantasy.nf_w2c")

_FANTASY = _PROJECT_ROOT / "quant_sports_intel_models/football/nfl/fantasy"
_REPORT_DIR = _FANTASY / "ablation_results"
#: `*_cache/` under artifacts is gitignored by the standing NFL-fantasy cache rule.
_CACHE = _FANTASY / "artifacts" / "wayback_injuries_cache"
_ARTIFACT = _FANTASY / "artifacts" / "nf_w2c_wayback_injuries_2025.parquet"
MODELED_POSITIONS = ("QB", "RB", "WR", "TE")


def enumerate_captures() -> pd.DataFrame:
    frames = []
    for source, pattern in WB.CDX_TARGETS:
        caps = WB.cdx_captures(pattern, _CACHE, name=source)
        df = pd.DataFrame(caps)
        df["source"] = source
        frames.append(df)
        log.info("%s: %d captures", source, len(df))
    return pd.concat(frames, ignore_index=True)


def crawl(caps: pd.DataFrame, limit: int | None = None) -> int:
    """Fetch every enumerated snapshot into the cache. A snapshot the archive cannot replay
    (or that keeps failing) is SKIPPED and counted — one bad capture costs only its own
    coverage, never the crawl (the build's missing-cache warning stays the reconciliation)."""
    n = failed = 0
    rows = caps if limit is None else caps.head(limit)
    for _, r in rows.iterrows():
        try:
            WB.fetch_snapshot_bytes(r["timestamp"], r["url"], _CACHE)
            n += 1
        except (WB.SnapshotUnavailable, RuntimeError) as exc:
            failed += 1
            log.warning("skipping snapshot %s %s: %s", r["timestamp"], r["url"],
                        str(exc)[:120])
        if (n + failed) % 25 == 0:
            log.info("crawled %d/%d snapshots (%d unavailable)", n + failed, len(rows), failed)
    if failed:
        log.warning("crawl complete with %d/%d snapshots UNAVAILABLE — their coverage is "
                    "simply absent (never zero-filled)", failed, len(rows))
    return n


def parse_cached(caps: pd.DataFrame) -> pd.DataFrame:
    frames, skipped = [], 0
    for _, r in caps.iterrows():
        if r["source"] == "cbs":
            continue  # fetched + retained; parser deferred (carded)
        key = f"{r['timestamp']}_" + __import__("re").sub(
            r"[^A-Za-z0-9]+", "_", r["url"])[:80]
        f = _CACHE / f"snap_{key}.bin"
        if not f.exists():
            skipped += 1
            continue
        try:
            text = WB.snapshot_text(f.read_bytes())
            df = WB.stamped_rows_from_capture(r["source"], r["timestamp"], text)
        except ValueError as exc:
            log.warning("snapshot %s refused: %s", f.name, str(exc)[:120])
            continue
        if not df.empty:
            frames.append(df)
    if skipped:
        log.warning("%d enumerated snapshots not in the cache — run --crawl first "
                    "(coverage below is a FLOOR, not the ceiling)", skipped)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def _gamedays_2025() -> pd.DataFrame:
    """(gsis_id, week, gameday, full name, position) for 2025 from the W2b matrix (cache hit;
    the PIT gate re-runs inside — the wired≠invoked rule)."""
    from quant_sports_intel_models.football.nfl.fantasy.run_nf_w2b_injury_rate_bakeoff import (
        SEASONS, build_matrix_w2b,
    )
    feat, _ = build_matrix_w2b(SEASONS)
    sub = feat[(feat["season"] == 2025) & feat["_target_gameday"].notna()]
    return sub[["gsis_id", "week", "position", "_target_gameday"]].drop_duplicates()


def build(caps: pd.DataFrame) -> dict:
    parsed = parse_cached(caps)
    if parsed.empty:
        raise SystemExit("no parsed rows — nothing cached? run --crawl first (NF1.7 (a): an "
                         "empty build must never be recorded as a measured null)")
    log.info("parsed %d capture-stamped rows from %d snapshots",
             len(parsed), parsed["capture_wayback"].nunique())

    # gsis crosswalk (name+position, adp_source's proven normalization, lake-backed)
    from quant_sports_intel_models.football.nfl.ingest.query_lake import _connect, delta
    con = _connect()
    con.sql(f"""create or replace temp view fct_player_week as
        select player_id, player_display_name as player_name, position, season,
               (coalesce(attempts,0)+coalesce(carries,0)+coalesce(targets,0)) > 0 as played_flag
        from {delta('stats_player_week')}
        where season = {WB.SEASON}""")
    xw = ADP.attach_gsis(con, parsed, WB.SEASON, schema="temp.main")
    stamped = xw[xw["player_id"].notna()].copy()
    log.info("crosswalk: %d/%d rows resolved to a gsis id", len(stamped), len(parsed))

    # week attribution + the player's own gameday
    gd = _gamedays_2025().rename(columns={"gsis_id": "player_id"})
    gd["gameday_iso"] = pd.to_datetime(gd["_target_gameday"]).dt.date.astype(str)
    nfl_rows = stamped[stamped["source"] == "nfl"].merge(
        gd.rename(columns={"week": "declared_week"})[
            ["player_id", "declared_week", "gameday_iso"]],
        on=["player_id", "declared_week"], how="inner")
    nfl_rows["week"] = nfl_rows["declared_week"]
    espn_rows = stamped[stamped["source"] == "espn"].merge(
        gd[["player_id", "week", "gameday_iso"]],
        left_on=["player_id", "game_date_hint"], right_on=["player_id", "gameday_iso"],
        how="inner")
    rows = pd.concat([nfl_rows, espn_rows], ignore_index=True)

    # admissibility: capture strictly before the player's own gameday 00:00 UTC
    cap_ts = pd.to_datetime(rows["capture_ts"], utc=True)
    gameday_utc = pd.to_datetime(rows["gameday_iso"]).dt.tz_localize("UTC")
    rows = rows[cap_ts < gameday_utc].copy()
    # latest admissible capture per (player, week, source); official nfl wins field conflicts
    rows = (rows.sort_values(["capture_ts"])
                .drop_duplicates(["player_id", "week", "source"], keep="last"))
    log.info("%d admissible stamped (player, week, source) rows", len(rows))

    # ── the §13 PIT gate over every admissible row, fail-closed, per (week, gameday) ──────────
    checked = dropped = 0
    kept = []
    for (week, gameday), grp in rows.groupby(["week", "gameday_iso"]):
        projection_ts = f"{gameday}T00:00:00+00:00"
        records = []
        for _, r in grp.iterrows():
            payload = f"{WB.SEASON}|{int(week)}|{r['player_id']}|{r['source']}|{r['capture_wayback']}"
            records.append({
                "capture_source": WB.CAPTURE_SOURCE,
                "capture_id": payload,
                "subject_key": payload,
                "payload_sha256": hashlib.sha256(payload.encode()).hexdigest(),
                "record_tier": "injury",
                "feature_timestamp": r["capture_ts"],
                "source_timestamp": None,
                "source_timestamp_absent_reason": (
                    "wayback page publishes no per-row vendor as-of; the archive capture "
                    "instant is the as-of bound"),
                "capture_timestamp": r["capture_ts"],
                "vendor_release_timestamp": None,
                "ingestion_timestamp": r["capture_ts"],
                "is_rolling_window": False,
            })
        checked += len(records)
        try:
            LG.assert_point_in_time(records, projection_ts, store_index={})
            kept.append(grp)
        except LG.LeakageRejection as exc:
            dropped += len(grp)
            log.warning("PIT gate dropped week %s gameday %s (%d rows): %s", week, gameday,
                        len(grp), sorted({f.reason.name for f in exc.findings}))
    final = pd.concat(kept, ignore_index=True) if kept else pd.DataFrame()
    log.info("PIT gate: %d records checked, %d rows dropped", checked, dropped)

    # ── measurement: coverage + agreement vs the stampless lake designations ──────────────────
    from quant_sports_intel_models.football.nfl.ingest.query_lake import q
    lake = q(f"""select week, gsis_id, position, lower(report_status) as lake_status
                 from {delta('injuries')} where season = {WB.SEASON}
                 and game_type = 'REG' and gsis_id is not null""")
    lake_m = lake[lake["position"].isin(MODELED_POSITIONS)]
    fin_m = final[final["position_x" if "position_x" in final.columns else "position"]
                  .isin(MODELED_POSITIONS)] if not final.empty else final
    per_week = []
    for week in sorted(lake_m["week"].unique()):
        lw = lake_m[lake_m["week"] == week]
        fw = fin_m[fin_m["week"] == week] if not fin_m.empty else fin_m
        merged = lw.merge(
            fw.rename(columns={"player_id": "gsis_id"})[
                ["gsis_id", "report_status", "source", "capture_ts"]],
            on="gsis_id", how="left") if not fin_m.empty else lw.assign(
                report_status=None, source=None, capture_ts=None)
        both = merged[merged["report_status"].notna() & merged["lake_status"].notna()]
        agree = float((both["report_status"] == both["lake_status"]).mean()) if len(both) else None
        per_week.append({
            "week": int(week),
            "lake_listed_modeled": int(len(lw)),
            "stamped_admissible": int(merged["capture_ts"].notna().sum()),
            "coverage": round(float(merged["capture_ts"].notna().mean()), 4),
            "designation_rows_compared": int(len(both)),
            "designation_agreement": None if agree is None else round(agree, 4),
        })
    covered_weeks = sum(1 for w in per_week if w["stamped_admissible"] > 0)
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "story": "NF-W2c", "season": WB.SEASON,
        "snapshots_enumerated": int(len(caps)),
        "snapshots_parsed": int(parsed["capture_wayback"].nunique()),
        "rows_parsed": int(len(parsed)),
        "rows_crosswalked": int(len(stamped)),
        "rows_admissible": int(len(rows)),
        "pit_records_checked": checked, "pit_rows_dropped": dropped,
        "weeks_with_any_stamped_row": covered_weeks,
        "per_week": per_week,
    }
    if not final.empty:
        final.to_parquet(_ARTIFACT, index=False)
        summary["artifact"] = str(_ARTIFACT.relative_to(_PROJECT_ROOT))
    (_REPORT_DIR / "nf_w2c_wayback_injuries.json").write_text(
        json.dumps(summary, indent=2, default=str))
    md = ["# NF-W2c — PIT-clean 2025 injury reconstruction from Wayback captures", "",
          f"Generated {summary['generated_at']}. Stamps are Wayback capture instants "
          f"(third-party-attested); admissibility = capture strictly before the player's own "
          f"gameday 00:00 UTC; every row through the NF-W0a §13 gate.", "",
          pd.DataFrame(per_week).to_markdown(index=False), "",
          "```json", json.dumps({k: v for k, v in summary.items() if k != "per_week"},
                                indent=2, default=str), "```"]
    (_REPORT_DIR / "nf_w2c_wayback_injuries.md").write_text("\n".join(md))
    log.info("→ %s + .md (%d weeks with stamped rows)", "nf_w2c_wayback_injuries.json",
             covered_weeks)
    return summary


def land() -> dict:
    """Append the built rows to the immutable NF-W0a store (OPERATOR, after review)."""
    from quant_sports_intel_models.football.nfl.pit import store
    from quant_sports_intel_models.football.nfl.pit.timestamps import CaptureStamps
    df = pd.read_parquet(_ARTIFACT)
    rows = []
    for _, r in df.iterrows():
        subject = f"{WB.SEASON}|{int(r['week'])}|{r['player_id']}|{r['source']}"
        payload = {k: (None if pd.isna(v) else v) for k, v in r.items()}
        stamps = CaptureStamps.build(
            capture_source=WB.CAPTURE_SOURCE, subject_key=subject,
            checkpoint=str(r["capture_wayback"]), payload=payload,
            feature_timestamp=r["capture_ts"], capture_timestamp=r["capture_ts"],
            source_timestamp=None, vendor_release_timestamp=None,
        )
        row = stamps.as_dict()
        row.update({
            "record_tier": "injury",
            "source_timestamp_absent_reason": (
                "wayback page publishes no per-row vendor as-of; the archive capture instant "
                "is the as-of bound"),
            "season": WB.SEASON, "week": int(r["week"]), "gsis_id": r["player_id"],
            "full_name": r.get("player_name"), "position": r.get("position"),
            "report_status": r.get("report_status"), "practice_status": r.get("practice_status"),
            "payload": payload,
        })
        rows.append(row)
    manifest = store.append_captures(rows, source=WB.CAPTURE_SOURCE)
    log.info("landed: %s", {k: v for k, v in manifest.items() if k != "revisions"})
    return manifest


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="NF-W2c Wayback injury reconstruction")
    ap.add_argument("--enumerate", action="store_true", dest="enumerate_only")
    ap.add_argument("--crawl", action="store_true")
    ap.add_argument("--limit", type=int, default=None, help="crawl at most N snapshots (smoke)")
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--land", action="store_true")
    args = ap.parse_args(argv)

    caps = enumerate_captures()
    if args.enumerate_only:
        print(caps.groupby("source")["timestamp"].agg(["count", "min", "max"]).to_string())
        return 0
    if args.crawl:
        n = crawl(caps, limit=args.limit)
        log.info("crawl complete: %d snapshots cached", n)
    if args.build:
        summary = build(caps)
        print(json.dumps({k: v for k, v in summary.items() if k != "per_week"}, indent=2))
    if args.land:
        land()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
