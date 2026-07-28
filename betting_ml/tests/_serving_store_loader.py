"""Shared, ISOLATION-SAFE loader for scripts/write_serving_store.py.

`write_serving_store.py` is a script, not an installed package, so tests load it by path. It
pulls heavy optional deps (`snowflake.connector`, `dotenv`) that the fast gate has no reason to
pay for, so the loader stubs them — but the stub must be TEMPORARY.

WHY (CI hygiene, 2026-07-27): the two copies of this loader that lived in
`test_best_price_e9_11.py` and `test_serving_timestamp_coercion.py` installed their MagicMock
stubs into `sys.modules` at MODULE-IMPORT time and never removed them. pytest imports every test
module during COLLECTION, before a single test runs, so those stubs leaked into every other test
in the same process for the rest of the session. Worse, each was guarded by
`if stub not in sys.modules`, which makes the behaviour depend on whether some *other* module
happened to import `dotenv` first — i.e. on collection order. That is the precise shape of a
"passes in isolation, fails in the full run" flake, and it is also what makes a suite unsafe to
shard across xdist workers.

THE RULE: a test module may not mutate global interpreter state (`sys.modules`, `os.environ`,
cwd) at import time without restoring it. Enforced by
`betting_ml/tests/test_fast_gate_hygiene.py`.
"""
from __future__ import annotations

import contextlib
import importlib.util
import sys
import unittest.mock as _mock
from pathlib import Path
from types import ModuleType

_REPO_ROOT = Path(__file__).resolve().parents[2]

# Heavy/optional deps write_serving_store imports at module scope but that no test exercises.
_STUBBED = ("snowflake.connector", "dotenv")

_MISSING = object()  # sentinel: the key was absent from sys.modules before we touched it


@contextlib.contextmanager
def _stubbed_heavy_imports():
    """Install MagicMock stubs for the duration of the load, then restore sys.modules exactly.

    Restores the PREVIOUS entry (or removes the key when there was none), so the loader leaves
    `sys.modules` byte-for-byte as it found it regardless of what was imported before us.
    """
    saved = {name: sys.modules.get(name, _MISSING) for name in _STUBBED}
    try:
        for name in _STUBBED:
            stub = _mock.MagicMock()
            if name == "dotenv":
                stub.load_dotenv = lambda *a, **kw: None
            sys.modules[name] = stub
        yield
    finally:
        for name, prev in saved.items():
            if prev is _MISSING:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = prev


def load_write_serving_store(alias: str) -> ModuleType:
    """Exec scripts/write_serving_store.py under `alias` without running main().

    `alias` must be unique per test module — two modules loading under the same name would share
    (and clobber) one `sys.modules` entry.
    """
    src = _REPO_ROOT / "scripts" / "write_serving_store.py"
    spec = importlib.util.spec_from_file_location(alias, src)
    mod = importlib.util.module_from_spec(spec)
    # Registered before exec so any self-referential import inside the module resolves.
    sys.modules[alias] = mod
    with _stubbed_heavy_imports():
        spec.loader.exec_module(mod)
    return mod
