"""NF-K1 — the box's CD trigger must cover every path the box actually RUNS.

🔴 WHY THIS EXISTS. `orchestration_cd.yml` is the ONLY thing that rebuilds the Dagster box image,
and the root Dockerfile ends in `COPY . .` — so the image contains the whole repo and the workflow's
`paths:` filter is the sole decider of whether a change ever reaches production. A path missing from
that filter means: CI green → merged to `main` → **the box keeps running the old code, silently, with
green runs**. The file's own comments record that class biting via `dbt/**`, `scripts/**`,
`betting_ml/**` and `quant_sports_intel_models/sports_dbt/**`, each added after it bit.

It bit again at NF-K1. `sports_nfl_board_publish_job` executes `run_nf1_5`, `run_league_board` and
`export_draft_board_json` on the box, and **none** of `quant_sports_intel_models/football/nfl/fantasy/**`
was in the filter. The NF-K1 fix reached the box only because that PR incidentally edited a docstring
in `pipeline/`; a fantasy-only fix would have merged and kept publishing from the old image.

⭐ SO THE LIST IS RE-DERIVED HERE, NOT RESTATED. A test that hardcoded the same list would be a
second copy of the thing that rotted — it would have passed happily throughout the NF-K1 outage. This
walks `pipeline/` and `scripts/` for the `quant_sports_intel_models.*` modules they reference and
requires the workflow to cover each one, so a new box-run module cannot ship without the filter
gaining its line.

⚠️ SCOPE, stated so nobody widens this into a false promise: this proves the filter covers what
`pipeline/`/`scripts/` REFERENCE. It cannot prove a module is reachable at runtime, and it says
nothing about `app/backend/**` or `frontend/**` — those are not on the box (the API Lambda ships via
`infrastructure/lambda/deploy.sh`, the frontend via Vercel) and must NOT be added here.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW = _ROOT / ".github/workflows/orchestration_cd.yml"

#: The trees whose code the box executes, and which therefore must trigger a rebuild. `pipeline/`
#: and `scripts/` are the entry points; everything else is reached from them.
_BOX_ENTRY_DIRS = ("pipeline", "scripts")

#: The package root itself is a namespace, not a deployable subtree.
_NOT_A_SUBTREE = {"quant_sports_intel_models"}


def _is_deployable_dir(subtree: str) -> bool:
    """A directory that HOLDS code, as opposed to a namespace that only groups other packages.

    `quant_sports_intel_models/football` holds nothing but `ncaaf/` and `nfl/`, so requiring a
    filter line for it would mean covering both entire sports — every research runner included —
    which is the whole-tree cost this list was measured to avoid. `fantasy_engine`, by contrast,
    holds the scorer itself. The discriminator is "does it own any module other than `__init__`",
    which needs no hand-maintained exception list."""
    d = _ROOT / subtree
    return d.is_dir() and any(p.name != "__init__.py" for p in d.glob("*.py"))


def _trigger_paths() -> list[str]:
    """The workflow's `on.push.paths`.

    ⚠️ Parsed as YAML, never grepped: `paths:` also appears under `paths-ignore` and in comments in
    workflows generally, and a substring scan over this file would be satisfied by the very comments
    that EXPLAIN each entry (the INC-38 prose-cannot-satisfy rule)."""
    spec = yaml.safe_load(_WORKFLOW.read_text())
    # `on` is parsed as the boolean True by YAML 1.1 — the reason a naive `spec["on"]` returns None.
    trigger = spec.get("on") or spec.get(True)
    assert trigger, "could not read the workflow's trigger block"
    paths = trigger["push"]["paths"]
    assert paths, "the CD workflow has no path filter at all"
    return list(paths)


def _subtrees_in(paths) -> set[str]:
    """The `quant_sports_intel_models.<...>` subtrees referenced by the given files.

    Truncated to the depth the repo organises deployable units at: `fantasy_engine`,
    `sports_dbt`, and `football/<sport>/<area>`."""
    pattern = re.compile(r"quant_sports_intel_models[\w.]*")
    found: set[str] = set()
    for py in paths:
        for hit in pattern.findall(py.read_text()):
            # `[\w.]*` happily swallows a sentence-ending dot out of prose ("…football.nfl. The"),
            # which would otherwise derive a subtree with an empty final segment.
            parts = [p for p in hit.split(".") if p]
            if len(parts) == 1:
                continue
            # football/<sport>/<area>; everything else at one level (fantasy_engine, sports_dbt)
            depth = 4 if len(parts) > 3 and parts[1] == "football" else 2
            found.add("/".join(parts[:depth]))
    return found - _NOT_A_SUBTREE


def _referenced_subtrees() -> set[str]:
    """The TRANSITIVE closure of `quant_sports_intel_models` subtrees the box can execute.

    ⭐ THE CLOSURE IS THE POINT, and the first cut of this guard got it wrong in an instructive way:
    scanning only `pipeline/` and `scripts/` found four subtrees and MISSED
    `quant_sports_intel_models/fantasy_engine`, which is box-executed — `run_league_board` (run by
    `sports_nfl_board_publish_job`) imports `fantasy_engine.score_players` for the scoring/VOR maths.
    Nothing in `pipeline/` or `scripts/` names it directly, so a direct-reference scan would have
    left the repo's actual board SCORER outside the CD trigger — the same silent-staleness gap this
    file exists to close, one hop further out.

    So: start at the entry points and expand until nothing new appears."""
    seen: set[str] = set()
    frontier = _subtrees_in(
        py for d in _BOX_ENTRY_DIRS for py in (_ROOT / d).rglob("*.py")
    )
    while frontier - seen:
        seen |= frontier
        frontier = seen | _subtrees_in(
            py for s in seen for py in (_ROOT / s).rglob("*.py") if (_ROOT / s).is_dir()
        )
    # Namespaces are traversed (their children are real subtrees) but never REQUIRED themselves.
    return {s for s in seen if _is_deployable_dir(s)}


def _covered(subtree: str, paths: list[str]) -> bool:
    """Is `subtree` matched by some filter entry? A `foo/**` entry covers `foo` and everything below."""
    for p in paths:
        base = p[:-3] if p.endswith("/**") else p
        if subtree == base or subtree.startswith(base + "/"):
            return True
    return False


def test_the_derivation_is_not_vacuous():
    """⭐ FIRST, because every assertion below is trivially true over an empty set. A regex that
    stopped matching would otherwise turn this whole file green (NF1.7 (a) / DSR-CONV #690)."""
    subtrees = _referenced_subtrees()
    assert len(subtrees) >= 5, f"only derived {sorted(subtrees)} — the scan is not finding the modules"
    assert "quant_sports_intel_models/football/nfl/fantasy" in subtrees, (
        "the NFL fantasy subtree is not being derived, so the regression this guard was written "
        "for would not be caught")


def test_every_box_run_subtree_triggers_a_deploy():
    """🔴 THE NF-K1 GUARD. A box-executed subtree missing from the filter means CI-green code that
    never reaches the box."""
    paths = _trigger_paths()
    missing = sorted(s for s in _referenced_subtrees() if not _covered(s, paths))
    assert not missing, (
        "these subtrees are executed on the box (referenced from pipeline/ or scripts/) but do NOT "
        "trigger the orchestration CD, so a change to them would merge to main and keep running "
        "STALE on the box:\n"
        + "\n".join(f"  - {m}/**" for m in missing)
        + "\n\nAdd each to `on.push.paths` in .github/workflows/orchestration_cd.yml.")


@pytest.mark.parametrize("entry", ["pipeline/**", "scripts/**", "betting_ml/**", "dbt/**"])
def test_the_long_standing_entries_are_still_present(entry):
    """Each of these was added after it bit. Removing one silently reopens that incident."""
    assert entry in _trigger_paths(), f"{entry} was removed from the CD trigger"


@pytest.mark.parametrize("entry", ["Dockerfile", "pyproject.toml", "uv.lock"])
def test_the_image_build_inputs_trigger_a_deploy(entry):
    """The Dockerfile pins every pickle-fragile ML lib and asserts them against pyproject/uv.lock at
    build time. A pin bump that does not rebuild leaves the box on the OLD versions while the repo
    claims otherwise — the 2026-07-03 train/serve pickle-skew landmine on the delivery side."""
    assert entry in _trigger_paths(), f"{entry} does not trigger a box rebuild"


def test_the_lambda_and_frontend_are_not_wired_to_the_box_deploy():
    """⛔ THE OTHER DIRECTION, and it matters as much. `app/backend/**` ships via
    `infrastructure/lambda/deploy.sh` and `frontend/**` via Vercel; putting either here would fire a
    box rebuild for a change the box does not run, and — worse — would read as though merging
    deployed the API, which is exactly the NF-C0 skew misconception."""
    paths = _trigger_paths()
    for forbidden in ("app/backend/**", "app/**", "frontend/**"):
        assert forbidden not in paths, (
            f"{forbidden} triggers the BOX deploy; it is not box code, and its presence implies a "
            "deploy that does not happen")
