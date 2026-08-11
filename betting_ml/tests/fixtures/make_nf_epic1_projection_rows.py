"""Generate `nf_epic1_projection_rows.json` — the NF-EPIC 1 parity fixture.

⭐ REAL EXPORTER OUTPUT, NEVER HAND-WRITTEN (NF-C0e). A fixture an author types cannot disconfirm
the author's own assumption about which fields the payload carries — and the parity guard's whole
job is to compare two scoring implementations against the payload as it really is.

The fixture is committed; this generator is committed beside it so it can be regenerated when the
exporter's field set changes.

═══════════════════════════════════════════════════════════════════════════════════════════════════
WHEN YOU NEED THIS — RARELY
═══════════════════════════════════════════════════════════════════════════════════════════════════
Only when the projections payload's FIELD SET changes: a new scorable stat lands in `STAT_FIELD`, a
graduated term is added (NF-C0e added four), or the exporter renames a column. A re-publish with the
same columns does NOT need a new fixture — the parity guard compares two engines AGAINST EACH OTHER,
not against the current numbers, so a stale-but-complete fixture still proves exactly what it claims.

═══════════════════════════════════════════════════════════════════════════════════════════════════
HOW TO RUN IT — a SUBSCRIBER access token is required
═══════════════════════════════════════════════════════════════════════════════════════════════════
Since NF-EPIC 1 the raw stat line is PAID, so the only source that carries it is the gated
`/fantasy/nfl/projections-full`. Get a token from a signed-in SUBSCRIBER browser session:

    DevTools → Application → Local Storage → https://www.credencesports.com
    key:  CognitoIdentityServiceProvider.<clientId>.<username>.accessToken

Then, on the LAPTOP:

    export CREDENCE_ACCESS_TOKEN='eyJ…'
    uv run python betting_ml/tests/fixtures/make_nf_epic1_projection_rows.py

⚠️ The token is short-lived (about an hour). An expired one is reported as its own error rather than
being folded into "no stat line" — see `_fetch`.

⛔ THERE IS DELIBERATELY NO PUBLIC FALLBACK. The first cut fell back to `/fantasy/nfl/projections`
when the gated read failed, which made sense for the couple of hours before the split shipped and is
a trap afterwards: the public blob can no longer carry a stat line, so the fallback would always
"succeed" at fetching and then fail at the vacuity check — reporting "no raw stat line" for what is
really a missing or expired TOKEN. One failure wearing another's message is how a five-minute fix
becomes an afternoon.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

SOURCE = "https://api.credencesports.com/fantasy/nfl/projections-full"
OUT = Path(__file__).parent / "nf_epic1_projection_rows.json"

#: Enough rows per position that REPLACEMENT LEVEL is a real computation. A 12-team league starts
#: 12 QBs and up to ~36 WRs, so a fixture thinner than the starting demand would put every position's
#: replacement at "weakest rostered" and never exercise the `idx < len(arr)` branch — or the flex
#: allocation that is the subtlest part of `vor.py`.
PER_POSITION = 60


def _fetch(token: str) -> dict:
    """Read the gated payload, reporting each failure as ITSELF rather than as a later symptom."""
    request = urllib.request.Request(SOURCE, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(request, timeout=60) as resp:  # noqa: S310
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise SystemExit(
                "401 from the API Gateway authorizer — the token is missing, malformed or EXPIRED "
                "(they last about an hour). Grab a fresh one and re-export CREDENCE_ACCESS_TOKEN."
            ) from e
        if e.code == 403:
            raise SystemExit(
                "403 — the token is valid but this account is NOT a subscriber. "
                "`/fantasy/nfl/projections-full` needs fantasy entitlement (subscriber / admin / "
                "fantasy_comp); a free account cannot generate this fixture."
            ) from e
        raise SystemExit(f"{e.code} from {SOURCE}: {e.reason}") from e


def main() -> None:
    token = (os.getenv("CREDENCE_ACCESS_TOKEN") or "").strip()
    if not token:
        raise SystemExit(
            "CREDENCE_ACCESS_TOKEN is not set. The raw stat line is paid since NF-EPIC 1, so this "
            "fixture can only be built from a SUBSCRIBER session — see this file's docstring for "
            "where to find the token."
        )

    payload = _fetch(token)
    players = payload.get("players") or []
    by_pos: dict[str, list[dict]] = {}
    for p in players:
        by_pos.setdefault(str(p.get("pos") or ""), []).append(p)

    rows: list[dict] = []
    for pos in sorted(by_pos):
        ordered = sorted(by_pos[pos], key=lambda r: -(r.get("fpPpr") or 0.0))
        rows.extend(ordered[:PER_POSITION])

    # Anti-vacuity: a fixture with no stat line would let the parity guard pass on nothing, because
    # both engines would score every arm at zero and agree trivially.
    if not any(r.get("rec") is not None for r in rows):
        raise SystemExit(
            f"{SOURCE} returned 200 but carried no raw stat line. That should be impossible for an "
            "entitled caller — check the payload before writing a fixture the parity guard cannot "
            "fail against."
        )

    OUT.write_text(json.dumps(rows, indent=1, sort_keys=True) + "\n")
    print(f"wrote {len(rows)} rows ({len(players)} available) → {OUT}")


if __name__ == "__main__":
    main()
