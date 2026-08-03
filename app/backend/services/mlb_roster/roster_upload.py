"""E8.2 — the league-roster UPLOAD parser (Path A, the guaranteed floor).

Two accepted shapes, auto-detected:

  * **CBS "roster grid"** — one row per fantasy TEAM, columns are POSITION SLOTS
    (`Team,C,1B,2B,3B,SS,MI,CI,OF,DH,P`), and every player a team holds at that position is
    CONCATENATED into the one cell.
  * **long form** — the documented generic schema, one row per rostered player, with a
    team/owner column and a player column (+ optional position and status). This is what makes
    the feature platform-independent: a Yahoo/ESPN/Fantrax user can always reshape their export
    into three columns and get the same product.

════════════════════════════════════════════════════════════════════════════════════════════════
⚠️  THE CRUX: A GRID CELL HAS NO DELIMITER, AND `[a-z][A-Z]` IS THE WRONG SPLIT
════════════════════════════════════════════════════════════════════════════════════════════════
The OF cell `G SpringerT GrishamS KwanV RoblesL TaverasK Watson(R)A Hays(I)` is SEVEN players.
There is not even a space at the boundary. The obvious rule — cut at every lowercase→uppercase
junction — is WRONG on real rosters, and wrong in the direction that silently invents players:

    Z McKinstry     → "Z Mc"    + "Kinstry"      ✗   (also DeLauter, McNeil, LaViolette, DeLuca)
    T O'Neill(R)    → "T O'"    + "Neill(R)"     ✗
    J.P. Crawford   → "J."      + "P. Crawford"  ✗   (a period junction, not a name boundary)

and in the direction that silently MERGES two players, which is worse because the merged token
then fails to match and one of the two disappears from the roster entirely:

    E De Los SantosK Finnegan   — the junction is inside `SantosK`, not at a space
    V Mesa Jr.A Judge(I)        — the junction is `.` → `A`, after a SUFFIX
    D Lynch IVZ Matthews        — `V` → `Z`, uppercase → uppercase, no lowercase anywhere

So a junction is a player boundary only when the text AFTER it actually starts like a player —
an initial block followed by a space (`J `, `J.P. `, `A.J. `, `J.T. `). That single guard is what
kills the `McKinstry` class: `Kinstry` is not a player start, so `Mc|K` is not a cut.

⭐ THE INVARIANT THAT MAKES THIS SAFE: the cuts PARTITION the cell, so re-joining the parsed
players must reproduce it byte for byte. A tokenizer that cannot lose or invent a character
cannot silently drop a rostered player — and a dropped rostered player is the one failure that
matters here, because it reads on the board as "available" (see `board_match`).

Every rule below is pinned by `betting_ml/tests/test_e8_2_roster_upload.py` against the operator's
real 2026-07-31 CBS export, which contains all of the hard cases above.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field

#: Upper bound on an accepted upload. Generous for a 12–20 team league (the operator's real export
#: is ~5 KB) and small enough that a mis-paste cannot cost a Lambda timeout.
MAX_UPLOAD_BYTES = 512_000

#: Upper bound on parsed players, so a malformed file cannot write an unbounded roster to DynamoDB.
MAX_ENTRIES = 1_500

#: A player STARTS with an initial block followed by a space: `J `, `J.P. `, `A.J. `, `J.T. `.
#: This is the guard that makes a lowercase→uppercase junction safe — see the module docstring.
_PLAYER_START = re.compile(r"(?:[A-Z]\.){1,3}\s|[A-Z]\s")

#: Name SUFFIXES that may sit between the surname and the next player. `IV`/`III` matter because
#: they are the only way a boundary can be uppercase→uppercase (`D Lynch IV` + `Z Matthews`) with
#: no lowercase letter anywhere to cut on. `JR`/`SR` are covered by the lowercase rule when written
#: `Jr.`, and are listed for the all-caps rendering.
_SUFFIXES = frozenset({"JR", "JR.", "SR", "SR.", "II", "III", "IV"})

#: A trailing `(M)` / `(I)` / `(R)` status tag. Two letters are allowed so an unknown code is
#: captured and reported rather than glued onto the surname.
_STATUS = re.compile(r"^(?P<name>.*?)\((?P<code>[A-Za-z]{1,2})\)$")

#: CBS's legend. `minors` is the one that earns this story: a board prospect sitting in someone's
#: minors slot is ROSTERED, which is exactly the dynasty stash the availability filter exists for.
STATUS_CODES = {"M": "minors", "I": "injured", "R": "reserve"}

#: Long-form column synonyms. Lowercased, non-alphanumerics stripped, so `Fantasy Team` and
#: `fantasy_team` are the same header.
_TEAM_HEADERS = ("team", "fantasyteam", "owner", "manager", "franchise", "teamname", "ownername")
_PLAYER_HEADERS = ("player", "playername", "name", "athlete", "fullname")
_SLOT_HEADERS = ("slot", "position", "pos", "rosterslot", "lineupslot")
_STATUS_HEADERS = ("status", "rosterstatus", "designation")


class RosterUploadError(ValueError):
    """The upload could not be read as a roster. Carries a message written FOR THE USER."""


@dataclass(frozen=True)
class RosterEntry:
    """One rostered player, exactly as the upload described them.

    `name` is kept VERBATIM (`J.P. Crawford`, `V Mesa Jr.`, `T O'Neill`) — normalization belongs to
    the matcher, and keeping the original is what lets the review UI show the user their own text.
    """

    team: str
    slot: str
    name: str
    #: "minors" | "injured" | "reserve" | None (active). None is a real state, never a gap.
    status: str | None = None
    #: A status code we do not have a legend for. Kept, reported, never silently dropped.
    status_code: str | None = None

    @property
    def key(self) -> str:
        """Stable identity for a manual override.

        ⚠️ TEAM **AND STATUS** ARE BOTH LOAD-BEARING, and the real export proves it: it holds
        `T Rogers` three times — Taylor and Tyler Rogers on the SAME team (KCStat, same `P` slot,
        one active and one `(R)`), plus a third on `phantoms`. Keying on the name alone collapses
        all three; keying on team+slot+name still collapses the two KCStat pitchers and would send
        a user's manual fix to the wrong one.

        ⛔ DELIBERATELY NOT an ordinal index, which would be trivially unique. An index shifts the
        moment the user re-uploads a changed roster, so every stored override would silently
        re-point at whichever player now sits in that position — a wrong pin that still looks
        resolved. A rare unresolvable tie (same team, slot, name AND status) is a player the source
        data cannot distinguish either, so sharing one override is the honest outcome.
        """
        return f"{self.team}␟{self.slot}␟{self.name}␟{self.status or ''}"


@dataclass
class ParsedRoster:
    entries: list[RosterEntry] = field(default_factory=list)
    teams: list[str] = field(default_factory=list)
    #: "cbs_grid" | "long"
    upload_format: str = "cbs_grid"
    #: Non-fatal observations for the user (unknown status code, a row we could not attribute).
    warnings: list[str] = field(default_factory=list)


# ── the tokenizer ────────────────────────────────────────────────────────────────────────────────


def _starts_player(text: str) -> bool:
    """Does `text` begin with an initial block + space?  `J Latz` yes, `Kinstry` no."""
    return _PLAYER_START.match(text) is not None


def split_grid_cell(cell: str) -> list[str]:
    """One concatenated grid cell → its player tokens, status tags still attached.

    The returned tokens PARTITION the stripped cell: `"".join(result) == cell.strip()`. That is the
    invariant that makes a silent drop impossible; it is asserted in the test suite against every
    cell of the real export.
    """
    cell = cell.strip()
    if not cell:
        return []

    cuts = [0]
    for i in range(1, len(cell)):
        char, prev = cell[i], cell[i - 1]
        # Only an uppercase letter can open a player, and only if what follows it actually looks
        # like one. This second test is the whole defence against `Mc|Kinstry` / `O'|Neill`.
        if not char.isupper() or not _starts_player(cell[i:]):
            continue

        if prev.islower():
            # ...WallsW Aloy  /  ...SantosK Finnegan — the ordinary boundary.
            cut = True
        elif prev == ")":
            # ...(M)A Nimmala — a status tag closed the previous player.
            cut = True
        elif prev == "." and i >= 2 and cell[i - 2].islower():
            # ...Jr.A Judge — a suffix period. The `islower` test is what keeps `J.P.` intact:
            # there the character before the period is `J`, uppercase, so it is not a boundary.
            cut = True
        elif prev.isupper():
            # ...IV|Z Matthews — the only uppercase→uppercase boundary, and admissible ONLY when
            # the word we are leaving is a known suffix. Without this clause the two players merge.
            cut = cell[:i].split(" ")[-1].upper() in _SUFFIXES
        else:
            # A space cannot be a boundary (players are concatenated with none), and an apostrophe
            # or hyphen is inside a surname.
            cut = False

        if cut:
            cuts.append(i)

    cuts.append(len(cell))
    return [tok for tok in (cell[a:b] for a, b in zip(cuts, cuts[1:])) if tok.strip()]


def _split_status(token: str) -> tuple[str, str | None, str | None]:
    """`"K Watson(R)"` → `("K Watson", "reserve", None)`; an unknown code comes back for reporting."""
    token = token.strip()
    match = _STATUS.match(token)
    if not match:
        return token, None, None
    name = match.group("name").strip()
    code = match.group("code").upper()
    if not name:
        # Something like a bare "(R)" — not a player. Keep the original so nothing is lost.
        return token, None, None
    return name, STATUS_CODES.get(code), None if code in STATUS_CODES else code


# ── format detection + the two readers ───────────────────────────────────────────────────────────


def _normalize_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").strip().lower())


def _read_rows(text: str) -> list[list[str]]:
    text = text.lstrip("﻿")
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",\t;")
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = "\t" if "\t" in text.splitlines()[0] else ","
    rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))
    return [row for row in rows if any((cell or "").strip() for cell in row)]


def _looks_long_form(header: list[str]) -> bool:
    """A long-form file names a PLAYER column; the grid's headers are position slots only."""
    normalized = {_normalize_header(cell) for cell in header}
    return any(candidate in normalized for candidate in _PLAYER_HEADERS)


