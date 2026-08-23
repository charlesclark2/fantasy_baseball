"""NF-INJ-NEWS-1 — the reported-absence games cap: an OPERATOR JUDGMENT with provenance.

⚖️ WHAT THESE GUARDS DEFEND is not accuracy — there is no accuracy claim to defend. The mechanism
is a human reading a beat report; it is not fitted and never backtested. What can go wrong is
everything AROUND that judgment: a cap that double-discounts a player the formal path already
handles, a cap that raises availability, a stale judgment that never dies, a join that silently
matches nothing, a payload that claims a cap which was never applied, and copy that dresses an
operator's guess as a projection improvement. Each of those is a clause below.

⭐ EVERY CLAUSE HAS ITS OWN ISOLATING FIXTURE. NF-D17's lesson: a guard on an `and`-composed rule is
VACUOUS unless its fixture satisfies every OTHER clause, because a second clause already refusing
the fixture makes deleting the clause under test change nothing observable. So each fixture here is
built so that ONLY the rule it names can decide the outcome. All of it is RED-proven by
`betting_ml/tests/nf_inj_news_1_red_proof.py` — a mutation that lands on disk AND moves the
asserted predicate, per #682/#815/E11.24.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quant_sports_intel_models.football.nfl.fantasy import reported_absence_overrides as RAO
from quant_sports_intel_models.football.nfl.fantasy import season_projection as SP

_REPO = Path(__file__).resolve().parents[2]
_FANTASY = _REPO / "quant_sports_intel_models/football/nfl/fantasy"


def _row(pid="00-0039918", name="Jordyn Tyson", miss=8, url="https://example.com/report",
         entered=date(2026, 8, 23), review=date(2026, 9, 20)):
    return RAO.OverrideRow(player_id=pid, player_name=name, expected_games_missed=miss,
                           source_url=url, entered_by="operator", entered_at=entered,
                           review_by=review)


def _frame(pid="00-0039918", games=13.6, status=None, name="Jordyn Tyson"):
    """A minimal projection frame. ⭐ `proj_status` is present and NULL by default so the
    disjointness clause is the only thing that can refuse a row — a frame with the column ABSENT
    would exercise a different branch and make the disjointness test vacuous."""
    return pd.DataFrame({"player_id": [pid], "player_name": [name],
                         "proj_games": [games], "proj_status": [status]})


# ══ RULE 1 — DISJOINTNESS: the formal path always wins ═══════════════════════════════════════════

@pytest.mark.parametrize("status", sorted(SP._INJURY_STATUS_GAMES_CAP))
def test_a_formally_tagged_player_is_never_touched_by_an_override(status):
    """The hard rule. Parametrized over the formal map ITSELF, not a hand-copied list, so a future
    status added to `_INJURY_STATUS_GAMES_CAP` is covered the day it is added.

    ⭐ THE FIXTURE IS BUILT SO ONLY DISJOINTNESS CAN REFUSE IT: the id matches, the row is
    unexpired, well-formed and un-duplicated, and the cap (9) is genuinely BELOW the player's games
    (13.6), so a working override WOULD move this row. The only reason it must not is the tag."""
    games, decisions = SP.reported_absence_games(_frame(status=status), [_row()])
    assert games[0] == pytest.approx(13.6), (
        f"a {status} player was moved by an override — the formal cap governs him, and applying "
        "both is a double discount")
    assert decisions[0]["reason"] == RAO.REASON_FORMAL_STATUS
    assert decisions[0]["applied"] is False


def test_the_same_override_DOES_move_the_player_when_no_formal_tag_is_present():
    """The other half of the pair, and it is what makes the clause above non-vacuous: the identical
    row, the identical frame, differing ONLY in `proj_status`, must move the number. Without this
    the disjointness test would pass just as well against an override mechanism that never worked."""
    games, decisions = SP.reported_absence_games(_frame(status=None), [_row()])
    assert games[0] == pytest.approx(9.0)
    assert decisions[0]["applied"] is True


def test_the_disjointness_rule_reads_the_formal_map_itself_not_a_copy_of_its_keys():
    """⭐ A DRIFT GUARD, not a behaviour guard. The whole design claim is that the two populations
    cannot separate because the disjointness dispatches on `_INJURY_STATUS_GAMES_CAP` — the very
    object the formal cap uses. If someone re-implements it against a literal set, the populations
    drift silently the next time a status is added. Proven behaviourally with a status injected at
    runtime, which a hand-copied literal could not know about."""
    injected = dict(SP._INJURY_STATUS_GAMES_CAP)
    injected["FAKE_NEW_STATUS"] = 5.0
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(SP, "_INJURY_STATUS_GAMES_CAP", injected)
        games, decisions = SP.reported_absence_games(_frame(status="FAKE_NEW_STATUS"), [_row()])
    assert games[0] == pytest.approx(13.6), (
        "a status added to the formal map was not respected by the disjointness rule — it is "
        "reading a COPY of the keys, so the two populations will drift")
    assert decisions[0]["reason"] == RAO.REASON_FORMAL_STATUS


# ══ RULE 2 — CAP-ONLY and MONOTONE ═══════════════════════════════════════════════════════════════

def test_an_override_can_never_raise_expected_games():
    """Cap-only. The player already sits at 4.0 games (say the NF-D11 return prior cut him); an
    override asserting he misses 8 (ceiling 9) must leave him at 4.0, NOT lift him to 9.

    ⭐ Note the fixture: everything else about the row is valid and the player is un-tagged, so the
    monotone rule is the only thing that can produce this outcome."""
    games, decisions = SP.reported_absence_games(_frame(games=4.0), [_row(miss=8)])
    assert games[0] == pytest.approx(4.0), "an override raised availability — it is not cap-only"
    assert decisions[0]["applied"] is True
    assert decisions[0]["inert"] is True, (
        "a cap that changed nothing must be reported INERT — otherwise it is indistinguishable "
        "from a working discount in the build log")


def test_the_cap_is_a_hard_min_not_a_blend():
    """The formal path blends 0.7 toward an EMPIRICAL level; this path does not, because the number
    IS the operator's stated expectation and blending it would silently overrule the judgment.
    A blend of 0.7 would land on 10.38, not 9.0 — the assertion separates the two."""
    games, _ = SP.reported_absence_games(_frame(games=13.6), [_row(miss=8)])
    assert games[0] == pytest.approx(17.0 - 8), "the reported-absence cap is not a hard MIN"


def test_the_three_availability_caps_compose_monotonically():
    """Property check over the composition, not one example: applying an override after any prior
    availability step can only ever move games DOWN or leave them alone, for every starting level."""
    for start in (0.5, 1.0, 4.0, 8.9, 9.0, 9.1, 13.6, 17.0):
        games, _ = SP.reported_absence_games(_frame(games=start), [_row(miss=8)])
        assert games[0] <= start + 1e-9, f"games rose from {start} to {games[0]}"


# ══ RULE 3 — the join is NORMALISED on both ends and verifiable BY NAME ══════════════════════════

def test_a_whitespace_padded_board_id_still_receives_its_override():
    """The NF-C9 defect, on this path. 275 of 2,501 live feed ids carried a LEADING SPACE; an exact
    match dropped them and the miss classified as 'this player is not on the board'. Both ends of
    this join normalise, so a padded board id still matches a clean override id."""
    games, decisions = SP.reported_absence_games(_frame(pid=" 00-0039918"), [_row()])
    assert games[0] == pytest.approx(9.0), (
        "a whitespace-padded board id did not match its override — the join normalises only one "
        "end, which makes correctness a property of the caller")
    assert decisions[0]["applied"] is True


def test_an_override_matching_no_board_row_is_REPORTED_not_silently_dropped():
    """⭐ THE FAILURE THAT LOOKS LIKE SUCCESS. A wrong id and a genuine absence render identically
    on every surface (no chip, no discount), so the only way an operator learns their id was wrong
    is if the build says so. The decision must name the row AND tell them how to check it."""
    games, decisions = SP.reported_absence_games(_frame(pid="00-0000001"), [_row()])
    assert games[0] == pytest.approx(13.6)
    assert len(decisions) == 1, "an unmatched override produced no decision at all — it vanished"
    assert decisions[0]["reason"] == RAO.REASON_UNMATCHED
    assert "name" in decisions[0]["detail"].lower(), (
        "the unmatched message must point the operator at verifying BY NAME — the id is the key "
        "under test and cannot verify itself")


def test_the_override_row_carries_a_name_so_the_join_is_verifiable_by_something_else():
    assert "player_name" in RAO._REQUIRED_FIELDS, (
        "player_name is what makes the join checkable by a key other than the one under test")


# ══ RULE 4 — review_by expiry: a stale judgment dies LOUDLY ══════════════════════════════════════

def _write(tmp_path, rows, season=2026):
    body = ["schema_version: 1", f"season: {season}", "overrides:"]
    for r in rows:
        body.append("  - " + "\n    ".join(f"{k}: {v}" for k, v in r.items()))
    p = tmp_path / "ov.yaml"
    p.write_text("\n".join(body) + "\n")
    return p


_GOOD = {"player_id": '"00-0039918"', "player_name": '"Jordyn Tyson"',
         "expected_games_missed": "8", "source_url": '"https://example.com/r"',
         "entered_by": '"operator"', "entered_at": '"2026-08-23"', "review_by": '"2026-09-20"'}


def test_a_row_past_its_review_by_stops_applying_and_says_so(tmp_path):
    """⭐ THE FIXTURE IS OTHERWISE PERFECT — a valid, unique, well-formed row with a real URL — so
    expiry is the ONLY clause that can reject it. That is what stops this test passing for the
    wrong reason if the expiry check were deleted."""
    p = _write(tmp_path, [_GOOD])
    fresh = RAO.load_overrides(p, as_of=date(2026, 9, 19), season=2026)
    assert len(fresh.rows) == 1, "the fixture must be applicable the day BEFORE review_by, or the "\
                                 "expiry assertion below proves nothing"
    stale = RAO.load_overrides(p, as_of=date(2026, 9, 21), season=2026)
    assert stale.rows == [], "an expired judgment was still applied"
    assert [j.reason for j in stale.rejected] == [RAO.REASON_EXPIRED]
    assert "re-source" in stale.rejected[0].detail or "delete" in stale.rejected[0].detail


def test_expiry_is_measured_against_an_injected_date_not_a_hidden_clock(tmp_path):
    """A hidden `date.today()` inside the comparison would make the boundary untestable and the
    build unreproducible. Same day as `review_by` still applies (the row expires AFTER it)."""
    p = _write(tmp_path, [_GOOD])
    assert len(RAO.load_overrides(p, as_of=date(2026, 9, 20), season=2026).rows) == 1


# ══ THE LOAD CONTRACT — every row accounted for, every ambiguity fails toward doing nothing ══════

def test_a_row_with_no_source_url_is_rejected(tmp_path):
    bad = dict(_GOOD); bad.pop("source_url")
    r = RAO.load_overrides(_write(tmp_path, [bad]), as_of=date(2026, 8, 23), season=2026)
    assert r.rows == [] and r.rejected[0].reason == RAO.REASON_MALFORMED
    assert "source_url" in r.rejected[0].detail


def test_a_source_url_that_is_not_a_link_is_rejected(tmp_path):
    bad = dict(_GOOD, source_url='"beat writer on twitter"')
    r = RAO.load_overrides(_write(tmp_path, [bad]), as_of=date(2026, 8, 23), season=2026)
    assert r.rows == [], "a citation nobody can follow is not a citation"


@pytest.mark.parametrize("games", ["0", "18", "3.5", "true", '"eight"'])
def test_an_out_of_range_or_non_integer_games_count_is_rejected(tmp_path, games):
    """`0` is rejected on purpose (delete the row instead of encoding a no-op) and `true` because
    a bool is an int in Python and would silently become 1 game."""
    bad = dict(_GOOD, expected_games_missed=games)
    r = RAO.load_overrides(_write(tmp_path, [bad]), as_of=date(2026, 8, 23), season=2026)
    assert r.rows == [], f"expected_games_missed={games} was accepted"


def test_two_rows_for_one_player_reject_the_WHOLE_GROUP(tmp_path):
    """Silently choosing between them (first? harshest? newest?) would apply a judgment nobody
    made. Failing toward doing nothing keeps the board explicable."""
    r = RAO.load_overrides(_write(tmp_path, [_GOOD, dict(_GOOD, expected_games_missed="4")]),
                           as_of=date(2026, 8, 23), season=2026)
    assert r.rows == [], "one of two conflicting rows was silently chosen"
    assert r.rejected[0].reason == RAO.REASON_DUPLICATE


def test_an_unreadable_file_is_a_DIFFERENT_state_from_an_empty_one(tmp_path):
    """NF-FRESH2's absent-vs-null, on the load side. If a broken file reported as 'no rows' it
    would render as 'there are no reported absences', which is a claim we did not make."""
    p = tmp_path / "broken.yaml"
    p.write_text("overrides: [ this is not: valid: yaml: at all\n")
    broken = RAO.load_overrides(p, as_of=date(2026, 8, 23), season=2026)
    assert broken.readable is False
    empty = RAO.load_overrides(tmp_path / "does_not_exist.yaml", as_of=date(2026, 8, 23))
    assert empty.readable is True and empty.rows == []


def test_a_malformed_row_does_not_take_a_valid_sibling_down_with_it(tmp_path):
    bad = dict(_GOOD, player_id='"00-0000002"', player_name='"Other"'); bad.pop("entered_by")
    r = RAO.load_overrides(_write(tmp_path, [_GOOD, bad]), as_of=date(2026, 8, 23), season=2026)
    assert len(r.rows) == 1 and len(r.rejected) == 1


def test_every_rejection_carries_a_reason_and_reaches_the_build_log(tmp_path):
    """A curated file whose rows silently do nothing looks exactly like one that works."""
    bad = dict(_GOOD, player_id='"00-0000009"', source_url='"nope"')
    r = RAO.load_overrides(_write(tmp_path, [_GOOD, bad]), as_of=date(2026, 8, 23), season=2026)
    lines = "\n".join(RAO.format_load_log(r))
    assert "APPLY" in lines and "IGNORE" in lines
    assert "00-0000009" in lines, "the rejected row is not named in the build log"


# ══ THE LEAKAGE GATE — a 2026 judgment must never reach a historical fold ════════════════════════

def test_the_season_gate_yields_nothing_for_a_different_season(tmp_path):
    """The same assembly path builds the live board AND the historical walk-forward band panel. A
    human who has seen how a season went, editing that season's projection, is an outright leak."""
    p = _write(tmp_path, [_GOOD], season=2026)
    assert len(RAO.load_overrides(p, as_of=date(2026, 8, 23), season=2026).rows) == 1
    assert RAO.load_overrides(p, as_of=date(2026, 8, 23), season=2019).rows == [], (
        "a 2026 operator judgment reached a 2019 fold")


