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
    max_lag_hours: float     # ACTIVE hours since the last commit before it is STALE (see below)
    cadence: str             # the writer's declared cadence, in words
    why: str                 # what silently degrades when this freezes
    remediate: str           # the operator's first action
    #: NCAAF-P1.2W — the CALENDAR MONTHS in which this writer is supposed to run, or None for a
    #: writer with no seasonal cliff. `None` is the default precisely so every pre-existing
    #: contract keeps plain wall-clock lag, byte-identical.
    #:
    #: ⭐ WHY IT MUST BE ACTIVE-WINDOW LAG AND NOT A "SKIP THE CHECK OFF-SEASON" FLAG (INC-41's
    #: core mechanic). Suppressing the check while `now` is off-season leaves the FIRST in-season
    #: read seeing a lag that spans the whole winter, so the monitor's first act every August
    #: would be a false CRITICAL. Counting only the minutes inside the window makes a January
    #: final commit legitimately fresh right through July and start ageing again on August 1 —
    #: idle by DECLARATION rather than by a silently suppressed check.
    active_months: tuple[int, ...] | None = None
    #: NCAAB-P0 — hours at the START of an active run during which a MISSING write is not yet a
    #: defect, because the writer legitimately has nothing to write.
    #:
    #: 🔴 THE DEFECT THIS CLOSES, MEASURED BEFORE ARMING RATHER THAN AFTER IT PAGED. `active_months`
    #: is MONTH-granular, so an NCAAB contract's clock restarts at 00:00 on November 1 — but the
    #: D-I season tips ~November 3, and hoopR publishes `team_box_YYYY` only once games have been
    #: PLAYED. So a 36h SLA on the box-score table breaches at **Nov 3 00:00Z, about twelve hours
    #: BEFORE the first tip**, and keeps paging CRITICAL until the first box file lands — every
    #: season, on a completely healthy pipeline, in the opening week when the monitor is most
    #: likely to be believed. That is the same systematic-false-page failure `active_lag_hours`
    #: was written to prevent at the season BOUNDARY, reappearing at the season's START because a
    #: month boundary cannot express "the season has actually tipped".
    #:
    #: ⭐ IT IS A GRACE, NOT AN EXEMPTION, and the distinction is what keeps the contract
    #: falsifiable. The budget is widened only while the active run is YOUNGER than this many
    #: hours; past it the ordinary `max_lag_hours` applies unchanged. So "box scores have not
    #: started yet" stays quiet, while "box scores never arrived at all" still pages — which a
    #: blanket in-season exemption would have silenced forever (the NF1.7(a) vacuous-anchor class).
    #:
    #: Defaults to 0.0, so every pre-existing contract is byte-identical.
    season_warmup_hours: float = 0.0


# ── The registry ────────────────────────────────────────────────────────────────────────────
# Deliberately small. An entry is a CLAIM about a table's real commit behaviour, and an
# unmeasured claim produces a permanent false page (the reason INC-41 REJECTED
# `feature_pregame_game_features_raw` from its own registry). Only add a table whose cadence you
# have actually observed.
#: NCAAF-P1.2W — the season window, imported from the module that owns it rather than retyped as
#: `(8, 9, 10, 11, 12, 1)` here. A second literal is a second owner of the season boundary, and a
#: month-range that drifts from the cron it describes is this repo's documented seasonal-hole class
#: (E9.48(c) / INC-37 / NCAAF-RF1).
from betting_ml.monitoring.ncaaf_strength_refit import SEASON_MONTHS as _NCAAF_SEASON_MONTHS

#: NCAAB-P0 — the season window, imported from the module that OWNS it rather than retyped, for
#: the same reason as the NCAAF line above: a second literal is a second owner of the boundary.
#: `ncaab_season` imports nothing from here, so this direction is one-way and cycle-free.
from betting_ml.monitoring.ncaab_season import SEASON_MONTHS as _NCAAB_SEASON_MONTHS

