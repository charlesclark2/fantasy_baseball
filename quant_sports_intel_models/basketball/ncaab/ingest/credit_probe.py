"""credit_probe.py — NCAAB-P0 node 1: MEASURE what the Odds API charges, never quote a price sheet.

WHY THIS MODULE EXISTS. NF-CAP1 recorded figures that were **10x too high** because they were
reasoned from the vendor's documented multiplier instead of measured: the 10x applies to the
`/historical` endpoint and the tier being costed used the LIVE one. The correction came from
reading `x-requests-remaining` on real calls. NCAAB is a different budget class again (~360 D-I
teams, 50+ games a night in season vs NCAAF's Saturday slate), so every number the operator is
asked to approve spend against is measured HERE, on live headers, before any schedule turns on.

HOW A MEASUREMENT IS MADE HONEST. Two independent instruments per call:

  1. `x-requests-last` — the API's OWN statement of what that call cost.
  2. The BRACKET — a free `/sports` read before and after. `/sports` bills 0 (measured:
     `x-requests-last: 0`), so the drop in `x-requests-remaining` across the bracket is an
     independent total that does not depend on trusting the per-call header.

They are recorded separately and RECONCILED. Agreement is the evidence; a disagreement is a
finding about the instrument, not a number to average. A probe that reported only one of them
could not tell "this call is free" from "this header is wrong" — the NF1.7(a) class.

WHAT A ZERO-ROW RESULT MEANS HERE, and why it is not a failure. `basketball_ncaab` is INACTIVE
out of season, so its live `/odds` returns an empty board. That is the expected off-season state
and the probe records it as OFF_SEASON_EMPTY rather than a defect — but it also records what the
empty call COST, because "an out-of-season poll is free" and "an out-of-season poll bills full
freight" are different cadence recommendations and nobody should have to guess which.

⛔ NO SCHEDULE IS ENABLED BY THIS MODULE. It measures and reports. Enablement is the operator's
spend decision, and the arithmetic it needs is the deliverable.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from typing import Any

ODDS_BASE = "https://api.the-odds-api.com/v4"

#: The free balance/bracket endpoint. Measured 2026-09-14: `x-requests-last: 0`.
FREE_BRACKET_PATH = "sports/"

#: NCAAB sport keys on The Odds API (measured from the live `/sports` list, not assumed).
SPORT_GAME_LINES = "basketball_ncaab"
SPORT_TITLE_FUTURES = "basketball_ncaab_championship_winner"

#: The game-line markets the NCAAF-parity MVP needs. Priced per market x region.
GAME_LINE_MARKETS = "h2h,spreads,totals"
FUTURES_MARKETS = "outrights"
DEFAULT_REGIONS = "us"


class ProbeRefusal(RuntimeError):
    """The probe refused to spend. Raised LOUDLY rather than truncating a plan silently."""


@dataclass
class Call:
    """One measured HTTP call against the Odds API."""

    label: str
    path: str
    params: dict
    paid: bool
    http_status: int | None = None
    x_requests_last: int | None = None      # the API's own per-call cost
    x_requests_remaining: int | None = None
    x_requests_used: int | None = None
    rows: int | None = None
    snapshot_ts: str | None = None          # /historical envelope `timestamp`
    previous_timestamp: str | None = None   # /historical envelope — granularity, for FREE
    next_timestamp: str | None = None
    note: str = ""
    error: str | None = None
    fetched_at: str = ""

    def cost(self) -> int:
        return int(self.x_requests_last or 0)


@dataclass
class Ledger:
    """Every call this probe made, with the bracket reconciliation.

    An EXECUTION WITNESS: it records attempts and refusals, not only successes, so a run that
    spent nothing is distinguishable from a run that never happened (the spec's named-witness
    discipline).
    """

    calls: list[Call] = field(default_factory=list)
    bracket_open_remaining: int | None = None
    bracket_close_remaining: int | None = None
    refusals: list[str] = field(default_factory=list)
    board_shapes: dict = field(default_factory=dict)
    started_at: str = ""
    finished_at: str = ""

    def paid_calls(self) -> list[Call]:
        return [c for c in self.calls if c.paid and c.error is None]

    def header_total(self) -> int:
        """Total spend per the API's own per-call headers."""
        return sum(c.cost() for c in self.paid_calls())

    def bracket_total(self) -> int | None:
        """Total spend per the independent free-read bracket."""
        if self.bracket_open_remaining is None or self.bracket_close_remaining is None:
            return None
        return self.bracket_open_remaining - self.bracket_close_remaining

    def reconciliation(self) -> dict:
        """Do the two independent instruments agree? Disagreement is a FINDING, not an average."""
        h, b = self.header_total(), self.bracket_total()
        if b is None:
            return {"state": "UNBRACKETED", "header_total": h, "bracket_total": None,
                    "detail": "no free-read bracket — the per-call header is unconfirmed"}
        if h == b:
            return {"state": "AGREE", "header_total": h, "bracket_total": b,
                    "detail": "per-call headers and the free-read bracket agree exactly"}
        return {"state": "DISAGREE", "header_total": h, "bracket_total": b,
                "delta": b - h,
                "detail": ("the two instruments disagree — treat the BRACKET as authoritative "
                           "(it does not depend on the per-call header being right) and treat "
                           "the gap as a measurement finding")}


