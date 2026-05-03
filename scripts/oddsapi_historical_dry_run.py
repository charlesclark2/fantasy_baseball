"""
oddsapi_historical_dry_run.py
-----------------------------
Validates that the OddsAPI historical endpoint returns meaningfully different
odds across intraday timestamps before committing to a full historical backfill
(7.P2) or line-movement feature engineering (7.P3).

For each date × timestamp combination the script calls:
    GET /v4/historical/sports/baseball_mlb/odds
        ?apiKey=<ODDS_API_KEY>
        &date=<YYYY-MM-DDThh:mm:ssZ>
        &regions=us
        &markets=h2h
        &oddsFormat=american

It then converts American odds to implied win probability, measures intraday
movement per game, and writes a Markdown report with a PROCEED / CLOSE gate
recommendation.

Gate rule:
  PROCEED  if ≥50% of qualifying games show ≥1 pp of home-win-prob movement.
  CLOSE    otherwise (cancel 7.P2 and 7.P3).

Usage:
    uv run oddsapi_historical_dry_run.py \\
        --dates 2024-05-10,2024-06-15,2024-07-20 \\
        --timestamps 12:00,17:00,23:00 \\
        [--bookmaker draftkings] \\
        [--sleep-seconds 1.0] \\
        [--dry-run]

    --dry-run   Prints the dates/timestamps matrix and exits without
                making any API calls.

Environment variables (resolved from .env in the parent directory):
    ODDS_API_KEY            Required for live runs.
"""

import argparse
import logging
import os
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

ODDS_API_BASE_URL   = "https://api.the-odds-api.com/v4"
HIST_ODDS_ENDPOINT  = "/historical/sports/baseball_mlb/odds"
MOVEMENT_THRESHOLD  = 0.01   # 1 percentage point
PROCEED_THRESHOLD   = 0.50   # ≥50% of qualifying games must clear movement threshold
DEFAULT_BOOKMAKER   = "draftkings"
DEFAULT_SLEEP       = 1.0    # seconds between API calls

REPORT_PATH = (
    Path(__file__).parent.parent
    / "betting_ml" / "evaluation" / "oddsapi_historical_dry_run.md"
)


# ── Implied-probability conversion ────────────────────────────────────────────

def american_to_implied_prob(odds: int | float) -> float:
    """
    Convert American moneyline odds to implied win probability (0–1).

    Standard formulas:
        odds < 0:  p = |odds| / (|odds| + 100)
        odds > 0:  p = 100   / (odds   + 100)
        odds == 0: undefined — return 0.5 (even money)
    """
    if odds == 0:
        return 0.5
    if odds < 0:
        abs_odds = abs(odds)
        return abs_odds / (abs_odds + 100)
    return 100 / (odds + 100)


# ── API helpers ───────────────────────────────────────────────────────────────

def _get_api_key() -> str:
    key = os.environ.get("ODDS_API_KEY")
    if not key:
        raise EnvironmentError("ODDS_API_KEY is not set in environment or .env file.")
    return key


def fetch_historical_odds(
    snapshot_ts: str,
    bookmaker: str,
    sleep_seconds: float,
) -> tuple[list[dict], int | None, int | None]:
    """
    Call the OddsAPI historical h2h endpoint at a single snapshot timestamp.

    Returns:
        (events, requests_used, requests_remaining)
        events is the list of event objects from data[]; empty on 404 or no data.

    Raises SystemExit on 401/403 (plan tier) or 429 (rate limit).
    """
    api_key = _get_api_key()
    url = f"{ODDS_API_BASE_URL}{HIST_ODDS_ENDPOINT}"
    params = {
        "apiKey":     api_key,
        "date":       snapshot_ts,
        "regions":    "us",
        "markets":    "h2h",
        "oddsFormat": "american",
        "bookmakers": bookmaker,
    }

    log.info("GET %s  date=%s  bookmaker=%s", url, snapshot_ts, bookmaker)

    try:
        resp = requests.get(url, params=params, timeout=30)
    except requests.RequestException as exc:
        log.warning("  Request failed: %s — treating as missing", exc)
        time.sleep(sleep_seconds)
        return [], None, None

    used      = _parse_int_header(resp.headers.get("x-requests-used"))
    remaining = _parse_int_header(resp.headers.get("x-requests-remaining"))
    log.info("  HTTP %d  credits used=%s  remaining=%s", resp.status_code, used, remaining)

    if resp.status_code in (401, 403):
        print(
            f"\nERROR: HTTP {resp.status_code} — the OddsAPI historical endpoint requires "
            "a paid plan tier. Please upgrade your plan and retry.\n",
            file=sys.stderr,
        )
        sys.exit(1)

    if resp.status_code == 429:
        print(
            "\nERROR: HTTP 429 — OddsAPI rate limit reached. "
            "Re-run with --sleep-seconds 2 or split dates into smaller batches.\n",
            file=sys.stderr,
        )
        sys.exit(1)

    if resp.status_code == 404:
        log.info("  404 — no data at this snapshot; treating as missing")
        time.sleep(sleep_seconds)
        return [], used, remaining

    try:
        resp.raise_for_status()
    except requests.HTTPError as exc:
        log.warning("  HTTP error: %s — treating as missing", exc)
        time.sleep(sleep_seconds)
        return [], used, remaining

    payload = resp.json()
    if isinstance(payload, dict):
        events = payload.get("data", [])
    elif isinstance(payload, list):
        events = payload
    else:
        events = []

    log.info("  %d event(s) in response", len(events))
    time.sleep(sleep_seconds)
    return events, used, remaining


