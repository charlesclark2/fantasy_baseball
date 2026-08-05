"""NF-W0a — the doc §13 leakage guard, with every rejection case DELIBERATELY CONSTRUCTED.

The story's AC is not "there is a guard" — it is "unit and integration tests deliberately
construct leakage cases and REQUIRE rejection", RED-proven. Two things are proven here:

  1. EVERY §13 rejection case is constructed and rejected (`TestEachLeakageCaseIsRejected`).
  2. ⭐ EACH FIXTURE IS ISOLATING — it trips exactly ONE clause and satisfies all the others
     (`TestTheGuardIsNotVacuous`). This is the NF-D17 lesson made mechanical: a guard over an
     `and`-composed rule stays GREEN when you delete the clause it names, if a DIFFERENT clause
     is already rejecting the fixture. So for each case we DISABLE the owning clause and require
     the record to become CLEAN — if it stays rejected, the fixture was proving something else
     and the test would be measuring nothing. That is a RED-proof of the clause, run every time
     the suite runs rather than performed once by hand.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from quant_sports_intel_models.football.nfl.pit import leakage_guard as lg
from quant_sports_intel_models.football.nfl.pit.leakage_guard import (
    LeakageRejection,
    Rejection,
    assert_point_in_time,
    evaluate_point_in_time,
)

# A Tuesday projection for a Sunday game — the canonical NFL early-build shape.
PROJECTION = datetime(2026, 9, 15, 15, 0, tzinfo=timezone.utc)   # Tue
KICKOFF = datetime(2026, 9, 20, 17, 0, tzinfo=timezone.utc)      # Sun
BEFORE = PROJECTION - timedelta(hours=2)
AFTER = PROJECTION + timedelta(hours=2)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def clean_record(**overrides) -> dict:
    """A record that passes EVERY clause. Every fixture below is this, with ONE field flipped."""
    base = {
        "capture_source": "weather",
        "capture_id": "cid-0001",
        "subject_key": "2026_02_GB_CHI|forecast_intraday|T-120h",
        "payload_sha256": "sha-original",
        "hash_excluded_keys": "",
        "record_tier": "weather",
        "feature_timestamp": _iso(BEFORE),
        "source_timestamp": _iso(BEFORE),
        "capture_timestamp": _iso(BEFORE),
        "vendor_release_timestamp": _iso(BEFORE),
        "ingestion_timestamp": _iso(BEFORE),
    }
    base.update(overrides)
    return base


def clean_store_index(record: dict | None = None) -> dict:
    """A store index holding the record's OWN original capture — no revision."""
    record = record or clean_record()
    return {
        record["subject_key"]: [
            {"capture_timestamp": record["capture_timestamp"],
             "payload_sha256": record["payload_sha256"]}
        ]
    }


# ── the fixture set: (name, reason, record, store_index, owning clause function) ─────────
def _market_record(**over) -> dict:
    r = clean_record(record_tier="market", kickoff_timestamp=_iso(KICKOFF),
                     market_phase="open", subject_key="game_lines|evt-1")
    r.update(over)
    return r


def _window_record(**over) -> dict:
    r = clean_record(
        is_rolling_window=True,
        window_end_timestamp=_iso(KICKOFF - timedelta(days=7)),
        target_game_timestamp=_iso(KICKOFF),
        window_game_ids=["2026_01_GB_CHI"],
        target_game_id="2026_02_GB_DET",
    )
    r.update(over)
    return r


