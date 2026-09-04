"""MLB-INC-0904 (2026-09-04) — the W3pre tier outgrew its intraday leg cap, and the ONE table
with an intraday consumer was built LAST, so it was the one that died.

MEASURED (quiet overnight tick 03:30Z, reconstructed from S3 write timestamps):

    stg_oddsapi_odds      ~140 s   no intraday consumer
    stg_oddsapi_events       8 s   no intraday consumer
    stg_derivative_odds    299 s   no intraday consumer (daily CLV)
    stg_statsapi_games      12 s   ⚠ the ONLY intraday consumer — 90-min freshness SLA
                          ------
                          ~459 s against a 480 s cap  ⇒ 21 s of margin on a QUIET tick

Two guards, because the incident had two independent halves:

  1. ORDER — the 12-second serving-critical table must be built FIRST. Its position is the whole
     difference between "a timeout truncates staging nobody reads intraday" and "a timeout
     freezes served game state".
  2. THRESHOLD — the per-model seconds were ALWAYS printed; nothing compared them to the budget
     they had to fit in. A season of monotonic growth crossed 480 s unannounced (the E11.30
     shape: detection existed, notification did not).

Fast-gate safe: `scripts.run_w1_lakehouse` imports cleanly and the tick-budget policy is pure
stdlib; the wiring is checked by source inspection (importing `pipeline` would crash collection —
the E11.23 rule).
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from betting_ml.monitoring.intraday_tick_budget import (
    LEG_TIMEOUT_SECONDS,
    W3PRE_TIER_WARN_FRACTION,
    w3pre_tier_verdict,
)

ROOT = Path(__file__).resolve().parents[2]
RUN_W1 = ROOT / "scripts" / "run_w1_lakehouse.py"

#: The tick that actually died, as measured. Used as a fixture rather than a round number so the
#: guard is anchored on the incident instead of on a threshold someone liked the look of.
MEASURED_TIER = {
    "stg_statsapi_games": 12.0,
    "stg_oddsapi_odds": 140.0,
    "stg_oddsapi_events": 8.0,
    "stg_derivative_odds": 299.0,
}

#: The serving-critical member: the only W3pre table with an intraday consumer (a 90-minute
#: freshness SLA in betting_ml/monitoring/artifact_freshness.py).
SERVING_CRITICAL = "stg_statsapi_games"


def _source_without_comments(path: Path) -> str:
    """Source with `#` comment bodies stripped.

    INC-38: a source-inspection guard that a COMMENT can satisfy is vacuous — and this change
    ships a long explanatory comment block naming the very symbols under test, so an unstripped
    scan here would pass with the code deleted.
    """
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        # Crude but sufficient: these files have no `#` inside string literals on the lines the
        # assertions below care about, and stripping too much can only make a guard STRICTER.
        out.append(line.split("#", 1)[0])
    return "\n".join(out)


# ── 1. ORDER: the serving-critical table is built first ────────────────────────────────
def test_serving_critical_table_is_built_first():
    from scripts.run_w1_lakehouse import W3PRE_STG_MODELS

    assert W3PRE_STG_MODELS[0] == SERVING_CRITICAL, (
        f"{SERVING_CRITICAL} must be the FIRST W3pre model. It costs ~12 s, it is the only one "
        f"with an intraday consumer, and it carries a 90-minute freshness SLA. Built later it "
        f"queues behind ~447 s of daily-cadence odds staging and is the table a leg timeout "
        f"kills — which is MLB-INC-0904. Got order: {list(W3PRE_STG_MODELS)}"
    )


def test_the_reorder_did_not_quietly_drop_a_model():
    """The cheap way to 'fix' a timeout is to delete a table. That must not pass as a reorder."""
    from scripts.run_w1_lakehouse import W3PRE_STG_MODELS

    assert set(W3PRE_STG_MODELS) == {
        "stg_statsapi_games",
        "stg_oddsapi_odds",
        "stg_oddsapi_events",
        "stg_derivative_odds",
    }, f"the W3pre tier's MEMBERSHIP changed, not just its order: {list(W3PRE_STG_MODELS)}"
    assert len(W3PRE_STG_MODELS) == len(set(W3PRE_STG_MODELS)), "duplicate model in the tier"


# ── 2. THRESHOLD: an over-budget tier must SURFACE ─────────────────────────────────────
def test_an_over_budget_tier_surfaces_and_names_its_worst_model():
    """The spec's requirement: a build exceeding its per-table budget must surface."""
    over = dict(MEASURED_TIER, stg_derivative_odds=600.0)  # past the 480 s cap
    v = w3pre_tier_verdict(over)

    assert v.verdict == "OVER", f"a tier over the leg cap must grade OVER, got {v.verdict}"
    assert v.fraction >= 1.0
    assert v.worst_model == "stg_derivative_odds"
    # An alert that does not name the biggest contributor sends the reader hunting.
    assert "stg_derivative_odds" in v.message


def test_a_healthy_tier_passes():
    """Baseline-pass control: the guard must not fire on a tier that comfortably fits."""
    v = w3pre_tier_verdict({"stg_statsapi_games": 12.0, "stg_oddsapi_odds": 40.0})
    assert v.verdict == "OK", f"a 52 s tier against a {LEG_TIMEOUT_SECONDS} s cap must be OK"


def test_the_measured_incident_tier_would_have_warned_before_the_kill():
    """The 'what would have caught it earlier' assertion, on the REAL numbers.

    The tier that survived by 21 s already sits at ~96% of the cap. The warning must fire THERE —
    while there is still headroom to act — not only once the tick is being killed.
    """
    v = w3pre_tier_verdict(MEASURED_TIER)
    assert v.verdict == "WARN", (
        f"the measured 459 s tier must WARN (it is {v.fraction:.0%} of the cap), got {v.verdict}"
    )
    assert v.worst_model == "stg_derivative_odds"


