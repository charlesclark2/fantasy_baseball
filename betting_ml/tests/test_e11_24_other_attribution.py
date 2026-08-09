"""E11.24 — measurement-hygiene guards for the `other`-bucket statement attribution instrument.

This script is analysis tooling, so what is worth guarding is not its output but the two
structural properties that make its output MEAN anything. Both were violated during the session
that built it, and both fail SILENTLY — the script still runs and still prints a plausible table.

GUARD 1 — `warehouse_size is not null` on every awake-time cut.
    A `query_history` row carrying `warehouse_name='COMPUTE_WH'` has NOT necessarily used the
    warehouse: cloud-services-only statements (SHOW OBJECTS, ALTER SESSION, ALTER EXTERNAL TABLE
    REFRESH, CALL SYSTEM$..., and every `create or replace view`) are billed to cloud services
    and can neither resume the warehouse nor keep it awake. Measured 2026-08-08 they are 40-138%
    of the naive awake-minutes figure. Without the filter the instrument ranked a Snowsight
    browser tab's notification poll as the largest awake-time consumer in the account — a
    phantom that would have sent a fix session at nothing.

GUARD 2 — `FAMILY_CASE` is IMPORTED from the census, never restated.
    Two copies of a classifier drift, and when they drift an `other` total silently stops meaning
    the same thing in the two scripts. The 2026-08-03 session's 110-char truncation bug is the
    same failure one level down: classify over a different window and real families land in
    `other`, inventing a phantom waker.

SOURCE-INSPECTION, because both properties are structural (which SQL text reaches Snowflake),
not behavioural — there is no warehouse in CI to observe. Comments are STRIPPED before every
assertion: INC-38's prose-cannot-satisfy lesson, and it binds hard here because this file's
docstrings quote the very strings being asserted on.

⛔ NOT an import of `pipeline` (E11.23): the fast gate has no dbt manifest. The attribution
script is import-safe (its Snowflake import is inside main()), so it is loaded by path.
"""

from __future__ import annotations

import ast
import importlib.util
import io
import re
import tokenize
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "report_e11_24_other_attribution.py"
CENSUS = REPO_ROOT / "scripts" / "report_e11_24_wake_census.py"


def _strip_comments(src: str) -> str:
    """Remove python DOCSTRINGS, `#` comments and SQL `--` comments — and nothing else.

    A source-inspection assertion satisfiable by a COMMENT measures the documentation, not the
    code (INC-38). Docstrings must go because this module's own prose names every guarded string.

    ⚠️ BUT THE OBVIOUS IMPLEMENTATION IS WORSE THAN NO STRIPPING AT ALL, and it shipped in the
    first cut of this file. Blanket-removing every triple-quoted string (`re.sub(r'\"\"\".*?\"\"\"')`)
    deletes the SQL payloads too — every query in the instrument is a triple-quoted f-string. That
    left only the prose `note=` kwargs behind, so:
      · the LTZ guard could not fail (its subject had been deleted before matching), and
      · the `waits_real` guard passed off the sentence in a `note=`, i.e. the guard asserted its
        own documentation — the precise failure the stripping exists to prevent, inverted.
    Caught only because the deliberate break did NOT turn it red. Hence AST-scoped docstring
    removal: a docstring is the first statement of a module/class/function, which no SQL is.
    """
    # 1. Python comments via `tokenize`, NOT a regex. A regex cannot tell a `#` that starts a
    #    comment from one inside a string literal, and must choose between missing TRAILING
    #    comments (leaving prose able to satisfy a guard) or corrupting string payloads.
    #    Truncating at the comment token's start column handles both positions exactly.
    lines = src.splitlines()
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type == tokenize.COMMENT:
            row, col = tok.start
            lines[row - 1] = lines[row - 1][:col]
    src = "\n".join(lines)

    # 2. Docstrings via AST — the first statement of a module/class/function, which no SQL is.
    #    Line numbering is unchanged by step 1, and the source is still valid Python.
    drop: set[int] = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if ast.get_docstring(node, clean=False) is not None:
                first = node.body[0]
                drop.update(range(first.lineno, (first.end_lineno or first.lineno) + 1))
    src = "\n".join(
        "" if i + 1 in drop else ln for i, ln in enumerate(src.splitlines())
    )

    # 3. SQL `--` comments, which live INSIDE string literals and so are invisible to tokenize.
    #    Trailing form requires whitespace on both sides, so argparse flags
    #    (`ap.add_argument("--days"`) are untouched — that `--` follows a quote, not a space.
    src = re.sub(r"(?m)^\s*--.*$", "", src)
    src = re.sub(r"(?m)\s--\s.*$", "", src)
    return src


def _code() -> str:
    return _strip_comments(SCRIPT.read_text())


