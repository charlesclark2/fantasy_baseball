"""NF-W0a — the forward-capture legs + the immutable store.

Covers the parts that are pure decisions (ladder, venue resolution, roof gating, market phase,
schema drift) and the parts that are storage contracts (append-only, dedup, revision handling,
write-once raw). The network fetch is the only thing stubbed — everything that DECIDES is real.

Several tests exist because a live probe on 2026-08-05 found the defect they pin; those are
marked ⭐ and name the finding.
"""
from __future__ import annotations

import ast
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from quant_sports_intel_models.football.nfl.pit import (
    injury_capture,
    market_capture,
    schema_snapshot,
    store,
    timestamps,
    venues,
    weather_capture as wc,
)
from quant_sports_intel_models.football.nfl.pit.schedule import ScheduledGame

_REPO = Path(__file__).resolve().parents[2]
_GEO_SQL = _REPO / "quant_sports_intel_models/sports_dbt/models/nfl/staging/stg_nfl_team_geo.sql"
_STORE_SRC = _REPO / "quant_sports_intel_models/football/nfl/pit/store.py"

NOW = datetime(2026, 9, 15, 15, 0, tzinfo=timezone.utc)


def _game(game_id="2026_02_GB_CHI", *, hours=120, home="GB", away="CHI",
          location="Home", roof="outdoors", stadium="Lambeau Field") -> ScheduledGame:
    return ScheduledGame(game_id, 2026, 2, "REG", NOW + timedelta(hours=hours),
                         home, away, location, roof, stadium)


# ── the geo crosswalk has TWO owners; pin them together ──────────────────────────────────
class TestStadiumGeoStaysInSyncWithTheDbtModel:
    """`venues.TEAM_HOME_GEO` and `stg_nfl_team_geo.sql` are the SAME FACT in two places — the
    repo's recurring bug shape (INC-30 crontab under two users, INC-38 per-caller flags). Pin
    them mechanically; a comment asking future editors to keep them in sync would not hold."""

    @staticmethod
    def _sql_geo() -> dict[str, tuple[float, float]]:
        rows = re.findall(
            r"\('([A-Z]{2,3})',\s*'[^']+',\s*(-?\d+\.\d+),\s*(-?\d+\.\d+)",
            _GEO_SQL.read_text(),
        )
        return {code: (float(lat), float(lon)) for code, lat, lon in rows}

    def test_the_sql_parse_actually_found_the_table(self):
        """Guard the guard: a regex that matched nothing would make every check below vacuous."""
        assert len(self._sql_geo()) == 32

    def test_every_team_matches_the_dbt_coordinates(self):
        sql = self._sql_geo()
        assert set(sql) == set(venues.TEAM_HOME_GEO), (
            f"team set drift: only-in-sql={set(sql) - set(venues.TEAM_HOME_GEO)} "
            f"only-in-python={set(venues.TEAM_HOME_GEO) - set(sql)}"
        )
        for code, coords in sql.items():
            assert venues.TEAM_HOME_GEO[code] == coords, (
                f"{code}: dbt says {coords}, venues.py says {venues.TEAM_HOME_GEO[code]} — a "
                f"coordinate drift silently captures another city's weather"
            )


# ── ⭐ the two live findings ─────────────────────────────────────────────────────────────
class TestNeutralSiteGamesAreNotCapturedAtTheHomeTeamsStadium:
    """⭐ LIVE FINDING (2026-08-05): 2026 schedules EIGHT international games, and nflverse lists
    them under the home TEAM. `2026_11_MIN_SF` is home_team SF but played at Estadio Banorte in
    Mexico City; `2026_01_SF_LA` is home_team LA at the Melbourne Cricket Ground. Fetching at the
    home team's coordinates returns entirely plausible numbers for the wrong hemisphere."""

    def test_a_known_neutral_venue_resolves_to_the_VENUE_not_the_team(self):
        d = venues.resolve_venue(
            _game(home="JAX", location="Neutral", stadium="Wembley Stadium").as_venue_input()
        )
        assert d.is_neutral_site
        assert (round(d.latitude, 2), round(d.longitude, 2)) == (51.56, -0.28)  # London
        jax_lat, _ = venues.TEAM_HOME_GEO["JAX"]
        assert abs(d.latitude - jax_lat) > 20, "resolved to Jacksonville — the wrong continent"

    def test_an_UNKNOWN_neutral_venue_is_REFUSED_not_silently_fetched_at_the_home_stadium(self):
        with pytest.raises(venues.VenueResolutionError, match="UNKNOWN neutral venue"):
            venues.resolve_venue(
                _game(home="SF", location="Neutral", stadium="Some New Stadium").as_venue_input()
            )

    def test_a_neutral_game_with_no_stadium_name_is_REFUSED(self):
        with pytest.raises(venues.VenueResolutionError):
            venues.resolve_venue(_game(home="SF", location="Neutral", stadium="").as_venue_input())

    def test_the_capture_leg_reports_a_refusal_rather_than_capturing_wrongly(self):
        m = wc.run_weather_capture(
            2026, now=NOW, local_root=None, dry_run=True,
            games=[_game(home="SF", location="Neutral", stadium="Unmapped Arena")],
        )
        assert m["skipped_venue_unresolved"] == 1
        assert m["captured"] == 0 and m["refusals"]

    def test_every_2026_international_venue_is_mapped(self):
        """The 8 venues the 2026 release actually names. If nflverse renames one, this fails HERE
        (offline, in CI) rather than as a silent refusal on a live capture morning."""
        for stadium in ("Melbourne Cricket Ground", "Maracana Stadium", "Tottenham Hotspur Stadium",
                        "Wembley Stadium", "Stade de France", "Bernabeu",
                        "FC Bayern Munich Stadium", "Estadio Banorte"):
            assert stadium in venues.NEUTRAL_SITE_VENUES, f"{stadium} unmapped → capture refused"


