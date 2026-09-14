"""NF-INJ4b-VERIFY — the post-publish check must not confuse a CLEARED player, or a DRIFTED base,
with a discount that failed to serve.

⛔ THE INCIDENT (2026-09-13, the first real post-publish run). `--verify-published` joined the
served board to an expectation captured three days earlier and asked ONE question — "did this
player's games move off the pre-ship figure?" It printed

    ⛔ 4 of 58 scoreable designated player(s) still carry their PRE-SHIP games
       — the discount is not reaching the served board

and exited 1. The discount was reaching the board. The build had applied it to every designated row;
those four simply carry the four SMALLEST discounts in the set (0.067–0.152 games), and three days
of fresh depth charts, rosters and market had drifted their BASE by more than that — so the
post-discount value rounded, at the board's one decimal, back onto the captured figure.

⭐ TWO DISTINCT DEFECTS, AND THIS SUITE PINS BOTH FIXES:
  1. the check could not express "this player is no longer designated" (he was cleared — carrying no
     discount is CORRECT), so it rendered that as UNMOVED, i.e. as a wiring failure;
  2. the check INFERRED application from a board whose base it could not observe. The cure is for
     the build to RECORD what it did and the manifest to carry it — the same principle the
     freshness block already states one function over: read what the build wrote, never re-derive
     at export time, because re-deriving answers a different and more flattering question.

This is the repo's most-repeated lesson landing on a guard written to honour it: a check whose
failure state is indistinguishable from a healthy state has not verified anything (G100-D1), and an
expectation pinned to a live vendor snapshot expires (NF-INJ2b/2c).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

_FAN = _REPO / "quant_sports_intel_models/football/nfl/fantasy"


@pytest.fixture(scope="module")
def B():
    from quant_sports_intel_models.football.nfl.fantasy import run_nf_inj4b_ship_battery as B
    return B


def _row(pid, name="X", desig="Questionable", before=10.0, after=9.629, pos="RB"):
    return {"id": pid, "name": name, "pos": pos, "designation": desig,
            "games_before": before, "games_after": after}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. the states the check must be able to tell apart
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_a_player_who_LEFT_the_feed_is_not_reported_as_unmoved(B):
    """The defect verbatim: cleared since the capture, so carrying NO discount is CORRECT.

    His games sit at the undiscounted base — the very number the frozen expectation calls
    'pre-ship'. Scoring that as UNMOVED reports the system working as the system broken."""
    rows = [_row("00-001", "Cleared Guy")]
    detail, c = B.classify_verification(rows, {"00-001": 10.0}, {})   # absent from the live feed
    assert c[B.VERIFY_NO_LONGER_DESIGNATED] == 1
    assert c[B.VERIFY_UNMOVED] == 0, "a cleared player must never be scored as a missed discount"
    assert detail[0][0] == B.VERIFY_NO_LONGER_DESIGNATED


def test_a_player_whose_designation_CHANGED_is_its_own_state(B):
    """Questionable → Out prices a DIFFERENT constant, so the captured `games_after` is simply the
    wrong number to compare against. Neither a pass nor a failure: expired evidence."""
    rows = [_row("00-002", "Worse Now", desig="Questionable")]
    detail, c = B.classify_verification(rows, {"00-002": 10.0}, {"00-002": "Out"})
    assert c[B.VERIFY_DESIGNATION_CHANGED] == 1
    assert c[B.VERIFY_UNMOVED] == 0


def test_an_unpriceable_token_is_expired_evidence_not_a_failure(B):
    """`weekly_designation_map` returns None for a token this build cannot read (it renders
    'unknown' and is deliberately NEVER priced). A row serving no discount BY DESIGN must not be
    scored as a discount that failed to arrive."""
    rows = [_row("00-003", "Odd Token")]
    detail, c = B.classify_verification(rows, {"00-003": 10.0}, {"00-003": None})
    assert c[B.VERIFY_DESIGNATION_CHANGED] == 1
    assert c[B.VERIFY_UNMOVED] == 0


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. …and it must KEEP ITS TEETH (the other half — a fix that only ever passes is not a fix)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_a_STILL_designated_row_at_its_pre_ship_games_is_still_UNMOVED(B):
    """Two-sided proof. The whole risk of the fix above is over-forgiving the check into something
    that can no longer say NO, which would be the same vacuity in a friendlier costume."""
    rows = [_row("00-004", "Still Q")]
    detail, c = B.classify_verification(rows, {"00-004": 10.0}, {"00-004": "Questionable"})
    assert c[B.VERIFY_UNMOVED] == 1, "a still-designated row that did not move must still be caught"


def test_a_row_that_moved_is_MOVED_even_when_it_lands_off_the_captured_figure(B):
    """A rebuild refreshes depth charts, rosters and the market, so the base drifts; landing
    near-but-not-on the first-order number is expected and is not a defect."""
    rows = [_row("00-005", "Drifted")]
    _, c = B.classify_verification(rows, {"00-005": 9.7}, {"00-005": "Questionable"})
    assert c[B.VERIFY_MOVED] == 1


def test_a_discount_below_the_boards_rounding_is_its_own_state_not_a_pass(B):
    """Preserved from the original check: counting these as 'moved' once reported 2 successes
    against a board that had not shipped at all."""
    rows = [_row("00-006", "Tiny", before=1.1, after=1.06)]
    _, c = B.classify_verification(rows, {"00-006": 1.1}, {"00-006": "Questionable"})
    assert c[B.VERIFY_BELOW_ROUNDING] == 1
    assert c[B.VERIFY_UNMOVED] == 0


def test_the_case_that_actually_shipped_is_classified_correctly_both_ways(B):
    """Devin Neal, verbatim: 4.1 games, a 0.152 discount, still Questionable on the live feed.

    STILL UNMOVED at the per-row layer — the fix does not paper over him — which is exactly why the
    verdict has to be settled by the build's own record rather than by this comparison."""
    rows = [_row("00-0039901", "Devin Neal", before=4.1, after=3.9479)]
    _, c = B.classify_verification(rows, {"00-0039901": 4.1}, {"00-0039901": "Questionable"})
    assert c[B.VERIFY_UNMOVED] == 1


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. the manifest must state what the BUILD did — and UNKNOWN must never render as zero
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_an_absent_build_record_is_UNKNOWN_and_never_zero(tmp_path, monkeypatch):
    """NF1.7 (a) on the served payload. `rows_discounted: 0` asserts "the discount ran and moved
    nothing" — a claim about the world. An absent summary supports no such claim, and a board
    published before this change must not be made to make one."""
    from quant_sports_intel_models.football.nfl.fantasy import export_draft_board_json as EX
    monkeypatch.setattr(EX, "_ARTIFACTS", tmp_path)
    assert EX._designation_apply_record(None, 2026) == {}

    (tmp_path / "nf1_5_projection_summary_2026.json").write_text("{not json")
    assert EX._designation_apply_record(None, 2026) == {}, "unreadable is UNKNOWN, never zero"

    (tmp_path / "nf1_5_projection_summary_2026.json").write_text(json.dumps({"a": 1}))
    assert EX._designation_apply_record(None, 2026) == {}, "an older summary is UNKNOWN, never zero"


