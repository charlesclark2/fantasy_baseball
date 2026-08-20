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
import functools
import sys
from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]

sys.path.insert(0, str(_REPO_ROOT / "scripts"))
import ci_shards  # noqa: E402  (needs the sys.path line above)
from ci_shards import (  # noqa: E402
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


# ── 3b. the slow/research TIER wiring — no test may fall out of BOTH jobs ────────────────────

class TestSlowResearchTierWiring:
    """TD2 tiering: `slow` splits fast-vs-slow; `research` splits the slow job into the REQUIRED
    merge bar (`slow and not research`) and the nightly non-blocking job (`research`).

    The failure mode this guards is silent coverage loss: if ci.yml's slow job stopped saying
    `and not research`, the tier would collapse; if the nightly workflow stopped selecting
    `-m research`, those tests would run NOWHERE while both gates still went green.
    """

    def test_required_slow_job_excludes_research(self):
        wf = yaml.safe_load(_CI_WORKFLOW.read_text())
        steps = wf["jobs"]["slow-tests"]["steps"]
        run = " ".join(s.get("run", "") for s in steps)
        assert "slow and not research" in run, (
            "ci.yml's slow job must select `-m 'slow and not research'` — without the exclusion "
            "the research harness tests are back on the required merge bar."
        )

    def test_nightly_workflow_runs_the_research_tier(self):
        nightly = _REPO_ROOT / ".github" / "workflows" / "research_tests.yml"
        assert nightly.exists(), (
            "research_tests.yml is missing — tests marked `research` are excluded from the "
            "required slow job, so without this workflow they would run NOWHERE."
        )
        wf = yaml.safe_load(nightly.read_text())
        run = " ".join(s.get("run", "") for s in wf["jobs"]["research-tests"]["steps"])
        assert "-m research" in run
        # `on:` parses as the boolean True in YAML 1.1 — check both spellings.
        triggers = wf.get("on", wf.get(True, {}))
        assert "schedule" in triggers, "the research tier must actually be scheduled"

    def test_research_is_a_subset_of_slow(self):
        """`research` only tiers the SLOW job. A fast test carrying `research` would still run in
        the fast gate, so the marker would be misleading — keep the two aligned."""
        src = {p: (_REPO_ROOT / p).read_text(errors="ignore") for p in _ALL_TEST_FILES}
        offenders = []
        for path, text in src.items():
            tree = ast.parse(text, filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                marks = {_dotted(d.func) if isinstance(d, ast.Call) else _dotted(d)
                         for d in node.decorator_list}
                if any(m.endswith("mark.research") for m in marks) and not any(
                    m.endswith("mark.slow") for m in marks
                ):
                    offenders.append(f"{path.as_posix()}::{node.name}")
        assert not offenders, (
            "test marked `research` but not `slow` — `research` only removes a test from the "
            f"REQUIRED SLOW job, so this one still runs in the fast gate: {offenders}"
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

class TestSlowGatePathScoping:
    """The slow gate is handed an explicit file list; these keep that from silently narrowing.

    ⚠️ THE FAILURE MODE IS A TEST THAT STOPS RUNNING WITHOUT ANYONE NOTICING. `-m "slow and not
    research"` remains the selector, but pytest can only select from what it IMPORTS, so a slow test
    in a file the scanner misses is deselected by absence — green gate, no signal, no error. The
    scan is therefore derived from the marker itself (AST, not grep) and pinned here.
    """

    def test_the_scanner_finds_the_files_that_carry_the_marker(self):
        """Anti-vacuity + a floor: an empty or collapsed list would make the gate run nothing."""
        files = {p.name for p in ci_shards.slow_files()}
        assert len(files) >= 10, f"the slow-file scan collapsed to {len(files)} files"
        # The three that dominate the gate's cost (measured 2026-08-20: 65% of it is the first two).
        for expected in ("test_mh2_6_calibration_audit.py", "test_mh2_10_morning_audit.py",
                         "test_totals_distribution.py"):
            assert expected in files, f"{expected} fell out of the slow gate's file list"

    @pytest.mark.parametrize(
        "form",
        [
            "@pytest.mark.slow\ndef test_x():\n    pass\n",
            "import pytest\npytestmark = pytest.mark.slow\ndef test_x():\n    pass\n",
            "import pytest\npytestmark = [pytest.mark.slow]\ndef test_x():\n    pass\n",
            "import pytest\n@pytest.mark.parametrize('a', [pytest.param(1, marks=pytest.mark.slow)])\n"
            "def test_x(a):\n    pass\n",
        ],
        ids=["decorator", "pytestmark", "pytestmark-list", "param-marks"],
    )
    def test_every_way_of_writing_the_marker_is_detected(self, tmp_path, form):
        """⭐ THE CLAUSE THAT MAKES THE SCAN SAFE TO RELY ON.

        A regex would have to enumerate these spellings; all four parse to the same attribute chain,
        so the AST check covers them uniformly. If a fifth form appears and is NOT detected, the
        file it lives in is handed to nobody and its slow tests stop running silently.
        """
        f = tmp_path / "test_form.py"
        f.write_text(form)
        assert ci_shards._uses_marker(f, ci_shards.SLOW_MARKER), (
            "a real way of writing the slow marker is invisible to the scanner"
        )

    def test_a_file_with_no_slow_marker_is_not_claimed(self):
        """The two-sided half — a scanner that returns True for everything is not a scanner."""
        assert not ci_shards._uses_marker(
            _REPO_ROOT / "scripts" / "ci_shards.py", ci_shards.SLOW_MARKER
        )

    def test_an_unparseable_file_is_handed_over_rather_than_dropped(self, tmp_path):
        """A syntax error must fail LOUDLY inside pytest, never vanish from the run."""
        f = tmp_path / "test_broken.py"
        f.write_text("def test_x(:\n")
        assert ci_shards._uses_marker(f, ci_shards.SLOW_MARKER)

    def test_the_workflow_actually_uses_the_scoped_list(self):
        """WIRED ≠ INVOKED (NF-C0e) — a flag nothing calls buys nothing.

        Comment lines are stripped first: the block above the step EXPLAINS `--slow-paths`, and a
        substring check would be satisfied by the prose while the command ran unscoped (INC-38).
        """
        ci = _CI_WORKFLOW.read_text()
        code = "\n".join(l for l in ci.splitlines() if not l.lstrip().startswith("#"))
        assert "ci_shards.py --slow-paths" in code, (
            "the slow gate is not using the scoped file list — collection is back to the whole suite"
        )
        assert '-m "slow and not research"' in code, "the slow gate lost its marker selector"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# TD4 — the `research` tier's own precondition, enforced rather than documented
# ══════════════════════════════════════════════════════════════════════════════════════════════
#: Every `research`-marked test file → the modules whose ABSENCE from the serving path is what
#: justified moving it off the merge bar. Declared by hand ON PURPOSE: a test imports many things
#: and only its SUBJECT matters, and no automatic rule can tell a subject from an incidental shared
#: util without either missing real subjects or firing on `data_loader`. The exhaustiveness check
#: below is what stops the hand-written half from rotting (INC-38: pin the registry, not just the
#: rule it serves).
RESEARCH_SUBJECTS: dict[str, tuple[str, ...]] = {
    # TD2 (2026-07-27) — the original four.
    "test_derivative_model_gate.py": ("betting_ml.utils.derivative_model_gate",),
    "test_line_microstructure.py": ("betting_ml.utils.line_microstructure",),
    "test_perside_bakeoff.py": ("betting_ml.scripts.totals_generative.bakeoff_perside",),
    "test_f5_distribution.py": (
        "betting_ml.utils.f5_distribution",
        "betting_ml.scripts.totals_generative.bakeoff_f5_perside",
    ),
    # TD4 (2026-08-20) — the §0.5 audit + bake-off harnesses. 183s of the slow gate's 256s of
    # serial CPU guarded modules NOTHING in production imports; they execute only when a human
    # deliberately runs an audit or a bake-off.
    "test_mh2_6_calibration_audit.py": ("betting_ml.scripts.mh2_6_calibration_audit",),
    "test_mh2_10_morning_audit.py": ("betting_ml.scripts.mh2_10_morning_audit",),
    "test_nf_w2_injury_availability.py": (
        "quant_sports_intel_models.football.nfl.fantasy.weekly_frame",
        "quant_sports_intel_models.football.nfl.fantasy.weekly_projection",
        "quant_sports_intel_models.football.nfl.fantasy.weekly_projection_w2",
    ),
    "test_nf_w6b_stat_distributions.py": (
        "quant_sports_intel_models.football.nfl.fantasy.stat_distributions",
        "quant_sports_intel_models.football.nfl.fantasy.efficiency_marginals",
        "quant_sports_intel_models.football.nfl.fantasy.margin_calibration",
        "quant_sports_intel_models.football.nfl.fantasy.run_nf_w6b_stat_distributions",
    ),
}

_SERVING_ROOTS = ("scripts", "app", "pipeline")


def _research_files() -> list[Path]:
    """Test files carrying a `research` marker.

    ⚠️ AST, NOT A SUBSTRING SCAN — and this file is the proof. A `"mark.research" in source` check
    matched THIS module, because the registry above quotes the marker in its own prose, so the
    guard reported itself as an unregistered research file. The AST sees an attribute chain and a
    docstring is not one.
    """
    return [p for p in _ALL_TEST_FILES
            if ci_shards._uses_marker(_REPO_ROOT / p, "research")]


@functools.lru_cache(maxsize=1)
def _serving_import_map() -> dict[str, list[str]]:
    """Every dotted module imported by anything under `scripts/`, `app/`, `pipeline/`.

    ⭐ AST, NOT STRING NEEDLES, AND THE RED PROOF IS WHY. The first cut matched
    `f"from {module} import"` and friends — which misses `from betting_ml.scripts import
    mh2_6_calibration_audit`, the form this repo actually uses and the exact form the research test
    files themselves are written in. The guard would have reported a rotted tier as healthy: the
    realistic defect was the one it could not see.

    ⚠️ AND NOT A BARE LEAF EITHER. Matching leaf names reports `betting_ml.scripts` as "imported by
    194 files" because it matches every sibling — measured, and it made a research-only module look
    live. Both failure modes are covered by breaks in `ci_research_tier_red_proof.py`.

    Built once and cached: the parametrized checks below are then set lookups rather than a rescan.
    """
    out: dict[str, list[str]] = {}
    for root in _SERVING_ROOTS:
        base = _REPO_ROOT / root
        if not base.exists():
            continue
        for py in base.rglob("*.py"):
            if "/tests/" in py.as_posix():
                continue
            try:
                tree = ast.parse(py.read_text(errors="ignore"))
            except SyntaxError:
                continue
            rel = py.relative_to(_REPO_ROOT).as_posix()
            for node in ast.walk(tree):
                names: list[str] = []
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                    # BOTH forms: `from pkg.mod import thing` AND `from pkg import mod`.
                    names = [node.module] + [f"{node.module}.{a.name}" for a in node.names]
                for n in names:
                    out.setdefault(n, []).append(rel)
    return {k: sorted(set(v)) for k, v in out.items()}


def _serving_importers(module: str) -> list[str]:
    """Serving/pipeline/API files importing this EXACT dotted module."""
    return _serving_import_map().get(module, [])


class TestResearchTierPrecondition:
    """A test leaves the merge bar ONLY while nothing in production imports what it guards.

    That rule has been prose in `research_tests.yml` since TD2 — *"mark `research` ONLY if its
    module under test has no importer under `scripts/`, `app/`, `pipeline/`"* — with nothing
    checking it. A module that LATER gains a serving importer keeps its nightly-only tier silently,
    and the first sign is a production break that a non-blocking job noticed hours earlier.

    This is the same shape as the depth-target defect this session shipped: a rule that held when it
    was written, no mechanism to notice when it stopped holding.
    """

    def test_every_research_file_declares_what_it_guards(self):
        """Exhaustiveness — the hand-written registry cannot silently omit a new research file."""
        found = {p.name for p in _research_files()}
        assert found, "no research-marked test files — the checks below would be vacuous"
        missing = found - set(RESEARCH_SUBJECTS)
        assert not missing, (
            f"research-marked file(s) not in RESEARCH_SUBJECTS: {sorted(missing)} — declare the "
            f"module(s) each one guards so the serving-importer check can cover it"
        )
        stale = set(RESEARCH_SUBJECTS) - found
        assert not stale, f"RESEARCH_SUBJECTS names non-research file(s): {sorted(stale)}"

    @pytest.mark.parametrize("test_file", sorted(RESEARCH_SUBJECTS))
    def test_no_research_module_has_gained_a_serving_importer(self, test_file):
        """⭐ THE POINT. If this goes red, the fix is to DROP the `research` marker from that file —
        in the same change that introduced the importer — not to edit this registry."""
        for module in RESEARCH_SUBJECTS[test_file]:
            importers = _serving_importers(module)
            assert not importers, (
                f"{module} is guarded ONLY by the nightly job, but production now imports it:\n"
                f"  " + "\n  ".join(importers) + f"\n"
                f"Remove @pytest.mark.research from {test_file} so it blocks a merge again."
            )

    def test_the_registered_modules_actually_exist(self):
        """A registry entry that names nothing checks nothing — the vacuous half of the clause
        above, since `_serving_importers` on a typo'd module trivially returns []."""
        for test_file, modules in RESEARCH_SUBJECTS.items():
            for module in modules:
                path = _REPO_ROOT / (module.replace(".", "/") + ".py")
                assert path.exists(), f"{test_file} registers {module}, which does not exist"
