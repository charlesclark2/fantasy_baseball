#!/usr/bin/env python3
"""INC-16-P1 — validate flaresolverr egress-IP sharing via a real FanGraphs pull.

Run this INSIDE the dagster-codeloc container (so it uses the same egress IP and
the compose-internal FLARESOLVERR_URL=http://flaresolverr:8191/v1) after the stack
is up:

    docker compose -f services/dagster/aws/docker-compose.yml \
        exec dagster-codeloc python services/dagster/aws/validate_flaresolverr.py

A success — a non-empty hitting leaderboard (type 8 = batting dashboard) for the
current season — proves flaresolverr solved the Cloudflare JS challenge from the
box's shared egress IP: "Cloudflare clearance obtained". A failure (raise) means
either FLARESOLVERR_URL is unset, the container can't reach flaresolverr, or the
cf_clearance is IP-mismatched (flaresolverr NOT co-located / not IP-sharing).
"""
import os
import sys
from datetime import date

# The client lives under scripts/utils; ensure the repo root is importable.
sys.path.insert(0, "/app")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from scripts.utils.fangraphs_client import FLARESOLVERR_URL, fetch_leaderboard  # noqa: E402


def main() -> int:
    if not FLARESOLVERR_URL:
        print("FAIL: FLARESOLVERR_URL is not set — flaresolverr not wired.", file=sys.stderr)
        return 1
    print(f"Using FLARESOLVERR_URL={FLARESOLVERR_URL}")
    result = fetch_leaderboard(stats="bat", type_id=8, season=date.today().year)
    rows = result.get("data", [])
    if not rows:
        print("FAIL: flaresolverr returned 0 rows — clearance NOT obtained "
              "(check egress-IP sharing / co-location).", file=sys.stderr)
        return 1
    print(f"OK: Cloudflare clearance obtained — pulled {len(rows)} hitting-leaderboard rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
