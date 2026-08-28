#!/usr/bin/env python
"""ncaaf_odds_live_red_proof.py — prove every NCAAF-ODDS-LIVE guard FAILS on a deliberate break.

A guard that cannot go red is not a guard (NF1.7 (a) / INC-38 / INC-39). One deliberate defect at
a time against the real source; each must produce a failure.

Guarded against the three ways a RED proof itself lies: the mutation never LANDED (#682), the
anchor was not UNIQUE so it landed on the wrong symbol (#815 sibling — a false VACUITY report is
the dangerous direction), and it landed but did not move the ASSERTED predicate (#815). Stale
backups from a killed run are restored at start-up (E11.26).

Run:  uv run python betting_ml/tests/ncaaf_odds_live_red_proof.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_TEST = "betting_ml/tests/test_ncaaf_odds_live.py"

CAPTURE = _REPO / "quant_sports_intel_models/football/ncaaf/ingest/odds_live_capture.py"
BAKEOFF = _REPO / "quant_sports_intel_models/football/ncaaf/models/bakeoff_ncaaf_game.py"
SOURCES = _REPO / "quant_sports_intel_models/football/ncaaf/ingest/sources.py"
PAYLOADS = _REPO / "quant_sports_intel_models/football/ncaaf/serving/payloads.py"
JOB = _REPO / "pipeline/jobs/sports_ncaaf_odds_live_job.py"
SCHED = _REPO / "pipeline/schedules/sports_odds_capture_schedules.py"
WRITER = _REPO / "scripts/write_ncaaf_serving_store.py"

BREAKS: list[tuple[str, Path, str, str, str, str | None]] = [
    # ── the table separation: the break that could move a recorded result ────────────────────
    ("the live feed writes into the CLV benchmark table",
     CAPTURE, 'ODDS_LIVE_SOURCE = "odds_ncaaf_live"',
     'ODDS_LIVE_SOURCE = "odds_ncaaf_historical"',
     "writes_its_own_table or live_source_name_matches", '"odds_ncaaf_live"'),

    ("the live columns land in the DEFAULT staging frame (and become model features)",
     BAKEOFF,
     "def build_clv_staging(min_year: int = 2020, *, with_t1: bool = False,\n"
     "                      with_live: bool = False) -> pd.DataFrame:",
     "def build_clv_staging(min_year: int = 2020, *, with_t1: bool = False,\n"
     "                      with_live: bool = True) -> pd.DataFrame:",
     "default_frame_cannot_see_the_live_feed", None),

    ("the staging read points at a live table nothing writes",
     BAKEOFF, '_ODDS_LIVE_SOURCE = "odds_ncaaf_live"', '_ODDS_LIVE_SOURCE = "odds_live"',
     "live_source_name_matches", '_ODDS_LIVE_SOURCE = "odds_ncaaf_live"'),

    # ── the overwrite landmine ───────────────────────────────────────────────────────────────
    ("the merge key drops the instant, collapsing the movement history",
     CAPTURE, 'return (d.get("id"), d.get("_snapshot_ts"))', 'return (d.get("id"), None)',
     "second_row or merge_key_is_the_event", None),

    ("the writer plain-overwrites the season instead of merging (the replaceWhere landmine)",
     CAPTURE,
     "    existing = _existing_raw_rows(season, bucket=bucket, local_root=local_root)",
     "    existing = None",
     "never_deletes_a_prior_season or second_snapshot", None),

    ("an unreadable partition is guessed EMPTY and the season is overwritten",
     CAPTURE,
     "    df = query_lake.query_or_missing(",
     "    try:\n        df = query_lake.query_or_missing(",
     "unreadable_existing_partition_raises", None),

    # ── in-play prices ───────────────────────────────────────────────────────────────────────
    ("the pre-kickoff filter is removed, letting in-play prices into the store",
     CAPTURE, "        if c is None or not snapshot < c:", "        if False:",
     "already_underway or unreadable_kickoff_is_dropped or defences_are_independent",
     "if c is None or not snapshot < c:"),

    ("a game kicking off at exactly the snapshot instant is admitted",
     CAPTURE, "        if c is None or not snapshot < c:", "        if c is None or not snapshot <= c:",
     "already_underway", None),

    ("an unreadable kickoff is admitted rather than dropped",
     CAPTURE, "        if c is None or not snapshot < c:", "        if c is not None and not snapshot < c:",
     "unreadable_kickoff_is_dropped", None),

    ("the request stops excluding started games",
     SOURCES, '    if commence_from:\n        params["commenceTimeFrom"] = commence_from',
     "    if False:\n        pass",
     "request_itself_excludes_started_games", 'params["commenceTimeFrom"] = commence_from'),

    ("the capture stops passing the snapshot instant as the request bound",
     CAPTURE, "    return _odds_ncaaf(ctx, current_season(), commence_from=_iso(_now(now)))",
     "    return _odds_ncaaf(ctx, current_season())",
     "actually_passes_the_snapshot_instant", "commence_from=_iso"),

    # ── the tier ─────────────────────────────────────────────────────────────────────────────
    ("the dense window collapses so a game-day tick is only 6-hourly",
     CAPTURE, "DENSE_WINDOW_HOURS = 24", "DENSE_WINDOW_HOURS = 0",
     "inside_the_dense_window or boundary_of_the_dense_window", None),

    ("the baseline tier fires every hour, quadrupling the credit spend",
     CAPTURE, "BASELINE_EVERY_H = 6", "BASELINE_EVERY_H = 1",
     "outside_the_dense_window or off_season_tick", None),

    ("a skipped tick stops saying why",
     CAPTURE,
     '    return False, (f"skip: UTC hour {now.hour} is not a {baseline_every_h}-hourly tick and no "',
     '    return False, (f"" or (f"skip: UTC hour {now.hour} is not a {baseline_every_h}-hourly tick and no "',
     "skipped_tick_says_why", None),

    ("the op re-implements the tier instead of delegating to the shared rule",
     JOB, "        manifest = run_live_capture()",
     "        from quant_sports_intel_models.football.ncaaf.ingest.odds_live_capture import "
     "should_capture  # noqa\n        manifest = run_live_capture()",
     "tier_is_pure", None),

    # ── season placement, serving, orchestration ─────────────────────────────────────────────
    ("a January bowl is filed under the following season",
     CAPTURE, "    return ts.year if ts.month >= 7 else ts.year - 1", "    return ts.year",
     "january_bowl_is_filed", None),

    ("the serving read stops asking for the live leg",
     WRITER, "clv = build_clv_staging(min_year=int(season), with_t1=True, with_live=True)",
     "clv = build_clv_staging(min_year=int(season), with_t1=True)",
     "serving_read_opts_into_the_live_leg",
     "build_clv_staging(min_year=int(season), with_t1=True, with_live=True)"),

    ("a stale observation beats a fresher one (freshest-wins inverted)",
     PAYLOADS, "    eligible.sort(key=lambda e: (e[0], -e[1]))\n    _, _, source, line = eligible[-1]",
     "    eligible.sort(key=lambda e: (e[0], -e[1]))\n    _, _, source, line = eligible[0]",
     "live_line_wins_when_it_is_the_freshest", None),

    ("a post-kickoff LIVE price is served as a pre-game line",
     PAYLOADS, "        if not snapshot < kickoff:", "        if False:",
     "live_line_after_kickoff_is_refused", "if not snapshot < kickoff:"),

    ("the accent fold leaks into the DEFAULT leg, changing the CLV mart population",
     BAKEOFF, "             accent_fold: bool = False) -> str:",
     "             accent_fold: bool = True) -> str:",
     "accent_fold_is_live_leg_only", None),

    ("the paid schedule ships RUNNING",
     SCHED,
     "    default_status=DefaultScheduleStatus.STOPPED,  # ⛔ operator-gated — paid feed",
     "    default_status=DefaultScheduleStatus.RUNNING,",
     "paid_schedule_ships_stopped", None),

    ("a second cron appears for the same logical job",
     SCHED, 'NCAAF_ODDS_LIVE_CRON = "0 * * 8-12,1 *"',
     'NCAAF_ODDS_LIVE_CRON = "0 * * 8-12,1 *"\nNCAAF_ODDS_LIVE_DENSE_CRON = "*/30 * * 8-12,1 *"',
     "exactly_one_cron", None),

    ("a capture that stores ZERO events passes silently",
     JOB, '    if not manifest.get("events"):', "    if False:",
     "logs_on_both_branches", 'if not manifest.get("events"):'),

    ("the capture stops being WARN tier and fails its job",
     JOB, "    except Exception as exc:  # noqa: BLE001 — WARN tier: a market line never costs a job",
     "    except Exception as exc:  # noqa: BLE001\n        raise",
     "warn_tier_and_never_fails", None),
]


def _run(selector: str) -> bool:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", _TEST, "-q", "-k", selector, "--no-header",
         "-p", "no:cacheprovider"], cwd=_REPO, capture_output=True, text=True)
    if "no tests ran" in proc.stdout or "collected 0 items" in proc.stdout:
        print(f"      ⚠️  selector {selector!r} matched NO tests — the proof would be vacuous")
        return False
    return proc.returncode != 0


def main() -> int:
    backups = {p: p.with_suffix(p.suffix + ".redproof.bak") for p in {b[1] for b in BREAKS}}
    for original, backup in backups.items():
        if backup.exists():
            print(f"⚠️  restoring stale backup for {original.name}")
            original.write_text(backup.read_text())
            backup.unlink()

    print("baseline (all guards, unbroken source) …", end=" ", flush=True)
    base = subprocess.run([sys.executable, "-m", "pytest", _TEST, "-q", "--no-header",
                           "-p", "no:cacheprovider"], cwd=_REPO, capture_output=True, text=True)
    if base.returncode != 0:
        print("FAILED — fix the suite before RED-proving it")
        print(base.stdout[-3000:])
        return 1
    print("green ✅")

    reds = 0
    for label, path, old, new, selector, must_vanish in BREAKS:
        src = path.read_text()
        occurrences = src.count(old)
        if occurrences != 1:
            print(f"❌ {label}\n      anchor occurs {occurrences}× in {path.name} — a non-unique "
                  "anchor can land the break on the WRONG symbol (#815)")
            continue
        backup = backups[path]
        backup.write_text(src)
        try:
            path.write_text(src.replace(old, new, 1))
            landed = path.read_text()
            assert landed != src, f"the mutation for {label!r} did not land on disk"
            if must_vanish is not None and must_vanish in landed:
                print(f"❌ {label}\n      the break landed but {must_vanish!r} is still present — "
                      "it would not move the asserted predicate (#815)")
                continue
            went_red = _run(selector)
        finally:
            path.write_text(backup.read_text())
            backup.unlink()
        print(("🔴 RED  " if went_red else "❌ GREEN") + f"  {label}")
        reds += int(went_red)

    print(f"\n{reds}/{len(BREAKS)} deliberate breaks were caught.")
    return 0 if reds == len(BREAKS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