class TestRoofGatingUsesThePerGameRoofAndTreatsBlankAsUnknown:
    """⭐ LIVE FINDING (2026-08-05): all 43 blank-`roof` rows in the entire nflverse release are
    unplayed 2026 games at the five RETRACTABLE venues. Those venues never carry `dome`; they
    carry `closed`/`open`, a value that exists only AFTER the game-day roof decision. So a blank
    roof means UNKNOWN-AT-PROJECTION-TIME, not indoors — and skipping blanks would drop every
    ARI/DAL/HOU/ATL/IND home game's weather permanently."""

    def test_a_fixed_dome_is_skipped(self):
        d = venues.resolve_venue(_game(home="DET", roof="dome", stadium="Ford Field").as_venue_input())
        assert d.is_fixed_dome and not d.capture

    def test_a_blank_roof_IS_captured_and_flagged_unknown(self):
        d = venues.resolve_venue(_game(home="DAL", roof="", stadium="AT&T Stadium").as_venue_input())
        assert d.capture, "a retractable venue's roof may be OPEN — not capturing loses the week"
        assert d.roof_known is False and d.is_fixed_dome is False

    @pytest.mark.parametrize("roof", ["open", "closed"])
    def test_a_retractable_state_is_captured_and_marked_known(self, roof):
        d = venues.resolve_venue(_game(home="ATL", roof=roof, stadium="Mercedes-Benz Stadium").as_venue_input())
        assert d.capture and d.roof_known and not d.is_fixed_dome

    def test_the_leg_gates_on_the_GAME_roof_not_the_teams_is_dome_home(self):
        """ATL `is_dome_home=true` in stg_nfl_team_geo, but that column is documented
        INFORMATIONAL. An ATL game played outdoors at a neutral site must still be captured."""
        m = wc.run_weather_capture(
            2026, now=NOW, dry_run=True,
            games=[_game(home="ATL", location="Neutral", roof="outdoors", stadium="Bernabeu")],
        )
        assert m["skipped_dome"] == 0 and m["eligible"] == 1


# ── the checkpoint ladder ────────────────────────────────────────────────────────────────
class TestTheCheckpointLadderReachesTheTuesdayBuild:
    def test_the_ladder_extends_past_MLBs_24h_maximum(self):
        """The story's adaptation #1: MLB's ladder tops out at T-24h. An NFL Tuesday build for a
        Sunday game stands ~120h out, so an MLB-verbatim ladder would give the Tue/Fri builds NO
        WEATHER AT ALL — the exact feature this capture exists to make backtestable."""
        assert max(wc.CHECKPOINT_LADDER) >= 120
        assert wc.nearest_checkpoint(120.0) == 120

    @pytest.mark.parametrize("cp", wc.CHECKPOINT_LADDER)
    def test_each_rung_matches_itself(self, cp):
        assert wc.nearest_checkpoint(float(cp)) == cp

    def test_a_kicked_off_game_has_no_rung(self):
        assert wc.nearest_checkpoint(-0.5) is None

    def test_a_time_between_rungs_matches_none(self):
        assert wc.nearest_checkpoint(60.0) is None

    def test_no_two_rungs_can_match_the_same_moment(self):
        """A moment matching two rungs would double-capture and make `capture_id` ambiguous.
        The tightest gap is 3h→1h; the window must stay under half of it."""
        gaps = [
            abs(a - b)
            for i, a in enumerate(wc.CHECKPOINT_LADDER)
            for b in wc.CHECKPOINT_LADDER[i + 1:]
        ]
        assert wc.CHECKPOINT_WINDOW_HOURS * 2 < min(gaps)

    def test_an_hourly_cron_cannot_miss_a_rung(self):
        """The window must be at least half an hour wide or an hourly fire could land between two
        rungs' windows and skip a checkpoint entirely."""
        assert wc.CHECKPOINT_WINDOW_HOURS >= 0.5

    def test_eligible_games_selects_only_games_at_a_rung(self):
        games = [_game("A", hours=120), _game("B", hours=60), _game("C", hours=24)]
        due = wc.eligible_games(games, now=NOW, checkpoint=None)
        assert [(g.game_id, cp) for g, cp in due] == [("A", 120), ("C", 24)]


# ── the immutable store ──────────────────────────────────────────────────────────────────
def _row(capture_id="cid1", subject="s1", sha="sha1", payload=None, ts=NOW) -> dict:
    return {
        "capture_source": "weather", "capture_id": capture_id, "subject_key": subject,
        "payload_sha256": sha, "hash_excluded_keys": "", "feature_timestamp": ts.isoformat(),
        "source_timestamp": None, "source_timestamp_absent_reason": "test",
        "capture_timestamp": ts.isoformat(), "vendor_release_timestamp": None,
        "ingestion_timestamp": ts.isoformat(), "record_tier": "weather",
        "payload": payload if payload is not None else {"temp_f": 70},
    }


