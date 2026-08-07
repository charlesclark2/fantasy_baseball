"""artifact_freshness.py — per-artifact freshness SLAs on serving-critical parquet (INC-41).

WHY THIS EXISTS
    On 2026-08-06 a vendor INT32_MIN odds price crashed the `--w3pre-only` build. Because
    `--w3pre-only` and `--w7b-only` shared ONE try block, the lineups rebuild never ran:
    `stg_statsapi_lineups_wide` FROZE at 20:08Z and the lineup monitor read that frozen parquet
    for **6.5 hours across ~40 ticks**, reporting "No newly confirmed lineups" while the op
    returned SUCCESS every 30 minutes. Three games went unscored past first pitch.

    ⭐ THE THING THAT MADE IT INVISIBLE: **the FEED was healthy the whole time.** Every existing
    check watches a SOURCE (is the capture running? is the raw mirror advancing? did the op
    raise?) and every one of them was correctly green. Nothing asserted that the DERIVED artifact
    the serving path actually reads had ADVANCED. That is the INC-37 / E9.48 / Byparr class: a
    frozen derived artifact is structurally invisible to a freshness check on its source, and to
    a liveness check on the job that builds it.

    PR #638 fixed the two proximate causes (the bigint parse; the shared try block, which now
    pages per leg). Neither closes the general hole: a leg that FAILS now pages, but a build that
    is SKIPPED, gated off, never scheduled, or whose sensor stopped ticking still freezes the
    artifact in total silence. This module asserts the artifact itself.

⛔ WHY NOT S3 `LastModified` — the obvious implementation, and it is wrong twice over.
    (1) `aws s3 ls` prints LastModified in the SHELL'S LOCAL TIME, not UTC (E11.20 phase-2a),
        so diffing it against a UTC clock manufactures a ~5-6h phantom staleness.
    (2) More fundamentally, PR #638 made the S3 writes ATOMIC via a server-side copy — so a
        re-copied object carries a FRESH mtime even when the DATA inside it is unchanged. An
        mtime check would have read GREEN through the very incident it was meant to catch.
    ⇒ freshness is read from a CONTENT timestamp INSIDE the parquet, always.

⏰ THE CORE MECHANISM — ACTIVE-MINUTE LAG, not wall-clock lag.
    A naive `now - content_ts > SLA` false-pages every night. The schedule-capture writer runs
    `*/30 14-23` + `0,30 0-3` UTC (verified in pipeline/schedules/intraday_schedules.py), so its
    last write of the day is 03:30 UTC and the next is 14:00 UTC — a DELIBERATE 10.5-hour gap in
    which a frozen-looking artifact is perfectly healthy. Measured live 2026-08-07 05:00 UTC:
    every schedule-derived artifact sat at 03:30 UTC, a 90-minute raw lag, entirely correct.

    So lag is accumulated ONLY over the writer's DECLARED ACTIVE WINDOWS:

        active_lag = |{ minutes in [content_ts, now) whose UTC hour is an active hour }|

    - Overnight gap (froze 03:30, now 05:00): active lag = 30 min ⇒ SILENT. Correct.
    - INC-41 (froze 20:08, now 02:38): active lag = 390 min ⇒ CRITICAL. Correct.
    - Band reopens (froze 03:30, now 14:05): active lag = 35 min ⇒ silent; by 15:30 it is 120 min
      ⇒ pages. Correct — nothing writing 90 min INTO the band is a real freeze.

    This is the W12/W9 lesson ("the check cadence must match the WRITE cadence") made declarative
    instead of per-monitor folklore. An artifact with no off-hours (`active_hours_utc=None`) just
    gets plain wall-clock lag, which falls out of the same function.

🪞 PROXY TIMESTAMPS — declared, never silent.
    `stg_statsapi_lineups_wide` — the INC-41 victim itself — carries NO timestamp column: the
    pivot `group by game_pk, official_date, home_away` drops the source's `ingestion_ts` (verified
    against the live parquet: 30 columns, the only temporal one is `official_date`, a DATE).
    Rather than change a serving-coupled dual-branch model's column contract (read by
    `write_serving_store`, `picks.py`, three feature models and a generated ext-table DDL) to add
    one, its contract declares a PROXY: `stg_statsapi_lineups`, which IS timestamped and which
    `_build_w7b` rebuilds from raw in the SAME `--w7b-only` invocation, immediately before the
    pivot (INC-31-B2). The proxy is labelled PROXY in the table, the metrics and the page body —
    it is never presented as the artifact's own reading.

    ⚠️ ITS ONE BLIND SPOT, STATED: if the flatten succeeds and the PIVOT alone raises, the proxy
    reads fresh while `lineups_wide` is stale. That case is NOT silent — the `--w7b-only`
    subprocess exits non-zero and `intraday_ops` pages CRITICAL on the failing leg (PR #638). The
    class this module exists to catch is the opposite one: a build that never runs and reports
    SUCCESS, where the proxy freezes in lockstep with the artifact. Between the two, the freeze is
    covered; the residual is a known, loud-elsewhere gap, not an unexamined assumption.

TIER (E11.7): ALERT-loud-but-continue. A stale artifact PAGES via `send_alert` and never HALTs —
    observability only (`best_alpha=0`), and a monitor must never withhold a slate. An artifact
    that cannot be evaluated (absent, unreadable, null timestamp) is WARN and is NEVER scored
    healthy: an anchor that fails to evaluate makes its assertion vacuously true (NF1.7 (a)).

Lives in betting_ml/ (not pipeline/) so the fast gate can import it — `pipeline/__init__.py`
    reads the dbt manifest, absent in CI, so a fast-gate test importing `pipeline` dies at
    COLLECTION (E11.23). Same shape as `w11_tail_coverage.py` / `spine_horizon.py`. PURE stdlib:
    no duckdb / boto3 / pandas at import.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

# ── Declared writer cadences ────────────────────────────────────────────────────────────
# UTC hours in which each writer is expected to run. Sourced from the deployed crons, not from
# intent: pipeline/schedules/intraday_schedules.py declares
#   intraday_schedule_capture_daytime    "*/30 14-23 * * *"
#   intraday_schedule_capture_overnight  "0,30 0-3  * * *"
# so the band is [14..23] ∪ [0..3]; the last fire is 03:30 UTC and the next is 14:00 UTC.
#
# ⚠️ HOUR 4 IS DELIBERATELY EXCLUDED, and getting this wrong is a nightly false page. The
# tempting reasoning is "include hour 4 so the 03:30 fire gets its 30-minute interval before lag
# counts against it" — but an HOUR-granularity window cannot express 30 minutes: including hour 4
# adds a full 60. Measured live 2026-08-07 05:04Z with hour 4 included, every schedule-derived
# artifact read a lag of EXACTLY 90 against an SLA of 90, passing only because the comparison is
# strictly `>`. Hour 3 already supplies the grace (the 03:30 fire's own interval runs 03:30-04:00,
# inside hour 3), so excluding hour 4 caps the overnight lag at 30 against the 90 SLA — 3x
# headroom instead of none.
SCHEDULE_CAPTURE_HOURS = (0, 1, 2, 3, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23)

# `None` = always active (plain wall-clock lag) — for artifacts on a once-daily build.
ALWAYS = None


@dataclass(frozen=True)
class FreshnessContract:
    """One serving-critical artifact's declared freshness SLA.

    `ts_expr` is a SQL expression over `ts_table` returning that artifact's CONTENT timestamp
    (never an S3 mtime). It is cast at the use-site because the lakehouse stores every TIMESTAMP
    as ISO VARCHAR (the INC-23 binary-timestamp cure), so a bare comparison would bind wrong.
    """

    name: str                       # the artifact whose freshness is being asserted
    ts_table: str                   # the table the timestamp is READ from (== name, unless proxied)
    ts_expr: str                    # SQL over ts_table -> content timestamp
    max_lag_minutes: int            # SLA, in ACTIVE minutes (see module docstring)
    active_hours_utc: tuple[int, ...] | None
    cadence: str                    # human description of the writer's cadence
    why: str                        # what breaks downstream when this artifact freezes
    remediate: str                  # the first thing an operator should do

    @property
    def is_proxied(self) -> bool:
        """True when the timestamp comes from a DIFFERENT artifact than the one being asserted."""
        return self.ts_table != self.name


# ── The registry ────────────────────────────────────────────────────────────────────────
# Ordered most-serving-critical first. Every entry's `ts_expr` was verified against the LIVE
# parquet on 2026-08-07 before being registered — `feature_pregame_game_features_raw` was
# CONSIDERED and REJECTED here: its only temporal column, `odds_ingestion_ts`, measured 40 HOURS
# stale on a healthy store (it records when the joined odds were captured, not when the store was
# built), so registering it would have produced a permanent false page. A registry entry is a
# claim about a column's behaviour and has to be measured, not assumed.
REGISTRY: tuple[FreshnessContract, ...] = (
    FreshnessContract(
        name="stg_statsapi_lineups_wide",
        # PROXY: the pivot drops ingestion_ts (see the module docstring). Its co-built sibling is
        # rebuilt from raw in the same --w7b-only invocation, immediately before the pivot.
        ts_table="stg_statsapi_lineups",
        ts_expr="max(try_cast(ingestion_ts as timestamp))",
        # 3 missed 30-minute ticks. Tight enough that INC-41's 6.5h freeze pages on the FIRST
        # off-cycle check after ~90 minutes instead of never; loose enough that one skipped tick
        # (a slow build, a redeploy) is not a page.
        max_lag_minutes=90,
        active_hours_utc=SCHEDULE_CAPTURE_HOURS,
        cadence="every 30 min, 14:00-23:30 + 00:00-03:30 UTC (intraday_schedule_capture)",
        why=(
            "the lineup monitor detects confirmed lineups from this parquet, and the --s3 serving "
            "reads build the pick-detail lineup card from it. Frozen = post_lineup re-scores "
            "silently stop for the rest of the slate (INC-41: 6.5h, ~40 ticks, 3 games unscored "
            "past first pitch, every op reporting SUCCESS)"
        ),
        remediate=(
            "check intraday_schedule_capture is ticking and its --w7b-only leg is running, then "
            "rebuild: run_w1_lakehouse.py --w7b-only"
        ),
    ),
    FreshnessContract(
        name="stg_statsapi_games",
        ts_table="stg_statsapi_games",
        ts_expr="max(try_cast(ingestion_ts as timestamp))",
        max_lag_minutes=90,
        active_hours_utc=SCHEDULE_CAPTURE_HOURS,
        cadence="every 30 min, 14:00-23:30 + 00:00-03:30 UTC (intraday_schedule_capture)",
        why=(
            "served game state (Preview/Live/Final) and the game universe every downstream build "
            "scopes itself to. This is the leg that actually raised in INC-41 (--w3pre-only); "
            "frozen = prod serves day-stale game states"
        ),
        remediate="rebuild: run_w1_lakehouse.py --w3pre-only",
    ),
    FreshnessContract(
        name="stg_statsapi_probable_pitchers",
        ts_table="stg_statsapi_probable_pitchers",
        ts_expr="max(try_cast(ingestion_ts as timestamp))",
        max_lag_minutes=90,
        active_hours_utc=SCHEDULE_CAPTURE_HOURS,
        cadence="every 30 min, 14:00-23:30 + 00:00-03:30 UTC (intraday_schedule_capture)",
        why=(
            "the pregame starter block. On 2026-07-23 this froze at a retired native source and "
            "games whose starters were announced afterwards served both-NULL probables, so the "
            "starter block could not build and those games got NO prediction at all"
        ),
        remediate="rebuild: run_w1_lakehouse.py --w7b-only",
    ),
    FreshnessContract(
        name="feature_pregame_lineup_features",
        ts_table="feature_pregame_lineup_features",
        # A genuine BUILD stamp (not an inherited feed timestamp) — the only feature block that
        # carries one; the other five blocks predict_today gates on have no temporal column at all.
        ts_expr="max(try_cast(computed_at as timestamp))",
        # A once-per-day contract: the intraday rebuild of this block is gated
        # (LINEUP_INTRADAY_S3_REBUILD, default OFF), so the DAILY build (12:00 UTC) is the only
        # cadence that can be asserted without false-paging. 26h admits a late/slow daily run and
        # still catches the multi-day freeze class (the E11.20 spine-freeze shape).
        max_lag_minutes=26 * 60,
        active_hours_utc=ALWAYS,
        cadence="at least once daily (W8a in the 12:00 UTC daily build)",
        why=(
            "the lineup feature block predict_today reads. Frozen = the feature store loses the "
            "current slate and predict silently degrades to intraday_fallback"
        ),
        remediate="check the daily job's W8a step, then rebuild: run_w1_lakehouse.py --w8a-only",
    ),
)


# ── The core: active-minute lag ─────────────────────────────────────────────────────────
# A gap longer than this is reported at the cap rather than accumulated minute by minute. It only
# affects the NUMBER printed for an already-catastrophic freeze, never a verdict.
_MAX_SCAN_DAYS = 45


def active_minutes_between(
    start: datetime, end: datetime, active_hours: tuple[int, ...] | None
) -> float:
    """Minutes in ``[start, end)`` whose UTC hour is in ``active_hours`` (all hours if None).

    PURE. This is the whole off-hours-awareness mechanism — see the module docstring for why a
    raw wall-clock lag is unusable against a writer with a deliberate 10.5-hour overnight gap.
    Returns 0.0 when ``end <= start`` (a content timestamp AHEAD of now is not negative lag; the
    caller treats a materially future timestamp as unevaluable).
    """
    if end <= start:
        return 0.0
    if active_hours is None:
        return (end - start).total_seconds() / 60.0
    if (end - start) > timedelta(days=_MAX_SCAN_DAYS):
        # Cap the scan. Anything this stale is far past every SLA in the registry.
        return float(_MAX_SCAN_DAYS * 24 * 60)

    hours = frozenset(active_hours)
    total = 0.0
    # Walk hour buckets, clamping the first and last to the true bounds.
    cursor = start.replace(minute=0, second=0, microsecond=0)
    while cursor < end:
        nxt = cursor + timedelta(hours=1)
        if cursor.hour in hours:
            lo = max(cursor, start)
            hi = min(nxt, end)
            if hi > lo:
                total += (hi - lo).total_seconds() / 60.0
        cursor = nxt
    return total


# ── Verdicts ────────────────────────────────────────────────────────────────────────────
OK = "OK"
STALE = "STALE"
UNEVALUABLE = "UNEVALUABLE"


@dataclass(frozen=True)
class FreshnessReading:
    """One contract's evaluated state."""

    contract: FreshnessContract
    content_ts: datetime | None
    active_lag_minutes: float | None
    verdict: str
    detail: str = ""

    @property
    def is_problem(self) -> bool:
        return self.verdict in (STALE, UNEVALUABLE)


