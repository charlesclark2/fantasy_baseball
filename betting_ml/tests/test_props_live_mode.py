"""Guards the live intraday pitcher-strikeout props feed (E5.1b, 2026-07-02).

`backfill_multisport_props_to_s3.py --mode live` is the CURRENT-lines feed that keeps the
Player Props page fresh on par with the other odds crons. It must:
  - resolve the target day on the US BASEBALL calendar (not UTC) so it can't write a
    date=<UTC-tomorrow> partition the K-projection writer never reads (INC-22 class),
  - write the today partition at the canonical S3 key
    mlb/props/market=pitcher_strikeouts/season=<yr>/date=<day>/data.parquet,
  - overwrite with the CURRENT snapshot (snapshot_ts = fetch time), and
  - no-op cheaply (zero S3 writes) when there are no upcoming games (off-window / offday).

Pure/mocked — no network or S3. A fixed 2025 in-season date keeps the season lookup
deterministic (2025 range is static, unlike the current-year range which ends today-1).
"""
from datetime import date

import scripts.backfill_multisport_props_to_s3 as bf

_FIXED_DAY = date(2025, 6, 15)  # inside the static 2025 season range → season 2025


def _one_event():
    return {
        "id": "evt1", "sport_key": "baseball_mlb",
        "commence_time": "2025-06-15T23:05:00Z",
        "home_team": "H", "away_team": "A",
        "bookmakers": [{
            "key": "draftkings",
            "markets": [{
                "key": "pitcher_strikeouts",
                "outcomes": [
                    {"name": "Over",  "description": "Pitcher X", "point": 6.5, "price": -115},
                    {"name": "Under", "description": "Pitcher X", "point": 6.5, "price": -105},
                ],
            }],
        }],
    }


def _patch_common(monkeypatch, events):
    monkeypatch.setattr(bf, "_us_baseball_day", lambda: _FIXED_DAY)
    monkeypatch.setattr(bf, "fetch_live_events", lambda *a, **k: (events, 1000))
    monkeypatch.setattr(bf, "fetch_live_event_props",
                        lambda *a, **k: (_one_event(), 990))
    monkeypatch.setattr(bf.time, "sleep", lambda *_: None)


def test_live_writes_today_partition_at_canonical_key(monkeypatch):
    writes = []
    monkeypatch.setattr(bf, "write_to_s3",
                        lambda rows, key, s3, bucket: writes.append((key, rows)))
    _patch_common(monkeypatch, [_one_event()])

    bf.run_live(["baseball_mlb"], ["us"], "KEY", s3_client=object(),
                sleep_secs=0, markets_override=["pitcher_strikeouts"])

    assert len(writes) == 1, "exactly one (market, day) partition should be written"
    key, rows = writes[0]
    assert key == "mlb/props/market=pitcher_strikeouts/season=2025/date=2025-06-15/data.parquet"
    # rows carry the CURRENT snapshot (fetch-time UTC 'now'), not a historical timestamp
    assert rows and all(r["market_key"] == "pitcher_strikeouts" for r in rows)
    assert all(r["snapshot_ts"].endswith("+00:00") or r["snapshot_ts"].endswith("Z")
               for r in rows)


def test_live_no_upcoming_games_writes_nothing(monkeypatch):
    writes = []
    monkeypatch.setattr(bf, "write_to_s3",
                        lambda rows, key, s3, bucket: writes.append((key, rows)))
    _patch_common(monkeypatch, [])  # no events → off-window / offday

    bf.run_live(["baseball_mlb"], ["us"], "KEY", s3_client=object(),
                sleep_secs=0, markets_override=["pitcher_strikeouts"])

    assert writes == [], "no upcoming games must not write (and cost) anything"


def test_us_baseball_day_falls_back_without_helper(monkeypatch):
    # If the game_day helper can't import (standalone/local), it must still return a date,
    # never raise — the cron would otherwise hard-fail instead of no-op'ing.
    assert isinstance(bf._us_baseball_day(), date)
