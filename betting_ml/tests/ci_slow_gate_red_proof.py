"""RED proof for the slow-gate scoping guards — `uv run python betting_ml/tests/ci_slow_gate_red_proof.py`.

The slow gate is handed an explicit file list instead of collecting `testpaths`. That is a 36%
wall-clock saving and a way for a test to stop running with NO signal: `-m` can only select from
what pytest IMPORTS, so a slow test in a file the scanner misses is deselected by absence — green
gate, no error. These five breaks re-introduce each way that could happen and require a guard to
notice.

Same harness contract as the other RED proofs here: the anchor must be UNIQUE, pytest runs in a
SUBPROCESS, only exit code 1 counts as RED, and the file is restored in a `finally`.
"""
import subprocess, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
TEST = "betting_ml/tests/test_fast_gate_hygiene.py"
_SH, _CI = "scripts/ci_shards.py", ".github/workflows/ci.yml"
BREAKS = [
  ("scanner: only detect the DECORATOR form (pytestmark + param marks escape)", _SH,
   "        if (\n            isinstance(node, ast.Attribute)\n            and node.attr == marker\n            and isinstance(node.value, ast.Attribute)\n            and node.value.attr == \"mark\"\n        ):\n            return True",
   "        if isinstance(node, ast.FunctionDef) and any(\n            isinstance(d, ast.Attribute) and d.attr == marker for d in node.decorator_list\n        ):\n            return True",
   "every_way_of_writing"),
  ("scanner: claim EVERY file (a scanner that always says yes)", _SH,
   "    try:\n        tree = ast.parse(path.read_text(encoding=\"utf-8\"))",
   "    if True:\n        return True\n    try:\n        tree = ast.parse(path.read_text(encoding=\"utf-8\"))",
   "not_claimed"),
  ("scanner: DROP an unparseable file from the run", _SH,
   "    except (SyntaxError, UnicodeDecodeError, OSError):\n        return True",
   "    except (SyntaxError, UnicodeDecodeError, OSError):\n        return False",
   "unparseable"),
  ("scanner: lose the heavy files (a narrowed list the gate would silently accept)", _SH,
   "    return [p for p in all_test_files(root) if _uses_marker(root / p, SLOW_MARKER)]",
   "    return [p for p in all_test_files(root) if _uses_marker(root / p, SLOW_MARKER)\n            and 'mh2' not in p.name]",
   "finds_the_files"),
  ("workflow: revert to the unscoped command (wired-not-invoked)", _CI,
   "          uv run pytest $(uv run python scripts/ci_shards.py --slow-paths) \\\n            -m \"slow and not research\" -n auto --tb=short",
   "          uv run pytest -m \"slow and not research\" -n auto --tb=short",
   "workflow_actually_uses"),
]
fails = []
for name, rel, old, new, sel in BREAKS:
    path = REPO / rel
    orig = path.read_text()
    n = orig.count(old)
    if n != 1:
        print(f"{'BROKEN (anchor x%d)' % n:36} {name}"); fails.append(name); continue
    path.write_text(orig.replace(old, new, 1))
    try:
        r = subprocess.run([sys.executable, "-m", "pytest", TEST, "-q", "-k", sel,
                            "-p", "no:cacheprovider", "-o", "addopts="],
                           cwd=REPO, capture_output=True, text=True)
        v = "RED ✅" if r.returncode == 1 else (f"GREEN ❌ VACUOUS" if r.returncode == 0 else f"BROKEN rc={r.returncode}")
        if r.returncode != 1: fails.append(name)
        print(f"{v:36} {name}")
    finally:
        path.write_text(orig)
print()
print(f"{len(fails)} not caught" if fails else f"all {len(BREAKS)} breaks caught ✅")
sys.exit(1 if fails else 0)
