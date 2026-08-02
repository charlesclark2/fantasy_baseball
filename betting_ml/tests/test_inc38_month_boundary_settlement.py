"""INC-38 guard — a game whose Final lands after a month boundary must still settle its bets.

WHAT HAPPENED (2026-08-02; the LOOKBACK sibling of INC-37):

    `ingest_statsapi.py schedule` iterates WHOLE calendar months. INC-37 fixed the FORWARD half
    ("the last capture of July holds no games for 08-01") with `--lookahead-days 3`. Nothing
    fixed the BACKWARD half: once the calendar rolls, every default capture is scoped to the NEW
    month, so no capture ever revisits July again.

    Any game that first-pitches AFTER 00:00 UTC on the 1st — i.e. every West-coast night game on
    the last day of a month — is therefore still Pre-Game or In-Progress in the final same-month
    capture and never gets its Final + score written. Measured on the live lakehouse 2026-08-02:
    14 of 15 games on 07-31 were frozen non-final in stg_statsapi_games (7 'In Progress', 7
    'Pre-Game'), and the ONLY non-terminal historical games in the entire 2026 season sat on
    06-30 (4) and 07-31 (14) — the month boundaries, and nowhere else.

    settle_user_bets grades an h2h/totals bet only when its game reads status_code in ('F','O')
    with scores, so three user bets on two of those games (first pitch 00:40Z and 01:40Z) sat
    PENDING with no error and no alert. It never self-heals — the E9.48 permanent-wrong-state
    class — and the operator found it by reading the bet log two days later.

⚠️ THE NEAR-MISS THAT MAKES THE STATUS GATE LOAD-BEARING: those frozen rows carry NON-NULL
PARTIAL scores (game 824486 sat at 5-3 In Progress). A score-presence check alone would have
settled live bets off a mid-game score. Only `status_code in ('F','O')` prevents it, so that gate
is pinned here.

THREE INDEPENDENT CURES, ALL PINNED — they fail differently, which is why all three exist:
  (1) LOOKBACK — `--lookback-days N` makes the first N captures of every month re-fetch the prior
      month, so the tail of a month always gets a post-midnight capture carrying its finals.
      ⭐ It must be on EVERY caller. The daily op has passed `--start-date <yesterday>` since
      2026-07-15 for exactly this symptom and it did NOT hold, because the S3 raw writer uses
      mode='overwrite_partition' keyed on the FIRE DATE: each fire replaces the whole dt=<today>
      partition with only the months IT pulled, so the month-only intraday tick minutes later
      CLOBBERS the daily's wider fetch. One caller with the flag is not enough.
  (2) DECOUPLED SETTLEMENT — settle h2h/totals off the live Stats API when our own table has no
      final, so a schedule-capture hole can never strand a bet again (the E9.54 theme: settle off
      the intraday-fresh authority, not off a table only as fresh as the build that wrote it).
  (3) THE STALE GUARD — a pending bet whose game first-pitched >24h ago is a PAGE. Nothing else
      distinguishes "the game isn't over yet" from "this game's Final will never arrive".

Source-inspection where it touches `pipeline` (importing it crashes the fast gate at COLLECTION —
`pipeline/__init__.py` reads the dbt manifest, absent in CI: E11.23).
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

import scripts.settle_user_bets as sub
from betting_ml.monitoring.stale_pending_bets import (
    STALE_AFTER_HOURS,
    UNKNOWN,
    classify,
    parse_stale_pending_bets,
)
from scripts.ingest_statsapi import apply_lookahead, apply_lookback, iter_months

REPO = Path(__file__).resolve().parents[2]
DAILY_OPS = REPO / "pipeline" / "ops" / "daily_ingestion_ops.py"
INTRADAY_OPS = REPO / "pipeline" / "ops" / "intraday_ops.py"
SENSOR_OPS = REPO / "pipeline" / "ops" / "sensor_ops.py"
CAPTURE_ENTRYPOINT = REPO / "services" / "schedule_capture" / "entrypoint.sh"
INGEST = REPO / "scripts" / "ingest_statsapi.py"

# EVERY caller of `ingest_statsapi.py schedule`, exhaustively. A per-caller flag fails exactly
# where the registry is incomplete, and that is not hypothetical here: INC-37 shipped
# --lookahead-days to the two Dagster ops and MISSED the lean capture image — which is the LIVE
# 30-min game-day capture (the Dagster intraday op is the retained alternative), i.e. the one
# writing the last snapshot of every month and clobbering everyone else's partition. So INC-37's
# forward cure was never actually on the writer that mattered.
#
# ⛔ app/pages/1_Today_Picks.py also shells out to it — DEPRECATED legacy Streamlit, not deployed,
# deliberately excluded (CLAUDE.md: do not edit).
#
# The third element is the ARGUMENT FORM to accept, and it is load-bearing rather than cosmetic:
# a loose "the flag appears somewhere in the file" match is satisfied by a COMMENT or a docstring
# that merely NAMES the flag — which is exactly what happened while writing these tests (the
# explanatory comment above the fixed command made the guard pass on deliberately-broken source).
# A guard whose assertion can be satisfied by prose is vacuous (the NF1.7 (a) class). So:
#   "list" — must appear as real argv: `"--lookback-days", "3"`. Prose can't produce that.
#   "text" — shell / prescription string, matched only after comment lines are stripped.
SCHEDULE_CALLERS = [
    (DAILY_OPS, "daily ingest_statsapi_schedule", "list"),
    (INTRADAY_OPS, "intraday_schedule_capture", "list"),
    (SENSOR_OPS, "lineup_ingest_schedule (manual/emergency)", "list"),
    (CAPTURE_ENTRYPOINT, "services/schedule_capture (the live 30-min cron)", "text"),
    # Not an invocation but a PRESCRIPTION: the freshness sensor's page tells a human what to run,
    # and the likeliest moment they run it is a boundary morning — so a bare `schedule` in that
    # message re-opens the very hole they are closing. Held to the same standard.
    (REPO / "pipeline" / "sensors" / "schedule_freshness_alert_sensor.py",
     "schedule_freshness_alert_sensor (the remediation it prescribes)", "text"),
]


# ── 1. apply_lookback: the pure month-reach cure ─────────────────────────────

class TestApplyLookback:
    def test_a_capture_on_the_first_reaches_the_previous_month(self):
        # THE BUG, stated as a test: on 08-01 a month-scoped fetch covers August only.
        start = date(2026, 8, 1)
        assert [m for m, _ in iter_months(start, date(2026, 8, 31))] == [date(2026, 8, 1)]
        # With the lookback it also covers July, so 07-31's late finals are re-fetched.
        widened = apply_lookback(start, 3)
        assert widened == date(2026, 7, 29)
        assert [m for m, _ in iter_months(widened, date(2026, 8, 31))] == [
            date(2026, 7, 1), date(2026, 8, 1)
        ]

    @pytest.mark.parametrize("day", [1, 2, 3])
    def test_every_day_inside_the_window_still_reaches_back(self, day):
        start = date(2026, 9, day)
        months = [m for m, _ in iter_months(apply_lookback(start, 3), date(2026, 9, 30))]
        assert date(2026, 8, 1) in months, "the first days of a month must re-fetch the prior one"

    def test_mid_month_costs_nothing_extra(self):
        # The lookback must not widen an ordinary day into a second month fetch.
        start = date(2026, 8, 15)
        months = [m for m, _ in iter_months(apply_lookback(start, 3), date(2026, 8, 31))]
        assert months == [date(2026, 8, 1)]

    @pytest.mark.parametrize("n", [0, -1, -30])
    def test_zero_or_negative_is_a_no_op(self, n):
        assert apply_lookback(date(2026, 8, 1), n) == date(2026, 8, 1)

    def test_it_never_moves_the_start_forward(self):
        for n in range(0, 10):
            assert apply_lookback(date(2026, 8, 1), n) <= date(2026, 8, 1)

    def test_it_is_the_mirror_of_the_inc37_lookahead(self):
        """Together they cover BOTH boundary directions, and each acts only on its own end.

        On the LAST day of a month the lookahead reaches forward (July+August) while the lookback
        stays inside July — the lookback's job starts on the 1st. On the FIRST day it is the
        reverse. Neither ever widens an ordinary mid-month capture.
        """
        last = date(2026, 7, 31)
        assert [m for m, _ in iter_months(apply_lookback(last, 3), apply_lookahead(last, 3))] == [
            date(2026, 7, 1), date(2026, 8, 1)
        ]
        first = date(2026, 8, 1)
        assert [m for m, _ in iter_months(apply_lookback(first, 3), apply_lookahead(first, 3))] == [
            date(2026, 7, 1), date(2026, 8, 1)
        ]
        mid = date(2026, 8, 15)
        assert [m for m, _ in iter_months(apply_lookback(mid, 3), apply_lookahead(mid, 3))] == [
            date(2026, 8, 1)
        ]


# ── 2. BOTH callers must pass it (one alone is clobbered) ────────────────────

def _flag_value(src: str, flag: str, form: str) -> int | None:
    """The value passed for `flag`, matched ONLY in a form prose cannot fake. See SCHEDULE_CALLERS."""
    if form == "list":
        m = re.search(rf'"{re.escape(flag)}",\s*"(\d+)"', src)   # _run_script([... "--x", "3"])
        return int(m.group(1)) if m else None
    code = "\n".join(ln for ln in src.splitlines() if not ln.strip().startswith("#"))
    m = re.search(rf"{re.escape(flag)}\s+(\d+)", code)           # shell / prescription: --x 3
    return int(m.group(1)) if m else None


class TestEveryScheduleCallerCarriesBothGuards:
    """One caller carrying the flag is not enough — see the module docstring's cure (1)."""

    @pytest.mark.parametrize("path,label,form", SCHEDULE_CALLERS)
    def test_caller_passes_a_positive_lookback(self, path, label, form):
        n = _flag_value(path.read_text(), "--lookback-days", form)
        assert n is not None, (
            f"INC-38: {label} must pass --lookback-days so the FIRST captures of a month also "
            "re-fetch the previous one. Without it a game that first-pitches after 00:00 UTC on "
            "the 1st never gets its Final written and its bets stay PENDING forever."
        )
        assert n > 0, f"{label}: --lookback-days must be > 0, got {n}"

    @pytest.mark.parametrize("path,label,form", SCHEDULE_CALLERS)
    def test_caller_still_passes_a_positive_lookahead(self, path, label, form):
        """INC-37's forward cure, now asserted on EVERY caller — it was only ever on two of four,
        and the two it missed include the live capture cron."""
        n = _flag_value(path.read_text(), "--lookahead-days", form)
        assert n is not None, f"INC-37: {label} must pass --lookahead-days"
        assert n > 0, f"{label}: --lookahead-days must be > 0, got {n}"

    @pytest.mark.parametrize("path,label,form", SCHEDULE_CALLERS)
    def test_the_check_is_not_satisfied_by_prose(self, path, label, form):
        """The guard must FAIL on source where the flag survives only in a comment/docstring.

        This is not hypothetical: the first cut of this test matched any occurrence of the flag,
        so the explanatory comment above each fixed command made it pass on source with the flag
        DELETED from the actual command — a guard that could not fail (NF1.7 (a)).
        """
        src = path.read_text()
        for flag in ("--lookback-days", "--lookahead-days"):
            stripped = re.sub(rf'"{re.escape(flag)}",\s*"\d+"', "", src)      # kill argv form
            stripped = "\n".join(                                            # kill shell form
                ln for ln in stripped.splitlines()
                if ln.strip().startswith("#") or flag not in ln
            )
            assert _flag_value(stripped, flag, form) is None, (
                f"{label}: {flag} is still 'found' after removing every real invocation — the "
                "guard is matching prose and would pass on broken source"
            )


    def test_the_caller_registry_is_still_exhaustive(self):
        """A per-caller flag is only as good as the list of callers, so the list itself is pinned.

        If a new module shells out to `ingest_statsapi.py schedule`, this fails until it is added
        to SCHEDULE_CALLERS above — which is what forces the two tests above to cover it too.
        """
        known = {p.resolve() for p, _, _ in SCHEDULE_CALLERS}
        allowed_extra = {
            (REPO / "app" / "pages" / "1_Today_Picks.py").resolve(),  # deprecated Streamlit
            (REPO / "scripts" / "ingest_statsapi.py").resolve(),      # the script itself
        }
        found = set()
        for pattern in ("pipeline/**/*.py", "services/**/*.sh", "scripts/**/*.py", "app/**/*.py"):
            for f in REPO.glob(pattern):
                try:
                    src = f.read_text()
                except (UnicodeDecodeError, OSError):
                    continue
                # An INVOCATION, not a mention: the script name followed by the subcommand, or
                # passed to _run_script with a "schedule" arg.
                if re.search(r'ingest_statsapi\.py["\']?\s*,?\s*\[?\s*["\']?schedule', src):
                    found.add(f.resolve())
        missing = found - known - allowed_extra
        assert not missing, (
            "INC-37/INC-38: these call `ingest_statsapi.py schedule` but are not in "
            f"SCHEDULE_CALLERS, so nothing checks their month-boundary flags: "
            f"{sorted(str(m.relative_to(REPO)) for m in missing)}"
        )

    def test_the_writer_still_overwrites_the_whole_fire_date_partition(self):
        """The reason BOTH callers need the flag, pinned so the rationale can't silently rot.

        run_schedule writes with mode='overwrite_partition' into dt=<fire date>. So a fire
        replaces that partition with only the months IT pulled — a narrow tick erases a wide
        one. If this ever becomes an append, revisit the two-caller requirement above.
        """
        src = INGEST.read_text()
        assert 'mode="overwrite_partition"' in src
        assert "today_dt = fire_ts[:10]" in src


