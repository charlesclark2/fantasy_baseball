"""NF-WK-ACC1 part 1 — the league's ANY-FUMBLE rule is applied on the recap (PM ruling, option D).

⭐ WHAT THE RULING WAS, because these guards only make sense against it (2026-09-18, verbatim):
"NF-C0e rejected PROJECTING fumbles, a forecast we measurably cannot make with skill; the recap
scores a completed week, where a fumble count is a recorded fact. Different question, different
answer." So `fum` lands in `projection_fields.STAT_FIELD` (the key set the realized map may name)
and NOWHERE else — no projection column, no TS mirror entry — and the ratified consequence is that
ONE league rule reads APPLIED on the recap and CAPTURED on the season board.

Each clause below pins one half of that: the term is genuinely applied where it is claimed, it is
genuinely absent where NF-C0e requires absence, the paid-set diff is exactly the one the PM
accepted, and the disclosure narrows only when the term is really being scored.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.backend.services import (
    projection_fields,
    realized_stat_fields,
    weekly_recap,
)

ROOT = Path(__file__).resolve().parents[2]

#: The league under measurement pays BOTH fumble rules, as the operator's real Sleeper league does
#: (`fum` −1 and `fum_lost` −1, so a lost fumble is charged twice — that is the league's own choice,
#: not a double-count of ours).
#: ⚠️ `fum` IS SLEEPER'S OWN RAW KEY — the importer maps `fum_lost` onto the canonical
#: `fumbles_lost` and carries `fum` through unmapped, because no canonical term existed for it. So a
#: SAVED league record holds exactly this mix, and a fixture that "tidied" `fum` into a canonical
#: spelling would be testing a payload no import produces.
_SCORING = {"per_stat": {"rush_yds": 0.1, "fum": -1.0, "fumbles_lost": -2.0}}
_CFG = {"scoring": _SCORING}


def _row(**over):
    """One realized line: 100 rushing yards, two fumbles, one of them lost on a rush."""
    row = {"player_display_name": "Real Player", "position": "RB", "team": "ATL",
           "rushing_yards": 100, "fumbles_total": 2, "rushing_fumbles_lost": 1}
    row.update(over)
    return row


def _fetched(platform_pts=107.0):
    return {
        "season": 2025, "week": 1, "platform": "sleeper", "leagueId": "P1",
        "startingSlots": ["RB"],
        "teams": [{
            "teamKey": "1", "teamName": "A", "matchupId": 1, "platformTotal": platform_pts,
            "lineup": [{"slot": "RB", "seat": 0, "playerKey": "9", "empty": False,
                        "name": "Real Player", "position": "RB", "team": "ATL",
                        "platformPts": platform_pts}],
        }],
    }


def _score(rows, **kw):
    return weekly_recap.score_week(fetched=_fetched(**kw), realized_rows=rows, cfg=_CFG)


def _verdicts(scored):
    return {t["key"]: t["verdict"] for t in scored["coverage"]["terms"]}


# ── the term is applied, with the right column behind it ──────────────────────────────────────────

def test_the_any_fumble_rule_is_applied_and_charged_from_the_total_fumble_column():
    """10.0 rushing − 1.0 × 2 fumbles − 2.0 × 1 lost fumble = 6.0. Both rules, both charged."""
    scored = _score([_row()])
    seat = scored["teams"][0]["seats"][0]
    assert _verdicts(scored)["fum"] == "applied"
    assert seat["points"] == pytest.approx(6.0), seat
    # …and the any-fumble rule is what moved it: the same line with the column absent scores 8.0
    # (the two tests below own the captured half and the column identity).
    assert _verdicts(scored)["fumbles_lost"] == "applied"


def test_the_two_fumble_terms_read_different_columns_and_cannot_collapse_into_one():
    """`fum` counts EVERY fumble; `fumbles_lost` counts the per-phase lost ones. A row that fumbled
    twice and lost neither must still be charged the any-fumble rule and nothing else."""
    scored = _score([_row(fumbles_total=2, rushing_fumbles_lost=0)])
    assert scored["teams"][0]["seats"][0]["points"] == pytest.approx(8.0)
    assert realized_stat_fields.REALIZED_STAT_SOURCE["fum"] == ("fumbles_total",)
    assert "fumbles_total" not in realized_stat_fields.REALIZED_STAT_SOURCE["fumbles_lost"]


def test_the_lake_read_selects_the_column_the_term_needs():
    """A term whose column the query forgot to select resolves CAPTURED and scores zero, silently
    (the NF-C0e wired-≠-invoked shape) — so the derived column list is the real guard."""
    assert "fumbles_total" in realized_stat_fields.REALIZED_STAT_COLUMNS


def test_a_week_whose_line_does_not_carry_the_column_reports_captured_not_applied():
    """"We could not score this" must never wear the APPLIED label (NF1.7(a)). Absent column ⇒
    CAPTURED ⇒ the disclosure keeps naming fumbles, which is the honest state."""
    scored = _score([{k: v for k, v in _row().items() if k != "fumbles_total"}])
    assert _verdicts(scored)["fum"] == "captured"
    assert scored["teams"][0]["seats"][0]["points"] == pytest.approx(8.0)


# ── the disclosure narrows, and only for the right reason ─────────────────────────────────────────

def test_the_disclosure_no_longer_names_fumbles_once_the_term_is_scored():
    applied = _score([_row()])
    assert "fumble" not in (applied.get("itemisationGapNote") or "").lower()

    # …and it DOES name them while the term is only captured, with a measured gap present.
    captured = weekly_recap.itemisation_gap_note(
        {"terms": [{"key": "fum", "verdict": "captured", "weight": -1.0}]}, max_gap=4.0)
    assert captured and "fumbles" in captured


def test_the_measured_gap_rule_still_governs_the_narrowed_disclosure():
    """#1155: a league whose remaining captured terms scored NOTHING gets no sentence at all — the
    narrowing must not be bought by dropping that rule."""
    coverage = {"terms": [{"key": "pass_td_40p", "verdict": "captured", "weight": 2.0}]}
    assert weekly_recap.itemisation_gap_note(coverage, max_gap=0.0) is None
    assert weekly_recap.itemisation_gap_note(coverage, max_gap=3.0)


# ── the entitlement checkpoint: the paid-set diff the PM accepted ─────────────────────────────────

def test_the_paid_set_gains_exactly_fum_any_and_loses_nothing():
    """The ruling's recorded diff: +{fumAny}, nothing removed. Derived, so this reads the real set."""
    paid = projection_fields.PAID_PLAYER_FIELDS
    without = frozenset(
        v for k, v in projection_fields.STAT_FIELD.items() if k != "fum"
    ) | projection_fields.PAID_SCORING_FIELDS
    assert paid - without == {"fumAny"}
    assert without - paid == set()
    assert projection_fields.STAT_FIELD["fum"] == "fumAny"


