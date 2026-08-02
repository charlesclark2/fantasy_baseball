"""w11_tail_coverage.py — the paging policy for the W11 serving tail (INC-37, 2026-08-01).

WHY THIS EXISTS
    `scripts/check_w11_tail_coverage.py` is the TODAY-guard for the three feature blocks the
    six-block feature-store coverage gate structurally cannot see (umpire / weather /
    public_betting — the W11 serving tail). It was written during INC-37 as a MANUAL
    post-rebuild step, so the blind spot stayed open in prod: nothing ran it daily and nothing
    paged on it. `check_w11_tail_coverage_op` now runs it in the daily job and calls
    `send_alert` on the verdict the script already computes — the E11.30 rule that an
    ALERT-tier op must actually page, keyed on the signal its script already emits.

    Lives in betting_ml/ (not pipeline/) so the fast gate can import it: `pipeline/__init__.py`
    reads the dbt manifest, absent in CI, so a fast-gate test that imports `pipeline` crashes at
    COLLECTION rather than skipping (E11.23). Same shape as `spine_horizon.py`.

⭐ WHICH SLATE EACH BLOCK IS JUDGED ON — the thing that makes this pageable at all.

    The script's BUILD_GAP verdict (raw feed HAS the slate, the built feature table does not) is
    the INC-37 fingerprint. But "the built table has not caught up with the feed" is only a
    DEFECT for a block whose feed lands BEFORE the build that consumes it. In the daily job the
    W11 tail is built by `lakehouse_w11_nightly_op` (s5c), and two of the three feeds land
    AFTER it. Measured on the live lakehouse, 2026-08-01 (UTC):

      block           feed lands                                          W11 build   ⇒ same-day?
      --------------  --------------------------------------------------  ----------  -----------
      public_betting  12:00  ingest_action_network (s4)                    ~12:40 s5c  YES
      weather         12:50  ingest_weather (s7) writes forecast_pregame   ~12:40 s5c  NO (+1 cycle)
      umpire          12:0x/16:39  ingest_umpires.py --date today (s8/s17) ~12:40 s5c  NO (+1 cycle)

    (`stg_weather_raw_snapshots` filters `weather_observation_type='forecast_pregame'` by design,
    so the 00:00–02:00 UTC `forecast_intraday` rows do NOT make the weather block same-day
    capable — they are rejected by the model that feeds it.)

    So a monitor that paged on the CURRENT slate for umpire and weather would fire BUILD_GAP
    every single morning on the normal build cadence — the alert-fatigue failure mode this
    check's own two-sided design exists to avoid (E11.27; the injury feed-freshness carve-out).
    Instead each block is judged on the newest slate its build could actually have covered:

      - `public_betting` → TODAY. Its feed precedes its build in the same run, so a zero here IS
        a stale-game-universe defect. This is the same-day INC-37 detector: on 2026-08-01
        `public_betting_raw` held 240 rows for the slate from 12:00 while the built table held 0.
      - `umpire`, `weather` → the PRIOR slate, where exactly one build cycle has elapsed. This is
        the precedent `check_feature_block_coverage._DATE_OUTAGE_SKIP_NEWEST` already set for the
        same reason ("the newest played date legitimately lags one build cycle — exempt it"), and
        it costs a genuine outage one day of latency, which those outages always survive.

    Their current-slate verdicts are still printed in the step log — informative, never paged.

SEVERITY. BUILD_GAP → CRITICAL (a real serving defect: a front-end panel is blank and the
    aggregator's block is null). PARTIAL → WARN (degraded, worth a look). FEED_PENDING / OK /
    NO_SLATE → SILENT. A leg that could not be evaluated is WARN, never healthy — an anchor that
    fails to evaluate makes its assertion vacuously true (NF1.7 (a) / spine_horizon).
"""

from __future__ import annotations

import re

# The block whose raw feed lands BEFORE the W11 tail build in the same daily run, so its
# current-slate coverage is a valid same-day assertion.
SAME_DAY_BLOCKS = ("public_betting",)

# The blocks whose raw feed lands AFTER the W11 tail build, so the CURRENT slate is expected to
# be empty at check time and only the PRIOR slate is a valid assertion.
BUILD_LAGGED_BLOCKS = ("umpire", "weather")

ALL_BLOCKS = tuple(sorted(SAME_DAY_BLOCKS + BUILD_LAGGED_BLOCKS))

# verdict -> severity. Anything absent from this map is silent by design.
_PAGEABLE = {"BUILD_GAP": "CRITICAL", "PARTIAL": "WARN"}

_EVALUATED_PREFIX = "[METRIC] w11_tail_evaluated="
_DATE_PREFIX = "[METRIC] w11_tail_date="
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_BLOCK_RE = re.compile(
    r"^\[METRIC\]\s+w11_tail_(?P<block>[a-z_]+)_covered=(?P<n>\d+)/(?P<m>\d+)\s+"
    r"verdict=(?P<verdict>[A-Z_]+)\s*$"
)


def parse_evaluated(stdout: str) -> bool | None:
    """True/False from the LAST `w11_tail_evaluated` line; None when the line never appeared.

    None and False are treated identically by `classify` (both mean "unverified"), but they are
    distinguished here because they have different causes: False = the script ran and its read
    raised; None = the script never got far enough to print, or its output was lost.
    """
    value: bool | None = None
    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith(_EVALUATED_PREFIX):
            value = line[len(_EVALUATED_PREFIX):].strip() == "1"
    return value


