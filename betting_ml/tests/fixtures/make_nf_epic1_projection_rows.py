"""Generate `nf_epic1_projection_rows.json` — the NF-EPIC 1 parity fixture.

⭐ REAL EXPORTER OUTPUT, NEVER HAND-WRITTEN (NF-C0e). A fixture an author types cannot disconfirm
the author's own assumption about which fields the payload carries — and the parity guard's whole
job is to compare two implementations against the payload as it really is.

The fixture is committed; this generator is committed beside it so it can be regenerated when the
exporter's field set changes.

Run (LAPTOP):
    uv run python betting_ml/tests/fixtures/make_nf_epic1_projection_rows.py

It reads the LIVE published payload, so it needs no credentials — the projections blob is public
(that is the surface NF-EPIC 1 narrowed, not one it closed).
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

SOURCE = "https://api.credencesports.com/fantasy/nfl/projections-full"
FALLBACK = "https://api.credencesports.com/fantasy/nfl/projections"
OUT = Path(__file__).parent / "nf_epic1_projection_rows.json"

#: Enough rows per position that REPLACEMENT LEVEL is a real computation. A 12-team league starts
#: 12 QBs and up to ~36 WRs, so a fixture thinner than the starting demand would put every position's
#: replacement at "weakest rostered" and never exercise the `idx < len(arr)` branch — or the flex
#: allocation that is the subtlest part of `vor.py`.
PER_POSITION = 60


def main() -> None:
    url = SOURCE
    try:
        with urllib.request.urlopen(url, timeout=60) as resp:  # noqa: S310
            payload = json.loads(resp.read().decode())
    except Exception:  # noqa: BLE001
        # `/full` is entitlement-gated; without a token fall back to the public blob. That only
        # works BEFORE the NF-EPIC 1 split ships — after it, regenerate with a subscriber token.
        with urllib.request.urlopen(FALLBACK, timeout=60) as resp:  # noqa: S310
            payload = json.loads(resp.read().decode())
        url = FALLBACK

    players = payload.get("players") or []
    by_pos: dict[str, list[dict]] = {}
    for p in players:
        by_pos.setdefault(str(p.get("pos") or ""), []).append(p)

    rows: list[dict] = []
    for pos in sorted(by_pos):
        ordered = sorted(by_pos[pos], key=lambda r: -(r.get("fpPpr") or 0.0))
        rows.extend(ordered[:PER_POSITION])

    if not any(r.get("rec") is not None for r in rows):
        raise SystemExit(
            f"{url} carried no raw stat line — regenerate against /full with a subscriber token, "
            "or the parity fixture is vacuous"
        )

    OUT.write_text(json.dumps(rows, indent=1, sort_keys=True) + "\n")
    print(f"wrote {len(rows)} rows from {url} → {OUT}")


if __name__ == "__main__":
    main()