def test_the_realized_only_set_equals_the_mechanical_rule_and_cannot_be_widened_by_hand():
    """⭐ THE GUARD ON THE EXCUSE. `REALIZED_ONLY_KEYS` is what lets the Python map hold a key its
    TypeScript mirror does not (NF-EPIC1's parity guard reads it), so an unchecked hand-written set
    there would be a hole in that parity guard rather than a note in it.

    The rule: a key is realized-only exactly when the REALIZED map names it and the PROJECTION
    profile does not. Declared in `projection_fields` only because deriving it there would drag
    `NFL_PROFILE` onto the Lambda's cold-start path (the PERF finding); asserted here, where the
    import is free.
    """
    from quant_sports_intel_models.football.nfl.fantasy import league_presets as presets

    mechanical = {k for k in realized_stat_fields.REALIZED_STAT_SOURCE
                  if k not in presets.NFL_PROFILE.stat_columns}
    assert projection_fields.REALIZED_ONLY_KEYS == mechanical, (
        "REALIZED_ONLY_KEYS drifted from the rule that justifies it: "
        f"declared-not-derived={projection_fields.REALIZED_ONLY_KEYS - mechanical}, "
        f"derived-not-declared={mechanical - projection_fields.REALIZED_ONLY_KEYS}")
    assert projection_fields.REALIZED_ONLY_KEYS == {"fum"}, (
        "the set changed size — that needs a PM ruling, like `fum`'s, not an edit")
    # Every member must really be in the scorer's map, or the parity guard's excuse names nothing.
    for key in projection_fields.REALIZED_ONLY_KEYS:
        assert key in projection_fields.STAT_FIELD


def test_a_realized_only_field_is_never_named_as_a_withheld_stat():
    """It cannot be withheld because it was never published — and NF-INJ1-C's whole point is that a
    withheld value and a never-served one must stay distinguishable."""
    from app.backend.services import stat_line_suppression

    counting = stat_line_suppression.counting_stat_fields()
    assert "fumAny" not in counting
    assert "passYds" in counting, "the suppression universe is empty — this guard would be vacuous"