def _api_key(env: dict | None = None) -> str:
    env = os.environ if env is None else env
    key = (env.get("ODDS_API_KEY") or "").strip()
    if not key:
        raise ProbeRefusal(
            "ODDS_API_KEY is not set. The probe refuses to run rather than silently reporting "
            "zero measurements. Source the repo .env (the MAIN key — the starter tier does not "
            "support /historical)."
        )
    return key


def _int_header(v) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _request(label: str, path: str, params: dict, *, paid: bool, key: str,
             sleep: float = 0.34, timeout: int = 30) -> Call:
    """One measured call. Never raises on an HTTP error — records it, so a 4xx is DATA."""
    import requests

    call = Call(label=label, path=path, params=dict(params), paid=paid,
                fetched_at=datetime.now(timezone.utc).isoformat())
    try:
        resp = requests.get(f"{ODDS_BASE}/{path.lstrip('/')}",
                            params={"apiKey": key, **params}, timeout=timeout)
        call.http_status = resp.status_code
        call.x_requests_last = _int_header(resp.headers.get("x-requests-last"))
        call.x_requests_remaining = _int_header(resp.headers.get("x-requests-remaining"))
        call.x_requests_used = _int_header(resp.headers.get("x-requests-used"))
        if resp.status_code != 200:
            call.error = f"HTTP {resp.status_code}: {resp.text[:200]}"
            return call
        payload = resp.json()
        if isinstance(payload, dict) and "data" in payload:
            call.snapshot_ts = payload.get("timestamp")
            call.previous_timestamp = payload.get("previous_timestamp")
            call.next_timestamp = payload.get("next_timestamp")
            data = payload["data"]
        else:
            data = payload
        call.rows = len(data) if isinstance(data, list) else 1
    except Exception as exc:  # noqa: BLE001 — an exception is a measurement, not a crash
        call.error = f"{type(exc).__name__}: {exc}"
    finally:
        if sleep:
            time.sleep(sleep)
    return call


def bracket_read(ledger: Ledger, key: str, *, which: str) -> Call:
    """A FREE `/sports` read that anchors the bracket. Billing 0 is ASSERTED, not assumed."""
    call = _request(f"bracket:{which}", FREE_BRACKET_PATH, {"all": "true"}, paid=False, key=key)
    if call.error is None and call.x_requests_last not in (0, None):
        call.note = (f"⚠️ the bracket endpoint billed {call.x_requests_last} — it is supposed to "
                     f"be free; the bracket arithmetic below is off by that much per read")
    ledger.calls.append(call)
    if which == "open":
        ledger.bracket_open_remaining = call.x_requests_remaining
    else:
        ledger.bracket_close_remaining = call.x_requests_remaining
    return call


# ── the probe legs ───────────────────────────────────────────────────────────────────────
def probe_live(ledger: Ledger, key: str, *, regions: str = DEFAULT_REGIONS) -> None:
    """LIVE endpoints: the futures board (active NOW) and the game-line board (off-season)."""
    # The events list — documented free; MEASURED here because the fan-out ceiling depends on it.
    ledger.calls.append(_request(
        "live/events/game_lines", f"sports/{SPORT_GAME_LINES}/events", {}, paid=False, key=key))
    ledger.calls.append(_request(
        "live/events/title_futures", f"sports/{SPORT_TITLE_FUTURES}/events", {}, paid=False, key=key))

    # Title futures — ACTIVE now. This is the now-or-never capture.
    ledger.calls.append(_request(
        "live/odds/title_futures", f"sports/{SPORT_TITLE_FUTURES}/odds",
        {"regions": regions, "markets": FUTURES_MARKETS, "oddsFormat": "american"},
        paid=True, key=key))

    # Game lines — INACTIVE out of season. What does an empty board COST?
    ledger.calls.append(_request(
        "live/odds/game_lines_offseason", f"sports/{SPORT_GAME_LINES}/odds",
        {"regions": regions, "markets": GAME_LINE_MARKETS, "oddsFormat": "american"},
        paid=True, key=key))