def test_the_historical_panel_path_never_passes_overrides():
    """Structural, not behavioural: `build_veteran_panel_season` builds the historical panel through
    the SAME function as the live board, and the only thing keeping the judgments out of it is that
    it does not pass them. Pinned so a future edit cannot quietly add them."""
    src = (_FANTASY / "run_season_projection.py").read_text()
    body = src.split("def build_veteran_panel_season", 1)[1].split("\ndef ", 1)[0]
    assert "build_veteran_projection(" in body, "anchor moved — this guard is scanning nothing"
    assert "reported_absence" not in body, (
        "the historical band panel now receives reported-absence overrides — that is a leak")


# ══ THE PAYLOAD STAMP — additive, absent-vs-null, and never ahead of what was applied ════════════

def _board_row(**kw):
    base = {"player_id": "00-0039918", "player_name": "Jordyn Tyson", "position": "WR",
            "team_id": "ARI", "proj_games": 9.0, "overall_rank": 1, "positional_rank": 1,
            "is_rookie": False, "league_points": 100.0,
            "reported_absence_source_url": None, "reported_absence_entered_at": None,
            "reported_absence_games_missed": None}
    base.update(kw)
    return base


def test_an_un_overridden_row_carries_NO_reportedAbsence_KEY_AT_ALL():
    """Absent, not null. An absent key means 'no operator judgment touched this number', which is
    the true and normal state for ~870 of 870 rows, and it is what makes an un-overridden player
    byte-identical to the pre-story board."""
    from quant_sports_intel_models.football.nfl.fantasy import export_draft_board_json as E
    rec = E.board_records(pd.DataFrame([_board_row()]))[0]
    assert "reportedAbsence" not in rec


