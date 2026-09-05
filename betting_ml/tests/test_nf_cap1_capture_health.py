"""NF-CAP1 — the NFL point-in-time captures must not be able to fail SILENTLY again.

WHAT ACTUALLY WENT WRONG, because the guards below only make sense against it. On 2026-09-01 and
2026-09-04 the `nfl/pit/market` capture fired on its cron and wrote 272 game-line rows each time
and ZERO props rows, because `NFL_PIT_CAPTURE_PROPS` never reached the container that runs the
job. Every signal the run emits was identical to a healthy one: the game-line tier filled `rows`
so the leg's zero-capture escalation was satisfied, the artifact carries no record of the props
decision at all, and the op returned success. Two point-in-time props boards are gone permanently
— the live odds endpoint has no history.

The same investigation found the injuries leg had a matching hole one shape over: a season asset
that 404s is split into "not published yet" (quiet) and "should exist by now" (pages), but an
asset that READS FINE and returns ZERO ROWS took neither branch and came back clean.

So these guards assert three things, and each one is written so that DELETING the thing it names
turns it RED (proved by `nf_cap1_red_proof.py`):
  1. an UNDECLARED props flag pages, while a deliberate "0" stays silent;
  2. a zero-row injury landing past the data-expected bar pages;
  3. the freshness + heartbeat backstops actually cover these artifacts, with the seasonal
     window arithmetic pinned to the CADENCE rather than to a chosen number.

Fast gate: no `pipeline` import (E11.23 — `pipeline/__init__.py` reads the gitignored dbt
manifest and would die at COLLECTION in a fresh worktree), no network, no S3.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from betting_ml.monitoring.artifact_freshness import (
    ALWAYS,
    NFL_PIT_TUE_FRI,
    NFL_PIT_TUE_FRI_SLA_MINUTES,
    NFL_SEASON_MONTHS,
    OK,
    REGISTRY,
    STALE,
    UNEVALUABLE,
    active_minutes_between,
    evaluate,
)
from betting_ml.monitoring.monitor_health import CRITICAL_SCHEDULES
from quant_sports_intel_models.football.nfl.pit.market_capture import (
    PROPS_ENV_FLAG,
    PROPS_OFF,
    PROPS_ON,
    PROPS_UNDECLARED,
    props_state,
    run_market_capture,
)

_REPO = Path(__file__).resolve().parents[2]

UTC = timezone.utc


def _d(*args) -> datetime:
    return datetime(*args, tzinfo=UTC)


def _event(eid: str, commence: str) -> dict:
    return {"id": eid, "commence_time": commence, "home_team": "SEA", "away_team": "NE",
            "bookmakers": [{"key": "bovada", "markets": []}]}


# ── 1. the props flag: three states, and only the bad one pages ─────────────────────────
class TestPropsDeclarationIsThreeStated:
    """UNSET and "0" must not be the same value — that collapse is what made the loss silent."""

    def test_unset_is_undeclared_not_off(self):
        assert props_state({}) == PROPS_UNDECLARED

    def test_empty_string_is_undeclared_too(self):
        # A `.env` line with no value arrives as "" — indistinguishable from unset in effect,
        # and it is the shape a half-finished edit takes.
        assert props_state({PROPS_ENV_FLAG: "   "}) == PROPS_UNDECLARED

    def test_explicit_zero_is_a_real_decision(self):
        assert props_state({PROPS_ENV_FLAG: "0"}) == PROPS_OFF

    def test_only_the_exact_string_one_is_on(self):
        assert props_state({PROPS_ENV_FLAG: "1"}) == PROPS_ON
        for near_miss in ("true", "True", "yes", "01", "1 1", "2"):
            assert props_state({PROPS_ENV_FLAG: near_miss}) == PROPS_OFF, near_miss


class TestAPropsLossCannotBeSilent:
    """The live defect, reproduced: game lines land, props do not, and the run must NOT pass."""

    def _run(self, monkeypatch, tmp_path, flag, *, props_events=()):
        if flag is None:
            monkeypatch.delenv(PROPS_ENV_FLAG, raising=False)
        else:
            monkeypatch.setenv(PROPS_ENV_FLAG, flag)
        return run_market_capture(
            2026,
            now=_d(2026, 9, 8, 16, 15),
            local_root=str(tmp_path),
            fetch_game_lines=lambda: [_event("e1", "2026-09-10T00:20:00Z")],
            fetch_props=lambda: list(props_events),
        )

    def test_the_september_defect_reproduces_and_now_escalates(self, monkeypatch, tmp_path):
        """272 game lines + 0 props + no flag = the 09-01/09-04 runs. Must escalate."""
        m = self._run(monkeypatch, tmp_path, None)
        assert m["game_line_events"] == 1, "the game-line tier still captured"
        assert m["prop_events"] == 0
        assert m["props_state"] == PROPS_UNDECLARED
        assert m["escalate"] is True, (
            "an UNDECLARED props flag must page: this exact manifest shape was returned on "
            "2026-09-01 and 2026-09-04 and reported success"
        )

    def test_a_deliberate_zero_is_silent(self, monkeypatch, tmp_path):
        """Props are a real spend decision; a monitor that pages on a legitimate choice is muted."""
        m = self._run(monkeypatch, tmp_path, "0")
        assert m["props_state"] == PROPS_OFF
        assert m["escalate"] is False

    def test_props_enabled_but_zero_events_escalates(self, monkeypatch, tmp_path):
        """The other way props vanish: the flag IS set and the fetch yields nothing."""
        m = self._run(monkeypatch, tmp_path, "1")
        assert m["props_state"] == PROPS_ON
        assert m["prop_events"] == 0
        assert m["escalate"] is True

    def test_props_enabled_and_captured_is_healthy(self, monkeypatch, tmp_path):
        """The two-sided control: the healthy state must NOT page, or the guard is vacuous."""
        m = self._run(monkeypatch, tmp_path, "1",
                      props_events=[_event("e1", "2026-09-10T00:20:00Z")])
        assert m["prop_events"] == 1
        assert m["escalate"] is False, "a healthy props capture must not page"


# ── 2. a zero-row injury landing is loud past the bar ───────────────────────────────────
class TestAZeroRowInjuryLandingIsLoud:
    """NF-W2c: a reader that returns 0 rows and says nothing is the silent-death signature."""

    def _run(self, *, rows, now, bar, tmp_path):
        from quant_sports_intel_models.football.nfl.pit.injury_capture import run_injury_capture

        return run_injury_capture(2026, rows=rows, vendor_asof_present=False, now=now,
                                  local_root=str(tmp_path), expected_from=bar)

    def test_zero_rows_past_the_bar_escalates(self, tmp_path):
        m = self._run(rows=[], now=_d(2026, 10, 6, 16, 0),
                      bar=_d(2026, 9, 17), tmp_path=tmp_path)
        assert m["rows_read"] == 0
        assert m["escalate"] is True, (
            "a published-but-empty season asset past the data-expected bar must page — it took "
            "neither the 404 branch nor the captured-rows branch and came back clean"
        )
        assert m["expected_absent"] is False

    def test_zero_rows_before_the_bar_is_recorded_not_paged(self, tmp_path):
        """The two-sided control: before the bar, an empty asset is expected, exactly like a 404."""
        m = self._run(rows=[], now=_d(2026, 9, 5, 16, 0),
                      bar=_d(2026, 9, 17), tmp_path=tmp_path)
        assert m["escalate"] is False
        assert m["expected_absent"] is True, "recorded, so the absence is never merely invisible"

    def test_real_rows_still_capture(self, tmp_path):
        """Baseline-pass: the guard must not fire on the healthy path."""
        rows = [{"gsis_id": f"00-{i:05d}", "full_name": f"P{i}", "week": 1, "team": "SEA",
                 "position": "WR", "report_status": "Questionable", "practice_status": "LP"}
                for i in range(5)]
        m = self._run(rows=rows, now=_d(2026, 10, 6, 16, 0),
                      bar=_d(2026, 9, 17), tmp_path=tmp_path)
        assert (m["rows_read"], m["captured"], m["written"]) == (5, 5, 5)
        assert m["escalate"] is False


# ── 3. the backstops ────────────────────────────────────────────────────────────────────
class TestTheSeasonalCadenceWindowIsCorrect:
    """The SLA is DERIVED from the cron, so the arithmetic it rests on is pinned here."""

    def test_one_cadence_interval_is_exactly_24_active_hours(self):
        tue, fri = _d(2026, 9, 1, 16, 15), _d(2026, 9, 4, 16, 15)
        nxt = _d(2026, 9, 8, 16, 15)
        for a, b in ((tue, fri), (fri, nxt)):
            got = active_minutes_between(a, b, ALWAYS, NFL_PIT_TUE_FRI, NFL_SEASON_MONTHS)
            assert got == 24 * 60, f"{a}->{b} gave {got}"

    def test_the_sla_sits_between_healthy_and_one_missed_fire(self):
        tue, nxt = _d(2026, 9, 1, 16, 15), _d(2026, 9, 8, 16, 15)
        missed = active_minutes_between(tue, nxt, ALWAYS, NFL_PIT_TUE_FRI, NFL_SEASON_MONTHS)
        assert missed == 48 * 60
        assert 24 * 60 < NFL_PIT_TUE_FRI_SLA_MINUTES < missed, (
            "the SLA must page on one missed fire and tolerate a healthy interval"
        )

    def test_the_window_is_dst_invariant(self):
        """09:00 PT is 16:00 UTC in PDT and 17:00 in PST, and a season spans the switch. The
        contract carries NO hour filter precisely so that cannot shift it."""
        jan = active_minutes_between(_d(2027, 1, 5, 17, 15), _d(2027, 1, 8, 17, 15),
                                     ALWAYS, NFL_PIT_TUE_FRI, NFL_SEASON_MONTHS)
        assert jan == 24 * 60

    def test_the_off_season_contributes_nothing(self):
        """Frozen in August, read in August: zero active minutes, because the cron cannot fire."""
        got = active_minutes_between(_d(2026, 7, 1), _d(2026, 8, 20),
                                     ALWAYS, NFL_PIT_TUE_FRI, NFL_SEASON_MONTHS)
        assert got == 0.0

    def test_a_long_seasonal_gap_is_scanned_not_capped(self):
        """The cap used to return a flat days*24*60 regardless of which minutes were active, so a
        seasonal contract frozen 46 days earlier read as catastrophically stale when its true
        active lag was zero. Scanning day-buckets makes it exact."""
        got = active_minutes_between(_d(2026, 8, 5), _d(2026, 9, 20),
                                     ALWAYS, NFL_PIT_TUE_FRI, (10, 11, 12, 1, 2))
        assert got == 0.0, "September is not in this contract's active months"

    def test_the_existing_mlb_hour_only_contracts_are_unchanged(self):
        """The measured example from the module docstring: froze 03:30, read 05:00 => 30 min."""
        from betting_ml.monitoring.artifact_freshness import SCHEDULE_CAPTURE_HOURS

        assert active_minutes_between(_d(2026, 8, 7, 3, 30), _d(2026, 8, 7, 5, 0),
                                      SCHEDULE_CAPTURE_HOURS) == 30.0


class TestBothCaptureArtifactsAreRegistered:
    def test_both_are_present_and_read_from_the_pit_store(self):
        by_name = {c.name: c for c in REGISTRY}
        for name, source in (("nfl_pit_market", "market"), ("nfl_pit_injuries", "injuries")):
            c = by_name[name]
            assert c.pit_source == source
            assert not c.is_proxied, "these read their own capture_timestamp, never a proxy"
            assert "capture_timestamp" in c.ts_expr

    def test_a_frozen_capture_pages_and_a_healthy_one_does_not(self):
        """RED both ways at the verdict level, on the artifact this story exists for."""
        c = {x.name: x for x in REGISTRY}["nfl_pit_market"]
        now = _d(2026, 10, 6, 20, 0)                      # a Tuesday, in season
        healthy = evaluate(c, now - timedelta(hours=4), now)
        assert healthy.verdict == OK, healthy.detail
        frozen = evaluate(c, _d(2026, 9, 22, 16, 15), now)   # two weeks of missed fires
        assert frozen.verdict == STALE, frozen.detail

    def test_an_absent_capture_table_is_unevaluable_never_healthy(self):
        """NF1.7 (a): a capture that has never happened must not read as fresh."""
        c = {x.name: x for x in REGISTRY}["nfl_pit_injuries"]
        assert evaluate(c, None, _d(2026, 11, 3, 20, 0)).verdict == UNEVALUABLE


class TestTheScheduleCannotDriftStoppedUnnoticed:
    def test_the_two_free_self_starting_captures_are_heartbeat_checked(self):
        for name in ("sports_nfl_pit_weather_schedule", "sports_nfl_pit_metadata_schedule"):
            assert name in CRITICAL_SCHEDULES, (
                f"{name} can drift STOPPED with nothing paging — and a missed capture cannot be "
                "backfilled"
            )

    def test_the_paid_schedule_is_covered_by_the_artifact_not_the_heartbeat(self):
        """⛔ The PAID market schedule must NOT be in CRITICAL_SCHEDULES, and this is a
        correctness assertion rather than a scoping one.

        `stopped_critical_instigators` flags an instigator only when Dagster holds a PERSISTED
        STOPPED ROW for it. That schedule ships `default_status=STOPPED` and is RUNNING only
        because the operator toggled it on — so the very failure a heartbeat entry would claim to
        cover (a volume reset wiping the toggle) returns it to its STOPPED DEFAULT with NO row,
        which that function correctly does not flag. The entry would be a guard that cannot see
        the failure it names (NF1.7 (a)). Coverage comes from the artifact contract instead.
        """
        assert "sports_nfl_pit_market_schedule" not in CRITICAL_SCHEDULES
        assert any(c.name == "nfl_pit_market" for c in REGISTRY), (
            "the market schedule has neither heartbeat nor artifact coverage — one of them must "
            "exist or a stopped PAID capture is silent again"
        )

    def test_the_paid_schedule_still_ships_stopped(self):
        """A fresh deployment must not auto-start a PAID capture — a PM spend decision."""
        src = (_REPO / "pipeline/schedules/sports_nfl_pit_capture_schedules.py").read_text()
        market = src.split("def sports_nfl_pit_market_schedule")[0].rsplit("@schedule(", 1)[1]
        assert "DefaultScheduleStatus.STOPPED" in market


class TestThePropsFlagHasAllFourOwners:
    """One logical thing, four owners (INC-30/36/38). The absent ones are why the flip was a
    no-op; the box's live .env is the fourth and is verified by the operator, not from here."""

    def test_env_required_lists_it(self):
        text = (_REPO / "services/dagster/aws/env.required").read_text()
        lines = [ln.strip() for ln in text.splitlines()
                 if ln.strip() and not ln.strip().startswith("#")]
        assert PROPS_ENV_FLAG in lines, (
            "an absent key makes 'flip it to 1' a silent no-op — env.required's own documented "
            "bite, and exactly what happened here"
        )

    def test_the_box_env_example_carries_it(self):
        text = (_REPO / "services/dagster/aws/.env.example").read_text()
        assert re.search(rf"^{PROPS_ENV_FLAG}=", text, re.M), (
            "the operator provisions the box .env from this file"
        )

    def test_box_operations_records_the_measured_credit_cost(self):
        """§10 carried a 10x-overstated cost. Pinned BOTH WAYS — a presence-only assertion is
        blind to a partial revert that leaves the retired claim standing beside the new one."""
        text = (_REPO / "services/dagster/aws/BOX_OPERATIONS.md").read_text().lower()
        assert "3 credits/snapshot" in text, "the MEASURED game-line cost"
        assert "10 credits/event" in text, "the MEASURED per-event props cost"
        # The retired CLAIM forms, which were 10x/12x high. Matched in their exact claim shape so
        # the explanatory prose that CITES them ("was ~30", "the old ~75,000 figure") cannot
        # satisfy or violate this (INC-38: prose must not be able to answer a guard).
        for retired in ("~30 credits/snapshot", "~120 credits per event"):
            assert retired not in text, f"the retired 10x figure {retired!r} is still stated"