def test_an_unmeasured_tier_is_not_scored_healthy():
    """NF1.7 (a): a check that did not run is not a pass."""
    for empty in ({}, None):
        v = w3pre_tier_verdict(empty)
        assert v.verdict == "UNEVALUATED", f"empty timings must not be OK, got {v.verdict}"
        assert v.verdict != "OK"


def test_the_warn_threshold_leaves_real_headroom():
    """A threshold set just under the number that broke would fire only on the way past."""
    assert 0.0 < W3PRE_TIER_WARN_FRACTION < 1.0
    headroom = (1.0 - W3PRE_TIER_WARN_FRACTION) * LEG_TIMEOUT_SECONDS
    assert headroom >= 120, (
        f"the WARN threshold leaves only {headroom:.0f}s of headroom; at the growth measured in "
        f"this incident (211.4s -> 299.0s on one model) that is not enough lead time to act"
    )


# ── 3. WIRED *AND* INVOKED ─────────────────────────────────────────────────────────────
def test_build_w3pre_actually_invokes_the_verdict():
    """NF-C0e: a field is applied when something CALLS it, not when its name appears.

    Matches the CALL form on comment-stripped source (the DSR-CONV #690 lesson: a bare name grep
    is satisfied by an import line or a dict key).
    """
    src = _source_without_comments(RUN_W1)
    calls = len(re.findall(r"\bw3pre_tier_verdict\s*\(", src))
    assert calls >= 1, (
        "run_w1_lakehouse imports the tier-budget policy but never CALLS it — the budget check "
        "would be dead code and the tier could grow past its cap unannounced again"
    )


def test_build_w3pre_records_a_timing_for_every_model_it_builds():
    """Without a populated timings map the verdict is vacuously UNEVALUATED forever."""
    src = _source_without_comments(RUN_W1)
    body = src.split("def _build_w3pre(")[1].split("\ndef ")[0]
    assert "timings[model]" in body, "_build_w3pre must record a per-model build time"
    assert "time.monotonic()" in body, "_build_w3pre must measure elapsed time per model"
    assert "[METRIC] w3pre_tier_seconds=" in body, "the tier total must be machine-readable"


# ── 4. THE INC-41 FRESHNESS SEMANTICS ARE UNCHANGED ────────────────────────────────────
# The spec's hard line: this incident must not weaken the content-timestamp / active-hours
# semantics. These two are the ones that would have to break for the alert to go quiet for the
# WRONG reason.
def test_a_frozen_artifact_still_fires():
    from betting_ml.monitoring.artifact_freshness import REGISTRY, STALE, evaluate

    contract = next(c for c in REGISTRY if c.name == "stg_ref_players")
    now = datetime(2026, 9, 4, 4, 19, tzinfo=timezone.utc)
    # The exact reading that paged: content ts 2026-09-02 13:13Z.
    frozen = now - timedelta(minutes=2347)

    reading = evaluate(contract, frozen, now=now)
    assert reading.verdict == STALE, (
        "a frozen artifact must still be STALE — weakening this is how the E5.10 silent rot "
        "became invisible in the first place"
    )
    assert reading.active_lag_minutes is not None and reading.active_lag_minutes > contract.max_lag_minutes


def test_lag_is_counted_from_the_content_timestamp_not_a_write_time():
    """INC-41's core: an atomic server-side copy refreshes S3 mtime even on unchanged data, so a
    freshness verdict keyed on mtime reads GREEN through a freeze. The reading must move with the
    CONTENT timestamp and nothing else."""
    from betting_ml.monitoring.artifact_freshness import REGISTRY, OK, STALE, evaluate

    contract = next(c for c in REGISTRY if c.name == "stg_ref_players")
    now = datetime(2026, 9, 4, 4, 19, tzinfo=timezone.utc)

    fresh = evaluate(contract, now - timedelta(minutes=1), now=now)
    stale = evaluate(contract, now - timedelta(minutes=contract.max_lag_minutes + 60), now=now)
    assert fresh.verdict == OK and stale.verdict == STALE
    assert stale.active_lag_minutes > fresh.active_lag_minutes


# ── 5. THE MIRRORED LIST (one logical thing, two owners) ───────────────────────────────
# scripts/ddl/generate_w3pre_external_tables.py keeps its own copy of the tier. MLB-INC-0904 made
# the build list's ORDER load-bearing while the DDL generator's order stays cosmetic, so the two
# are deliberately allowed to differ in order — but their MEMBERSHIP must not drift (a flattened
# parquet with no external table over it, or an external table over a parquet nothing builds, are
# both real defects). Parsed from source rather than imported: the generator is a DDL script and
# importing it is not fast-gate business.
def test_the_ddl_generators_mirrored_tier_has_not_drifted_in_membership():
    import ast

    from scripts.run_w1_lakehouse import W3PRE_STG_MODELS

    ddl = ROOT / "scripts" / "ddl" / "generate_w3pre_external_tables.py"
    tree = ast.parse(ddl.read_text(encoding="utf-8"))
    mirrored = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "W3PRE_STG_MODELS" for t in node.targets
        ):
            mirrored = [ast.literal_eval(e) for e in node.value.elts]
            break

    assert mirrored is not None, "W3PRE_STG_MODELS not found in the DDL generator"
    assert set(mirrored) == set(W3PRE_STG_MODELS), (
        "the DDL generator's mirrored W3pre tier has drifted in MEMBERSHIP from the build list: "
        f"generator={sorted(mirrored)} build={sorted(W3PRE_STG_MODELS)}. Every flattened model "
        "needs an external table over it and vice versa."
    )
