"""timestamps.py — the §13 timestamp-key contract (PURE; no IO, no clock reads except `now_utc`).

The doc §13 required keys, and what each one MEANS (they are NOT interchangeable — the whole
fail-closed guard is a set of comparisons between them, so a wrong assignment silently disarms a
clause):

    projection_timestamp      the instant the BUILD claims to stand at. The reference. A Tuesday
                              model may consume only facts whose every other stamp is <= this.
    feature_timestamp         the as-of instant of the FEATURE VALUE itself (the last event the
                              feature summarises — e.g. the last game in a rolling window).
    source_timestamp          the SOURCE's own as-of claim (an odds `last_update`, an injury
                              report's `date_modified`). ⚠️ NF-W0 defect #2: nflverse DELETED
                              `injuries.date_modified` in 2025, so for injuries this is now NULL
                              upstream and `capture_timestamp` is the only honest as-of we have —
                              which is exactly why we capture forward.
    capture_timestamp         when WE fetched it. The ONE stamp we always control and the only
                              one that cannot be retroactively manufactured.
    vendor_release_timestamp  when the VENDOR published the artifact we read (an nflverse release
                              asset's Last-Modified). Distinct from source_timestamp: a release
                              published Wednesday can contain Sunday facts.
    ingestion_timestamp       when the row landed in OUR store.

TWO STORAGE RULES, both learned the hard way in this repo:

  • ISO-8601 UTC **VARCHAR**, always (INC-23 / the W8a binary-parquet-timestamp landmine).
    Snowflake mis-reads binary INT64 parquet timestamps per-row; DuckDB casts an ISO string at
    the use-site with no ambiguity. Never store a binary timestamp here.
  • TIMEZONE-AWARE OR REJECT. A naive datetime is refused, never assumed-UTC — this repo has
    produced FOUR distinct LTZ/NTZ confusion bugs (E11.20 phase-2b cost SIX DAYS of slate-wide
    false abstains off exactly one such assumption). Guessing a timezone is how a 7-hour error
    renders as a completely plausible timestamp.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone

# ── the §13 contract ────────────────────────────────────────────────────────────────────
PROJECTION_TIMESTAMP = "projection_timestamp"

#: Every stamp a captured record must carry, in doc §13 order. `projection_timestamp` is NOT
#: here — a CAPTURE has no projection; it is supplied by the BUILD that consumes the capture.
CAPTURE_TIMESTAMP_KEYS: tuple[str, ...] = (
    "feature_timestamp",
    "source_timestamp",
    "capture_timestamp",
    "vendor_release_timestamp",
    "ingestion_timestamp",
)

#: The full §13 key set (what a record joined into a build must carry).
REQUIRED_TIMESTAMP_KEYS: tuple[str, ...] = (PROJECTION_TIMESTAMP,) + CAPTURE_TIMESTAMP_KEYS

#: Non-timestamp provenance every immutable capture row carries. `capture_id` is the immutable
#: identity of ONE capture event; `payload_sha256` is what makes a silent vendor REVISION
#: detectable (§13 "revised vendor data replaced the original captured record").
REQUIRED_PROVENANCE_KEYS: tuple[str, ...] = (
    "capture_source",
    "capture_id",
    "subject_key",
    "payload_sha256",
)


class TimestampContractError(ValueError):
    """A timestamp value violates the storage contract (naive, unparseable, or absent)."""


def now_utc() -> datetime:
    """The capture clock. Timezone-aware UTC, always — injectable by callers for tests."""
    return datetime.now(timezone.utc)


def to_utc_iso(value: datetime | str, *, field: str = "timestamp") -> str:
    """Normalise to the stored form: an ISO-8601 string with an explicit `+00:00` UTC offset.

    ⛔ FAIL-CLOSED on a naive datetime or a naive ISO string. "It's probably UTC" is the exact
    assumption behind this repo's LTZ/NTZ family of bugs; a caller that genuinely has UTC can
    say so in one keystroke (`.replace(tzinfo=timezone.utc)`), and a caller that does NOT have
    UTC gets an error instead of a silent multi-hour shift.
    """
    if value is None:
        raise TimestampContractError(f"{field}: missing (fail-closed — a PIT stamp is never optional)")
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            raise TimestampContractError(f"{field}: empty string is not a timestamp")
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError as exc:
            raise TimestampContractError(f"{field}: {raw!r} is not ISO-8601 ({exc})") from exc
    elif isinstance(value, datetime):
        parsed = value
    else:
        raise TimestampContractError(f"{field}: {type(value).__name__} is not a datetime/ISO string")

    if parsed.tzinfo is None or parsed.tzinfo.utcoffset(parsed) is None:
        raise TimestampContractError(
            f"{field}: {value!r} is TIMEZONE-NAIVE. Refused rather than assumed-UTC — an assumed "
            f"offset renders as a perfectly plausible timestamp and silently shifts every "
            f"comparison (see the E11.20 phase-2b LTZ/NTZ incident)."
        )
    return parsed.astimezone(timezone.utc).isoformat()


def parse_utc(value: datetime | str, *, field: str = "timestamp") -> datetime:
    """Parse a stored stamp back to an aware UTC datetime (same fail-closed rules as `to_utc_iso`)."""
    return datetime.fromisoformat(to_utc_iso(value, field=field))


def payload_sha256(payload, exclude: tuple[str, ...] = ()) -> str:
    """A stable content hash of a captured payload's SUBSTANCE.

    `sort_keys` makes it invariant to dict ordering, so a re-serialised identical payload hashes
    identically and only a real content change moves the digest. This is the whole detection
    mechanism for the §13 "revised vendor data replaced the original" rejection.

    ⚠️ `exclude` DROPS declared VOLATILE top-level keys before hashing, and it is load-bearing
    rather than cosmetic. Measured 2026-08-05: Open-Meteo stamps every response with a
    `generationtime_ms` server-timing value, so two byte-identical forecasts hash differently and
    EVERY benign re-fetch was classified as a vendor revision. A revision detector with a 100%
    false-positive rate is worse than none — it is the over-paging monitor that gets muted, and
    then the one real revision goes unread.

    ⛔ The excluded set is STORED on the row (`hash_excluded_keys`) precisely because a hash that
    silently ignores fields is its own silent-death risk: excluding a substantive field would
    blind the detector with nothing to show for it.
    """
    if exclude and isinstance(payload, dict):
        payload = {k: v for k, v in payload.items() if k not in set(exclude)}
    blob = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def capture_id(*, capture_source: str, subject_key: str, checkpoint: str) -> str:
    """The DETERMINISTIC identity of one capture event.

    Deterministic (not a uuid) so a re-fired cron in the same checkpoint window produces the SAME
    id — that is what lets an append-only store deduplicate without ever overwriting, and what
    lets a revision be recognised as "same capture identity, different payload hash".
    """
    raw = f"{capture_source}|{subject_key}|{checkpoint}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


@dataclass(frozen=True)
class CaptureStamps:
    """The immutable stamp block attached to every captured record.

    Constructed via `build` so a capture site cannot forget a key or store a naive value — the
    "provenance missing" rejection should be impossible to reach from OUR OWN writers, and only
    reachable from a foreign/legacy record.
    """

    capture_source: str
    capture_id: str
    subject_key: str
    payload_sha256: str
    hash_excluded_keys: str
    feature_timestamp: str
    source_timestamp: str | None
    capture_timestamp: str
    vendor_release_timestamp: str | None
    ingestion_timestamp: str

    @classmethod
    def build(
        cls,
        *,
        capture_source: str,
        subject_key: str,
        checkpoint: str,
        payload,
        feature_timestamp: datetime | str,
        capture_timestamp: datetime | str,
        source_timestamp: datetime | str | None = None,
        vendor_release_timestamp: datetime | str | None = None,
        ingestion_timestamp: datetime | str | None = None,
        hash_exclude: tuple[str, ...] = (),
    ) -> "CaptureStamps":
        cap = to_utc_iso(capture_timestamp, field="capture_timestamp")
        return cls(
            capture_source=capture_source,
            capture_id=capture_id(
                capture_source=capture_source, subject_key=subject_key, checkpoint=checkpoint
            ),
            subject_key=subject_key,
            payload_sha256=payload_sha256(payload, exclude=hash_exclude),
            hash_excluded_keys=",".join(sorted(hash_exclude)),
            feature_timestamp=to_utc_iso(feature_timestamp, field="feature_timestamp"),
            capture_timestamp=cap,
            # ⚠️ source_timestamp is legitimately NULL for injuries (nflverse deleted
            # `date_modified` in 2025). NULL here means "the vendor publishes no as-of claim",
            # which the guard treats as UNKNOWN — NOT as "safe". See leakage_guard.
            source_timestamp=(
                None if source_timestamp is None else to_utc_iso(source_timestamp, field="source_timestamp")
            ),
            vendor_release_timestamp=(
                None
                if vendor_release_timestamp is None
                else to_utc_iso(vendor_release_timestamp, field="vendor_release_timestamp")
            ),
            ingestion_timestamp=to_utc_iso(
                ingestion_timestamp if ingestion_timestamp is not None else cap,
                field="ingestion_timestamp",
            ),
        )

    def as_dict(self) -> dict:
        return {
            "capture_source": self.capture_source,
            "capture_id": self.capture_id,
            "subject_key": self.subject_key,
            "payload_sha256": self.payload_sha256,
            "hash_excluded_keys": self.hash_excluded_keys,
            "feature_timestamp": self.feature_timestamp,
            "source_timestamp": self.source_timestamp,
            "capture_timestamp": self.capture_timestamp,
            "vendor_release_timestamp": self.vendor_release_timestamp,
            "ingestion_timestamp": self.ingestion_timestamp,
        }
