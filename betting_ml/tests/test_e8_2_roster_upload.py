"""Fast-gate tests for E8.2 — league-roster UPLOAD parsing and the board match.

The whole story rests on one fragile operation: a CBS roster grid concatenates every player a team
holds at a position into ONE cell with no delimiter, and we have to get them back out. So these
tests are pinned to the OPERATOR'S REAL 2026-07-31 EXPORT rather than to hand-written strings —
fixtures inherit the author's assumptions about the format, and a second real payload is what finds
what a fixture cannot (the NF-C0 Sleeper lesson, one story over).

Four things have to hold:

1. **THE TOKENIZER CANNOT LOSE OR INVENT A CHARACTER.** Re-joining a cell's parsed players must
   reproduce it byte for byte, on every cell of the real export. This is the invariant that makes a
   silently-dropped rostered player impossible — and a dropped rostered player is the one failure
   that matters, because it reads on the board as "available".

2. **THE NAIVE SPLIT IS PROVEN WRONG.** `TestTheNaiveSplitWouldBeWrong` runs the obvious
   `[a-z][A-Z]` rule against the real export and asserts it BREAKS. Without that, nothing
   distinguishes "the parser is careful" from "the input was easy", and the test suite would stay
   green if the guard were deleted.

3. **AN AMBIGUOUS NAME IS NEVER GUESSED**, and nothing is silently dropped: every entry lands in
   exactly one reported tier.

4. **THE OVERLAY KEYS ON THE BOARD'S UNIQUE COLUMN.** `rank` is unique on the live board;
   `mlbamId` is absent on 9 rows and `(name, org)` is not unique. Keying on the id would leave
   those rows permanently and wrongly "available".
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

import pytest

from app.backend.services.mlb_roster import (
    RosterEntry,
    RosterUploadError,
    match_roster,
    parse_roster_upload,
    split_grid_cell,
)
from app.backend.services.mlb_roster.board_match import (
    AMBIGUOUS,
    EXACT,
    MANUAL,
    MISSING_FROM_BOARD,
    UNRESOLVED,
    VARIANT,
    name_key,
)

FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "quant_sports_intel_models/baseball/edge_program/fixtures"
    / "e8_2_cbs_roster_grid_example_20260731.csv"
)


@pytest.fixture(scope="module")
def grid_text() -> str:
    return FIXTURE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def parsed(grid_text: str):
    return parse_roster_upload(grid_text)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1 — the tokenizer, against the real export
# ══════════════════════════════════════════════════════════════════════════════════════════════


class TestTheRealExport:
    def test_the_fixture_is_the_operators_real_export(self, grid_text: str):
        """Guards the fixture itself: these are the hard cases the parser is designed around."""
        for marker in ("J.P. Crawford", "C.J. Kayfus", "I Kiner-Falefa", "V Mesa Jr.",
                       "L Wade Jr.", "D Lynch IV", "E De Los Santos", "Z McKinstry"):
            assert marker in grid_text, f"the fixture no longer contains {marker!r}"

    def test_every_cell_round_trips(self, grid_text: str):
        """⭐ THE LOAD-BEARING INVARIANT: the cuts PARTITION the cell, so nothing can vanish."""
        rows = list(csv.reader(grid_text.splitlines()))
        checked = 0
        for row in rows[1:]:
            for cell in row[1:]:
                players = split_grid_cell(cell)
                assert "".join(players) == cell.strip(), f"round-trip lost characters in {cell!r}"
                checked += 1
        assert checked > 100, "the fixture shrank — this test is no longer exercising the grid"

    def test_the_whole_grid_parses_to_the_expected_player_counts(self, parsed):
        """Per-team counts, hand-checked against the export. A tokenizer change that merges or
        splits one player anywhere moves exactly one of these numbers."""
        counts = {}
        for entry in parsed.entries:
            counts[entry.team] = counts.get(entry.team, 0) + 1
        assert counts == {
            "Antonio Picante": 36,
            "Guelah Papyrus": 38,
            "KCStat": 39,
            "Less Than Jake": 35,
            "New York Other Ones": 32,
            "PACER’S": 34,
            "Pesky": 40,
            "phantoms": 37,
            "Red Paps": 39,
            "Sea Monkeys": 39,
            "Statcast and Chill": 33,
            "Texas Chaos": 40,
        }
        assert len(parsed.entries) == 442
        assert len(parsed.teams) == 12

    @pytest.mark.parametrize(
        "cell,expected",
        [
            # the story's own example: seven players, no delimiter anywhere
            ("G SpringerT GrishamS KwanV RoblesL TaverasK Watson(R)A Hays(I)",
             ["G Springer", "T Grisham", "S Kwan", "V Robles", "L Taveras",
              "K Watson(R)", "A Hays(I)"]),
            # dotted multi-initials — the `.` is NOT a boundary here
            ("J.P. CrawfordK Culpepper(M)B Carlson(M)",
             ["J.P. Crawford", "K Culpepper(M)", "B Carlson(M)"]),
            ("A.J. BlubaughK Yates", ["A.J. Blubaugh", "K Yates"]),
            ("C.J. Kayfus(M)S Jones(M)", ["C.J. Kayfus(M)", "S Jones(M)"]),
            # hyphenated surnames
            ("C Encarnacion-StrandN LopezD Jansen(I)",
             ["C Encarnacion-Strand", "N Lopez", "D Jansen(I)"]),
            ("I Kiner-Falefa(R)R Mountcastle(I)", ["I Kiner-Falefa(R)", "R Mountcastle(I)"]),
            # a suffix period IS a boundary (contrast with J.P. above)
            ("V Mesa Jr.A Judge(I)", ["V Mesa Jr.", "A Judge(I)"]),
            ("L Wade Jr.(R)S Basallo(I)", ["L Wade Jr.(R)", "S Basallo(I)"]),
            # the ONLY uppercase→uppercase boundary: a roman-numeral suffix
            ("D Lynch IVZ Matthews", ["D Lynch IV", "Z Matthews"]),
            # multi-word surnames — the junction is mid-word, not at a space
            ("E De Los SantosK Finnegan", ["E De Los Santos", "K Finnegan"]),
            ("H Yu LeeJ Soler(R)", ["H Yu Lee", "J Soler(R)"]),
            # a middle initial is not a new player
            ("R KreidlerJ H. Smith(R)", ["R Kreidler", "J H. Smith(R)"]),
        ],
    )
    def test_hard_cases(self, cell, expected):
        assert split_grid_cell(cell) == expected

    @pytest.mark.parametrize(
        "cell,expected",
        [
            # ⭐ the `Mc`/`De`/`La` class: an internal capital is NOT a boundary, because what
            # follows it (`Kinstry`) does not start like a player.
            ("Z McKinstry", ["Z McKinstry"]),
            ("C DeLauterA Benintendi", ["C DeLauter", "A Benintendi"]),
            ("J McNeilT Soderstrom", ["J McNeil", "T Soderstrom"]),
            ("S McClanahanT Bradley", ["S McClanahan", "T Bradley"]),
            ("J LaViolette(M)A Smith(M)", ["J LaViolette(M)", "A Smith(M)"]),
            ("K McGonigleC Williams(M)", ["K McGonigle", "C Williams(M)"]),
            ("L McCullers(R)D Sandlin(R)", ["L McCullers(R)", "D Sandlin(R)"]),
            # an apostrophe is inside a surname
            ("T O'Neill(R)B Matthews(I)", ["T O'Neill(R)", "B Matthews(I)"]),
        ],
    )
    def test_an_internal_capital_is_not_a_boundary(self, cell, expected):
        assert split_grid_cell(cell) == expected

    def test_status_tags_are_read(self, parsed):
        by_status = {}
        for entry in parsed.entries:
            by_status[entry.status] = by_status.get(entry.status, 0) + 1
        # (M) minors stashes are the signal this whole story turns on.
        assert by_status["minors"] == 61
        assert by_status["injured"] == 46
        assert by_status["reserve"] == 60
        assert by_status[None] == 275
        assert not any(e.status_code for e in parsed.entries), "unexpected unknown status code"

    def test_two_different_players_rendering_identically_keep_distinct_keys(self, parsed):
        """⭐ Found by this test, not by inspection. The real export holds `T Rogers` THREE times:
        Taylor and Tyler Rogers on the SAME fantasy team, in the SAME `P` slot, separated ONLY by
        one being `(R)` — plus a third on another team. A key of team+slot+name collapses the two
        KCStat pitchers, and a manual fix would then land on the wrong one."""
        rogers = [e for e in parsed.entries if e.name == "T Rogers"]
        assert len(rogers) == 3
        assert {(e.team, e.status) for e in rogers} == {
            ("KCStat", None), ("KCStat", "reserve"), ("phantoms", None),
        }
        assert len({e.key for e in rogers}) == 3


class TestTheNaiveSplitWouldBeWrong:
    """⭐ Proves these tests can FAIL. The obvious rule must break on the real export — otherwise
    the suite above is only asserting that the input was easy."""

    @staticmethod
    def _naive(cell: str) -> list[str]:
        return [t for t in re.split(r"(?<=[a-z])(?=[A-Z])", cell.strip()) if t]

    def test_the_naive_rule_shatters_real_surnames(self):
        assert self._naive("Z McKinstry") == ["Z Mc", "Kinstry"]
        assert split_grid_cell("Z McKinstry") == ["Z McKinstry"]

    def test_the_naive_rule_merges_two_players_it_cannot_see(self):
        # No lowercase→uppercase junction exists between these two at all.
        assert self._naive("D Lynch IVZ Matthews") == ["D Lynch IVZ Matthews"]
        assert split_grid_cell("D Lynch IVZ Matthews") == ["D Lynch IV", "Z Matthews"]

    def test_the_naive_rule_disagrees_with_ours_across_the_real_export(self, grid_text):
        rows = list(csv.reader(grid_text.splitlines()))
        disagreements = sum(
            1
            for row in rows[1:]
            for cell in row[1:]
            if cell.strip() and self._naive(cell) != split_grid_cell(cell)
        )
        assert disagreements >= 20, (
            "the naive split now agrees with ours almost everywhere — either the fixture was "
            "replaced with an easy one, or the tokenizer has regressed to the naive rule"
        )


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2 — the generic long form, and the refusals
# ══════════════════════════════════════════════════════════════════════════════════════════════


class TestTheGenericUploadSchema:
    def test_one_row_per_player(self):
        parsed = parse_roster_upload(
            "Team,Player,Position,Status\n"
            "Antonio Picante,Samuel Basallo,C,Minors\n"
            "Antonio Picante,Jasson Dominguez,OF,\n"
            "Red Paps,Kumar Rocker,P,IL\n"
        )
        assert parsed.upload_format == "long"
        assert [e.name for e in parsed.entries] == [
            "Samuel Basallo", "Jasson Dominguez", "Kumar Rocker",
        ]
        assert [e.status for e in parsed.entries] == ["minors", None, "injured"]
        assert parsed.teams == ["Antonio Picante", "Red Paps"]

    def test_header_synonyms_and_a_tagged_name(self):
        parsed = parse_roster_upload(
            "Fantasy Team\tplayer_name\tslot\n"
            "Sea Monkeys\tKevin McGonigle(M)\tSS\n"
        )
        assert parsed.entries[0] == RosterEntry(
            team="Sea Monkeys", slot="SS", name="Kevin McGonigle", status="minors"
        )

    def test_a_row_without_a_team_is_reported_not_dropped_silently(self):
        parsed = parse_roster_upload("Team,Player\nKCStat,Chase DeLauter\n,Orphan Player\n")
        assert len(parsed.entries) == 1
        assert any("Orphan Player" in w for w in parsed.warnings)

    @pytest.mark.parametrize(
        "text,fragment",
        [
            ("", "empty"),
            ("Team,C,1B\n", "no data rows"),
            ("Player,Position\nSamuel Basallo,C\n", "team/owner column"),
            ("Team\nAntonio Picante\n", "no position columns"),
        ],
    )
    def test_it_refuses_rather_than_returning_an_empty_roster(self, text, fragment):
        """⚠️ An empty roster would mark the ENTIRE board available — a silent, plausible-looking
        catastrophe. Every unusable upload must raise instead."""
        with pytest.raises(RosterUploadError) as excinfo:
            parse_roster_upload(text)
        assert fragment in str(excinfo.value)

    def test_an_oversized_upload_is_refused(self):
        with pytest.raises(RosterUploadError, match="KB"):
            parse_roster_upload("Team,Player\n" + "A,B\n" * 200_000)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3 — the board match
# ══════════════════════════════════════════════════════════════════════════════════════════════


def board_row(rank, name, league="AL", org="BAL", mlbam=None):
    return {"rank": rank, "name": name, "league": league, "org": org, "type": "batter",
            **({"mlbamId": mlbam} if mlbam is not None else {})}


BOARD = [
    board_row(1, "Samuel Basallo", org="BAL", mlbam=701),
    board_row(2, "Kevin McGonigle", org="DET", mlbam=702),
    board_row(3, "Hao-Yu Lee", org="DET", mlbam=703),
    board_row(4, "Elmer Rodríguez", org="TBR", mlbam=704),
    board_row(5, "Emmanuel Rodriguez", org="MIN", mlbam=705),
    board_row(6, "Griffin Hugus", org="SEA"),               # the board's duplicate-row pair,
    board_row(7, "Griffin Hugus", org="SEA", mlbam=707),    # one half with no MLBAM id
    board_row(8, "Konnor Griffin", league="NL", org="PIT", mlbam=708),
    board_row(9, "Jesus Made", league="NL", org="MIL", mlbam=709),
]


def entry(name, team="Antonio Picante", slot="C", status=None):
    return RosterEntry(team=team, slot=slot, name=name, status=status)


class TestTheMatch:
    def test_an_exact_name_resolves_and_marks_the_board_row_rostered(self):
        result = match_roster([entry("S Basallo", status="injured")], BOARD, "AL")
        assert result.matched[0].confidence == EXACT
        assert result.matched[0].board_rank == 1
        assert 1 in result.by_rank
        assert result.counts["rostered_board_rows"] == 1

    def test_a_rendering_variant_still_resolves(self):
        """CBS writes `Hao-Yu Lee` as `H Yu Lee`. Without the variant leg a genuinely rostered
        prospect would read as AVAILABLE — the dangerous direction."""
        result = match_roster([entry("H Yu Lee")], BOARD, "AL")
        assert result.matched[0].confidence == VARIANT
        assert result.matched[0].board_rank == 3

    def test_an_ambiguous_name_is_never_guessed(self):
        result = match_roster([entry("E Rodriguez", status="minors")], BOARD, "AL")
        matched = result.matched[0]
        assert matched.confidence == AMBIGUOUS
        assert matched.board_rank is None, "an ambiguous name must not claim a board row"
        assert {c["name"] for c in matched.candidates} == {"Elmer Rodríguez", "Emmanuel Rodriguez"}
        assert not result.by_rank

    def test_one_player_listed_twice_on_the_board_is_not_an_ambiguity(self):
        """Same name AND same org with one row missing its id is ONE player, not a choice."""
        result = match_roster([entry("G Hugus")], BOARD, "AL")
        assert result.matched[0].confidence == EXACT
        assert result.matched[0].board_rank == 7, "should keep the row that carries the MLBAM id"

    def test_league_scope_is_a_real_narrowing(self):
        """A dynasty league is single-league; scoping is what keeps the candidate set honest."""
        al = match_roster([entry("K Griffin")], BOARD, "AL")
        assert al.matched[0].confidence == UNRESOLVED
        nl = match_roster([entry("K Griffin")], BOARD, "NL")
        assert nl.matched[0].board_rank == 8
        assert al.counts["board_rows_in_scope"] < len(BOARD)

    def test_nothing_is_ever_silently_dropped(self):
        entries = [entry("S Basallo"), entry("E Rodriguez"), entry("Nobody Here"),
                   entry("H Yu Lee")]
        result = match_roster(entries, BOARD, "AL")
        assert len(result.matched) == len(entries)
        tiers = result.counts
        assert tiers[EXACT] + tiers[VARIANT] + tiers[AMBIGUOUS] + tiers[UNRESOLVED] == len(entries)

    def test_review_leads_with_the_rows_that_are_actually_holes(self):
        entries = [
            entry("H Yu Lee"),                                  # variant — already applied
            entry("Unknown Guy", status="minors"),              # a minors stash we could not place
            entry("E Rodriguez"),                               # ambiguous — a real hole
            entry("Another Nobody"),                            # not a prospect; must not nag
        ]
        review = match_roster(entries, BOARD, "AL").review
        assert [m.entry.name for m in review] == ["E Rodriguez", "Unknown Guy", "H Yu Lee"]

    def test_a_manual_override_pins_a_match_and_a_dismissal_clears_the_queue(self):
        ambiguous = entry("E Rodriguez", status="minors")
        pinned = match_roster([ambiguous], BOARD, "AL", overrides={ambiguous.key: 5})
        assert pinned.matched[0].board_rank == 5
        assert pinned.by_rank[5].entry.name == "E Rodriguez"

        unknown = entry("Some Veteran")
        dismissed = match_roster([unknown], BOARD, "AL", overrides={unknown.key: None})
        assert dismissed.counts["dismissed"] == 1
        assert not dismissed.review, "a dismissed row must stop being asked about"

    def test_a_manual_pin_beats_an_automatic_match_regardless_of_roster_ORDER(self):
        """⭐ Order-independence. In a single pass, whichever entry the file happened to list first
        would claim the board row — so a user's explicit correction could be silently discarded and
        still look accepted. The pin must win from either position in the file."""
        veteran = entry("S Basallo", team="Red Paps")          # auto-matches board row 1
        pinned = entry("Sammy Basallo", team="KCStat")         # the user says THIS is row 1
        for order in ([veteran, pinned], [pinned, veteran]):
            result = match_roster(order, BOARD, "AL", overrides={pinned.key: 1})
            assert result.by_rank[1].entry.team == "KCStat", "the manual pin lost to an auto match"
            loser = next(m for m in result.matched if m.entry.team == "Red Paps")
            assert loser.confidence == "contested", "the displaced entry vanished silently"
            assert len(result.matched) == 2

    def test_a_dangling_override_falls_back_to_resolving_rather_than_pinning_nothing(self):
        """The user switched the league scope, or the board was re-published. An override pointing
        out of scope must not silently mark the entry resolved-to-nothing."""
        basallo = entry("S Basallo")
        result = match_roster([basallo], BOARD, "AL", overrides={basallo.key: 9})  # 9 is NL
        assert result.matched[0].board_rank == 1
        assert result.matched[0].confidence == EXACT


OVERVIEW_FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "quant_sports_intel_models/baseball/edge_program/fixtures"
    / "e8_2_cbs_roster_overview_example_20260803.csv"
)


class TestThePerTeamRosterOverview:
    """The OTHER real CBS export (operator, 2026-08-03): one team, sectioned, and — the part that
    matters — FULL NAMES with the MLB club."""

    @pytest.fixture(scope="class")
    def parsed(self):
        return parse_roster_upload(OVERVIEW_FIXTURE.read_text(encoding="utf-8"),
                                   team="Statcast and Chill")

    def test_it_is_detected_without_being_told(self, parsed):
        assert parsed.upload_format == "roster_overview"

    def test_full_names_and_the_mlb_club_survive(self, parsed):
        meidroth = next(e for e in parsed.entries if "Meidroth" in e.name)
        assert meidroth.name == "Chase Meidroth"      # not `C Meidroth`
        assert meidroth.org == "CHW"
        assert meidroth.positions == "2B,SS"          # multi-position, comma inside a quoted cell

    def test_the_section_headings_set_the_status(self, parsed):
        by_status = {}
        for e in parsed.entries:
            by_status.setdefault(e.status, []).append(e.name)
        assert len(by_status[None]) == 23             # active, across BOTH blocks
        assert sorted(by_status["reserve"]) == [
            "Dylan Beavers", "Grayson Rodriguez", "Lane Thomas", "Shane Bieber", "Tyler Tolbert",
        ]
        assert by_status["minors"] == ["Tyler Bremner"]
        assert sorted(by_status["injured"]) == [
            "Brendan Donovan", "Connelly Early", "Matt Brash", "Parker Meadows",
        ]

    def test_a_pitchers_heading_resets_the_status_to_active(self, parsed):
        """`Minors` (empty) closes the batters block, then `Pitchers` begins — and Taj Bradley is
        ACTIVE, not a minors stash. Without the reset the whole pitching staff inherits `minors`."""
        assert next(e for e in parsed.entries if e.name == "Taj Bradley").status is None

    def test_the_exports_own_totals_are_enforced_as_a_CHECKSUM(self):
        """⭐ `Active: 23 Reserve: 5 Injured: 4 Minors: 1` is the file checking OUR work. A
        disagreement means a player was dropped — and a dropped player reads as AVAILABLE, the one
        failure that hides. So it refuses rather than importing a short roster."""
        text = OVERVIEW_FIXTURE.read_text(encoding="utf-8")
        with pytest.raises(RosterUploadError, match="missing players"):
            parse_roster_upload(text.replace("Active: 23", "Active: 24"), team="T")

    def test_a_missing_checksum_is_not_fatal(self):
        """A checksum we HAVE must be honoured; one that is absent must not block an import."""
        text = OVERVIEW_FIXTURE.read_text(encoding="utf-8")
        trimmed = "\n".join(ln for ln in text.splitlines() if not ln.startswith("Active:"))
        assert len(parse_roster_upload(trimmed, team="T").entries) == 33

    def test_it_says_it_needs_a_team_name_rather_than_filing_a_roster_under_nothing(self):
        """The per-team export does not name its own team. Silently filing 33 players under "" is
        how a whole roster comes to belong to nobody and everyone on it reads as available."""
        parsed = parse_roster_upload(OVERVIEW_FIXTURE.read_text(encoding="utf-8"))
        assert parsed.needs_team is True
        assert parsed.teams == []

    def test_it_agrees_with_the_LEAGUE_GRID_about_the_same_team(self, parsed, grid_text):
        """⭐ THE STRONGEST EVIDENCE EITHER PARSER IS RIGHT, and the check a single fixture cannot
        give (the NF-C0 second-real-payload lesson). Two INDEPENDENTLY-PRODUCED CBS exports of the
        same roster, read by two completely unrelated code paths — the no-delimiter concatenation
        tokenizer, and the sectioned per-team reader — must name the same players.

        They do: 33 each, with nobody on either side only."""
        grid = [e for e in parse_roster_upload(grid_text).entries
                if e.team == "Statcast and Chill"]
        assert len(grid) == len(parsed.entries) == 33

        def surname(name):
            return name_key(name)[1]

        assert {surname(e.name) for e in grid} == {surname(e.name) for e in parsed.entries}

    def test_the_STICKY_statuses_agree_across_the_two_exports(self, parsed, grid_text):
        """The exports are three days apart (7/31 grid, 8/03 overview), so ACTIVE↔RESERVE churn is
        the owner shuffling his lineup — 8 players moved and that is real, not a parse defect.
        MINORS and INJURED are sticky over three days, and those must agree exactly, because they
        are the statuses this feature actually turns on."""
        grid = {
            name_key(e.name)[1]: e.status
            for e in parse_roster_upload(grid_text).entries
            if e.team == "Statcast and Chill"
        }
        sticky = {
            name_key(e.name)[1]: e.status
            for e in parsed.entries
            if e.status in ("minors", "injured")
        }
        assert sticky, "no sticky statuses in the fixture — this assertion would be vacuous"
        for surname, status in sticky.items():
            assert grid[surname] == status, f"{surname}: grid {grid[surname]} vs overview {status}"


class TestFullNamesRemoveTheAmbiguityClass:
    BOARD = [
        board_row(1, "Elmer Rodriguez", org="TBR", mlbam=801),
        board_row(2, "Emmanuel Rodriguez", org="MIN", mlbam=802),
        board_row(3, "Elorky Rodriguez", org="HOU", mlbam=803),
    ]

    def test_an_initial_is_ambiguous_but_a_full_name_is_not(self):
        """⭐ The measured payoff of the per-team export. On the live AL board, initial+surname
        leaves 9 ambiguous keys; the full name leaves ZERO."""
        assert match_roster([entry("E Rodriguez")], self.BOARD, "AL").matched[0].confidence == (
            AMBIGUOUS
        )
        result = match_roster([entry("Emmanuel Rodriguez")], self.BOARD, "AL")
        assert result.matched[0].confidence == EXACT
        assert result.matched[0].board_rank == 2

    def test_the_mlb_club_breaks_a_tie_the_name_cannot(self):
        board = [board_row(1, "Jose Rodriguez", org="LAD", mlbam=811),
                 board_row(2, "Jose Rodriguez", org="MIL", mlbam=812)]
        blind = match_roster([entry("Jose Rodriguez")], board, "AL")
        assert blind.matched[0].confidence == AMBIGUOUS
        with_org = match_roster(
            [RosterEntry(team="T", slot="SS", name="Jose Rodriguez", org="MIL")], board, "AL"
        )
        assert with_org.matched[0].board_rank == 2

    def test_an_org_MISMATCH_never_rejects_a_lone_candidate(self):
        """⚠️ Asymmetric to the slot check on purpose. Batter-vs-pitcher does not change; a club
        does — the board carries a PARENT org and trades move it constantly. So an org match is
        strong evidence of the same player, but a mismatch is weak evidence of a different one."""
        board = [board_row(1, "Chase DeLauter", org="CLE", mlbam=821)]
        traded = RosterEntry(team="T", slot="OF", name="Chase DeLauter", org="NYY")
        assert match_roster([traded], board, "AL").matched[0].board_rank == 1


class TestBoardCoverageGaps:
    """⭐ The signal that used to be thrown away (operator, 2026-08-03): a player in somebody's
    MINORS slot who matches nothing is evidence of a prospect we should be carrying."""

    BOARD = [board_row(1, "Samuel Basallo", org="BAL", mlbam=701)]

    def test_an_unplaceable_minors_stash_is_reported_without_anyone_asking(self):
        stash = RosterEntry(team="KCStat", slot="OF", name="Vance Honeycutt",
                            status="minors", org="BAL", positions="OF")
        result = match_roster([stash], self.BOARD, "AL")
        assert result.counts["coverage_gaps"] == 1
        gap = result.coverage_gaps[0]
        assert gap["name"] == "Vance Honeycutt"
        assert gap["org"] == "BAL"          # what makes it actionable for an operator
        assert gap["source"] == "suggested"

    def test_the_two_dismissals_are_different_statements(self):
        """`S Perez` is an established major-leaguer; `V Honeycutt` is a prospect we are missing.
        Collapsing both into one silent delete is what lost the signal."""
        veteran = entry("Salvador Perez")
        prospect = entry("Vance Honeycutt", status="minors")
        result = match_roster(
            [veteran, prospect], self.BOARD, "AL",
            overrides={veteran.key: "not_a_prospect", prospect.key: "missing_from_board"},
        )
        assert [g["name"] for g in result.coverage_gaps] == ["Vance Honeycutt"]
        assert result.coverage_gaps[0]["source"] == "confirmed"
        assert result.counts["dismissed"] == 1

    def test_a_confirmed_gap_leaves_the_review_queue_but_stays_reported(self):
        """It must stop nagging without being forgotten — those are different things."""
        prospect = entry("Vance Honeycutt", status="minors")
        before = match_roster([prospect], self.BOARD, "AL")
        assert before.review and before.counts["coverage_gaps"] == 1
        after = match_roster([prospect], self.BOARD, "AL",
                             overrides={prospect.key: "missing_from_board"})
        assert not after.review
        assert after.counts["coverage_gaps"] == 1

    def test_neither_dismissal_ever_marks_a_board_row_rostered(self):
        for reason in ("not_a_prospect", "missing_from_board", None):
            e = entry("Whoever", status="minors")
            result = match_roster([e], self.BOARD, "AL", overrides={e.key: reason})
            assert not result.by_rank, f"{reason} claimed a board row"

    def test_confirmed_gaps_sort_ahead_of_suggested_ones(self):
        confirmed = entry("Aaron Confirmed", status="minors")
        suggested = entry("Zeb Suggested", status="minors")
        result = match_roster([suggested, confirmed], self.BOARD, "AL",
                              overrides={confirmed.key: "missing_from_board"})
        assert [g["source"] for g in result.coverage_gaps] == ["confirmed", "suggested"]


class TestTheGapSelfHeals:
    """⭐ E8.5 — the deferred E8.2 defect. `missing_from_board` used to be applied BEFORE matching,
    so once the board added the flagged player he stayed flagged (and out of the overlay) forever.
    It must instead be re-evaluated against the CURRENT board on every call."""

    BOARD_WITHOUT = [board_row(1, "Samuel Basallo", org="BAL", mlbam=701)]
    BOARD_WITH = BOARD_WITHOUT + [board_row(2, "Vance Honeycutt", org="BAL", mlbam=702)]

    def test_a_confirmed_gap_clears_itself_once_the_board_adds_the_player(self):
        prospect = entry("Vance Honeycutt", status="minors")
        overrides = {prospect.key: "missing_from_board"}

        before = match_roster([prospect], self.BOARD_WITHOUT, "AL", overrides=overrides)
        assert before.coverage_gaps and before.coverage_gaps[0]["source"] == "confirmed"
        assert before.matched[0].board_rank is None

        after = match_roster([prospect], self.BOARD_WITH, "AL", overrides=overrides)
        assert after.coverage_gaps == [], "the gap must clear itself, not require a manual undo"
        assert after.matched[0].confidence == EXACT
        assert after.matched[0].board_rank == 2
        assert after.by_rank[2].entry.name == "Vance Honeycutt"

    def test_a_still_missing_confirmed_gap_survives_an_unrelated_board_change(self):
        """The board changed (a rank shifted) but the flagged player is STILL not on it — the
        confirmation must not be lost just because *something* about the board is different."""
        prospect = entry("Vance Honeycutt", status="minors")
        overrides = {prospect.key: "missing_from_board"}
        reranked = [{**self.BOARD_WITHOUT[0], "rank": 5}]
        result = match_roster([prospect], reranked, "AL", overrides=overrides)
        assert result.coverage_gaps and result.coverage_gaps[0]["source"] == "confirmed"
        assert result.matched[0].confidence == MISSING_FROM_BOARD

    def test_not_a_prospect_never_self_heals(self):
        """A `not_a_prospect` dismissal is a statement about the PERSON, not the board's contents —
        it must stay dismissed even after the board changes, unlike `missing_from_board`."""
        veteran = entry("Salvador Perez")
        overrides = {veteran.key: "not_a_prospect"}
        board_with_a_perez_prospect = self.BOARD_WITHOUT + [
            board_row(9, "Salvador Perez", org="KC", mlbam=999)
        ]
        result = match_roster([veteran], board_with_a_perez_prospect, "AL", overrides=overrides)
        assert result.matched[0].confidence == MANUAL
        assert result.matched[0].board_rank is None
        assert result.coverage_gaps == []


class TestTheSlotHint:
    """⭐ The one signal the upload carries besides a name — and on the real export it is worth
    four corrections in 103 matches, every one a FALSE POSITIVE against a same-named pitcher."""

    BOARD = [
        board_row(1, "Steven Perez", org="TBR", mlbam=801),          # a pitching prospect…
        board_row(2, "Michael Massey", org="MIN", mlbam=802),
        board_row(3, "Gabriel Rodriguez", org="CLE", mlbam=803),
        board_row(4, "Gerardo Rodriguez", org="TEX", mlbam=804),
        board_row(5, "Shohei Futures", org="LAA", mlbam=805),
    ]

    def setup_method(self):
        for row, kind in zip(self.BOARD, ["pitcher", "pitcher", "batter", "batter", "two_way"]):
            row["type"] = kind

    def test_a_batter_slot_does_not_match_a_pitching_prospect(self):
        """`S Perez` in the C slot is Salvador Perez, not a SIRP prospect called Steven Pérez.
        Matching them marks an AVAILABLE prospect rostered and hides him from the draft pool."""
        result = match_roster([entry("S Perez", slot="C")], self.BOARD, "AL")
        matched = result.matched[0]
        assert matched.confidence == "position_conflict"
        assert matched.board_rank is None
        assert not result.by_rank

    def test_the_rejected_candidate_is_still_offered_for_a_manual_fix(self):
        """If the BOARD's type is what is wrong, the user must still be able to pin it. A silent
        non-match would be indistinguishable from 'no such prospect'."""
        result = match_roster([entry("M Massey", slot="2B")], self.BOARD, "AL")
        assert [c["name"] for c in result.matched[0].candidates] == ["Michael Massey"]
        assert result.matched[0] in result.review

    def test_the_slot_RESOLVES_an_ambiguity_rather_than_only_rejecting(self):
        """Two same-named batters and a P slot → neither is a pitcher, so it is a conflict; but a
        batter slot narrows nothing here, so both remain candidates and neither is guessed."""
        conflict = match_roster([entry("G Rodriguez", slot="P")], self.BOARD, "AL")
        assert conflict.matched[0].confidence == "position_conflict"
        ambiguous = match_roster([entry("G Rodriguez", slot="SS")], self.BOARD, "AL")
        assert ambiguous.matched[0].confidence == AMBIGUOUS
        assert len(ambiguous.matched[0].candidates) == 2

    def test_a_two_way_prospect_satisfies_both_kinds_of_slot(self):
        for slot in ("P", "OF"):
            result = match_roster([entry("S Futures", slot=slot)], self.BOARD, "AL")
            assert result.matched[0].board_rank == 5, f"{slot} rejected a two-way player"

    @pytest.mark.parametrize("slot", ["—", "UTIL-ISH", ""])
    def test_an_uninterpretable_slot_is_inert_rather_than_rejecting(self, slot):
        """A long-form upload may carry no position at all. A hint we cannot read must not veto."""
        result = match_roster([entry("M Massey", slot=slot)], self.BOARD, "AL")
        assert result.matched[0].board_rank == 2

    def test_a_board_row_with_no_type_is_also_inert(self):
        """Symmetric to the above: the check disables itself rather than rejecting on missing data."""
        board = [{"rank": 9, "name": "Typeless Guy", "league": "AL", "org": "OAK"}]
        result = match_roster([entry("T Guy", slot="P")], board, "AL")
        assert result.matched[0].board_rank == 9


class TestOneBoardRowCannotBeOnTwoRosters:
    def test_the_second_claimant_is_reported_not_silently_dropped(self):
        """⚠️ Found on the real export: `Texas Chaos` lists `C Smith` at BOTH OF and P — two
        different players. Keeping the first and discarding the second is exactly the silent drop
        this module exists to prevent, so the loser is surfaced instead."""
        # Deliberately the residual case the SLOT hint cannot settle: the same batter slot on two
        # different teams. (The real export's OF-vs-P `C Smith` is resolved by the slot filter — see
        # TestTheSlotHint — so this is the conflict that survives it.)
        board = [board_row(1, "Cade Smith", org="NYY", mlbam=901)]
        entries = [entry("C Smith", slot="OF"), entry("C Smith", slot="OF", team="Red Paps")]
        result = match_roster(entries, board, "AL")
        assert len(result.matched) == 2, "an entry vanished"
        assert len(result.by_rank) == 1, "one board row cannot be on two rosters"
        assert [m.confidence for m in result.matched] == [EXACT, "contested"]
        assert result.matched[1] in result.review


class TestTheOverlayKeysOnRankNotMlbamId:
    def test_a_board_row_without_an_mlbam_id_can_still_be_marked_rostered(self):
        """⚠️ 9 live board rows carry no `mlbamId`. Keying the overlay on the id would leave them
        permanently, and wrongly, 'available'."""
        board = [board_row(11, "Nolan Idless", org="TEX")]  # no mlbamId at all
        result = match_roster([entry("N Idless", status="minors")], board, "AL")
        assert result.matched[0].board_rank == 11
        assert 11 in result.by_rank


class TestNameNormalization:
    @pytest.mark.parametrize(
        "name,expected",
        [
            ("J.P. Crawford", ("j", "crawford", "crawford")),
            ("Vladimir Guerrero Jr.", ("v", "guerrero", "guerrero")),
            ("E De Los Santos", ("e", "delossantos", "santos")),
            ("J H. Smith", ("j", "smith", "smith")),          # middle initial dropped
            ("Elmer Rodríguez", ("e", "rodriguez", "rodriguez")),  # accents folded
            ("I Kiner-Falefa", ("i", "kinerfalefa", "kinerfalefa")),
            ("D Lynch IV", ("d", "lynch", "lynch")),
        ],
    )
    def test_keys(self, name, expected):
        assert name_key(name) == expected

    def test_a_nameless_token_yields_no_key_rather_than_a_bogus_one(self):
        assert name_key("") is None
        assert name_key("Cher") is None  # one token: no surname to match on


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4 — end to end, on the real export
# ══════════════════════════════════════════════════════════════════════════════════════════════


class TestEndToEndOnTheRealExport:
    def test_the_real_roster_matches_a_synthetic_board_without_crashing(self, parsed):
        # ⚠️ The `type` is load-bearing: Sloan and Yesavage sit in a `P` slot in the real export,
        # so a board that mislabels them as batters makes the slot check reject them (which is the
        # check working — it was this test's fixture that was wrong).
        board = [
            {**board_row(i + 1, n, org="BAL", mlbam=900 + i), "type": kind}
            for i, (n, kind) in enumerate([
                ("Samuel Basallo", "batter"), ("Kevin McGonigle", "batter"),
                ("Max Clark", "batter"), ("Franklin Arias", "batter"),
                ("Leo De Vries", "batter"), ("Ryan Sloan", "pitcher"),
                ("Chase DeLauter", "batter"), ("Trey Yesavage", "pitcher"),
                ("Hao-Yu Lee", "batter"),
            ])
        ]
        result = match_roster(parsed.entries, board, "AL")
        assert result.counts["players"] == 442
        # every one of those nine is genuinely on a roster in the real export
        assert result.counts["rostered_board_rows"] == 9, (
            "a board prospect that IS rostered failed to match — that prospect would wrongly "
            "show as available"
        )
        assert sum(result.counts[t] for t in (EXACT, VARIANT)) == 9