# ── 3. Settlement decoupled from the schedule flatten ────────────────────────

def _sched(game_pk, coded, detailed, home=None, away=None):
    teams = {}
    if home is not None:
        teams["home"] = {"score": home}
    if away is not None:
        teams["away"] = {"score": away}
    return {"gamePk": game_pk, "status": {"codedGameState": coded, "detailedState": detailed},
            "teams": teams}


class TestStatsApiFinalScores:
    def _payload(self, *games):
        return {"dates": [{"games": list(games)}]}

    def _call(self, monkeypatch, payload):
        class _Resp:
            def raise_for_status(self): pass
            def json(self): return payload
        import requests
        monkeypatch.setattr(requests, "get", lambda *a, **k: _Resp())
        return sub._statsapi_final_scores([824325])

    def test_a_terminal_game_yields_its_score_pair(self, monkeypatch):
        got = self._call(monkeypatch, self._payload(_sched(824325, "F", "Final", 6, 3)))
        assert got == {824325: (6, 3)}

    @pytest.mark.parametrize("coded,detailed", [
        ("I", "In Progress"),   # the exact frozen state INC-38 leaves behind
        ("P", "Pre-Game"),
        ("S", "Scheduled"),
    ])
    def test_a_live_or_unstarted_game_is_never_returned(self, monkeypatch, coded, detailed):
        # ⚠️ The frozen rows carry PARTIAL scores; a mid-game score must never settle a bet.
        got = self._call(monkeypatch, self._payload(_sched(824325, coded, detailed, 5, 3)))
        assert got == {}

    def test_a_postponed_game_is_never_returned(self, monkeypatch):
        # 'Final' abstract state with detailedState='Postponed' — the recurring DH landmine.
        got = self._call(monkeypatch, self._payload(_sched(824325, "F", "Postponed", 0, 0)))
        assert got == {}

    def test_a_terminal_game_with_no_score_maps_to_none_not_a_zero(self, monkeypatch):
        # Terminal is still a valid answer for the PROP path, but a game-market bet must not be
        # graded 0-0 off a missing score.
        got = self._call(monkeypatch, self._payload(_sched(824325, "F", "Final")))
        assert got == {824325: None}

    def test_a_network_failure_confirms_nothing(self, monkeypatch):
        import requests
        def _boom(*a, **k):
            raise requests.RequestException("down")
        monkeypatch.setattr(requests, "get", _boom)
        assert sub._statsapi_final_scores([824325]) == {}

    def test_the_prop_path_still_gets_its_set_view(self, monkeypatch):
        payload = self._payload(_sched(824325, "F", "Final", 6, 3), _sched(99, "I", "In Progress"))
        class _Resp:
            def raise_for_status(self): pass
            def json(self): return payload
        import requests
        monkeypatch.setattr(requests, "get", lambda *a, **k: _Resp())
        assert sub._statsapi_final_games([824325, 99]) == {824325}


