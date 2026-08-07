"""dbt_test_results.py — INC-41 dbt-test pager: the paging policy for a red dbt test.

WHY THIS EXISTS (INC-41, 2026-08-06)
    The daily dbt test step is deliberately WARN-tier / non-blocking, and that is CORRECT — INC-6
    (2026-06-21) had a bad StatsAPI bio row exit-1 the Sunday build and block every prediction, so
    `dbt_daily_build` now splits the model `run` (HALT) from the `test` suite (WARN-continue).

    The cost of that split is that a `not_null` failure on a SERVING-CRITICAL contract surfaces
    days later in CI, to whoever happens to open the next PR. In INC-41 the test WORKED — it went
    red on the nulled odds price — and nobody was notified. The detection existed; the page did
    not. That is the E11.30 finding ("ALERT-tier had quietly come to mean detected-nobody-notified")
    one layer over: here the detector is not even an op, it is a dbt test whose non-zero exit is
    caught and logged by design.

⭐ THE SIGNAL ALREADY EXISTS — key on the CONFIGURED severity.
    This repo already encodes "which failure matters" in the dbt project itself (the E11.7
    pipeline contract): serving-critical model contracts are `severity: error`, peripheral
    data-quality checks are `severity: warn`. Today that is 17 error / ~69 warn. So the pager
    needs no new registry to maintain and no heuristic about which model is important — it reads
    the severity the contract already declares. A registry that must be kept in sync with the dbt
    project would be one more documented-but-drifting surface (the `W7B_LAKEHOUSE_S3` class).

🪤 WHY STATUS ALONE IS NOT THE KEY — the false-page this module exists to avoid.
    It is tempting to key on `status` (dbt reports a warn-severity failure as `warn` and an
    error-severity failure as `fail`, so status looks like it already encodes severity). MEASURED
    against dbt-fusion 2.0.0-preview.204, that is true for a test that RUNS and returns rows:

        severity: error, failing rows  ->  status "fail"   failures: 1
        severity: warn,  failing rows  ->  status "warn"   failures: 1
        passing test                   ->  status "pass"
        model                          ->  status "success"

    But a test that cannot EXECUTE AT ALL (a binder error, a dropped column, a renamed source)
    reports `status: "error"` **regardless of its configured severity** — measured: a test
    explicitly configured `severity='warn'` whose SQL referenced a missing column came back
    `status: "error"`, indistinguishable at the status level from a broken serving contract. So a
    status-only pager would page CRITICAL every time a PERIPHERAL test broke, which is the
    alert-fatigue failure mode that gets a monitor muted (E11.27 / the injury feed-freshness
    carve-out). The configured severity is read from the manifest, which resolves that case.

    The reverse guard matters too: `severity` is stored UPPERCASE in the fusion manifest
    ("ERROR" / "WARN"), while dbt-core writes it lowercase — so it is normalised here rather than
    compared verbatim. A `.lower()` mismatch is exactly the silent-NULL class this repo has hit
    through Snowflake `VALUE:` case-sensitivity.

WHAT IS PAGEABLE
    CRITICAL  a test whose CONFIGURED severity is error and whose status is `fail` or `error`
              — a broken serving-critical contract, or one that could not be evaluated at all.
    WARN      a failing/erroring test whose severity could NOT be resolved (no manifest), and the
              UNAVAILABLE case below. Worth seeing; not worth waking someone.
    SILENT    warn-severity failures (logged as a digest, never paged — that is the whole point
              of the severity split), and a clean suite.

FOUR STATES, NOT TWO — and NOT_RUN is the one that keeps this quiet enough to be trusted.
    `dbt_daily_build` does not run the same command every day: build days (Sunday + every 3rd
    midweek) run `run` then `test`, while other days run a state-aware `build` which the runner
    rewrites to `source_status:fresher+`. Both of those DO execute tests, so both are checkable.
    But a day on which no test executed at all is a KNOWN-GOOD state, not a missing measurement —
    reporting it as "unverified" would fire a WARN on a routine cadence and train the operator to
    ignore this pager. It is therefore a distinct, SILENT state, the same carve-out
    `artifact_freshness` makes for a writer's declared inactive hours.

    UNAVAILABLE is the genuinely-unverified state: the suite ran but its results could not be
    read (the runner did not return them, the file was missing, the JSON was unparseable). That
    is WARN, never healthy — a check that did not run is not a pass (NF1.7 (a)).

Lives in betting_ml/ (not pipeline/) so the fast gate can import it: `pipeline/__init__.py` reads
the dbt manifest, which is absent in CI, so a fast-gate test importing `pipeline` crashes at
COLLECTION rather than skipping (E11.23). Same shape as `spine_horizon.py` / `w11_tail_coverage.py`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

# ── severity vocabulary ──────────────────────────────────────────────────────
# Normalised (upper) forms. dbt-fusion writes config.severity UPPERCASE in the manifest;
# dbt-core writes it lowercase. Never compare a raw manifest value — normalise first.
SEVERITY_ERROR = "ERROR"
SEVERITY_WARN = "WARN"
SEVERITY_UNKNOWN = "UNKNOWN"

# dbt's default when a test declares no severity is `error` (i.e. serving-critical unless the
# contract says otherwise). Matching that default is what makes "17 error / 69 warn" the whole
# story — a test with no explicit severity is genuinely error-severity, not unclassifiable.
DEFAULT_SEVERITY = SEVERITY_ERROR

# ── run_results statuses (measured against dbt-fusion 2.0.0-preview.204) ─────
STATUS_FAIL = "fail"    # test ran, returned failing rows, severity: error
STATUS_WARN = "warn"    # test ran, returned failing rows, severity: warn
STATUS_ERROR = "error"  # test could NOT execute — severity-independent, see module docstring
STATUS_PASS = "pass"
STATUS_SKIPPED = "skipped"

# A test in one of these states did not come back clean. `error` is included deliberately: a
# contract that could not be evaluated is not a passing contract.
FAILING_STATUSES = frozenset({STATUS_FAIL, STATUS_ERROR})

TEST_UNIQUE_ID_PREFIX = "test."

# ── outcome states ───────────────────────────────────────────────────────────
STATE_CLEAN = "CLEAN"
STATE_FAILURES = "FAILURES"
STATE_NOT_RUN = "NOT_RUN"          # no test executed in this dbt invocation — silent by design
STATE_UNAVAILABLE = "UNAVAILABLE"  # the suite ran but results could not be read — WARN


@dataclass(frozen=True)
class TestFailure:
    """One non-clean test node, with the severity that decides whether it pages."""

    unique_id: str
    status: str
    severity: str
    failures: int | None = None
    message: str = ""

    @property
    def name(self) -> str:
        """Short human name: the test's node name, without the `test.<project>.` prefix and
        without the trailing content hash fusion appends to generic tests."""
        parts = self.unique_id.split(".")
        return parts[-2] if len(parts) >= 4 else parts[-1]

    @property
    def could_not_execute(self) -> bool:
        return self.status == STATUS_ERROR


@dataclass(frozen=True)
class Verdict:
    """The full reading of one dbt invocation's test results."""

    state: str
    error_severity: tuple[TestFailure, ...] = ()
    warn_severity: tuple[TestFailure, ...] = ()
    unknown_severity: tuple[TestFailure, ...] = ()
    tests_total: int = 0
    tests_passed: int = 0
    tests_skipped: int = 0
    detail: str = ""
    provenance: dict[str, Any] = field(default_factory=dict)

    @property
    def pageable(self) -> tuple[TestFailure, ...]:
        """The failures that justify waking someone: broken serving-critical contracts."""
        return self.error_severity