LEAKAGE_CASES: list[tuple[str, Rejection, dict, dict | None, str]] = [
    (
        "a feature summarising a game the build cannot have seen",
        Rejection.FEATURE_TIMESTAMP_AFTER_PROJECTION,
        clean_record(feature_timestamp=_iso(AFTER)),
        clean_store_index(),
        "check_timestamps_not_after_projection",
    ),
    (
        "the vendor's own as-of claim postdates the projection",
        Rejection.SOURCE_TIMESTAMP_AFTER_PROJECTION,
        clean_record(source_timestamp=_iso(AFTER)),
        clean_store_index(),
        "check_timestamps_not_after_projection",
    ),
    (
        "we fetched it AFTER the projection instant (the Sunday inactive in a Tuesday build)",
        Rejection.CAPTURE_TIMESTAMP_AFTER_PROJECTION,
        clean_record(capture_timestamp=_iso(AFTER)),
        clean_store_index(clean_record(capture_timestamp=_iso(AFTER))),
        "check_timestamps_not_after_projection",
    ),
    (
        "the vendor published the file after the projection instant",
        Rejection.VENDOR_RELEASE_AFTER_PROJECTION,
        clean_record(vendor_release_timestamp=_iso(AFTER)),
        clean_store_index(),
        "check_timestamps_not_after_projection",
    ),
    (
        "the row landed in our store after the projection instant",
        Rejection.INGESTION_AFTER_PROJECTION,
        clean_record(ingestion_timestamp=_iso(AFTER)),
        clean_store_index(),
        "check_timestamps_not_after_projection",
    ),
    (
        "provenance missing — no capture_id",
        Rejection.PROVENANCE_MISSING,
        clean_record(capture_id=None),
        clean_store_index(),
        "check_provenance_present",
    ),
    (
        "provenance missing — an UNDECLARED null source_timestamp (the injuries.date_modified class)",
        Rejection.PROVENANCE_MISSING,
        clean_record(source_timestamp=None),
        clean_store_index(),
        "check_provenance_present",
    ),
    (
        "a revised vendor record replaced the original capture",
        Rejection.REVISED_VENDOR_RECORD,
        clean_record(payload_sha256="sha-REVISED"),
        {
            "2026_02_GB_CHI|forecast_intraday|T-120h": [
                {"capture_timestamp": _iso(BEFORE - timedelta(days=1)),
                 "payload_sha256": "sha-original"}
            ]
        },
        "check_original_capture",
    ),
    (
        # ISOLATING BY CONSTRUCTION: every stamp is BEFORE the projection, so the timestamp
        # clauses are all satisfied and only the phase clause can reject. This is the realistic
        # shape — a board labelled `closing` whose capture stamp claims Tuesday. A closing board
        # for a Sunday game cannot have existed on Tuesday whatever the stamp says.
        "a CLOSING line joined to an earlier (Tuesday) projection, with clean-looking stamps",
        Rejection.LATE_MARKET_JOIN,
        _market_record(market_phase="closing"),
        {"game_lines|evt-1": [{"capture_timestamp": _iso(BEFORE), "payload_sha256": "sha-original"}]},
        "check_market_phase",
    ),
    (
        "a rolling window whose END reaches the target game",
        Rejection.ROLLING_WINDOW_CONTAINS_TARGET,
        _window_record(window_end_timestamp=_iso(KICKOFF + timedelta(hours=1))),
        clean_store_index(_window_record()),
        "check_rolling_window",
    ),
    (
        "a rolling window that CONTAINS the target game by id (a same-day window a time bound misses)",
        Rejection.ROLLING_WINDOW_CONTAINS_TARGET,
        _window_record(window_game_ids=["2026_01_GB_CHI", "2026_02_GB_DET"]),
        clean_store_index(_window_record()),
        "check_rolling_window",
    ),
    (
        "UNEVALUABLE — a market record with no kickoff (an open line is indistinguishable from a close)",
        Rejection.UNEVALUABLE,
        _market_record(kickoff_timestamp=None),
        {"game_lines|evt-1": [{"capture_timestamp": _iso(BEFORE), "payload_sha256": "sha-original"}]},
        "check_market_phase",
    ),
    (
        "UNEVALUABLE — a rolling window with no bounds at all",
        Rejection.UNEVALUABLE,
        clean_record(is_rolling_window=True),
        clean_store_index(),
        "check_rolling_window",
    ),
    (
        "UNEVALUABLE — no store index, so ORIGINALITY cannot be proven (fail-closed, NF1.7 (a))",
        Rejection.UNEVALUABLE,
        clean_record(),
        None,
        "check_original_capture",
    ),
]

