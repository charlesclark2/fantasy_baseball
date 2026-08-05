"""leakage_guard.py — the doc §13 FAIL-CLOSED point-in-time enforcement (PURE; no IO).

§13 names the rejection set. This module implements each case as an INDEPENDENT check function
so that:

  • every clause can be triggered by a fixture that satisfies every OTHER clause, and
  • deleting any one clause from the source turns exactly one test RED.

That structure is the cure for NF-D17's vacuous-guard defect: a guard on `A and B and C` whose
fixture also trips B proves nothing about A, and stays green when A is deleted. Here the clauses
are disjoint by construction, and `test_nfl_pit_leakage_guard.py` RED-proves each one by
deleting it from the source.

FAIL-CLOSED means: **an unevaluable check is a REJECTION, never a pass.** A missing stamp, an
unparseable stamp, a market record with no kickoff, a rolling window with no bounds — all reject.
NF1.7 (a) is the whole reason: an anchor that fails to evaluate and returns `None` makes its
check VACUOUSLY TRUE, and the guard then "passes" on nothing at all.

WHY `source_timestamp=None` IS NOT AN EXCEPTION TO THAT: nflverse deleted `injuries.date_modified`
in 2025, so for injuries the vendor genuinely publishes no as-of claim. That is a KNOWN, NAMED
absence, and the record must declare it (`source_timestamp_absent_reason`). An undeclared NULL is
still a rejection — otherwise "the vendor stopped publishing it" and "we forgot to stamp it" are
indistinguishable, which is precisely the silent-death class W0a exists to end.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from enum import Enum

from .timestamps import (
    PROJECTION_TIMESTAMP,
    REQUIRED_PROVENANCE_KEYS,
    TimestampContractError,
    parse_utc,
)


class Rejection(str, Enum):
    """The §13 rejection reasons. String-valued so a manifest/log line is self-describing."""

    FEATURE_TIMESTAMP_AFTER_PROJECTION = "feature_timestamp > projection_timestamp"
    SOURCE_TIMESTAMP_AFTER_PROJECTION = "source_timestamp > projection_timestamp"
    CAPTURE_TIMESTAMP_AFTER_PROJECTION = "capture_timestamp > projection_timestamp"
    VENDOR_RELEASE_AFTER_PROJECTION = "vendor_release_timestamp > projection_timestamp"
    INGESTION_AFTER_PROJECTION = "ingestion_timestamp > projection_timestamp"
    PROVENANCE_MISSING = "point-in-time provenance is missing"
    REVISED_VENDOR_RECORD = "a revised vendor record replaced the original captured record"
    LATE_MARKET_JOIN = "a closing line / late prop joined an earlier projection"
    ROLLING_WINDOW_CONTAINS_TARGET = "a rolling window contains the target or a future game"
    UNEVALUABLE = "a required check could not be evaluated (fail-closed)"


@dataclass(frozen=True)
class LeakageFinding:
    reason: Rejection
    detail: str
    subject_key: str | None = None

    def __str__(self) -> str:  # pragma: no cover — formatting only
        who = f" [{self.subject_key}]" if self.subject_key else ""
        return f"{self.reason.value}{who}: {self.detail}"


class LeakageRejection(RuntimeError):
    """Raised by `assert_point_in_time` — the build is REFUSED (HALT, never a warning)."""

    def __init__(self, findings: list[LeakageFinding]):
        self.findings = findings
        super().__init__(
            f"point-in-time build REFUSED — {len(findings)} leakage finding(s):\n  "
            + "\n  ".join(str(f) for f in findings)
        )


#: A market snapshot captured within this many minutes of kickoff is treated as CLOSING/LATE
#: regardless of how it is labelled. Independent of the timestamp comparisons on purpose: it
#: catches a record whose stamps LOOK fine (e.g. a mis-stamped capture_timestamp) but whose
#: market phase makes it un-knowable at an earlier build.
DEFAULT_CLOSING_WINDOW_MINUTES = 240

#: Market phases that may never join a projection that stands before the market existed.
LATE_MARKET_PHASES = frozenset({"closing", "close", "late", "pregame_final", "inplay", "live"})


# ── clause 1..5: every *_timestamp must be <= projection_timestamp ───────────────────────
_TIMESTAMP_CLAUSES: tuple[tuple[str, Rejection], ...] = (
    ("feature_timestamp", Rejection.FEATURE_TIMESTAMP_AFTER_PROJECTION),
    ("source_timestamp", Rejection.SOURCE_TIMESTAMP_AFTER_PROJECTION),
    ("capture_timestamp", Rejection.CAPTURE_TIMESTAMP_AFTER_PROJECTION),
    ("vendor_release_timestamp", Rejection.VENDOR_RELEASE_AFTER_PROJECTION),
    ("ingestion_timestamp", Rejection.INGESTION_AFTER_PROJECTION),
)


def check_timestamps_not_after_projection(record: dict, projection_timestamp) -> list[LeakageFinding]:
    """Every stamp on the record must be at or before the instant the build claims to stand at.

    ⚠️ ALL FIVE are checked, not just the three §13 spells out. `ingestion_timestamp` and
    `vendor_release_timestamp` are equally disqualifying: if the row landed in our store — or the
    vendor published the file — after the projection instant, the build could not have known it,
    no matter how early the underlying fact is dated.
    """
    subject = record.get("subject_key")
    try:
        proj = parse_utc(projection_timestamp, field=PROJECTION_TIMESTAMP)
    except TimestampContractError as exc:
        return [LeakageFinding(Rejection.UNEVALUABLE, f"projection_timestamp unusable: {exc}", subject)]

    out: list[LeakageFinding] = []
    for key, reason in _TIMESTAMP_CLAUSES:
        raw = record.get(key)
        if raw is None:
            continue  # absence is clause 6's job (provenance), not this clause's
        try:
            ts = parse_utc(raw, field=key)
        except TimestampContractError as exc:
            out.append(LeakageFinding(Rejection.UNEVALUABLE, f"{key} unusable: {exc}", subject))
            continue
        if ts > proj:
            out.append(
                LeakageFinding(reason, f"{key}={ts.isoformat()} > projection={proj.isoformat()}", subject)
            )
    return out


# ── clause 6: provenance completeness ───────────────────────────────────────────────────
def check_provenance_present(record: dict) -> list[LeakageFinding]:
    """Refuse a record that cannot prove where it came from or when we saw it.

    `source_timestamp` may be NULL **only with a declared reason** — nflverse's 2025 deletion of
    `injuries.date_modified` is a real, permanent absence, but an UNDECLARED null is
    indistinguishable from a writer that forgot to stamp it. Declaring it is one field and keeps
    a genuine upstream deletion visible instead of laundered into "healthy".
    """
    subject = record.get("subject_key")
    out: list[LeakageFinding] = []

    for key in REQUIRED_PROVENANCE_KEYS:
        value = record.get(key)
        if value is None or (isinstance(value, str) and not value.strip()):
            out.append(LeakageFinding(Rejection.PROVENANCE_MISSING, f"{key} is absent/blank", subject))

    for key in ("feature_timestamp", "capture_timestamp", "ingestion_timestamp"):
        value = record.get(key)
        if value is None or (isinstance(value, str) and not value.strip()):
            out.append(LeakageFinding(Rejection.PROVENANCE_MISSING, f"{key} is absent/blank", subject))

    if record.get("source_timestamp") is None and not str(
        record.get("source_timestamp_absent_reason") or ""
    ).strip():
        out.append(
            LeakageFinding(
                Rejection.PROVENANCE_MISSING,
                "source_timestamp is NULL with no `source_timestamp_absent_reason` — an undeclared "
                "null hides an upstream field deletion (the nflverse injuries.date_modified class)",
                subject,
            )
        )
    return out


# ── clause 7: a revision may never stand in for the original capture ────────────────────
def check_original_capture(record: dict, store_index: dict | None) -> list[LeakageFinding]:
    """Reject when the presented record is a REVISION of an already-captured original.

    `store_index` maps `subject_key` -> list of `{capture_timestamp, payload_sha256}` for the
    captures the immutable store already holds. If the store holds an EARLIER capture of the same
    subject with a DIFFERENT payload hash, the vendor revised the record after we saw it, and the
    build must consume the ORIGINAL — the revision reflects information that did not exist at the
    earlier projection.

    ⛔ `store_index is None` REJECTS. A build that cannot consult the store cannot prove it is
    using originals, and "no index available" must never read as "no revisions found" (NF1.7 (a)).
    """
    subject = record.get("subject_key")
    if store_index is None:
        return [
            LeakageFinding(
                Rejection.UNEVALUABLE,
                "no immutable-store index supplied — cannot prove this is the ORIGINAL capture",
                subject,
            )
        ]
    if not subject:
        return []  # clause 6 already rejects a record with no subject_key

    priors = store_index.get(subject) or []
    if not priors:
        return []

    digest = record.get("payload_sha256")
    try:
        cap = parse_utc(record.get("capture_timestamp"), field="capture_timestamp")
    except TimestampContractError as exc:
        return [LeakageFinding(Rejection.UNEVALUABLE, f"capture_timestamp unusable: {exc}", subject)]

    out: list[LeakageFinding] = []
    for prior in priors:
        try:
            prior_cap = parse_utc(prior.get("capture_timestamp"), field="capture_timestamp")
        except TimestampContractError as exc:
            out.append(
                LeakageFinding(Rejection.UNEVALUABLE, f"stored capture_timestamp unusable: {exc}", subject)
            )
            continue
        if prior_cap < cap and prior.get("payload_sha256") != digest:
            out.append(
                LeakageFinding(
                    Rejection.REVISED_VENDOR_RECORD,
                    f"payload changed after capture (original {prior_cap.isoformat()} "
                    f"sha={str(prior.get('payload_sha256'))[:12]}… vs presented {cap.isoformat()} "
                    f"sha={str(digest)[:12]}…) — the build must use the ORIGINAL",
                    subject,
                )
            )
    return out


# ── clause 8: a closing line / late prop may not join an earlier projection ─────────────
def check_market_phase(
    record: dict,
    projection_timestamp,
    *,
    closing_window_minutes: int = DEFAULT_CLOSING_WINDOW_MINUTES,
) -> list[LeakageFinding]:
    """Reject a closing/late market record consumed by a projection that stands before the close.

    ⭐ THE COMPARISON IS PROJECTION-vs-KICKOFF, NOT PROJECTION-vs-CAPTURE — and that is what makes
    this clause independent rather than a restatement of `check_timestamps_not_after_projection`.
    A first cut compared the projection to the CAPTURE stamp, which fires only when the capture is
    already late by the stamps, i.e. exactly when the timestamp clause fires anyway. That clause
    would have been dead weight, and the guard's own non-vacuity test caught it.

    The question asked here is: *could a market in this PHASE have existed at that projection
    instant?* A board that is closing-tier for a Sunday game cannot have existed at a Tuesday
    projection, no matter what its capture stamp claims — so this still fires when the stamps
    themselves are wrong (a mis-copied capture_timestamp, a vendor `last_update` back-dated to the
    open, a mislabelled snapshot). It does NOT fire when the projection itself stands inside the
    closing window, because a Sunday-morning re-projection legitimately consumes a near-closing
    board — that is the whole point of the multi-build week.

    A record is late if it declares a late `market_phase` OR was captured inside
    `closing_window_minutes` of kickoff. Only market-tier records are examined. A market record
    with NO kickoff is UNEVALUABLE → rejected: without kickoff an open line and a closing line are
    indistinguishable.
    """
    if str(record.get("record_tier") or "").lower() != "market":
        return []

    subject = record.get("subject_key")
    try:
        proj = parse_utc(projection_timestamp, field=PROJECTION_TIMESTAMP)
        cap = parse_utc(record.get("capture_timestamp"), field="capture_timestamp")
    except TimestampContractError as exc:
        return [LeakageFinding(Rejection.UNEVALUABLE, f"market stamps unusable: {exc}", subject)]

    kickoff_raw = record.get("kickoff_timestamp")
    if kickoff_raw is None:
        return [
            LeakageFinding(
                Rejection.UNEVALUABLE,
                "market record carries no kickoff_timestamp — an open line and a closing line are "
                "indistinguishable without it",
                subject,
            )
        ]
    try:
        kickoff = parse_utc(kickoff_raw, field="kickoff_timestamp")
    except TimestampContractError as exc:
        return [LeakageFinding(Rejection.UNEVALUABLE, f"kickoff_timestamp unusable: {exc}", subject)]

    phase = str(record.get("market_phase") or "").strip().lower()
    close_opens = kickoff - timedelta(minutes=closing_window_minutes)
    within_close = cap >= close_opens
    if not (phase in LATE_MARKET_PHASES or within_close):
        return []

    if proj < close_opens:
        label = phase or f"captured within {closing_window_minutes}min of kickoff"
        return [
            LeakageFinding(
                Rejection.LATE_MARKET_JOIN,
                f"late market ({label}, captured {cap.isoformat()}) joined to a projection standing "
                f"at {proj.isoformat()}, which is before the close opens at "
                f"{close_opens.isoformat()} (kickoff {kickoff.isoformat()})",
                subject,
            )
        ]
    return []


# ── clause 9: a rolling window may not contain the target or a future game ──────────────
def check_rolling_window(record: dict) -> list[LeakageFinding]:
    """Reject a rolling-window feature whose window reaches the target game or beyond.

    Two independent tells, because either alone is escapable:
      • BY TIME — `window_end_timestamp >= target_game_timestamp` (an inclusive end-bound is the
        classic off-by-one: "through the target game" reads as "up to the target game").
      • BY IDENTITY — `target_game_id` appears in `window_game_ids`. This catches the case a time
        bound cannot: same-day games, a rescheduled kickoff, or a window built from a game list
        rather than a date range.

    A record declaring `is_rolling_window` but carrying neither bound is UNEVALUABLE → rejected.
    """
    if not record.get("is_rolling_window"):
        return []

    subject = record.get("subject_key")
    target_id = record.get("target_game_id")
    window_ids = record.get("window_game_ids")
    if window_ids is not None and target_id is not None and target_id in set(window_ids):
        return [
            LeakageFinding(
                Rejection.ROLLING_WINDOW_CONTAINS_TARGET,
                f"target_game_id={target_id!r} is inside window_game_ids",
                subject,
            )
        ]

    end_raw, target_raw = record.get("window_end_timestamp"), record.get("target_game_timestamp")
    if end_raw is None or target_raw is None:
        if window_ids is not None and target_id is not None:
            return []  # the identity check above was evaluable and clean
        return [
            LeakageFinding(
                Rejection.UNEVALUABLE,
                "is_rolling_window is set but neither (window_end_timestamp, target_game_timestamp) "
                "nor (window_game_ids, target_game_id) is complete — the window cannot be bounded",
                subject,
            )
        ]
    try:
        end, target = parse_utc(end_raw, field="window_end_timestamp"), parse_utc(
            target_raw, field="target_game_timestamp"
        )
    except TimestampContractError as exc:
        return [LeakageFinding(Rejection.UNEVALUABLE, f"window bounds unusable: {exc}", subject)]

    if end >= target:
        return [
            LeakageFinding(
                Rejection.ROLLING_WINDOW_CONTAINS_TARGET,
                f"window_end={end.isoformat()} reaches target game at {target.isoformat()}",
                subject,
            )
        ]
    return []


# ── the composed gate ───────────────────────────────────────────────────────────────────
@dataclass
class GuardReport:
    """The outcome of a guard pass. `ok` is True only when NOTHING was found."""

    checked: int = 0
    findings: list[LeakageFinding] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.findings

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for f in self.findings:
            out[f.reason.name] = out.get(f.reason.name, 0) + 1
        return out


def evaluate_point_in_time(
    records,
    projection_timestamp,
    *,
    store_index: dict | None = None,
    closing_window_minutes: int = DEFAULT_CLOSING_WINDOW_MINUTES,
) -> GuardReport:
    """Run every §13 clause over `records`. Returns the report; does NOT raise."""
    report = GuardReport()
    for record in records:
        report.checked += 1
        report.findings.extend(check_provenance_present(record))
        report.findings.extend(check_timestamps_not_after_projection(record, projection_timestamp))
        report.findings.extend(check_original_capture(record, store_index))
        report.findings.extend(
            check_market_phase(record, projection_timestamp, closing_window_minutes=closing_window_minutes)
        )
        report.findings.extend(check_rolling_window(record))
    return report


def assert_point_in_time(
    records,
    projection_timestamp,
    *,
    store_index: dict | None = None,
    closing_window_minutes: int = DEFAULT_CLOSING_WINDOW_MINUTES,
) -> GuardReport:
    """FAIL-CLOSED gate: raise `LeakageRejection` on any finding.

    This is HALT-tier by design — a leaked build is not a degraded build, it is an INVALID one,
    and a warning that scrolls past is exactly the E11.30 "detected, nobody notified" failure.
    """
    report = evaluate_point_in_time(
        records,
        projection_timestamp,
        store_index=store_index,
        closing_window_minutes=closing_window_minutes,
    )
    if not report.ok:
        raise LeakageRejection(report.findings)
    return report
