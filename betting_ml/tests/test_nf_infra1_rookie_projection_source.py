"""NF-INFRA1 — the rookie-projection feeder must be obtainable ON THE BOX.

THE DEFECT (2026-08-15, the first time the board build ever ran on the box): `run_nf1_5 --mode
build` died with a bare

    FileNotFoundError: '/app/.../ncaaf/models/artifacts/ncaaf_nfl_rookie_projections.parquet'

`*.parquet` is gitignored in that artifacts directory, so the file is a **laptop-run output that is
never in the `COPY . .` image** — the SAME class as the sports DuckDB this story fixed, one artifact
over. ⛔ Copying it onto the box is not a cure either: `/app` is replaced by every deploy.

The fix reads the LOCAL artifact when it exists and the SPORTS LAKE when it does not. The order is
load-bearing in both directions and each direction gets its own clause below:
  * local first  → a LAPTOP build stays byte-identical to every certified board;
  * lake second  → the BOX, where the local copy can never exist, reads the authoritative table.

Fast-gate safe: no `pipeline` import; the lake read is monkeypatched, never performed.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pandas as pd
import pytest

from quant_sports_intel_models.football.nfl.fantasy import run_season_projection as RSP

_REPO = Path(__file__).resolve().parents[2]
_MODULE = _REPO / "quant_sports_intel_models/football/nfl/fantasy/run_season_projection.py"

_ROWS = pd.DataFrame({
    "gsis_id": ["00-1", "00-2"],
    "position_group": ["RB", "WR"],
    "draft_year": [2026, 2026],
    "draft_overall": [12, 40],
    "projected_nfl_z": [0.4, -0.1],
    "projected_nfl_z_sd": [0.3, 0.35],
})


@pytest.fixture(autouse=True)
def _clear_cache():
    """The loader memoizes per process so one build reads one vintage — which would otherwise leak
    the first test's frame into every later one."""
    RSP._rookie_frame_cache = None
    yield
    RSP._rookie_frame_cache = None


def _no_lake(monkeypatch):
    """Make any lake read fail loudly, so a test asserting the LOCAL path cannot pass by silently
    falling through to a stubbed lake."""
    from quant_sports_intel_models.football.ncaaf.ingest import query_lake

    def _boom(*a, **k):
        raise AssertionError("the lake was read when the LOCAL artifact was available")

    monkeypatch.setattr(query_lake, "q", _boom)


def _lake_returns(monkeypatch, frame):
    from quant_sports_intel_models.football.ncaaf.ingest import query_lake

    seen: list[str] = []
    monkeypatch.setattr(query_lake, "q", lambda sql: seen.append(sql) or frame.copy())
    return seen


# ── 1. the LOCAL artifact wins when it exists (laptop byte-identity) ─────────────────────────
def test_a_present_local_artifact_is_used_and_the_lake_is_NOT_read(tmp_path, monkeypatch, caplog):
    local = tmp_path / "ncaaf_nfl_rookie_projections.parquet"
    _ROWS.to_parquet(local, index=False)
    monkeypatch.setattr(RSP, "_ROOKIE_PARQUET", local)
    _no_lake(monkeypatch)

    with caplog.at_level("INFO"):
        out = RSP.load_rookie_projection_frame()

    assert len(out) == 2
    assert "LOCAL artifact" in caplog.text, (
        "the chosen source must be logged — a source preference that does not announce itself is "
        "how the pre-draft board regen silently published a 2-day-old board")


def test_the_local_branch_logs_the_mtime_so_a_stale_copy_is_findable(tmp_path, monkeypatch, caplog):
    """The residual risk of preferring local is a STALE local copy. The mtime is what makes that
    visible in a run log instead of invisible."""
    local = tmp_path / "r.parquet"
    _ROWS.to_parquet(local, index=False)
    monkeypatch.setattr(RSP, "_ROOKIE_PARQUET", local)
    _no_lake(monkeypatch)
    with caplog.at_level("INFO"):
        RSP.load_rookie_projection_frame()
    assert "mtime" in caplog.text