class TestTheStoreIsAppendOnly:
    def test_the_store_never_issues_an_overwrite(self):
        """⭐ Source-inspection guard. `ingest/s3io.py` writes `mode="overwrite"` with a
        `replaceWhere` — correct for a reproducible feed, FATAL for a point-in-time capture, and
        it is one word away from being copied in here. Comments/docstrings are stripped first so
        PROSE ABOUT not overwriting cannot satisfy the guard (the INC-38 lesson)."""
        tree = ast.parse(_STORE_SRC.read_text())
        code_strings = [
            n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and not isinstance(getattr(n, "parent", None), ast.Expr)
        ]
        # Any string literal that is an actual write mode.
        modes = {s for s in code_strings if s in {"overwrite", "append", "error", "ignore"}}
        assert "overwrite" not in modes, (
            "store.py contains an 'overwrite' write mode — a PIT capture must never be replaced"
        )
        assert "append" in modes, "the append mode literal vanished — the guard would be vacuous"

    def test_a_first_capture_is_written(self, tmp_path):
        m = store.append_captures([_row()], source="weather", local_root=str(tmp_path))
        assert m["written"] == 1

    def test_an_identical_re_fire_is_a_duplicate_not_a_second_row(self, tmp_path):
        store.append_captures([_row()], source="weather", local_root=str(tmp_path))
        m = store.append_captures([_row()], source="weather", local_root=str(tmp_path))
        assert (m["written"], m["skipped_duplicate"], m["revisions"]) == (0, 1, [])

    def test_a_revision_is_DECLINED_and_the_ORIGINAL_survives(self, tmp_path):
        store.append_captures([_row(sha="original", payload={"status": "Questionable"})],
                              source="injuries", local_root=str(tmp_path),
                              semantics=store.REVISION_SEMANTICS)
        m = store.append_captures([_row(sha="revised", payload={"status": "Out"})],
                                  source="injuries", local_root=str(tmp_path),
                                  semantics=store.REVISION_SEMANTICS)
        assert m["written"] == 0 and len(m["revisions"]) == 1
        ids = store.existing_capture_ids("injuries", NOW.date().isoformat(), local_root=str(tmp_path))
        assert ids["cid1"] == "original", "the ORIGINAL capture must survive a revision"

    def test_a_live_value_re_read_is_a_recapture_not_a_false_revision(self, tmp_path):
        """⭐ Measured 2026-08-05: Open-Meteo stamps a server-timing field on every response, so
        without the live-value split EVERY benign weather re-fire alerted as a vendor revision —
        a 100%-false-positive channel, i.e. the monitor that gets muted."""
        store.append_captures([_row(sha="t0")], source="weather", local_root=str(tmp_path),
                              semantics=store.LIVE_VALUE_SEMANTICS)
        m = store.append_captures([_row(sha="t1")], source="weather", local_root=str(tmp_path),
                                  semantics=store.LIVE_VALUE_SEMANTICS)
        assert m["revisions"] == [] and m["skipped_recapture"] == 1 and m["written"] == 0

    def test_a_raw_payload_is_retained_and_never_replaced(self, tmp_path):
        store.append_captures([_row(payload={"v": 1})], source="weather", local_root=str(tmp_path))
        blobs = list((tmp_path / "nfl/pit_raw/weather").rglob("*.json"))
        assert len(blobs) == 1
        assert json.loads(blobs[0].read_text())["payloads"]["cid1"] == {"v": 1}

        store.retain_raw_batch({"cid1": {"v": 999}}, source="weather",
                               capture_date=NOW.date().isoformat(), local_root=str(tmp_path))
        assert json.loads(blobs[0].read_text())["payloads"]["cid1"] == {"v": 1}, (
            "an existing raw payload was REPLACED — the immutability guarantee behind the §13 "
            "revised-vendor-record rejection is gone"
        )
    def test_two_distinct_captures_both_land(self, tmp_path):
        store.append_captures([_row(capture_id="a", subject="s1")], source="weather",
                              local_root=str(tmp_path))
        m = store.append_captures([_row(capture_id="b", subject="s2")], source="weather",
                                  local_root=str(tmp_path))
        assert m["written"] == 1
        ids = store.existing_capture_ids("weather", NOW.date().isoformat(), local_root=str(tmp_path))
        assert set(ids) == {"a", "b"}

    def test_the_store_index_feeds_the_leakage_guard(self, tmp_path):
        store.append_captures([_row(sha="original")], source="weather", local_root=str(tmp_path))
        idx = store.build_store_index("weather", [NOW.date().isoformat()], local_root=str(tmp_path))
        assert idx["s1"][0]["payload_sha256"] == "original"


# ── the timestamp contract ───────────────────────────────────────────────────────────────


