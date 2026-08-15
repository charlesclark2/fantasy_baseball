"""RED proof for NF-FRESH2's guards — `uv run python betting_ml/tests/nf_fresh2_red_proof.py`.

The bug NF-FRESH2 fixed produced NO error, NO log line, and an artifact byte-indistinguishable from
a healthy one: the market cache was simply never refreshed. A test suite over a defect like that is
worth exactly as much as its falsifiability, so each of the 12 claims below is proved by
re-introducing the real defect and requiring the named test to go RED.

Applies each break IN-PROCESS and ASSERTS THE SOURCE ACTUALLY CHANGED before running pytest — a red
proof whose mutation silently no-ops reports a triumphant, false "the guard caught it" (the E11.24
#682 lesson). Restores the file in a `finally`, so an interrupted run cannot leave a break on disk.

⚠️ NOT SCHEDULED, and that is a known limitation rather than a claim: like the repo's nine other
`*_red_proof.py` harnesses this runs only when somebody types the command, and E9.64 measured what
that costs — six frontend cases had silently stopped proving anything, each still reading as
coverage. Wiring the Python red proofs into a scheduled workflow (as `frontend_red_proof.yml` does
for the E2E side) is worth doing; it is deliberately not smuggled into this story.

Runtime ~20s. Prints one line per case; exits non-zero if ANY break stays green.
"""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TEST = "betting_ml/tests/test_nfl_fresh2_board_freshness.py"

BREAKS = [
    ("P1 boundary: refresh every season",
     "quant_sports_intel_models/football/nfl/fantasy/market_freshness.py",
     "    if not market_refresh:\n        return False\n    return int(season) == current_season(today)",
     "    return bool(market_refresh)",
     "historical_seasons_are_refused or clock_derived or pinned_snapshot_off_disk or exporters_own_fetch"),
    ("P1 refetch: cache always wins (the pre-NF-FRESH2 behaviour)",
     "quant_sports_intel_models/football/nfl/fantasy/adp_source.py",
     "    if not refresh:\n        cached = _read_cached_payload(cache)\n        if cached is not None:\n            return cached\n\n    url = _FFC_URL",
     "    cached = _read_cached_payload(cache)\n    if cached is not None:\n        return cached\n\n    url = _FFC_URL",
     "refresh_true_refetches"),
    ("P1 fallback: a failed refresh loses the market",
     "quant_sports_intel_models/football/nfl/fantasy/adp_source.py",
     "        cached = _read_cached_payload(cache) if refresh else None\n        if cached is not None:\n            log.warning(\"⚠️ FFC ADP %s %s/%dteam REFRESH FAILED",
     "        cached = None\n        if cached is not None:\n            log.warning(\"⚠️ FFC ADP %s %s/%dteam REFRESH FAILED",
     "failed_refresh_keeps_the_last_good"),
    ("P1 stamps: drop adp_as_of from the locked-payload allowlist",
     "app/backend/services/entitlement.py",
     '        "adp_as_of",\n        "ecr_as_of",\n        "freshness",\n    }\n)\n\n# Manifest keys a non-entitled caller keeps:',
     '        "ecr_as_of",\n        "freshness",\n    }\n)\n\n# Manifest keys a non-entitled caller keeps:',
     "survive_the_entitlement_allowlists"),
    ("P0: restore the 3-8 seasonal cliff on the roll-forward",
     "pipeline/schedules/sports_rollforward_schedules.py",
     'NFL_ROLL_FORWARD_CRON = "15 6 * 3-12,1-2 1"',
     'NFL_ROLL_FORWARD_CRON = "15 6 * 3-8 1"',
     "crons_reach_the_opener"),
    ("P0: restore the 3-8 seasonal cliff on the Sleeper capture",
     "pipeline/schedules/sports_rollforward_schedules.py",
     'NFL_SLEEPER_INJURIES_CRON = "30 6 * 3-12,1-2 *"',
     'NFL_SLEEPER_INJURIES_CRON = "30 6 * 3-8 *"',
     "crons_reach_the_opener"),
    ("P2 INC-25: run the two ops independently instead of chaining them",
     "pipeline/jobs/sports_nfl_board_publish_job.py",
     "    nfl_board_publish_op(start=nfl_board_input_refresh_op())",
     "    nfl_board_input_refresh_op()\n    nfl_board_publish_op(start=nfl_board_input_refresh_op.alias('x')())",
     "downstream_of_the_ingest"),
    ("P2: swallow the missing-DuckDB precondition (the 19-green-runs shape)",
     "pipeline/jobs/sports_nfl_board_publish_job.py",
     '        raise Exception(f"NFL board publish precondition failed — {msg}")',
     '        return',
     "refuses_to_report_success_without_a_duckdb"),
    ("P2: drop the explicit --market-refresh from the scheduled build step",
     "pipeline/jobs/sports_nfl_board_publish_job.py",
     '(f"{_FANTASY}.run_nf1_5", ["--mode", "build", "--market-refresh",',
     '(f"{_FANTASY}.run_nf1_5", ["--mode", "build",',
     "passes_market_refresh_explicitly"),
    ("P2 verify: treat an unreadable manifest as a pass",
     "pipeline/jobs/sports_nfl_board_publish_job.py",
     '        raise Exception(f"NFL board publish verification could not read {path}: {exc}") from exc',
     '        return',
     "unreadable_manifest_as_a_failure"),
    ("P2 verify: drop the stale-artifact clause (stamp clause left intact)",
     "pipeline/jobs/sports_nfl_board_publish_job.py",
     '            problems.append(f"manifest.generated_at={raw} predates this run ({started.isoformat()})"\n                            " — a STALE artifact was published")',
     '            pass',
     "rejects_a_stale_or_unstamped"),
    ("P2 verify: drop the market-stamp clause (stale clause left intact)",
     "pipeline/jobs/sports_nfl_board_publish_job.py",
     '    if not blob.get("adp_as_of"):',
     '    if False:',
     "rejects_a_stale_or_unstamped"),
]


def main() -> int:
    failures = []
    for name, rel, old, new, selector in BREAKS:
        path = REPO / rel
        original = path.read_text()
        if old not in original:
            failures.append(f"{name}: MUTATION TARGET NOT FOUND in {rel}")
            continue
        mutated = original.replace(old, new, 1)
        assert mutated != original, name  # the mutation must actually land
        path.write_text(mutated)
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", TEST, "-q", "-k", selector,
                 "-p", "no:cacheprovider"],
                cwd=REPO, capture_output=True, text=True)
            tail = (proc.stdout or "").strip().splitlines()[-1] if proc.stdout else ""
            verdict = "RED ✅" if proc.returncode != 0 else "GREEN ❌ (VACUOUS GUARD)"
            if proc.returncode == 0:
                failures.append(name)
            print(f"{verdict:26} {name}\n{'':26} -> {tail}")
        finally:
            path.write_text(original)
    print()
    if failures:
        print("VACUOUS / BROKEN:", *failures, sep="\n  - ")
        return 1
    print(f"All {len(BREAKS)} deliberate breaks were caught.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