def _parse_int_header(value: str | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


# ── Odds extraction ───────────────────────────────────────────────────────────

def extract_home_win_prob(event: dict, bookmaker_key: str) -> float | None:
    """
    Return the implied home-win probability from the first matching bookmaker's
    h2h market, or None if not found.
    """
    home_team  = event.get("home_team")
    bookmakers = event.get("bookmakers", [])

    for bk in bookmakers:
        if bk.get("key") != bookmaker_key:
            continue
        for market in bk.get("markets", []):
            if market.get("key") != "h2h":
                continue
            for outcome in market.get("outcomes", []):
                if outcome.get("name") == home_team:
                    price = outcome.get("price")
                    if price is not None:
                        return american_to_implied_prob(price)
    return None


# ── Game key ──────────────────────────────────────────────────────────────────

def game_key(event: dict) -> str:
    """Stable identifier: home_team|away_team|game_date."""
    ct = event.get("commence_time", "")
    game_date = ct[:10] if ct else "unknown"
    return f"{event.get('home_team', '?')}|{event.get('away_team', '?')}|{game_date}"


# ── Core analysis ─────────────────────────────────────────────────────────────

def run_analysis(
    dates: list[str],
    timestamps: list[str],
    bookmaker: str,
    sleep_seconds: float,
) -> dict:
    """
    Query the API for every date × timestamp combination, collect per-game
    home-win-prob snapshots, compute movement, and return a results dict.

    Returns:
        {
            "game_results": [
                {
                    "game_key": str,
                    "game_date": str,
                    "home_team": str,
                    "away_team": str,
                    "snapshots": {ts_label: prob | None},
                    "earliest_prob": float | None,
                    "latest_prob":   float | None,
                    "abs_movement":  float | None,
                    "meets_threshold": bool | None,
                }
            ],
            "n_games_sampled": int,
            "mean_abs_movement": float | None,
            "pct_above_1pp": float | None,
            "recommend": "proceed" | "close",
            "bookmaker": str,
            "dates_queried": list[str],
            "timestamps_queried": list[str],
            "last_credits_used": int | None,
            "last_credits_remaining": int | None,
        }
    """
    # game_key → {ts_label: prob | None}
    game_probs: dict[str, dict[str, float | None]] = {}
    game_meta:  dict[str, dict]                    = {}

    last_used:      int | None = None
    last_remaining: int | None = None

    for date_str in dates:
        for ts_str in timestamps:
            ts_label   = f"{date_str}T{ts_str}:00Z"
            snapshot_ts = ts_label

            events, used, remaining = fetch_historical_odds(
                snapshot_ts=snapshot_ts,
                bookmaker=bookmaker,
                sleep_seconds=sleep_seconds,
            )
            if used is not None:
                last_used = used
            if remaining is not None:
                last_remaining = remaining

            for event in events:
                ct = event.get("commence_time", "")
                event_date = ct[:10] if ct else ""
                if event_date != date_str:
                    continue  # skip games not on this date

                gk = game_key(event)
                if gk not in game_probs:
                    game_probs[gk] = {}
                    game_meta[gk]  = {
                        "game_date": event_date,
                        "home_team": event.get("home_team", ""),
                        "away_team": event.get("away_team", ""),
                    }

                prob = extract_home_win_prob(event, bookmaker)
                game_probs[gk][ts_label] = prob

    # Build per-game result rows
    all_ts_labels = [
        f"{d}T{t}:00Z"
        for d in dates
        for t in timestamps
    ]

    game_results = []
    for gk, probs_by_ts in game_probs.items():
        valid_probs = [(ts, p) for ts, p in probs_by_ts.items() if p is not None]
        if len(valid_probs) < 2:
            abs_movement     = None
            earliest_prob    = valid_probs[0][1] if valid_probs else None
            latest_prob      = None
            meets_threshold  = None
        else:
            valid_probs_sorted = sorted(valid_probs, key=lambda x: x[0])
            earliest_prob   = valid_probs_sorted[0][1]
            latest_prob     = valid_probs_sorted[-1][1]
            abs_movement    = abs(latest_prob - earliest_prob)
            meets_threshold = abs_movement >= MOVEMENT_THRESHOLD

        meta = game_meta[gk]
        snapshots = {ts: probs_by_ts.get(ts) for ts in all_ts_labels if ts.startswith(meta["game_date"])}

        game_results.append({
            "game_key":        gk,
            "game_date":       meta["game_date"],
            "home_team":       meta["home_team"],
            "away_team":       meta["away_team"],
            "snapshots":       snapshots,
            "earliest_prob":   earliest_prob,
            "latest_prob":     latest_prob,
            "abs_movement":    abs_movement,
            "meets_threshold": meets_threshold,
        })

    game_results.sort(key=lambda r: (r["game_date"], r["home_team"]))

    qualifying = [r for r in game_results if r["abs_movement"] is not None]
    n_games_sampled = len(qualifying)

    if qualifying:
        mean_abs_movement = sum(r["abs_movement"] for r in qualifying) / n_games_sampled
        n_above = sum(1 for r in qualifying if r["meets_threshold"])
        pct_above_1pp = n_above / n_games_sampled
        recommend = "proceed" if pct_above_1pp >= PROCEED_THRESHOLD else "close"
    else:
        mean_abs_movement = None
        pct_above_1pp     = None
        recommend         = "close"

    return {
        "game_results":          game_results,
        "n_games_sampled":       n_games_sampled,
        "mean_abs_movement":     mean_abs_movement,
        "pct_above_1pp":         pct_above_1pp,
        "recommend":             recommend,
        "bookmaker":             bookmaker,
        "dates_queried":         dates,
        "timestamps_queried":    timestamps,
        "last_credits_used":     last_used,
        "last_credits_remaining": last_remaining,
    }


# ── Console output ─────────────────────────────────────────────────────────────

def print_results(results: dict) -> None:
    print("\n" + "=" * 72)
    print("OddsAPI Historical Dry-Run — Per-Game Results")
    print("=" * 72)

    rows = results["game_results"]
    if not rows:
        print("  No game data returned.")
    else:
        header = f"{'Date':<12}{'Home':<26}{'Away':<26}{'EarliestP':>10}{'LatestP':>10}{'|ΔP|':>8}{'≥1pp':>6}"
        print(header)
        print("-" * len(header))
        for r in rows:
            ep = f"{r['earliest_prob']:.3f}" if r["earliest_prob"] is not None else "  n/a "
            lp = f"{r['latest_prob']:.3f}"   if r["latest_prob"]   is not None else "  n/a "
            mv = f"{r['abs_movement']:.3f}"  if r["abs_movement"]  is not None else "  n/a "
            th = ("yes" if r["meets_threshold"] else "no") if r["meets_threshold"] is not None else " n/a"
            print(f"{r['game_date']:<12}{r['home_team'][:25]:<26}{r['away_team'][:25]:<26}{ep:>10}{lp:>10}{mv:>8}{th:>6}")

    print()
    print("=" * 72)
    print("Aggregate Summary")
    print("=" * 72)

    n   = results["n_games_sampled"]
    mam = results["mean_abs_movement"]
    pct = results["pct_above_1pp"]
    rec = results["recommend"].upper()

    print(f"  n_games_sampled   : {n}")
    print(f"  mean_abs_movement : {f'{mam:.4f}' if mam is not None else 'n/a'} (implied prob pp)")
    print(f"  pct_above_1pp     : {f'{pct*100:.1f}%' if pct is not None else 'n/a'}")
    print(f"  recommendation    : {rec}")
    if results["last_credits_remaining"] is not None:
        print(f"  credits remaining : {results['last_credits_remaining']}")
    print()


# ── Markdown report ────────────────────────────────────────────────────────────

def write_report(results: dict, report_path: Path) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)

    rec     = results["recommend"]
    pct     = results["pct_above_1pp"]
    mam     = results["mean_abs_movement"]
    n       = results["n_games_sampled"]
    bk      = results["bookmaker"]
    dates   = results["dates_queried"]
    tss     = results["timestamps_queried"]

    pct_str = f"{pct*100:.1f}%" if pct is not None else "n/a"
    mam_str = f"{mam:.4f}"      if mam is not None else "n/a"

    rec_label = "**PROCEED**" if rec == "proceed" else "**CLOSE**"
    if rec == "proceed":
        rationale = (
            f"≥50% of qualifying games ({pct_str}) showed ≥1 pp of intraday "
            "home-win-probability movement; historical resolution is sufficient "
            "for the line-movement feature track."
        )
    else:
        rationale = (
            f"Fewer than 50% of qualifying games ({pct_str}) showed ≥1 pp of "
            "intraday movement; historical OddsAPI resolution is insufficient "
            "for line-movement features. Cards 7.P2 and 7.P3 are cancelled."
        )

    lines = [
        "# OddsAPI Historical Snapshot Dry-Run",
        "",
        f"## Recommendation: {rec_label}",
        "",
        rationale,
        "",
        "---",
        "",
        "## Methodology",
        "",
        f"- **Bookmaker:** {bk}",
        f"- **Dates sampled ({len(dates)}):** {', '.join(dates)}",
        f"- **Timestamps queried (UTC):** {', '.join(tss)}",
        "- **Movement metric:** `abs(home_win_prob_latest − home_win_prob_earliest)`",
        "- **Threshold for ≥1pp:** `abs_movement ≥ 0.01`",
        "- **Proceed gate:** `pct_above_1pp ≥ 0.50`",
        "- **Implied-prob formula:** `|odds| / (|odds| + 100)` for negative odds; `100 / (odds + 100)` for positive",
        "",
        "---",
        "",
        "## Per-Game Results",
        "",
        "| Date | Home | Away | Earliest Prob | Latest Prob | Abs Movement | ≥1pp |",
        "|------|------|------|:-------------:|:-----------:|:------------:|:----:|",
    ]

    for r in results["game_results"]:
        ep = f"{r['earliest_prob']:.3f}" if r["earliest_prob"] is not None else "n/a"
        lp = f"{r['latest_prob']:.3f}"   if r["latest_prob"]   is not None else "n/a"
        mv = f"{r['abs_movement']:.3f}"  if r["abs_movement"]  is not None else "n/a"
        th = ("yes" if r["meets_threshold"] else "no") if r["meets_threshold"] is not None else "n/a"
        lines.append(
            f"| {r['game_date']} | {r['home_team']} | {r['away_team']} "
            f"| {ep} | {lp} | {mv} | {th} |"
        )

    lines += [
        "",
        "---",
        "",
        "## Aggregate Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| n_games_sampled | {n} |",
        f"| mean_abs_movement | {mam_str} |",
        f"| pct_above_1pp | {pct_str} |",
        f"| recommendation | {rec.upper()} |",
        "",
    ]

    report_path.write_text("\n".join(lines))
    log.info("Report written → %s", report_path)


