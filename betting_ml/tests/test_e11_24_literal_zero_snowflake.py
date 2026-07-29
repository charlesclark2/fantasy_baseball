"""E11.24 — LITERAL-ZERO SNOWFLAKE: guards for the stage-1 cutovers.

Each test pins a property that is INVISIBLE to the runtime gate but cheap to assert statically,
and that a future edit could plausibly break:

  1. compute_elo's SF-free branch really is Snowflake-free, and its parquet column contract
     stays UPPERCASE (a lowercase write reads ALL-NULL through the Snowflake external table
     while DuckDB stays green — the `VALUE:<key>` case-sensitivity landmine).
  2. Both S3 export-mirrors retire team_elo_history under the same lever (INC-31
     writer-uniqueness: exactly ONE writer per S3 key).
  3. ingest_weather's SF-free path reads from the lakehouse, stays lean-image-safe (no
     betting_ml import node), and never opens a Snowflake session when no leg needs one.
  4. The statcast catch-up gate is fail-OPEN and cannot disagree with the sensor that fires it.
  5. Cost/metering readers run on the monitoring warehouse, never the measured one.

Fast-gate safe: source inspection + `betting_ml` imports only, never `pipeline`
(pipeline/__init__ reads the dbt manifest, absent in CI).
"""
from __future__ import annotations

import ast
import os
from datetime import date
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def _src(rel: str) -> str:
    return (REPO / rel).read_text()


# ── 1. compute_elo ────────────────────────────────────────────────────────────────────────
class TestComputeEloIsSnowflakeFree:
    def test_the_lakehouse_column_contract_is_uppercase(self):
        """The existing parquet was written by a Snowflake `SELECT *` mirror, so its columns are
        UPPERCASE and the ext table addresses them as case-sensitive `VALUE:<KEY>`. A lowercase
        native write would read ALL-NULL through Snowflake while DuckDB (case-insensitive)
        stayed green — silent, and exactly the INC-31 / `VALUE:<key>` landmine."""
        from betting_ml.scripts.compute_elo import _LAKEHOUSE_COLUMNS

        names = [n for n, _ in _LAKEHOUSE_COLUMNS]
        assert names == ["GAME_PK", "GAME_DATE", "TEAM_ABBREV",
                         "ELO_BEFORE_GAME", "ELO_AFTER_GAME"], names
        assert all(n == n.upper() for n in names), (
            "team_elo_history parquet columns must stay UPPERCASE — the Snowflake external "
            "table reads VALUE:<KEY> case-sensitively."
        )

    def test_the_sf_free_reader_and_writer_never_import_snowflake(self):
        """`snowflake.connector` must only be reachable from the Snowflake branch. If it were a
        module-level import the SF-free path would still load (and on a lean host, still need)
        the connector — and a stray `_connect()` would still wake the warehouse."""
        src = _src("betting_ml/scripts/compute_elo.py")
        tree = ast.parse(src)
        module_level_imports = {
            alias.name.split(".")[0]
            for node in tree.body
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in getattr(node, "names", [])
        }
        assert "snowflake" not in module_level_imports, (
            "snowflake.connector must be imported lazily INSIDE the Snowflake branch so the "
            "E11_24_ELO_SF_FREE path is genuinely Snowflake-free."
        )
        # Inspect IMPORT and CALL nodes only — the docstrings legitimately say "Snowflake".
        for fn in ("load_games_from_lakehouse", "write_to_lakehouse"):
            node = next(n for n in ast.walk(tree)
                        if isinstance(n, ast.FunctionDef) and n.name == fn)
            for sub in ast.walk(node):
                if isinstance(sub, (ast.Import, ast.ImportFrom)):
                    mods = [a.name for a in getattr(sub, "names", [])]
                    mods.append(getattr(sub, "module", "") or "")
                    assert not any("snowflake" in m.lower() for m in mods), \
                        f"{fn} imports Snowflake: {mods}"
                if isinstance(sub, ast.Call):
                    called = ast.unparse(sub.func).lower()
                    assert "snowflake" not in called and "_connect" not in called, \
                        f"{fn} calls {called}"

    def test_the_writer_refuses_a_short_write(self):
        """A partial publish silently degrades every downstream elo feature, so the row count is
        asserted before the COPY rather than trusted."""
        src = _src("betting_ml/scripts/compute_elo.py")
        body = src[src.find("def write_to_lakehouse"):src.find("def _write_to_snowflake")]
        assert "refusing to publish a" in body and "raise RuntimeError" in body

    def test_the_lever_name_matches_what_the_env_declares(self):
        from betting_ml.scripts.compute_elo import _SF_FREE_ENV

        assert _SF_FREE_ENV == "E11_24_ELO_SF_FREE"

    def test_sf_free_defaults_off(self, monkeypatch):
        from betting_ml.scripts import compute_elo

        monkeypatch.delenv("E11_24_ELO_SF_FREE", raising=False)
        assert compute_elo.sf_free() is False
        monkeypatch.setenv("E11_24_ELO_SF_FREE", "1")
        assert compute_elo.sf_free() is True

    def test_the_elo_kernel_is_shared_by_both_branches(self):
        """Both branches feed the SAME `compute_elo()` with UPPERCASE keys. If the lakehouse
        reader returned lowercase keys the kernel would KeyError — cheap proof they cannot
        drift into two different Elo implementations."""
        from betting_ml.scripts.compute_elo import compute_elo as kernel

        rows = kernel([
            {"GAME_YEAR": 2026, "GAME_PK": 1, "GAME_DATE": date(2026, 4, 1),
             "HOME_TEAM": "AAA", "AWAY_TEAM": "BBB", "HOME_TEAM_WON": True},
        ])
        assert len(rows) == 2
        assert rows[0][3] == 1500.0 and rows[0][4] > 1500.0  # home won → home elo rises
        assert rows[1][4] < 1500.0

    def test_the_lakehouse_read_routes_through_the_registrar(self):
        """A hardcoded `read_parquet('<lakehouse>/<table>/…')` glob is what broke the daily job
        on 2026-07-20 when phase-1.5 deleted the legacy layout (grep the PATH, not the name)."""
        src = _src("betting_ml/scripts/compute_elo.py")
        assert "register_lakehouse_views" in src
        body = src[src.find("def load_games_from_lakehouse"):src.find("def write_to_lakehouse")]
        assert "read_parquet(" not in body, (
            "route the lakehouse read through register_lakehouse_views, not a hardcoded glob"
        )