def normalise_severity(raw: Any) -> str:
    """Normalise a manifest severity to ERROR/WARN, defaulting to dbt's own default (error).

    Case-normalising is load-bearing, not cosmetic: fusion stores "WARN", core stores "warn".
    An unrecognised value falls back to the dbt default rather than to UNKNOWN — a typo'd
    severity in a contract still describes a test dbt itself treats as error-severity.
    """
    if raw is None:
        return DEFAULT_SEVERITY
    value = str(raw).strip().upper()
    if value in (SEVERITY_ERROR, SEVERITY_WARN):
        return value
    return DEFAULT_SEVERITY


def load_severity_map(manifest: Any) -> dict[str, str]:
    """Build {test unique_id -> ERROR|WARN} from a dbt manifest (path, file object, or dict).

    Returns {} when the manifest cannot be read. An empty map is NOT an error here — the caller
    degrades to status-inferred severity and reports the affected tests at WARN rather than
    CRITICAL, because an unresolvable severity must not silently become a page.
    """
    data: Any = manifest
    if isinstance(manifest, (str, bytes)) or hasattr(manifest, "__fspath__"):
        try:
            with open(manifest) as fh:  # type: ignore[arg-type]
                data = json.load(fh)
        except (OSError, ValueError):
            return {}
    elif hasattr(manifest, "read"):
        try:
            data = json.load(manifest)
        except (OSError, ValueError):
            return {}
    if not isinstance(data, dict):
        return {}

    out: dict[str, str] = {}
    for uid, node in (data.get("nodes") or {}).items():
        if not str(uid).startswith(TEST_UNIQUE_ID_PREFIX) or not isinstance(node, dict):
            continue
        config = node.get("config") or {}
        out[uid] = normalise_severity(config.get("severity") if isinstance(config, dict) else None)
    return out


