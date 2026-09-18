"""The committed week-1 realized capture, and the ONE adaptation that brings it up to contract.

⭐ WHY THIS MODULE EXISTS AT ALL — it is the repo's own "one logical thing, many owners" lesson
(INC-30 crontab / INC-36 concurrency / INC-38 per-caller flags) applied to a test helper. Two suites
build a season artifact from the same committed capture:

  * `test_nf_wk_rc1_contract.py` — the publish-time contract and the season artifact
  * `test_nf_wvr1_fact_columns.py` — the waiver fact columns computed over that season artifact

NF-WK-ACC1 ruling ① widened `realized_week.required_columns()` with `fumbles_lost_total`, which put
BOTH suites' fixtures one column behind the contract at once. A copy of the adaptation in each file
is a second owner of one rule: the next widening fixes one and silently leaves the other asserting
yesterday's contract. So the adaptation lives here, once.

⛔ THIS IS AN ADAPTATION, NOT A CAPTURE, and the distinction is load-bearing. `build_season` gates
every served week on `required_columns()`, so a week published before a column existed is legitimately
`columns_behind` until it is republished — that is real, correct behaviour, and it is why NF-WK-ACC1's
closeout lists a 2026 republish as an operator step. `test_nf_wk_rc1_contract.py::
test_the_authentic_capture_is_columns_behind_until_it_is_republished` pins that behaviour on the
UNTOUCHED capture. This module exists so the OTHER clauses can test season logic, joins and ordering
rather than all failing on one contract gap.
"""

from __future__ import annotations

import copy
import gzip
import json
from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "nf_wk_rc1_realized_2026_wk1_stored.json.gz"

#: The per-phase lost-fumble columns ruling ① superseded as the scoring source and kept as declared
#: diagnostics (`realized_stat_fields.REALIZED_DIAGNOSTIC_COLUMNS`).
PER_PHASE_LOST_FUMBLES = ("sack_fumbles_lost", "rushing_fumbles_lost", "receiving_fumbles_lost")


def stored() -> dict:
    """The committed capture, exactly as it was served (columnar)."""
    return json.loads(gzip.decompress(FIXTURE.read_bytes()))


def week1() -> tuple[dict, list[dict]]:
    """`(manifest, players)` for the captured week, untouched."""
    fx = stored()
    players = [dict(zip(fx["columns"], r)) for r in fx["rows"]]
    return copy.deepcopy(fx["manifest"]), players


def columns_the_capture_predates() -> list[str]:
    """Columns today's contract demands that the CAPTURE does not carry.

    ⭐ DERIVED, never a literal: empty whenever the capture is current, and it grows on its own the
    next time the contract widens — so no caller can silently rot into asserting an old contract.
    """
    from quant_sports_intel_models.football.nfl.fantasy import realized_week as RW

    return sorted(set(RW.required_columns()) - set(stored()["manifest"]["columns"]))


def bring_up_to_contract(man: dict, players: list[dict]) -> tuple[dict, list[dict]]:
    """The captured week ADAPTED to today's column contract (see the module docstring).

    The fill for `fumbles_lost_total` is the PER-PHASE SUM, which is exact on 1,116 of the capture's
    1,118 rows and undercounts only the two return-fumble rows NF-WK-ACC1 ruling ① names.

    ⚠️ THE CONSEQUENCE A CALLER MUST KNOW, because it decides what a passing clause proves: filling
    from the per-phase sum makes the two lost-fumble readings AGREE BY CONSTRUCTION on every adapted
    row. So a clause that compares our scorer against nflverse's own `fantasy_points_ppr` stays an
    exact identity here, and that identity is NOT evidence that ruling ① agrees with nflverse — it
    does not. Measured on the 2025 REG lake: the two readings differ on 36 rows and nflverse's PPR
    sides with the PER-PHASE reading on every one of them, while Sleeper charges on the total. A
    clause that wants to exercise that divergence must inject a row where the readings differ; the
    adapted capture structurally cannot show it.
    """
    missing = columns_the_capture_predates()
    if not missing:
        return man, players
    for p in players:
        for column in missing:
            if column == "fumbles_lost_total":
                p[column] = float(sum(float(p.get(c) or 0.0) for c in PER_PHASE_LOST_FUMBLES))
            else:
                p.setdefault(column, 0.0)
    return {**man, "columns": sorted(set(man["columns"]) | set(missing))}, players