def evaluate(
    contract: FreshnessContract, content_ts: datetime | None, now: datetime
) -> FreshnessReading:
    """PURE. Map a contract + the content timestamp read for it to a verdict.

    A missing timestamp is UNEVALUABLE, never OK (NF1.7 (a)): the artifact may be absent, empty,
    unreadable, or its timestamp column all-NULL — every one of those is a thing to look at, and
    none of them is evidence of freshness.
    """
    if content_ts is None:
        return FreshnessReading(
            contract, None, None, UNEVALUABLE,
            "no content timestamp could be read (absent / empty / unreadable / all-NULL)",
        )

    if content_ts.tzinfo is None:
        content_ts = content_ts.replace(tzinfo=timezone.utc)
    else:
        content_ts = content_ts.astimezone(timezone.utc)

    # A timestamp materially in the FUTURE is a corrupt clock or a typo'd upstream date (the
    # E9.48-b class, where a keying error dated a row 900 years out and silently DISABLED a
    # max()-based freshness guard by making its lag hugely negative). Refuse to score it healthy.
    if content_ts > now + timedelta(minutes=15):
        return FreshnessReading(
            contract, content_ts, None, UNEVALUABLE,
            f"content timestamp {content_ts:%Y-%m-%d %H:%M}Z is in the FUTURE relative to "
            f"{now:%Y-%m-%d %H:%M}Z — a future-dated max() disables the guard rather than "
            "passing it (E9.48-b)",
        )

    lag = active_minutes_between(content_ts, now, contract.active_hours_utc)
    if lag > contract.max_lag_minutes:
        return FreshnessReading(
            contract, content_ts, lag, STALE,
            f"{lag:.0f} active min since {content_ts:%Y-%m-%d %H:%M}Z "
            f"(SLA {contract.max_lag_minutes})",
        )
    return FreshnessReading(
        contract, content_ts, lag, OK,
        f"{lag:.0f} active min (SLA {contract.max_lag_minutes})",
    )


