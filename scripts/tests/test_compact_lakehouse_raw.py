"""INC-42 — guards for the lakehouse_raw compactor.

The script's whole safety argument rests on two claims that live OUTSIDE it, so both are pinned
here against the real files rather than restated:

  1. the write order (promote-then-delete) is safe ONLY because every reader of the
     `mlb_odds_raw` glob is duplicate-idempotent — so this asserts the dedup construct is still
     present in each reader, and that the reader list is still exhaustive;
  2. an original file is deleted ONLY after the compacted object has been re-read FROM S3 and
     verified — so this asserts the call ORDER, and that a verification failure leaves the
     partition byte-for-byte as it was found.

Every test drives the real functions against an in-memory fake S3 holding REAL parquet bytes
(no mocked pyarrow), so a wrong schema union or a lost column fails here rather than in prod.
Each clause has its own isolating test: deleting any one clause from the source must fail exactly
one test (the NF-D17 rule — a fixture that trips several clauses proves none of them).
"""
from __future__ import annotations

import io
import re
from datetime import date
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

import compact_lakehouse_raw as clr

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _never_build_a_real_s3_client(monkeypatch):
    """⛔ No test in this module may reach real AWS. This is not belt-and-braces — it is a fix.

    Two tests below drive `main(..., "--apply")` to prove a REFUSAL, relying on main() returning
    before it builds a client. That holds for the shipped source — but a RED-proof deletes exactly
    those refusals, and the first run of this module's RED-proof therefore executed a real
    `--apply` against PRODUCTION S3 (2026-08-12): it compacted mlb_odds_raw at --min-age-days 0
    and one catcher_framing_raw partition. Nothing was lost — `compact_partition` was unmutated,
    so every partition went through the verified promote-then-delete — but a test suite must not
    be one deleted `if` away from mutating prod.

    With this stub a removed guard still fails the test (main() hits the stub and raises), which
    is the RED the proof is looking for, without any network call.
    """
    def _refuse(*_a, **_kw):
        raise AssertionError(
            "a test tried to build a REAL S3 client — pass a FakeS3 explicitly. If you are "
            "RED-proofing a guard in main(), this AssertionError IS the expected failure."
        )
    monkeypatch.setattr(clr, "make_s3_client", _refuse)


# ────────────────────────────────────────────────────────────────────────────────
# In-memory S3 (records the operation ORDER — that is what several tests assert on)
# ────────────────────────────────────────────────────────────────────────────────
class FakeS3:
    def __init__(self, objects: dict[str, bytes] | None = None):
        self.objects: dict[str, bytes] = dict(objects or {})
        self.calls: list[tuple[str, str]] = []          # (op, key)
        self.corrupt_readback: bytes | None = None      # forces a verification failure

    def get_paginator(self, _op):
        outer = self

        class _P:
            def paginate(self, Bucket, Prefix):          # noqa: N803 - boto3 signature
                assert Bucket == clr.BUCKET
                yield {"Contents": [{"Key": k} for k in sorted(outer.objects) if k.startswith(Prefix)]}

        return _P()

    def get_object(self, Bucket, Key):                   # noqa: N803
        self.calls.append(("get", Key))
        if self.corrupt_readback is not None and Key.rsplit("/", 1)[-1].startswith(clr.COMPACT_PREFIX):
            return {"Body": io.BytesIO(self.corrupt_readback)}
        return {"Body": io.BytesIO(self.objects[Key])}

    def put_object(self, Bucket, Key, Body):             # noqa: N803
        self.calls.append(("put", Key))
        self.objects[Key] = Body

    def delete_object(self, Bucket, Key):                # noqa: N803
        self.calls.append(("delete", Key))
        self.objects.pop(Key, None)

    def delete_objects(self, Bucket, Delete):            # noqa: N803
        for o in Delete["Objects"]:
            self.calls.append(("delete", o["Key"]))
            self.objects.pop(o["Key"], None)


def _parquet(rows: list[dict]) -> bytes:
    """Real parquet bytes from row dicts (columns are the union across rows, missing ⇒ null)."""
    cols: list[str] = []
    for r in rows:
        for c in r:
            if c not in cols:
                cols.append(c)
    table = pa.table({c: [r.get(c) for r in rows] for c in cols})
    buf = io.BytesIO()
    pq.write_table(table, buf)
    return buf.getvalue()


