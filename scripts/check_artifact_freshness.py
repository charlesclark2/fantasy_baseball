"""
check_artifact_freshness.py — freshness SLAs on serving-critical parquet (INC-41, 2026-08-06).

WHAT IT DOES
    For every artifact in `betting_ml.monitoring.artifact_freshness.REGISTRY`, read a CONTENT
    timestamp from INSIDE the parquet and compare it against now, counting lag ONLY across the
    writer's declared active hours. Prints a `[METRIC]` line per artifact; the daily/off-cycle
    `check_artifact_freshness_op` parses those and pages via send_alert.

    The registry and all policy live in `betting_ml/monitoring/artifact_freshness.py` (import-safe,
    unit-testable without the dbt manifest — the E11.23 fast-gate rule). This file is only the
    read layer: it owns no thresholds and no verdicts.

WHY (INC-41): `stg_statsapi_lineups_wide` FROZE for 6.5h and nothing watched it. The FEED was
    healthy throughout, so every existing check — which watches sources, not derived artifacts —
    was correctly green while the lineup monitor read a 6.5-hour-stale parquet ~40 times and the
    op reported SUCCESS every 30 minutes. See the policy module's docstring for the full rationale,
    including why S3 `LastModified` cannot be used (shell-local time; and PR #638's atomic
    server-side copy refreshes the mtime even when the data is unchanged).

TIER (E11.7): ALERT-loud-but-continue — exits 0 even on a breach, because an observability check
    must never withhold a slate. `--strict` exits 1 for an operator running it as an explicit
    acceptance gate after a rebuild.

Snowflake-FREE: DuckDB over S3 via `register_lakehouse_views` (never a hardcoded parquet glob —
    that is the 2026-07-20 phase-1.5 P0) and the instance-role credential_chain (never
    os.environ AWS keys — the W7b-1 AKID landmine).

Usage (LAPTOP or BOX; on the box add -e AWS_DEFAULT_REGION=us-east-2):
    uv run python scripts/check_artifact_freshness.py
    uv run python scripts/check_artifact_freshness.py --strict
    uv run python scripts/check_artifact_freshness.py --artifact stg_statsapi_lineups_wide
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.monitoring.artifact_freshness import (  # noqa: E402
    REGISTRY,
    STALE,
    UNEVALUABLE,
    FreshnessContract,
    FreshnessReading,
    evaluate,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)


def _read_content_ts(conn, contract: FreshnessContract) -> datetime | None:
    """The artifact's content timestamp, or None when it cannot be read.

    Returning None (rather than raising) for a single unreadable artifact is deliberate: one
    absent table must not blind the check for every OTHER registered artifact. None surfaces
    downstream as UNEVALUABLE — a WARN, never a pass (NF1.7 (a)).
    """
    from betting_ml.utils.delta_lakehouse import register_lakehouse_views

    try:
        # Route through the shared registry, never a hardcoded glob: under Delta cutover the
        # legacy parquet path is frozen/absent and a hardcoded glob raises (E11.20 phase-1.5).
        register_lakehouse_views(conn, [contract.ts_table])
        row = conn.execute(f"select {contract.ts_expr} from {contract.ts_table}").fetchone()
    except Exception as exc:  # noqa: BLE001 — per-artifact isolation, see the docstring
        log.warning("[ALERT] %s: could not read %s (%s): %s",
                    contract.name, contract.ts_table, type(exc).__name__, exc)
        return None

    if not row or row[0] is None:
        return None
    value = row[0]
    # The lakehouse stores TIMESTAMPs as ISO VARCHAR (the INC-23 binary-timestamp cure), so a
    # try_cast in ts_expr normally yields a datetime — but a mixed/unwrapped column can still come
    # back a str. Coerce here rather than assuming either shape.
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            log.warning("[ALERT] %s: content timestamp %r is not parseable", contract.name, value)
            return None
    if not isinstance(value, datetime):
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _fetch(contracts: tuple[FreshnessContract, ...], now: datetime) -> list[FreshnessReading]:
    from betting_ml.utils.lakehouse_monitor import duck

    conn = duck()
    try:
        return [evaluate(c, _read_content_ts(conn, c), now) for c in contracts]
    finally:
        conn.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--artifact", action="append", default=None,
                    help="only check this registered artifact (repeatable; default: all)")
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 on a STALE/UNEVALUABLE artifact (acceptance-gate mode)")
    args = ap.parse_args()

    contracts = REGISTRY
    if args.artifact:
        wanted = set(args.artifact)
        unknown = wanted - {c.name for c in REGISTRY}
        if unknown:
            log.error("unknown artifact(s): %s", ", ".join(sorted(unknown)))
            return 2
        contracts = tuple(c for c in REGISTRY if c.name in wanted)

    now = datetime.now(timezone.utc)
    # INC-39 — STAMP THE INSTANT THIS OUTPUT DESCRIBES, on EVERY exit path (including the failure
    # path below), so the op can prove the readings are about THIS run. Freshness output is the
    # most replay-sensitive thing a monitor can parse: a stale stdout parses byte-identically to a
    # live read and every number in it is individually real. Printed BEFORE the read so it
    # survives a crash, and unconditionally so the cross-check cannot be vacuously satisfied by an
    # absent line (NF1.7 (a)).
    print(f"[METRIC] artifact_freshness_now={now.isoformat()}")

    try:
        readings = _fetch(contracts, now)
    except Exception as exc:  # noqa: BLE001 — ALERT tier: never take a slate down
        log.warning("[ALERT] artifact freshness check could not run: %s", exc)
        print("[METRIC] artifact_freshness_evaluated=0")
        return 1 if args.strict else 0

    print(f"\nServing-artifact freshness — {now:%Y-%m-%d %H:%M}Z "
          f"(lag counted only across each writer's active hours)\n")
    print(f"  {'artifact':<36}{'content ts (UTC)':<21}{'lag':>7}{'SLA':>7}   verdict")
    for r in readings:
        ts_txt = f"{r.content_ts:%Y-%m-%d %H:%M}" if r.content_ts else "—"
        lag_txt = "—" if r.active_lag_minutes is None else f"{r.active_lag_minutes:.0f}m"
        proxy = "  [ts via PROXY " + r.contract.ts_table + "]" if r.contract.is_proxied else ""
        print(f"  {r.contract.name:<36}{ts_txt:<21}{lag_txt:>7}"
              f"{r.contract.max_lag_minutes:>7}   {r.verdict}{proxy}")

    problems = [r for r in readings if r.is_problem]
    print("\n[METRIC] artifact_freshness_evaluated=1")
    print(f"[METRIC] artifact_freshness_problem_count={len(problems)}")
    for r in readings:
        lag = "NA" if r.active_lag_minutes is None else f"{r.active_lag_minutes:.0f}"
        print(f"[METRIC] artifact_freshness_{r.contract.name}={r.verdict} "
              f"lag_min={lag} sla={r.contract.max_lag_minutes}")

    for r in problems:
        if r.verdict == STALE:
            log.warning(
                "[ALERT] %s is STALE: %s — %s. FIX: %s",
                r.contract.name, r.detail, r.contract.why, r.contract.remediate,
            )
        elif r.verdict == UNEVALUABLE:
            log.warning(
                "[ALERT] %s could NOT be evaluated (%s) — this is not a pass; an anchor that "
                "fails to evaluate makes its assertion vacuously true.",
                r.contract.name, r.detail,
            )

    if problems:
        return 1 if args.strict else 0

    log.info("All %d registered artifacts are within their freshness SLA.", len(readings))
    return 0


if __name__ == "__main__":
    sys.exit(main())