def test_an_overridden_row_carries_the_source_and_the_date_and_nothing_else():
    from quant_sports_intel_models.football.nfl.fantasy import export_draft_board_json as E
    rec = E.board_records(pd.DataFrame([_board_row(
        reported_absence_source_url="https://example.com/r",
        reported_absence_entered_at="2026-08-23")]))[0]
    assert rec["reportedAbsence"] == {"sourceUrl": "https://example.com/r",
                                      "enteredAt": "2026-08-23"}
    assert set(rec["reportedAbsence"]) == {"sourceUrl", "enteredAt"}, (
        "the stamp grew a field — it must carry provenance only, never a forecast, a diagnosis or "
        "a return date")


def test_the_stamp_is_written_from_what_was_APPLIED_not_from_the_override_file():
    """⭐ NF-C0e — a declaration must not outrun its production. A player who has since acquired a
    formal tag is refused by the disjointness rule; his projection is untouched, so nothing may
    stamp him as carrying a reported-absence cap. This is exactly what re-reading the YAML at
    export time would get wrong, because the exporter cannot see `proj_status`."""
    src = (_FANTASY / "export_draft_board_json.py").read_text()
    body = src.split("def _reported_absence(", 1)[1].split("\ndef ", 1)[0]
    # ⚠️ STRIP THE DOCSTRING FIRST. It EXPLAINS why the file must not be re-read, so it contains
    # the very words the scan forbids — leaving it in makes the guard fire on the comment that
    # documents the rule, and the cheapest way to pass would be to delete the explanation
    # (INC-38: prose must neither satisfy nor violate a source scan).
    code = re.sub(r'"""[\s\S]*?"""', "", body, count=1)
    assert "reported_absence_source_url" in code, "anchor moved — this guard scans nothing"
    assert "load_overrides" not in code and "yaml" not in code.lower(), (
        "the export stamp reads the overrides FILE — it must read the built board's own columns, "
        "or it will disclose caps the disjointness rule refused")