REGISTRY: tuple[SportsDeltaContract, ...] = (
    # ── NCAAB (armed 2026-09-15, when the schedule's first AUTONOMOUS fire succeeded) ────
    # ⚠️ DEFINED HERE, not imported from `ncaab_freshness`, and that is forced: that module
    # imports `SportsDeltaContract` from THIS one, so importing its objects back is a cycle
    # (measured: `partially initialized module` whenever ncaab_freshness is imported first).
    # The season window comes from `ncaab_season`, which imports nothing from here — a one-way
    # dependency, not an ordering trick. `ncaab_freshness.ARMED_IN_REGISTRY` names these two,
    # and a guard cross-checks them against this registry.
    SportsDeltaContract(
        name="ncaab_schedules",
        sport="ncaab",
        source="schedules",
        tier="raw",
        # Daily writer. 36h tolerates a late run and one deploy window, not a skipped day.
        max_lag_hours=36.0,
        cadence="daily 14:00Z (sports_ncaab_ingest_schedule, RUNNING; first autonomous fire 2026-09-15)",
        active_months=_NCAAB_SEASON_MONTHS,
        why=("the game spine every NCAAB surface and model reads. Frozen, the slate silently "
             "stops advancing while every job still reports success — hoopR overwrites the "
             "current season's file in place, so a frozen mirror is indistinguishable from a "
             "quiet day in every signal except this one"),
        remediate=("run the ingest for the current season and READ THE RECEIPT: "
                   "`uv run python -m quant_sports_intel_models.basketball.ncaab.ingest.handler "
                   "--sources schedules`. It exits non-zero on an escalation rather than "
                   "swallowing, and refuses to overwrite a good partition with an empty one"),
    ),
    SportsDeltaContract(
        name="ncaab_team_box",
        sport="ncaab",
        source="team_box",
        tier="raw",
        max_lag_hours=36.0,
        cadence="daily 14:00Z (sports_ncaab_ingest_schedule, RUNNING; first autonomous fire 2026-09-15)",
        active_months=_NCAAB_SEASON_MONTHS,
        why=("the box lines the possession estimate — and therefore every tempo and efficiency "
             "figure — is computed from. Frozen, ratings keep serving off last week's games "
             "with no error anywhere"),
        remediate=("as ncaab_schedules, with `--sources team_box`. ⚠️ Before the season's first "
                   "tip the upstream file legitimately 404s and the ingest reports "
                   "`not published yet` — that is the expected pre-season state, which is why "
                   "this contract is active_months-gated and not wall-clock"),
        # ⭐ MEASURED BEFORE ARMING, NOT AFTER IT PAGED. `active_months` restarts this clock at
        # 00:00 on Nov 1, but the season tips ~Nov 3 and hoopR publishes `team_box_YYYY` only
        # once games have been PLAYED — so a bare 36h SLA breaches Nov 3 00:00Z, about twelve
        # hours BEFORE the first tip, and pages CRITICAL right through opening week on a
        # perfectly healthy pipeline. 120h covers the window opening -> first tip -> first box
        # file with room to spare, and it is a GRACE not an exemption: from 120h in, the
        # ordinary 36h SLA applies, so a feed that never starts at all still pages (verified at
        # Nov 6 and Nov 20).
        season_warmup_hours=120.0,
    ),
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
    SportsDeltaContract(
        name="ncaaf_team_strength_week",
        sport="ncaaf",
        source="team_strength_week",
        tier="derived",
        # NCAAF-P1.2W. The writer is WEEKLY (`sports_ncaaf_strength_refit_schedule`, Mon 07:30 PT,
        # Aug-Jan), so the SLA is one cadence plus a day of grace: 192 ACTIVE hours. `classify`
        # then splits the two regimes it must not conflate — up to 2x the SLA is ONE missed Monday
        # (WARN, the schedule can be re-fired while the week is still ahead), beyond it the re-fit
        # is not running at all (CRITICAL). Sized against the break it exists to catch, which was
        # sitting at 619 wall-clock hours on 2026-09-13.
        max_lag_hours=192.0,
        cadence="weekly, Monday 07:30 America/Los_Angeles, Aug-Jan "
                "(sports_ncaaf_strength_refit_schedule)",
        # ⭐ THE SEASON WINDOW, and it is the reason this contract could not simply reuse wall-clock
        # lag. Between the CFP final and August there is genuinely nothing to re-fit, so the last
        # January commit must stay OK for ~6 months and start ageing again on August 1 — idle by
        # DECLARATION, never by a silently suppressed check.
        active_months=_NCAAF_SEASON_MONTHS,
        why=(
            "every NCAAF surface's strength rating, uncertainty band and both ranks move ONLY when "
            "this table is rewritten. Frozen, a team can win by 26 on Saturday while its rating "
            "sits unchanged beside that win in its own schedule — which is what NCAAF-P3.3b "
            "measured and NCAAF-P1.2W exists to end. It is also what the served 'next update' "
            "stamp now PROMISES, so a freeze here turns a stated date into an overclaim"
        ),
        remediate=(
            "launch sports_ncaaf_strength_refit_job in Dagit and READ THE RUN — it fails loud on a "
            "cold-start reproduction rather than reporting a green tick. Check first that "
            "sports_ncaaf_roll_forward_schedule is RUNNING (the job refuses to fit on raw games it "
            "considers stale) and that SPORTS_DUCKDB_PATH points inside the sports_duckdb volume"
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

    lag_hours = round(active_lag_hours(reading.last_commit, now, contract.active_months), 2)
    wall_hours = round((now - reading.last_commit).total_seconds() / 3600.0, 2)
    window = ("" if contract.active_months is None
              else f" [ACTIVE-WINDOW lag over months {contract.active_months}; "
                   f"{wall_hours}h wall-clock]")
    if reading.rows is not None and reading.rows <= 0:
        return {"name": contract.name, "verdict": "EMPTY", "severity": "CRITICAL",
                "lag_hours": lag_hours,
                "detail": (f"the newest commit (v{reading.version}, {lag_hours}h ago) wrote ZERO "
                           f"rows. The table is advancing but carrying nothing.")}
    if contract.season_warmup_hours > 0.0:
        # Hours since the CURRENT active run opened — a different quantity from `lag_hours`,
        # which is measured from the last commit. Reusing the same clock keeps one owner for the
        # window arithmetic (the rule `active_lag_hours` already documents).
        run_age = (0.0 if contract.active_months is None
                   else active_lag_hours(active_window_start(now, contract.active_months), now,
                                         contract.active_months))
        if run_age <= contract.season_warmup_hours:
            return {"name": contract.name, "verdict": "WARMUP", "severity": None,
                    "lag_hours": lag_hours,
                    "detail": (f"{run_age:.1f}h into this season's active window, inside the "
                               f"{contract.season_warmup_hours:.0f}h warmup. The writer has "
                               f"nothing to write yet, which is not the same as having stopped — "
                               f"the ordinary {contract.max_lag_hours}h SLA applies from "
                               f"{contract.season_warmup_hours:.0f}h in, so a feed that never "
                               f"starts still pages.")}
    if lag_hours > contract.max_lag_hours:
        # ≤2x the SLA is one missed cycle; beyond it the writer is not running at all.
        severity = "WARN" if lag_hours <= 2 * contract.max_lag_hours else "CRITICAL"
        return {"name": contract.name, "verdict": "STALE", "severity": severity,
                "lag_hours": lag_hours,
                "detail": (f"last Delta commit v{reading.version} was {lag_hours}h ago, over the "
                           f"{contract.max_lag_hours}h SLA{window} (cadence: {contract.cadence}). "
                           f"{contract.why}. FIRST ACTION: {contract.remediate}")}
    return {"name": contract.name, "verdict": "OK", "severity": None, "lag_hours": lag_hours,
            "detail": (f"last Delta commit v{reading.version} {lag_hours}h ago "
                       f"(SLA {contract.max_lag_hours}h){window}"
                       + (f", {reading.rows} rows" if reading.rows is not None else ""))}


def active_lag_hours(last_commit: datetime, now: datetime,
                     active_months: "tuple[int, ...] | None") -> float:
    """Hours of DECLARED-ACTIVE time between `last_commit` and `now`.

    ⭐ ONE OWNER for the window arithmetic: `artifact_freshness.active_minutes_between`, the INC-41
    instrument that already walks day/hour buckets and handles a month axis. A second copy here is
    the "one logical thing, two execution owners" shape this repo keeps paying for (INC-30/36/38).

    ⭐⭐ AND ONE THING INC-41's HOURLY WINDOWS NEVER HAD TO DECIDE: WHETHER LAG CARRIES ACROSS THE
    GAP. An overnight window is ~10 hours, so whatever accrues before it is small and carrying it
    is harmless. A SEASON gap is ~six months, and the tail of the last active month carries
    straight into the first active month of the next season — which produces a SYSTEMATIC false
    page every opening week, at the exact moment the monitor is most likely to be believed.
    Measured on this contract: a final fit on the last Monday of January 2027 carries 152h into
    August and breaches a 192h SLA barely an hour after the season's first scheduled fire.

    So the clock RESTARTS at the beginning of the current active run of months. That is what "idle
    by declaration" actually means: the off-season is not a suspended check (which would fire on
    its first read back), and it is not forgiven staleness either — the season simply begins with a
    fresh clock, and an artifact that has not been rewritten `max_lag_hours` into the season is
    STALE on its own merits rather than on the winter's.

    Returns 0.0 whenever `now` itself is outside the window: there is no cadence to be late for.
    """
    from betting_ml.monitoring.artifact_freshness import active_minutes_between

    if active_months is None:
        return max(0.0, (now - last_commit).total_seconds() / 3600.0)
    if now.month not in active_months:
        return 0.0
    start = max(last_commit, active_window_start(now, active_months))
    return active_minutes_between(start, now, None, None, active_months) / 60.0


def active_window_start(now: datetime, active_months: "tuple[int, ...]") -> datetime:
    """Midnight UTC on the first day of the CURRENT contiguous run of active months.

    Walks back a month at a time while the month is still in the window, so a wrap-around season
    (Aug→Jan) resolves to the previous August rather than to January 1st. `now` is assumed inside
    the window; the caller checks that first.
    """
    from datetime import timedelta

    cursor = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    # At most 12 steps: a run of active months cannot be longer than a year.
    for _ in range(12):
        previous = (cursor - timedelta(days=1)).replace(day=1)
        if previous.month not in active_months:
            return cursor
        cursor = previous
    return cursor


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
