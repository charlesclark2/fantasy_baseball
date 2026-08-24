#!/usr/bin/env python
"""ncaaf_p3_1_red_proof.py — prove every NCAAF-P3.1 guard actually FAILS on a deliberate break.

A guard that cannot go red is not a guard (NF1.7 (a) / INC-38 / INC-39). This harness applies one
deliberate defect at a time to the real source, runs the named test(s), and REQUIRES a failure.

THREE WAYS A RED PROOF ITSELF LIES, and each is guarded here because this repo has hit all three:

  1. **THE MUTATION NEVER LANDED** (#682) — a shell-quoting or anchor bug edits nothing and the run
     comes back green, reported as "the guard is vacuous". Every break asserts the file CHANGED.
  2. **THE ANCHOR WAS NOT UNIQUE** (#815 sibling) — two functions with byte-identical tails send a
     single-occurrence replace to the WRONG one, and the guard under test never sees its mutation.
     A false VACUITY report is the dangerous direction: it reads as a finding and invites weakening
     a correct guard. Every anchor is asserted to occur EXACTLY ONCE.
  3. **IT LANDED BUT DID NOT MOVE THE ASSERTED PREDICATE** (#815) — a rename that still satisfies
     an `x in src` check. Where a break is meant to REMOVE a token, its absence is asserted too.

⚠️ Restores happen in a `finally`, and any stale backup from a previous killed run is restored at
START-UP — a source-mutating harness's worst case is being killed mid-mutation, which leaves the
deliberate break on disk (E11.26).

Run:  uv run python betting_ml/tests/ncaaf_p3_1_red_proof.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_TEST = "betting_ml/tests/test_ncaaf_p3_1_serving.py"

CONTRACT = _REPO / "app/backend/models/ncaaf.py"
PAYLOADS = _REPO / "quant_sports_intel_models/football/ncaaf/serving/payloads.py"
WRITER = _REPO / "scripts/write_ncaaf_serving_store.py"
ROUTER = _REPO / "app/backend/routers/ncaaf.py"
SERVICE = _REPO / "app/backend/services/ncaaf_serving.py"
GUARDRAILS = _REPO / "app/backend/services/cost_guardrails.py"
SNAP_JOB = _REPO / "pipeline/jobs/sports_ncaaf_prediction_snapshot_job.py"

#: (label, file, old, new, pytest -k selector, token that must DISAPPEAR or None)
BREAKS: list[tuple[str, Path, str, str, str, str | None]] = [
    ("a pick field is declared on the served contract",
     CONTRACT,
     "    home_spread: float | None = None",
     "    home_spread: float | None = None\n    best_pick: str | None = None",
     "no_pick_or_edge_field_exists", None),

    ("the served token list forks from the lake-row one",
     CONTRACT,
     '    "edge", "pick", "bet", "wager", "win_rate", "roi", "clv", "recommend", "kelly", "alpha",',
     '    "edge", "bet", "wager", "win_rate", "roi", "clv", "recommend", "kelly", "alpha",',
     "forbidden_token_list_matches", '"edge", "pick", "bet"'),

    ("the served quantile ladder drifts from what the snapshot persists",
     PAYLOADS,
     "QUANTILE_LEVELS: tuple[float, ...] = (0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95)",
     "QUANTILE_LEVELS: tuple[float, ...] = (0.05, 0.25, 0.50, 0.75, 0.95)",
     "quantile_ladder_matches", "0.10, 0.25, 0.50, 0.75, 0.90"),

    ("the game-day is taken from the UTC date instead of the LA day (INC-22)",
     PAYLOADS,
     "    return current_game_date(now=ts.to_pydatetime()).isoformat()",
     "    return str(commence_time)[:10]",
     "la_game_day or slates_are_split or default_slate", "current_game_date(now=ts"),

    ("the serving layer keys on season_order_week (the alias landmine)",
     PAYLOADS,
     '    ts = pd.to_datetime(commence_time, utc=True, errors="coerce")',
     '    season_order_week = 1  # noqa\n    ts = pd.to_datetime(commence_time, utc=True, errors="coerce")',
     "keys_on_season_order_week", None),

    ("a NaN is fabricated into a 0.0 instead of staying NULL",
     PAYLOADS,
     "    return None if out != out else out  # NaN",
     "    return 0.0 if out != out else out  # NaN",
     "nan_becomes_null", None),

    ("both market-unavailable causes render identically",
     PAYLOADS,
     'MARKET_REASON_READ_FAILED = "market_read_failed"',
     'MARKET_REASON_READ_FAILED = "no_line_captured_for_this_kickoff"',
     "market_line_names_its_cause", '"market_read_failed"'),

    ("the writer succeeds quietly when NEITHER store took a blob (HALT tier removed)",
     WRITER,
     '            raise RuntimeError(\n                f"NCAAF serving write reached NEITHER store',
     '            log.warning(\n                f"NCAAF serving write reached NEITHER store',
     "halts_when_neither_store", None),

    ("a no-op writes to the serving store anyway",
     WRITER,
     '        result.update(status="no_snapshots", n_games=0, n_game_days=0, keys_written=0)\n        return result',
     '        raw = pd.DataFrame()',
     "no_snapshots_is_a_no_op", None),

    ("the market read stops being WARN tier and takes the slate down with it",
     WRITER,
     "    except Exception as exc:  # noqa: BLE001 \u2014 WARN tier: enrichment must never cost the slate",
     "    except Exception as exc:  # noqa: BLE001\n        raise",
     "market_read_is_warn_tier", None),

    ("the NCAAF routes drop out of the degrade floor",
     GUARDRAILS, '    "/ncaaf",\n    # \u2b50 THE WHOLE BILLING PATH', '    # \u2b50 THE WHOLE BILLING PATH',
     "degrade_floor_and_the_public_cache", '    "/ncaaf",\n'),

    ("the NCAAF routes drop out of the public cache rules",
     GUARDRAILS, '    ("/ncaaf", 900, 3600),\n)', ")",
     "degrade_floor_and_the_public_cache", '("/ncaaf", 900, 3600)'),

    ("the public router is mounted behind the paid gate",
     _REPO / "app/backend/main.py",
     "app.include_router(ncaaf.router)",
     "app.include_router(ncaaf.router, dependencies=_paid)",
     "carries_no_entitlement_dependency", None),

    ("the S3 fallback is removed, leaving DynamoDB as a single point of failure",
     SERVICE,
     "    return _s3_get(s3_key)",
     "    return None",
     "s3_fallback_runs", "_s3_get(s3_key)"),

    ("the serving write is unchained from the snapshot ops (INC-25 ordering lost)",
     SNAP_JOB,
     "    ncaaf_serving_write_after_snapshot_op(\n        start=ncaaf_futures_snapshot_op(start=ncaaf_prediction_snapshot_op()))",
     "    ncaaf_futures_snapshot_op(start=ncaaf_prediction_snapshot_op())\n    ncaaf_serving_write_after_snapshot_op(start=ncaaf_prediction_snapshot_op())",
     "runs_after_the_snapshot_ops", None),

    ("a declared field is dropped from the wire (the E9.41 silent drop)",
     ROUTER,
     '@router.get("/games/{game_id}", response_model=NcaafGamePrediction)',
     '@router.get("/games/{game_id}", response_model=NcaafGamePrediction,\n            response_model_exclude_none=True)',
     "round_trips_the_router", None),

    ("an unpublished game becomes an empty 200 instead of a 404",
     ROUTER,
     '        raise HTTPException(status_code=404, detail=f"{_NO_GAME} (game_id={game_id})")',
     '        return NcaafGamePrediction(game_id=game_id, season=0, game_day="")',
     "unpublished_game_is_a_404", None),

    ("an unwritten snapshot table crashes the pre-opener publish instead of no-opping",
     WRITER,
     '        if _EMPTY_LOG_SEGMENT_MARKER not in str(exc) and not query_lake.is_missing_table_error(exc):',
     '        if True:',
     "unwritten_snapshot_table_is_an_empty_read", "_EMPTY_LOG_SEGMENT_MARKER not in str(exc)"),

    ("the empty-log leniency widens far enough to swallow a real read failure",
     WRITER,
     '        if _EMPTY_LOG_SEGMENT_MARKER not in str(exc) and not query_lake.is_missing_table_error(exc):\n            raise',
     '        if False:\n            raise',
     "genuine_read_failure_still_raises", None),

    ("the served disclosure starts asserting a claim",
     CONTRACT,
     '    "— we make no claim to an advantage over it, and we publish no picks."',
     '    "— our edge over it is where the value lives, so here are our best picks."',
     "disclosure_asserts_no_claim", None),
]


def _run(selector: str) -> bool:
    """True iff pytest FAILED (which is the outcome a break must produce)."""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", _TEST, "-q", "-k", selector, "--no-header", "-p",
         "no:cacheprovider"],
        cwd=_REPO, capture_output=True, text=True)
    if "no tests ran" in proc.stdout or "collected 0 items" in proc.stdout:
        print(f"      ⚠️  selector {selector!r} matched NO tests — the proof would be vacuous")
        return False
    return proc.returncode != 0


def main() -> int:
    backups = {p: p.with_suffix(p.suffix + ".redproof.bak")
               for p in {b[1] for b in BREAKS}}
    # A previous run killed mid-mutation would have left a break on disk (E11.26).
    for original, backup in backups.items():
        if backup.exists():
            print(f"⚠️  restoring stale backup for {original.name}")
            original.write_text(backup.read_text())
            backup.unlink()

    # Baseline: every guard must be GREEN before any break, or a red below proves nothing.
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
            print(f"❌ {label}\n      anchor occurs {occurrences}× in {path.name} — a "
                  "non-unique anchor can land the break on the WRONG symbol (#815)")
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
