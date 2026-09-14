"""test_pipeline_job_registry.py — every job imported into `pipeline/jobs/__init__.py` must
actually reach `Definitions(jobs=all_jobs)`.

⛔ THE DEFECT THIS EXISTS FOR. `sports_nfl_weekly_freshness_job` was defined (NF-C6-PH2), imported
here — TWICE, a copy-paste duplicate that made the block look thoroughly wired — and never added to
`all_jobs`. `Definitions` therefore never saw it, and it was invisible and unlaunchable in Dagit
from the day it shipped. It surfaced only when an operator went to launch it by hand during a live
verification and could not find it.

⭐ THE SHAPE IS THE REPO'S OLDEST ONE: wired ≠ invoked (NF-C0e). An import is not a registration,
and a name appearing in a file is not a name appearing in the list that does the work. The existing
guards each pinned ONE job they cared about (`artifact_freshness_job`, the NFL PIT jobs, the NCAAF
snapshot), which is why a thirty-fourth job could be added and silently registered nowhere — a
per-item guard cannot see an omission it was not written for.

⇒ this check is EXHAUSTIVE AND DERIVED: it re-computes both sets from the source and compares them,
so a job added tomorrow is covered without anyone remembering to extend it.

⚠️ AST, NOT AN IMPORT (E11.23). `pipeline/__init__.py` reads the dbt manifest at import, which is
ABSENT in the fast gate — importing `pipeline` here would kill this file at COLLECTION rather than
skipping cleanly. Reading the source is also the stronger check: it is what a human reviewer reads.
"""
from __future__ import annotations

import ast
from pathlib import Path

_REGISTRY = Path(__file__).resolve().parents[2] / "pipeline/jobs/__init__.py"


def _parsed() -> ast.Module:
    return ast.parse(_REGISTRY.read_text())


def _imported_job_names(tree: ast.Module) -> list[str]:
    """Every name pulled in from a `pipeline.jobs.*` module — duplicates preserved on purpose."""
    return [alias.asname or alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("pipeline.jobs.")
            for alias in node.names]


def _registered_job_names(tree: ast.Module) -> list[str]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
                getattr(t, "id", None) == "all_jobs" for t in node.targets):
            return [e.id for e in node.value.elts if isinstance(e, ast.Name)]
    raise AssertionError("no `all_jobs = [...]` assignment found — this guard would pass on nothing")


def test_every_imported_job_is_registered_in_all_jobs():
    """The omission itself: a job Definitions never sees cannot be launched, scheduled or found."""
    tree = _parsed()
    imported, registered = set(_imported_job_names(tree)), set(_registered_job_names(tree))

    # ⛔ NON-VACUITY FIRST (NF1.7(a)): an empty set difference is meaningless if either side is empty.
    assert len(imported) > 20, f"only {len(imported)} imported jobs parsed — the guard has gone blind"
    assert len(registered) > 20, f"only {len(registered)} registered jobs parsed — parser drift"

    missing = sorted(imported - registered)
    assert not missing, (
        f"imported into pipeline/jobs/__init__.py but absent from `all_jobs`: {missing}. "
        "`Definitions(jobs=all_jobs)` never sees these, so they are invisible in Dagit and cannot "
        "be launched, scheduled or run by hand — the wired-≠-invoked class on the job registry.")


def test_all_jobs_carries_nothing_it_did_not_import():
    """The mirror: a name in the list that nothing imports is a NameError waiting for a deploy."""
    tree = _parsed()
    stray = sorted(set(_registered_job_names(tree)) - set(_imported_job_names(tree)))
    assert not stray, f"listed in `all_jobs` but never imported: {stray}"


def test_no_job_is_imported_twice():
    """A duplicated import is how the original omission hid in plain sight: the block LOOKED
    thoroughly wired because the name appeared twice, while the list that matters had it zero
    times. Cheap to check, and it is the tell that a paste went wrong."""
    imported = _imported_job_names(_parsed())
    dupes = sorted({n for n in imported if imported.count(n) > 1})
    assert not dupes, f"imported more than once in pipeline/jobs/__init__.py: {dupes}"


def test_the_weekly_freshness_job_specifically_is_registered():
    """The regression that produced this file. Named explicitly so a future reader can see WHICH
    job was lost without reading git history — the exhaustive check above is what makes it general,
    this one is what makes it legible."""
    assert "sports_nfl_weekly_freshness_job" in set(_registered_job_names(_parsed()))
