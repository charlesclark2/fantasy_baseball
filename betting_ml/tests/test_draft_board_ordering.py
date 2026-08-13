"""The BEST-AVAILABLE board must defer K/DST exactly as the recommendations do.

⛔ ANCHORED IN ITS OWN CLAUSE. These tests fail only for the board-ordering property. Nothing here
is bolted onto the NF1.6 K/DST guards (`test_nf1_6_kdst_projection.py`) or the engine guards
(`test_draft_optimizer.py`) — the E9.60 coupling trap.

⭐ WHY THIS EXISTS. PR #754 deferred K/DST in `recommend`, so the RECOMMENDATION panel stopped
offering a D/ST in the early rounds. The "Available players" board underneath it was sorted INLINE in
the component by raw `ovrRank`/`pts`/`vor`, so the same D/ST reappeared at the top of best-available —
reported live 2026-08-13 with PIT D/ST at #56, level with WRs on VOR 6. A user who declines the
recommendation reads that board, so fixing one surface and not the other left them one click from the
advice we had just decided not to give.

⚠️ The inline sort's own comment read "null pts/vor (K/DST) always sort to the bottom regardless of
direction" — TRUE when MVP-3 shipped K/DST as null-VOR placeholders, silently false from NF1.6 on.
The same stale pre-NF1.6 assumption that produced the recommendation bug, in a second place. That is
what this file is really guarding against: the rule living in two places and drifting apart.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
_LIB = _FRONTEND / "lib" / "draft-optimizer.ts"
_COMPONENT = _FRONTEND / "components" / "fantasy" / "draft-optimizer.tsx"


def _strip_ts_comments(src: str) -> str:
    """⚠️ INC-38: a source-inspection guard a COMMENT can satisfy cannot fail. Both files here
    explain the defect at length in prose, quoting the very identifiers the scans below look for.

    ⚠️⚠️ LINE COMMENTS COME OFF **FIRST**, AND THAT ORDER IS THE WHOLE FUNCTION. Stripping blocks
    first is the obvious implementation and it is blind in the dangerous direction: `draft-
    optimizer.tsx` carries a real `//` comment containing "(/fantasy/nfl/*, require_fantasy_access)",
    whose `/*` a `/\\*.*?\\*/` regex happily closes at the next genuine `*/` — measured at 55 lines of
    LIVE CODE deleted, after which the guard scans a source with the lines it polices removed and
    reports green over a defect physically present on disk.
    """
    src = re.sub(r"(?<!:)//[^\n]*", "", src)  # (?<!:) keeps `https://` intact
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return src


@pytest.fixture(scope="module")
def lib_src() -> str:
    return _strip_ts_comments(_LIB.read_text())


@pytest.fixture(scope="module")
def component_src() -> str:
    return _strip_ts_comments(_COMPONENT.read_text())


def test_the_comment_stripper_cannot_eat_live_code():
    """The stripper is load-bearing, so prove it on the exact shape that broke it before.

    Without this, every assertion in the file could be passing over source the stripper deleted.
    """
    fixture = "\n".join(
        [
            "// boards load through the gated backend (/fantasy/nfl/*, require_fantasy_access)",
            "const KEEP_ME = sortAvailable(rows, opts)",
            "/* a real block comment mentioning sortAvailable */",
            "const ALSO_KEEP = p.lowPred",
        ]
    )
    out = _strip_ts_comments(fixture)
    assert "KEEP_ME = sortAvailable(rows, opts)" in out, "the stripper ate a live line"
    assert "ALSO_KEEP = p.lowPred" in out, "the stripper ate a live line after a block comment"
    assert "require_fantasy_access" not in out and "a real block comment" not in out


def test_the_board_ordering_lives_in_the_engine_module(lib_src: str):
    """One implementation, exported — not a comparator copied into a component."""
    assert "export function sortAvailable" in lib_src


def test_the_shared_sorter_defers_low_predictability_rows(lib_src: str):
    """`sortAvailable` must consult `lowPred`, and BEFORE the chosen sort column.

    Ordering matters: the deferral has to outrank the column so it holds under an explicit
    VOR-descending click — which is exactly the ordering that surfaced the D/ST.
    """
    body = lib_src.split("export function sortAvailable", 1)[1]
    body = body.split("\nexport ", 1)[0]
    assert "deferLowPred" in body and "lowPred" in body
    defer_at = body.index("deferLowPred &&")
    column_at = body.index("val(a)")
    assert defer_at < column_at, (
        "the low-predictability deferral is applied AFTER the sort column, so an explicit "
        "VOR-descending sort would still float a D/ST to the top of best-available"
    )


def test_the_component_uses_the_shared_sorter_and_keeps_no_comparator_of_its_own(component_src: str):
    """WIRED **AND** INVOKED, and the second half is the one that bites (NF-C0e).

    Importing `sortAvailable` while a local comparator still runs would leave the board ordered by
    the old rule with an unused import to make it look fixed.
    """
    assert "sortAvailable(" in component_src, "the component does not call the shared sorter"
    assert "deferLowPred" in component_src, "the component does not pass the deferral decision"
    # No hand-rolled comparator left behind: the tell is a local sort keyed on the board columns.
    assert "sortCol === \"ovrRank\" ? p.ovrRank" not in component_src, (
        "a local ovrRank/pts/vor comparator survives in the component — the rule is in two places "
        "again, which is how the board and the recommendations drifted apart in the first place"
    )


def test_an_explicit_kdst_filter_still_shows_those_rows(component_src: str):
    """Deferral must be OFF when the user has asked for K or D/ST by name.

    A deferral that also applied inside the K/DST tabs would bury the rows inside the one view whose
    entire purpose is to show them — a fix that reads as a worse bug.
    """
    assert 'posFilter !== "K" && posFilter !== "DST"' in component_src, (
        "the component no longer disables the deferral for an explicit K/DST filter"
    )


def test_a_low_predictability_row_shows_no_cross_position_overall_rank(component_src: str):
    """`ovrRank` is built from VOR across positions, and that comparison is the defect itself.

    Rendering it beside a deferred row both restates the untrustworthy number and makes the column
    jump backwards at the deferral boundary, which reads as a broken sort.
    """
    assert 'p.lowPred ? "—" : p.ovrRank' in component_src


@pytest.mark.parametrize(
    "claim",
    [
        "aren&apos;t projected",
        "won&apos;t appear on the board",
        "offensive skill only",
    ],
)
def test_the_retired_pre_nf1_6_claim_is_gone(component_src: str, claim: str):
    """⛔ The roster panel claimed "K & DST aren't projected (offensive skill only) — they won't
    appear on the board." False since NF1.6, and it contradicted the caption over the board on the
    SAME PAGE, which correctly said they are projected as streaming tiers. A user reading both learns
    the tool does not know what it does.
    """
    assert claim not in component_src, f"the retired pre-NF1.6 K/DST claim is back: {claim!r}"
