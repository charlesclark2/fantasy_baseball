"""FU-3 / E11.24-6a-PRE — the PER-GAME, content-aware `--skip-if-exists` guard.

TWO defects are pinned here, and the second is the one that makes this change safe rather
than merely cheaper:

1. **The guard never ran in production.** It was gated
   ``if args.skip_if_exists and not args.dry_run and do_sf`` — SF-leg-only — while the box
   runs ``W11_RAW_WRITE_MODE=s3`` ⇒ ``do_sf=False``. Every intraday tick therefore re-fetched
   the Stats API and re-wrote the whole slate, re-stamping ``loaded_at`` on unchanged rows
   (measured: median 8 distinct same-day instants per slate, range 6-20).

2. **It was an ANY-ROW check.** ``COUNT(*) > 0`` for the date would have skipped the ENTIRE
   remaining slate the moment the FIRST game's umpire landed. MLB announces HP umpires in
   WAVES (measured 2026-07-31: 1→5→7→9→10→11→13→15 games over seven hours), so simply
   un-gating defect 1 would have shipped a swallow of every later-announced assignment.

   ⇒ ``test_a_later_announced_assignment_is_still_ingested`` is the load-bearing test in this
   file. If only one test here survives, it must be that one: fixing (1) without (2) trades a
   wasteful no-op for silent DATA LOSS on the serving path.

The guard FAILS OPEN everywhere (unreadable mirror / no duckdb / Snowflake-only write mode ⇒
write everything). A check that could not run is never scored as a pass (NF1.7 (a)) — this
feature block has an incident history (INC-31, F2) of silently zeroing.

⭐ One test drives the REAL DuckDB read over a REAL parquet file (only the S3 location is
redirected), not a mocked cursor: the guard's correctness lives in a QUALIFY/try_cast SQL
string, and a test that stubs the query away would stay green while the SQL rotted (the INC-39
"both ends covered, unexercised middle" gap).
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_REPO = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO / "scripts" / "ingest_umpires.py"


@pytest.fixture(scope="module")
def iu():
    """Load scripts/ingest_umpires.py by path (it is a script, not a package module)."""
    if str(_REPO / "scripts") not in sys.path:
        sys.path.insert(0, str(_REPO / "scripts"))
    spec = importlib.util.spec_from_file_location("ingest_umpires_fu3", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _a(game_pk: int, uid: str, name: str) -> dict:
    return {"game_pk": game_pk, "game_date": "2026-07-31", "season": 2026,
            "umpire_name": name, "umpire_id": uid}


# ── the load-bearing defect: a wave-announced slate must not be swallowed ──────────────────

class TestLateAnnouncedAssignmentSurvives:

    def test_a_later_announced_assignment_is_still_ingested(self, iu):
        """THE any-row defect. Game 2's umpire is announced AFTER game 1 was written.

        Under the old `COUNT(*) > 0` form the whole date was already "present", so game 2
        would never have been ingested. Per-game, it must be written on the next tick.
        """
        existing = {101: ("111", "Ump One")}                      # tick 1 wrote game 101 only
        fetched = [_a(101, "111", "Ump One"), _a(102, "222", "Ump Two")]   # tick 2: 102 posted

        new = iu.filter_new_assignments(fetched, existing)

        assert [r["game_pk"] for r in new] == [102], (
            "a later-announced assignment was SWALLOWED — this is the any-row defect and it "
            "is silent data loss on the served umpire block, not an optimisation miss"
        )

    def test_a_full_wave_sequence_writes_every_game_exactly_once(self, iu):
        """Replays the measured 2026-07-31 shape: each tick brings a few new games and the
        accumulated state must end up holding every one, with no game written twice."""
        waves = [[101], [101, 102, 103], [101, 102, 103, 104], [101, 102, 103, 104, 105]]
        acc: dict[int, tuple] = {}
        writes: list[list[int]] = []
        for wave in waves:
            fetched = [_a(g, str(g), f"Ump {g}") for g in wave]
            new = iu.filter_new_assignments(fetched, acc)
            if new:
                writes.append([r["game_pk"] for r in new])
                acc.update({r["game_pk"]: iu._key(r) for r in new})

        assert writes == [[101], [102, 103], [104], [105]]
        assert sorted(acc) == [101, 102, 103, 104, 105], "a game was never ingested"

    def test_a_repeat_tick_on_an_unchanged_slate_writes_nothing(self, iu):
        """The saving itself: an unchanged slate must produce NO write, so `loaded_at` is not
        re-stamped and the E11.24-6a watermark does not bump."""
        existing = {101: ("111", "Ump One"), 102: ("222", "Ump Two")}
        fetched = [_a(101, "111", "Ump One"), _a(102, "222", "Ump Two")]

        assert iu.filter_new_assignments(fetched, existing) == []

    def test_a_reassigned_umpire_is_re_written(self, iu):
        """Content-awareness, not mere existence: a mid-slate umpire CHANGE must be ingested.

        An existence-only per-game check would fix the swallow above and still silently pin a
        stale umpire for the rest of the slate — the daily early/late ops run in the MORNING,
        hours before assignments post, so nothing else would correct it in time.
        """
        existing = {101: ("111", "Ump One")}
        fetched = [_a(101, "999", "Ump Nine")]

        assert [r["game_pk"] for r in iu.filter_new_assignments(fetched, existing)] == [101]


# ── fail-open ─────────────────────────────────────────────────────────────────────────────

class TestFailsOpen:

    def test_an_unevaluable_guard_writes_everything(self, iu):
        """`existing is None` = "could not establish" ⇒ write everything, never skip."""
        fetched = [_a(101, "111", "A"), _a(102, "222", "B")]
        assert iu.filter_new_assignments(fetched, None) == fetched

    def test_a_read_failure_returns_none_rather_than_an_empty_skip_set(self, iu, monkeypatch):
        """A transient S3/DuckDB error must NOT masquerade as "nothing recorded yet" — the two
        are indistinguishable downstream only if the error path returns {}."""
        import betting_ml.utils.lakehouse_monitor as lm

        monkeypatch.setattr(lm, "duck", MagicMock(side_effect=RuntimeError("s3 exploded")))
        assert iu.existing_statsapi_assignments("2026-07-31") is None

    def test_a_missing_glob_is_no_data_not_an_error(self, iu, monkeypatch):
        """An absent mirror partition is a legitimate "nothing recorded", so the guard may
        return an empty set — the first write of the season then proceeds normally."""
        import betting_ml.utils.lakehouse_monitor as lm

        conn = MagicMock()
        conn.execute.side_effect = RuntimeError("No files found that match the pattern")
        monkeypatch.setattr(lm, "duck", MagicMock(return_value=conn))
        assert iu.existing_statsapi_assignments("2026-07-31") == {}


# ── id normalisation (the nullable-int → DOUBLE poisoning class) ──────────────────────────

class TestIdNormalisation:

    @pytest.mark.parametrize("stored", ["664983", 664983, 664983.0, "664983.0", " 664983 "])
    def test_equivalent_id_spellings_compare_equal(self, iu, stored):
        """The mirror unions four writers plus the SF bridge, so the same id arrives as a str,
        an int or a poisoned float ('664983.0'). All must collapse to one value, or an
        unchanged slate would be re-written every tick and the fix would be a no-op."""
        assert iu._norm(stored) == "664983"

    @pytest.mark.parametrize("blank", [None, "", "   "])
    def test_absent_ids_collapse_to_none(self, iu, blank):
        assert iu._norm(blank) is None

    def test_a_missing_id_never_matches_a_present_one(self, iu):
        existing = {101: (None, "Ump One")}
        assert iu.filter_new_assignments([_a(101, "111", "Ump One")], existing) != []


# ── the REAL DuckDB leg over a REAL parquet (no mocked cursor) ────────────────────────────

class TestTheActualLakehouseRead:
    """Drives `existing_statsapi_assignments` through real DuckDB against a real parquet
    laid out exactly like the append-only S3 mirror. Only `lh_raw()` is redirected."""

    @pytest.fixture(autouse=True)
    def _hermetic_aws_env(self, monkeypatch):
        """Dummy AWS creds so `duck()`'s `CREATE SECRET (PROVIDER credential_chain)` resolves.

        The read under test is a LOCAL parquet, so no real credential is ever used — but
        `duck()` builds the S3 secret unconditionally and DuckDB VALIDATES the chain at
        create time, raising `Secret Validation Failure ... Credential Chain: 'config'`
        when it resolves to nothing. `existing_statsapi_assignments` then correctly fails
        OPEN and returns None, so both tests below fail on any credential-less runner.

        This passed on a laptop for the accidental reason that `ingest_umpires.py` calls
        `load_dotenv(.env)` at import and the repo `.env` carries `AWS_ACCESS_KEY_ID` —
        i.e. the test was reading the developer's real credentials. CI has no `.env`,
        so it went red there and only there (the "green locally, red on a clean runner"
        environment-dependence class). Pinning dummy values makes the test hermetic in
        BOTH places and keeps the assertion about the SQL, not about the runner.
        """
        for var in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
            monkeypatch.setenv(var, "testing")

    @staticmethod
    def _write_mirror(tmp_path: Path) -> str:
        pa = pytest.importorskip("pyarrow")
        import pyarrow.parquet as pq

        # Append-only history: game 101 written twice (the later row must win), game 102
        # written once, plus an umpscorecards tendency row and a different date that must
        # both be excluded. loaded_at/game_date are ISO VARCHAR (the live-writer shape).
        rows = {
            "game_pk":     [101, 101, 102, 103, 104],
            "game_date":   ["2026-07-31", "2026-07-31", "2026-07-31", "2026-07-31", "2026-07-30"],
            "umpire_id":   ["111", "999", "222", "333", "444"],
            "umpire_name": ["Old Ump", "New Ump", "Ump Two", "Scorecard Ump", "Yesterday"],
            "data_source": ["statsapi", "statsapi", "statsapi", "umpscorecards", "statsapi"],
            "loaded_at":   ["2026-07-31T16:00:00+00:00", "2026-07-31T19:00:00+00:00",
                            "2026-07-31T19:00:00+00:00", "2026-07-31T20:00:00+00:00",
                            "2026-07-30T19:00:00+00:00"],
        }
        out = tmp_path / "umpire_game_log" / "dt=2026-07-31"
        out.mkdir(parents=True)
        pq.write_table(pa.table(rows), out / "part-0.parquet")
        return str(tmp_path / "umpire_game_log" / "**" / "*.parquet")

    def test_it_takes_the_latest_row_per_game_and_scopes_to_statsapi(self, iu, tmp_path,
                                                                    monkeypatch):
        pytest.importorskip("duckdb")
        import betting_ml.utils.lakehouse_monitor as lm

        glob = self._write_mirror(tmp_path)
        monkeypatch.setattr(lm, "lh_raw", lambda _table: glob)

        got = iu.existing_statsapi_assignments("2026-07-31")

        assert got == {101: ("999", "New Ump"), 102: ("222", "Ump Two")}, (
            "expected latest-loaded_at-per-game, data_source='statsapi', this date only"
        )
        # 103 is umpscorecards (a tendency row, not an assignment) — it must NOT mask a
        # missing assignment; 104 belongs to another slate.
        assert 103 not in got and 104 not in got

    def test_the_filter_composes_with_the_real_read(self, iu, tmp_path, monkeypatch):
        """End-to-end over the real SQL: the reassigned game 101 is settled, 102 unchanged,
        and a newly-announced 105 is written."""
        pytest.importorskip("duckdb")
        import betting_ml.utils.lakehouse_monitor as lm

        monkeypatch.setattr(lm, "lh_raw", lambda _t: self._write_mirror(tmp_path))
        existing = iu.existing_statsapi_assignments("2026-07-31")

        fetched = [_a(101, "999", "New Ump"), _a(102, "222", "Ump Two"), _a(105, "555", "Five")]
        assert [r["game_pk"] for r in iu.filter_new_assignments(fetched, existing)] == [105]


# ── main(): the S3 leg, and no Snowflake in the guard path ────────────────────────────────

def _run_main(iu, *, mode: str, existing, fetched):
    """Drive main() with --skip-if-exists under a given W11_RAW_WRITE_MODE, capturing the
    rows the S3 mirror leg would write. Returns (written_rows, sf_conn_calls)."""
    written: list[list[dict]] = []
    sf_calls: list[int] = []
    args = argparse.Namespace(date="2026-07-31", dry_run=False, skip_if_exists=True)

    with patch.object(iu, "w11_write_mode", return_value=mode), \
         patch.object(iu, "fetch_hp_umpires", return_value=fetched), \
         patch.object(iu, "existing_statsapi_assignments", return_value=existing), \
         patch.object(iu, "get_snowflake_conn", side_effect=lambda: sf_calls.append(1)), \
         patch.object(iu, "write_raw_rows_s3", side_effect=lambda _s, rows, **kw:
                      (written.append(rows), len(rows))[1]), \
         patch.object(iu.argparse.ArgumentParser, "parse_args", return_value=args):
        iu.main()

    return (written[0] if written else []), sf_calls


class TestMainOnTheS3Leg:

    def test_the_guard_runs_under_s3_mode_and_writes_only_the_new_game(self, iu):
        """The headline fix: under W11_RAW_WRITE_MODE=s3 (what the box runs) the guard is
        ACTIVE and only the newly-announced game reaches the mirror."""
        rows, _ = _run_main(
            iu, mode="s3",
            existing={101: ("111", "Ump One")},
            fetched=[_a(101, "111", "Ump One"), _a(102, "222", "Ump Two")],
        )
        assert [r["game_pk"] for r in rows] == [102]

    def test_an_unchanged_slate_writes_nothing_at_all_under_s3_mode(self, iu):
        """No write ⇒ no `loaded_at` re-stamp ⇒ no E11.24-6a watermark bump. This is the
        entire measurable saving."""
        rows, _ = _run_main(
            iu, mode="s3",
            existing={101: ("111", "Ump One")},
            fetched=[_a(101, "111", "Ump One")],
        )
        assert rows == []

    def test_the_guard_path_never_connects_to_snowflake(self, iu):
        """The per-tick Snowflake CONNECT that existed purely to decide whether to skip is
        gone. Under s3 mode nothing in main() may touch Snowflake at all."""
        _, sf_calls = _run_main(
            iu, mode="s3",
            existing={101: ("111", "Ump One")},
            fetched=[_a(101, "111", "Ump One"), _a(102, "222", "Ump Two")],
        )
        assert sf_calls == [], "main() connected to Snowflake on the S3 write path"

    def test_snowflake_only_mode_fails_open_rather_than_silently_skipping(self, iu):
        """No S3 mirror exists to compare against under `snowflake` mode, so the guard is
        inert — and must write EVERYTHING. Silently skipping there would re-introduce the
        exact landmine this change removes, facing the other way."""
        written: list[dict] = []
        args = argparse.Namespace(date="2026-07-31", dry_run=False, skip_if_exists=True)
        fetched = [_a(101, "111", "Ump One"), _a(102, "222", "Ump Two")]

        with patch.object(iu, "w11_write_mode", return_value="snowflake"), \
             patch.object(iu, "fetch_hp_umpires", return_value=fetched), \
             patch.object(iu, "existing_statsapi_assignments") as read, \
             patch.object(iu, "get_snowflake_conn", return_value=MagicMock()), \
             patch.object(iu, "insert_rows",
                          # ⚠️ RETURNS THE COUNT, not `list.extend()`'s None. `main()` logs it
                          # through `log.info("Inserted %d ...", loaded)`, which raises
                          # TypeError on None — but ONLY when the record is actually
                          # FORMATTED, i.e. only when the root logger happens to sit at INFO.
                          # That made this an ORDER-DEPENDENT failure: it passed alone and in
                          # most shard layouts, and surfaced under `-n 4` once an unrelated
                          # story added tests and shifted xdist's distribution.
                          side_effect=lambda _c, rows: (written.extend(rows), len(rows))[1]), \
             patch.object(iu.argparse.ArgumentParser, "parse_args", return_value=args):
            iu.main()

        assert not read.called, "there is no S3 mirror to read under snowflake-only mode"
        assert [r["game_pk"] for r in written] == [101, 102]


# ── source guards: the conjunct that disabled the whole thing must not come back ──────────

def _code_only(path: Path) -> str:
    """The script's EXECUTABLE source, with every docstring and `#` comment blanked out.

    ⚠️ A source-inspection guard that PROSE can satisfy is vacuous (INC-38). Both invariants
    below are described at length in this module's docstring and in the script's own comments,
    so a naive substring test over the raw file passes with the real code deleted. Docstrings
    are located via the AST (not a regex) and their line ranges blanked.
    """
    import ast

    lines = path.read_text().splitlines()
    tree = ast.parse("\n".join(lines))
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) \
                and isinstance(first.value.value, str):
            for i in range(first.lineno - 1, first.end_lineno):
                lines[i] = ""
    return "\n".join(line.split("#", 1)[0] for line in lines)


class TestSourceInvariants:

    def test_the_do_sf_conjunct_is_gone(self):
        """`and do_sf` on the skip guard is what silently disabled it for the entire S3 era.

        Asserted over EXECUTABLE source only, and on the co-occurrence (a `do_sf` reference on
        the same statement as `skip_if_exists`) rather than a fixed spelling, so reordering the
        conjuncts cannot slip past it.
        """
        code = _code_only(_SCRIPT)
        assert "do_sf" in code, "sanity: the write-leg flag should still exist in the script"
        offenders = [
            line.strip() for line in code.splitlines()
            if "skip_if_exists" in line and "do_sf" in line
        ]
        assert not offenders, (
            f"the skip guard is gated on the Snowflake write leg again ({offenders}) — under "
            f"W11_RAW_WRITE_MODE=s3 that makes it dead code (the FU-3 defect)"
        )

    def test_the_guard_reads_through_the_shared_lh_raw_helper(self):
        """A hardcoded lakehouse parquet glob is the 2026-07-20 phase-1.5 P0 (a deleted key
        took the whole daily job down). Route every read through the shared helper."""
        code = _code_only(_SCRIPT)
        assert "lh_raw(" in code, "the mirror read must go through the shared lh_raw() helper"
        offenders = [
            line.strip() for line in code.splitlines()
            if ("read_parquet(" in line and "lh_raw(" not in line)
            or "'s3://" in line or '"s3://' in line
        ]
        assert not offenders, f"hardcoded lakehouse path in executable source: {offenders}"

    def test_it_does_not_hand_build_a_boto3_client_with_env_keys(self):
        """W7b-1: `aws_access_key_id=os.environ.get(...)` is None on the EC2 box and DISABLES
        boto3's instance-role chain. (Also enforced repo-wide by the credential lint.)"""
        assert "aws_access_key_id" not in _SCRIPT.read_text()