def _key(dt: str, name: str, source: str = "mlb_odds_raw") -> str:
    return f"{clr.RAW_PREFIX}/{source}/dt={dt}/{name}"


def _partition(dt: str, n_files: int = 3, source: str = "mlb_odds_raw") -> dict[str, bytes]:
    return {
        _key(dt, f"part-{i:012x}.parquet", source): _parquet(
            [{"ingestion_ts": f"{dt}T0{i}:00:00", "load_id": f"L{i}", "raw_json": '{"id":"e1"}'}]
        )
        for i in range(n_files)
    }


def _live_keys(s3: FakeS3, dt: str) -> list[str]:
    return sorted(k for k in s3.objects if f"dt={dt}/" in k)


# ────────────────────────────────────────────────────────────────────────────────
# 1. The allowlist — an unvetted source must be refused, not compacted by analogy
# ────────────────────────────────────────────────────────────────────────────────
def test_only_allowlisted_sources_may_be_compacted():
    assert set(clr.COMPACTABLE_SOURCES) == {"mlb_odds_raw"}, (
        "adding a source here asserts that EVERY reader of its glob is duplicate-idempotent; "
        "state that rationale in the registry value and extend the reader guards below"
    )


def test_a_known_raw_source_that_is_not_allowlisted_is_still_refused(capsys):
    """The dangerous case: a real source whose readers were never checked."""
    other = sorted(clr.RAW_SOURCES - set(clr.COMPACTABLE_SOURCES))[0]
    assert clr.main(["--source", other, "--apply"]) == 1
    assert "NOT allowlisted" in capsys.readouterr().err


def test_every_allowlisted_source_states_its_rationale():
    for source, why in clr.COMPACTABLE_SOURCES.items():
        assert source in clr.RAW_SOURCES
        assert len(why) > 80 and "dedup" in why.lower()


# ────────────────────────────────────────────────────────────────────────────────
# 2. The reader claim — pinned against the REAL files, so a removed dedup fails the build
# ────────────────────────────────────────────────────────────────────────────────
#   path → (why it is duplicate-idempotent, regex proving it, on comment-stripped source)
_MLB_ODDS_RAW_READERS: dict[str, tuple[str, str]] = {
    "dbt/models/staging/stg_oddsapi_odds.sql": (
        "qualify row_number()=1 per (load_id, event, bookmaker, market, outcome)",
        r"qualify\s+row_number\(\)\s+over\s*\(\s*partition\s+by\s+load_id",
    ),
    "dbt/models/mart/mart_bookmaker_disagreement.sql": (
        "historical path group-bys + qualifies, and filters to commence years 2021-2025",
        r"qualify\s+row_number\(\)",
    ),
    "pipeline/sensors/odds_freshness_alert_sensor.py": (
        "reads MAX(ingestion_ts) / ORDER BY ingestion_ts DESC LIMIT 1 — both dup-invariant",
        r"MAX\(ingestion_ts",
    ),
    "scripts/run_w1_lakehouse.py": (
        "the recent-scoped intraday view REWRITES stg_oddsapi_odds' glob but reuses its SQL, "
        "so it inherits that model's qualify",
        r"extract_duckdb_sql\(\"stg_oddsapi_odds\"\)",
    ),
}

# A READ of this glob, as opposed to a mention of the source name. Deliberately narrow: the
# writers (odds_api_ingestion), the retired export bridge, the Snowflake DDL and the path registry
# in lakehouse_monitor all NAME mlb_odds_raw in live code without ever binding its glob, and a
# detector that fired on those would go red on unrelated edits — which trains the next reader to
# widen the allowlist instead of thinking about it.
_READ_CONSTRUCT = re.compile(
    r"read_parquet|lh_raw\(|lakehouse_raw_loc\(|delta_scan|\*\*/\*\.parquet"
)
_READ_WINDOW = 1   # lines either side, so a wrapped call still matches

_SQL_LINE_COMMENT = re.compile(r"^\s*(--|#).*$", re.MULTILINE)
_SQL_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_PY_HASH_COMMENT = re.compile(r"^\s*#.*$", re.MULTILINE)


