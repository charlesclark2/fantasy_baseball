"""PERF (2026-08-11) — the API Lambda's COLD START must not import pandas/pyarrow/snowflake.

WHY THIS EXISTS. `/fantasy/import` measured 5.4 s on a PR-preview trace. Re-measured on the
deployed function, the handler is not slow at all — CloudWatch over 7 days: 8,399 invocations,
warm p50 **88 ms**, but 541 cold starts whose **init averaged 3,976 ms** (p50 4,023 / max 5,130).
The page fans out three authenticated reads at mount, so on an idle function each one can land on
its own cold container and pay that 4 s independently. The load time was init, not queries.

Init was dominated by one import chain: `main.py` imports every router to register it →
`routers/{admin,finances,pipeline}.py` imported `services/snowflake.py` at module scope →
`snowflake.connector` → `snowflake.connector.options` → **pandas** → **pyarrow**. Measured locally,
`routers.admin` alone was 595 ms of a 1,383 ms import, 466 ms of it this chain; making it lazy drops
`sys.modules` from 2,218 to 1,594 (−624) and the import from ~996 ms to ~769 ms. On Lambda the win
is larger than that ratio suggests — init there runs on a COLD filesystem at 512 MB (~0.3 vCPU), and
pandas/pyarrow are exactly the large C extensions that punishes.

⭐ THIS RESTORES AN INVARIANT THE REPO ALREADY BELIEVED IT HAD. `services/fantasy_import_telemetry.py`
documents "no pandas/pyarrow in this Lambda" — that was untrue, silently, through a transitive import
nobody was looking at. Snowflake is never supposed to be on a request path (repo rule), and it was
not: the three routers that use it are admin/ops surfaces. It was on the IMPORT path, which is worse,
because every caller pays it and no endpoint mentions it.

⛔ THE FAILURE THIS PREVENTS IS SILENT. A new module-scope `import pandas` (or a router importing
`services.snowflake` at module scope again) adds seconds to every cold start for every user, returns
correct results, raises nothing, and no other test notices. The only signal is a latency number
nobody is watching.

Both tests are independently RED-provable against the pre-fix source (verified: restoring the
module-scope import in `services/snowflake.py` fails both).
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SNOWFLAKE_SERVICE = REPO_ROOT / "app" / "backend" / "services" / "snowflake.py"

# Heavy third-party roots that must never be pulled in merely by importing the ASGI app.
# `snowflake.connector` is the entry point; pandas and pyarrow are what it drags behind it.
FORBIDDEN_AT_IMPORT = ("pandas", "pyarrow", "snowflake.connector")


def _import_app_in_subprocess() -> dict:
    """Import `app.backend.main` in a clean interpreter and report what landed in `sys.modules`.

    A SUBPROCESS is required, not a convenience: pytest's own session imports pandas via other test
    modules, so asking this question in-process would answer it about the test runner rather than
    about the Lambda. The child starts from a bare interpreter, exactly as Lambda's init does.
    """
    probe = (
        "import json, sys\n"
        "import app.backend.main\n"
        "print(json.dumps({\n"
        "    'loaded': sorted(m for m in sys.modules if m in %r),\n"
        "    'module_count': len(sys.modules),\n"
        "    'app_imported': 'app.backend.main' in sys.modules,\n"
        "    'route_count': len(app.backend.main.app.routes),\n"
        "}))\n" % (FORBIDDEN_AT_IMPORT,)
    )
    proc = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=180,
    )
    if proc.returncode != 0:
        pytest.skip(
            "could not import app.backend.main in a subprocess "
            f"(rc={proc.returncode}); backend deps unavailable in this environment.\n"
            f"stderr tail: {proc.stderr[-600:]}"
        )
    # The probe prints exactly one JSON line; anything the app logged goes to stderr.
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_importing_the_api_does_not_load_pandas_pyarrow_or_snowflake():
    """Importing the ASGI app must not pull the heavy analytics stack into a cold start."""
    result = _import_app_in_subprocess()

    # ── NON-VACUITY, FIRST ────────────────────────────────────────────────────────────────────
    # "pandas is absent" is also what a CRASHED import looks like. Prove the app really loaded
    # before reading anything into the absence (NF1.7 (a) — a check that did not run is not a pass).
    assert result["app_imported"], "the probe did not actually import app.backend.main"
    assert result["route_count"] > 50, (
        f"only {result['route_count']} routes registered — the app did not build, so the "
        "absence of pandas below would be measuring a broken import, not a lean one"
    )

    assert result["loaded"] == [], (
        f"importing app.backend.main pulled {result['loaded']} into sys.modules. "
        "Every one of these is paid on EVERY Lambda cold start (init p50 ~4 s at 512 MB) by every "
        "caller, including anonymous ones. Import them inside the function that needs them — see "
        "app/backend/services/snowflake.py's module docstring."
    )


def test_the_snowflake_service_has_no_module_scope_heavy_import():
    """`services/snowflake.py` must keep `snowflake.connector` off its module scope.

    Parsed with `ast`, deliberately, rather than grepped. The module's own docstring names
    `snowflake.connector` while telling you not to import it there, and the lazy imports carry
    explanatory comments — a text search matches all of that and would pass on prose (the INC-38
    "a guard a comment can satisfy" class). The AST sees only real statements.

    A `TYPE_CHECKING`-guarded import is nested inside an `If` and therefore correctly ignored: it
    never executes at runtime, which is the whole point of keeping the annotation resolvable.
    """
    tree = ast.parse(SNOWFLAKE_SERVICE.read_text())

    module_scope_imports: list[str] = []
    for node in tree.body:  # DIRECT children only — nested/guarded imports do not run at import
        if isinstance(node, ast.Import):
            module_scope_imports.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            module_scope_imports.append(node.module)

    offenders = [
        name
        for name in module_scope_imports
        if name.split(".")[0] in {"snowflake", "pandas", "pyarrow", "cryptography"}
    ]
    assert not offenders, (
        f"{SNOWFLAKE_SERVICE.name} imports {offenders} at module scope. Three routers import this "
        "module at module scope and main.py imports every router, so this lands in every cold "
        "start. Move it inside the function that uses it."
    )

    # Non-vacuity: the parse must have seen real imports, or an empty/renamed file would pass.
    assert module_scope_imports, "no module-scope imports parsed — wrong file or a broken parse"