def probe_historical_depth(ledger: Ledger, key: str, dates: list[str], *,
                           regions: str = DEFAULT_REGIONS,
                           markets: str = GAME_LINE_MARKETS,
                           max_calls: int = 12) -> None:
    """DEPTH: the earliest `date` that returns real NCAAB snapshots.

    ⛔ REFUSES over `max_calls` rather than truncating the plan. A silently-shortened depth
    probe reports a shallower archive than exists and the operator prices a backfill that does
    not match reality.
    """
    if len(dates) > max_calls:
        raise ProbeRefusal(
            f"historical depth probe asked for {len(dates)} paid calls against a ceiling of "
            f"{max_calls}. REFUSING rather than truncating to the first {max_calls} — a "
            f"silently-shortened depth probe understates the archive. Raise --max-historical-calls "
            f"deliberately if the extra spend is intended."
        )
    for d in dates:
        ledger.calls.append(_request(
            f"historical/depth/{d[:10]}", f"historical/sports/{SPORT_GAME_LINES}/odds",
            {"date": d, "regions": regions, "markets": markets, "oddsFormat": "american"},
            paid=True, key=key))


def probe_historical_markets(ledger: Ledger, key: str, date: str, *,
                             regions: str = DEFAULT_REGIONS) -> None:
    """MARKETS: is each of h2h / spreads / totals retained historically, and at what unit cost?

    Asked ONE MARKET AT A TIME on purpose. A combined call returns a board and tells you nothing
    about which of the three markets actually carried prices — and the per-market unit cost is
    the multiplier in the backfill arithmetic.
    """
    for m in ("h2h", "spreads", "totals"):
        ledger.calls.append(_request(
            f"historical/market/{m}", f"historical/sports/{SPORT_GAME_LINES}/odds",
            {"date": date, "regions": regions, "markets": m, "oddsFormat": "american"},
            paid=True, key=key))


def probe_historical_events(ledger: Ledger, key: str, date: str) -> None:
    """The historical EVENTS list — measured because a props/per-event fan-out would start here."""
    ledger.calls.append(_request(
        "historical/events", f"historical/sports/{SPORT_GAME_LINES}/events",
        {"date": date}, paid=True, key=key))


def probe_board_shape(ledger: Ledger, key: str, date: str, *,
                      regions: str = DEFAULT_REGIONS,
                      markets: str = GAME_LINE_MARKETS) -> dict:
    """Measure the SHAPE of one historical snapshot: how many events, spread over how many
    distinct tip-off times, how many books, which markets actually carried prices.

    This is the input to the FAN-OUT CEILING, and it is the measurement that decides whether
    NCAAB can reuse NCAAF's per-kickoff `/historical` loop at all. NCAAF staggers ~60 kickoffs
    across a Saturday, so one call per kickoff is affordable. NCAAB runs 50+ games a NIGHT that
    CLUSTER into a handful of tip-off slots — if one snapshot already carries most of an
    evening's board, a per-kickoff loop would pay for the same board dozens of times over.
    Nobody should design that loop from intuition about the sport's calendar.

    Records COUNTS, never payloads — the ledger is a budget witness, not an odds store.
    """
    import requests

    call = Call(label=f"shape/{date[:10]}", path=f"historical/sports/{SPORT_GAME_LINES}/odds",
                params={"date": date, "regions": regions, "markets": markets},
                paid=True, fetched_at=datetime.now(timezone.utc).isoformat())
    shape: dict[str, Any] = {}
    try:
        resp = requests.get(
            f"{ODDS_BASE}/historical/sports/{SPORT_GAME_LINES}/odds",
            params={"apiKey": key, "date": date, "regions": regions, "markets": markets,
                    "oddsFormat": "american"}, timeout=30)
        call.http_status = resp.status_code
        call.x_requests_last = _int_header(resp.headers.get("x-requests-last"))
        call.x_requests_remaining = _int_header(resp.headers.get("x-requests-remaining"))
        payload = resp.json()
        call.snapshot_ts = payload.get("timestamp")
        call.previous_timestamp = payload.get("previous_timestamp")
        call.next_timestamp = payload.get("next_timestamp")
        data = payload.get("data", [])
        call.rows = len(data)
        commence = sorted({e.get("commence_time") for e in data if e.get("commence_time")})
        books, mkts = set(), set()
        for e in data:
            for b in e.get("bookmakers", []):
                books.add(b.get("key"))
                for m in b.get("markets", []):
                    mkts.add(m.get("key"))
        # how much of the board tips within 24h of the snapshot
        snap = _parse_z(call.snapshot_ts)
        within24 = sum(1 for c in commence
                       if snap and 0 <= (_parse_z(c) - snap).total_seconds() <= 86400)
        shape = {
            "events": len(data),
            "distinct_commence_times": len(commence),
            "commence_span_hours": (
                round((_parse_z(commence[-1]) - _parse_z(commence[0])).total_seconds() / 3600, 1)
                if len(commence) > 1 else 0.0),
            "distinct_commence_times_within_24h": within24,
            "books": sorted(books),
            "n_books": len(books),
            "markets_present": sorted(mkts),
            "max_books_on_one_event": max(
                (len(e.get("bookmakers", [])) for e in data), default=0),
        }
        call.note = (f"{shape['events']} events / {shape['distinct_commence_times']} tip slots "
                     f"/ {shape['n_books']} books / markets={','.join(shape['markets_present'])}")
    except Exception as exc:  # noqa: BLE001
        call.error = f"{type(exc).__name__}: {exc}"
    finally:
        time.sleep(0.34)
    ledger.calls.append(call)
    return shape


