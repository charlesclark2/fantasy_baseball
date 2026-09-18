"""NF-WK-ACC1 — the two residual rulings (PM, 2026-09-18). ① SHIPPED, ② REVERTED TO OPTION C.

⭐ WHY BOTH LIVE IN ONE FILE. They were handed down together and they are each other's control: ①
changed a mapping and ② deliberately did not, so a guard that only pinned the change would leave
nothing stopping a later session from "finishing the job" on ② — which the measurement says would be
wrong. The clauses below pin the change AND pin the non-change.

RULING ① — option A. `fumbles_lost` reads `fumbles_lost_total`. Measured on DJ Moore's real 2025 wk1
line under the operator's real league settings: 8.40 → 7.40, against the league's published 7.40.

RULING ② — the pre-declared gate returned CONTRADICTED, so the map is UNTOUCHED. Sleeper credits all
19 measured rows with the individual event; it records it under a different KEY NAMESPACE from the
team-defence keys a league's `def_*` weights reference. The rule is namespace, not position.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.backend.services import league_scoring as LS
from app.backend.services import realized_stat_fields as R

ROOT = Path(__file__).resolve().parents[2]

#: DJ Moore, 2025 week 1, CHI at MIN — his REAL line, read off the lake on 2026-09-18 and recorded
#: here with its provenance rather than invented. ⚠️ `carries` IS LOAD-BEARING and was missing from
#: the first hand-built version of this fixture, which scored 0.30 low both ways and sent a session
#: hunting a phantom: the league pays `rush_att` 0.1. A fixture assembled from the columns a session
#: THINKS matter is the NF-C0e restate-the-code shape (part 3's own lesson, one layer over).
DJ_MOORE_2025_WK1: dict = {
    "player_id": "00-0034827", "player_display_name": "DJ Moore",
    "position": "WR", "team": "CHI", "opponent_team": "MIN",
    "receptions": 3, "targets": 5, "receiving_yards": 68, "receiving_tds": 0,
    "carries": 3, "rushing_yards": 8, "rushing_tds": 0,
    # ⭐ THE WHOLE POINT OF THE ROW: a fumble lost OUTSIDE the three offensive phases. The total says
    # 1; every per-phase column says 0. That is the shape the old mapping could not charge for.
    "fumbles_total": 1, "fumbles_lost_total": 1,
    "sack_fumbles_lost": 0, "rushing_fumbles_lost": 0, "receiving_fumbles_lost": 0,
    "fantasy_points_ppr": 10.6,
}

#: The operator's league, reduced to the terms that touch this row. `fum` −1 AND `fumbles_lost` −1 is
#: the league's own choice — a lost fumble is charged twice — and `rush_att` 0.1 is what the first
#: fixture missed.
LEAGUE_SCORING: dict = {"per_stat": {
    "rec": 0.5, "rec_yds": 0.1, "rush_yds": 0.1, "rush_att": 0.1,
    "fum": -1.0, "fumbles_lost": -1.0,
}}

#: What the league itself published for this seat — the external authority, not our recomputation.
PLATFORM_POINTS = 7.40

#: What the per-phase mapping produced. Kept so the guard is TWO-SIDED: a clause that only asserts
#: the new number cannot tell a working change from a fixture that never exercised the old one.
PRE_RULING_POINTS = 8.40


def _score(source: tuple[str, ...], row: dict | None = None) -> float:
    """`row` (default DJ Moore's real line) under the league's real weights, with `fumbles_lost` read
    from `source`. Drives the REAL resolver and the REAL scorer — a test that re-derived the
    arithmetic would be restating the code rather than testing it.

    ⚠️ BOTH THE SOURCE MAP AND THE RESOLVED FIELD MAP MUST MOVE TOGETHER, and the first cut of this
    helper moved only the first. `flatten_realized_row` writes each value under the MODULE-LEVEL
    `REALIZED_STAT_FIELD` (resolved at import), so patching only `REALIZED_SOURCE_ALL` left the
    flattener writing under the NEW field name while the scorer was handed the OLD one — the value
    landed somewhere nothing looked up and silently scored 0. That is the NF-C0e wrong-key class
    inside a test fixture, and it made a real assertion fail for a fake reason.
    """
    keep_source = R.REALIZED_SOURCE_ALL["fumbles_lost"]
    keep_field = dict(R.REALIZED_STAT_FIELD)
    try:
        R.REALIZED_SOURCE_ALL["fumbles_lost"] = source
        field = R.resolve_realized_fields()
        R.REALIZED_STAT_FIELD.clear()
        R.REALIZED_STAT_FIELD.update(field)
        flat = R.flatten_realized_row(row if row is not None else DJ_MOORE_2025_WK1)
        resolved, _ = LS.resolve_scoring(LEAGUE_SCORING, stat_field=field,
                                         fields=LS.available_fields([flat]))
        return LS.score_row(flat, "WR", resolved, field)["pts"]
    finally:
        R.REALIZED_SOURCE_ALL["fumbles_lost"] = keep_source
        R.REALIZED_STAT_FIELD.clear()
        R.REALIZED_STAT_FIELD.update(keep_field)


def _score_as_shipped() -> float:
    """DJ Moore's real line through the map AS SHIPPED — nothing patched, nothing recomputed.

    ⭐ THIS is what makes the ruling's own clause sensitive to the SHIPPED configuration rather than to
    a source the test hands in. `_score` exists only for the historical comparison.
    """
    flat = R.flatten_realized_row(DJ_MOORE_2025_WK1)
    resolved, _ = LS.resolve_scoring(LEAGUE_SCORING, stat_field=R.REALIZED_STAT_FIELD,
                                     fields=LS.available_fields([flat]))
    return LS.score_row(flat, "WR", resolved, R.REALIZED_STAT_FIELD)["pts"]


# ── ruling ①: the mapping, and the number it was ruled on ────────────────────────────────────────

def test_the_lost_fumble_term_reads_the_total():
    """The mapping itself. `fum` stays on `fumbles_total` — they are different terms and the league
    pays both, so a change that collapsed them would 'agree' for the wrong reason."""
    assert R.REALIZED_STAT_SOURCE["fumbles_lost"] == ("fumbles_lost_total",)
    assert R.REALIZED_STAT_FIELD["fumbles_lost"] == "fumbles_lost_total"
    assert R.REALIZED_STAT_SOURCE["fum"] == ("fumbles_total",)
    assert R.REALIZED_STAT_FIELD["fum"] != R.REALIZED_STAT_FIELD["fumbles_lost"]


def test_dj_moore_2025_wk1_now_reproduces_his_leagues_own_figure():
    """⭐ THE RULING'S OWN TEST CASE (PM: "RED-prove on DJ Moore 2025 wk1, 8.40 → 7.40").

    TWO-SIDED ON PURPOSE. Asserting 7.40 alone would pass on a fixture that never had a lateral-class
    fumble in it; asserting that the OLD mapping produces 8.40 on the SAME row is what proves this
    row exercises the mechanism the ruling is about.

    ⛔ THE "NOW" NUMBER IS SCORED THROUGH THE **SHIPPED** MAP, with nothing patched, and the first cut
    of this clause was not. `_score` takes a source and patches it in, so asking it for the new number
    measured the scorer's ARITHMETIC over a source the TEST supplied — leaving the clause GREEN when
    the shipped mapping was reverted to the per-phase columns, which is precisely the break the ruling
    exists to forbid. The RED proof caught it. The historical number still comes through `_score`,
    because a comparison against a mapping that is no longer in the code has nowhere else to come from.
    """
    new = _score_as_shipped()
    old = _score(("sack_fumbles_lost", "rushing_fumbles_lost", "receiving_fumbles_lost"))
    assert new == pytest.approx(PLATFORM_POINTS), "we must now reproduce the league's own figure"
    assert old == pytest.approx(PRE_RULING_POINTS), (
        "the old mapping must still produce 8.40 on this row — otherwise the fixture does not "
        "exercise the mechanism and the 7.40 above proves nothing")
    assert old - new == pytest.approx(1.0), "the gap is exactly the one `fumbles_lost` weight"


def test_a_purely_offensive_fumble_is_unaffected_by_the_change():
    """⛔ THE CHANGE MUST NOT MOVE A ROW IT HAS NO BUSINESS MOVING. On a fumble lost on a rush, the
    total and the per-phase sum agree, so both mappings must score identically — otherwise this was
    a level shift on every fumbling player rather than a fix to one class of row."""
    row = {**DJ_MOORE_2025_WK1, "rushing_fumbles_lost": 1}
    new = _score(R.REALIZED_STAT_SOURCE["fumbles_lost"], row)
    old = _score(("sack_fumbles_lost", "rushing_fumbles_lost", "receiving_fumbles_lost"), row)
    assert new == pytest.approx(old)
    # NON-VACUITY: both mappings must actually CHARGE on this row, or "they agree" would just mean
    # neither term fired and the clause would pass on a row it never exercised.
    assert new == pytest.approx(PLATFORM_POINTS), (
        "an offensive fumble must be charged under both readings — if this is 8.40 the row is not "
        "exercising the term at all")


# ── ruling ①: the publish path the change would otherwise have stranded ──────────────────────────

def test_the_per_phase_columns_are_still_carried_so_the_change_can_actually_ship():
    """⛔ THE NON-OBVIOUS HALF. `fumbles_lost` no longer READS these three, but if they left the
    artifact the column set would SHRINK, and `publish_decision` classifies a shrink as a vendor
    `restate` — so every already-published week would keep serving its old rows and the ruling would
    never reach a reader. They are declared as diagnostic columns for exactly that reason."""
    RW = pytest.importorskip(
        "quant_sports_intel_models.football.nfl.fantasy.realized_week",
        reason="realized_week pulls pandas through the lake read")
    carried = set(RW.required_columns())
    for column in R.REALIZED_DIAGNOSTIC_COLUMNS:
        assert column in carried, f"{column} leaving the artifact would strand the ruling"
    assert "fumbles_lost_total" in carried
    # The set must be a strict SUPERSET of what it was before the ruling — that is what makes the
    # republish a `widen_columns` rather than a refused narrowing.
    pre_ruling = carried - {"fumbles_lost_total"}
    assert not (pre_ruling - carried)


def test_the_diagnostic_columns_are_declared_with_a_reason_not_left_as_cruft():
    """A column nothing reads is pruned by the next reader; a column something deliberately keeps
    needs a name. This pins that the set is the three per-phase columns and no more, so it cannot
    quietly become a dumping ground."""
    assert set(R.REALIZED_DIAGNOSTIC_COLUMNS) == {
        "sack_fumbles_lost", "rushing_fumbles_lost", "receiving_fumbles_lost"}
    # ...and none of them is a scoring source any more, which is what makes them diagnostic
    scoring_columns = {c for cols in R.REALIZED_SOURCE_ALL.values() for c in cols}
    assert not (set(R.REALIZED_DIAGNOSTIC_COLUMNS) & scoring_columns)


def test_the_amended_refusal_says_what_the_pm_required_it_to_say():
    """The PM's explicit instruction: rewrite the refusal, do not delete it, and have it state what
    the old one claimed, which half died and why, which half is superseded and by what precedent, and
    the measured cost that forced the amendment.

    ⚠️ A PROSE GUARD IS WEAK BY NATURE, so this pins FACTUAL ANCHORS a paraphrase cannot carry
    (the figures and the named precedent) rather than adjectives.
    """
    header = R.__doc__ or ""
    assert "WHAT THE OLD REFUSAL CLAIMED" in header
    assert "Do not 'tidy' this back to the total" in header, \
        "the old refusal's own words must survive, or a reader cannot tell what was overturned"
    # which half died, and the measurement that killed it
    assert "THERE IS NO LIVE PARITY GUARD" in header
    assert "CARRIED THROUGH VERBATIM" in header
    # which half is superseded, and by what
    assert "option D" in header
    # the measured cost
    for anchor in ("36 rows", "8.40", "7.40"):
        assert anchor in header, f"the amended refusal must carry the measured cost: {anchor}"


# ── ruling ②: the map is UNTOUCHED, and that is deliberate ───────────────────────────────────────

#: The seven terms that came from Sleeper's TEAM-DEFENCE scoring keys and sit in the PLAYER-grain map.
#: ⛔ THIS IS THE STATE RULING ② LEFT IN PLACE, not an endorsement of it — see the test below.
_TEAM_DEFENCE_TERMS = ("def_sacks", "def_int", "def_fumble_rec", "def_td", "def_safety",
                       "def_forced_fumble", "st_td")


def test_ruling_two_left_the_player_grain_defensive_terms_ALONE():
    """⛔ THE NON-CHANGE, PINNED. The pre-declared gate returned CONTRADICTED — Sleeper credits all 19
    measured rows with the individual event, under `idp_*` / `st_*` keys rather than the team-defence
    keys a league's `def_*` weights reference — so its rule is NAMESPACE, not position. Scoping these
    by position would give the right answer for the wrong reason on those rows and the WRONG answer
    for a league paying `idp_*`.

    A later session reading only "Trey Benson is still 1.00 out" would reach for the position scope.
    This clause is here to stop that: the fix is refused BY MEASUREMENT, and re-opening it needs the
    study the PM asked for, not an edit.
    """
    for term in _TEAM_DEFENCE_TERMS:
        assert term in R.REALIZED_STAT_SOURCE, (
            f"{term} was removed or scoped — ruling ② reverted to option C on the measured evidence; "
            "see run_nf_wk_acc1_idp_scope_verify")


def test_the_pre_registered_gate_and_its_vacuity_control_are_still_present():
    """The gate is the record of WHY ② is refused, so it must not be deleted as a spent script — and
    its vacuity control is what makes its verdict worth anything (the first run of that gate returned
    PASS on keys no individual player can ever carry)."""
    mod = pytest.importorskip(
        "quant_sports_intel_models.football.nfl.fantasy.run_nf_wk_acc1_idp_scope_verify",
        reason="the gate imports the lake reader lazily but pandas may be absent")
    # the corrected namespace: each term names the INDIVIDUAL keys, not only the team-defence one
    for term, (_lake, team_key, indiv) in mod.IDP_FAMILY.items():
        assert indiv, f"{term} names no individual key — the gate would pass vacuously"
        assert team_key not in indiv, "the team-defence key is not an individual key"
    assert set(mod.SUPERSEDED_TEAM_GRAIN_KEYS.values()) == {"fum_rec", "ff", "sack"}, \
        "the superseded keys are kept so the vacuous first run stays reproducible"
    # ⚠️ READ `verify`'s OWN SOURCE, not the module's. The first cut checked the whole file, and the
    # tokens also appear in the CLI print block — so deleting the control from the function that
    # COMPUTES the verdict left the clause green. The RED proof caught it; a file-wide `x in src`
    # check is insensitive to exactly the deletion it is written to catch.
    import inspect
    verify_src = inspect.getsource(mod.verify)
    for token in ("instrumentSound", "deadKeys", "dead = sorted"):
        assert token in verify_src, (
            f"the vacuity control ({token}) left `verify` — without it a sweep of zeros reads as a "
            "PASS, which is how the first run of this gate returned PASS on nothing")
