"""test_nf_inj3b_m_out_stems.py — NF-INJ3b-M node 1 (PM ruling D4).

Two STANDING runners rewrote a DECIDED story's fixed artifact as a side effect, and NF-INJ3b hit
both while merely running them as ship-path gates:

  · `run_nf_tr2b_placement_read.main()`  overwrote `nf_tr2b_placement_read.*`
  · `run_interval_revalidation`          overwrote `nf1_9_interval_revalidation.json`
                                         **even under `--no-report`**

⭐ These are STANDING jobs (the interval re-validation is the annual one), so the workaround
NF-INJ3b used — call the pure `run()`, byte-restore afterwards — would be re-invented by whoever
ran them next, and forgotten once. The fix is in the runners: an `--out` stem whose DEFAULT is a
neutral "latest" path, so writing a decided record is an EXPLICIT act.

⚠️ CONSEQUENCE, guarded here rather than left implicit: the standing annual invocation now writes
to the neutral stem, so refreshing NF1.9's record is `--out nf1_9_interval_revalidation`. Both
runners must SAY SO on every non-decided write — a run that quietly wrote somewhere else is how a
stale decided record goes unnoticed, which is the opposite failure to the one D4 fixes.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from quant_sports_intel_models.football.nfl.fantasy import run_interval_revalidation as IV
from quant_sports_intel_models.football.nfl.fantasy import run_nf_tr2b_placement_read as PR

RUNNERS = (
    pytest.param(PR, id="placement_read"),
    pytest.param(IV, id="interval_revalidation"),
)


def _code_only(src: str) -> str:
    """Strip comments AND docstrings before scanning source (INC-38: prose must not satisfy a
    guard — and both these modules DISCUSS the decided stems at length in their docstrings)."""
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if (node.body and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)):
                node.body[0].value.value = ""
    return ast.unparse(tree)


def _main_src(mod) -> str:
    """The `main()` body only — the write sites live there and nowhere else."""
    tree = ast.parse(Path(mod.__file__).read_text())
    fn = next(n for n in tree.body
              if isinstance(n, ast.FunctionDef) and n.name == "main")
    return _code_only(ast.unparse(fn))


@pytest.mark.parametrize("mod", RUNNERS)
class TestTheDefaultInvocationCannotTouchADecidedArtifact:
    def test_the_decided_stem_and_a_neutral_default_are_BOTH_declared(self, mod):
        assert isinstance(mod.DECIDED_STEM, str) and mod.DECIDED_STEM
        assert isinstance(mod.DEFAULT_STEM, str) and mod.DEFAULT_STEM
        assert mod.DEFAULT_STEM != mod.DECIDED_STEM, (
            "the default must not BE the decided stem — that is the defect D4 fixes")
        assert mod.DEFAULT_STEM.startswith(mod.DECIDED_STEM), (
            "keep the neutral default recognisable as this runner's output")

    def test_the_out_flag_exists_and_DEFAULTS_to_the_neutral_stem(self, mod):
        src = _main_src(mod)
        m = re.search(r"add_argument\('--out', default=(\w+)", src)
        assert m, "no --out flag on main() — this guard would pass on NOTHING"
        assert m.group(1) == "DEFAULT_STEM", (
            f"--out defaults to {m.group(1)}, not the neutral DEFAULT_STEM")

    def test_every_write_site_is_parameterised_by_the_out_stem(self, mod):
        """⛔ A hardcoded decided path anywhere in `main()` re-opens the defect."""
        src = _main_src(mod)
        writes = re.findall(r"([A-Za-z_.\[\]/ '\"{}()f]+)\.write_text\(", src)
        assert writes, "no write site found — this guard would pass on NOTHING"
        for w in writes:
            assert "args.out" in w or "a.out" in w, f"write site not keyed on --out: {w!r}"
        # and no module-level decided path constant is written to
        assert "_OUT_JSON.write_text" not in src
        assert "_OUT_MD" not in src

    def test_a_non_decided_write_SAYS_the_decided_record_was_not_updated(self, mod):
        """The opposite failure to D4's: a run that quietly wrote elsewhere is how a decided record
        goes stale unnoticed. The runner must name it every time."""
        src = _main_src(mod)
        assert re.search(r"if (?:a|args)\.out != DECIDED_STEM", src), (
            "no disclosure branch — a silent redirect is its own defect")
        assert "was NOT updated" in Path(mod.__file__).read_text()


class TestTheIntervalRunnersNoReportActuallyWritesNothing:
    """⭐ THE REAL BUG D4 NAMES. The JSON write sat OUTSIDE the `--no-report` branch, so
    `--no-report` rewrote NF1.9's decided record anyway. A `--no-report` that writes is not one."""

    def test_no_write_site_survives_outside_the_no_report_branch(self):
        tree = ast.parse(Path(IV.__file__).read_text())
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")

        guarded, unguarded = [], []
        for node in ast.walk(fn):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "write_text"):
                continue
            src = ast.unparse(node)
            # is this call inside an `if not args.no_report:` block?
            inside = any(
                isinstance(p, ast.If) and "no_report" in ast.unparse(p.test)
                and any(node is c for c in ast.walk(ast.Module(body=p.body, type_ignores=[])))
                for p in ast.walk(fn))
            (guarded if inside else unguarded).append(src)

        assert guarded, "no guarded write found — this guard would pass on NOTHING"
        assert not unguarded, f"write sites outside the --no-report branch: {unguarded}"

    def test_write_report_is_also_inside_the_branch(self):
        src = _main_src(IV)
        m = re.search(r"if not args\.no_report:(.*?)(?:\n    \S|\Z)", src, re.S)
        assert m, "the --no-report branch is gone"
        assert "write_report(" in m.group(1)