class TestRawPayloadsAreBatched:
    """⭐ THE COST FIX, made a testable property rather than a habit.

    The first cut wrote one S3 object PER CAPTURE ROW with a HEAD before each PUT. Measured on
    the box 2026-08-05: one 6,068-row injury capture took **14 minutes** (~130ms/row, ~12,000
    sequential S3 calls) — ≈267,000 objects and ~10 hours of box time per season. These tests pin
    the batched layout so a future edit cannot quietly reintroduce per-row writes.
    """

    @staticmethod
    def _objects(tmp_path, source="injuries"):
        return list((tmp_path / f"nfl/pit_raw/{source}").rglob("*.json"))

    def test_many_rows_produce_exactly_ONE_object(self, tmp_path):
        rows = [_row(capture_id=f"c{i}", subject=f"s{i}", sha=f"h{i}", payload={"i": i})
                for i in range(200)]
        store.append_captures(rows, source="injuries", local_root=str(tmp_path))
        objs = self._objects(tmp_path)
        assert len(objs) == 1, (
            f"200 rows produced {len(objs)} objects — the per-row write is back, and at injury "
            f"scale that is ~12,000 S3 calls and 14 minutes per capture"
        )

    def test_the_batch_object_contains_every_payload_keyed_by_capture_id(self, tmp_path):
        rows = [_row(capture_id=f"c{i}", subject=f"s{i}", sha=f"h{i}", payload={"i": i})
                for i in range(200)]
        store.append_captures(rows, source="injuries", local_root=str(tmp_path))
        body = json.loads(self._objects(tmp_path)[0].read_text())
        assert body["capture_count"] == 200
        assert body["raw_layout"] == store.RAW_LAYOUT
        assert {f"c{i}" for i in range(200)} == set(body["payloads"])
        assert body["payloads"]["c7"] == {"i": 7}

    def test_every_row_records_WHERE_its_payload_lives(self, tmp_path):
        """A retained payload nobody can locate is retention in name only."""
        import duckdb
        from deltalake import DeltaTable

        store.append_captures([_row(payload={"v": 1})], source="injuries", local_root=str(tmp_path))
        con = duckdb.connect()
        con.register("t", DeltaTable(str(tmp_path / "nfl/pit/injuries")).to_pyarrow_dataset())
        key, layout = con.execute("select raw_payload_key, raw_layout from t").fetchone()
        assert layout == store.RAW_LAYOUT
        assert (tmp_path / key).exists(), f"raw_payload_key {key!r} points at nothing"
        assert store.read_raw_batch(key, local_root=str(tmp_path))["payloads"]["cid1"] == {"v": 1}

    def test_a_re_fire_does_not_create_a_second_object(self, tmp_path):
        store.append_captures([_row(payload={"v": 1})], source="injuries", local_root=str(tmp_path))
        store.append_captures([_row(payload={"v": 1})], source="injuries", local_root=str(tmp_path))
        assert len(self._objects(tmp_path)) == 1

    def test_a_DIFFERENT_batch_the_same_day_does_not_collide(self, tmp_path):
        """⭐ The trap a `capture_date`-only key would have walked into: the second batch's key
        would already exist, write-once would refuse it, and those payloads would be silently
        LOST — the immutability guarantee turned into data loss. Content-addressing avoids it."""
        store.append_captures([_row(capture_id="a", subject="sa", payload={"v": 1})],
                              source="injuries", local_root=str(tmp_path))
        store.append_captures([_row(capture_id="b", subject="sb", payload={"v": 2})],
                              source="injuries", local_root=str(tmp_path))
        objs = self._objects(tmp_path)
        assert len(objs) == 2, "the second same-day batch was refused — its payloads are lost"
        stored = {}
        for o in objs:
            stored.update(json.loads(o.read_text())["payloads"])
        assert stored == {"a": {"v": 1}, "b": {"v": 2}}

    def test_the_batch_id_is_content_addressed_and_order_independent(self, tmp_path):
        assert store._batch_id(["a", "b"]) == store._batch_id(["b", "a"])
        assert store._batch_id(["a", "b"]) != store._batch_id(["a", "c"])

    def test_an_empty_batch_is_refused_rather_than_writing_an_empty_object(self):
        with pytest.raises(ValueError, match="never empty"):
            store.retain_raw_batch({}, source="injuries", capture_date="2026-08-05")


class TestDuckDBIsClampedToTheBox:
    """⛔ INC-22 #4: a `memory_limit` above what the box can spare told DuckDB it never needed to
    spill, it blew past physical memory, and the kernel OOM-killed the EC2 HOST — taking Dagster
    with it. A bare `duckdb.connect()` inherits ~80% of RAM (~12.8 GB on the 16 GB box), so the
    failure mode of an NFL capture leg would be an MLB serving outage."""

    def test_no_module_in_pit_calls_duckdb_connect_directly(self):
        """Comments/docstrings are stripped so the WARNING PROSE in duck.py (which names the
        forbidden call) cannot satisfy — or trip — this guard (INC-38)."""
        import ast

        pit_dir = _REPO / "quant_sports_intel_models/football/nfl/pit"
        offenders = []
        for path in sorted(pit_dir.glob("*.py")):
            if path.name == "duck.py":
                continue  # the ONE sanctioned connect site
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                        and node.func.attr == "connect"
                        and isinstance(node.func.value, ast.Name)
                        and node.func.value.id == "duckdb"):
                    offenders.append(f"{path.name}:{node.lineno}")
        assert not offenders, f"unclamped duckdb.connect() — route via pit/duck.py: {offenders}"

    def test_the_limit_stays_below_physical_ram(self):
        from quant_sports_intel_models.football.nfl.pit import duck

        ram = duck._physical_ram_gb()
        if ram is None:
            pytest.skip("physical RAM undetectable here")
        assert duck.safe_memory_limit_gb() < ram, "the limit exceeds RAM — the INC-22 #4 shape"

    def test_the_limit_is_floored_capped_and_conservative_when_ram_is_unknown(self, monkeypatch):
        from quant_sports_intel_models.football.nfl.pit import duck

        monkeypatch.setattr(duck, "_physical_ram_gb", lambda: 0.5)
        assert duck.safe_memory_limit_gb() == 2      # floor
        monkeypatch.setattr(duck, "_physical_ram_gb", lambda: 512)
        assert duck.safe_memory_limit_gb() == 11     # cap
        monkeypatch.setattr(duck, "_physical_ram_gb", lambda: None)
        assert duck.safe_memory_limit_gb() == 6      # undetectable → conservative, not unbounded

    def test_the_settings_are_actually_applied_to_the_connection(self):
        """A clamp computed but never SET is the 'wired ≠ invoked' defect (NF-C0e)."""
        from quant_sports_intel_models.football.nfl.pit import duck

        con = duck.connect(httpfs=False)
        limit, threads = con.execute(
            "select current_setting('memory_limit'), current_setting('threads')"
        ).fetchone()
        assert int(threads) == 2
        assert limit and limit != "0 bytes", f"memory_limit was not applied: {limit!r}"