def test_the_provenance_columns_survive_the_emitted_schema():
    """`OUTPUT_COLS` is a strict whitelist; a column absent from it is dropped on write with no
    error (the E9.41 silently-dropped-field class, on the parquet side).

    ⭐ THE COLUMN NAMES ARE WRITTEN OUT LITERALLY HERE, and that is the whole point. The first cut
    looped over `SP.REPORTED_ABSENCE_COLS` and checked membership in `OUTPUT_COLS` — but
    `OUTPUT_COLS` is BUILT from that same constant (`*_SP.REPORTED_ABSENCE_COLS`), so shrinking the
    constant shrank both sides and the assertion could not fail for any input. Its own RED proof
    caught it: the deliberate break stayed GREEN. A test that reads a value back out of the
    structure the code built from it is a restatement of the code, not a test of it (NF-C0e).

    The literals are also what the CONSUMER reads: `export_draft_board_json._reported_absence`
    looks up these exact strings on the built board."""
    from quant_sports_intel_models.football.nfl.fantasy import run_season_projection as R
    for c in ("reported_absence_source_url", "reported_absence_entered_at",
              "reported_absence_games_missed"):
        assert c in SP.REPORTED_ABSENCE_COLS, f"{c} is no longer stamped by the projection"
        assert c in R.OUTPUT_COLS, f"{c} is stamped by the projection and then dropped on write"
    stamp = (_FANTASY / "export_draft_board_json.py").read_text()
    for c in ("reported_absence_source_url", "reported_absence_entered_at"):
        assert c in stamp, f"the exporter no longer reads {c} — the stamp and the schema disagree"


