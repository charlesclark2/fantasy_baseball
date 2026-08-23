"""NF-C-LDA-1 — the API Lambda may import the draft optimizer, and NOTHING ELSE it does not carry.

The live-draft assistant runs `fantasy_engine.draft.recommend` inside the API Lambda so the
extension gets the SAME ranking the web app produces. That is only possible because two things
hold, and both are the kind that decay silently:

  1. ⭐ `fantasy_engine.draft` IS STDLIB-ONLY, INCLUDING ITS PACKAGE `__init__`. It used to be
     unimportable without pandas — not because of anything in `draft.py`, but because Python runs a
     package's `__init__` before its submodule and that `__init__` eagerly re-exported `scoring`
     and `vor`. Exactly the transitive module-scope import the PERF audit found in this same Lambda
     (`snowflake.connector` → pandas → pyarrow on EVERY cold start, −21.8% once lazied), reappearing
     through a package's front door.

  2. ⛔ THE DEPLOY ZIP CARRIES ONLY WHAT `deploy.sh` COPIES. The bundle has no
     `quant_sports_intel_models` install and already sits near the size cap, so `deploy.sh` lifts
     three stdlib-only modules the way it already lifts `betting_ml/utils/game_day.py`. A backend
     import of any OTHER module resolves fine locally, passes every test, and
     `ModuleNotFoundError`s in prod — CI mocks IO, but nothing mocks the zip.

⚠️ THE PANDAS CLAUSE RUNS IN A SUBPROCESS. In-process it would be VACUOUS: pytest itself has
already imported pandas, so `"pandas" in sys.modules` is true before the test body starts and the
assertion would be about the TEST RUNNER rather than about the import under test. Same shape as
`test_api_cold_start_imports.py`, for the same reason.

⛔ ANCHORED IN ITS OWN CLAUSE (E9.60).
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
import textwrap
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / "app" / "backend"
DEPLOY = REPO / "infrastructure" / "lambda" / "deploy.sh"

HEAVY = ("pandas", "numpy", "pyarrow", "scipy", "sklearn", "duckdb")


def _deploy_copied_modules() -> set[str]:
    """The `fantasy_engine` modules `deploy.sh` step 3c puts in the zip."""
    body = DEPLOY.read_text()
    m = re.search(r"for _m in ([^;]+); do", body)
    assert m, "deploy.sh no longer copies a fantasy_engine module list — step 3c is gone"
    return {name for name in m.group(1).split() if name != "__init__"}


def _run_copy_section(pkg: Path) -> None:
    """Execute `deploy.sh`'s copy steps for real into `pkg`. Raises with the operator's own output.

    Shared by the clauses below so each one measures the SAME tree a deploy produces, rather than
    re-implementing shell quoting / `${_m}` expansion / `[ -f … ] &&` in a regex (this file's own
    argument for executing the section instead of parsing it).
    """
    script = "set -euo pipefail\nPACKAGE_DIR=" + str(pkg) + "\n" + _copy_section()
    run = subprocess.run(["bash", "-c", script], cwd=REPO, capture_output=True, text=True,
                         timeout=120)
    assert run.returncode == 0, (
        "deploy.sh's copy steps FAILED — this is exactly what an operator sees on a real deploy:\n"
        f"{run.stdout}\n{run.stderr}"
    )


def _deploy_copied_dotted_modules(pkg: Path) -> set[str]:
    """Every `quant_sports_intel_models.*` module the deploy zip ACTUALLY carries, dotted.

    ⭐ MEASURED, NOT PARSED, and generalised from one hard-coded package to the whole tree. The
    previous reading of "is this import in the zip?" was `mod.startswith("…fantasy_engine.")` — i.e.
    the ANSWER was hard-coded to the only package step 3c copied, so a second copy step (3d's
    `projection_coherence`, NF-INJ1-C) would be reported as "outside fantasy_engine entirely" while
    sitting in the zip. The PROPERTY this clause defends is unchanged — every engine module the
    backend imports must be in the bundle — so what is generalised is how the bundle's contents are
    read, not what is required of them (⛔ the E9.60 rule: re-anchor an existing property onto a new
    implementation; never graft a new story's requirement into an old story's clause).
    """
    _run_copy_section(pkg)
    root = pkg / "quant_sports_intel_models"
    assert root.is_dir(), "the deploy copied no quant_sports_intel_models tree at all"
    out = {
        ".".join(path.relative_to(pkg).with_suffix("").parts)
        for path in root.rglob("*.py")
        if path.name != "__init__.py"
    }
    assert out, "the deploy tree carries no importable modules — the clauses below would pass on nothing"
    return out


def _backend_engine_imports() -> dict[str, set[str]]:
    """`{file: {module, …}}` — every `quant_sports_intel_models.*` module the backend imports.

    ⭐ AST, NOT grep. `app/backend/models/fantasy.py` and `services/league_scoring.py` both DISCUSS
    `quant_sports_intel_models` in prose (they document why they do NOT import it), so a text scan
    reports the opposite of the truth — the NF-C0e lesson, where a module's own docstring naming a
    forbidden import false-matched the guard written to forbid it.
    """
    found: dict[str, set[str]] = {}
    for path in BACKEND.rglob("*.py"):
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:  # pragma: no cover
            continue
        mods: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("quant_sports_intel_models"):
                        mods.add(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith("quant_sports_intel_models"):
                    mods.add(node.module)
        if mods:
            found[str(path.relative_to(REPO))] = mods
    return found


def test_the_draft_optimizer_imports_without_pandas():
    """⭐ THE PROPERTY THE WHOLE ENDPOINT RESTS ON, measured in a clean interpreter."""
    code = textwrap.dedent(
        """
        import sys, json
        import quant_sports_intel_models.fantasy_engine.draft as d
        import quant_sports_intel_models.fantasy_engine.league_config as lc
        print(json.dumps({
            "heavy": sorted(m for m in %r if m in sys.modules),
            "recommend": callable(d.recommend),
            "config": hasattr(lc.LeagueConfig, "from_dict"),
        }))
        """
        % (HEAVY,)
    )
    run = subprocess.run([sys.executable, "-c", code], cwd=REPO, capture_output=True, text=True,
                         timeout=180)
    assert run.returncode == 0, f"the import itself failed:\n{run.stderr[-2000:]}"
    import json as _json

    out = _json.loads(run.stdout.strip().splitlines()[-1])
    # ⚠️ NON-VACUITY FIRST: a crashed import also has no pandas loaded, so "no heavy module" is only
    # meaningful once we know the module actually came up and is usable.
    assert out["recommend"], "fantasy_engine.draft imported but exposes no `recommend`"
    assert out["config"], "league_config imported but exposes no `LeagueConfig.from_dict`"
    assert out["heavy"] == [], (
        f"importing the draft optimizer pulled in {out['heavy']}. The API Lambda carries none of "
        "these, so the live-draft endpoint would ModuleNotFoundError in prod while passing here. "
        "Check `fantasy_engine/__init__.py` — an EAGER re-export is how this breaks."
    )


def test_the_lazy_package_still_resolves_every_public_name():
    """Laziness must be invisible to callers, or it is a breaking change wearing a perf costume."""
    code = textwrap.dedent(
        """
        import json
        import quant_sports_intel_models.fantasy_engine as fe
        names = [n for n in fe.__all__]
        missing = [n for n in names if not hasattr(fe, n)]
        print(json.dumps({"n": len(names), "missing": missing}))
        """
    )
    run = subprocess.run([sys.executable, "-c", code], cwd=REPO, capture_output=True, text=True,
                         timeout=180)
    assert run.returncode == 0, run.stderr[-2000:]
    import json as _json

    out = _json.loads(run.stdout.strip().splitlines()[-1])
    assert out["n"] > 20, "the package exports almost nothing — the clause below proves little"
    assert out["missing"] == [], f"__all__ names that no longer resolve: {out['missing']}"


def test_every_engine_module_the_backend_imports_is_in_the_deploy_zip(tmp_path):
    """⛔ THE COPY LIST IS THE CONTRACT.

    An import the zip does not carry is invisible everywhere except production, which is the same
    class as the gitignored artifacts NF-INFRA1/NF-K1 kept tripping over: the local checkout has
    the file, the deployed image does not, and the failure surfaces at the worst possible moment.
    """
    copied = _deploy_copied_dotted_modules(tmp_path / "package")
    imports = _backend_engine_imports()
    assert imports, (
        "no backend file imports quant_sports_intel_models — if that is now true on purpose, the "
        "deploy.sh copy step should go too; if not, this guard has stopped measuring anything"
    )
    #: Packages, not modules — importing one only needs the DIRECTORY (a PEP 420 namespace) or its
    #: own `__init__.py`, both of which the copy steps create. Derived from what was copied rather
    #: than listed, so a new copied package needs no edit here.
    packages = {mod.rsplit(".", 1)[0] for mod in copied} | {"quant_sports_intel_models"}
    problems = []
    for where, mods in imports.items():
        for mod in mods:
            if mod in copied or mod in packages:
                continue
            problems.append(
                f"{where} imports {mod}, which deploy.sh does NOT copy into the zip "
                f"(it carries {sorted(copied)})"
            )
    assert not problems, "\n  ".join(["the Lambda bundle would be missing an import:"] + problems)


def test_the_copied_modules_are_stdlib_only(tmp_path):
    """A carried module that grows a pandas import breaks the bundle just as surely as a missing
    one — and it would do it at the next `deploy.sh`, not at the next test run.

    ⚠️ MODULE SCOPE ONLY, deliberately. `projection_coherence.frame_rows` imports pandas INSIDE the
    function (it is the build-frame reducer, which the Lambda never calls); a nested import costs
    the bundle nothing, and forbidding it would refuse a module that imports correctly there.
    """
    pkg = tmp_path / "package"
    for name in sorted(_deploy_copied_dotted_modules(pkg) | {"quant_sports_intel_models.fantasy_engine.__init__"}):
        src = (pkg / Path(*name.split("."))).with_suffix(".py").read_text()
        tree = ast.parse(src)
        for node in tree.body:                 # module scope only — see the docstring
            names = []
            if isinstance(node, ast.Import):
                names = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module.split(".")[0]]
            for imported in names:
                assert imported not in HEAVY, (
                    f"{name} imports {imported!r} at module scope, which the API Lambda bundle "
                    "does not carry"
                )


def test_the_endpoint_imports_the_engine_lazily():
    """A module-scope import here would put the optimizer on EVERY route's cold-start path for the
    sake of one endpoint — the exact defect the PERF audit measured and fixed in this Lambda."""
    for rel in ("services/draft_assistant.py", "routers/fantasy.py"):
        tree = ast.parse((BACKEND / rel).read_text())
        for node in tree.body:                 # module scope only
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                mod = getattr(node, "module", None) or ""
                names = [a.name for a in node.names] if isinstance(node, ast.Import) else []
                assert not mod.startswith("quant_sports_intel_models"), (
                    f"{rel} imports {mod} at MODULE scope"
                )
                assert not any(n.startswith("quant_sports_intel_models") for n in names), (
                    f"{rel} imports the engine at MODULE scope"
                )


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The copy steps must actually RUN — the clause that was missing
# ══════════════════════════════════════════════════════════════════════════════════════════════
#
# 🔴 THE DEFECT THIS EXISTS FOR (2026-08-19, caught by the operator on the first real deploy).
# Everything above checked the copy LIST — that it names the modules the backend imports, and that
# those modules are stdlib-only. Nothing checked that the paths `deploy.sh` copies EXIST, so step 3c
# shipped with `cp quant_sports_intel_models/__init__.py`, a file that does not exist:
# `quant_sports_intel_models` is a PEP 420 NAMESPACE package. `set -euo pipefail` aborted the deploy
# at `cp: No such file or directory` — the safe direction, nothing was uploaded — but the endpoint
# could not ship until someone hit it by hand.
#
# It got there because the check was written against the file's absence with `cat … 2>/dev/null`,
# which prints nothing for an EMPTY file and nothing for a MISSING one. The two are
# indistinguishable at the point of measurement, and the wrong reading was the plausible one. Same
# family as every "a check that could not run is not a check that passed" lesson, one level down: a
# MEASUREMENT whose two outcomes look identical is not a measurement (NF1.7(a)).
#
# ⭐ SO THIS RUNS THE REAL COPY STEPS instead of parsing them. A regex over `cp` lines would have to
# re-implement shell quoting, `${_m}` expansion and the `[ -f … ] &&` guards — i.e. it would be a
# second, weaker copy of bash. Executing the section fails in EXACTLY the way the deploy failed.
_SECTION_START = "# ── 3b."
_SECTION_END = "# ── 4."


def _copy_section() -> str:
    body = DEPLOY.read_text()
    start, end = body.index(_SECTION_START), body.index(_SECTION_END)
    assert start < end, "deploy.sh's copy steps are no longer between markers 3b and 4"
    return body[start:end]


def test_the_deploy_copy_steps_only_copy(tmp_path):
    """⚠️ NON-VACUITY + SAFETY, BEFORE EXECUTING ANYTHING. The clause below runs this shell for
    real, so it must first be true that the section is nothing but directory creation and copying —
    otherwise a future edit could make this test execute something surprising, and a section that
    had shrunk to nothing would make the execution clause pass on no work at all."""
    # ⚠️ LOGICAL commands, not physical lines: a `cp src \\\n   dst` spans two lines, and judging
    # the second one on its own reads the DESTINATION as a command of its own. (Caught by this
    # clause failing on the real script — which is the shape a safety check should fail in.)
    section = _copy_section().replace("\\\n", " ")
    commands = [
        line.strip() for line in section.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    assert commands, "deploy.sh's copy section is empty — the clause below would run nothing"
    assert sum(1 for c in commands if c.startswith("cp ") or " cp " in c) >= 4, (
        f"expected several cp lines, found: {commands}"
    )
    allowed = ("cp ", "mkdir ", "echo ", "for ", "done", "[ -f")
    for c in commands:
        assert any(c.startswith(a) for a in allowed), (
            f"deploy.sh's copy section runs {c!r}, which is not a copy — this test executes this "
            "section, so it may only ever create directories and copy files"
        )


def test_every_path_the_deploy_copies_actually_exists(tmp_path):
    """Run `deploy.sh`'s copy steps for real against a throwaway PACKAGE_DIR.

    ⭐ AND THEN IMPORT OUT OF THE RESULT. Copying successfully is necessary but not sufficient: the
    question the deploy is really asking is whether the RESULTING TREE can serve the endpoint. So
    the tree is imported from in a clean interpreter with only that directory on `sys.path`, which
    also pins the namespace-package resolution the fix relies on (there is no
    `quant_sports_intel_models/__init__.py`, and there must not be one).
    """
    pkg = tmp_path / "package"
    pkg.mkdir()
    script = "set -euo pipefail\nPACKAGE_DIR=" + str(pkg) + "\n" + _copy_section()
    run = subprocess.run(["bash", "-c", script], cwd=REPO, capture_output=True, text=True,
                         timeout=120)
    assert run.returncode == 0, (
        "deploy.sh's copy steps FAILED — this is exactly what an operator sees on a real deploy:\n"
        f"{run.stdout}\n{run.stderr}"
    )

    engine = pkg / "quant_sports_intel_models" / "fantasy_engine"
    assert engine.is_dir(), "the engine directory was not created"
    for name in _deploy_copied_modules() | {"__init__"}:
        assert (engine / f"{name}.py").is_file(), f"{name}.py did not reach the package"
    assert not (pkg / "quant_sports_intel_models" / "__init__.py").exists(), (
        "an `__init__.py` was generated for the namespace package — the deployed tree would then "
        "differ from the tree every test imports through (deploy.sh step 3c says why)"
    )

    code = textwrap.dedent(
        """
        import json, sys
        import quant_sports_intel_models as q
        import quant_sports_intel_models.fantasy_engine.draft as d
        from quant_sports_intel_models.fantasy_engine.league_config import LeagueConfig
        print(json.dumps({
            "from_package": d.__file__.startswith(sys.argv[1]),
            "recommend": callable(d.recommend),
            "config": hasattr(LeagueConfig, "from_dict"),
            "namespace": getattr(q, "__file__", None) is None,
            "heavy": sorted(m for m in %r if m in sys.modules),
        }))
        """
        % (HEAVY,)
    )
    # ⛔ cwd OUTSIDE the repo and PYTHONPATH set to the package alone, or the import would resolve
    # against the checkout and prove nothing about what was copied.
    proved = subprocess.run(
        [sys.executable, "-c", code, str(pkg)],
        cwd=tmp_path, capture_output=True, text=True, timeout=180,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(pkg), "HOME": str(tmp_path)},
    )
    assert proved.returncode == 0, f"the copied tree does not import:\n{proved.stderr[-2000:]}"
    import json as _json

    out = _json.loads(proved.stdout.strip().splitlines()[-1])
    assert out["from_package"], "the import resolved somewhere other than the copied package"
    assert out["recommend"] and out["config"], "the copied engine is not usable"
    assert out["namespace"], "the copied tree is not a namespace package"
    assert out["heavy"] == [], f"the copied tree pulls in {out['heavy']}"