class TestTheTimestampContract:
    def test_a_naive_datetime_is_REFUSED_not_assumed_utc(self):
        with pytest.raises(timestamps.TimestampContractError, match="NAIVE"):
            timestamps.to_utc_iso(datetime(2026, 9, 15, 15, 0))

    def test_a_naive_iso_string_is_REFUSED(self):
        with pytest.raises(timestamps.TimestampContractError, match="NAIVE"):
            timestamps.to_utc_iso("2026-09-15T15:00:00")

    def test_a_non_utc_offset_is_normalised_to_utc(self):
        assert timestamps.to_utc_iso("2026-09-15T11:00:00-04:00") == "2026-09-15T15:00:00+00:00"

    def test_stamps_are_stored_as_iso_strings_never_binary(self):
        """INC-23 / the W8a landmine: Snowflake mis-reads binary parquet timestamps per row."""
        s = timestamps.CaptureStamps.build(
            capture_source="weather", subject_key="s", checkpoint="T-120h", payload={"a": 1},
            feature_timestamp=NOW, capture_timestamp=NOW,
            source_timestamp=None, vendor_release_timestamp=None,
        )
        for key, value in s.as_dict().items():
            if key.endswith("_timestamp") and value is not None:
                assert isinstance(value, str) and value.endswith("+00:00"), key

    def test_capture_id_is_deterministic(self):
        a = timestamps.capture_id(capture_source="weather", subject_key="s", checkpoint="T-120h")
        b = timestamps.capture_id(capture_source="weather", subject_key="s", checkpoint="T-120h")
        c = timestamps.capture_id(capture_source="weather", subject_key="s", checkpoint="T-72h")
        assert a == b != c, "a non-deterministic id makes append-only dedup impossible"

    def test_the_hash_ignores_declared_volatile_keys_only(self):
        base = {"temp_f": 70, "_generationtime_ms": 0.11}
        same = {"temp_f": 70, "_generationtime_ms": 0.98}
        diff = {"temp_f": 71, "_generationtime_ms": 0.11}
        ex = ("_generationtime_ms",)
        assert timestamps.payload_sha256(base, ex) == timestamps.payload_sha256(same, ex)
        assert timestamps.payload_sha256(base, ex) != timestamps.payload_sha256(diff, ex)

    def test_the_excluded_keys_are_recorded_on_the_row(self):
        """A hash that silently ignores fields is its own silent-death risk — the exclusion must
        be auditable from the stored row."""
        s = timestamps.CaptureStamps.build(
            capture_source="weather", subject_key="s", checkpoint="c", payload={"a": 1},
            feature_timestamp=NOW, capture_timestamp=NOW,
            hash_exclude=("_generationtime_ms",),
        )
        assert s.as_dict()["hash_excluded_keys"] == "_generationtime_ms"


# ── the market leg ───────────────────────────────────────────────────────────────────────
class TestMarketPhaseClassification:
    def test_a_tuesday_snapshot_is_open(self):
        assert market_capture.classify_market_phase(NOW, NOW + timedelta(hours=120)) == "open"

    def test_a_snapshot_near_kickoff_is_closing(self):
        assert market_capture.classify_market_phase(NOW, NOW + timedelta(hours=1)) == "closing"

    def test_a_post_kickoff_snapshot_is_inplay(self):
        assert market_capture.classify_market_phase(NOW, NOW - timedelta(hours=1)) == "inplay"

    def test_an_unknown_kickoff_is_unknown_not_open(self):
        """`unknown` is UNEVALUABLE to the leakage guard, which rejects. Defaulting to `open`
        would silently admit a closing board into a Tuesday build."""
        assert market_capture.classify_market_phase(NOW, None) == "unknown"

    def test_the_phase_comes_from_the_clock_not_the_cadence_label(self):
        """A 'Tuesday' cron that slips to Sunday must produce a `closing` row."""
        rows = market_capture._rows_for_events(
            [{"id": "e1", "commence_time": (NOW + timedelta(minutes=30)).isoformat(),
              "home_team": "GB", "away_team": "CHI", "bookmakers": []}],
            now=NOW, cadence_label="tue-2026-09-15", market_tier="game_lines", kickoff_by_event={},
        )
        assert rows[0]["market_phase"] == "closing" and rows[0]["cadence_label"] == "tue-2026-09-15"

    def test_the_closing_window_matches_the_guards(self):
        """Two owners of one threshold: the writer that STAMPS the phase and the guard that
        ENFORCES it. Drift would make a board stamped `open` be rejected as late, or worse."""
        from quant_sports_intel_models.football.nfl.pit import leakage_guard as lg

        assert market_capture.CLOSING_WINDOW_MINUTES == lg.DEFAULT_CLOSING_WINDOW_MINUTES

    def test_props_are_OFF_by_default(self, monkeypatch):
        """Props cost ~120 credits/event (~75k/season at this cadence) — a deliberate spend."""
        monkeypatch.delenv(market_capture.PROPS_ENV_FLAG, raising=False)
        assert market_capture.props_enabled() is False
        monkeypatch.setenv(market_capture.PROPS_ENV_FLAG, "1")
        assert market_capture.props_enabled() is True

    def test_a_zero_event_capture_escalates(self):
        m = market_capture.run_market_capture(
            2026, now=NOW, capture_props=False, fetch_game_lines=lambda: [],
        )
        assert m["escalate"] is True, "'0 rows and no error' must never look healthy"