# ── 2. INC-31 writer-uniqueness ───────────────────────────────────────────────────────────
class TestExactlyOneWriterPerS3Key:
    """Both mirrors wrote `baseball/lakehouse/team_elo_history/data.parquet` with a
    `SELECT * FROM <snowflake table>`. Once compute_elo owns that key natively, a surviving
    mirror does not merely duplicate work — it publishes a FROZEN Snowflake snapshot over fresh
    Elo on every daily run. INC-31 is the same shape (there it flipped column case)."""

    MIRRORS = ("scripts/export_w8a_precursors_to_s3.py", "scripts/export_features_to_s3.py")

    @pytest.mark.parametrize("mirror", MIRRORS)
    def test_the_mirror_declares_the_retirement(self, mirror):
        src = _src(mirror)
        assert "CUTOVER_RETIRED" in src and "E11_24_ELO_SF_FREE" in src, (
            f"{mirror} still mirrors team_elo_history unconditionally — under the E11.24 lever "
            f"that clobbers the natively-written key with a frozen Snowflake snapshot."
        )
        assert "def retired_by_cutover" in src

    @pytest.mark.parametrize("mirror", MIRRORS)
    def test_the_skip_is_loud_and_an_explicit_request_is_a_hard_error(self, mirror):
        """A silent skip is a tier violation (ALERT-loud-but-continue), and a stale runbook
        running `--table team_elo_history` must FAIL rather than clobber the key."""
        src = _src(mirror)
        assert "WARNING: skipping" in src
        assert "REFUSING to mirror" in src and "sys.exit(2)" in src

    @pytest.mark.parametrize("mirror", MIRRORS)
    def test_retired_by_cutover_is_env_driven_and_defaults_off(self, mirror, monkeypatch):
        import importlib.util

        spec = importlib.util.spec_from_file_location(f"m_{Path(mirror).stem}", REPO / mirror)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        monkeypatch.delenv("E11_24_ELO_SF_FREE", raising=False)
        assert mod.retired_by_cutover("team_elo_history") is None
        monkeypatch.setenv("E11_24_ELO_SF_FREE", "1")
        assert "E11_24_ELO_SF_FREE=1" in mod.retired_by_cutover("team_elo_history")
        assert mod.retired_by_cutover("some_other_table") is None


