"""NCAAF-P3.3b follow-ups — the three affordances the 2026-09-05 deploy proved were missing.

None of these is a feature. Each closes a gap that COST TIME on the acceptance run for P3.3b, and
each is written down here so the cost is auditable rather than remembered:

  1. THE RUN REPORT WAS SILENT ON THE THING THE RUN WAS GATING. The box writer computed the ratings
     vintage and logged it, while `report["team_pages"]` carried block counts and no vintage — so a
     clean-looking acceptance JSON could not answer "did the stamp populate?", and the operator had
     to read the served S3 blob to find out. E11.30 in miniature: detected, not reported.

  2. A CACHED READ AND A FAILED DEPLOY ARE BYTE-IDENTICAL. Every `/ncaaf/*` route answers
     `cache-control: public, s-maxage=900, stale-while-revalidate=3600` (G100-D1's public cache
     rule). One plain read of a team payload showed a field missing; that read as "the Lambda was
     not deployed", the deploy was in fact fine, and isolating it needed a direct S3 read. The
     `@live` suite — the one place that asks "does the SERVER still send X" — used plain reads and
     had no team-page clause at all.

  3. "IS THE DEPLOYED BUILD THE ONE I THINK IT IS?" HAD NO CHEAP ANSWER. This Lambda has no CD and
     `deploy.sh` packages the CURRENT WORKING TREE with no ref pin, so the question was answerable
     only by curling a feature through that same cache and inferring backwards. G100-C0-MFA
     recorded this once already; this is its second instance, hence a permanent affordance.

RED-proven by `betting_ml/tests/ncaaf_p3_3b_followups_red_proof.py`.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pandas as pd

from app.backend import build_info

REPO = Path(__file__).resolve().parents[2]
WRITER = REPO / "scripts/write_ncaaf_serving_store.py"
DEPLOY = REPO / "infrastructure/lambda/deploy.sh"
MAIN = REPO / "app/backend/main.py"
LIVE_SPEC = REPO / "frontend/e2e/specs/ncaaf-live-api.spec.ts"
CACHE_RULES = REPO / "app/backend/services/cost_guardrails.py"


def _executable_source(src: str) -> str:
    """`src` minus every comment AND docstring.

    The same helper `test_ncaaf_p3_3b_ratings_stamp.py` needed, and for the same reason: these
    modules EXPLAIN the defects they avoid, so a scan that only strips `#` comments is satisfied —
    or tripped — by prose saying the opposite of the code (INC-38).
    """
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                node.body = body[1:] or [ast.Pass()]
    return ast.unparse(ast.fix_missing_locations(tree))


def _strip_sh_comments(src: str) -> str:
    """Shell source minus `#` comment LINES. ⛔ Not a full parser — but the anchors below are
    command lines, and a comment describing a command must not satisfy a guard about it (INC-38).
    """
    return "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("#"))


# ── 1. the run report carries the vintage ────────────────────────────────────────────────────

def _strength_row() -> dict:
    return {
        "team_id": 68, "season": 2026, "as_of_week": 1, "games_in_window": 0,
        "strength_margin": 3.09, "strength_margin_sd": 7.29,
        "model_version": "ncaaf_team_strength_v1",
    }


def test_the_run_report_carries_the_ratings_vintage(monkeypatch):
    """The acceptance JSON must answer the question the acceptance run exists to gate.

    ⭐ ASSERTED ON THE REPORT THE WRITER ACTUALLY BUILDS, not on its source. A source scan for
    `"ratings_as_of": stamp[...]` would pin one spelling of one line and pass the moment someone
    reformatted it — and it cannot see whether the value SURVIVES into the dict at all.
    """
    import scripts.write_ncaaf_serving_store as writer

    monkeypatch.setattr(writer, "read_team_strength",
                        lambda season: pd.DataFrame([_strength_row()]))
    monkeypatch.setattr(writer, "read_team_marts",
                        lambda season: ({}, "source_marts_unavailable"))
    monkeypatch.setattr(
        "betting_ml.monitoring.ncaaf_ratings_vintage.ratings_vintage_fields",
        lambda **kw: {"ratings_as_of": "2026-08-18T06:16:36.806000+00:00",
                      "ratings_next_update": None})

    _blobs, report = writer.build_team_blobs(2026)
    assert report["ratings_as_of"] == "2026-08-18T06:16:36.806000+00:00", (
        "the run report is silent on the ratings vintage — the acceptance run would be unable to "
        "answer the very question it exists to gate, which is what happened on 2026-09-05")
    assert "ratings_next_update" in report
    assert report["ratings_next_update"] is None


def test_the_report_reports_a_null_vintage_rather_than_omitting_the_key(monkeypatch):
    """A MISSING key and a null value are different findings, and only one of them is legible.

    `ratings_as_of: null` means the lake read FAILED — the ALERT an operator most needs to see in
    this JSON. Omitting the key on failure would make an outage look like an older writer, which is
    the absent-vs-null discipline this vertical is built on (NF-C6b).
    """
    import scripts.write_ncaaf_serving_store as writer

    monkeypatch.setattr(writer, "read_team_strength",
                        lambda season: pd.DataFrame([_strength_row()]))
    monkeypatch.setattr(writer, "read_team_marts", lambda season: ({}, "source_marts_unavailable"))

    def _boom(**kw):
        raise RuntimeError("simulated lake outage")

    monkeypatch.setattr(
        "betting_ml.monitoring.ncaaf_ratings_vintage.ratings_vintage_fields", _boom)

    _blobs, report = writer.build_team_blobs(2026)
    # The write DEGRADES rather than failing — it is HALT-tier and the stamp is not.
    assert "ratings_as_of" in report, "the key vanished on a failed read — an outage now looks " \
        "like an older writer"
    assert report["ratings_as_of"] is None
    assert report["ratings_next_update"] is None


# ── 2. the @live suite cannot be fooled by the CDN ───────────────────────────────────────────

def test_the_ncaaf_routes_really_are_shared_cached():
    """The PREMISE of the cache-bust, measured from the rule table rather than assumed.

    If `/ncaaf` ever leaves `_PUBLIC_CACHE_RULES`, the bust becomes harmless but its RATIONALE is
    stale — and a comment explaining a hazard that no longer exists is how the next reader deletes
    a guard that still matters elsewhere.
    """
    from app.backend.services import cost_guardrails

    cc = cost_guardrails.public_cache_control("/ncaaf/teams/68")
    assert cc is not None, "/ncaaf is no longer shared-cacheable — re-check the @live bust rationale"
    assert "s-maxage=" in cc and "stale-while-revalidate=" in cc


def test_health_is_not_shared_cached_so_the_build_marker_cannot_go_stale():
    """⛔ THE LOAD-BEARING HALF OF PUTTING THE MARKER ON `/health`.

    A build marker behind `s-maxage=900` would report the PREVIOUS build for up to 15 minutes —
    which is exactly the confusion it exists to end, one indirection later.
    """
    from app.backend.services import cost_guardrails

    assert cost_guardrails.public_cache_control("/health") is None, (
        "/health became shared-cacheable — the build marker can now be served stale, so either "
        "move the marker or exempt this path")


def test_every_live_ncaaf_request_is_cache_busted():
    """A plain read cannot distinguish 'the server stopped sending X' from 'the cache has not
    turned over' — and this suite exists to answer exactly the first question."""
    src = LIVE_SPEC.read_text()
    body = "\n".join(ln for ln in src.splitlines() if not ln.strip().startswith(("//", "*", "/*")))
    raw = re.findall(r"request\.get\(([^)]*)\)", body)
    assert raw, "no request.get calls found — re-anchor this clause"
    for call in raw:
        assert call.strip().startswith("bust("), (
            f"a @live request bypasses the cache-bust: request.get({call.strip()})")
    assert "_cb=" in src and "Math.random()" in src, (
        "the bust must be UNIQUE per call — a fixed param is itself cacheable")


