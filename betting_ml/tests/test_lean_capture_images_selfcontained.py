"""test_lean_capture_images_selfcontained.py  (lean-capture-image cure — fast gate)
================================================================================
The recurring box regression (2026-07-05): the LEAN capture images (services/*_capture/) are built
on purpose WITHOUT the betting_ml / pandas / dbt / Dagster stack — each copies only a couple of
"self-contained" scripts (+ maybe scripts/utils/). A straggler-sweep that "fixed" a hand-rolled
Snowflake resolver by repointing it at ``from betting_ml.utils.data_loader import get_snowflake_connection``
is CORRECT for the full images but FATAL here: betting_ml isn't in the image (and it imports pandas),
so the script ImportErrors on EVERY cron fire → the capture silently stalls → mlb_odds_raw / weather /
derivative odds go stale (odds-freshness CRITICAL). CI can't catch it (it never builds/runs these
images). See CLAUDE.md INC-22 + the odds-capture Dockerfile's "self-contained, no betting_ml" note.

INVARIANT (this guard): every ``scripts/*.py`` that a lean capture Dockerfile COPYs into its image
MUST NOT contain an executable ``import betting_ml`` / ``from betting_ml…`` (docstrings/comments are
fine — AST-based). Lean-image scripts resolve Snowflake auth SELF-CONTAINED (inline key via
cryptography), NOT by delegating to betting_ml. Pure source scan → fast gate; no image build needed.
"""
import ast
import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
CAPTURE_DOCKERFILES = sorted((REPO / "services").glob("*_capture/Dockerfile"))

# COPY scripts/foo.py …   |   COPY scripts/utils/ ./utils/   |   COPY scripts/utils/bar.py …
_COPY_SRC = re.compile(r"^\s*COPY\s+(.+?)\s+\S+\s*$", re.MULTILINE)


def _copied_scripts(dockerfile: pathlib.Path) -> list[pathlib.Path]:
    """Every scripts/*.py file a Dockerfile COPYs into the image (globs a copied dir)."""
    text = dockerfile.read_text()
    out: list[pathlib.Path] = []
    for line in text.splitlines():
        m = re.match(r"\s*COPY\s+(.+)$", line)
        if not m:
            continue
        # tokens before the final destination arg
        toks = m.group(1).split()
        for tok in toks[:-1] if len(toks) > 1 else toks:
            if not tok.startswith("scripts/"):
                continue
            p = REPO / tok
            if tok.endswith("/") or (p.is_dir()):
                out.extend(sorted(p.glob("*.py")))
            elif tok.endswith(".py") and p.exists():
                out.append(p)
    return out


def _imports_betting_ml(path: pathlib.Path) -> bool:
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("betting_ml"):
            return True
        if isinstance(node, ast.Import) and any(a.name.startswith("betting_ml") for a in node.names):
            return True
    return False


def test_capture_dockerfiles_discovered():
    assert CAPTURE_DOCKERFILES, "no services/*_capture/Dockerfile found — glob/layout changed?"


@pytest.mark.parametrize("dockerfile", CAPTURE_DOCKERFILES, ids=lambda p: p.parent.name)
def test_lean_capture_scripts_do_not_import_betting_ml(dockerfile):
    offenders = [p.relative_to(REPO) for p in _copied_scripts(dockerfile) if _imports_betting_ml(p)]
    assert not offenders, (
        f"{dockerfile.parent.name} is a LEAN capture image (no betting_ml/pandas installed), but it "
        f"COPYs script(s) that import betting_ml: {[str(o) for o in offenders]}. That ImportErrors on "
        f"every cron fire → the capture stalls → stale data (INC-22 / odds-freshness CRITICAL). Make "
        f"the script SELF-CONTAINED (resolve Snowflake auth inline via cryptography — see "
        f"scripts/odds_api_ingestion.py::get_snowflake_connection), do NOT delegate to betting_ml here."
    )