# ── 2. the LAKE is read when the local artifact is absent (the box) ──────────────────────────
def test_an_absent_local_artifact_falls_back_to_the_lake(tmp_path, monkeypatch, caplog):
    """⭐ THE BOX CASE. This is the read that used to be a bare FileNotFoundError."""
    monkeypatch.setattr(RSP, "_ROOKIE_PARQUET", tmp_path / "definitely-absent.parquet")
    seen = _lake_returns(monkeypatch, _ROWS)

    with caplog.at_level("INFO"):
        out = RSP.load_rookie_projection_frame()

    assert len(out) == 2
    assert seen and "delta_scan" in seen[0], "the fallback must read the Delta table"
    assert "ncaaf/derived/nfl_rookie_projections" in seen[0], (
        "the fallback must read the DERIVED tier table the dbt view reads — the authoritative copy")
    assert "SPORTS LAKE" in caplog.text


def test_the_frame_is_cached_so_one_build_reads_ONE_vintage(tmp_path, monkeypatch):
    """Three call sites per build; three independent reads could straddle a concurrent re-land and
    mix vintages inside one board."""
    monkeypatch.setattr(RSP, "_ROOKIE_PARQUET", tmp_path / "absent.parquet")
    seen = _lake_returns(monkeypatch, _ROWS)
    RSP.load_rookie_projection_frame()
    RSP.load_rookie_projection_frame()
    RSP.load_rookie_projection_frame()
    assert len(seen) == 1


def test_a_caller_cannot_mutate_the_cached_frame_for_the_next_caller(tmp_path, monkeypatch):
    monkeypatch.setattr(RSP, "_ROOKIE_PARQUET", tmp_path / "absent.parquet")
    _lake_returns(monkeypatch, _ROWS)
    first = RSP.load_rookie_projection_frame()
    first.loc[0, "projected_nfl_z"] = 999.0
    assert RSP.load_rookie_projection_frame().loc[0, "projected_nfl_z"] != 999.0


# ── 3. neither source ⇒ a NAMED failure, not a bare FileNotFoundError ────────────────────────
def test_both_sources_absent_raises_a_message_that_names_BOTH_and_the_cure(tmp_path, monkeypatch):
    """The original failure was a bare FileNotFoundError on a path whose absence is EXPECTED on the
    box — legible only to someone who already knew the gitignore. The replacement has to say what to
    do."""
    monkeypatch.setattr(RSP, "_ROOKIE_PARQUET", tmp_path / "absent.parquet")
    from quant_sports_intel_models.football.ncaaf.ingest import query_lake

    monkeypatch.setattr(query_lake, "q", lambda sql: (_ for _ in ()).throw(RuntimeError("no creds")))

    with pytest.raises(FileNotFoundError) as exc:
        RSP.load_rookie_projection_frame()
    msg = str(exc.value)
    assert "gitignored" in msg
    assert "nfl_rookie_projections" in msg
    assert "SPORTS_LAKE_REGION" in msg, "the box's actual cure must be named"
    assert "run_college_nfl_translation.py --s3" in msg, "the laptop's cure must be named"


def test_an_EMPTY_lake_table_refuses_rather_than_building_a_rookieless_board(tmp_path, monkeypatch):
    """A readable-but-empty table is the silent-empty class: every downstream filter would return
    nothing and the board would publish with NO rookies and no error."""
    monkeypatch.setattr(RSP, "_ROOKIE_PARQUET", tmp_path / "absent.parquet")
    _lake_returns(monkeypatch, _ROWS.iloc[0:0])
    with pytest.raises(ValueError, match="EMPTY"):
        RSP.load_rookie_projection_frame()


# ── 4. no call site may bypass the resolver ─────────────────────────────────────────────────
def test_no_call_site_reads_the_parquet_directly():
    """A new `pd.read_parquet(_ROOKIE_PARQUET)` anywhere re-introduces the box failure for that
    code path only — the hardest kind to notice, because the other paths keep working."""
    tree = ast.parse(_MODULE.read_text())
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and "_ROOKIE_PARQUET" in ast.unparse(node):
            src = ast.unparse(node)
            if "read_parquet" in src:
                offenders.append(src)
    # The ONE legitimate read lives inside the resolver itself.
    assert len(offenders) == 1, (
        f"exactly one read_parquet(_ROOKIE_PARQUET) may exist (inside load_rookie_projection_frame); "
        f"found {len(offenders)}: {offenders}")


def test_the_resolver_is_the_only_thing_that_names_the_parquet_outside_its_own_definition():
    """Non-vacuity companion to the clause above: prove the scan actually sees the module."""
    src = _MODULE.read_text()
    assert src.count("load_rookie_projection_frame()") >= 2, (
        "both historical call sites must go through the resolver — this guard is stale otherwise")