def _parse_grid(rows: list[list[str]]) -> ParsedRoster:
    header = rows[0]
    # The real export ends its header with a trailing empty column; slots are everything after the
    # team column that is actually named.
    slots = [(idx, cell.strip()) for idx, cell in enumerate(header[1:], start=1) if cell.strip()]
    if not slots:
        raise RosterUploadError(
            "That file has a team column but no position columns, so there is nothing to read. "
            "A CBS roster grid looks like: Team,C,1B,2B,3B,SS,MI,CI,OF,DH,P"
        )

    out = ParsedRoster(upload_format="cbs_grid")
    seen_teams: set[str] = set()
    for row in rows[1:]:
        team = (row[0] if row else "").strip()
        if not team:
            continue
        if team in seen_teams:
            out.warnings.append(
                f"Two rows are both named “{team}”. They were merged into one team — rename them "
                "in the export if they are different teams."
            )
        seen_teams.add(team)
        if team not in out.teams:
            out.teams.append(team)

        for idx, slot in slots:
            cell = row[idx] if idx < len(row) else ""
            for token in split_grid_cell(cell):
                name, status, unknown = _split_status(token)
                if unknown:
                    out.warnings.append(
                        f"“{name}” ({team}, {slot}) carries an unfamiliar tag “({unknown})”. "
                        "They were kept as rostered."
                    )
                out.entries.append(
                    RosterEntry(team=team, slot=slot, name=name, status=status, status_code=unknown)
                )
    return out