def parse_date(stdout: str) -> str | None:
    """The slate the script says this output describes, from its `[METRIC] w11_tail_date=` line.

    None when the line never appeared — which means the output did NOT come from the current
    script (it stamps the date on every exit path). `classify` deliberately treats None as
    "cannot cross-check" rather than as a mismatch, so this can only ever ADD a refusal on
    positive evidence of a wrong slate, never manufacture one from a missing line.
    """
    value: str | None = None
    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith(_DATE_PREFIX):
            value = line[len(_DATE_PREFIX):].strip() or None
    return value


def parse_block_verdicts(stdout: str) -> dict[str, str]:
    """Map block -> verdict from the script's per-block `[METRIC] w11_tail_<block>_covered=` lines.

    Later lines win, so re-running the script inside one op invocation reports the final state.
    """
    out: dict[str, str] = {}
    for line in stdout.splitlines():
        m = _BLOCK_RE.match(line.strip())
        if m:
            out[m.group("block")] = m.group("verdict")
    return out


def parse_block_coverage(stdout: str) -> dict[str, tuple[int, int]]:
    """Map block -> (feature_games, slate_games) — the numbers for the page body / metadata."""
    out: dict[str, tuple[int, int]] = {}
    for line in stdout.splitlines():
        m = _BLOCK_RE.match(line.strip())
        if m:
            out[m.group("block")] = (int(m.group("n")), int(m.group("m")))
    return out


def classify(
    today_stdout: str,
    prior_stdout: str,
    *,
    today_date: str = "today",
    prior_date: str = "the prior slate",
) -> tuple[str | None, str]:
    """PURE. Map the two script runs to (severity, message). severity None = do not page.

    `today_stdout` is the run over the current slate (judges SAME_DAY_BLOCKS); `prior_stdout` is
    the run over the previous day (judges BUILD_LAGGED_BLOCKS). Each block is read from exactly
    one of them — see the module docstring for why.
    """
    legs = (
        (SAME_DAY_BLOCKS, today_stdout, today_date),
        (BUILD_LAGGED_BLOCKS, prior_stdout, prior_date),
    )

    critical: list[str] = []
    warn: list[str] = []
    unverified: list[str] = []

    for blocks, stdout, day in legs:
        evaluated = parse_evaluated(stdout)
        verdicts = parse_block_verdicts(stdout)
        coverage = parse_block_coverage(stdout)
        # INC-39 — the leg must be ABOUT the slate we asked for. The per-block metric lines carry
        # no date of their own, so replayed / stale / synthetic output parses exactly like a live
        # read and would page CRITICAL on a slate nobody checked. A reported date that disagrees
        # with the requested one demotes the whole leg to UNVERIFIED (WARN, never CRITICAL and
        # never healthy) — the numbers may be perfectly real, they are just not this slate's.
        # Only cross-checkable when the caller asked for a real date: `today_date`/`prior_date`
        # default to human labels ("today"), which carry no slate to compare against.
        reported = parse_date(stdout)
        wrong_slate = (
            reported is not None and _ISO_DATE_RE.match(day) is not None and reported != day
        )
        for block in blocks:
            verdict = verdicts.get(block)
            if wrong_slate:
                unverified.append(f"{block} (asked for {day}, output is for {reported})")
                continue
            if not evaluated or verdict is None:
                unverified.append(f"{block} ({day})")
                continue
            severity = _PAGEABLE.get(verdict)
            if severity is None:
                continue
            n, m = coverage.get(block, (0, 0))
            detail = f"{block} {verdict} {n}/{m} slate games on {day}"
            (critical if severity == "CRITICAL" else warn).append(detail)

    if not critical and not warn and not unverified:
        return None, (
            "W11 serving tail OK — every block covers the newest slate its build could have "
            "reached (pending feeds are informational, not defects)."
        )

    parts: list[str] = []
    if critical:
        parts.append("BUILD GAP: " + "; ".join(critical))
    if warn:
        parts.append("PARTIAL: " + "; ".join(warn))
    if unverified:
        parts.append("UNVERIFIED (the check could not be evaluated): " + "; ".join(unverified))

    msg = (
        "W11 SERVING TAIL (INC-37): " + " | ".join(parts) + ". "
        "These are the blocks the six-block feature-store coverage gate structurally CANNOT see "
        "(it excludes the anchor date, so it is a store-HISTORY guard, never a TODAY guard) — a "
        "zero here means a blank front-end transparency panel and a null block in the served "
        "aggregate while every other monitor reads green. A BUILD GAP means the raw feed HAS the "
        "slate and the built table does not, i.e. the W11 tail was built on a stale game "
        "universe (on the 1st of a month, suspect the INC-37 month-boundary schedule hole). "
        "Remediate: confirm the schedule reaches the slate (ingest_statsapi.py schedule "
        "--lookahead-days 3), then rebuild the affected tier "
        "(run_w1_lakehouse.py --w11b-only / --w11c-only / --w11d-only + "
        "refresh_w1_external_tables.py --w11b/--w11c/--w11d) and re-verify with "
        "scripts/check_w11_tail_coverage.py --strict."
    )
    if critical:
        return "CRITICAL", msg
    return "WARN", msg
