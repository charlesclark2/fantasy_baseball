"""
probe_batter_prop_coverage.py
─────────────────────────────
Two cheap, costed probes against The Odds API HISTORICAL event-level endpoint that
settle two questions the EXISTING S3 archive cannot answer — because the archive only
ever sampled two snapshot times per day and only ever started at 2023-05-03.

⚠️ SPENDS PAID CREDITS.  `--dry-run` (the default) makes NO API call and prints the
exact projected cost.  Nothing runs until `--execute` is passed.

────────────────────────────────────────────────────────────────────────────────
PROBE A — "is the 2023-05-03 player-prop floor real?"

`scripts/backfill_mlb_props_to_s3.py` probed 2021/2022 and found nothing — but that
script is DEPRECATED because it used the FEATURED-markets historical endpoint
(`/historical/sports/{sport}/odds`), which returns INVALID_MARKET for every player
prop key.  **Its negative result for pre-2023 dates is therefore not evidence.**  The
floor is vendor-documented but has never been independently checked here on the
CORRECT two-step event endpoint.

Why it matters: the Phase-2 pre-registration names the fold count as the binding
design constraint (at 3 folds the max attainable DSR is 0.977 against a 0.95 gate).
2023–2026 gives 6 half-season folds.  If props reach back to 2021, that becomes ~10 —
which attacks the power limitation directly, and is worth far more than any single
modelling choice downstream.

────────────────────────────────────────────────────────────────────────────────
PROBE B — "does batter_home_runs two-sidedness depend on the SNAPSHOT TIME?"

Measured on the existing archive, the two-sided HR share is **28.9% at 17:00Z** and
**40.4% at 23:30Z** — it moves +11.5pp with time of day.  But those are the ONLY two
timestamps we have ever pulled, so the claim "these books post HR one-way by
construction" is an inference from a 2-point sample of a quantity that visibly varies.

This probe re-requests the SAME (date, event) at several ADDITIONAL timestamps and
reports the two-sided share per book per timestamp.  Two outcomes, both useful:
  • two-sidedness rises materially at some other hour  ⇒ the HR de-vig gap is partly a
    SAMPLING artifact and IS buyable back by re-pulling at that hour;
  • it stays ~0 for the one-way books at every hour    ⇒ the market-structure reading
    is confirmed on evidence rather than on inference, and the pre-registration's HR
    fold restriction stands as written.

⛔ Leakage: every probed timestamp is clamped to strictly BEFORE the event's
commence_time, so a probe can never manufacture a post-first-pitch quote.

────────────────────────────────────────────────────────────────────────────────
USAGE
    # cost estimate only — no API calls (DEFAULT):
    uv run python scripts/probe_batter_prop_coverage.py

    # run probe A only (does the archive predate 2023-05-03?):
    uv run python scripts/probe_batter_prop_coverage.py --probe floor --execute

    # run probe B only (snapshot-time dependence of HR two-sidedness):
    uv run python scripts/probe_batter_prop_coverage.py --probe snapshot --execute

    # both:
    uv run python scripts/probe_batter_prop_coverage.py --probe both --execute
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

BASE  = "https://api.the-odds-api.com/v4"
SPORT = "baseball_mlb"

# ── PROBE A: dates strictly BEFORE the documented 2023-05-03 prop floor ────────
# Mid-week, mid-season dates guaranteed to have a full MLB slate, walking backwards
# so the earliest hit bounds the true floor.
FLOOR_DATES = [
    date(2023, 4, 12),   # 3 weeks before the documented floor
    date(2023, 3, 30),   # 2023 opening week
    date(2022, 7, 13),   # mid-2022
    date(2021, 7, 14),   # mid-2021
]

# ── PROBE B: timestamps to re-request, beyond the archive's 17:00 / 23:30 ──────
# 23:30Z already shows the highest two-sided share, so the interesting direction is
# BOTH earlier (is 17:00 simply too early?) and later (does the under side appear
# only near first pitch?).  All are clamped below commence_time.
SNAPSHOT_TIMES = ["13:00", "15:00", "20:00", "22:00", "23:00"]
SNAPSHOT_DATES = [date(2026, 7, 15), date(2026, 8, 5)]
SNAPSHOT_MARKET = "batter_home_runs"
SNAPSHOT_EVENTS_PER_DATE = 3

REGIONS = ["us", "eu"]          # eu carries Pinnacle
CR_PER_EVENT = 10 * 1 * len(REGIONS)   # 10 x markets x regions, 1 market here


def _key() -> str:
    k = os.getenv("ODDS_API_KEY")
    if not k:
        log.error("ODDS_API_KEY not set — check .env")
        sys.exit(1)
    return k


def _events(game_date: date, snap: str, api_key: str):
    """GET /historical/sports/{sport}/events — 1 credit."""
    r = requests.get(
        f"{BASE}/historical/sports/{SPORT}/events",
        params={"apiKey": api_key, "date": f"{game_date}T{snap}:00Z",
                "commenceTimeFrom": f"{game_date}T00:00:00Z",
                "commenceTimeTo": f"{game_date + timedelta(days=1)}T07:00:00Z"},
        timeout=30)
    if r.status_code == 404:
        return [], r.headers.get("x-requests-remaining", "?")
    r.raise_for_status()
    d = r.json()
    return d.get("data", []), r.headers.get("x-requests-remaining", "?")


def _event_odds(event_id: str, snap_ts: str, market: str, api_key: str):
    """GET /historical/.../events/{id}/odds — 10 x markets x regions credits."""
    r = requests.get(
        f"{BASE}/historical/sports/{SPORT}/events/{event_id}/odds",
        params={"apiKey": api_key, "date": snap_ts, "markets": market,
                "regions": ",".join(REGIONS), "oddsFormat": "american"},
        timeout=30)
    last = r.headers.get("x-requests-last", "?")
    rem  = r.headers.get("x-requests-remaining", "?")
    if r.status_code in (404, 422):
        return None, last, rem
    r.raise_for_status()
    d = r.json()
    ev = d.get("data") or d
    if isinstance(ev, list):
        ev = ev[0] if ev else None
    return ev, last, rem


def _two_sided_by_book(event: dict, market: str) -> dict[str, tuple[int, int]]:
    """{book: (n_players, n_two_sided)} for `market` in one event payload."""
    out: dict[str, tuple[int, int]] = {}
    for bm in (event or {}).get("bookmakers", []):
        for mkt in bm.get("markets", []):
            if mkt.get("key") != market:
                continue
            players: dict[str, dict] = defaultdict(dict)
            for o in mkt.get("outcomes", []):
                name = (o.get("description") or "").strip()
                side = (o.get("name") or "").strip().lower()
                if name and side in ("over", "under"):
                    players[name][side] = o.get("price")
            n  = len(players)
            ts = sum(1 for v in players.values()
                     if v.get("over") is not None and v.get("under") is not None)
            out[bm.get("key", "?")] = (n, ts)
    return out


# ── PROBE A ────────────────────────────────────────────────────────────────────

def probe_floor(api_key: str) -> None:
    print("\n" + "=" * 78)
    print("PROBE A — does the player-prop archive predate 2023-05-03?")
    print("  (the deprecated script's 2021/22 probe used the FEATURED endpoint,")
    print("   which returns INVALID_MARKET for props — that result is NOT evidence)")
    print("=" * 78)
    earliest = None
    for d in FLOOR_DATES:
        try:
            evs, rem = _events(d, "23:30", api_key)
        except requests.HTTPError as e:
            print(f"  {d}  events -> HTTP {e.response.status_code}  (no archive)")
            continue
        if not evs:
            print(f"  {d}  events -> 0  (no slate archived)")
            continue
        ev0 = evs[0]
        data, last, rem = _event_odds(ev0.get("id", ""), f"{d}T23:30:00Z",
                                      SNAPSHOT_MARKET, api_key)
        books = _two_sided_by_book(data, SNAPSHOT_MARKET) if data else {}
        tot = sum(n for n, _ in books.values())
        ts  = sum(t for _, t in books.values())
        if tot:
            earliest = d if earliest is None or d < earliest else earliest
            print(f"  {d}  ✓ {len(evs)} events | {SNAPSHOT_MARKET}: {tot} players, "
                  f"{ts} two-sided, books={sorted(books)}  (cost {last}, rem {rem})")
        else:
            print(f"  {d}  ✗ {len(evs)} events but NO {SNAPSHOT_MARKET} data  "
                  f"(cost {last}, rem {rem})")
    print("-" * 78)
    if earliest:
        print(f"  RESULT: player props DO exist at {earliest} — EARLIER than the")
        print(f"          documented 2023-05-03 floor.  Extending SEASON_RANGES back")
        print(f"          adds folds, which is the binding Phase-2 power constraint.")
    else:
        print("  RESULT: no player-prop data before 2023-05-03 on the CORRECT endpoint.")
        print("          The documented floor is confirmed independently; 6 folds stand.")
    print()


# ── PROBE B ────────────────────────────────────────────────────────────────────

def probe_snapshot(api_key: str) -> None:
    print("\n" + "=" * 78)
    print(f"PROBE B — does {SNAPSHOT_MARKET} two-sidedness depend on SNAPSHOT TIME?")
    print("  archive baseline: 17:00Z = 28.9% two-sided | 23:30Z = 40.4%")
    print("  (only two timestamps have ever been pulled — this samples five more)")
    print("=" * 78)
    # book -> snap -> [players, two_sided]
    agg: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for d in SNAPSHOT_DATES:
        try:
            evs, _ = _events(d, "23:30", api_key)
        except requests.HTTPError as e:
            print(f"  {d}: events HTTP {e.response.status_code} — skipping")
            continue
        evs = evs[:SNAPSHOT_EVENTS_PER_DATE]
        print(f"\n  {d} — {len(evs)} events probed")
        for ev in evs:
            eid = ev.get("id", "")
            ct  = ev.get("commence_time", "")
            try:
                ct_dt = datetime.fromisoformat(ct.replace("Z", "+00:00"))
            except ValueError:
                continue
            for snap in SNAPSHOT_TIMES:
                snap_ts = f"{d}T{snap}:00Z"
                # ⛔ leakage clamp: never request at/after first pitch
                if datetime.fromisoformat(snap_ts.replace("Z", "+00:00")) >= ct_dt:
                    continue
                data, last, rem = _event_odds(eid, snap_ts, SNAPSHOT_MARKET, api_key)
                if not data:
                    continue
                for book, (n, ts) in _two_sided_by_book(data, SNAPSHOT_MARKET).items():
                    agg[book][snap][0] += n
                    agg[book][snap][1] += ts
                print(f"    {eid[:8]} @ {snap}Z -> "
                      f"{sum(n for n,_ in _two_sided_by_book(data, SNAPSHOT_MARKET).values())} players "
                      f"(cost {last}, rem {rem})")

    print("\n" + "-" * 78)
    print(f"  TWO-SIDED SHARE BY BOOK x SNAPSHOT ({SNAPSHOT_MARKET})")
    hdr = "  " + f"{'book':<16}" + "".join(f"{s+'Z':>10}" for s in SNAPSHOT_TIMES)
    print(hdr); print("  " + "-" * (len(hdr) - 2))
    for book in sorted(agg):
        row = f"  {book:<16}"
        for s in SNAPSHOT_TIMES:
            n, ts = agg[book][s]
            row += f"{(f'{100*ts/n:.0f}%' if n else '—'):>10}"
        print(row)
    print()
    print("  READ IT: a one-way book (williamhill_us / betrivers — 0 two-sided across")
    print("  ~74k archived quotes) showing >0% at ANY hour means the HR gap is partly a")
    print("  SAMPLING artifact and IS buyable back.  All-zero at every hour confirms the")
    print("  market-structure reading, and the pre-registration's HR fold caveat stands.")
    print()


def estimate() -> None:
    a_events = len(FLOOR_DATES)
    a_cost   = a_events * (1 + CR_PER_EVENT)
    b_calls  = len(SNAPSHOT_DATES) * SNAPSHOT_EVENTS_PER_DATE * len(SNAPSHOT_TIMES)
    b_cost   = len(SNAPSHOT_DATES) * 1 + b_calls * CR_PER_EVENT
    print("\n" + "=" * 78)
    print("COST ESTIMATE (no API calls made)")
    print("=" * 78)
    print(f"  credits/event-odds call : {CR_PER_EVENT}  (10 x 1 market x {len(REGIONS)} regions)")
    print()
    print(f"  PROBE A (floor)    : {a_events} dates x (1 events + 1 odds)      "
          f"-> ~{a_cost:,} credits")
    print(f"  PROBE B (snapshot) : {len(SNAPSHOT_DATES)} dates x "
          f"{SNAPSHOT_EVENTS_PER_DATE} events x {len(SNAPSHOT_TIMES)} times  "
          f"-> ~{b_cost:,} credits")
    print(f"  {'':<21}{'TOTAL':<38}-> ~{a_cost + b_cost:,} credits")
    print()
    print("  Context: the post-2026-07-17 budget is ~100,000 credits/month, so this is")
    print(f"  ~{100*(a_cost+b_cost)/100_000:.1f}% of one month.  Re-pulling 2023-25 HR with --force")
    print("  would be ~280,000 credits — this probe is what tells you whether that")
    print("  spend could ever be worth it, BEFORE committing to it.")
    print()
    print("  Re-run with --execute to spend.")
    print()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--probe", choices=["floor", "snapshot", "both"], default="both")
    ap.add_argument("--execute", action="store_true",
                    help="Actually call the API and SPEND CREDITS (default: dry-run).")
    args = ap.parse_args()

    if not args.execute:
        estimate()
        return
    api_key = _key()
    if args.probe in ("floor", "both"):
        probe_floor(api_key)
    if args.probe in ("snapshot", "both"):
        probe_snapshot(api_key)


if __name__ == "__main__":
    main()
