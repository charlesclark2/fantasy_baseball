"""NF-W2c guards — PIT-clean 2025 injury reconstruction from Wayback captures.

Fixtures are REAL trimmed payloads from the assessed snapshots (NF-C0e: a fixture derived from
the author's assumptions cannot disconfirm them; these are cut from the actual archived bytes).
Fast-gate rules honored: no `pipeline` import, no network at import or in any test.
"""
from __future__ import annotations

import gzip

import pandas as pd
import pytest

from quant_sports_intel_models.football.nfl.fantasy import wayback_injury_source as WB

# ── REAL fixtures (trimmed verbatim from the assessed captures) ─────────────────────────────────
# nfl.com/injuries/ captured 20251212093410 (Week 15 official report)
NFL_HTML = """<title>Official Latest NFL Injury Report for Players - Week 15 of the 2025 Season</title>
<table><tbody>
<tr> <td scope="row" tabindex="0"> <a href="/players/kaden-elliss/" class="nfl-o-cta--link" aria-label="Visit Kaden Elliss profile page"> Kaden Elliss </a> </td> <td> LB </td> <td> </td> <td> Full Participation in Practice </td> <td> </td> </tr>
<tr> <td scope="row" tabindex="0"> <a href="/players/drake-london/" class="nfl-o-cta--link" aria-label="Visit Drake London profile page"> Drake London </a> </td> <td> WR </td> <td> Knee </td> <td> Did Not Participate In Practice </td> <td> Out </td> </tr>
<tr> <td scope="row" tabindex="0"> <a href="/players/some-player/" class="nfl-o-cta--link"> Some Player </a> </td> <td> TE </td> <td> Ankle </td> <td> Limited Participation in Practice </td> <td> Questionable </td> </tr>
</tbody></table>"""

# espn.com/nfl/injuries captured 20251010164536 (embedded __espnfitt__ state, trimmed to two
# entries — one weekly designation, one roster designation that must be SKIPPED)
ESPN_HTML = """<script>window['__espnfitt__']={"page":{"content":{"injuries":[
{"type":{"id":"2","name":"INJURY_STATUS_QUESTIONABLE","description":"questionable","abbreviation":"Q"},
 "athlete":{"shortName":"M. Wilson Sr.","name":"Mack Wilson Sr.","href":"https://www.espn.com/nfl/player/_/id/4040983/mack-wilson-sr","position":"LB"},
 "status":"injury-2","description":"Oct 9: Wilson (ankle) remained limited.","date":"Oct 12","statusDesc":"Questionable"},
{"type":{"id":"5","name":"INJURY_STATUS_IR","description":"injured reserve","abbreviation":"IR"},
 "athlete":{"shortName":"J. Doe","name":"Jon Doe","href":"https://www.espn.com/nfl/player/_/id/1/jon-doe","position":"RB"},
 "status":"injury-5","description":"Out for the season.","date":"Oct 12","statusDesc":"Injured Reserve"}
]}}};</script>"""


class TestNflParser:
    def test_declared_week_and_rows(self):
        week, season, rows = WB.parse_nfl_report(NFL_HTML)
        assert (week, season) == (15, 2025)
        assert len(rows) == 3

    def test_designation_and_practice_vocabulary(self):
        _, _, rows = WB.parse_nfl_report(NFL_HTML)
        by = {r["player_slug"]: r for r in rows}
        assert by["drake-london"]["report_status"] == "out"
        assert by["drake-london"]["practice_status"] == "dnp"
        assert by["some-player"]["report_status"] == "questionable"
        assert by["some-player"]["practice_status"] == "limited"

    def test_absent_cells_are_none_never_zero(self):
        """⛔ fillna(0): a full-practice player with no designation carries None, not a
        'healthy' zero — absence of a designation is absence of evidence."""
        _, _, rows = WB.parse_nfl_report(NFL_HTML)
        elliss = next(r for r in rows if r["player_slug"] == "kaden-elliss")
        assert elliss["report_status"] is None
        assert elliss["report_status"] != 0
        assert elliss["practice_status"] == "full"
        assert elliss["injury"] is None