# ── 3. ingest_weather ─────────────────────────────────────────────────────────────────────
class TestWeatherCaptureGoesSnowflakeFree:
    def test_no_slate_read_bypasses_the_branching_helper(self):
        """Every slate read must go through `_slate_games`; a leftover raw
        `cur.execute(_SCHEDULE_SQL)` would keep waking the warehouse under the lever."""
        src = _src("scripts/ingest_weather.py")
        # The ONLY legal Snowflake slate read is the else-branch inside `_slate_games` itself.
        helper = src[src.find("def _slate_games(conn"):]
        helper = helper[:helper.find("\n\n\n")]
        outside = src.replace(helper, "")
        assert "cur.execute(_SCHEDULE_SQL" not in outside
        assert "cur.execute(_COMPLETED_GAMES_SQL" not in outside
        assert "_SCHEDULE_SQL" in helper and "_COMPLETED_GAMES_SQL" in helper
        assert src.count("_slate_games(conn") >= 5  # the def + 4 call sites

    def test_the_lean_image_rule_holds(self):
        """services/weather_capture/ has NO betting_ml — an import node here ImportErrors on
        every cron fire and the capture silently stalls (the INC-29 lean-image class)."""
        src = _src("scripts/ingest_weather.py")
        assert "betting_ml" not in src.replace("# ", "").split("_SF_FREE_ENV")[0] or True
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [a.name for a in getattr(node, "names", [])]
                mod = getattr(node, "module", "") or ""
                assert not mod.startswith("betting_ml"), f"betting_ml import in lean script: {mod}"
                assert not any(n.startswith("betting_ml") for n in names)

    def test_the_image_ships_duckdb_and_the_ref_venues_seed(self):
        """`ref_venues` is a dbt SEED with no parquet — the SF-free join needs the CSV in the
        image, and the DuckDB read needs duckdb installed. Either omission = a cron that
        crashes on every fire once the lever is flipped."""
        dockerfile = _src("services/weather_capture/Dockerfile")
        assert "duckdb" in dockerfile
        assert "dbt/seeds/ref_venues.csv" in dockerfile

    def test_no_snowflake_session_is_opened_when_no_leg_needs_one(self):
        """Reads-only-to-S3 while the INSERT leg still points at Snowflake saves NOTHING — the
        connection itself is the wake. This pins the `do_sf or not sf_free` conjunction."""
        src = _src("scripts/ingest_weather.py")
        assert "needs_snowflake = do_sf or not weather_sf_free()" in src
        assert "conn = get_snowflake_conn() if needs_snowflake else None" in src

    def test_the_timestamp_is_cast_at_the_use_site(self):
        """INC-23: `stg_statsapi_games.game_date` is an ISO VARCHAR in the lakehouse. The
        Snowflake query returned a naive UTC datetime and callers branch on `isinstance(str)`,
        so the cast must happen in SQL rather than leaking a string to four call sites."""
        src = _src("scripts/ingest_weather.py")
        assert "::timestamptz AT TIME ZONE 'UTC'" in src

    def test_the_s3_dedup_read_is_preserved(self):
        """Dropping the dedup would re-fetch every completed park on all ~17 hourly fires —
        trading a Snowflake wake for a 17x weather-API bill."""
        src = _src("scripts/ingest_weather.py")
        assert "_already_fetched_lakehouse" in src
        body = src[src.find("def _already_fetched_lakehouse"):src.find("def _slate_games(")]
        assert "weather_observation_type" in body and "hours_to_first_pitch" in body

    def test_sf_free_defaults_off(self, monkeypatch):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "iw_probe", REPO / "scripts" / "ingest_weather.py")
        # exec_module would import requests/snowflake; assert on source semantics instead.
        assert spec is not None
        src = _src("scripts/ingest_weather.py")
        body = src[src.find("def weather_sf_free"):]
        assert 'os.environ.get(_SF_FREE_ENV, "0")' in body


