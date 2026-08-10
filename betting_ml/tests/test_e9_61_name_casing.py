"""E9.61 item 4 — the ONE name-casing authority, and the gate that makes it safe.

Its own file, per the anti-coupling rule: `test_track_record_export.py` and
`test_fantasy_board_export.py` each own their exporter's behaviour, and a new cross-cutting
requirement bolted onto either of them would fail for a reason that story never claimed.

⭐ WHAT THESE PIN, AND WHY EACH ONE EXISTS. Every case below is anchored on a LIVE-MEASURED pair
from the 2026 payload (858 players / 745 joined to the roster), not on an invented example — the
whole reason this story exists is that the previous diagnosis was reasoned rather than measured and
came out backwards ("MacK Hollins is carried in the data"; we were producing it).

The `_LIVE_*` tables below ARE the measurement, recorded so a future reader can see what the fix was
sized against without re-running an S3 join. Offline/pure: no lake read, no S3, no network.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from quant_sports_intel_models.football.nfl.fantasy import player_naming as PN

_SRC = Path(__file__).resolve().parents[2] / "quant_sports_intel_models/football/nfl/fantasy"
_BOARD = _SRC / "export_draft_board_json.py"
_TRACK = _SRC / "export_track_record_json.py"
_NAMING = _SRC / "player_naming.py"


# ── the measurement (live 2026 payload, joined to the nflverse roster by gsis id) ────────────────

#: Names the LIVE board serves wrongly, with the roster's spelling. Pure case changes, every one.
#: 30 veterans (source ALL-CAPS, unrecoverable by rule) + 3 rookies the exporter's unconditional
#: `.title()` DAMAGED from an already-correct source.
_LIVE_CASE_DEFECTS = {
    "Aj Barner": "AJ Barner",
    "Ceedee Lamb": "CeeDee Lamb",
    "Deandre Hopkins": "DeAndre Hopkins",
    "Devonta Smith": "DeVonta Smith",
    "Dj Moore": "DJ Moore",
    "Dk Metcalf": "DK Metcalf",
    "Dont'E Thornton Jr.": "Dont'e Thornton Jr.",
    "Isaac Teslaa": "Isaac TeSlaa",
    "John Fitzpatrick": "John FitzPatrick",
    "Juju Smith-Schuster": "JuJu Smith-Schuster",
    "Ka'Imi Fairbairn": "Ka'imi Fairbairn",
    "Kc Concepcion": "KC Concepcion",          # rookie — the source had it RIGHT and we broke it
    "MacK Hollins": "Mack Hollins",            # the headline; produced by our own `Mac` rule
    "Marshawn Lloyd": "MarShawn Lloyd",
    "Sam Laporta": "Sam LaPorta",
    "Treveyon Henderson": "TreVeyon Henderson",
}

#: Roster disagreements that are NOT casing and MUST be refused. Measured: 32 of the 62 live
#: disagreements. Suffixes disagree in BOTH directions, so "trust the roster" is not a shortcut.
_LIVE_NON_CASE_DISAGREEMENTS = [
    ("Travis Etienne Jr.", "Travis Etienne"),    # we carry the suffix, roster does not
    ("Odell Beckham", "Odell Beckham Jr."),      # ...and the other way round
    ("James Cook III", "James Cook"),
    ("Lew Nichols", "Lew Nichols III"),
    ("Hollywood Brown", "Marquise Brown"),       # the market's name vs the legal one
    ("Drew Ogletree", "Andrew Ogletree"),
    ("Joshua Palmer", "Josh Palmer"),
    ("Scotty Miller", "Scott Miller"),
]

#: ALL-CAPS source spellings, from the seven published seasons.
_LIVE_SHOUTING = {
    "MACK HOLLINS": "Mack Hollins",
    "CHRISTIAN MCCAFFREY": "Christian McCaffrey",
    "JAMES COOK III": "James Cook III",
    "JA'MARR CHASE": "Ja'Marr Chase",
    "AMON-RA ST. BROWN": "Amon-Ra St. Brown",
    "A.J. BROWN": "A.J. Brown",
}


# ── 1. the safety property: this module may change CASE and nothing else ─────────────────────────


@pytest.mark.parametrize("ours,roster", _LIVE_NON_CASE_DISAGREEMENTS)
def test_a_roster_disagreement_that_is_more_than_case_is_refused(ours, roster):
    """⭐ THE CLAUSE THE WHOLE DESIGN RESTS ON.

    The obvious reading of "carry nflverse's display name" is to repoint the name column at the
    roster. Measured, that is a REGRESSION on 32 live players: it drops the "Jr." a manager uses to
    tell two players apart, and replaces "Hollywood Brown" with a legal name nobody drafts by.
    """
    assert PN.reconcile_casing(ours, roster) == ours


@pytest.mark.parametrize("ours,roster", list(_LIVE_CASE_DEFECTS.items()))
def test_the_output_always_casefolds_equal_to_the_input(ours, roster):
    """The invariant stated as an invariant, over the pairs it is meant to ACT on — so this cannot
    pass merely because nothing happened. (Its partner above covers the refusal side.)"""
    out = PN.reconcile_casing(ours, roster)
    assert out == roster                        # it did act
    assert out.casefold() == ours.casefold()    # ...and only on case


def test_the_invariant_holds_even_for_an_authority_that_is_wildly_wrong():
    """A defensive case, not a measured one: whatever the roster says, an identity-changing value
    can never come back. If this ever fails, the casefold gate has been removed or inverted."""
    for bogus in ("", "   ", "Someone Else Entirely", "Mack Hollins Jr.", "MACK"):
        assert PN.reconcile_casing("MacK Hollins", bogus) == "MacK Hollins"


# ── 2. the two producer bugs, pinned at the function that produced them ──────────────────────────


def test_the_mac_rule_no_longer_invents_an_internal_capital():
    """THE HEADLINE DEFECT, at its source. `_titlecase` looped over `("Mc", "Mac")` upper-casing the
    next letter, so MACK -> "MacK". Across all seven seasons the MAC* names are AUSTIN MACK / MAC
    JONES / MACK HOLLINS / MARLON MACK / Alizé Mack — not one wants the capital."""
    assert PN.de_shout("MACK HOLLINS") == "Mack Hollins"
    assert PN.de_shout("MARLON MACK") == "Marlon Mack"
    assert PN.de_shout("AUSTIN MACK") == "Austin Mack"


def test_the_mc_rule_survives_because_it_is_the_one_that_earns_its_keep():
    """The other side of dropping `Mac`: all 37 Mc-prefixed all-caps names DO want the capital, so
    removing both rules would trade one defect for thirty-seven."""
    for shout, want in [
        ("CHRISTIAN MCCAFFREY", "Christian McCaffrey"),
        ("TERRY MCLAURIN", "Terry McLaurin"),
        ("LADD MCCONKEY", "Ladd McConkey"),
        ("TREY MCBRIDE", "Trey McBride"),
    ]:
        assert PN.de_shout(shout) == want


def test_a_name_that_is_not_shouting_is_left_alone():
    """The second live defect: 81 of 784 rows arrive from the clean rookie pipeline and the exporter
    ran `.title()` over ALL of them, publishing "Kc Concepcion" from a correct `KC Concepcion`.

    A de-shouter's contract is only defined on shouting input."""
    for clean in ("KC Concepcion", "CJ Daniels", "CJ Williams", "Dont'e Thornton", "Ashton Jeanty",
                  "MacKenzie Morgan", "LeQuint Allen", "Ja'Marr Chase"):
        assert PN.display_name(clean) == clean


