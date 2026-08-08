#!/usr/bin/env python3
"""E9.46 — regenerate the featured-player E2E fixture from the LIVE served board.

    uv run python frontend/e2e/fixtures/build-featured-player.py

WHY THIS EXISTS RATHER THAN `npm run e2e:capture`. E9.63's rule is ⛔ do not hand-write a fixture,
because a hand-written one encodes the assumption under test. This hits the one case that rule does
not cover, the same one `build-track-record-claim.py` hit at NF-TR1: the endpoint is not deployed
yet, so there is nothing to capture. It 401s until the operator runs `deploy.sh` AND sets the
API-Gateway authorizer to NONE.

⭐ NOTHING HERE IS AUTHORED. The fixture is the output of the SHIPPING selector
(`fantasy_public._featured_payload`) run over the REAL served artifact
(`s3://credence-prod-s3-api-cache/fantasy/nfl/2026/{projections,manifest}.json`) — so it is
generated output of the code under test, not a guess about it. The selection is deterministic, so
re-running against the same artifact reproduces it byte-for-byte.

⚠️ RE-CAPTURE ONCE THE ROUTE IS LIVE. After the deploy and the gateway change, add
`/fantasy/nfl/featured-player` to `capture-fixtures.mjs`'s TARGETS and delete this script — exactly
as E9.59's synthetic pricing fixture was deleted the day its route went live.

⚠️ THE CONTENT CHANGES WHENEVER THE BOARD IS RE-PUBLISHED (a different player can win the largest
gap). That is expected and is not a test failure: `home-positioning.spec.ts` asserts against the
payload's OWN values, never a hardcoded name or number.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
BUCKET = "credence-prod-s3-api-cache"
PREFIX = "fantasy/nfl/2026"
OUT = REPO / "frontend/e2e/fixtures/api/fantasy-nfl-featured-player.json"


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        season_dir = Path(tmp) / "2026"
        season_dir.mkdir()
        for name in ("projections.json", "manifest.json"):
            r = subprocess.run(
                ["aws", "s3", "cp", f"s3://{BUCKET}/{PREFIX}/{name}",
                 str(season_dir / name), "--region", "us-east-1"],
                capture_output=True, text=True,
            )
            if r.returncode:
                print(f"FAILED to read s3://{BUCKET}/{PREFIX}/{name}\n{r.stderr}", file=sys.stderr)
                return 1

        # Point the shipping loader at the downloaded copy, then call the shipping selector.
        os.environ["FANTASY_BOARD_DIR"] = tmp
        sys.path.insert(0, str(REPO))
        from app.backend.routers import fantasy, fantasy_public  # noqa: E402

        fantasy._LOCAL_BOARD_DIR = tmp
        payload = fantasy_public._featured_payload()

    if payload is None:
        print("the selector returned nothing — no player qualified", file=sys.stderr)
        return 1

    OUT.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"wrote {OUT.relative_to(REPO)}  →  {payload['player']['name']} "
          f"({payload['player']['pos']}{payload['market']['ourRank']} vs market "
          f"{payload['player']['pos']}{payload['market']['adpRank']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
