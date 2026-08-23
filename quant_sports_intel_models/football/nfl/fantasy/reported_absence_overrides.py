"""reported_absence_overrides.py — NF-INJ-NEWS-1: the OPERATOR-CURATED reported-absence games cap.

⚖️ WHAT THIS IS, STATED FIRST BECAUSE EVERYTHING ELSE DEPENDS ON IT: **an operator judgment with
provenance attached. It is NOT a model.** Nothing here is fitted, nothing here is backtested, nothing
here has been shown to improve a projection, and no copy on any surface may claim that it does. It
exists because the availability discount has exactly one entry point — a FORMAL roster transaction
(IR/PUP/NFI/SUS via `season_projection._INJURY_STATUS_GAMES_CAP`) — so a player credibly reported to
miss two months but carrying no formal tag is projected as if healthy. That gap is traced in
`ablation_results/nf_c8_injury_designation_gap.md`; Jordyn Tyson (WR27, `proj_games` 13.6 against
reporting of a ~two-month absence) is the case that surfaced it on a live draft board.

The honest fix is an empirical designation/news → games-missed duration model, which is a §0.5
story with a real bake-off (parent card wufGcjB8) and is scheduled to REPLACE this mechanism after
draft season. This is the approved interim: forward-only, never backtested, `best_alpha = 0`.

⛔ FOUR HARD RULES. Each one is a correctness property, not a preference, and each is pinned by a
   RED-proven guard in `betting_ml/tests/test_nf_inj_news_1_reported_absence.py`:

 1. **DISJOINTNESS — the formal path always wins.** A row applies ONLY to a player with NO formal
    status. The disjointness is evaluated against `season_projection._INJURY_STATUS_GAMES_CAP`
    ITSELF (see `season_projection.reported_absence_games`), not against a copy of its keys, so the
    two populations cannot drift apart: whatever the formal cap fires on, this one does not. A row
    whose player HAS acquired a formal tag is IGNORED and named in the build log — it is not a
    double discount and it does not collide with NF-INJ3b's cap constants, which govern the
    formally-tagged population only.

 2. **CAP-ONLY and MONOTONE.** `min(current_expected_games, 17 − expected_games_missed)`. An
    override can only ever LOWER expected games. It cannot raise availability, it cannot rebound a
    player another availability step already cut, and it feeds the SAME `proj_games` quantity the
    formal caps feed — no second modelling pathway is created.

 3. **NORMALISED ID, VERIFIED BY NAME.** The join key is normalised on BOTH sides through the one
    owner below. `player_name` is carried so the join can be verified by NAME rather than by the id
    under test — NF-C9 published a board whose id-keyed verification reported "0 join failures"
    while 275 of 2,501 feed ids carried a LEADING SPACE, and Josh Jacobs and DK Metcalf silently
    carried no disclosure. A check keyed on the join key cannot see a defect in that key.

 4. **`review_by` EXPIRY — a stale judgment dies LOUDLY.** Past its `review_by` a row stops being
    applied and is reported as EXPIRED. A hand-entered absence estimate that nobody revisits is
    wrong within weeks (players return); silent persistence is the failure mode this field exists
    to prevent. Expiry is evaluated against an injectable `as_of`, never a hidden clock.

⭐ EVERY REJECTION IS REPORTED, NEVER DROPPED. A malformed, expired, duplicated or formally-superseded
row is returned in `LoadResult.rejected` with a reason and printed by `format_load_log`. A curated
file whose rows silently do nothing is indistinguishable from a curated file that works, which is
the exact class of defect this repo keeps re-finding (NF1.7 (a) / INC-38 / NF-C6P3): "we publish
nothing here" and "we could not read this" must never render the same.

⭐ AND THE FAILURE DIRECTION IS DELIBERATE: every ambiguity resolves toward APPLYING NOTHING. An
unreadable file, a malformed row, an ambiguous duplicate — all leave the board byte-identical to the
pre-story board. Doing nothing is a state we understand; applying a half-parsed operator judgment is
not.

IO BOUNDARY: `load_overrides` is the ONLY function here that touches disk. The cap ARITHMETIC lives
in `season_projection.reported_absence_games` (pure, beside the formal cap it must stay disjoint
from); this module supplies the data and the provenance.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

log = logging.getLogger("nfl.fantasy.reported_absence")

# The curated file. IN THE REPO on purpose: git is the provenance store — who added a row, when, and
# with what source is `git log`, reviewable in the PR that adds it, and impossible to edit without a
# trace. A database row would carry none of that.
DEFAULT_OVERRIDES_PATH = Path(__file__).resolve().parent / "data" / "reported_absence_overrides.yaml"

# A regular season is 17 games. `expected_games_missed` is bounded by it on both ends: 0 would be a
# no-op row (an operator meaning "no absence" should DELETE the row, not encode one that does
# nothing), and >17 is not expressible.
SEASON_GAMES = 17

_REQUIRED_FIELDS = ("player_id", "player_name", "expected_games_missed",
                    "source_url", "entered_by", "entered_at", "review_by")

# Reason codes. Stable strings — the build log, the tests and the operator report all key on them.
REASON_MALFORMED = "MALFORMED"
REASON_EXPIRED = "EXPIRED"
REASON_DUPLICATE = "DUPLICATE"
REASON_FORMAL_STATUS = "FORMAL_STATUS_WINS"
REASON_UNMATCHED = "UNMATCHED_ON_BOARD"


def normalize_player_id(value) -> str:
    """⭐ THE ONE OWNER OF PLAYER-ID NORMALISATION ON THE OVERRIDE PATH — and it normalises BOTH
    ends of the join, never just one.

    The mirror of `export_draft_board_json._norm_player_id`, and it exists for the same measured
    reason: the Sleeper feed delivered **275 of 2,501 `player_id`s with a LEADING SPACE**
    (`' 00-0035700'`) on 2026-08-22, an exact match dropped them, and because a padded id is absent
    from the board's id set the miss classified as *"this player is not on the board"* rather than
    as a join failure. Josh Jacobs and DK Metcalf were the cost.

    ⚠️ Normalising one end and trusting the other makes correctness a property of the CALLER, and
    which end is dirty is a property of the FEED, not of our code — so it can change under us. Both
    ends go through here.

    ⏭️ NF-C9b (carded, Sprint) normalises at the INGEST so every consumer inherits it. When it
    lands this stays as a defensive no-op on already-clean ids; it does not become wrong, it becomes
    redundant, and the guard that pins it keeps a padded id from ever silently dropping again.
    """
    return str(value).strip()


@dataclass(frozen=True)
class OverrideRow:
    """One operator judgment, with the provenance that makes it auditable.

    `source_url` is REQUIRED by the spec and enforced at load: a games cap with no citation is
    indistinguishable from a guess, and the whole claim this mechanism makes is *"a human read a
    report and wrote it down"*. `review_by` is the expiry — see rule 4 in the module docstring.
    """

    player_id: str                 # NORMALISED (see `normalize_player_id`)
    player_name: str               # carried so the join is verifiable BY NAME (rule 3)
    expected_games_missed: int
    source_url: str
    entered_by: str
    entered_at: date
    review_by: date
    note: str = ""

    @property
    def games_cap(self) -> float:
        """The expected-games ceiling this row asserts. Cap-only: the projection takes the MIN of
        this and whatever the player already carries (rule 2), so this is a ceiling, never a level."""
        return float(SEASON_GAMES - self.expected_games_missed)


@dataclass(frozen=True)
class RejectedRow:
    """A row that was READ but NOT applied, with why. Never a silent drop (see the module docstring
    — a curated file whose rows quietly do nothing looks exactly like one that works)."""

    reason: str
    detail: str
    player_id: str = ""
    player_name: str = ""


@dataclass
class LoadResult:
    """What the curated file yielded: the applicable rows, and every row that was not applied.

    ⚠️ `readable` is a THIRD state, distinct from "no rows". `False` means the file could not be
    read or parsed at all — which is an operator-visible failure — whereas an empty `rows` with
    `readable=True` is the normal, healthy state of a file with nothing currently curated. Collapsing
    the two would let a broken file render as "there are no reported absences" (NF-FRESH2's
    absent-vs-null rule, on the load side)."""

    rows: list[OverrideRow] = field(default_factory=list)
    rejected: list[RejectedRow] = field(default_factory=list)
    readable: bool = True
    path: str = ""
    as_of: "date | None" = None
    season: "int | None" = None

    def caps(self) -> dict[str, float]:
        """`{normalised player_id -> expected-games ceiling}` for the rows that survived load.
        Disjointness against the formal statuses is applied LATER, at the frame, where `proj_status`
        is visible — see `season_projection.reported_absence_games`."""
        return {r.player_id: r.games_cap for r in self.rows}

    def provenance(self) -> dict[str, OverrideRow]:
        """`{normalised player_id -> the row}` for the payload stamp."""
        return {r.player_id: r for r in self.rows}


def _parse_date(value, label: str) -> date:
    """ISO date or raise. PyYAML already yields a `datetime.date` for a bare `2026-08-23`; a quoted
    string arrives as `str`. Both are accepted; anything else is a malformed row, not a guess."""
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip())
    except Exception as exc:  # noqa: BLE001 — the reason is reported, never swallowed
        raise ValueError(f"{label} is not an ISO date (got {value!r})") from exc


def _validate(raw: dict) -> OverrideRow:
    """One raw mapping → an `OverrideRow`, or `ValueError` naming exactly what is wrong.

    ⚠️ Every check here fails the row TOWARD DOING NOTHING. There is no defaulting, no coercion of a
    missing `source_url` to empty, no clamping of an out-of-range games count into range — a row we
    cannot read the way the operator meant it must not be applied at all."""
    missing = [k for k in _REQUIRED_FIELDS if raw.get(k) in (None, "")]
    if missing:
        raise ValueError(f"missing required field(s): {', '.join(missing)}")

    pid = normalize_player_id(raw["player_id"])
    if not pid:
        raise ValueError("player_id is blank after normalisation")

    url = str(raw["source_url"]).strip()
    if not url.lower().startswith(("http://", "https://")):
        # A citation that is not a link is not a citation anyone can check.
        raise ValueError(f"source_url must be an http(s) URL (got {url!r})")

    games = raw["expected_games_missed"]
    if isinstance(games, bool) or not isinstance(games, int):
        # `bool` is an `int` in Python and `True` would silently become 1 game.
        raise ValueError(f"expected_games_missed must be an integer (got {games!r})")
    if not (1 <= games <= SEASON_GAMES):
        raise ValueError(
            f"expected_games_missed must be between 1 and {SEASON_GAMES} (got {games}); "
            "0 is a no-op row — delete it instead of encoding one that does nothing")

    entered_at = _parse_date(raw["entered_at"], "entered_at")
    review_by = _parse_date(raw["review_by"], "review_by")
    if review_by < entered_at:
        raise ValueError(f"review_by ({review_by}) precedes entered_at ({entered_at}) — "
                         "the row would be expired the moment it was written")

    return OverrideRow(
        player_id=pid,
        player_name=str(raw["player_name"]).strip(),
        expected_games_missed=games,
        source_url=url,
        entered_by=str(raw["entered_by"]).strip(),
        entered_at=entered_at,
        review_by=review_by,
        note=str(raw.get("note") or "").strip(),
    )


def load_overrides(path: "str | Path | None" = None, as_of: "date | None" = None,
                   season: "int | None" = None) -> LoadResult:
    """Read + validate the curated file. THE ONLY function in this module that touches disk.

    `as_of` is the date `review_by` is measured against — INJECTED, never a hidden `date.today()`
    read inside the expiry comparison, so a test can drive both sides of the boundary and a build can
    be reproduced. Defaults to today.

    ⭐ `season` IS A LEAKAGE GATE, not a convenience. The file declares the season its judgments are
    about, and passing a `season` that does not match yields NO rows. That matters because the same
    assembly path (`build_veteran_projection`) builds BOTH the live board AND the historical
    walk-forward band panel: a 2026 operator judgment silently applied to a 2019 backtest fold would
    be an outright leak — a human who has seen how the season went, editing the past. Gating on a
    DECLARED season makes that structurally impossible rather than a thing a caller must remember,
    and it also makes the file self-expiring: it stops applying the moment the board rolls forward.

    Returns a `LoadResult` in which EVERY row of the file is accounted for: applied (`rows`) or
    rejected with a reason (`rejected`). An absent file is the normal empty state (`readable=True`,
    no rows); an UNREADABLE file is `readable=False` — a different fact, reported as such."""
    as_of = as_of or date.today()
    p = Path(path or DEFAULT_OVERRIDES_PATH)
    result = LoadResult(path=str(p), as_of=as_of)

    if not p.exists():
        # Not an error: the mechanism is inert until an operator curates something. This is the
        # by-design state on any checkout where the file has not been created.
        return result

    try:
        import yaml  # declared in pyproject; a hard failure here is reported, never swallowed
        payload = yaml.safe_load(p.read_text()) or {}
        raw_rows = payload.get("overrides") or []
        if not isinstance(raw_rows, list):
            raise ValueError("`overrides` must be a list")
        file_season = payload.get("season")
        if file_season is not None:
            file_season = int(file_season)
    except Exception as exc:  # noqa: BLE001
        log.error("[ALERT] NF-INJ-NEWS-1: reported-absence overrides at %s are UNREADABLE (%s). "
                  "NO cap is applied — the board is the pre-override board.", p, exc)
        result.readable = False
        return result

    result.season = file_season
    if season is not None and file_season is not None and int(season) != file_season:
        # The leakage gate (see the docstring). LOUD, and it yields no rows: a historical fold must
        # never see a judgment written about a different season.
        log.info("NF-INJ-NEWS-1: overrides declare season %s, this build is season %s — "
                 "no reported-absence cap applied (leakage gate).", file_season, season)
        return result

    parsed: list[OverrideRow] = []
    for i, raw in enumerate(raw_rows):
        if not isinstance(raw, dict):
            result.rejected.append(RejectedRow(
                REASON_MALFORMED, f"row {i} is not a mapping (got {type(raw).__name__})"))
            continue
        try:
            parsed.append(_validate(raw))
        except ValueError as exc:
            result.rejected.append(RejectedRow(
                REASON_MALFORMED, str(exc),
                player_id=normalize_player_id(raw.get("player_id") or ""),
                player_name=str(raw.get("player_name") or "")))

    # ⚠️ DUPLICATES REJECT THE WHOLE GROUP rather than picking one. Two rows for one player is an
    # EDITING error, and silently choosing (the first? the harshest? the newest?) would apply an
    # operator judgment nobody made. Failing toward doing nothing keeps the board explicable.
    by_id: dict[str, list[OverrideRow]] = {}
    for row in parsed:
        by_id.setdefault(row.player_id, []).append(row)

    for pid, group in by_id.items():
        if len(group) > 1:
            result.rejected.append(RejectedRow(
                REASON_DUPLICATE,
                f"{len(group)} rows share this player_id — resolve the file to exactly one; "
                "the whole group is ignored rather than one silently chosen",
                player_id=pid, player_name=group[0].player_name))
            continue
        row = group[0]
        if row.review_by < as_of:
            # Rule 4 — LOUD, not silent. A stale absence estimate is wrong in the optimistic
            # direction (the player came back) and must stop being applied.
            result.rejected.append(RejectedRow(
                REASON_EXPIRED,
                f"review_by {row.review_by} has passed (as of {as_of}) — re-source or delete this row",
                player_id=pid, player_name=row.player_name))
            continue
        result.rows.append(row)

    return result


def format_load_log(result: LoadResult) -> list[str]:
    """Human-readable build-log lines for what the curated file did. One line per APPLIED row and
    one per REJECTED row — the spec's "build-log line for every applied AND every ignored override".

    ⭐ It reports the file's own state FIRST, including the empty and unreadable cases, so a build
    log can never be silent about a mechanism that is switched on."""
    lines: list[str] = []
    if not result.readable:
        lines.append(f"[ALERT] NF-INJ-NEWS-1: overrides file UNREADABLE ({result.path}) — "
                     "no reported-absence cap applied.")
        return lines
    lines.append(
        f"NF-INJ-NEWS-1: reported-absence overrides — {len(result.rows)} applicable, "
        f"{len(result.rejected)} rejected (as of {result.as_of}; {result.path})")
    for r in result.rows:
        lines.append(
            f"  APPLY  {r.player_name} [{r.player_id}] miss {r.expected_games_missed} "
            f"⇒ games ≤ {r.games_cap:.0f} · review_by {r.review_by} · {r.source_url}")
    for j in result.rejected:
        who = f"{j.player_name} [{j.player_id}]".strip() if (j.player_name or j.player_id) else "-"
        lines.append(f"  IGNORE {who} · {j.reason}: {j.detail}")
    return lines


def emit_load_log(result: LoadResult, logger: "logging.Logger | None" = None) -> None:
    """Write `format_load_log` to a logger. A rejection goes out at WARNING so it is visible in a
    normal build log (an ignored operator judgment is something a human needs to see), an applied
    row at INFO."""
    lg = logger or log
    if not result.readable:
        for line in format_load_log(result):
            lg.warning("%s", line)
        return
    lg.info("%s", format_load_log(result)[0])
    for r in result.rows:
        lg.info("  APPLY  %s [%s] miss %d ⇒ games <= %.0f · review_by %s · %s",
                r.player_name, r.player_id, r.expected_games_missed, r.games_cap,
                r.review_by, r.source_url)
    for j in result.rejected:
        lg.warning("  IGNORE %s [%s] · %s: %s", j.player_name, j.player_id, j.reason, j.detail)