def test_the_live_suite_covers_the_team_payloads_stamp():
    """The clause whose absence made 2026-09-05 a hand-diagnosis.

    🪤 THIS GUARD WAS VACUOUS ON ITS FIRST CUT AND THE RED PROOF CAUGHT IT. It matched the bare
    substring `/ncaaf/teams/`, which ALSO appears inside the assertion's own failure message
    ("GET /ncaaf/teams/68 → ..."), so deleting the actual request left the clause green. Match the
    REQUEST FORM, over comment-stripped source — a string a diagnostic message happens to contain
    is not evidence that a call exists (the NF-DTB-1 / INC-38 family).
    """
    src = LIVE_SPEC.read_text()
    body = "\n".join(ln for ln in src.splitlines() if not ln.strip().startswith(("//", "*", "/*")))
    assert re.search(r'request\.get\(\s*bust\(\s*[`"\']/ncaaf/teams/', body), (
        "@live never REQUESTS a team payload — the surface's own contract is unchecked")
    # The two halves must be asserted as a pair, driven from a list rather than named once in prose.
    assert re.search(r'for \(const key of \[[^\]]*"ratings_as_of"[^\]]*"ratings_next_update"', body), (
        "@live does not assert BOTH stamp keys on the served payload")
    # ⛔ And the asymmetry is deliberate and must survive: a null next-update is CORRECT (nothing
    # rewrites the ratings), so a clause requiring it non-null would fail on a healthy payload.
    assert re.search(r'expect\(\s*s\.ratings_as_of[\s\S]{0,400}?\.not\.toBeNull\(\)', body), (
        "the vintage is not asserted non-null — a failed lake read would pass unnoticed")
    assert not re.search(r'expect\(\s*s\.ratings_next_update[\s\S]{0,200}?\.not\.toBeNull\(\)', body), (
        "the next-update half is asserted non-null, which FAILS on a correct payload: null is its "
        "measured state (the P1.2 re-fit is an operator step, on no schedule)")


