"""INC-43 guards — a DuckDB error must never destroy its own diagnostic.

Context (2026-08-13). `daily_ingestion_job` HALTed at `lakehouse_w3_marts_op` with

    UnicodeDecodeError: 'utf-8' codec can't decode byte 0xfc in position 15639

raised at `run_w1_lakehouse.py:2503`, the `CREATE OR REPLACE VIEW stg_batter_pitches`.
The whole daily slate was down and the message said nothing about why.

MEASURED root cause: the DuckDB *client* converts the C++ exception string to `str`;
when that string carries raw bytes the conversion raises `UnicodeDecodeError` and the
real DuckDB error is thrown away. INC-37 carded exactly this and a fix landed at ONE
call site (`_build_marts`); INC-43 hit a different, unwrapped one.

⚠️ HONEST SCOPE OF EACH GUARD — do not read more into these than they defend:

  * `TestModelSqlEncoding` is the file-encoding lint the story asked for. It defends a
    REAL and separate failure: a genuinely non-UTF-8 byte in a model `.sql`, which
    would crash `extract_duckdb_sql`'s `read_text()`. It would **NOT** have caught
    INC-43 — the model file was, and is, clean UTF-8 (45 non-ASCII bytes, every one a
    valid multi-byte sequence), and the extracted duckdb branch is 305 pure-ASCII
    bytes, so a byte at offset 15639 could not have come from it.

  * `TestSalvage` / `TestConnectionIsWrapped` are the guards that defend what actually
    broke: the salvage must exist, must be installed on the CONNECTION (not per call
    site), and must recover the message in full.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER = REPO_ROOT / "scripts" / "run_w1_lakehouse.py"
MODELS_DIR = REPO_ROOT / "dbt" / "models"


def _load_runner():
    """Import the builder by path — no sys.path mutation, no global state.

    (Fast-gate hygiene: this imports `scripts/`, never `pipeline/`, so it cannot
    trip the missing-dbt-manifest collection crash.)
    """
    spec = importlib.util.spec_from_file_location("_inc43_run_w1_lakehouse", RUNNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _source_without_comments() -> str:
    """The runner's source with `#` line comments stripped.

    INC-38: a source-inspection guard that matches anywhere in the file is satisfied
    by the explanatory COMMENT sitting above the code it checks, so it stays green
    with the real code deleted. Strip comments so only executable source can pass.
    """
    out = []
    for line in RUNNER.read_text(encoding="utf-8").splitlines():
        # Not a full tokenizer — good enough here, and it can only ever make the
        # guard STRICTER (a stripped string literal cannot satisfy a match).
        out.append(re.sub(r"#.*$", "", line))
    return "\n".join(out)


def _decodes_as_utf8(path: Path) -> tuple[bool, str]:
    try:
        path.read_bytes().decode("utf-8")
    except UnicodeDecodeError as exc:
        return False, f"{path}: byte {hex(exc.object[exc.start])} at offset {exc.start}"
    return True, ""


class TestModelSqlEncoding:
    """Every dbt model file `find_model`/`extract_duckdb_sql` can reach is UTF-8.

    `extract_duckdb_sql` does `find_model(name).read_text(encoding="utf-8")`. A
    non-UTF-8 byte anywhere in a model file is therefore an unconditional crash of
    whichever build reads it — and, because these builds are HALT-tier, a downed slate.
    """

    def test_every_model_sql_file_decodes_as_utf8(self):
        files = sorted(MODELS_DIR.rglob("*.sql"))
        # Non-vacuity: an empty scan set would pass on nothing (NF1.7(a)).
        assert len(files) > 50, (
            f"expected the dbt project to hold many models, found {len(files)} — "
            "the scan set is wrong, so this guard is passing on nothing"
        )

        failures = [msg for ok, msg in map(_decodes_as_utf8, files) if not ok]
        assert not failures, (
            "model .sql files are not valid UTF-8; extract_duckdb_sql's read_text "
            "will raise on them:\n  " + "\n  ".join(failures)
        )

    def test_the_incident_model_is_clean_and_its_duckdb_branch_is_ascii(self):
        """Pins the measured facts that REFUTE the 'bad byte in the SQL' hypothesis."""
        model = MODELS_DIR / "staging" / "stg_batter_pitches.sql"
        assert model.exists()
        ok, msg = _decodes_as_utf8(model)
        assert ok, msg

        runner = _load_runner()
        sql = runner.extract_duckdb_sql("stg_batter_pitches")
        statement = f"CREATE OR REPLACE VIEW stg_batter_pitches AS {sql}".encode("utf-8")
        assert sql.isascii(), "the executed duckdb branch is expected to be pure ASCII"
        # INC-43 reported a bad byte at offset 15639. The whole statement is ~350
        # bytes; if that ever stops being true this pin should be re-read, not deleted.
        assert len(statement) < 5000, (
            f"statement is {len(statement)} bytes — the INC-43 reasoning that offset "
            "15639 cannot lie inside it no longer holds"
        )

    def test_the_encoding_check_rejects_a_bad_byte(self, tmp_path):
        """RED-proof: the lint above must actually be able to FAIL."""
        bad = tmp_path / "bad_model.sql"
        bad.write_bytes(b"select 1 -- caf\xfc\n")
        ok, msg = _decodes_as_utf8(bad)
        assert not ok, "the encoding check passed a file carrying a raw 0xfc byte"
        assert "0xfc" in msg


class TestExtractorReadsUtf8Explicitly:
    def test_model_reads_pin_the_encoding(self):
        source = _source_without_comments()
        bare = re.findall(r"read_text\(\s*\)", source)
        assert not bare, (
            f"{len(bare)} bare read_text() call(s) remain in run_w1_lakehouse.py — "
            "a bare read_text() decodes with the LOCALE default, which is not "
            "guaranteed to be UTF-8 on the box"
        )
        assert 'read_text(encoding="utf-8")' in source

    def test_the_model_read_never_decodes_leniently(self):
        """⛔ errors='ignore'/'replace' on the SQL read would silently corrupt the SQL."""
        source = _source_without_comments()
        for bad in ('read_text(encoding="utf-8", errors=', "read_text(errors="):
            assert bad not in source, (
                f"found `{bad}` — a lenient decode of model SQL drops or mangles a byte "
                "and feeds the damaged text straight to conn.execute (NF-W2c)"
            )


class TestConnectionIsWrapped:
    """The salvage must be installed ONCE on the connection, not per call site."""

    def test_duckdb_connect_is_wrapped_at_construction(self):
        source = _source_without_comments()
        assert "_DiagnosticDuckDBConn(duckdb.connect())" in source, (
            "duckdb.connect() is not wrapped — INC-37 fixed one call site and INC-43 "
            "then landed on a different one; the guard belongs on the connection"
        )
        # And there must be no OTHER, unwrapped connection in this module.
        raw_connects = re.findall(r"duckdb\.connect\(", source)
        wrapped = re.findall(r"_DiagnosticDuckDBConn\(duckdb\.connect\(", source)
        assert len(raw_connects) == len(wrapped), (
            f"{len(raw_connects)} duckdb.connect() call(s) but only {len(wrapped)} "
            "wrapped — an unwrapped connection reopens the INC-43 blind spot"
        )

    def test_the_execute_sites_are_numerous_enough_to_justify_the_shape(self):
        """Non-vacuity for the claim above: a per-site guard really is unworkable."""
        source = _source_without_comments()
        assert len(re.findall(r"conn\.execute\(", source)) > 40


class _FakeConn:
    """Stands in for a DuckDB connection whose error message is not valid UTF-8."""

    def __init__(self, raw: bytes | None, *, fail_on: str = "execute"):
        self._raw = raw
        self._fail_on = fail_on
        self.closed = False
        self.registered: list[str] = []

    def _boom(self):
        if self._raw is None:
            raise UnicodeDecodeError("utf-8", b"", 0, 1, "invalid start byte")
        raise UnicodeDecodeError(
            "utf-8", self._raw, len(self._raw) - 1, len(self._raw), "invalid start byte"
        )

    def execute(self, sql, *args, **kwargs):
        if self._fail_on == "execute":
            self._boom()
        return self

    def fetchone(self):
        if self._fail_on == "fetchone":
            self._boom()
        return (1,)

    def close(self):
        self.closed = True

    def register(self, name, _obj):
        self.registered.append(name)


class TestSalvage:
    """The behaviour that was missing when the slate went down."""

    # The real DuckDB message this class produces: an httpfs/S3 diagnostic with a raw
    # byte in it. `0xfc` is the byte INC-43 reported.
    REAL_MESSAGE = (
        b"HTTP Error: HTTP GET error on 's3://baseball-betting-ml-artifacts/baseball/"
        b"lakehouse/stg_batter_pitches/2026/data.parquet' (HTTP 403)\n"
        b"<?xml version=\"1.0\"?><Error><Code>RequestTimeTooSkewed</Code>\xfc"
    )

    def test_execute_salvages_and_names_the_statement(self):
        runner = _load_runner()
        conn = runner._DiagnosticDuckDBConn(_FakeConn(self.REAL_MESSAGE))

        with pytest.raises(runner.NonUtf8DuckDBError) as excinfo:
            conn.execute("CREATE OR REPLACE VIEW stg_batter_pitches AS select 1")

        message = str(excinfo.value)
        # The whole point: the DuckDB diagnostic survives.
        assert "RequestTimeTooSkewed" in message
        assert "HTTP 403" in message
        # And it says WHICH statement.
        assert "CREATE OR REPLACE VIEW stg_batter_pitches" in message
        # The original exception is chained, so the traceback still shows the frame.
        assert isinstance(excinfo.value.__cause__, UnicodeDecodeError)

    def test_the_salvaged_message_is_not_truncated(self):
        """INC-42: head-truncating a traceback drops the diagnosis."""
        runner = _load_runner()
        raw = b"Invalid Input Error: " + b"x" * 20_000 + b"\xfc" + b"TAIL_MARKER"
        conn = runner._DiagnosticDuckDBConn(_FakeConn(raw))

        with pytest.raises(runner.NonUtf8DuckDBError) as excinfo:
            conn.execute("select 1")

        message = str(excinfo.value)
        assert "TAIL_MARKER" in message, "the salvaged message was truncated"
        assert "20022 bytes" in message or "bytes)" in message

    def test_a_lazy_error_surfacing_at_fetch_is_salvaged_too(self):
        """The S3 parquet scan actually fails at fetch, not at execute."""
        runner = _load_runner()
        conn = runner._DiagnosticDuckDBConn(
            _FakeConn(self.REAL_MESSAGE, fail_on="fetchone")
        )

        with pytest.raises(runner.NonUtf8DuckDBError) as excinfo:
            conn.execute("SELECT count(*) FROM stg_batter_pitches").fetchone()

        message = str(excinfo.value)
        assert "RequestTimeTooSkewed" in message
        assert "SELECT count(*) FROM stg_batter_pitches" in message
        assert "fetchone" in message

    def test_an_exception_carrying_no_bytes_is_reported_not_swallowed(self):
        runner = _load_runner()
        conn = runner._DiagnosticDuckDBConn(_FakeConn(None))
        with pytest.raises(runner.NonUtf8DuckDBError) as excinfo:
            conn.execute("select 1")
        assert "nothing to salvage" in str(excinfo.value)

    def test_the_proxy_is_otherwise_transparent(self):
        runner = _load_runner()
        fake = _FakeConn(None)
        # fail_on defaults to execute; use a conn that does not raise.
        fake._fail_on = "never"
        conn = runner._DiagnosticDuckDBConn(fake)

        assert conn.execute("select 1").fetchone() == (1,)
        conn.register("t", object())
        conn.close()
        assert fake.registered == ["t"]
        assert fake.closed is True

    def test_a_normal_duckdb_error_passes_through_unchanged(self):
        """The salvage must not swallow or reshape ordinary errors."""
        runner = _load_runner()

        class _Boom:
            def execute(self, *_a, **_k):
                raise ValueError("Binder Error: column x not found")

        conn = runner._DiagnosticDuckDBConn(_Boom())
        with pytest.raises(ValueError, match="Binder Error"):
            conn.execute("select x")


class TestBuildMartsSiteStillFires:
    """_build_marts adds the model + destination the connection proxy cannot know.

    NF-D17: after INC-43 the proxy raises NonUtf8DuckDBError, so a handler catching
    only UnicodeDecodeError there would be dead code (wired-but-never-invoked).
    """

    def test_it_catches_the_salvaged_type_too(self):
        source = _source_without_comments()
        assert "except (UnicodeDecodeError, NonUtf8DuckDBError)" in source, (
            "_build_marts still catches only UnicodeDecodeError — with the connection "
            "proxy installed that branch can never fire, and the model name and S3 "
            "destination are lost from the message"
        )
