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


def test_every_engine_module_the_backend_imports_is_in_the_deploy_zip():
    """⛔ THE COPY LIST IS THE CONTRACT.

    An import the zip does not carry is invisible everywhere except production, which is the same
    class as the gitignored artifacts NF-INFRA1/NF-K1 kept tripping over: the local checkout has
    the file, the deployed image does not, and the failure surfaces at the worst possible moment.
    """
    copied = _deploy_copied_modules()
    assert copied, "deploy.sh copies no engine modules — this clause would pass on nothing"
    imports = _backend_engine_imports()
    assert imports, (
        "no backend file imports quant_sports_intel_models — if that is now true on purpose, the "
        "deploy.sh copy step should go too; if not, this guard has stopped measuring anything"
    )
    problems = []
    for where, mods in imports.items():
        for mod in mods:
            leaf = mod.rsplit(".", 1)[-1]
            if mod == "quant_sports_intel_models.fantasy_engine":
                continue                       # the package itself, which deploy.sh always copies
            if not mod.startswith("quant_sports_intel_models.fantasy_engine."):
                problems.append(f"{where} imports {mod} — outside fantasy_engine entirely")
            elif leaf not in copied:
                problems.append(f"{where} imports {mod}, which deploy.sh does NOT copy ({sorted(copied)})")
    assert not problems, "\n  ".join(["the Lambda bundle would be missing an import:"] + problems)


def test_the_copied_modules_are_stdlib_only():
    """A carried module that grows a pandas import breaks the bundle just as surely as a missing
    one — and it would do it at the next `deploy.sh`, not at the next test run."""
    engine = REPO / "quant_sports_intel_models" / "fantasy_engine"
    for name in _deploy_copied_modules() | {"__init__"}:
        src = (engine / f"{name}.py").read_text()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module.split(".")[0]]
            for imported in names:
                assert imported not in HEAVY, (
                    f"fantasy_engine/{name}.py imports {imported!r}, which the API Lambda bundle "
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