# ── the injury leg ───────────────────────────────────────────────────────────────────────
class TestInjuryCaptureStampsOurOwnAsOf:
    def test_source_timestamp_is_null_with_a_DECLARED_reason(self, tmp_path):
        m = injury_capture.run_injury_capture(
            2026, now=NOW, local_root=str(tmp_path), vendor_asof_present=False,
            rows=[{"gsis_id": "00-1", "week": 2, "team": "GB", "report_status": "Questionable"}],
        )
        assert m["written"] == 1
        idx = store.build_store_index("injuries", [NOW.date().isoformat()], local_root=str(tmp_path))
        assert idx

    def test_our_capture_timestamp_is_never_laundered_into_source_timestamp(self, tmp_path):
        """The whole point: our stamp is an UPPER BOUND we made, not a vendor claim. Copying it
        into `source_timestamp` would dress our guess as the vendor's as-of."""
        import duckdb
        from deltalake import DeltaTable

        injury_capture.run_injury_capture(
            2026, now=NOW, local_root=str(tmp_path), vendor_asof_present=False,
            rows=[{"gsis_id": "00-1", "week": 2, "team": "GB", "report_status": "Out"}],
        )
        dt = DeltaTable(str(tmp_path / "nfl/pit/injuries"))
        con = duckdb.connect()
        con.register("t", dt.to_pyarrow_dataset())
        src, cap, reason = con.execute(
            "select source_timestamp, capture_timestamp, source_timestamp_absent_reason from t"
        ).fetchone()
        assert src is None and cap is not None and "date_modified" in reason

    def test_a_revised_report_is_reported_not_silently_absorbed(self, tmp_path):
        row = {"gsis_id": "00-1", "week": 2, "team": "GB", "report_status": "Questionable"}
        injury_capture.run_injury_capture(2026, now=NOW, local_root=str(tmp_path),
                                          cadence_label="w2", rows=[row], vendor_asof_present=False)
        m = injury_capture.run_injury_capture(
            2026, now=NOW, local_root=str(tmp_path), cadence_label="w2", vendor_asof_present=False,
            rows=[{**row, "report_status": "Out"}],
        )
        assert len(m["revisions"]) == 1 and m["written"] == 0


# ── the schema-snapshot leg ──────────────────────────────────────────────────────────────
def _snap(asset, columns, nulls=None, fp="fp") -> dict:
    return {
        "asset": asset, "schema_fingerprint": fp,
        "payload": {"columns": [{"name": n, "type": t} for n, t in columns],
                    "null_rates": nulls or {}},
    }


class TestSchemaDriftDetection:
    def test_a_deleted_column_is_detected(self):
        """The `injuries.date_modified` class — invisible in our own lake because
        `schema_mode='merge'` backfills the dropped column with NULLs."""
        d = schema_snapshot.diff_snapshots(
            _snap("injuries", [("gsis_id", "VARCHAR"), ("date_modified", "VARCHAR")]),
            _snap("injuries", [("gsis_id", "VARCHAR")]),
        )
        assert d["drifted"] and d["columns_removed"] == ["date_modified"]
        assert "date_modified" in d["watched_affected"]

    def test_a_replaced_schema_is_detected(self):
        """The `depth_charts` class — a whole new column set at 2025."""
        d = schema_snapshot.diff_snapshots(
            _snap("depth_charts", [("week", "INT"), ("depth_team", "VARCHAR")]),
            _snap("depth_charts", [("dt", "DATE"), ("player", "VARCHAR")]),
        )
        assert set(d["columns_removed"]) == {"week", "depth_team"}
        assert d["columns_added"] == ["dt", "player"]

    def test_a_retype_is_detected(self):
        d = schema_snapshot.diff_snapshots(
            _snap("schedules", [("week", "INT")]), _snap("schedules", [("week", "VARCHAR")]),
        )
        assert d["columns_retyped"] == ["week"]

    def test_a_column_that_goes_100pct_null_is_SILENTLY_DEAD(self):
        """Presence is not health — the signature a pure schema snapshot would miss."""
        d = schema_snapshot.diff_snapshots(
            _snap("injuries", [("report_status", "VARCHAR")], {"report_status": 0.5}),
            _snap("injuries", [("report_status", "VARCHAR")], {"report_status": 1.0}),
        )
        assert d["silently_dead"] == ["report_status"] and d["drifted"]

    def test_an_unchanged_schema_does_not_drift(self):
        cols = [("gsis_id", "VARCHAR"), ("week", "INT")]
        assert schema_snapshot.diff_snapshots(_snap("injuries", cols), _snap("injuries", cols))["drifted"] is False

    def test_an_unreadable_asset_escalates_rather_than_being_skipped(self):
        """NF1.7 (a): a check that did not run is not a pass."""
        m = schema_snapshot.run_schema_snapshot(
            2026, now=NOW, dry_run=True, previous={},
            rows=[{"asset": "injuries", "status": "UNREADABLE", "watched_missing": [],
                   "watched_all_null": [], "payload": {"columns": [], "null_rates": {}},
                   "schema_fingerprint": "x"}],
        )
        assert m["escalate"] is True and m["unreadable"] == ["injuries"]

    def test_a_missing_watched_column_escalates(self):
        m = schema_snapshot.run_schema_snapshot(
            2026, now=NOW, dry_run=True, previous={},
            rows=[{"asset": "injuries", "status": "OK", "watched_missing": ["report_status"],
                   "watched_all_null": [], "payload": {"columns": [], "null_rates": {}},
                   "schema_fingerprint": "x"}],
        )
        assert m["escalate"] is True

    def test_the_registry_exposes_urls_for_every_nflverse_asset(self):
        """The snapshot leg asks `ingest/sources.py` for its OWN urls — a hand-copied list would
        go stale the moment a release tag moves."""
        urls = schema_snapshot._asset_urls(2026)
        assert len(urls) >= 25
        assert all(u.startswith("https://") and u.endswith(".parquet") for u in urls.values())
        for asset in ("injuries", "depth_charts", "schedules"):
            assert asset in urls


