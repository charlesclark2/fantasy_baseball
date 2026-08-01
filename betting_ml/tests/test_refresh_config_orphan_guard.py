"""
test_refresh_config_orphan_guard.py  (E11.29 — dead *_TABLES/*_SOURCES refresh-config constant; fast gate)
============================================================================================================
E9.48 found `W7B_TABLES` was DEFINED in refresh_w1_external_tables.py but REFERENCED NOWHERE in the
refresh flow: the E9.48 fix carved the injury-chain members out into a new `W7B_INJURY_TABLES` constant
(wired into the daily refresh) but left the now-fully-redundant `W7B_TABLES` sitting in the file, unused,
undeleted. Its shape is silent (no error, no HALT) — a `*_TABLES`/`*_SOURCES` constant nobody reads means
whatever it lists never gets refreshed, so the derived Snowflake external table quietly rots while the S3
parquet underneath it keeps moving (the INC-25 "built but never refreshed" class). E11.29 audited every
refresh-config constant of this shape and found the same `W7B_TABLES` still sitting there, confirming the
class recurs even after a documented fix — hence this guard.

⚠️ THE TELL IS *USE*, NOT DEFINITION: grepping for a constant's definition always looks fine (it's right
there, with a comment explaining its purpose). The bug only shows up when you grep for where the NAME is
ACTUALLY READ — a `_refresh(NAME, ...)` call, a dict merge, a cross-module `module.NAME` attribute access,
an argparse branch. This test mechanizes that check with an AST scan (so a name mentioned only inside a
string literal or `#` comment — e.g. a docstring citing "refresh: ... (NAME)" — does NOT count as a use;
only an actual `ast.Name`/`ast.Attribute` reference does).

Any module-level `*_TABLES` / `*_SOURCES` constant (assigned a list/dict/set/tuple literal, optionally via
a `{**a, **b}` merge) under scripts/, pipeline/, or betting_ml/ must be referenced somewhere beyond its own
assignment. A constant that fails this check is either:
  (a) a genuine orphan — DELETE it (do not reflexively wire it into a refresh; that only makes sense if its
      tables are still consumed by something that isn't already refreshed elsewhere — audit before wiring), or
  (b) an intentional, already-documented, already-guarded historical/rollback artifact — add it to
      `_ALLOWLIST` below with a citation to why it's deliberately unused (e.g. `W1_TABLES`, which
      `test_delta_lakehouse_guard.py` explicitly asserts stays OUT of the daily refresh as part of the
      E11.20 phase-1.5 retirement).

Pure source-scan (AST only, no pipeline/snowflake import) — runs in the fast gate.
"""
import ast
import collections
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]

_SCAN_ROOTS = ["scripts", "pipeline", "betting_ml"]
_EXCLUDE_DIR_PARTS = {".venv", "node_modules", "__pycache__", ".git"}

# ── Allowlist ────────────────────────────────────────────────────────────────────────────────────
# (relative_path, constant_name) -> reason it's exempt from "must be referenced somewhere".
# Each entry must be a DELIBERATE, DOCUMENTED, already-guarded exception — not a shrug.
_ALLOWLIST = {
    ("scripts/refresh_w1_external_tables.py", "W1_TABLES"): (
        "E11.20 phase-1.5 retired the 7 mart_pitch_* Snowflake external tables/views on purpose "
        "(zero readers, confirmed). W1_TABLES is kept ONLY as the documented rollback table list "
        "(docs/e11_20_delta_rollout.md §6 — recreate via scripts/ddl/w1_external_tables.sql, set "
        "W1_SF_COMPAT_MIRROR=1, re-add here), and test_delta_lakehouse_guard.py explicitly asserts "
        "it stays OUT of the daily refresh. Its non-use is the guarded, intended state."
    ),
}


def _iter_py_files():
    for root in _SCAN_ROOTS:
        base = REPO / root
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            if any(part in _EXCLUDE_DIR_PARTS for part in path.parts):
                continue
            yield path


def _parse_all():
    parsed = {}
    for path in _iter_py_files():
        try:
            parsed[path] = ast.parse(path.read_text())
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
    return parsed


_PARSED = _parse_all()

_LITERAL_VALUE_NODES = (ast.List, ast.Dict, ast.Set, ast.Tuple, ast.BinOp)


def _find_refresh_config_constants():
    """Return [(relpath, name, lineno)] for every module-level `NAME = [...]`/`{...}` (or annotated
    equivalent) assignment whose NAME ends in _TABLES or _SOURCES."""
    found = []
    for path, tree in _PARSED.items():
        relpath = path.relative_to(REPO).as_posix()
        for node in tree.body:  # module level only
            if isinstance(node, ast.Assign):
                targets = node.targets
                value = node.value
            elif isinstance(node, ast.AnnAssign) and node.value is not None:
                targets = [node.target]
                value = node.value
            else:
                continue
            if not isinstance(value, _LITERAL_VALUE_NODES):
                continue
            for target in targets:
                if isinstance(target, ast.Name) and (
                    target.id.endswith("_TABLES") or target.id.endswith("_SOURCES")
                ):
                    found.append((relpath, target.id, node.lineno))
    return found