def _resolve_severity(uid: str, status: str, severity_map: dict[str, str]) -> str:
    """Configured severity first; fall back to what the STATUS can prove, else UNKNOWN.

    The fallback exists only for the no-manifest case. It is deliberately asymmetric:
      - `warn` is emitted ONLY for a warn-severity test  -> WARN, safe to infer.
      - `fail` is emitted ONLY for an error-severity test -> ERROR, safe to infer.
      - `error` is severity-INDEPENDENT (see the module docstring) -> UNKNOWN, never inferred.
    Inferring ERROR from `error` is the false-page this module exists to prevent.
    """
    configured = severity_map.get(uid)
    if configured:
        return configured
    if status == STATUS_WARN:
        return SEVERITY_WARN
    if status == STATUS_FAIL:
        return SEVERITY_ERROR
    return SEVERITY_UNKNOWN


def classify(
    payload: Any,
    severity_map: dict[str, str] | None = None,
) -> Verdict:
    """PURE. Turn a captured dbt result payload into a Verdict. Never raises.

    `payload` is what `pipeline.ops._dbt_exec.capture_dbt_results` persists:
        {"available": bool, "tested": bool, "reason": str, "provenance": {...},
         "run_results": {<the raw run_results.json>}}
    A bare run_results.json dict is also accepted so the artifact can be classified directly.
    """
    if not isinstance(payload, dict):
        return Verdict(state=STATE_UNAVAILABLE,
                       detail="no dbt result payload was captured for this run")

    provenance = payload.get("provenance") or {}
    if not isinstance(provenance, dict):
        provenance = {}

    # An explicitly-recorded miss. `tested is False` means the invocation genuinely executed no
    # tests — a routine cadence, not a gap in measurement (see the docstring).
    if payload.get("available") is False:
        reason = str(payload.get("reason") or "dbt test results were not available")
        if payload.get("tested") is False:
            return Verdict(state=STATE_NOT_RUN, detail=reason, provenance=provenance)
        return Verdict(state=STATE_UNAVAILABLE, detail=reason, provenance=provenance)

    run_results = payload.get("run_results", payload)
    if not isinstance(run_results, dict) or not isinstance(run_results.get("results"), list):
        return Verdict(
            state=STATE_UNAVAILABLE,
            detail="dbt run_results.json was missing or unparseable",
            provenance=provenance,
        )

    severity_map = severity_map or {}
    errors: list[TestFailure] = []
    warns: list[TestFailure] = []
    unknowns: list[TestFailure] = []
    total = passed = skipped = 0

    for result in run_results["results"]:
        if not isinstance(result, dict):
            continue
        uid = str(result.get("unique_id") or "")
        if not uid.startswith(TEST_UNIQUE_ID_PREFIX):
            continue  # models/seeds/snapshots — the `run` step already gated on those (HALT tier)
        total += 1
        status = str(result.get("status") or "").strip().lower()
        if status == STATUS_PASS:
            passed += 1
            continue
        if status == STATUS_SKIPPED:
            skipped += 1
            continue
        if status not in FAILING_STATUSES and status != STATUS_WARN:
            continue

        severity = _resolve_severity(uid, status, severity_map)
        failure = TestFailure(
            unique_id=uid,
            status=status,
            severity=severity,
            failures=result.get("failures") if isinstance(result.get("failures"), int) else None,
            message=str(result.get("message") or "")[:500],
        )
        if severity == SEVERITY_UNKNOWN:
            unknowns.append(failure)
        elif severity == SEVERITY_ERROR and status in FAILING_STATUSES:
            errors.append(failure)
        else:
            # warn-severity failures, and the (unexpected) error-severity `warn` status.
            warns.append(failure)

    state = STATE_FAILURES if (errors or warns or unknowns) else STATE_CLEAN
    if total == 0:
        # The invocation ran, but selected no tests (e.g. a `source_status:fresher+` build whose
        # selection matched only views). Nothing was measured, and nothing was expected to be.
        state = STATE_NOT_RUN

    return Verdict(
        state=state,
        error_severity=tuple(errors),
        warn_severity=tuple(warns),
        unknown_severity=tuple(unknowns),
        tests_total=total,
        tests_passed=passed,
        tests_skipped=skipped,
        provenance=provenance,
    )