@pytest.mark.parametrize("shout,want", list(_LIVE_SHOUTING.items()))
def test_a_shouting_name_is_de_shouted(shout, want):
    assert PN.display_name(shout) == want


def test_a_unit_name_is_not_a_person():
    """NF1.6 — "DEN D/ST" is a team code plus a unit label; `.title()` renders it "Den D/St"."""
    for unit in ("DEN D/ST", "KC D/ST", "SF DST"):
        assert PN.display_name(unit) == unit


# ── 3. end to end, over the live defect table ────────────────────────────────────────────────────


@pytest.mark.parametrize("served,roster", list(_LIVE_CASE_DEFECTS.items()))
def test_every_live_case_defect_is_repaired_when_the_authority_knows(served, roster):
    """The full round trip on real pairs: whichever spelling the source ships — the ALL-CAPS one or
    the already-damaged one we published — both land on the roster's answer."""
    assert PN.display_name(served.upper(), roster) == roster
    assert PN.display_name(served, roster) == roster


def test_the_frozen_fallback_keeps_the_pre_authority_answer_when_the_roster_is_unreachable():
    """⭐ WHY THE OLD HAND MAP WAS KEPT RATHER THAN DELETED.

    Deleting it looked like the clean end state and was wrong: `roster_casing_authority` is a
    best-effort S3 read, and with no map an unreachable roster does not merely fail to IMPROVE these
    names — it makes them WORSE than the pre-E9.61 behaviour, because the hand map used to catch
    them. A best-effort authority whose absence silently regresses the output is the repo's
    "graceful fallback hides a defect" shape.

    Two of the old suite's tests caught this when the map was first removed. A test that passed
    before a refactor and fails after it is reporting lost coverage, not obstructing the refactor.
    """
    assert PN.display_name("DEVONTA SMITH") == "DeVonta Smith"      # no authority passed
    assert PN.display_name("CEEDEE LAMB") == "CeeDee Lamb"
    assert PN.display_name("SAM LAPORTA") == "Sam LaPorta"