def _build_reference_index():
    """One pass over every parsed file, building per-file Counters of (a) `ast.Name` reads in
    Load context and (b) `ast.Attribute` reads by `.attr` name. A module-level assignment target
    is ast.Store context, never ast.Load, so a definition site is *never* counted as a read here
    -- no separate "exclude the def site" bookkeeping is needed. A name that only appears inside a
    string literal or `#` comment produces no AST node at all and is correctly never counted.

    Returns (global_counts, per_file_counts): global_counts sums every file's reads for O(1)
    lookup (the fast path for a constant name defined in exactly one file); per_file_counts keeps
    each file's reads separate, needed only for names whose CONSTANT is (re)defined identically in
    more than one file (e.g. W8A_TABLES exists in both refresh_w1_external_tables.py and
    parity_check_w8a.py as unrelated local constants) -- there, a global count could hide one
    definition being dead by crediting it with the OTHER file's real usage, so those names are
    checked file-locally instead."""
    global_counts = collections.Counter()
    per_file_counts = {}
    for path, tree in _PARSED.items():
        relpath = path.relative_to(REPO).as_posix()
        local = collections.Counter()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                local[node.id] += 1
            elif isinstance(node, ast.Attribute):
                local[node.attr] += 1
        per_file_counts[relpath] = local
        global_counts.update(local)
    return global_counts, per_file_counts


_CONSTANTS = _find_refresh_config_constants()
_GLOBAL_REF_COUNTS, _PER_FILE_REF_COUNTS = _build_reference_index()
_COLLIDING_NAMES = {
    name for name, n in collections.Counter(n for _, n, _ in _CONSTANTS).items() if n > 1
}


def _is_referenced(relpath, name):
    """True if `name`'s definition at `relpath` has at least one real (AST-level) read. For a
    name defined in only one file, a global hit is unambiguous. For a name defined in multiple
    files (a same-named-but-unrelated local constant in each), require a hit WITHIN that specific
    file, since a global count would be conflated across the colliding definitions."""
    if name in _COLLIDING_NAMES:
        return _PER_FILE_REF_COUNTS.get(relpath, {}).get(name, 0) > 0
    return _GLOBAL_REF_COUNTS.get(name, 0) > 0


@pytest.mark.parametrize(
    "relpath,name,lineno",
    _CONSTANTS,
    ids=[f"{r}::{n}" for r, n, _ in _CONSTANTS],
)
def test_refresh_config_constant_is_referenced(relpath, name, lineno):
    if (relpath, name) in _ALLOWLIST:
        pytest.skip(f"allowlisted: {_ALLOWLIST[(relpath, name)]}")
    assert _is_referenced(relpath, name), (
        f"{relpath}:{lineno} defines `{name}` but it is never actually READ anywhere in "
        f"{_SCAN_ROOTS} — this is the W7B_TABLES 'built-but-never-refreshed' class (E9.48/E11.29): "
        f"a refresh-config constant nobody consumes means whatever tables it lists never get "
        f"refreshed, silently (no error, no HALT). Resolve by EITHER (a) wiring it into its "
        f"driver's refresh flow if the tables are still consumed elsewhere and not already covered "
        f"by another wired constant, (b) deleting it if it's a genuine dead leftover (e.g. superseded "
        f"by a narrower constant, as W7B_TABLES was by W7B_INJURY_TABLES), or (c) adding it to "
        f"_ALLOWLIST in this file with a citation if it's a deliberate, documented, already-guarded "
        f"exception (like W1_TABLES)."
    )


def test_allowlist_entries_still_exist():
    """Keep the allowlist honest: an entry for a constant that no longer exists (renamed/deleted)
    is stale and should be removed."""
    found_keys = {(r, n) for r, n, _ in _CONSTANTS}
    for key in _ALLOWLIST:
        assert key in found_keys, (
            f"Allowlist entry {key} no longer matches any defined refresh-config constant in the "
            f"scanned surface — remove the stale entry from _ALLOWLIST in this file."
        )


def test_found_at_least_the_known_constants():
    """Sanity: the scan should find the well-known refresh-config constants this story audited —
    if this drops to zero, the scan itself is broken (wrong roots, AST changes, etc.), not proof
    the codebase has no more refresh configs."""
    names = {n for _, n, _ in _CONSTANTS}
    for expected in ("W2_TABLES", "W3_TABLES", "W7B_INJURY_TABLES", "W7B_SERVING_TABLES"):
        assert expected in names, (
            f"Expected refresh-config constant `{expected}` was not found by the scanner — "
            f"the scan's roots/logic may have regressed."
        )