# ── 4. the statcast catch-up gate ─────────────────────────────────────────────────────────
class TestStatcastCatchupGate:
    def test_defaults_off(self, monkeypatch):
        from betting_ml.monitoring import statcast_catchup_gate as g

        monkeypatch.delenv(g.CATCHUP_GATE_ENV, raising=False)
        assert g.catchup_gate_on() is False
        monkeypatch.setenv(g.CATCHUP_GATE_ENV, "1")
        assert g.catchup_gate_on() is True

    def test_it_fails_open_on_a_lakehouse_error(self):
        """A transient S3 blip must NOT suppress the catch-up — that converts a hiccup into a
        skipped self-heal, the 'silently never runs' outage class. Any failure ⇒ run the chain."""
        from betting_ml.monitoring.statcast_catchup_gate import catchup_landed_pitches

        def boom():
            raise RuntimeError("s3 down")

        assert catchup_landed_pitches(date(2026, 7, 28), conn_factory=boom) is True

        class BadConn:
            def execute(self, *a, **k):
                raise RuntimeError("binder error")

            def close(self):
                pass

        assert catchup_landed_pitches(date(2026, 7, 28), conn_factory=BadConn) is True

    def test_it_reports_absence_and_presence_correctly(self):
        from betting_ml.monitoring.statcast_catchup_gate import catchup_landed_pitches

        class Conn:
            def __init__(self, n):
                self.n = n
                self.sql = None

            def execute(self, sql, params):
                self.sql = sql
                self.params = params
                return self

            def fetchone(self):
                return (self.n,)

            def close(self):
                pass

        assert catchup_landed_pitches(date(2026, 7, 28), conn_factory=lambda: Conn(0)) is False
        assert catchup_landed_pitches(date(2026, 7, 28), conn_factory=lambda: Conn(4123)) is True

    def test_it_reads_the_same_partition_predicate_as_the_sensor(self):
        """If the gate and `statcast_freshness_sensor._pitches_present` could disagree, the
        sensor would re-request work the gate just skipped — an infinite no-op loop."""
        gate = _src("betting_ml/monitoring/statcast_catchup_gate.py")
        sensor = _src("pipeline/sensors/statcast_freshness_sensor.py")
        for token in ("lh_year('stg_batter_pitches'", "WHERE game_date = ?", "is_missing_glob"):
            assert token in gate, token
            assert token in sensor, token

    def test_the_op_uses_a_conditional_output_and_logs_loudly(self):
        """`Out(Nothing, is_required=False)` + no yield is what makes Dagster SKIP (not FAIL) the
        downstream chain. A plain `return` on a required Out would fail the whole run."""
        src = _src("pipeline/ops/sensor_ops.py")
        head = src[src.find("def catchup_ingest_statcast") - 200:src.find("def catchup_refresh_ext_tables")]
        assert "Out(Nothing, is_required=False)" in head
        assert "yield Output(None)" in head
        assert "context.log.warning" in head, "a silent skip is a failure-tier violation"

    def test_the_ingest_still_runs_before_the_gate(self):
        """The gate must never skip the INGEST itself — that is the sensor's whole purpose and
        the only thing that can make the next fire land data."""
        src = _src("pipeline/ops/sensor_ops.py")
        body = src[src.find("def catchup_ingest_statcast"):src.find("def catchup_refresh_ext_tables")]
        assert body.index("ingest_statcast_to_s3.py") < body.index("catchup_gate_on()")


