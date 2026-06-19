"""E1.8 (§7.3) — pin the leakage-critical contract of the sequential as-of lookup.

`asof_lookup.load_seq_posteriors_asof` is THE single sequential-posterior lookup used by both
the training backfill and daily inference. Its leakage safety rests on two invariants that must
never regress (the module docstring calls them out explicitly):
  - a STRICT `game_date < scoring_date` (never `<=`), and
  - it must NEVER use `is_current` (the season-FINAL flag would inject end-of-season info into
    mid-season training rows).
This test captures the SQL the function emits and asserts both — so a regression to `<=` or to
`is_current` fails CI instead of silently re-introducing leakage.
"""

from __future__ import annotations

import re
from datetime import date

from betting_ml.scripts.sequential_bayes import asof_lookup


class _FakeCursor:
    def __init__(self):
        self.executed_sql = None
        self.executed_params = None
        self.description = [(c,) for c in
                            ("PLAYER_ID", "POSTERIOR_MU", "POSTERIOR_SIGMA2", "GAME_DATE", "N_CUMULATIVE")]

    def execute(self, sql, params=None):
        self.executed_sql = sql
        self.executed_params = params

    def fetchall(self):
        return []

    def close(self):
        return None


class _FakeConn:
    def __init__(self):
        self.cur = _FakeCursor()

    def cursor(self):
        return self.cur


def _run_lookup():
    conn = _FakeConn()
    out = asof_lookup.load_seq_posteriors_asof(
        conn, player_ids=["123", "456"], player_type="batter",
        metric="xwoba", game_date=date(2024, 6, 1), season=2024,
    )
    return conn.cur, out


def test_lookup_uses_strict_less_than_and_never_is_current():
    cur, out = _run_lookup()
    sql = cur.executed_sql
    assert sql is not None and out == {}

    # STRICT inequality on game_date, parameterized — robust to whitespace reformatting.
    assert re.search(r"game_date\s*<\s*%\(game_date\)s", sql), \
        "as-of guard must keep the strict `game_date < %(game_date)s` filter"
    # ...and NOT a leaky `<=`.
    assert not re.search(r"game_date\s*<=", sql), "as-of guard must NOT relax to `<=`"
    # NEVER is_current (would inject season-final info into mid-season training rows).
    assert "is_current" not in sql.lower(), "as-of lookup must NEVER use is_current"
    # latest-prior selection preserved.
    assert re.search(r"order\s+by\s+game_date\s+desc", sql, re.IGNORECASE)

    # game_date is passed as an ISO string param (write_pandas date-serialization safety).
    assert cur.executed_params["game_date"] == "2024-06-01"
    assert cur.executed_params["season"] == 2024


def test_empty_player_ids_short_circuits_without_querying():
    conn = _FakeConn()
    out = asof_lookup.load_seq_posteriors_asof(
        conn, player_ids=[], player_type="batter", metric="xwoba",
        game_date=date(2024, 6, 1), season=2024,
    )
    assert out == {}
    assert conn.cur.executed_sql is None      # no query issued for an empty id list