def test_an_unknown_season_is_UNKNOWN_rather_than_a_guessed_year(tmp_path, monkeypatch):
    """⛔ A guessed fallback year would read a DIFFERENT season's summary and report its count as
    this build's — a wrong answer dressed as a measurement, strictly worse than an honest UNKNOWN.
    (The first cut of this reader did exactly that, via a constant that did not exist; the NameError
    it raised would have dropped the ENTIRE stamp from the served manifest — NF-TR2, found because
    a test INVOKED the block rather than reading its source.)"""
    from quant_sports_intel_models.football.nfl.fantasy import export_draft_board_json as EX
    monkeypatch.setattr(EX, "_ARTIFACTS", tmp_path)
    (tmp_path / "nf1_5_projection_summary_2026.json").write_text(json.dumps(
        {"designation_discount": {"rows_moved": 60, "designated_rows_on_frame": 60}}))
    assert EX._designation_apply_record(None, None) == {}, (
        "with no season the reader must decline, never fall back to a year and read a "
        "different build's record")


def test_the_build_record_reaches_the_served_stamp(tmp_path, monkeypatch):
    from quant_sports_intel_models.football.nfl.fantasy import export_draft_board_json as EX
    monkeypatch.setattr(EX, "_ARTIFACTS", tmp_path)
    (tmp_path / "nf1_5_projection_summary_2026.json").write_text(json.dumps(
        {"designation_discount": {"feed_readable": True, "designated_rows_on_frame": 60,
                                  "rows_moved": 60}}))
    stamp = EX.designation_discount_stamp(None, None, season=2026)
    assert stamp is not None
    assert stamp["rows_discounted"] == 60
    assert stamp["designated_rows_at_build"] == 60
    assert "null` means UNKNOWN" in stamp["records_what"]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4. the WIRING that carries it — guard the plumbing, not a token spelling (the NF-CAP1 re-key)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _src(name: str) -> str:
    return (_FAN / name).read_text()


def test_the_build_threads_its_discount_record_all_the_way_to_the_summary():
    """⭐ Three hops, each pinned, because the record is useless if any one of them is dropped —
    and a dropped hop fails SILENTLY (the manifest just says UNKNOWN forever)."""
    proj = _src("run_season_projection.py")
    assert "desig_log: dict | None = None" in proj, "build_projection must accept the out-param"
    assert "desig_log.update(_desig_log)" in proj, "…and must actually populate it"

    nf15 = _src("run_nf1_5.py")
    assert "desig_log=desig_log" in nf15, "build_season_projection must pass it down"
    assert "desig_log=_desig_applied" in nf15, "main must supply a dict to fill"
    assert '"designation_discount": _desig_applied' in nf15, "…and write it into the summary"


def test_the_verifier_prefers_the_build_record_over_its_own_inference():
    src = _src("run_nf_inj4b_ship_battery.py")
    assert 'built.get("rows_discounted")' in src, "the check must read the build's own count"
    # ⛔ and it must SAY SO when it cannot: a board with no record yields an INFERRED verdict, and
    #    an inferred UNMOVED is ambiguous. Silence there is how the original defect read as fact.
    assert "AMBIGUOUS" in src


def test_an_unreadable_designation_feed_is_UNVERIFIABLE_and_never_green():
    """With no live designations EVERY row looks cleared, so a check that treated an unreadable
    feed as 'nothing changed' would return GREEN over a board it could not assess — the one
    direction that must not be reachable."""
    src = _src("run_nf_inj4b_ship_battery.py")
    i = src.index("live_designations = EX.weekly_designation_map")
    window = src[i:i + 900]
    assert "if live_designations is None" in window
    assert "return 2" in window, "an unreadable feed must exit UNVERIFIABLE, not 0 and not 1"
