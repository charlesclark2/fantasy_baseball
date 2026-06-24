"""
probe_ms2_multisport_props.py
─────────────────────────────
DEPRECATED — superseded by scripts/backfill_multisport_props_to_s3.py --mode probe

This script probed the wrong historical endpoint (/v4/historical/sports/{sport}/odds).
Player props require the two-step events endpoint.  Use:
    uv run scripts/backfill_multisport_props_to_s3.py --mode probe
─────────────────────────────
Phase-0 probe for MS.2: does The Odds API offer historical player-prop markets
on its /v4/historical/sports/{sport}/odds endpoint for NFL, NCAAF, and NCAAB?

E5.1 (MLB) proved the endpoint returns HTTP 422 INVALID_MARKET for all MLB
prop markets, consuming ZERO credits.  This script runs the same test for the
three fall multi-sport targets.

Per-sport probe: one API call, one candidate market, one game date, us region
only.  If the response is INVALID_MARKET → sport is BLOCKED (consistent with
E5.1 finding).  If events are returned → sport is AVAILABLE; the script prints
the full list of markets present in the response.

Usage:
    uv run scripts/probe_ms2_multisport_props.py

Environment (from ../.env):
    ODDS_API_KEY   Required.
"""

import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

ODDS_API_BASE_URL = "https://api.the-odds-api.com/v4"
REQUEST_DELAY     = 1.0

# ── Probe targets ──────────────────────────────────────────────────────────────
# One candidate date and one representative prop market per sport.
# Dates chosen on known busy game days (playoffs/tournament) to maximise
# the chance of events being present even if props aren't.
#
# NFL market keys (Odds API v4): player_pass_yards, player_rush_yards,
#   player_reception_yards, player_receptions, player_anytime_td
# NCAAF market keys: player_pass_yards, player_rush_yards
# NCAAB market keys: player_points, player_rebounds, player_assists

PROBE_TARGETS = [
    {
        "label"         : "NFL",
        "sport"         : "americanfootball_nfl",
        "probe_date"    : "2024-01-14T17:00:00Z",   # Divisional playoff weekend
        "commence_from" : "2024-01-14T00:00:00Z",
        "commence_to"   : "2024-01-15T07:00:00Z",
        "market"        : "player_pass_yards",
    },
    {
        "label"         : "NCAAF",
        "sport"         : "americanfootball_ncaaf",
        "probe_date"    : "2024-01-08T17:00:00Z",   # CFP Championship
        "commence_from" : "2024-01-08T00:00:00Z",
        "commence_to"   : "2024-01-09T07:00:00Z",
        "market"        : "player_pass_yards",
    },
    {
        "label"         : "NCAAB",
        "sport"         : "basketball_ncaab",
        "probe_date"    : "2024-03-17T17:00:00Z",   # March Madness Round of 32
        "commence_from" : "2024-03-17T00:00:00Z",
        "commence_to"   : "2024-03-18T07:00:00Z",
        "market"        : "player_points",
    },
]


def probe_sport(api_key: str, target: dict) -> dict:
    """
    Make one historical-odds call for `target`.
    Returns a result dict with keys: label, sport, available, markets, error,
    credits_remaining.
    """
    url = f"{ODDS_API_BASE_URL}/historical/sports/{target['sport']}/odds"
    params = {
        "apiKey"            : api_key,
        "date"              : target["probe_date"],
        "regions"           : "us",
        "markets"           : target["market"],
        "oddsFormat"        : "american",
        "commenceTimeFrom"  : target["commence_from"],
        "commenceTimeTo"    : target["commence_to"],
    }

    try:
        resp = requests.get(url, params=params, timeout=20)
        remaining = resp.headers.get("x-requests-remaining", "unknown")

        if resp.status_code == 422:
            body = resp.json()
            return {
                "label"             : target["label"],
                "sport"             : target["sport"],
                "available"         : False,
                "markets"           : [],
                "error"             : body.get("message", "INVALID_MARKET"),
                "error_code"        : body.get("error_code", ""),
                "credits_remaining" : remaining,
            }

        resp.raise_for_status()
        data = resp.json()
        events = data.get("data", [])

        # Collect all distinct market keys present in the response
        market_keys: set[str] = set()
        for event in events:
            for bm in event.get("bookmakers", []):
                for mkt in bm.get("markets", []):
                    market_keys.add(mkt.get("key", ""))

        return {
            "label"             : target["label"],
            "sport"             : target["sport"],
            "available"         : bool(events),
            "event_count"       : len(events),
            "markets"           : sorted(market_keys),
            "error"             : None,
            "credits_remaining" : remaining,
        }

    except requests.exceptions.HTTPError as exc:
        return {
            "label"             : target["label"],
            "sport"             : target["sport"],
            "available"         : False,
            "markets"           : [],
            "error"             : str(exc),
            "credits_remaining" : "unknown",
        }


def main() -> None:
    api_key = os.getenv("ODDS_API_KEY")
    if not api_key:
        log.error("ODDS_API_KEY not set — check .env")
        sys.exit(1)

    print()
    print("══ MS.2 MULTI-SPORT PROPS — PHASE 0 PROBE ═══════════════════════════════════")
    print("  E5.1 finding: MLB historical props → HTTP 422 INVALID_MARKET (0 credits).")
    print("  Testing NFL / NCAAF / NCAAB on the same /v4/historical/…/odds endpoint.")
    print()

    results = []
    for target in PROBE_TARGETS:
        print(f"  Probing {target['label']} ({target['sport']})  market={target['market']}  "
              f"date={target['probe_date'][:10]}")
        result = probe_sport(api_key, target)
        results.append(result)

        if result["available"]:
            print(f"    ✓  AVAILABLE — {result['event_count']} events found")
            print(f"       Markets present: {result['markets']}")
        else:
            print(f"    ✗  BLOCKED — {result['error']}  (error_code={result.get('error_code', 'n/a')})")
        print(f"       credits_remaining={result['credits_remaining']}")
        print()
        time.sleep(REQUEST_DELAY)

    # ── Summary ────────────────────────────────────────────────────────────────
    available = [r for r in results if r["available"]]
    blocked   = [r for r in results if not r["available"]]

    print("═" * 79)
    if not available:
        print("RESULT: The Odds API does NOT offer historical player props for any of")
        print("        NFL / NCAAF / NCAAB on the historical-odds endpoint.")
        print()
        print("MS.2 is BLOCKED — same finding as E5.1 (MLB).  This is a real finding,")
        print("not a failure.  The /v4/historical endpoint does not archive prop markets")
        print("for any sport.")
        print()
        print("Next steps:")
        print("  • Update build_roadmap.md: MS.2 → BLOCKED.")
        print("  • Alternative paid sources: Sportradar, StatsPerform, Action Network PRO.")
        print("  • Remaining ~3.77M credits are unexpendable on props for any sport.")
        print("  • Consider MS.1 (free outcomes backfill) — unaffected by this finding.")
    else:
        print(f"RESULT: {len(available)} sport(s) AVAILABLE: "
              f"{', '.join(r['label'] for r in available)}")
        print(f"        {len(blocked)} sport(s) BLOCKED: "
              f"{', '.join(r['label'] for r in blocked)}")
        print()
        for r in available:
            print(f"  {r['label']}  markets: {r['markets']}")
        print()
        print("Next step: build backfill_ms2_props_to_s3.py for available sports,")
        print("reusing backfill_mlb_props_to_s3.py patterns.  Blocked sports → paid source.")
    print("═" * 79)
    print()


if __name__ == "__main__":
    main()