# ── 4. End-to-end: the INC-38 bets settle without the schedule table ─────────

class _FakeTable:
    def __init__(self, pending):
        self._pending = pending
        self.updates: list[dict] = []

    def scan(self, **kwargs):
        return {"Items": list(self._pending)}

    def update_item(self, **kwargs):
        self.updates.append(kwargs)
        return {}


class _FakeConn:
    def close(self): pass


def _game_bet(bet_id="b1", market="under", game_pk=824325, **over):
    bet = {"user_id": "u1", "bet_id": bet_id, "market": market, "pending_game_pk": game_pk,
           "total_line": 11, "stake": 5, "american_odds": -110}
    bet.update(over)
    return bet


def _install(monkeypatch, pending, *, scores, api_scores=None, first_pitch=None):
    table = _FakeTable(pending)

    class _Res:
        def Table(self, _n): return table

    class _Sess:
        def resource(self, *a, **k): return _Res()

    monkeypatch.setattr(sub, "_aws_session", lambda: _Sess())
    monkeypatch.setattr(sub, "_connect_lakehouse", lambda: _FakeConn())
    monkeypatch.setattr(sub, "_final_scores", lambda conn, pks: dict(scores))
    monkeypatch.setattr(sub, "_starter_strikeouts", lambda conn, pks: {})
    monkeypatch.setattr(sub, "_statsapi_final_scores", lambda pks: dict(api_scores or {}))
    monkeypatch.setattr(sub, "_statsapi_final_games", lambda pks: set())
    monkeypatch.setattr(sub, "_boxscore_starter_strikeouts", lambda gp: {})
    monkeypatch.setattr(sub, "_first_pitch_utc", lambda conn, pks: dict(first_pitch or {}))
    return table