def _decommented(path: Path) -> str:
    """Strip line comments — INC-38: a guard a COMMENT can satisfy is not a guard."""
    return _SQL_LINE_COMMENT.sub("", path.read_text())


def _code_only(path: Path) -> str:
    """Source with comments AND docstrings removed, so a passing MENTION is not a reference.

    Without this the exhaustiveness detector flags five files whose only tie to mlb_odds_raw is a
    sentence in a docstring about the retired export bridge — noise that would train the next
    reader to widen the allowlist instead of thinking.
    """
    text = path.read_text(errors="ignore")
    if path.suffix == ".sql":
        # ⚠️ line comments FIRST: a `--` that comments out a `/*` would otherwise make the block
        # regex swallow real code.
        return _SQL_BLOCK_COMMENT.sub("", _SQL_LINE_COMMENT.sub("", text))
    import ast
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return text
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                text = text.replace(doc, "", 1)
    return _PY_HASH_COMMENT.sub("", text)


@pytest.mark.parametrize("rel", sorted(_MLB_ODDS_RAW_READERS))
def test_each_mlb_odds_raw_reader_still_dedups(rel):
    why, pattern = _MLB_ODDS_RAW_READERS[rel]
    src = _decommented(REPO_ROOT / rel)
    assert re.search(pattern, src, re.IGNORECASE), (
        f"{rel} no longer matches /{pattern}/.\n"
        f"compact_lakehouse_raw.py deletes a partition's original files only AFTER writing the "
        f"compacted one, which is safe ONLY because this reader is duplicate-idempotent ({why}). "
        f"If that dedup is genuinely gone, the compactor's write order must change — do not "
        f"loosen this guard."
    )


def _detect_glob_readers() -> set[str]:
    """Files whose LIVE CODE binds the mlb_odds_raw glob (comments and docstrings excluded)."""
    found: set[str] = set()
    for root in ("dbt/models", "pipeline", "scripts", "betting_ml"):
        for path in (REPO_ROOT / root).rglob("*"):
            if path.suffix not in (".sql", ".py") or "tests" in path.parts:
                continue
            if path.name == "compact_lakehouse_raw.py":
                continue                      # this script — the compactor, not a consumer
            lines = _code_only(path).splitlines()
            for i, line in enumerate(lines):
                if "mlb_odds_raw" not in line:
                    continue
                window = "\n".join(lines[max(0, i - _READ_WINDOW): i + _READ_WINDOW + 1])
                if _READ_CONSTRUCT.search(window):
                    found.add(str(path.relative_to(REPO_ROOT)))
                    break
    return found


def test_the_reader_list_is_still_exhaustive():
    """A NEW reader of this glob must join the registry — INC-38's exhaustive-registry rule."""
    found = _detect_glob_readers()

    # Non-vacuity (NF1.7(a)): the detector must actually find the known readers, or "no new
    # readers" would be indistinguishable from "the detector matches nothing".
    assert found >= set(_MLB_ODDS_RAW_READERS), (
        f"the detector stopped finding known readers: missing "
        f"{sorted(set(_MLB_ODDS_RAW_READERS) - found)}"
    )
    unregistered = found - set(_MLB_ODDS_RAW_READERS)
    assert not unregistered, (
        f"new reader(s) of the mlb_odds_raw glob: {sorted(unregistered)}. Prove each is "
        f"duplicate-idempotent and register it in _MLB_ODDS_RAW_READERS, or compaction's "
        f"promote-then-delete order is no longer safe for this source."
    )


def test_parity_check_still_skips_mlb_odds_raw():
    """The one consumer whose non-reader status could silently flip.

    parity_check_w3pre's pre-flight reads `count(*) vs count(distinct key)` as "a partition was
    doubled" and PRINTS `aws s3 rm ...` as the remedy. mlb_odds_raw is in FROZEN_SOURCES so it is
    skipped — but if it is ever un-frozen, that check and a compaction dup window could collide on
    live capture data. This goes RED at exactly that moment.
    """
    src = _decommented(REPO_ROOT / "scripts/parity_check_w3pre.py")
    frozen = re.search(r"FROZEN_SOURCES\s*=\s*\{(.*?)\n\}", src, re.DOTALL)
    assert frozen, "FROZEN_SOURCES not found in parity_check_w3pre.py"
    # ⚠️ the QUOTED key, not a substring: `"mlb_odds_raw_X"` contains `mlb_odds_raw`, so a
    # substring check passes on a renamed key. (This guard's own RED-proof caught that.)
    assert re.search(r'"mlb_odds_raw"\s*:', frozen.group(1)), (
        "mlb_odds_raw left parity_check_w3pre's FROZEN_SOURCES — re-check how its duplicate "
        "pre-flight interacts with compaction before allowing this"
    )