def test_the_provenance_fields_are_public_because_nothing_here_is_scorable():
    """NF-EPIC 1's rule is mechanical: if it goes in `STAT_FIELD` it is paid; a display/provenance
    value with no scoring weight stays public, like `g` and `adp`. A source URL and a date cannot
    be multiplied by a league weight, so the free board keeps its provenance — withholding the
    CITATION while showing the capped number would be the dishonest half of the split."""
    from app.backend.services import projection_fields as PF
    assert "reportedAbsence" not in PF.PAID_PLAYER_FIELDS
    row = {"id": "x", "g": 9.0, "reportedAbsence": {"sourceUrl": "https://e/x",
                                                    "enteredAt": "2026-08-23"}}
    assert "reportedAbsence" in PF.public_player_row(row), (
        "the provenance stamp is stripped from the public payload — the reader sees a discounted "
        "number with no way to learn why")


# ══ HONESTY — no accuracy or improvement claim may attach to an operator judgment ════════════════

# ⚠️ THESE ARE CLAIM PHRASES, NOT SINGLE WORDS, and that is deliberate. A bare "proven" fires on
# "RED-proven", which is this repo's word for a guard that was shown to fail on broken source —
# a testing fact, not an accuracy claim — and a bare "validated" fires on every honest sentence
# about a validated INTERVAL. Forbidding an ambiguous word makes the cheapest way to pass be to
# stop using the repo's own vocabulary, so the predicate has to be the claim itself.
_FORBIDDEN = ("more accurate", "improves the projection", "improved accuracy", "better projection",
              "outperform", "beats", "proven accuracy", "proven improvement", "backtested",
              "expected to return", "will return", "will miss", "diagnosis", "recovery timeline")