# ── 3. the build marker ──────────────────────────────────────────────────────────────────────

def test_the_repo_copy_of_the_marker_holds_the_sentinel():
    """⛔ A real SHA must never be committed. The working-tree copy is what an UNPACKAGED process
    reports, and a stale SHA there would be a marker that lies with authority."""
    assert build_info.BUILD_SHA == build_info.SENTINEL
    assert build_info.BUILT_AT is None
    marker = build_info.build_marker()
    assert marker["packaged"] is False
    assert marker["sha"] == build_info.SENTINEL


def test_health_serves_the_marker_additively():
    """NF-C0: `status` and `environment` keep their meaning — a deployed client reading either is
    unaffected."""
    import app.backend.main as main

    body = main.health()
    assert body["status"] == "ok"
    assert "environment" in body
    assert body["build"] == build_info.build_marker()


def test_deploy_stamps_the_package_and_never_the_working_tree():
    """The write must target `$PACKAGE_DIR`. Rewriting `app/backend/build_info.py` in place would
    leave a real SHA in the tree, which is the one thing the sentinel exists to prevent."""
    sh = _strip_sh_comments(DEPLOY.read_text())
    assert 'cat > "$PACKAGE_DIR/app/backend/build_info.py"' in sh, (
        "deploy.sh does not stamp the packaged build_info.py")
    assert not re.search(r'>\s*app/backend/build_info\.py', sh), (
        "deploy.sh writes build_info.py in the WORKING TREE — it must write only into $PACKAGE_DIR")
    assert "git rev-parse HEAD" in sh, "the marker is not derived from the packaged commit"


def test_the_marker_never_becomes_a_lambda_environment_variable():
    """⛔⛔ THE LANDMINE THIS DESIGN EXISTS TO AVOID, pinned so a 'simplification' cannot reintroduce it.

    `update-function-configuration --environment` REPLACES the whole Variables map, and `deploy.sh`
    only ever calls `update-function-code` — so it could not restore what it wiped. E9.8-P2 measured
    that on the billing path, on the day money started moving. A build marker is not worth a class
    of outage that severe, which is why it is baked into the package instead.
    """
    sh = _strip_sh_comments(DEPLOY.read_text())
    assert "update-function-configuration" not in sh, (
        "deploy.sh gained an update-function-configuration call — it REPLACES the entire env "
        "Variables map and this script cannot restore it (E9.8-P2). Bake values into the package.")


def test_the_marker_costs_nothing_at_import():
    """PERF measured this Lambda's cold init as I/O-bound on unpacking a 57 MB package, so a marker
    that opened a file (or shelled out to git) at import would pay into exactly the wrong budget."""
    code = _executable_source((REPO / "app/backend/build_info.py").read_text())
    for banned in ("open(", "read_text", "subprocess", "Path(", "os.environ", "importlib"):
        assert banned not in code, f"build_info does IO/lookup at import ({banned})"