_IDS = [c[0] for c in LEAKAGE_CASES]


class TestTheCleanBaselineIsActuallyClean:
    """Without a clean baseline every rejection below could be an artifact of the fixture."""

    def test_a_well_formed_point_in_time_record_passes(self):
        report = evaluate_point_in_time([clean_record()], PROJECTION, store_index=clean_store_index())
        assert report.ok, f"the baseline must pass or every case below is uninterpretable: {report.findings}"

    def test_a_legitimately_declared_absent_source_timestamp_passes(self):
        """The nflverse injuries case: the vendor deleted its as-of column. A DECLARED absence is
        honest and must pass; only an UNDECLARED null is rejected (see the case list)."""
        rec = clean_record(
            source_timestamp=None,
            source_timestamp_absent_reason="nflverse deleted injuries.date_modified in 2025",
        )
        report = evaluate_point_in_time([rec], PROJECTION, store_index=clean_store_index(rec))
        assert report.ok, report.findings

    def test_an_early_market_snapshot_joins_a_later_projection_fine(self):
        """The whole POINT of the Tue/Fri forward capture: a Tuesday board IS usable by a Tuesday
        build. If this rejected, the capture would be worthless."""
        rec = _market_record(capture_timestamp=_iso(BEFORE), market_phase="open")
        report = evaluate_point_in_time(
            [rec], PROJECTION,
            store_index={"game_lines|evt-1": [{"capture_timestamp": _iso(BEFORE),
                                               "payload_sha256": "sha-original"}]},
        )
        assert report.ok, report.findings


class TestEachLeakageCaseIsRejected:
    @pytest.mark.parametrize("name,reason,record,index,_clause", LEAKAGE_CASES, ids=_IDS)
    def test_case_is_rejected_with_the_right_reason(self, name, reason, record, index, _clause):
        report = evaluate_point_in_time([record], PROJECTION, store_index=index)
        assert not report.ok, f"{name}: LEAKED — the guard accepted it"
        assert reason in {f.reason for f in report.findings}, (
            f"{name}: rejected, but for the wrong reason "
            f"({[f.reason.name for f in report.findings]}) — a case rejected by an unrelated clause "
            f"proves nothing about the clause it is named for"
        )

    @pytest.mark.parametrize("name,reason,record,index,_clause", LEAKAGE_CASES, ids=_IDS)
    def test_the_fail_closed_gate_raises(self, name, reason, record, index, _clause):
        with pytest.raises(LeakageRejection) as exc:
            assert_point_in_time([record], PROJECTION, store_index=index)
        assert reason in {f.reason for f in exc.value.findings}


class TestTheGuardIsNotVacuous:
    """⭐ The RED-proof, run mechanically (NF-D17).

    For each case: DISABLE the clause that owns it and require the record to become CLEAN. If it
    stays rejected, some OTHER clause was doing the rejecting, the fixture is not isolating, and
    the test above would stay green even with the named clause deleted from the source.
    """

    @pytest.mark.parametrize("name,reason,record,index,clause", LEAKAGE_CASES, ids=_IDS)
    def test_disabling_the_owning_clause_makes_the_case_pass(
        self, name, reason, record, index, clause, monkeypatch
    ):
        monkeypatch.setattr(lg, clause, lambda *a, **k: [])
        # `check_original_capture` fail-closes on a missing index; with it disabled a `None` index
        # is no longer a finding, which is exactly what the disable is meant to demonstrate.
        report = evaluate_point_in_time([record], PROJECTION, store_index=index)
        assert report.ok, (
            f"{name}: still rejected after disabling `{clause}` "
            f"({[f.reason.name for f in report.findings]}) — the fixture trips more than one "
            f"clause, so it does NOT prove `{clause}` is what rejects it (the NF-D17 vacuous-guard "
            f"defect)."
        )

    def test_every_rejection_reason_has_at_least_one_constructed_case(self):
        """A rejection reason with no fixture is an unenforced clause wearing a badge."""
        covered = {reason for _, reason, _, _, _ in LEAKAGE_CASES}
        missing = set(Rejection) - covered
        assert not missing, f"§13 rejection reasons with NO deliberately-constructed case: {missing}"

    def test_every_clause_function_is_exercised_by_some_case(self):
        clauses = {c[4] for c in LEAKAGE_CASES}
        declared = {
            "check_provenance_present", "check_timestamps_not_after_projection",
            "check_original_capture", "check_market_phase", "check_rolling_window",
        }
        assert declared == clauses, f"clause coverage drifted: declared={declared} exercised={clauses}"