def _parse_long(rows: list[list[str]]) -> ParsedRoster:
    header = [_normalize_header(cell) for cell in rows[0]]

    def column(candidates: tuple[str, ...]) -> int | None:
        for candidate in candidates:
            if candidate in header:
                return header.index(candidate)
        return None

    player_idx = column(_PLAYER_HEADERS)
    team_idx = column(_TEAM_HEADERS)
    slot_idx = column(_SLOT_HEADERS)
    status_idx = column(_STATUS_HEADERS)
    if player_idx is None:
        raise RosterUploadError("That file has no player column.")
    if team_idx is None:
        raise RosterUploadError(
            "That file has a player column but no team/owner column, so we cannot tell WHO rosters "
            "each player — which is the whole point of the import. Add a column named “Team”."
        )

    out = ParsedRoster(upload_format="long")
    for line, row in enumerate(rows[1:], start=2):
        def cell(idx: int | None) -> str:
            return (row[idx] if idx is not None and idx < len(row) else "").strip()

        name = cell(player_idx)
        team = cell(team_idx)
        if not name:
            continue
        if not team:
            out.warnings.append(f"Row {line} (“{name}”) has no team and was skipped.")
            continue
        if team not in out.teams:
            out.teams.append(team)

        # A long-form row may carry the status in its own column OR still tagged onto the name.
        name, status, unknown = _split_status(name)
        raw_status = cell(status_idx)
        if raw_status:
            token = re.sub(r"[^a-z]", "", raw_status.lower())
            by_word = {"minors": "minors", "minor": "minors", "il": "injured", "injured": "injured",
                       "injuredlist": "injured", "dl": "injured", "reserve": "reserve",
                       "bench": "reserve", "taxi": "minors", "active": None, "starter": None}
            if token in by_word:
                status = by_word[token]
            elif len(raw_status.strip("()")) <= 2:
                code = raw_status.strip("()").upper()
                status = STATUS_CODES.get(code, status)
                unknown = None if code in STATUS_CODES else code
        if unknown:
            out.warnings.append(
                f"“{name}” ({team}) carries an unfamiliar status “{unknown}”. They were kept as "
                "rostered."
            )
        out.entries.append(
            RosterEntry(
                team=team,
                slot=cell(slot_idx) or "—",
                name=name,
                status=status,
                status_code=unknown,
            )
        )
    return out