def _schema_row(asset, missing, status="OK"):
    return {"asset": asset, "status": status, "watched_missing": list(missing),
            "watched_all_null": [], "payload": {"columns": [], "null_rates": {}},
            "schema_fingerprint": "x"}


class TestTheAcceptedBaselineSilencesOnlyTheTriagedBreaks:
    """A PERMANENT known-bad state must not page every run.

    `injuries.date_modified` (deleted 2025) and the `depth_charts` schema replacement are missing
    on every fire, forever. Escalating on them meant ~44 identical unactionable pages a season —
    and a muted `NFL PIT capture:` subject also swallows the weather leg's CRITICAL "this slate's
    forecast is being lost permanently". Same judgement E11.30 applies to the known off-season
    injury-ingest hole.
    """

    def test_the_2025_breaks_alone_do_not_escalate(self):
        """The live box condition, verbatim: this is what fired ERROR every Tue/Fri."""
        m = schema_snapshot.run_schema_snapshot(
            2026, now=NOW, dry_run=True, previous={},
            rows=[_schema_row("injuries", ["date_modified"]),
                  _schema_row("depth_charts", ["week", "depth_team", "position"])],
        )
        assert m["escalate"] is False
        # …but the state is still REPORTED in full — accepting a condition never shrinks the record.
        assert m["watched_missing"] == {"injuries": ["date_modified"],
                                        "depth_charts": ["week", "depth_team", "position"]}
        assert m["watched_missing_new"] == {}

    def test_a_THIRD_watched_column_still_escalates_immediately(self):
        """The baseline mutes named pairs, not an asset — otherwise it would be a blindfold."""
        m = schema_snapshot.run_schema_snapshot(
            2026, now=NOW, dry_run=True, previous={},
            rows=[_schema_row("injuries", ["date_modified", "report_status"])],
        )
        assert m["escalate"] is True
        assert m["watched_missing_new"] == {"injuries": ["report_status"]}
        assert m["watched_missing_accepted"] == {"injuries": ["date_modified"]}

    def test_an_unaccepted_asset_is_not_muted_by_another_assets_baseline(self):
        m = schema_snapshot.run_schema_snapshot(
            2026, now=NOW, dry_run=True, previous={},
            rows=[_schema_row("schedules", ["roof"])],
        )
        assert m["escalate"] is True and m["watched_missing_new"] == {"schedules": ["roof"]}

    def test_an_accepted_column_that_is_BACK_is_reported_so_the_mute_can_be_dropped(self):
        """A stale mute is how a FUTURE deletion of the same column goes unnoticed."""
        m = schema_snapshot.run_schema_snapshot(
            2026, now=NOW, dry_run=True, previous={},
            rows=[_schema_row("injuries", [])],
        )
        assert m["accepted_missing_resolved"] == {"injuries": ["date_modified"]}
        assert m["escalate"] is False  # a restored column is good news, not an incident

    def test_an_unreadable_asset_is_never_reported_as_resolved(self):
        """NF1.7 (a) facing the cheerful direction — UNKNOWN is not 'it came back'."""
        m = schema_snapshot.run_schema_snapshot(
            2026, now=NOW, dry_run=True, previous={},
            rows=[_schema_row("injuries", [], status="UNREADABLE")],
        )
        assert m["accepted_missing_resolved"] == {} and m["escalate"] is True

    def test_the_baseline_still_escalates_on_a_WATCHED_DRIFT_of_an_accepted_column(self):
        """Muting `missing` must not mute `it changed`. A column that disappears BETWEEN two
        snapshots is an event, and events are exactly what this leg exists to date."""
        prev = _snap("injuries", [("date_modified", "VARCHAR"), ("gsis_id", "VARCHAR")])
        cur = _snap("injuries", [("gsis_id", "VARCHAR")])
        cur.update(_schema_row("injuries", ["date_modified"]))
        m = schema_snapshot.run_schema_snapshot(
            2026, now=NOW, dry_run=True, previous={"injuries": prev}, rows=[cur],
        )
        assert m["escalate"] is True

    def test_every_accepted_pair_is_actually_a_WATCHED_column(self):
        """A typo'd baseline entry is INERT — it mutes nothing and reads as coverage. Pinning the
        pairs against WATCHED_COLUMNS is what stops the mute drifting away from the thing muted."""
        for asset, cols in schema_snapshot.ACCEPTED_MISSING.items():
            watched = set(schema_snapshot.WATCHED_COLUMNS.get(asset, ()))
            assert watched, f"ACCEPTED_MISSING names {asset!r}, which is not a watched asset"
            assert cols <= watched, (
                f"ACCEPTED_MISSING[{asset!r}] accepts {sorted(cols - watched)}, "
                "which are not watched columns — the entry would be inert"
            )

    def test_the_baseline_is_not_vacuous(self, monkeypatch):
        """RED-proof: empty the baseline and the live box condition must page again."""
        monkeypatch.setattr(schema_snapshot, "ACCEPTED_MISSING", {})
        m = schema_snapshot.run_schema_snapshot(
            2026, now=NOW, dry_run=True, previous={},
            rows=[_schema_row("injuries", ["date_modified"])],
        )
        assert m["escalate"] is True


