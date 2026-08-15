"""NF-INFRA1 — artifact-freshness SLAs for the SPORTS S3 Delta lake, read from INSIDE `_delta_log`.

WHY (NF-FRESH1 / INC-41): `sports_nfl_sleeper_injuries_schedule` returned SUCCESS on 19 consecutive
daily runs while `nfl/raw/sleeper_injuries` held ONE 19-day-old commit. Every instrument that
watched the JOB was green the whole time, because the job genuinely completed — it just wrote
nothing. ⭐ A heartbeat, a run-status check and a schedule-is-RUNNING check are all structurally
incapable of seeing that. The only signal that can is the ARTIFACT's own advance, which is the
INC-41 lesson restated for the sports lake: assert on the landed data, not on the producer.

⛔ NEVER AN S3 `LastModified` — INC-41's central mechanic, and it applies with full force here:
  * `aws s3 ls` prints SHELL-LOCAL time, not UTC (a ~5-6h phantom staleness);
  * an mtime is refreshed by any server-side rewrite that changes no data;
  * Delta compaction/vacuum rewrites files without a logical update.
The timestamp used here is the Delta transaction log's own COMMIT timestamp — written by the
writer, at commit time, inside `_delta_log`. It advances if and only if a commit happened, which
is exactly the question.

TIERING — this module DECIDES, it never pages or raises. `pipeline/jobs/…` does the paging so the
policy stays import-safe for the fast gate (the E11.23 rule: nothing here imports `pipeline`).

⚠️ AN UNREADABLE TABLE IS `UNKNOWN`/WARN, NEVER HEALTHY (NF1.7(a)) — a check that could not run is
not a check that passed. That distinction is the whole reason this module exists.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class SportsDeltaContract:
    """One sports-lake Delta table's declared freshness SLA."""

    name: str                # human/`[METRIC]` key, e.g. "nfl_sleeper_injuries"
    sport: str               # s3io.table_uri(sport=…)
    source: str              # s3io.table_uri(source=…)
    tier: str                # "raw" | "derived"
    max_lag_hours: float     # wall-clock hours since the last commit before it is STALE
    cadence: str             # the writer's declared cadence, in words
    why: str                 # what silently degrades when this freezes
    remediate: str           # the operator's first action


# ── The registry ────────────────────────────────────────────────────────────────────────────
# Deliberately small. An entry is a CLAIM about a table's real commit behaviour, and an
# unmeasured claim produces a permanent false page (the reason INC-41 REJECTED
# `feature_pregame_game_features_raw` from its own registry). Only add a table whose cadence you
# have actually observed.
REGISTRY: tuple[SportsDeltaContract, ...] = (
    SportsDeltaContract(
        name="nfl_sleeper_injuries",
        sport="nfl",
        source="sleeper_injuries",
        tier="raw",
        # The writer is DAILY (`NFL_SLEEPER_INJURIES_CRON = "30 6 * 3-12,1-2 *"`, i.e. every month,
        # every day, 06:30 PT). 36h therefore tolerates a late run and one deploy window but not a
        # SKIPPED DAY, and `classify` splits the two regimes it must not conflate: ≤2× the SLA is a
        # missed cycle (WARN), beyond it the feed is dead (CRITICAL). The break this exists to catch
        # sat at ~456h.
        max_lag_hours=36.0,
        cadence="daily, 06:30 America/Los_Angeles (sports_nfl_sleeper_injuries_schedule)",
        why=(
            "the forward-availability designations (PUP/RES/NFI/SUS) `load_forward_roster_status` "
            "COALESCEs OVER nflverse's lagging roster status. Frozen = the draft board quietly "
            "reverts to nflverse-only months-late availability, with no error anywhere: NF-FRESH1 "
            "measured 19 days of it behind 19 green runs"
        ),
        remediate=(
            "launch sports_nfl_sleeper_injuries_job in Dagit and READ THE RUN — post-NF-INFRA1 it "
            "fails loud instead of swallowing. The usual cause is the sports DuckDB: confirm "
            "SPORTS_DUCKDB_PATH points inside the sports_duckdb volume and that "
            "sports_nfl_dbt_build_job has materialized it"
        ),
    ),
)


@dataclass(frozen=True)
class DeltaReading:
    """What the Delta log actually said (or why it could not be read)."""

    name: str
    last_commit: datetime | None = None   # tz-aware UTC
    version: int | None = None
    rows: int | None = None               # last commit's num_output_rows, when the writer reports it
    error: str | None = None

    @property
    def readable(self) -> bool:
        return self.error is None and self.last_commit is not None


def by_name(name: str) -> SportsDeltaContract:
    for c in REGISTRY:
        if c.name == name:
            return c
    raise KeyError(f"no sports Delta freshness contract named {name!r} "
                   f"(have: {', '.join(c.name for c in REGISTRY)})")


