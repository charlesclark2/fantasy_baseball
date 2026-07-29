"""test_fast_gate_hygiene.py — keep the sharded fast gate honest and xdist-safe.

CONTEXT (2026-07-27 CI-hygiene profile). The fast gate is the merge bar every session runs. It
was profiled at ~2,360 tests / ~90s serial, and the bottleneck turned out NOT to be slow tests
(the slowest single test is 4.5s, inside the `@slow` >5s rule) but per-worker COLLECTION — every
xdist worker imports all ~175 test modules before running its share. The fix was to SHARD the
gate by domain (scripts/ci_shards.py). Sharding is only safe if two properties hold, and this
file pins both:

  1. COVERAGE CANNOT SILENTLY ESCAPE. Splitting a suite across jobs introduces a brand-new
     failure mode the single-job gate never had: a test file that belongs to NO shard simply
     stops being run, and the merge bar goes green anyway. The shard map defends against this by
     construction (`core` is a computed catch-all), and these tests prove it — partition, no
     overlap, no empty shard, and the CI matrix listing every shard name.

  2. NO TEST MODULE MUTATES GLOBAL STATE AT IMPORT. pytest imports every collected module before
     running a single test, so a module-level `sys.modules[...] = MagicMock()` or
     `os.environ[...] = ...` leaks into every other test in that worker. That is what makes a
     test "passes in isolation, fails in the full run", and under xdist — where which tests
     share a worker varies per run — it becomes an outright flake. It also blocks sharding,
     because a test's result would depend on which shard it landed in.

Pure source/AST inspection: no IO, no `pipeline` import (the manifest is absent in the fast gate).
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]

sys.path.insert(0, str(_REPO_ROOT / "scripts"))
from ci_shards import (  # noqa: E402  (needs the sys.path line above)
    CATCH_ALL,
    SHARD_NAMES,
    _RULES,
    all_test_files,
    shard_of,
)

_CI_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "ci.yml"

# Resolved once at import — all_test_files() rglobs both test roots, and every check below needs
# the full list. Recomputing it per shard/per file made this guard an O(n²) 8-SECOND test, which
# would have violated the very >5s `@slow` rule it exists to protect.
_ALL_TEST_FILES: list[Path] = all_test_files()
_BY_SHARD: dict[str, list[Path]] = {s: [] for s in SHARD_NAMES}
for _f in _ALL_TEST_FILES:
    _BY_SHARD[shard_of(_f)].append(_f)


# ── 1. the shard map is a true partition — no test can escape the merge bar ──────────────────

class TestShardPartition:
    def test_every_test_file_lands_in_exactly_one_shard(self):
        assert _ALL_TEST_FILES, "found no test files at all — TEST_ROOTS is wrong"

        claimed: dict[Path, list[str]] = {
            f: [s for s, files in _BY_SHARD.items() if f in files] for f in _ALL_TEST_FILES
        }
        unclaimed = [f.as_posix() for f, s in claimed.items() if not s]
        doubled = {f.as_posix(): s for f, s in claimed.items() if len(s) > 1}
        assert not unclaimed, (
            "test file belongs to NO CI shard — it would silently stop being run by the merge "
            f"bar while CI still went green: {unclaimed}"
        )
        assert not doubled, f"test file claimed by MORE THAN ONE shard (wasted CI time): {doubled}"

    def test_union_of_shards_is_the_whole_suite(self):
        union = {f for files in _BY_SHARD.values() for f in files}
        assert union == set(_ALL_TEST_FILES)

    def test_no_shard_is_empty(self):
        """An empty shard makes `ci_shards.py --shard X` exit non-zero in CI (by design — an
        empty target list would make pytest fall back to testpaths and re-run everything)."""
        empty = [s for s, files in _BY_SHARD.items() if not files]
        assert not empty, f"shard(s) match no files — the rules are stale: {empty}"

    def test_every_declared_prefix_still_claims_a_file(self):
        """A prefix that matches nothing is a rotted rule — usually a renamed/deleted test, or a
        prefix shadowed by an earlier shard. Harmless to CI but it hides real drift, and a
        shadowed prefix means a file is silently in a different shard than the author intended."""
        dead = []
        for shard, prefixes in _RULES:
            owned = _BY_SHARD[shard]
            for prefix in prefixes:
                if not any(f.name.startswith(prefix) for f in owned):
                    dead.append(f"{shard}:{prefix}")
        assert not dead, (
            "shard prefix claims no file for its own shard (renamed/deleted test, or shadowed by "
            f"an earlier shard's rule — delete or reorder it): {dead}"
        )

    def test_catch_all_is_last_resort_only(self):
        """`core` must never be given explicit rules — it is defined as the remainder, which is
        exactly what guarantees a new test file cannot escape the gate."""
        assert CATCH_ALL not in {shard for shard, _ in _RULES}


# ── 2. the CI matrix runs every shard ────────────────────────────────────────────────────────

class TestCIWorkflowMatchesShardMap:
    def test_matrix_lists_exactly_the_shard_names(self):
        wf = yaml.safe_load(_CI_WORKFLOW.read_text())
        matrix = wf["jobs"]["unit-tests-shard"]["strategy"]["matrix"]["shard"]
        assert sorted(matrix) == sorted(SHARD_NAMES), (
            "ci.yml's fast-gate matrix has drifted from SHARD_NAMES — a shard missing from the "
            f"matrix is NEVER RUN. matrix={sorted(matrix)} shards={sorted(SHARD_NAMES)}"
        )

    def test_required_status_check_name_is_preserved(self):
        """`Unit Tests (fast gate)` is a REQUIRED check in branch protection. If the roll-up job
        is renamed, that check never reports and every PR blocks on a pending gate."""
        wf = yaml.safe_load(_CI_WORKFLOW.read_text())
        assert wf["jobs"]["unit-tests"]["name"] == "Unit Tests (fast gate)"
        assert "unit-tests-shard" in wf["jobs"]["unit-tests"]["needs"]

    def test_shards_do_not_fail_fast(self):
        """fail-fast would cancel sibling shards on the first red one, hiding failures in other
        domains and making the gate report an incomplete picture."""
        wf = yaml.safe_load(_CI_WORKFLOW.read_text())
        assert wf["jobs"]["unit-tests-shard"]["strategy"]["fail-fast"] is False


# ── 3. no test module mutates global interpreter state at IMPORT time ────────────────────────

# The shared, restore-on-exit loader is the sanctioned way to stub heavy imports for a
# by-path module load (betting_ml/tests/_serving_store_loader.py).
_MUTABLE_GLOBALS = {
    ("sys", "modules"): "sys.modules",
    ("os", "environ"): "os.environ",
}
_BANNED_CALLS = {
    "os.chdir": "changes the process CWD for every later test",
    "os.environ.setdefault": "leaks an env var into every later test",
    "os.environ.update": "leaks env vars into every later test",
    "os.environ.pop": "removes an env var for every later test",
}


def _module_level_nodes(tree: ast.Module):
    """Yield statements that execute at IMPORT time.

    Descends into try/if/with/for/while bodies (they run on import) but NOT into function or
    class bodies (they only run when called / are safely scoped)."""
    stack = list(tree.body)
    while stack:
        node = stack.pop()
        yield node
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        for field in ("body", "orelse", "finalbody", "handlers"):
            stack.extend(getattr(node, field, []) or [])


def _dotted(node: ast.AST) -> str:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def _import_time_violations(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(errors="ignore"), filename=str(path))
    out = []
    for node in _module_level_nodes(tree):
        # `sys.modules[x] = ...` / `os.environ[x] = ...` / `del sys.modules[x]`
        targets = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
            targets = [node.target]
        elif isinstance(node, ast.Delete):
            targets = node.targets
        for t in targets:
            if isinstance(t, ast.Subscript) and isinstance(t.value, ast.Attribute):
                key = (_dotted(t.value.value), t.value.attr)
                if key in _MUTABLE_GLOBALS:
                    out.append(f"line {node.lineno}: mutates {_MUTABLE_GLOBALS[key]} at import")
        # banned module-level calls
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            name = _dotted(node.value.func)
            if name in _BANNED_CALLS:
                out.append(f"line {node.lineno}: calls {name}() at import — {_BANNED_CALLS[name]}")
    return out


@pytest.mark.parametrize("test_file", _ALL_TEST_FILES, ids=lambda p: p.name)
def test_module_does_not_mutate_global_state_at_import(test_file: Path):
    violations = _import_time_violations(_REPO_ROOT / test_file)
    assert not violations, (
        f"{test_file.as_posix()} mutates global interpreter state while being IMPORTED. pytest "
        "imports every test module during collection, before any test runs, so this leaks into "
        "every other test in the same worker — the classic 'passes alone, fails in the full run' "
        "flake, and under xdist it becomes non-deterministic because which tests share a worker "
        "varies per run. It also makes the suite unsafe to shard.\n"
        "  FIX: do it inside a fixture/test with `monkeypatch` (auto-reverted), or — for a "
        "by-path module load that needs heavy imports stubbed — use the restore-on-exit helper "
        "betting_ml/tests/_serving_store_loader.py.\n"
        "  " + "\n  ".join(violations)
    )


# ── 4. the pipeline-import env contract belongs to conftest, not to a test module ────────────

def test_conftest_supplies_the_dummy_snowflake_env():
    """`pipeline/resources` reads os.environ["SNOWFLAKE_ACCOUNT"] etc. at IMPORT (bracket access),
    so any test that imports `pipeline` needs them present. The root conftest sets them in
    pytest_configure — once per process, before collection, so the guarantee does not depend on
    filename order.

    REGRESSION PIN (2026-07-27): these defaults previously lived at module scope in
    test_e11_1_w12_sensor_fire.py, which sorts before test_monitor_health_wiring.py, so that
    module's env LEAK was silently what made the other module's `import pipeline` succeed.
    Properly scoping the leak away broke the slow gate (the only job that builds the dbt manifest
    and therefore actually reaches the import). Asserting it here means deleting the conftest
    block fails the FAST gate in seconds, instead of the slow job discovering it minutes later.
    """
    import os

    missing = [
        v for v in ("SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER", "SNOWFLAKE_WAREHOUSE", "SNOWFLAKE_ROLE")
        if not os.environ.get(v)
    ]
    assert not missing, (
        f"{missing} unset during the test session — importing `pipeline` will KeyError. Restore "
        "the os.environ.setdefault block in the root conftest.py's pytest_configure."
    )


# ── 5. importing a module must not do NETWORK IO ─────────────────────────────────────────────

def test_predict_today_does_not_fetch_the_calibrator_at_import():
    """Regression guard for the 2026-07-27 finding: `scripts/predict_today.py` ran
    `_calibrator = _load_calibrator()` at MODULE level, which fires a REAL S3 GET. Eleven test
    modules import predict_today, so every xdist worker paid a network round-trip during
    collection — in a suite whose whole premise is that external IO is mocked. The loader is now
    lazy + memoized (`_calibrator()`), so scoring behaviour is identical but importing is free.
    """
    src = (_REPO_ROOT / "scripts" / "predict_today.py").read_text()
    tree = ast.parse(src)
    eager = [
        node.lineno
        for node in tree.body
        if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Call)
        and _dotted(node.value.func) == "_load_calibrator"
    ]
    assert not eager, (
        "scripts/predict_today.py calls _load_calibrator() at module scope (line(s) "
        f"{eager}) — that is an S3 fetch on IMPORT, paid by every pytest worker and by anything "
        "that merely imports this module. Keep it behind the memoized _calibrator() accessor."
    )