def test_no_payload_emits_the_new_paid_field_so_the_addition_is_inert():
    """Why the diff is safe to accept: the field is in the paid SET but nothing serves it, so no
    field changes hands. If a payload ever carries `fumAny`, this goes red and the entitlement
    question is live again — which is the point of pinning it."""
    sources = ("quant_sports_intel_models/football/nfl/fantasy/export_draft_board_json.py",
               "quant_sports_intel_models/football/nfl/fantasy/weekly_serving.py")
    emitted: set[str] = set()
    for src in sources:
        p = ROOT / src
        assert p.is_file(), f"{src} moved — this guard reads nothing until it is repointed"
        emitted |= set(re.findall(r"[\"'](\w+)[\"']", p.read_text()))
    # ⚠️ NON-VACUITY FIRST. A path typo, a rename, or a payload that stopped naming its fields
    # would leave `emitted` empty and pass this on nothing (NF1.7(a)) — so prove the scan can SEE a
    # paid field before trusting that it cannot see this one.
    assert {"passYds", "rushYds"} <= emitted, "the scan found no known paid field — it is blind"
    assert "fumAny" not in emitted, "a payload now emits fumAny — re-read the entitlement diff"


# ── the half NF-C0e owns: no projection anywhere ──────────────────────────────────────────────────

def test_the_term_gained_no_projection_column_and_no_ts_mirror_entry():
    """Option D's whole content. A projection column here would reverse a measured rejection."""
    from quant_sports_intel_models.football.nfl.fantasy import league_presets as presets

    assert "fum" not in presets.NFL_PROFILE.stat_columns
    ts = (ROOT / "frontend/lib/league-config.ts").read_text()
    block = re.search(r"export const STAT_FIELD: Record<string, string> = \{(.*?)\n\}", ts, re.S)
    assert block, "could not locate STAT_FIELD in league-config.ts"
    assert "fum:" not in block.group(1).replace(" ", ""), "the TS mirror gained the term"


#: The two surfaces that render a captured term to a user. ⚠️ THE STRING IS DUPLICATED between them
#: (a pre-existing drift surface, out of this story's scope) — which is exactly why both are pinned:
#: a reword that reached one and not the other is the failure this guard exists to catch.
_CAPTURED_LABEL_SURFACES = (
    "frontend/components/fantasy/league-settings-editor.tsx",
    "frontend/components/fantasy/league-import.tsx",
)


@pytest.mark.parametrize("surface", _CAPTURED_LABEL_SURFACES)
def test_the_captured_label_says_not_projected_rather_than_not_supported(surface):
    """The PM's copy requirement on ruling ①, made mechanical (2026-09-18).

    With `fum` applied on the recap and captured on the board, the board's wording is what keeps
    the two surfaces reading as consistent rather than contradictory: "we do not PROJECT this stat"
    is a claim about forecasting and stays true, while a bare "not supported" would be flatly
    contradicted by the recap itemising the same rule a week later.
    """
    src = (ROOT / surface).read_text()
    # ⚠️ ANCHOR ON `VERDICT_COPY`, NOT ON A BARE `captured:`. Both surfaces also carry a
    # `VERDICT_STYLE` map whose `captured:` entry is a Tailwind class list — the first cut of this
    # guard matched THAT and failed for a reason that had nothing to do with the copy (and its RED
    # proof then "passed" on an already-failing clause, which is the trap, not the proof).
    block = re.search(r"const VERDICT_COPY: Record<string, string> = \{(.*?)\n\}", src, re.S)
    assert block, f"{surface}: could not find VERDICT_COPY"
    label = re.search(r"captured:\s*\"([^\"]+)\"", block.group(1))
    assert label, f"{surface}: VERDICT_COPY has no captured label"
    text = label.group(1).lower()
    assert "project" in text, f"{surface}: the captured label no longer names PROJECTION: {text!r}"
    for banned in ("not supported", "unsupported", "we can't score", "we cannot score"):
        assert banned not in text, f"{surface}: {banned!r} contradicts the recap, which scores it"


def test_the_season_board_still_calls_the_rule_captured_the_ratified_split():
    """⭐ THE RATIFIED CONSEQUENCE, pinned so nobody "tidies" the two surfaces into agreement: the
    projection profile resolves the SAME rule as CAPTURED while the recap resolves it as APPLIED.
    Two surfaces, two maps, both true — and a change that made them agree would mean either the
    board started projecting fumbles or the recap stopped scoring a recorded fact.
    """
    from quant_sports_intel_models.fantasy_engine import league_config as lc
    from quant_sports_intel_models.fantasy_engine import settings as st
    from quant_sports_intel_models.football.nfl.fantasy import league_presets as presets

    _, report = st.resolve_scoring(lc.ScoringRules(per_stat={"fum": -1.0}), presets.NFL_PROFILE)
    assert {t.key: t.verdict for t in report.terms}["fum"] == st.CAPTURED
    assert _verdicts(_score([_row()]))["fum"] == "applied"