def parse_roster_upload(text: str) -> ParsedRoster:
    """A pasted/uploaded league roster → its entries. Raises `RosterUploadError` with user-facing
    copy; never returns a partially-read roster silently.

    ⚠️ An EMPTY result is raised, not returned. A roster that parsed to nothing would mark the
    entire board "available", which is the failure this feature exists to prevent — and it would
    look exactly like a correct board.
    """
    if not text or not text.strip():
        raise RosterUploadError("The upload was empty.")
    if len(text.encode("utf-8", "ignore")) > MAX_UPLOAD_BYTES:
        raise RosterUploadError(
            f"That upload is larger than {MAX_UPLOAD_BYTES // 1000} KB. A league roster export is "
            "a few KB — this looks like the wrong file."
        )

    rows = _read_rows(text)
    if len(rows) < 2:
        raise RosterUploadError(
            "That upload has no data rows. Paste the whole roster grid, including its header row."
        )

    parsed = _parse_long(rows) if _looks_long_form(rows[0]) else _parse_grid(rows)

    if not parsed.entries:
        raise RosterUploadError(
            "No players could be read out of that file. If this is a CBS export, make sure the "
            "first column is the team name and the remaining columns are position slots."
        )
    if len(parsed.entries) > MAX_ENTRIES:
        raise RosterUploadError(
            f"That upload contains {len(parsed.entries):,} players, more than the {MAX_ENTRIES:,} "
            "we accept for one league. It is probably not a single league's rosters."
        )
    return parsed