# ────────────────────────────────────────────────────────────────────────────────
# 3. The live partition is never in scope
# ────────────────────────────────────────────────────────────────────────────────
def test_the_live_and_previous_partitions_are_never_eligible():
    today = date(2026, 8, 12)
    dts = ["2026-08-08", "2026-08-10", "2026-08-11", "2026-08-12"]
    got = clr.eligible_partitions(dts, today=today, min_age_days=2)
    assert got == ["2026-08-08", "2026-08-10"]
    assert "2026-08-12" not in got, "today's partition is the one the 30-min capture appends to"


def test_min_age_days_below_the_floor_is_refused(capsys):
    assert clr.main(["--source", "mlb_odds_raw", "--min-age-days", "0", "--apply"]) == 1
    assert "floor" in capsys.readouterr().err


def test_the_nullts_sentinel_partition_is_never_compacted():
    assert not clr.is_date_partition(clr.NULL_TS_PARTITION)
    assert clr.eligible_partitions(
        [clr.NULL_TS_PARTITION, "2026-01-01"], today=date(2026, 8, 12), min_age_days=2
    ) == ["2026-01-01"]


# ────────────────────────────────────────────────────────────────────────────────
# 4. Row/column/value preservation
# ────────────────────────────────────────────────────────────────────────────────
def test_compaction_preserves_every_row_column_and_value():
    dt = "2026-08-01"
    s3 = FakeS3({
        _key(dt, "part-a.parquet"): _parquet([{"ingestion_ts": "t1", "load_id": "L1"},
                                              {"ingestion_ts": "t2", "load_id": "L2"}]),
        # a column only SOME files carry — union_by_name readers see it, so compaction must keep it
        _key(dt, "part-b.parquet"): _parquet([{"ingestion_ts": "t3", "load_id": "L3",
                                               "x_requests_remaining": 42}]),
    })
    res = clr.compact_partition(s3, "mlb_odds_raw", dt, apply=True)

    assert res["files_before"] == 2 and res["files_after"] == 1 and res["rows"] == 3
    remaining = _live_keys(s3, dt)
    assert len(remaining) == 1 and remaining[0].rsplit("/", 1)[-1].startswith(clr.COMPACT_PREFIX)

    out = pq.read_table(io.BytesIO(s3.objects[remaining[0]]))
    assert out.num_rows == 3
    assert set(out.column_names) == {"ingestion_ts", "load_id", "x_requests_remaining"}
    assert sorted(out.column("load_id").to_pylist()) == ["L1", "L2", "L3"]
    assert out.column("x_requests_remaining").to_pylist().count(42) == 1


def test_verify_compacted_catches_a_dropped_column():
    src = pa.table({"a": [1], "b": [2]})
    with pytest.raises(clr.CompactionRefused, match="column set changed"):
        clr.verify_compacted(pa.table({"a": [1]}), [src])


def test_verify_compacted_catches_a_lost_row():
    src = pa.table({"a": [1, 2]})
    with pytest.raises(clr.CompactionRefused, match="row count mismatch"):
        clr.verify_compacted(pa.table({"a": [1]}), [src])


def test_verify_compacted_catches_values_silently_becoming_null():
    src = pa.table({"a": [1, 2]})
    with pytest.raises(clr.CompactionRefused, match="non-null counts changed"):
        clr.verify_compacted(pa.table({"a": [None, None]}), [src])