class TestFailClosedOnUnusableInput:
    """Fail-closed means UNPARSEABLE and NAIVE are rejections, not passes."""

    def test_a_naive_timestamp_is_rejected_not_assumed_utc(self):
        rec = clean_record(capture_timestamp="2026-09-15T13:00:00")  # no offset
        report = evaluate_point_in_time([rec], PROJECTION, store_index=clean_store_index(rec))
        assert not report.ok
        assert Rejection.UNEVALUABLE in {f.reason for f in report.findings}

    def test_an_unparseable_projection_timestamp_rejects_everything(self):
        report = evaluate_point_in_time([clean_record()], "not-a-timestamp",
                                        store_index=clean_store_index())
        assert not report.ok
        assert Rejection.UNEVALUABLE in {f.reason for f in report.findings}

    def test_an_empty_record_is_rejected_rather_than_trivially_clean(self):
        """A guard that passes an empty dict passes on nothing at all."""
        report = evaluate_point_in_time([{}], PROJECTION, store_index={})
        assert not report.ok
        assert Rejection.PROVENANCE_MISSING in {f.reason for f in report.findings}


class TestClosingWindowIsPhaseIndependent:
    """The late-market clause must fire on the CAPTURE-TO-KICKOFF distance too, not only on a
    self-reported `market_phase` — a mislabelled board is the likelier real-world failure."""

    def test_a_snapshot_inside_the_closing_window_is_late_even_when_labelled_open(self):
        rec = _market_record(
            market_phase="open",  # ⚠️ mislabelled
            capture_timestamp=_iso(KICKOFF - timedelta(minutes=45)),
        )
        index = {"game_lines|evt-1": [{"capture_timestamp": rec["capture_timestamp"],
                                       "payload_sha256": "sha-original"}]}
        report = evaluate_point_in_time([rec], PROJECTION, store_index=index)
        assert Rejection.LATE_MARKET_JOIN in {f.reason for f in report.findings}

    def test_a_non_market_record_is_not_subjected_to_the_market_clause(self):
        assert lg.check_market_phase(clean_record(), PROJECTION) == []

    def test_a_gameday_projection_MAY_consume_a_closing_board(self):
        """The clause must not be a blanket ban: the Sunday-morning re-projection is a designed
        build of the weekly system, and it legitimately sees a near-closing market. A clause that
        rejected this would break the product rather than protect it."""
        gameday_projection = KICKOFF - timedelta(minutes=90)
        rec = _market_record(
            market_phase="closing",
            capture_timestamp=_iso(KICKOFF - timedelta(minutes=100)),
            feature_timestamp=_iso(KICKOFF - timedelta(minutes=100)),
            source_timestamp=_iso(KICKOFF - timedelta(minutes=100)),
            vendor_release_timestamp=_iso(KICKOFF - timedelta(minutes=100)),
            ingestion_timestamp=_iso(KICKOFF - timedelta(minutes=100)),
        )
        assert lg.check_market_phase(rec, gameday_projection) == []