def _parse_z(ts: str | None):
    if not ts:
        return None
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def run(dates: list[str], *, regions: str = DEFAULT_REGIONS, markets_date: str | None = None,
        shape_dates: list[str] | None = None,
        max_historical_calls: int = 12, do_live: bool = True,
        key: str | None = None) -> Ledger:
    """Execute the probe end-to-end under one bracket. Returns the ledger (the witness)."""
    key = key or _api_key()
    ledger = Ledger(started_at=datetime.now(timezone.utc).isoformat())
    bracket_read(ledger, key, which="open")
    try:
        if do_live:
            probe_live(ledger, key, regions=regions)
        if dates:
            probe_historical_depth(ledger, key, dates, regions=regions,
                                   max_calls=max_historical_calls)
        for sd in (shape_dates or []):
            ledger.board_shapes[sd] = probe_board_shape(ledger, key, sd, regions=regions)
        if markets_date:
            probe_historical_markets(ledger, key, markets_date, regions=regions)
            probe_historical_events(ledger, key, markets_date)
    except ProbeRefusal as exc:
        ledger.refusals.append(str(exc))
    finally:
        bracket_read(ledger, key, which="close")
        ledger.finished_at = datetime.now(timezone.utc).isoformat()
    return ledger


def to_dict(ledger: Ledger) -> dict:
    return {
        "probe": "ncaab_p0_credit_probe",
        "started_at": ledger.started_at,
        "finished_at": ledger.finished_at,
        "sport_keys": {"game_lines": SPORT_GAME_LINES, "title_futures": SPORT_TITLE_FUTURES},
        "reconciliation": ledger.reconciliation(),
        "bracket_open_remaining": ledger.bracket_open_remaining,
        "bracket_close_remaining": ledger.bracket_close_remaining,
        "refusals": ledger.refusals,
        "board_shapes": ledger.board_shapes,
        "calls": [asdict(c) for c in ledger.calls],
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="NCAAB-P0 measured Odds-API credit probe")
    p.add_argument("--dates", default="", help="comma-separated ISO instants for the depth probe")
    p.add_argument("--markets-date", default=None, help="ISO instant for the per-market probe")
    p.add_argument("--regions", default=DEFAULT_REGIONS)
    p.add_argument("--max-historical-calls", type=int, default=12)
    p.add_argument("--shape-dates", default="",
                   help="comma-separated ISO instants for the board-SHAPE probe (fan-out sizing)")
    p.add_argument("--no-live", action="store_true")
    p.add_argument("--out", default=None, help="write the ledger JSON here")
    a = p.parse_args(argv)

    dates = [d.strip() for d in a.dates.split(",") if d.strip()]
    shape_dates = [d.strip() for d in a.shape_dates.split(",") if d.strip()]
    ledger = run(dates, regions=a.regions, markets_date=a.markets_date,
                 shape_dates=shape_dates,
                 max_historical_calls=a.max_historical_calls, do_live=not a.no_live)
    payload = to_dict(ledger)
    if a.out:
        os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
        with open(a.out, "w") as fh:
            json.dump(payload, fh, indent=2)
    print(json.dumps(payload["reconciliation"], indent=2))
    for c in ledger.calls:
        print(f"  {c.label:38s} paid={str(c.paid):5s} cost={c.x_requests_last} "
              f"rows={c.rows} http={c.http_status} {c.error or c.note}")
    for r in ledger.refusals:
        print(f"  ⛔ REFUSED: {r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