# ── [METRIC] protocol ───────────────────────────────────────────────────────────────────
# The op parses these rather than re-reading S3, mirroring check_w11_tail_coverage.
_EVALUATED_PREFIX = "[METRIC] artifact_freshness_evaluated="
_NOW_PREFIX = "[METRIC] artifact_freshness_now="
_ARTIFACT_RE = re.compile(
    r"^\[METRIC\]\s+artifact_freshness_(?P<name>[a-z0-9_]+)="
    r"(?P<verdict>OK|STALE|UNEVALUABLE)\s+lag_min=(?P<lag>-?\d+|NA)\s+sla=(?P<sla>\d+)\s*$"
)


def parse_evaluated(stdout: str) -> bool | None:
    """True/False from the last `artifact_freshness_evaluated` line; None when it never appeared.

    None and False are both "unverified" to `classify`, but they differ in cause: False = the
    script ran and its read raised; None = it never got far enough to print, or output was lost.
    """
    value: bool | None = None
    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith(_EVALUATED_PREFIX):
            value = line[len(_EVALUATED_PREFIX):].strip() == "1"
    return value


def parse_now(stdout: str) -> datetime | None:
    """The instant the script says its readings describe, from `artifact_freshness_now=`.

    INC-39: freshness output is the single most replay-sensitive thing a monitor can parse — a
    stale/synthetic/replayed stdout parses byte-identically to a live read, and every number in it
    is individually real. Stamped on EVERY exit path so the op's skew cross-check can never be
    vacuously satisfied by an absent line (NF1.7 (a)).
    """
    value: datetime | None = None
    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith(_NOW_PREFIX):
            raw = line[len(_NOW_PREFIX):].strip()
            try:
                parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                continue
            value = parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return value


