#!/usr/bin/env python3
"""Backfill the EXPECTED-GAMES field into the captured track-record season fixture.

    uv run python frontend/e2e/fixtures/build-track-record-proj-games.py

WHY THIS EXISTS — the same one case the E9.63 "⛔ do not hand-write a fixture" rule does not cover,
and the third time this repo has hit it (E9.59's pricing fixture for a day, NF-TR1's `claim` block,
now this): `projGames` does not exist in production yet. It lands at the operator's post-merge
`--publish`, so there is nothing to capture, and the alternative — typing plausible-looking games
figures into the fixture by hand — would be exactly the fabrication the E2E spec is supposed to
catch. A spec asserting "13.9 games renders" against a 13.9 the test author invented proves nothing
about the pipeline that has to produce it.

So NOTHING here is authored either. Every other byte stays the verbatim prod capture; `projGames`
is joined in per player from the SAME served NF1.5 projection artifact the real export reads:

    quant_sports_intel_models/football/nfl/fantasy/artifacts/nf1_5_season_projections_2025.parquet

⚠️ THAT ARTIFACT IS GITIGNORED, so this script runs only in a checkout that has built (or holds) it
— which is why the RESULT is committed and the script is not part of any gate. Same standing as
`capture-fixtures.mjs`, whose `--check` is deliberately not wired into CI for the same reason: a
fixture is a snapshot taken on the operator's cadence, not a build step.

⚠️ RE-CAPTURE AFTER THE PUBLISH. Once the operator has run the export with `--publish`, the real
payload carries `projGames` and `npm run e2e:capture` supersedes this script entirely. Delete it
then, the way E9.59's synthetic pricing fixture was deleted the day its route went live.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_REPO = _HERE.parents[3]
sys.path.insert(0, str(_REPO))

import pandas as pd  # noqa: E402

SEASON = 2025
FIXTURE = _HERE.parent / "api" / f"fantasy-nfl-track-record-{SEASON}.json"
ARTIFACT = (
    _REPO
    / "quant_sports_intel_models/football/nfl/fantasy/artifacts"
    / f"nf1_5_season_projections_{SEASON}.parquet"
)


def main() -> int:
    if not ARTIFACT.is_file():
        print(
            f"no served projection artifact at {ARTIFACT}.\n"
            f"It is gitignored — run this from a checkout that has it (build it with "
            f"`run_nf1_5.py --mode build`), or leave the committed fixture as it is.",
            file=sys.stderr,
        )
        return 1

    proj = pd.read_parquet(ARTIFACT)
    if "proj_games" not in proj.columns:
        print(f"{ARTIFACT.name} carries no `proj_games` column", file=sys.stderr)
        return 1
    # Same rounding the export applies (`_fnum(..., 1)`), so the committed fixture holds the bytes
    # a real capture would — not a differently-rounded near-miss that a byte comparison would flag.
    games = {
        str(pid): (None if pd.isna(g) else round(float(g), 1))
        for pid, g in zip(proj["player_id"], proj["proj_games"])
    }

    rows = json.loads(FIXTURE.read_text())
    matched = 0
    for row in rows:
        row["projGames"] = games.get(str(row["playerId"]))
        # ⚠️ Insert it where the export emits it (straight after `ourPoints`) rather than appending:
        # the fixture is compared against a future real capture, and key ORDER is part of "the same
        # bytes". Python dicts preserve insertion order and `json.dump` follows it.
        ordered = {}
        for key, value in row.items():
            if key == "projGames":
                continue
            ordered[key] = value
            if key == "ourPoints":
                ordered["projGames"] = row["projGames"]
        row.clear()
        row.update(ordered)
        matched += row["projGames"] is not None

    if matched == 0:
        print("joined ZERO players — the id spaces do not line up; refusing to write", file=sys.stderr)
        return 1

    FIXTURE.write_text(json.dumps(rows, indent=2) + "\n")
    print(f"wrote {FIXTURE.name}: {matched}/{len(rows)} rows carry projGames")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
