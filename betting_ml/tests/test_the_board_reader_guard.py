"""E7.4 — the FanGraphs-BOARD reader guard (2026-07-27).

`baseball/milb/the_board` has exactly ONE valid reader, and the two wrong ones both fail
QUIETLY-ish in ways that cost real time:

  ❌ `delta_scan('…/the_board')` — the board's `mlbam_id` column is 100% NULL (by design: THE
     BOARD publishes no MLBAM id), so pyarrow inferred the arrow `null` type and the Delta schema
     records `"void"`. DuckDB's delta reader then hard-errors
     `Unsupported Delta table type: 'void'` on the WHOLE table — not just that column.

  ❌ `read_parquet('…/the_board/**/*.parquet')` — a glob has no Delta file list, so it unions
     TOMBSTONED files. The 2026-07-27 partition globs to 3,870 rows across three superseded
     ingest generations vs the ACID truth of 1,290, and the superseded generation extracted
     `fg_minor_id` differently — which silently drags the measured board→leaderboard match rate
     from 99.3% to 84.2%. A wrong number that LOOKS like a real finding is worse than an error.
     (Same class as the E11.20 phase-1.5 path-reader P0: a Delta table has no valid glob reader.)

  ✅ `DeltaTable(...).to_pyarrow_dataset()` — tolerates the void column AND honours tombstones.
     Shared as `betting_ml.scripts.milb_xref.player_xref.register_board`; import it.

E8.0 and E7.8 both join through this table, so a reintroduced glob would poison the draft board.
This guard is source-inspection only (no network, no imports of `pipeline` — fast-gate safe).
"""
import ast
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]

# Where a board reader could plausibly be written. Extend when a new consumer joins.
_SEARCH_DIRS = [
    _ROOT / "betting_ml" / "scripts",
    _ROOT / "scripts",
    _ROOT / "pipeline",
    _ROOT / "quant_sports_intel_models",
]

# The ingest owns the WRITE path (it constructs the same table URI to write it), so a bare
# `the_board` URI there is expected and not a read.
_WRITER_ALLOWLIST = {"ingest_fangraphs_prospects_to_s3.py"}


def _python_sources():
    for root in _SEARCH_DIRS:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if "__pycache__" in path.parts or path.name in _WRITER_ALLOWLIST:
                continue
            yield path


def _docstring_lines(text: str) -> set[int]:
    """Line numbers occupied by DOCSTRINGS.

    Prose deliberately names the wrong readers — this guard's own module docstring, and
    `player_xref`'s landmine notes, exist precisely to warn about them. A naive `#`-prefix filter
    misses those (they are triple-quoted, not commented), so the exclusion is parsed rather than
    guessed. Non-docstring string literals are NOT excluded: the real reads live in f-strings, so
    excluding every string would blind the guard to exactly what it is looking for."""
    covered: set[int] = set()
    try:
        tree = ast.parse(text)
    except SyntaxError:  # pragma: no cover — not our problem to report here
        return covered
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) \
                and isinstance(first.value.value, str):
            covered.update(range(first.lineno, (first.end_lineno or first.lineno) + 1))
    return covered


def _offending_lines(text: str, needles: tuple[str, ...]) -> list[str]:
    skip = _docstring_lines(text)
    out = []
    for i, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if i in skip or stripped.startswith("#"):
            continue
        if "the_board" not in line:
            continue
        if any(n in line for n in needles):
            out.append(f"{i}: {stripped}")
    return out


@pytest.mark.parametrize("bad_reader", ["delta_scan", "read_parquet"])
def test_the_board_is_never_read_with_delta_scan_or_a_parquet_glob(bad_reader):
    """A `delta_scan`/`read_parquet` on the same source line as `the_board` is the bug."""
    offenders = {}
    for path in _python_sources():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):  # pragma: no cover
            continue
        if "the_board" not in text:
            continue
        lines = _offending_lines(text, (bad_reader,))
        if lines:
            offenders[str(path.relative_to(_ROOT))] = lines

    assert not offenders, (
        f"`{bad_reader}` used to read baseball/milb/the_board:\n"
        + "\n".join(f"  {f}\n    " + "\n    ".join(v) for f, v in offenders.items())
        + "\n\nTHE BOARD has one valid reader — "
        "`betting_ml.scripts.milb_xref.player_xref.register_board` "
        "(DeltaTable(...).to_pyarrow_dataset()). `delta_scan` hard-errors on the table's "
        "void-typed mlbam_id column; a parquet glob silently unions TOMBSTONED ingest "
        "generations and fabricates a wrong match rate. See test docstring."
    )


def test_the_sanctioned_reader_exists_and_is_importable():
    """The guard only helps if the blessed alternative is actually reachable."""
    from betting_ml.scripts.milb_xref.player_xref import register_board

    assert callable(register_board)


def test_the_board_ingest_pins_its_string_columns():
    """Root-cause fix for the void column: an all-None object column makes pyarrow infer the
    `null` type. The writer must pin string columns so a future pull can never recreate it."""
    src = (_ROOT / "scripts" / "ingest_fangraphs_prospects_to_s3.py").read_text(encoding="utf-8")
    assert "_STRING_PINNED" in src, "the board ingest lost its string-column pin"
    assert 'astype("string")' in src, (
        "the board ingest must cast pinned columns to pandas StringDtype BEFORE "
        "pa.Table.from_pandas — otherwise an all-None column becomes an arrow `null` type and "
        "Delta records it as `void`, which makes the WHOLE table unreadable by delta_scan."
    )
    assert '"mlbam_id"' in src.split("_STRING_PINNED")[1][:600], (
        "mlbam_id is the column that actually triggered this (100% NULL by design) — it must "
        "stay in the pinned set."
    )