# ────────────────────────────────────────────────────────────────────────────────
# 5. ⭐ The destructive-order invariants
# ────────────────────────────────────────────────────────────────────────────────
def test_originals_are_deleted_only_after_the_new_object_is_re_read_from_s3():
    dt = "2026-08-01"
    s3 = FakeS3(_partition(dt, n_files=3))
    clr.compact_partition(s3, "mlb_odds_raw", dt, apply=True)

    ops = s3.calls
    put_at = next(i for i, (op, k) in enumerate(ops) if op == "put")
    new_key = ops[put_at][1]
    readback_at = next(i for i, (op, k) in enumerate(ops) if op == "get" and k == new_key)
    first_delete = next(i for i, (op, _) in enumerate(ops) if op == "delete")

    assert put_at < first_delete, "an original was deleted before the compacted object was written"
    assert readback_at < first_delete, (
        "an original was deleted before the compacted object was re-read from S3 — verifying the "
        "in-memory table proves nothing about what a reader will find"
    )


def test_a_failed_readback_removes_the_new_object_and_keeps_every_original():
    dt = "2026-08-01"
    originals = _partition(dt, n_files=3)
    s3 = FakeS3(originals)
    s3.corrupt_readback = _parquet([{"ingestion_ts": "t1", "load_id": "L1"}])  # 1 row, not 3

    with pytest.raises(clr.CompactionRefused):
        clr.compact_partition(s3, "mlb_odds_raw", dt, apply=True)

    assert _live_keys(s3, dt) == sorted(originals), (
        "a failed verification must leave the partition byte-for-byte as it was found"
    )


def test_a_dry_run_neither_writes_nor_deletes():
    dt = "2026-08-01"
    originals = _partition(dt, n_files=4)
    s3 = FakeS3(originals)
    res = clr.compact_partition(s3, "mlb_odds_raw", dt, apply=False)

    assert res["dry_run"] is True and res["files_before"] == 4
    assert _live_keys(s3, dt) == sorted(originals)
    assert not [c for c in s3.calls if c[0] in ("put", "delete")]


# ────────────────────────────────────────────────────────────────────────────────
# 6. Crash recovery — the promote-then-delete order's repayment
# ────────────────────────────────────────────────────────────────────────────────
def test_an_interrupted_run_is_finished_on_the_next_pass():
    """Crash between promote and delete ⇒ compacted file beside its originals. Decidable."""
    dt = "2026-08-01"
    originals = _partition(dt, n_files=3)
    all_rows = [{"ingestion_ts": f"{dt}T0{i}:00:00", "load_id": f"L{i}",
                 "raw_json": '{"id":"e1"}'} for i in range(3)]
    s3 = FakeS3({**originals, _key(dt, f"{clr.COMPACT_PREFIX}deadbeef.parquet"): _parquet(all_rows)})

    res = clr.compact_partition(s3, "mlb_odds_raw", dt, apply=True)

    assert res["repaired"] is True and res["rows"] == 3
    remaining = _live_keys(s3, dt)
    assert len(remaining) == 1 and clr.COMPACT_PREFIX in remaining[0]


def test_an_undecidable_partial_state_is_refused_and_deletes_nothing():
    dt = "2026-08-01"
    originals = _partition(dt, n_files=3)
    partial = [{"ingestion_ts": "t1", "load_id": "L1", "raw_json": "{}"}]  # 1 row, not 3
    compact_key = _key(dt, f"{clr.COMPACT_PREFIX}deadbeef.parquet")
    s3 = FakeS3({**originals, compact_key: _parquet(partial)})

    with pytest.raises(clr.CompactionRefused, match="cannot be repaired automatically"):
        clr.compact_partition(s3, "mlb_odds_raw", dt, apply=True)
    assert _live_keys(s3, dt) == sorted([*originals, compact_key])


def test_an_already_compacted_partition_is_a_no_op():
    dt = "2026-08-01"
    s3 = FakeS3({_key(dt, f"{clr.COMPACT_PREFIX}deadbeef.parquet"): _parquet([{"a": 1}])})
    assert clr.compact_partition(s3, "mlb_odds_raw", dt, apply=True) is None
    assert not [c for c in s3.calls if c[0] in ("put", "delete")]


def test_a_single_file_partition_is_left_alone():
    dt = "2026-08-01"
    s3 = FakeS3({_key(dt, "part-a.parquet"): _parquet([{"a": 1}])})
    assert clr.compact_partition(s3, "mlb_odds_raw", dt, apply=True) is None
    assert not [c for c in s3.calls if c[0] in ("put", "delete")]
