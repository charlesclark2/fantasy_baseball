"""INC-45 — the DuckDB lake read must authenticate through the channel `delta_scan` ACTUALLY READS.

🔴 THE LIVE DEFECT THIS PINS. NF-K1 cured a published board that shipped ZERO K and ZERO D/ST by
adding a LAKE fallback for the K/DST projection (the one artifact the box's publish chain reads and
never writes). NF-K1's own recap flagged the fallback as UNPROVEN, because the repair ran on the
laptop — where the local parquet exists, so the lake path never fired. On the box it fired and
loaded 0 rows every morning, NF-K1's publish coverage guard correctly refused to ship the gap, and
the board froze mid-draft-season.

THE CAUSE IS THE CREDENTIAL CHANNEL, and it is invisible on any developer machine:

    DuckDB's `delta` extension resolves S3 credentials through the SECRET MANAGER only.
    `SET s3_access_key_id / s3_secret_access_key / s3_region` is an **httpfs** channel and is
    IGNORED by `delta_scan`.

Six fantasy call sites resolved credentials through `s3io.storage_options()` (the botocore chain —
env → profile → IMDS instance role, the one every box writer here depends on) and then handed them
to DuckDB through those legacy settings, i.e. into a channel the reader never reads. What actually
authenticated the read was delta-kernel-rs's OWN ambient resolution: on a laptop it finds
`~/.aws`, so every one of those reads looked fine; off the laptop it does not.

MEASURED, before the fix, with real credentials passed ONLY through the legacy settings and the
ambient environment stripped: `delta_scan` ignored them and went off to IMDS by itself
(`DeltaKernel ObjectStoreError … PUT http://169.254.169.254/latest/api/token`). After the fix, the
identical environment reads the 74 rows (42 K + 32 D/ST). Every lake reader in this repo that is
PROVEN on the box already used the secret channel — `sports_dbt/profiles.yml` (`provider:
credential_chain`, which `delta_scan`s this exact bucket on this exact box), `ingest/query_lake`,
`run_nf_c0e_captured_terms`.

⚠️ WHY THESE TESTS DRIVE A RECORDING CONNECTION RATHER THAN A REAL ONE: a real
`configure_duckdb_lake_auth` call runs `INSTALL delta` (a download) and then talks to S3. The fast
gate mocks all IO, so the assertions here are made against the SQL the helper actually emits —
which is the thing that was wrong. The live end-to-end read is the operator's box run.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from quant_sports_intel_models.football.nfl.ingest import s3io

_FANTASY_DIR = Path(s3io.__file__).resolve().parent.parent / "fantasy"

# The credential/region settings that DO NOT reach `delta_scan`. Their presence anywhere in this
# tree is the INC-45 defect, whatever else the module also does.
_DEAD_CHANNEL = ("s3_access_key_id", "s3_secret_access_key", "s3_session_token", "set s3_region")


class _RecordingCon:
    """A stand-in DuckDB connection that records the SQL it is asked to execute."""

    def __init__(self):
        self.sql: list[str] = []

    def execute(self, sql: str):
        self.sql.append(sql)
        return self

    def joined(self) -> str:
        return "\n".join(self.sql)


def _configure(monkeypatch, opts: dict) -> _RecordingCon:
    monkeypatch.setattr(s3io, "storage_options", lambda region=s3io.DEFAULT_REGION: dict(opts))
    con = _RecordingCon()
    s3io.configure_duckdb_lake_auth(con)
    return con


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. The channel itself
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_resolved_credentials_are_placed_in_a_secret_not_the_legacy_settings(monkeypatch):
    """THE regression. Credentials `storage_options()` resolved (on the box: the instance role via
    IMDS) must land in a SECRET — the only channel `delta_scan` reads."""
    con = _configure(monkeypatch, {"AWS_REGION": "us-east-2",
                                   "AWS_ACCESS_KEY_ID": "AKIAPROBE", "AWS_SECRET_ACCESS_KEY": "shh"})
    sql = con.joined()

    secret = [s for s in con.sql if "SECRET" in s.upper()]
    assert secret, f"no CREATE SECRET was issued — delta_scan will see NO credentials: {con.sql}"
    assert "TYPE S3" in secret[0].upper()
    assert "AKIAPROBE" in secret[0] and "shh" in secret[0], (
        "the resolved credentials never reached the secret — this is exactly the INC-45 defect, "
        f"where they were handed to a channel delta_scan ignores: {secret[0]}")
    # ⛔ and NOT through the dead channel, in any form
    for dead in _DEAD_CHANNEL:
        assert dead not in sql.lower(), f"{dead!r} is an httpfs setting delta_scan ignores: {sql}"


def test_a_session_token_is_carried_because_an_instance_role_always_issues_one(monkeypatch):
    """The box authenticates as an IMDS instance role, whose credentials are ALWAYS temporary —
    dropping the session token would authenticate as nothing at all."""
    con = _configure(monkeypatch, {"AWS_REGION": "us-east-2", "AWS_ACCESS_KEY_ID": "AKIAPROBE",
                                   "AWS_SECRET_ACCESS_KEY": "shh", "AWS_SESSION_TOKEN": "tok-42"})
    assert "tok-42" in con.joined(), "an instance-role session token was dropped"


def test_the_region_is_pinned_on_the_secret_because_the_bucket_is_us_east_2(monkeypatch):
    """`SET s3_region` is part of the same ignored channel, so the region has to ride the secret."""
    con = _configure(monkeypatch, {"AWS_REGION": "us-east-2", "AWS_ACCESS_KEY_ID": "AKIAPROBE",
                                   "AWS_SECRET_ACCESS_KEY": "shh"})
    secret = next(s for s in con.sql if "SECRET" in s.upper())
    assert re.search(r"REGION\s+'us-east-2'", secret, re.I), secret


def test_it_falls_back_to_credential_chain_when_botocore_resolves_nothing(monkeypatch):
    """With no concrete credentials, DuckDB resolves internally rather than signing nothing."""
    con = _configure(monkeypatch, {"AWS_REGION": "us-east-2"})
    secret = next(s for s in con.sql if "SECRET" in s.upper())
    assert "credential_chain" in secret.lower(), secret


def test_an_empty_string_akid_never_reaches_the_secret(monkeypatch):
    """🪪 THE AKID LANDMINE. A compose-interpolated unset host var lands in the container as an
    EMPTY STRING. It must not be signed verbatim — `storage_options()` skips it, and so must this."""
    con = _configure(monkeypatch, {"AWS_REGION": "us-east-2", "AWS_ACCESS_KEY_ID": "",
                                   "AWS_SECRET_ACCESS_KEY": ""})
    secret = next(s for s in con.sql if "SECRET" in s.upper())
    assert "credential_chain" in secret.lower(), (
        f"an empty AKID was passed through instead of falling back to the chain: {secret}")
    assert "KEY_ID ''" not in secret


def test_the_delta_extension_is_loaded_before_the_secret_is_created(monkeypatch):
    con = _configure(monkeypatch, {"AWS_REGION": "us-east-2"})
    joined = con.joined().lower()
    assert "load delta" in joined and "load httpfs" in joined
    assert joined.index("load delta") < joined.index("secret")


def test_an_absent_home_gets_an_explicit_extension_directory(monkeypatch):
    """E5.10 — DuckDB resolves its extension dir under $HOME and raises `Can't find the home
    directory at ''` BEFORE any download when HOME is empty. A no-op wherever HOME is set."""
    monkeypatch.delenv("HOME", raising=False)
    con = _configure(monkeypatch, {"AWS_REGION": "us-east-2"})
    assert any("home_directory" in s for s in con.sql), con.sql

    monkeypatch.setenv("HOME", "/root")
    assert not any("home_directory" in s for s in _configure(
        monkeypatch, {"AWS_REGION": "us-east-2"}).sql), "must not override a real HOME"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. ONE owner — the six call sites that each carried their own copy
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _string_literals(path: Path) -> list[str]:
    """Every string literal in `path` EXCEPT docstrings.

    Docstrings are excluded on purpose: this file's own prose names the dead settings, and a guard
    that prose can satisfy — or that prose can BREAK — is not a guard (INC-38).
    """
    tree = ast.parse(path.read_text())
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            doc = node.body[0] if node.body else None
            if isinstance(doc, ast.Expr) and isinstance(doc.value, ast.Constant) \
                    and isinstance(doc.value.value, str):
                docstrings.add(id(doc.value))
    return [n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docstrings]


def _delta_readers() -> dict[Path, list[str]]:
    """Every fantasy module that issues a `delta_scan(...)` — measured, not listed."""
    out = {}
    for path in sorted(_FANTASY_DIR.glob("*.py")):
        lits = [s for s in _string_literals(path) if "delta_scan(" in s]
        if lits:
            out[path] = lits
    return out


# A module authenticates correctly if it reaches the owner, borrows a helper that does (pinned
# behaviourally below), or creates an equivalent S3 secret inline. What is NOT acceptable is the
# legacy channel — that is the dead one, and it has its own test.
_OWNER_REFERENCES = ("duckdb_lake_connection", "_lake_connection", "_kdst_lake_connection")


def test_every_fantasy_delta_reader_authenticates_through_the_secret_channel():
    """A per-module copy of the connection setup is how six call sites came to share one silent
    bug. Whatever route a reader takes, it must end at a SECRET — the only channel `delta_scan`
    reads."""
    readers = _delta_readers()
    # ⛔ anti-vacuity FIRST: an empty match set would pass this test on nothing (DSR-CONV #690).
    assert len(readers) >= 4, f"the delta-reader scan found almost nothing — it has rotted: {readers}"
    for expected in ("run_league_board.py", "export_draft_board_json.py", "defense_source.py"):
        assert any(p.name == expected for p in readers), f"{expected} is no longer a delta reader?"

    offenders = []
    for path in readers:
        src = path.read_text()
        inline_secret = any("create secret" in s.lower() and "type s3" in s.lower()
                            for s in _string_literals(path))
        if not (inline_secret or any(ref in src for ref in _OWNER_REFERENCES)):
            offenders.append(path.name)
    assert not offenders, (
        f"{offenders} run delta_scan without ever creating an S3 secret — they will authenticate "
        "off delta-kernel-rs's ambient chain, which works on a laptop and not on the box (INC-45)")


def test_the_borrowed_connection_helpers_really_delegate_to_the_owner():
    """Closes the hole the text scan above cannot see: `player_naming` borrows
    `export_draft_board_json._lake_connection`, and `run_league_board` reads the lake through
    `_kdst_lake_connection`. Both are accepted by name up there, so BOTH are pinned by behaviour
    here — otherwise re-forking one back onto its own `duckdb.connect()` would stay green."""
    from quant_sports_intel_models.football.nfl.fantasy import export_draft_board_json as EX
    from quant_sports_intel_models.football.nfl.fantasy import run_league_board as RLB

    sentinel = object()
    for module, helper in ((EX, "_lake_connection"), (RLB, "_kdst_lake_connection")):
        original = s3io.duckdb_lake_connection
        try:
            s3io.duckdb_lake_connection = lambda **_: sentinel
            assert getattr(module, helper)() is sentinel, (
                f"{module.__name__}.{helper} no longer delegates to s3io.duckdb_lake_connection")
        finally:
            s3io.duckdb_lake_connection = original


@pytest.mark.parametrize("path", sorted(_FANTASY_DIR.glob("*.py")), ids=lambda p: p.name)
def test_no_fantasy_module_configures_the_channel_delta_scan_ignores(path):
    """The dead channel is gone and must stay gone — asserted over executable string literals, so
    a docstring explaining the landmine cannot satisfy or break it."""
    for literal in _string_literals(path):
        low = literal.lower()
        for dead in _DEAD_CHANNEL:
            assert dead not in low, (
                f"{path.name} configures {dead!r} — an httpfs setting `delta_scan` IGNORES. "
                "Use s3io.duckdb_lake_connection() (INC-45).")