# ── 5. the self-inflicted metering wake ───────────────────────────────────────────────────
class TestCostQueriesDoNotWakeTheWarehouseTheyMeasure:
    def test_data_loader_exposes_a_monitoring_connection(self):
        from betting_ml.utils.data_loader import (
            DEFAULT_MONITOR_WAREHOUSE,
            MONITOR_WAREHOUSE_ENV,
            get_monitoring_connection,
        )

        assert MONITOR_WAREHOUSE_ENV == "SNOWFLAKE_MONITOR_WAREHOUSE"
        assert DEFAULT_MONITOR_WAREHOUSE == "MONITOR_WH"
        assert callable(get_monitoring_connection)

    def test_the_monitoring_connection_overrides_the_warehouse(self, monkeypatch):
        import betting_ml.utils.data_loader as dl

        captured = {}
        monkeypatch.setattr(dl, "_load_private_key", lambda: b"key")
        monkeypatch.setattr(
            dl.snowflake.connector, "connect", lambda **kw: captured.update(kw) or object()
        )
        monkeypatch.setenv("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH")
        monkeypatch.delenv("SNOWFLAKE_MONITOR_WAREHOUSE", raising=False)

        dl.get_monitoring_connection()
        assert captured["warehouse"] == "MONITOR_WH", (
            "an account_usage read on COMPUTE_WH RESUMES the warehouse it is measuring — that "
            "was a measured top-3 waker and it contaminated the 7/29 census's own UTC day."
        )

        captured.clear()
        dl.get_snowflake_connection()
        assert captured["warehouse"] == "COMPUTE_WH", "normal reads must be unaffected"

    @pytest.mark.parametrize("script", [
        "scripts/report_sf_cost_flips_after.py",
        "scripts/ops/snowflake_cost_by_job.py",
    ])
    def test_every_metering_reader_is_routed_off_the_compute_warehouse(self, script):
        src = _src(script)
        assert "MONITOR" in src.upper(), (
            f"{script} reads snowflake.account_usage — it must connect on the monitoring "
            f"warehouse, else the measurement perturbs the measurement."
        )
        assert "get_snowflake_connection()" not in src


# ── 6. the levers are declared where an operator will look ────────────────────────────────
def test_the_e11_24_levers_are_declared_in_env_example():
    """The W6_ODDS_SF_FREE bite: an absent key makes `sed -i 's/^# *KEY=.*/KEY=1/'` a silent
    no-op and the deploy still succeeds. (Also covered by ROLLOUT_LEVERS in
    test_cost_wake_gates.py — pinned here too so this file stands alone.)"""
    env_example = _src("services/dagster/aws/.env.example")
    for key in ("E11_24_ELO_SF_FREE=0", "E11_24_WEATHER_SF_FREE=0",
                "E11_24_STATCAST_CATCHUP_GATE=0", "SNOWFLAKE_MONITOR_WAREHOUSE="):
        assert key in env_example, f"{key} must be a real KEY=<value> line in .env.example"


def test_the_weather_lever_names_the_RIGHT_write_leg_variable():
    """Flipping the read without also flipping the WRITE leg leaves the INSERT waking the
    warehouse — zero measurable saving.

    🚨 And the write leg is `W11_RAW_WRITE_MODE`, NOT `LAKEHOUSE_RAW_WRITE_MODE`:
    `ingest_weather.py` calls `w11_write_mode()`, whose env is `W11_WRITE_MODE_ENV =
    "W11_RAW_WRITE_MODE"` (the W11 Tier-A wave has its own switch, deliberately independent of
    the odds one). A handoff that names the odds variable produces a SILENT NO-OP flip — the
    W6_ODDS_SF_FREE class of bite, caught in review 2026-07-29. This test pins the correct name
    so the docs can never drift back."""
    from pathlib import Path as _P

    writer = (REPO / "scripts" / "utils" / "lakehouse_raw_writer.py").read_text()
    assert 'W11_WRITE_MODE_ENV = "W11_RAW_WRITE_MODE"' in writer, (
        "the weather write-leg env var was renamed — update .env.example and the E11.24 doc"
    )
    weather = _src("scripts/ingest_weather.py")
    assert "w11_write_mode()" in weather

    env_example = _src("services/dagster/aws/.env.example")
    block = env_example[env_example.find("E11_24_WEATHER_SF_FREE") - 900:]
    block = block[:2200]
    assert "W11_RAW_WRITE_MODE" in block, (
        ".env.example must name W11_RAW_WRITE_MODE beside the weather lever"
    )
    assert "NOT" in block and "LAKEHOUSE_RAW_WRITE_MODE" in block, (
        "keep the explicit 'NOT LAKEHOUSE_RAW_WRITE_MODE' warning — that wrong name was handed "
        "to the operator once already"
    )
    assert _P(str(REPO / "services" / "dagster" / "aws" / ".env.example")).exists()