def render(verdict: Verdict) -> str:
    """Human-readable body for the page / step log. Names the tests and what to do first."""
    lines: list[str] = []
    prov = verdict.provenance or {}
    stamp = " ".join(
        f"{k}={prov[k]}" for k in ("command", "generated_at", "invocation_id") if prov.get(k)
    )

    if verdict.state == STATE_NOT_RUN:
        lines.append(f"dbt tests: NOT RUN this invocation — {verdict.detail or 'no tests selected'}")
    elif verdict.state == STATE_UNAVAILABLE:
        lines.append(
            "dbt test results UNVERIFIED for this run — the suite ran but its results could not "
            f"be read ({verdict.detail}). This is NOT a clean bill of health: an error-severity "
            "contract may be red and unreported."
        )
    else:
        lines.append(
            f"dbt tests: {verdict.tests_total} selected | {verdict.tests_passed} passed | "
            f"{len(verdict.error_severity)} ERROR-severity failing | "
            f"{len(verdict.warn_severity)} warn-severity failing | "
            f"{len(verdict.unknown_severity)} unclassifiable | {verdict.tests_skipped} skipped"
        )

    if verdict.error_severity:
        lines.append("")
        lines.append(
            "SERVING-CRITICAL contracts red (severity: error) — these gate the serving path:"
        )
        for f in verdict.error_severity:
            why = "COULD NOT EXECUTE" if f.could_not_execute else f"{f.failures} failing row(s)"
            lines.append(f"  - {f.name}  [{f.status}: {why}]")
            if f.message and f.could_not_execute:
                lines.append(f"      {f.message.splitlines()[0][:200]}")

    if verdict.unknown_severity:
        lines.append("")
        lines.append(
            "Failing, severity UNRESOLVED (no manifest available — could not tell a serving "
            "contract from a peripheral check):"
        )
        for f in verdict.unknown_severity:
            lines.append(f"  - {f.name}  [{f.status}]")

    if verdict.warn_severity:
        lines.append("")
        lines.append(
            f"Peripheral (severity: warn) failures — NOT paged, listed for the digest "
            f"({len(verdict.warn_severity)}):"
        )
        for f in verdict.warn_severity[:20]:
            lines.append(f"  - {f.name}  [{f.status}]")
        if len(verdict.warn_severity) > 20:
            lines.append(f"  … and {len(verdict.warn_severity) - 20} more")

    if stamp:
        lines.append("")
        lines.append(f"dbt invocation: {stamp}")

    if verdict.error_severity:
        lines.append("")
        lines.append(
            "First action: the dbt test step is non-blocking by design (INC-6) so PREDICTIONS "
            "ARE NOT BLOCKED — but the contract above is red now, not at next PR time. Inspect "
            "the failing rows, then decide whether the model or the contract is wrong."
        )
    return "\n".join(lines)


def page_decision(verdict: Verdict) -> tuple[str | None, str]:
    """PURE. Map a Verdict to (severity, message). severity None = do NOT page.

    CRITICAL only for a confirmed error-severity failure — the serving-critical contract case
    INC-41 was made of. WARN for an unverifiable reading (never healthy — NF1.7 (a)) and for a
    failure whose severity could not be resolved. Warn-severity failures and a clean suite are
    SILENT: paging on peripheral data-quality noise is what gets a monitor muted, and the whole
    reason this repo splits severity is to say those do not warrant a page.
    """
    message = render(verdict)
    if verdict.error_severity:
        return "CRITICAL", message
    if verdict.state == STATE_UNAVAILABLE:
        return "WARN", message
    if verdict.unknown_severity:
        return "WARN", message
    return None, message


def dedup_key(verdict: Verdict) -> str:
    """Rate-limit key that carries WHICH contracts are red, not just "a dbt test failed".

    send_alert rate-limits per key with a 1-hour TTL. A single constant key would let an ongoing
    failure on contract A swallow the FIRST page for a new failure on contract B — the "a smoke
    test ate the real alert's slot" hazard (INC-39) arriving by a different road. Keyed on the
    affected SET, a continuing failure stays rate-limited while any change pages immediately.
    """
    names = sorted({f.name for f in verdict.error_severity} |
                   {f.name for f in verdict.unknown_severity})
    if not names:
        return "dbt_test_results:unverified"
    joined = ",".join(names)
    if len(joined) > 180:  # keep the key bounded but still set-sensitive
        import hashlib
        joined = f"{joined[:140]}+{hashlib.sha1(joined.encode()).hexdigest()[:12]}"
    return f"dbt_test_results:{joined}"