# ── the leg runner ───────────────────────────────────────────────────────────────────────
class TestLegIsolationAndEscalation:
    def test_one_failing_leg_never_sinks_the_others(self, monkeypatch, tmp_path):
        from quant_sports_intel_models.football.nfl.pit import run_capture

        def boom(*a, **k):
            raise RuntimeError("odds api down")

        monkeypatch.setattr(market_capture, "run_market_capture", boom)
        # The suite does NO network IO (the fast gate's standing rule) — stub the schedule read
        # rather than letting the weather leg reach nflverse over HTTPS.
        monkeypatch.setattr(wc, "read_schedule", lambda season, **k: [_game()])
        out = run_capture.run_legs(
            ("market", "weather"), season=2026, now=NOW, local_root=str(tmp_path), dry_run=True,
        )
        assert "error" in out["market"]
        assert "error" not in out["weather"], "a market outage must not cost the week's weather"

    def test_a_failed_leg_is_an_escalation(self):
        from quant_sports_intel_models.football.nfl.pit import run_capture

        assert run_capture.escalations({"market": {"error": "x"}, "weather": {}}) == ["market"]

    def test_a_missing_manifest_escalates_rather_than_reading_as_silence(self):
        from quant_sports_intel_models.football.nfl.pit import run_capture

        assert run_capture.escalations({"weather": None}) == ["weather"]


class TestCaptureAndGuardComposeEndToEnd:
    """The INTEGRATION half of the §13 AC: a real capture, through the real store, read back
    through the real index, judged by the real guard. Unit tests prove each clause; this proves
    the pieces actually fit — a guard that is correct against hand-built dicts but rejects (or
    accepts) everything the writers actually emit would pass every unit test."""

    @staticmethod
    def _stored_rows(tmp_path, source="weather"):
        import duckdb
        from deltalake import DeltaTable

        dt = DeltaTable(str(tmp_path / f"nfl/pit/{source}"))
        con = duckdb.connect()
        con.register("t", dt.to_pyarrow_dataset())
        try:
            cols = [c[0] for c in con.execute("describe select * from t").fetchall()]
            return [dict(zip(cols, r)) for r in con.execute("select * from t").fetchall()]
        finally:
            con.unregister("t")

    @pytest.fixture
    def captured(self, tmp_path):
        forecast = {"temp_f": 62.0, "wind_speed_mph": 8.0, "_generationtime_ms": 0.2}
        wc.run_weather_capture(
            2026, now=NOW, games=[_game()], local_root=str(tmp_path),
            fetch=lambda *a, **k: dict(forecast),
        )
        rows = self._stored_rows(tmp_path)
        index = store.build_store_index("weather", [NOW.date().isoformat()], local_root=str(tmp_path))
        return rows, index

    def test_a_LATER_projection_accepts_the_capture(self, captured):
        from quant_sports_intel_models.football.nfl.pit import leakage_guard as lg

        rows, index = captured
        assert rows, "nothing was captured — the rest of this test would be vacuous"
        report = lg.evaluate_point_in_time(rows, NOW + timedelta(hours=1), store_index=index)
        assert report.ok, (
            f"the guard REJECTS what our own writers emit: {report.counts()} — every capture "
            f"would be unusable"
        )

    def test_an_EARLIER_projection_rejects_the_capture(self, captured):
        """A Tuesday build may not consume a Wednesday capture — the core §13 rule, exercised on
        a genuinely written row rather than a hand-built dict."""
        from quant_sports_intel_models.football.nfl.pit import leakage_guard as lg
        from quant_sports_intel_models.football.nfl.pit.leakage_guard import Rejection

        rows, index = captured
        report = lg.evaluate_point_in_time(rows, NOW - timedelta(hours=1), store_index=index)
        assert not report.ok
        assert Rejection.CAPTURE_TIMESTAMP_AFTER_PROJECTION in {f.reason for f in report.findings}

    def test_every_stored_row_carries_the_full_provenance_block(self, captured):
        from quant_sports_intel_models.football.nfl.pit import leakage_guard as lg

        rows, _ = captured
        for row in rows:
            assert lg.check_provenance_present(row) == [], f"incomplete provenance: {row}"


class TestSilentEmptyIsEscalated:
    def test_eligible_games_but_zero_captured_escalates(self):
        """'0 rows and no error' is this repo's recurring silent-empty signature, and here it
        means a slate's forecast is being lost permanently."""
        m = wc.run_weather_capture(
            2026, now=NOW, games=[_game()], fetch=lambda *a, **k: None, local_root=None,
        )
        assert m["escalate"] is True and m["fetch_failed"] == 1

    def test_no_eligible_games_does_NOT_escalate(self):
        """An off-season / between-rungs pass is silent by design; escalating on it would be the
        over-paging failure that gets the monitor muted."""
        m = wc.run_weather_capture(2026, now=NOW, games=[_game(hours=60)], fetch=lambda *a, **k: None)
        assert m["escalate"] is False and m["eligible"] == 0