def test_the_authority_wins_over_the_frozen_fallback():
    """The map is a backstop, not a competing source of truth — otherwise a corrected roster row
    could never propagate, which is exactly the staleness the derived authority exists to end."""
    assert PN.display_name("DEVONTA SMITH", "Devonta Smith") == "Devonta Smith"


def test_a_repair_that_changes_characters_is_not_a_casing_repair():
    """`DEVON ACHANE` -> `De'Von Achane` ADDS an apostrophe, so the casefold gate refuses it — by
    the same rule that protects "Hollywood Brown". It stays an explicit, hand-verified entry, and it
    is the ONE of the old map's nine names the roster cannot supply."""
    assert PN.display_name("DEVON ACHANE") == "De'Von Achane"
    assert PN.reconcile_casing("Devon Achane", "De'Von Achane") == "Devon Achane"


# ── 4. wiring: the renderers must actually CONSULT the authority ─────────────────────────────────
#
# The NF-C0e "wired ≠ invoked" lesson. A shared module that no renderer calls is a module that
# changes nothing — and the failure is silent, because every unit test above still passes.


def _call_sites(src: str, fn: str) -> list[ast.Call]:
    """CALL sites of `fn` — parsed, not grepped.

    ⚠️ BOTH cheaper forms were tried and BOTH were vacuous, caught by the red proof:
      * `grep -c "fn"` counts a mention in a docstring or a dict key naming the function
        (the DSR-CONV lesson, which shipped a vacuous guard exactly this way);
      * `re.search(r"fn\\([^)]*\\bcasing\\b", src)` matches the multi-line `def fn(...casing...)`
        SIGNATURE, so deleting the argument at every real call site left the guard green.
    An AST walk cannot confuse a definition with a call.
    """
    return [
        n for n in ast.walk(ast.parse(src))
        if isinstance(n, ast.Call)
        and (getattr(n.func, "attr", None) == fn or getattr(n.func, "id", None) == fn)
    ]


def _passes_casing(call: ast.Call) -> bool:
    """Is `casing` handed to this call — positionally or by keyword?"""
    names = [a.id for a in call.args if isinstance(a, ast.Name)]
    names += [k.value.id for k in call.keywords if isinstance(k.value, ast.Name)]
    return "casing" in names


def test_both_renderers_route_through_the_shared_authority():
    """Two exporters render a player name — the board (Rankings / Projections / Player Search) and
    the track record. Before E9.61 they carried DIFFERENT rule passes, which is how one of them
    served a defect the other's guard would have caught."""
    for path in (_BOARD, _TRACK):
        src = path.read_text()
        assert _call_sites(src, "display_name"), f"{path.name} no longer calls the shared authority"


@pytest.mark.parametrize("builder", ["board_records", "projection_records"])
def test_the_board_export_passes_the_authority_to_both_record_builders(builder):
    """The specific wiring that carries the fix to the live surfaces. `projection_records` feeds
    Projections + Player Search; `board_records` feeds Rankings + every league board. A fix wired
    into one and not the other is the shape of half this repo's landmines — so they are two
    parametrized cases, not one assertion that either could satisfy."""
    src = _BOARD.read_text()
    assert re.search(r"casing\s*=\s*PN\.roster_casing_authority\(", src), \
        "main() no longer resolves the casing authority"
    calls = _call_sites(src, builder)
    assert calls, f"{builder} is never called — this guard would otherwise pass on nothing"
    assert all(_passes_casing(c) for c in calls), f"a {builder} call does not receive the authority"


def test_the_track_record_export_resolves_the_authority_too():
    src = _TRACK.read_text()
    assert re.search(r"casing\s*=\s*PN\.roster_casing_authority\(", src)
    calls = _call_sites(src, "season_records")
    assert calls, "season_records is never called"
    assert all(_passes_casing(c) for c in calls), "season_records does not receive the authority"