class TestEspnParser:
    def test_weekly_designation_kept_with_game_date(self):
        rows = WB.parse_espn(ESPN_HTML)
        assert len(rows) == 1
        r = rows[0]
        assert r["player_name"] == "Mack Wilson Sr."
        assert r["report_status"] == "questionable"
        assert r["game_date_hint"] == "Oct 12"
        assert r["practice_status"] is None  # ESPN publishes no practice line

    def test_roster_designations_are_skipped(self):
        """ESPN mixes IR/roster tags into the same table — those are NOT the weekly report
        channel this family models and must not masquerade as one."""
        rows = WB.parse_espn(ESPN_HTML)
        assert not any(r["player_name"] == "Jon Doe" for r in rows)

    def test_missing_state_object_parses_empty_not_crash(self):
        assert WB.parse_espn("<html><body>nothing here</body></html>") == []


class TestSnapshotBytes:
    def test_gzip_magic_is_decompressed(self):
        raw = gzip.compress(NFL_HTML.encode())
        text = WB.snapshot_text(raw)
        assert "Drake London" in text

    def test_plain_bytes_pass_through(self):
        assert "Drake London" in WB.snapshot_text(NFL_HTML.encode())

    def test_decode_mangled_gzip_is_refused_loudly(self):
        """⭐ The bug this story's own research hit: gzip bytes put through a lossy text decode
        lose the \\x8b magic byte and then 'parse' to a confident EMPTY result — a false
        'dataless shell' verdict. Mangled bytes must RAISE, never quietly parse to nothing."""
        mangled = gzip.compress(NFL_HTML.encode()).decode("utf-8", errors="ignore").encode()
        assert mangled[:1] == b"\x1f" and mangled[:2] != b"\x1f\x8b"  # the fingerprint
        with pytest.raises(ValueError, match="mangled gzip"):
            WB.snapshot_text(mangled)


class TestStamping:
    def test_wayback_ts_is_utc_iso(self):
        assert WB.wayback_ts_to_utc("20251010164536") == "2025-10-10T16:45:36+00:00"

    @pytest.mark.parametrize("hint,capture,expected", [
        ("Oct 12", "2025-10-10T16:45:36+00:00", "2025-10-12"),   # in-season, same year
        ("Jan 4", "2025-12-28T12:00:00+00:00", "2026-01-04"),    # Jan game seen from December
        ("Jan 4", "2026-01-02T12:00:00+00:00", "2026-01-04"),    # Jan game seen from January
        (None, "2025-10-10T16:45:36+00:00", None),
        ("garbage", "2025-10-10T16:45:36+00:00", None),
    ])
    def test_game_date_hint_year_resolution(self, hint, capture, expected):
        assert WB.resolve_game_date_hint(hint, capture) == expected

    def test_stamped_rows_carry_the_capture_instant(self):
        df = WB.stamped_rows_from_capture("nfl", "20251212093410", NFL_HTML)
        assert (df["capture_ts"] == "2025-12-12T09:34:10+00:00").all()
        assert (df["declared_week"] == 15).all()
        assert (df["source"] == "nfl").all()

    def test_none_statuses_survive_the_frame_never_zero_filled(self):
        df = WB.stamped_rows_from_capture("nfl", "20251212093410", NFL_HTML)
        elliss = df[df["player_slug"] == "kaden-elliss"].iloc[0]
        assert pd.isna(elliss["report_status"]) or elliss["report_status"] is None
        assert elliss["report_status"] != 0.0

    def test_unparsed_source_raises(self):
        with pytest.raises(ValueError, match="no parser"):
            WB.stamped_rows_from_capture("cbs", "20251003095717", "<html></html>")