class TestSettlementSurvivesAScheduleHole:
    def test_the_inc38_bet_settles_from_the_live_api(self, monkeypatch):
        """The regression, verbatim: our table has NO final (the 07-31 hole), the game is over."""
        table = _install(monkeypatch, [_game_bet()], scores={}, api_scores={824325: (4, 6)})
        assert sub.main([]) == 0
        assert len(table.updates) == 1
        vals = table.updates[0]["ExpressionAttributeValues"]
        assert vals[":o"] == "win"          # total 10 < line 11 → 'under' wins
        assert vals[":s"] == "statsapi"     # settle_source records the authority used
        assert "REMOVE pending_game_pk" in table.updates[0]["UpdateExpression"]

    def test_it_fails_on_the_pre_fix_code_path(self, monkeypatch):
        """Two-sided proof: with the fallback OFF the bet stays pending — i.e. this test would
        have FAILED before the fix, so it is a real guard and not a tautology."""
        monkeypatch.setenv("SETTLE_SCORE_STATSAPI_FALLBACK", "0")
        table = _install(monkeypatch, [_game_bet()], scores={}, api_scores={824325: (4, 6)})
        assert sub.main([]) == 0
        assert table.updates == []

    def test_the_lakehouse_stays_primary_when_it_has_the_final(self, monkeypatch):
        called = {"api": False}

        def _spy(pks):
            called["api"] = True
            return {}

        table = _install(monkeypatch, [_game_bet()], scores={824325: (4, 6)})
        monkeypatch.setattr(sub, "_statsapi_final_scores", _spy)
        assert sub.main([]) == 0
        assert table.updates[0]["ExpressionAttributeValues"][":s"] == "mart"
        assert not called["api"], "no API call when our own table already answers"

    def test_a_terminal_game_with_no_score_pair_is_left_pending(self, monkeypatch):
        table = _install(monkeypatch, [_game_bet()], scores={}, api_scores={824325: None})
        assert sub.main([]) == 0
        assert table.updates == []

    def test_an_in_progress_game_is_still_left_pending(self, monkeypatch):
        # _statsapi_final_scores already excludes non-terminal games, so the API returns nothing.
        table = _install(monkeypatch, [_game_bet()], scores={}, api_scores={})
        assert sub.main([]) == 0
        assert table.updates == []

    def test_an_h2h_bet_settles_the_same_way(self, monkeypatch):
        bet = _game_bet(market="h2h away", total_line=None)
        table = _install(monkeypatch, [bet], scores={}, api_scores={824325: (4, 6)})
        assert sub.main([]) == 0
        assert table.updates[0]["ExpressionAttributeValues"][":o"] == "win"

    def test_a_prop_bet_does_not_trigger_the_game_market_fallback(self, monkeypatch):
        called = {"api": False}

        def _spy(pks):
            called["api"] = True
            return {}

        prop = {"user_id": "u1", "bet_id": "p1", "market": "strikeouts over",
                "pending_game_pk": 824325, "player_id": 1, "prop_line": 5.5,
                "stake": 5, "american_odds": -110}
        _install(monkeypatch, [prop], scores={})
        monkeypatch.setattr(sub, "_statsapi_final_scores", _spy)
        assert sub.main([]) == 0
        assert not called["api"], "the game-market fallback must not fire for a prop"