def classify(contract: SportsDeltaContract, reading: DeltaReading,
             now: datetime | None = None) -> dict:
    """PURE — the verdict for one contract/reading.

    Verdicts: `OK` · `STALE` (lag over SLA) · `EMPTY` (a commit that wrote zero rows) ·
    `UNKNOWN` (unreadable — WARN, never healthy).
    """
    now = now or datetime.now(timezone.utc)
    if not reading.readable:
        return {"name": contract.name, "verdict": "UNKNOWN", "severity": "WARN",
                "lag_hours": None,
                "detail": (f"could not read the Delta log for {contract.sport}/{contract.tier}/"
                           f"{contract.source}: {reading.error or 'no commit timestamp'}. "
                           "Reported UNVERIFIED rather than healthy — a check that could not run "
                           "is not a check that passed.")}

    lag_hours = round((now - reading.last_commit).total_seconds() / 3600.0, 2)
    if reading.rows is not None and reading.rows <= 0:
        return {"name": contract.name, "verdict": "EMPTY", "severity": "CRITICAL",
                "lag_hours": lag_hours,
                "detail": (f"the newest commit (v{reading.version}, {lag_hours}h ago) wrote ZERO "
                           f"rows. The table is advancing but carrying nothing.")}
    if lag_hours > contract.max_lag_hours:
        # ≤2x the SLA is one missed cycle; beyond it the writer is not running at all.
        severity = "WARN" if lag_hours <= 2 * contract.max_lag_hours else "CRITICAL"
        return {"name": contract.name, "verdict": "STALE", "severity": severity,
                "lag_hours": lag_hours,
                "detail": (f"last Delta commit v{reading.version} was {lag_hours}h ago, over the "
                           f"{contract.max_lag_hours}h SLA (cadence: {contract.cadence}). "
                           f"{contract.why}. FIRST ACTION: {contract.remediate}")}
    return {"name": contract.name, "verdict": "OK", "severity": None, "lag_hours": lag_hours,
            "detail": (f"last Delta commit v{reading.version} {lag_hours}h ago "
                       f"(SLA {contract.max_lag_hours}h)"
                       + (f", {reading.rows} rows" if reading.rows is not None else ""))}


def is_problem(verdict: dict) -> bool:
    """True when the verdict warrants operator attention (anything but OK)."""
    return verdict.get("verdict") != "OK"


# ── The reader (IO — imported lazily so this module stays fast-gate safe) ────────────────────
def read_contract(contract: SportsDeltaContract, *, bucket: str | None = None,
                  local_root: str | None = None) -> DeltaReading:
    """Read the newest `_delta_log` commit for `contract`. Never raises — an unreadable table
    becomes a `DeltaReading` carrying the error, which `classify` turns into UNKNOWN/WARN."""
    try:
        from deltalake import DeltaTable

        from quant_sports_intel_models.football.nfl.ingest import s3io

        if local_root:
            uri = s3io.local_table_uri(local_root, contract.sport, contract.source,
                                       tier=contract.tier)
            opts = None
        else:
            uri = s3io.table_uri(contract.sport, contract.source,
                                 bucket=bucket or s3io.DEFAULT_BUCKET, tier=contract.tier)
            opts = s3io.storage_options(
                os.environ.get("SPORTS_LAKE_REGION", s3io.DEFAULT_REGION))
        dt = DeltaTable(uri, storage_options=opts)
        history = dt.history(1)
        if not history:
            return DeltaReading(name=contract.name, error=f"{uri} has an EMPTY transaction log")
        entry = history[0]
        return DeltaReading(
            name=contract.name,
            last_commit=_commit_timestamp(entry),
            version=_as_int(entry.get("version")),
            rows=_commit_rows(entry),
        )
    except Exception as exc:  # noqa: BLE001 — surfaced as UNKNOWN/WARN, never swallowed
        return DeltaReading(name=contract.name, error=f"{type(exc).__name__}: {exc}")


def _as_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _commit_timestamp(entry: dict) -> datetime | None:
    """delta-rs reports `timestamp` as EPOCH MILLISECONDS (an int), but the field has been a
    datetime in some versions — accept either rather than silently returning None (which would
    read as UNKNOWN forever)."""
    raw = entry.get("timestamp")
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    ms = _as_int(raw)
    if ms is None:
        return None
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)


def _commit_rows(entry: dict) -> int | None:
    """The commit's output-row count when the writer reported one. `None` (not 0) when absent —
    an ABSENT metric must never classify as EMPTY."""
    metrics = entry.get("operationMetrics") or {}
    if not isinstance(metrics, dict):
        return None
    for key in ("num_output_rows", "numOutputRows"):
        if key in metrics:
            return _as_int(metrics[key])
    return None


def evaluate(contracts: "tuple[SportsDeltaContract, ...] | None" = None,
             *, now: datetime | None = None, bucket: str | None = None,
             local_root: str | None = None) -> list[dict]:
    """Read + classify every contract. Returns one verdict dict per contract, in registry order."""
    now = now or datetime.now(timezone.utc)
    out = []
    for contract in (contracts if contracts is not None else REGISTRY):
        out.append(classify(contract, read_contract(contract, bucket=bucket,
                                                    local_root=local_root), now=now))
    return out