def _load():
    spec = importlib.util.spec_from_file_location("other_attribution", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_instrument_exists_and_is_import_safe():
    """It must import without a warehouse — the Snowflake import belongs inside main()."""
    assert SCRIPT.exists(), f"missing instrument: {SCRIPT}"
    mod = _load()
    assert callable(mod.base_cte)


# ---------------------------------------------------------------------------------------------
# GUARD 1 — the metadata-only filter
# ---------------------------------------------------------------------------------------------

def test_awake_time_cuts_filter_out_cloud_services_only_queries():
    """`base_cte` must exclude non-warehouse-occupying rows by default.

    Isolating fixture: the DEFAULT call. If the filter is dropped from the default branch this
    fails on its own, with no other clause able to mask it.
    """
    mod = _load()
    assert "warehouse_size is not null" in mod.base_cte("COMPUTE_WH", 6)


def test_the_filter_is_a_real_predicate_not_only_prose():
    """The literal must survive comment-stripping of the SOURCE.

    Without this, a session could delete the predicate and leave the explanatory comment, and
    the assertion above would still pass off the docstring in `OCCUPIES_WAREHOUSE`'s vicinity.
    """
    assert "warehouse_size is not null" in _code()


def test_the_filter_is_escapable_only_deliberately():
    """`occupying_only=False` must still be available — and must actually drop the filter.

    Table 0's reconciliation has to count EVERY row (including metadata-only ones) or it cannot
    cross-check against an unclassified total. A filter that could not be turned off would make
    the reconciliation vacuously self-consistent.
    """
    mod = _load()
    assert "warehouse_size is not null" not in mod.base_cte("COMPUTE_WH", 6, occupying_only=False)


def test_waits_are_never_silently_filtered_by_the_warehouse_size_predicate():
    """Table 1 must report waits BOTH ways, so the filter's harmlessness is proven, not assumed.

    A metadata query cannot queue on provisioning, so `waits == waits_real` on every row is the
    evidence the filter costs no wake signal. If the second column is dropped, the claim becomes
    an assertion about Snowflake internals with nothing backing it.
    """
    code = _code()
    assert "as waits_real" in code, (
        "Table 1 must SELECT the filtered wait count beside the raw one. Asserting on the bare\n"
        "token would be satisfiable by the explanatory `note=` prose; the SQL alias cannot be."
    )


# ---------------------------------------------------------------------------------------------
# GUARD 2 — no second copy of the classifier
# ---------------------------------------------------------------------------------------------

def test_family_case_is_imported_from_the_census_not_restated():
    code = _code()
    assert re.search(
        r"from\s+scripts\.report_e11_24_wake_census\s+import\s+[^\n]*FAMILY_CASE", code
    ), "FAMILY_CASE must be imported from the census so the two instruments cannot drift"


def test_the_attribution_script_defines_no_rival_family_case():
    """A local `FAMILY_CASE = ...` would shadow the import and silently fork the classifier."""
    assert not re.search(r"(?m)^\s*FAMILY_CASE\s*=", _code())


def test_both_scripts_agree_on_the_classifier_object():
    """Behavioural, not textual: literally the SAME object, so drift is impossible.

    ⚠️ The census must be imported the way the script imports it (`scripts.…`), NOT loaded by
    path: a by-path load builds a fresh module instance whose `FAMILY_CASE` is a distinct string
    object, so an identity check against it fails even when the code is correct. Reaching the
    real shared object is what makes `is` a legitimate assertion rather than a flaky one.
    """
    from scripts.report_e11_24_wake_census import FAMILY_CASE as census_case

    assert _load().FAMILY_CASE is census_case


# ---------------------------------------------------------------------------------------------
# GUARD 3 — the two read-discipline rules the story keeps re-learning
# ---------------------------------------------------------------------------------------------

def test_every_time_filter_is_a_dateadd_never_a_date_string_boundary():
    """LTZ boundary-day landmine: `start_time >= 'YYYY-MM-DD'` prunes ~7h off the first day."""
    code = _code()
    assert not re.search(r"(start_time|timestamp)\s*>=\s*'\d{4}-\d{2}-\d{2}", code), (
        "bound the window with dateadd() on a timestamp; a date-string boundary on a "
        "TIMESTAMP_LTZ column prunes in the session tz"
    )


@pytest.mark.parametrize("setting", ["timezone='UTC'", "STATEMENT_TIMEOUT_IN_SECONDS"])
def test_session_is_pinned_and_bounded(setting):
    """UTC pinning defends the LTZ landmine; a finite timeout is the INC-32 rule."""
    assert setting in _code()


# ---------------------------------------------------------------------------------------------
# GUARD 4 — a guard on the guard
# ---------------------------------------------------------------------------------------------

def test_comment_stripping_keeps_sql_and_drops_docstrings():
    """The stripper must delete DOCSTRINGS without deleting the SQL it is meant to inspect.

    This is the regression that made three assertions above vacuous in the first cut: a blanket
    triple-quote strip removed every query, so the guards matched prose or nothing at all. Pinned
    with a synthetic module carrying one token in a docstring and one in a triple-quoted SQL
    value — the two cases the naive implementation cannot tell apart.
    """
    sample = '\n'.join([
        '"""MODULE_DOCSTRING_TOKEN."""',
        'def f():',
        '    """FUNCTION_DOCSTRING_TOKEN."""',
        '    return """',
        '        select SQL_PAYLOAD_TOKEN from t  -- SQL_COMMENT_TOKEN',
        '    """',
        'X = "INLINE_STRING_TOKEN"  # HASH_COMMENT_TOKEN',
    ])
    out = _strip_comments(sample)
    assert "SQL_PAYLOAD_TOKEN" in out, "stripping must NOT delete triple-quoted SQL"
    assert "INLINE_STRING_TOKEN" in out
    for gone in ("MODULE_DOCSTRING_TOKEN", "FUNCTION_DOCSTRING_TOKEN",
                 "SQL_COMMENT_TOKEN", "HASH_COMMENT_TOKEN"):
        assert gone not in out, f"stripping must delete {gone}"