# ── 5. The stale-pending-bet guard ───────────────────────────────────────────

def _ago(hours):
    return datetime.now(timezone.utc) - timedelta(hours=hours)


class TestStalePendingMetric:
    def test_a_bet_stuck_past_the_window_is_counted(self, monkeypatch, capsys):
        table = _install(monkeypatch, [_game_bet()], scores={},
                         first_pitch={824325: _ago(STALE_AFTER_HOURS + 6)})
        assert sub.main([]) == 0
        assert table.updates == []
        out = capsys.readouterr()
        assert parse_stale_pending_bets(out.out) == 1
        assert "[ALERT]" in out.err

    def test_a_game_still_in_its_window_is_not_counted(self, monkeypatch, capsys):
        """The other side of the two-sided proof: an ordinary evening slate must NOT page."""
        _install(monkeypatch, [_game_bet()], scores={}, first_pitch={824325: _ago(2)})
        assert sub.main([]) == 0
        assert parse_stale_pending_bets(capsys.readouterr().out) == 0

    def test_a_settled_bet_is_never_counted(self, monkeypatch, capsys):
        _install(monkeypatch, [_game_bet()], scores={824325: (4, 6)},
                 first_pitch={824325: _ago(72)})
        assert sub.main([]) == 0
        assert parse_stale_pending_bets(capsys.readouterr().out) == 0

    def test_an_unknown_first_pitch_can_never_manufacture_a_page(self, monkeypatch, capsys):
        _install(monkeypatch, [_game_bet()], scores={}, first_pitch={})
        assert sub.main([]) == 0
        assert parse_stale_pending_bets(capsys.readouterr().out) == 0

    def test_a_failed_first_pitch_read_reports_unknown_not_healthy(self, monkeypatch, capsys):
        """NF1.7 (a): a guard that could not be evaluated must never be scored as passing."""
        def _boom(conn, pks):
            raise RuntimeError("S3 down")

        _install(monkeypatch, [_game_bet()], scores={})
        monkeypatch.setattr(sub, "_first_pitch_utc", _boom)
        assert sub.main([]) == 0
        assert parse_stale_pending_bets(capsys.readouterr().out) == UNKNOWN

    def test_the_metric_is_emitted_even_with_nothing_pending(self, monkeypatch, capsys):
        # An absent metric is classified UNKNOWN, so a clean pass must still emit 0 — otherwise
        # every quiet day would page WARN.
        _install(monkeypatch, [], scores={})
        assert sub.main([]) == 0
        assert parse_stale_pending_bets(capsys.readouterr().out) == 0

    def test_the_check_never_changes_the_exit_code(self, monkeypatch):
        _install(monkeypatch, [_game_bet()], scores={},
                 first_pitch={824325: _ago(500)})
        assert sub.main([]) == 0, "settlement is WARN-tier; a stuck bet pages, it does not fail"