def parse_verdicts(stdout: str) -> dict[str, tuple[str, float | None, int]]:
    """Map artifact -> (verdict, active_lag_minutes|None, sla_minutes). Later lines win."""
    out: dict[str, tuple[str, float | None, int]] = {}
    for line in stdout.splitlines():
        m = _ARTIFACT_RE.match(line.strip())
        if m:
            lag_raw = m.group("lag")
            out[m.group("name")] = (
                m.group("verdict"),
                None if lag_raw == "NA" else float(lag_raw),
                int(m.group("sla")),
            )
    return out


# How far the script's stamped `now` may drift from the op's own clock before the whole reading is
# treated as not-about-this-moment. The script runs as a subprocess of the op, so a legitimate
# skew is seconds; 30 minutes is generous and still far tighter than the tightest SLA (90 min).
MAX_CLOCK_SKEW_MINUTES = 30


def classify(
    stdout: str, now: datetime, registry: tuple[FreshnessContract, ...] = REGISTRY
) -> tuple[str | None, str]:
    """PURE. Map the script's stdout to (severity, message). severity None = do not page.

    CRITICAL for a STALE serving-critical artifact; WARN for anything that could not be evaluated
    — including an artifact the script never reported on at all, which is the shape a partial
    crash takes and must not read as healthy.
    """
    evaluated = parse_evaluated(stdout)
    reported_now = parse_now(stdout)
    verdicts = parse_verdicts(stdout)

    # INC-39 — the readings must be ABOUT this moment. Freshness numbers from an earlier run are
    # all individually real and would page (or, worse, reassure) about a moment nobody checked.
    skewed = (
        reported_now is not None
        and abs((now - reported_now).total_seconds()) / 60.0 > MAX_CLOCK_SKEW_MINUTES
    )

    stale: list[str] = []
    unverified: list[str] = []

    for contract in registry:
        if skewed:
            unverified.append(
                f"{contract.name} (output is stamped {reported_now:%Y-%m-%d %H:%M}Z, "
                f"this run is {now:%Y-%m-%d %H:%M}Z)"
            )
            continue
        entry = verdicts.get(contract.name)
        if not evaluated or entry is None:
            unverified.append(f"{contract.name} (no reading)")
            continue
        verdict, lag, sla = entry
        if verdict == STALE:
            proxy = f" [ts via PROXY {contract.ts_table}]" if contract.is_proxied else ""
            lag_txt = "unknown" if lag is None else f"{lag:.0f}"
            stale.append(
                f"{contract.name}: {lag_txt} active min behind (SLA {sla}; {contract.cadence})"
                f"{proxy} — {contract.why}. FIX: {contract.remediate}"
            )
        elif verdict == UNEVALUABLE:
            unverified.append(f"{contract.name} (unevaluable)")

    if not stale and not unverified:
        return None, (
            "Artifact freshness OK — every registered serving-critical parquet has advanced "
            "within its declared SLA (lag counted only across each writer's active hours)."
        )

    parts: list[str] = []
    if stale:
        parts.append("STALE: " + " | ".join(stale))
    if unverified:
        parts.append("UNVERIFIED (not evaluated — NOT verified healthy): " + "; ".join(unverified))

    msg = (
        "SERVING ARTIFACT FRESHNESS (INC-41): " + " || ".join(parts) + ". "
        "A STALE artifact means the build that writes it has stopped advancing it while every "
        "upstream feed and every op may still read green — that is exactly INC-41 (2026-08-06), "
        "where stg_statsapi_lineups_wide froze for 6.5h across ~40 ticks, the lineup monitor "
        "reported 'No newly confirmed lineups' the whole time, and the op returned SUCCESS. Lag "
        "is measured from a CONTENT timestamp inside the parquet (never the S3 mtime, which the "
        "atomic-copy write refreshes even when the data is unchanged) and is accumulated ONLY "
        "across the writer's declared active hours, so an overnight gap is not a breach."
    )
    if stale:
        return "CRITICAL", msg
    return "WARN", msg