def test_the_authority_is_keyed_on_the_id_not_the_name(monkeypatch):
    """A name-keyed authority would have to guess the very casing it is being asked to supply, and
    would silently mis-resolve two players whose names differ only by a suffix.

    Asserted BEHAVIOURALLY against a stub connection: an earlier source-inspection version ("the
    string `gsis_id` appears in the function") passed happily with the SELECT re-keyed onto the
    name, because `gsis_id` still appeared in the WHERE clause. Substring presence is not structure.
    """
    import pandas as pd

    from quant_sports_intel_models.football.nfl.fantasy import export_draft_board_json as board

    captured: dict[str, str] = {}

    class _Rel:
        def df(self):
            return pd.DataFrame(
                [{"gsis_id": "00-0000001", "full_name": "CeeDee Lamb"},
                 {"gsis_id": "00-0000002", "full_name": "DJ Moore"}]
            )

    class _Con:
        def sql(self, q):
            captured["q"] = q
            return _Rel()

        def close(self):
            pass

    monkeypatch.setattr(board, "_lake_connection", lambda: _Con())
    PN.roster_casing_authority.cache_clear()
    try:
        out = PN.roster_casing_authority(1999)
    finally:
        PN.roster_casing_authority.cache_clear()

    assert out == {"00-0000001": "CeeDee Lamb", "00-0000002": "DJ Moore"}, \
        "the authority must be keyed on the gsis id, mapping to the roster's spelling"
    assert "gsis_id" in captured["q"] and "group by gsis_id" in captured["q"].lower()


def test_an_authority_read_that_fails_returns_empty_rather_than_raising(monkeypatch):
    """Best-effort by contract: the exporters must still produce a board when S3 is unreachable.
    Paired with the warning clause below — degrading is fine, degrading QUIETLY is not."""
    from quant_sports_intel_models.football.nfl.fantasy import export_draft_board_json as board

    def _boom():
        raise RuntimeError("s3 unreachable")

    monkeypatch.setattr(board, "_lake_connection", _boom)
    PN.roster_casing_authority.cache_clear()
    try:
        assert PN.roster_casing_authority(1998) == {}
    finally:
        PN.roster_casing_authority.cache_clear()


def test_an_unreachable_authority_is_reported_rather_than_silently_empty():
    """A best-effort read that returns `{}` on failure must SAY so — otherwise the board simply
    reverts to the old wrong names and the run still looks clean (NF1.7 (a): a check that did not
    run is not a pass)."""
    src = _NAMING.read_text()
    body = src[src.index("def roster_casing_authority"):]
    assert "log.warning" in body, "a failed roster read must warn, not fail silently"
    assert body.count("log.warning") >= 2, \
        "both failure modes need a warning: the read RAISING, and the read returning zero rows"


def test_the_board_export_reports_what_the_authority_did():
    """The count is the difference between "the authority ran" and "the authority worked". An S3
    failure shows up as a repaired count of zero plus an ALERT, not as a clean export."""
    src = _BOARD.read_text()
    assert "casing authority repaired" in src
    assert re.search(r"if casing and not repaired", src), \
        "an authority that repaired NOTHING on a populated board must alert"


# ── 5. the rule pass must not grow a second home ─────────────────────────────────────────────────


def test_the_board_exporter_no_longer_carries_its_own_rule_pass():
    """⭐ THE STRUCTURAL FIX, not just the symptom.

    "There is no rule that does this" was TRUE of the file the previous session grepped and FALSE of
    the one serving the defect. Two renderers of one field were two rule sets. This asserts the
    board exporter has no independent casing rules left to drift — the Mc/Mac loop, the suffix map
    and the `.title()` all live in `player_naming` now.
    """
    src = _BOARD.read_text()
    body = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))
    body = re.sub(r'"""(?:.|\n)*?"""', "", body)  # docstrings describe the history; they are not code
    for banned, why in [
        (".title()", "title-casing belongs to player_naming.de_shout"),
        ('"Mac"', "the Mac rule is measured to earn nothing and to break 'Mack'"),
        ("_NAME_SUFFIXES", "the suffix map belongs to player_naming"),
    ]:
        assert banned not in body, f"{_BOARD.name} grew its own casing rule again: {why}"


def test_the_track_record_exporter_no_longer_carries_its_own_rule_pass():
    src = _TRACK.read_text()
    body = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))
    body = re.sub(r'"""(?:.|\n)*?"""', "", body)
    for banned in (".title()", "_KNOWN_CASINGS", "_MISCASINGS"):
        assert banned not in body, f"{_TRACK.name} grew its own casing rule again: {banned}"


def test_the_frozen_fallback_map_is_not_quietly_growing():
    """It is a backstop for names the authority already agrees with, not a maintenance surface. A
    new entry means someone hand-patched a name the roster should have supplied — which is invisible
    to the other renderer and re-creates the per-draft-class burden this module ended."""
    assert len(PN._FALLBACK_CASINGS) == 8, (
        "the frozen fallback changed size — a NEW mis-cased name is the authority's job. If a roster "
        "row is genuinely wrong, report it upstream rather than patching it here."
    )
    assert len(PN._REPAIRS) == 1, (
        "_REPAIRS is for repairs that change CHARACTERS (De'Von Achane's apostrophe), never casing"
    )