class TestStalePendingClassifier:
    def test_zero_does_not_page(self):
        assert classify(0)[0] is None

    @pytest.mark.parametrize("n", [1, 3, 40])
    def test_any_stuck_bet_is_critical(self, n):
        sev, msg = classify(n)
        assert sev == "CRITICAL"
        assert str(n) in msg
        assert "lookback" in msg, "the page must name the remediation"

    def test_unevaluated_is_warn_not_silence(self):
        assert classify(UNKNOWN)[0] == "WARN"

    def test_an_absent_metric_is_warn_not_silence(self):
        assert classify(None)[0] == "WARN"

    def test_parse_takes_the_last_value(self):
        stdout = "[METRIC] stale_pending_bets=3\nnoise\n[METRIC] stale_pending_bets=0\n"
        assert parse_stale_pending_bets(stdout) == 0

    def test_parse_ignores_garbage(self):
        assert parse_stale_pending_bets("[METRIC] stale_pending_bets=abc") is None
        assert parse_stale_pending_bets("nothing here") is None


# ── 6. The op actually pages (E11.30: a tier label is not enforcement) ───────

class TestSettleOpPages:
    """Source-inspection — importing pipeline crashes the fast gate at collection (E11.23)."""

    def test_the_settlement_body_passes_stdout_to_the_alerting_hook(self):
        src = DAILY_OPS.read_text()
        assert "_alert_on_stale_pending_bets" in src
        assert re.search(r'stdout\s*=\s*_run_script\(context,\s*"settle_user_bets\.py"\)', src), \
            "the settle body must CAPTURE stdout — the metric rides on it"

    def test_the_hook_calls_send_alert(self):
        src = DAILY_OPS.read_text()
        idx = src.find("def _alert_on_stale_pending_bets")
        assert idx != -1
        body = src[idx:idx + 1600]
        assert "send_alert(" in body, (
            "E11.30: an ALERT-tier check that only reaches context.log.warning is 'detected, "
            "nobody notified' — which is exactly how INC-38 survived two days."
        )
        assert "dedup_key" in body

    def test_a_failed_page_cannot_take_down_the_op(self):
        src = DAILY_OPS.read_text()
        idx = src.find("def _alert_on_stale_pending_bets")
        body = src[idx:idx + 1600]
        assert "except Exception" in body and "send_alert failed" in body
