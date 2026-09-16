"""NF-INC-0916 node 3 — the level measurement is ONE method, and it reproduces TD1's before-table.

⭐ WHY A REPRODUCTION PIN IS THE POINT OF THIS FILE. The whole value of a before/after pair is that
ONE method produced both tables. TD1 computed its before table by hand and recorded the figures
without stating the realized population's bounds; `run_nf_inc_0916_level` recovers that population
BY REPRODUCTION (four candidates scored against TD1's numbers) and then owns it. If the two ever
drift, a reader is left with two tables and no way to tell a model change from a benchmark change.

⚠️ NO LAKE HERE. The served side of the table comes entirely from the committed payload, so it is
computed live below. The realized side needs the lake, which the fast gate must never touch — so it
is pinned against the COMMITTED artifact the runner produced, which is itself evidence.

⛔ AND NO ACCEPTANCE THRESHOLD IS ASSERTED ANYWHERE IN THIS FILE. The spec is explicit that no
threshold is invented post hoc: the runner measures, the operator reads the table and rules. A test
asserting "the ratio must exceed X" would be this session choosing the bar, which is not its call.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from quant_sports_intel_models.football.nfl.fantasy import run_nf_inc_0916_level as L

_REPO = Path(__file__).resolve().parents[2]
_FAN = _REPO / "quant_sports_intel_models/football/nfl/fantasy/ablation_results"
_BEFORE_PAYLOAD = _FAN / "nf_wk_td1_before_week2_players.json"
_BEFORE_TABLE = _FAN / "nf_inc_0916_level_before.json"

#: NF-WK-TD1's recorded before-table (`docs/nf_wk_td1_touchdown_components.md`), verbatim.
#: ⛔ The SUPERSEDED 0.17-0.37 sizing (served vs the realized top-24 by realized points) is a
#: SELECTION CONFOUND and is not quoted anywhere — it selects the players who actually boomed,
#: which no unbiased projection can match.
TD1_RECORDED = {
    "QB":  {"n_served": 88,  "mean_projection": 1.345, "ratio": 0.205},
    "RB":  {"n_served": 113, "mean_projection": 2.585, "ratio": 0.465},
    "WR":  {"n_served": 179, "mean_projection": 2.057, "ratio": 0.358},
    "TE":  {"n_served": 120, "mean_projection": 1.433, "ratio": 0.402},
    "ALL": {"n_served": 500, "mean_projection": 1.901, "ratio": 0.355},
}


def test_the_committed_inputs_exist_and_are_the_before_capture():
    """Non-vacuity floor: every clause below reads one of these."""
    assert _BEFORE_PAYLOAD.exists(), "the TD1 before-capture is missing — this file is vacuous"
    payload = json.loads(_BEFORE_PAYLOAD.read_text())
    assert payload["season"] == 2026 and payload["week"] == 2
    assert len(payload["players"]) == 500


def test_the_served_side_reproduces_td1_exactly():
    """The served half needs no lake — it is arithmetic over the committed payload — so it is
    recomputed live rather than pinned, and it must match TD1 to the recorded precision."""
    payload = json.loads(_BEFORE_PAYLOAD.read_text())
    # A realized frame is required by the signature but only the served columns are read here.
    import pandas as pd
    realized = pd.DataFrame({"position": ["QB", "RB", "WR", "TE"], "fantasy_points": [1.0] * 4})
    table = L.level_table(payload, realized).set_index("pos")

    for pos, rec in TD1_RECORDED.items():
        assert int(table.loc[pos, "n_served"]) == rec["n_served"], (
            f"{pos}: served population is {table.loc[pos, 'n_served']}, TD1 recorded "
            f"{rec['n_served']} — the two tables are over different populations"
        )
        assert table.loc[pos, "mean_projection"] == pytest.approx(rec["mean_projection"], abs=5e-4)


def test_the_runner_reproduces_td1s_recorded_ratios():
    """⭐ THE REPRODUCTION PIN. The realized side needs the lake, so it is read from the artifact the
    runner produced — committed evidence rather than a live query the fast gate must not make.

    ⚠️ TOLERANCE IS 0.002 ON THE RATIO, and it is a stated allowance rather than a loose bar: the
    lake's roster partitions are refreshed several times a day, so a read taken later returns a
    fractionally larger population (+718 of 84,553 = 0.85% when this was recovered). What the pin
    proves is that the METHOD matches, not that two reads of a moving store are byte-identical.
    """
    assert _BEFORE_TABLE.exists(), (
        "the before-table artifact is missing — regenerate it:\n"
        "  uv run python -m quant_sports_intel_models.football.nfl.fantasy.run_nf_inc_0916_level "
        f"--payload {_BEFORE_PAYLOAD.relative_to(_REPO)} --label BEFORE "
        f"--out {_BEFORE_TABLE.relative_to(_REPO)}"
    )
    rows = {r["pos"]: r for r in json.loads(_BEFORE_TABLE.read_text())["level"]}
    for pos, rec in TD1_RECORDED.items():
        assert rows[pos]["ratio"] == pytest.approx(rec["ratio"], abs=2e-3), (
            f"{pos}: this runner reads {rows[pos]['ratio']:.4f}, TD1 recorded {rec['ratio']} — "
            "the method has drifted from the one that produced the before table, so an after "
            "table computed with it would not be comparable"
        )


def test_the_realized_population_bounds_are_pinned():
    """⛔ MOVING THESE WHILE A BEFORE/AFTER PAIR IS LIVE CONFOUNDS THE READING: a ratio that changed
    because the benchmark moved is indistinguishable, in the table, from one that changed because
    the model improved."""
    assert L.REALIZED_SEASONS == (2016, 2025), (
        f"the realized population is {L.REALIZED_SEASONS}; the before table was computed over "
        "(2016, 2025) — completed seasons only"
    )
    assert L.LAST_REG_WEEK == 18


def test_the_realized_side_excludes_byes_and_the_postseason():
    """Both exclusions are load-bearing and they point in OPPOSITE directions, which is why each
    needs saying: a bye is not a player-week anyone could score in (including it would drag the
    benchmark down and FLATTER the projection), and a 31-row championship week is a different
    population from a slate."""
    import inspect

    src = inspect.getsource(L.realized_population)
    assert '_has_game' in src and "LAST_REG_WEEK" in src


def test_the_zero_atom_read_finds_the_signature_in_the_before_payload():
    """⭐ THE DISCRIMINATING READ. A uniform scale error and an inflated zero atom both depress the
    mean; they are different defects with different fixes. Ten of ten top projections carrying a
    ZERO p10 against plausible ceilings is the atom, and it is what says the conditional-on-playing
    half of the hurdle was intact."""
    payload = json.loads(_BEFORE_PAYLOAD.read_text())
    atom = L.zero_atom_read(payload, top_n=10)
    assert atom["n_top_with_zero_p10"] == 10, (
        "the before-capture no longer shows the zero-atom signature — either the capture was "
        "replaced or this read has drifted"
    )
    named = {r["name"]: r for r in atom["rows"]}
    mc = named.get("Christian McCaffrey")
    assert mc is not None, "the recorded example row is not in the top ten any more"
    # The row the record quotes: 0.00 / 10.45 / 27.17.
    assert mc["fpP10"] == pytest.approx(0.0)
    assert mc["fpP90"] == pytest.approx(27.17, abs=5e-3)


def test_the_atom_read_is_two_sided():
    """A read that cannot come back clean would say nothing about a fixed model."""
    healthy = {"players": [
        {"name": f"p{i}", "pos": "RB", "fpPpr": 10.0 - i, "fpP10": 2.0, "fpP90": 25.0}
        for i in range(10)]}
    assert L.zero_atom_read(healthy, top_n=10)["n_top_with_zero_p10"] == 0