# ── CLI ────────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Dry-run the OddsAPI historical endpoint across sample dates to "
            "determine whether intraday line movement is present (gate for 7.P2/7.P3)."
        )
    )
    parser.add_argument(
        "--dates",
        required=True,
        metavar="YYYY-MM-DD,...",
        help="Comma-separated list of game dates to query (e.g. 2024-05-10,2024-06-15).",
    )
    parser.add_argument(
        "--timestamps",
        required=True,
        metavar="HH:MM,...",
        help="Comma-separated UTC timestamps to snapshot on each date (e.g. 12:00,17:00,23:00).",
    )
    parser.add_argument(
        "--bookmaker",
        default=DEFAULT_BOOKMAKER,
        metavar="KEY",
        help=f"Bookmaker key to extract prices from (default: {DEFAULT_BOOKMAKER}).",
    )
    parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=DEFAULT_SLEEP,
        metavar="N",
        help=f"Seconds to sleep between API calls (default: {DEFAULT_SLEEP}).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print the dates/timestamps matrix and exit without making API calls.",
    )
    return parser


def main() -> None:
    args   = build_parser().parse_args()
    dates  = [d.strip() for d in args.dates.split(",") if d.strip()]
    tss    = [t.strip() for t in args.timestamps.split(",") if t.strip()]

    if not dates:
        print("ERROR: --dates is empty.", file=sys.stderr)
        sys.exit(1)
    if not tss:
        print("ERROR: --timestamps is empty.", file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        print("DRY-RUN mode — no API calls will be made.\n")
        print(f"Dates ({len(dates)}):      {', '.join(dates)}")
        print(f"Timestamps ({len(tss)}):   {', '.join(tss)}")
        print(f"Bookmaker:           {args.bookmaker}")
        print(f"Total snapshots:     {len(dates) * len(tss)}")
        print("\nDry-run complete.")
        return

    log.info(
        "Starting dry-run: %d date(s) × %d timestamp(s) = %d API call(s)",
        len(dates), len(tss), len(dates) * len(tss),
    )

    results = run_analysis(
        dates=dates,
        timestamps=tss,
        bookmaker=args.bookmaker,
        sleep_seconds=args.sleep_seconds,
    )

    print_results(results)
    write_report(results, REPORT_PATH)

    rec = results["recommend"]
    print(f"Gate result: {rec.upper()}")
    if rec == "close":
        print(
            "Recommendation is CLOSE — proceed to update project_context.md "
            "to cancel Cards 7.P2 and 7.P3."
        )
    else:
        print(
            "Recommendation is PROCEED — proceed to Card 7.P2 (historical odds backfill)."
        )


if __name__ == "__main__":
    main()