def test_no_module_or_data_file_in_this_story_claims_accuracy_or_forecasts_a_return():
    """⛔ The mechanism is a human reading a report. Anything that reads as a projection improvement
    or as a medical/return forecast is out of bounds, in code comments as much as in UI copy — a
    false premise in a comment is worse than in a doc, because the next reader builds on it."""
    for rel in ("reported_absence_overrides.py", "data/reported_absence_overrides.yaml"):
        text = (_FANTASY / rel).read_text().lower()
        for phrase in _FORBIDDEN:
            # ⚠️ NEGATION-AWARE (NF-C6P3): our own honest copy says "never backtested" and "is NOT
            # a model", and a bare substring scan would fire on exactly the sentences that make
            # this file honest — making the cheapest way to pass the guard to DELETE them.
            # ⚠️ WORD-BOUNDARY, never a raw substring: a bare `in` scan fires on
            # 'proven' ⊂ 'provenance' and this file is ABOUT provenance, so the cheapest way to
            # pass would be to stop calling it that (the NF-W7 'temp' ⊂ 'attempt' family).
            for m in re.finditer(rf"\b{re.escape(phrase)}\b", text):
                before = text[max(0, m.start() - 40):m.start()]
                assert re.search(r"\b(no|not|never|nothing|cannot|must not|neither)\b", before), (
                    f"{rel} contains an unnegated claim {phrase!r} — an operator judgment carries "
                    "no accuracy claim")


def test_the_negation_scan_can_actually_fire():
    """⭐ THE ANTI-VACUITY CHECK for the clause above. A negation-aware scan that never fires on
    anything is not a guard, and this one is scanning files we wrote to be honest — so it must be
    proven to reject a genuine overclaim before its silence means anything."""
    text = "this override makes the projection more accurate for injured players"
    fired = [p for p in _FORBIDDEN
             for m in re.finditer(rf"\b{re.escape(p)}\b", text)
             if not re.search(r"\b(no|not|never|nothing|cannot|must not|neither)\b",
                              text[max(0, m.start() - 40):m.start()])]
    assert fired, "the honesty scan cannot detect a plain overclaim — it is vacuous"


def test_the_honesty_scan_is_word_bounded_so_provenance_does_not_read_as_a_claim():
    """The other side of the same coin. `proven` is on the forbidden list and `provenance` is the
    word this whole mechanism is built around — a raw substring scan makes the honest vocabulary
    unusable, which is how an over-eager guard ends up deleting the copy that makes a surface
    honest (NF-C6P3's negation-blind scan, one class over)."""
    text = "an operator judgment with provenance attached"
    fired = [p for p in _FORBIDDEN if re.search(rf"\b{re.escape(p)}\b", text)]
    assert not fired, f"the honesty scan false-fires on honest vocabulary: {fired}"


def test_the_shipped_overrides_file_is_valid_and_declares_its_season():
    """The committed file must parse and be season-gated. It ships EMPTY by design — the mechanism
    is inert until an operator confirms rows — so an empty `rows` here is a PASS, but an
    UNREADABLE file is not (the two are different facts)."""
    r = RAO.load_overrides(RAO.DEFAULT_OVERRIDES_PATH, as_of=date(2026, 8, 23))
    assert r.readable is True, "the committed overrides file does not parse"
    assert r.season == 2026, "the committed file does not declare its season — the leakage gate is off"
    assert r.rejected == [], f"the committed file has rejected rows: {r.rejected}"


def test_the_whole_step_is_a_no_op_when_nothing_is_curated():
    """The rollback state, asserted rather than assumed: with no rows the frame is untouched."""
    df = _frame()
    games, decisions = SP.reported_absence_games(df, [])
    assert np.allclose(games, df["proj_games"].to_numpy()) and decisions == []
