"""NF-EPIC 1 — THE PARITY GUARD between the Lambda scorer and `fantasy_engine`.

═══════════════════════════════════════════════════════════════════════════════════════════════════
⭐ WHY THIS FILE IS LOAD-BEARING (PM, 2026-08-10, Option C)
═══════════════════════════════════════════════════════════════════════════════════════════════════

Option C made the raw stat line PAID and moved league scoring onto the server, which created a THIRD
implementation of one scoring policy:

    fantasy_engine/{scoring,vor}.py   pandas/numpy   → the SHIPPED PRESET BOARDS (the authority)
    frontend/lib/league-scoring.ts    browser port   → instant re-score on edit
    app/backend/services/league_scoring.py           → bare Python, runs inside the API Lambda

The PM named the risk directly: *"a drift means a free user's league score silently disagrees with
the board."* Nothing else would surface that — the board still renders, the numbers are still
plausible, no error is raised anywhere. So this guard runs BOTH engines over the SAME inputs and
asserts they agree field-for-field.

⚠️ SAME INPUTS IS THE WHOLE DESIGN. `fantasy_engine` normally scores the model's raw frame while the
Lambda scores the PUBLISHED PAYLOAD (already rounded to 1dp by the exporter). Comparing the shipped
board against a payload-scored board would fold INPUT ROUNDING into the diff and could only ever
prove "close enough", which is not a guard — it is a tolerance nobody can defend. So the payload
rows are lifted into a DataFrame under `NFL_PROFILE`'s own column names and BOTH engines score that
identical frame. Then equality is exact, and any diff is a real algorithmic drift.

⛔ ANCHORED IN ITS OWN CLAUSE. Nothing here is bolted onto an older story's guard (the E9.60
coupling trap): these tests fail only for NF-EPIC 1's property.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.backend.services import league_scoring, projection_fields

pd = pytest.importorskip("pandas", reason="fantasy_engine needs pandas; the Lambda scorer does not")

from quant_sports_intel_models.fantasy_engine.scoring import score_players  # noqa: E402
from quant_sports_intel_models.fantasy_engine.vor import build_board as engine_build_board  # noqa: E402
from quant_sports_intel_models.football.nfl.fantasy.league_presets import (  # noqa: E402
    NFL_PROFILE,
    PRESETS,
)

_FIXTURE = Path(__file__).parent / "fixtures" / "nf_epic1_projection_rows.json"


# ── the shared input ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def payload_rows() -> list[dict]:
    """Real published projection rows — the exact shape both engines must agree on.

    ⚠️ REAL exporter output, never hand-written JSON (NF-C0e): a fixture an author typed cannot
    disconfirm the author's own assumption about which fields the payload carries.
    """
    rows = json.loads(_FIXTURE.read_text())
    assert len(rows) >= 50, "a parity fixture this thin cannot exercise replacement levels"
    return rows


def _payload_to_engine_frame(rows: list[dict]) -> pd.DataFrame:
    """Lift payload rows into the frame `fantasy_engine` expects, renaming nothing else.

    Every value is carried ACROSS UNCHANGED — this is a column-name translation, not a
    transformation. If it did any arithmetic the parity result would be about this function.
    """
    records = []
    for r in rows:
        rec: dict = {NFL_PROFILE.position_column: r.get("pos")}
        for stat_key, payload_field in projection_fields.STAT_FIELD.items():
            column = NFL_PROFILE.stat_columns.get(stat_key)
            if column:
                rec[column] = r.get(payload_field)
        rec[NFL_PROFILE.base_points_column] = r.get(league_scoring.BASE_POINTS_FIELD)
        rec[NFL_PROFILE.base_sd_column] = r.get(league_scoring.BASE_SD_FIELD)
        rec[NFL_PROFILE.base_p10_column] = r.get(league_scoring.BASE_P10_FIELD)
        rec[NFL_PROFILE.base_p90_column] = r.get(league_scoring.BASE_P90_FIELD)
        rec["_payload_id"] = r.get("id")
        records.append(rec)
    return pd.DataFrame(records)


def _engine_board(rows: list[dict], config) -> dict[str, dict]:
    """Score `rows` through `fantasy_engine` + the exporter's rounding → `{player_id: fields}`.

    `_fnum`'s `round(x, 1)` is applied here because the shipped boards go through it — matching the
    engine without matching the exporter would compare against numbers no caller has ever seen.
    """
    frame = _payload_to_engine_frame(rows)
    scored = score_players(frame, config, NFL_PROFILE)
    board = engine_build_board(scored, config, NFL_PROFILE)
    out: dict[str, dict] = {}
    for _, r in board.iterrows():
        out[str(r["_payload_id"])] = {
            "pts": round(float(r["league_points"]), 1),
            "repl": round(float(r["replacement_points"]), 1),
            "vor": round(float(r["vor"]), 1),
            "posRank": int(r["positional_rank"]),
            "ovrRank": int(r["overall_rank"]),
            "ptsP10": round(float(r["league_points_p10"]), 1),
            "ptsP90": round(float(r["league_points_p90"]), 1),
            "vorP10": round(float(r["vor_p10"]), 1),
            "vorP90": round(float(r["vor_p90"]), 1),
        }
    return out


def _lambda_board(rows: list[dict], config) -> dict[str, dict]:
    """The same board through the Lambda scorer → `{player_id: fields}`."""
    built = league_scoring.build_board(rows, config.to_dict(), projection_fields.STAT_FIELD)
    return {
        str(p["id"]): {k: p[k] for k in
                       ("pts", "repl", "vor", "posRank", "ovrRank",
                        "ptsP10", "ptsP90", "vorP10", "vorP90")}
        for p in built["players"]
    }


def _rosterable_rows(rows: list[dict], config) -> list[dict]:
    """Pre-filter to the positions the league can start.

    The Lambda scorer applies this filter (a league with no kicker slot gets no kicker board);
    `fantasy_engine.build_board` ranks whatever frame it is handed. Applying it to BOTH inputs is
    what keeps the comparison about the scoring math instead of about the filter.
    """
    rosterable: set[str] = set()
    for slot in config.roster:
        if slot.count > 0:
            rosterable.update(slot.eligible)
    return [r for r in rows
            if league_scoring.normalize_position(r.get("pos")) in rosterable]


# ── the guard ────────────────────────────────────────────────────────────────────────────────────

#: Every shipped preset, at both league sizes. Superflex is the one that exercises the flex
#: allocation hardest (QB-eligible spots pull QBs into starting lineups and QB replacement drops
#: deep), so a drift in the most subtle part of `vor.py` cannot hide behind the simple presets.
_PRESET_CASES = [(name, size) for name in sorted(PRESETS) for size in (10, 12)]


@pytest.mark.parametrize("preset,size", _PRESET_CASES)
def test_the_lambda_scorer_agrees_with_fantasy_engine(payload_rows, preset, size):
    """THE guard: both engines, same rows, same config → identical boards.

    Exact equality, no tolerance. A tolerance here would be a place for drift to live.
    """
    config = PRESETS[preset](n_teams=size)
    rows = _rosterable_rows(payload_rows, config)

    engine = _engine_board(rows, config)
    lambda_ = _lambda_board(rows, config)

    assert lambda_.keys() == engine.keys(), "the two engines scored different player sets"
    assert engine, "vacuous: the engine produced no rows (NF1.7 (a))"

    mismatches = {
        pid: {k: (v, engine[pid][k]) for k, v in fields.items() if v != engine[pid][k]}
        for pid, fields in lambda_.items()
        if fields != engine[pid]
    }
    assert not mismatches, (
        f"{preset}/{size}: {len(mismatches)} players differ between the Lambda scorer and "
        f"fantasy_engine. First few: {dict(list(mismatches.items())[:3])}"
    )


def test_the_parity_fixture_actually_exercises_the_paid_fields(payload_rows):
    """Anti-vacuity: a fixture whose stat line is empty would make the guard above pass on nothing.

    The NF1.7 (a) lesson — a check that cannot fail is not a check. If the fixture carried no
    scorable stats every arm would score 0 and agree trivially.
    """
    present = projection_fields.paid_fields_present({"players": payload_rows})
    assert len(present) >= 20, (
        f"the parity fixture carries only {len(present)} scorable fields; it cannot distinguish "
        "two scoring implementations"
    )
    scoring_stats = {f for f in present if f not in projection_fields.PAID_SCORING_FIELDS}
    assert scoring_stats, "no raw stat line in the fixture — the guard would be vacuous"


def test_a_deliberate_drift_is_caught(payload_rows):
    """RED-proof, in-process: break ONE weight and confirm the comparison notices.

    ⭐ Proves the guard can FAIL. A parity assertion that has only ever been run against two
    agreeing implementations is indistinguishable from one comparing something to itself — this is
    the repo's vacuous-guard class, and the reason it is checked rather than assumed.
    """
    config = PRESETS["full_ppr"](n_teams=12)
    rows = _rosterable_rows(payload_rows, config)
    engine = _engine_board(rows, config)

    drifted = config.to_dict()
    drifted["scoring"]["per_stat"]["rec_yds"] = (
        float(drifted["scoring"]["per_stat"].get("rec_yds") or 0.1) * 2 + 0.05
    )
    built = league_scoring.build_board(rows, drifted, projection_fields.STAT_FIELD)
    drifted_board = {str(p["id"]): p["pts"] for p in built["players"]}

    differs = sum(1 for pid, pts in drifted_board.items() if pts != engine[pid]["pts"])
    assert differs > 0, "the parity comparison did not notice a changed scoring weight"


# ── the name join, which moved server-side with the scorer ───────────────────────────────────────

#: Real awkward cases. The last one is the ORDERING trap called out in `league_scoring`: strip
#: punctuation before filtering suffix tokens and "iv" reads as a generational suffix, deleting a
#: real initial.
_NAME_CASES = [
    ("Ja'Marr Chase", "jamarr chase"),
    ("Odell Beckham Jr.", "odell beckham"),
    ("Robert Griffin III", "robert griffin"),
    ("Amon-Ra St. Brown", "amonra st brown"),
    ("José Álvarez", "jose alvarez"),
    ("A.J. Brown", "aj brown"),
    ("I.V. Jones", "i jones"),
]


@pytest.mark.parametrize("raw,expected", _NAME_CASES)
def test_the_server_name_normalizer_matches_the_browser_rules(raw, expected):
    """The roster join must fold names identically to the TS version.

    A divergence here does not error — it silently fails to match, and the user sees their players
    vanish from a league that worked yesterday.
    """
    assert league_scoring.normalize_player_name(raw) == expected
