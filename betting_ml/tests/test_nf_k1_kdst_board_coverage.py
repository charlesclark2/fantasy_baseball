"""NF-K1 — guards for the K/DST board regression: the lake fallback, the publish-time position
coverage guard, and the three distinguishable "not matched" causes.

🔴 THE DEFECT, MEASURED (2026-08-16). The published NFL board carried 795 players — QB/RB/WR/TE and
ZERO K, ZERO D/ST — so every rostered kicker and team defence rendered "not matched". Dated exactly:
the operator's 2026-08-15 laptop publish shipped 868 players WITH 42 K + 32 DST; the first automated
`sports_nfl_board_publish_job` run (schedule `15 7 * * *` America/Los_Angeles → 14:15Z, artifact
`generated_at` 14:22:15Z) shipped neither.

⭐ WHY NO EXISTING TEST COULD SEE IT, which is the whole design brief for this file.
`test_nf1_6_kdst_projection.py` guards the K/DST code PATH and was green throughout. The E2E fixture
`fantasy-nfl-projections-2026-entitled.synthetic.json` still carries 42 K + 32 DST, so every fixture-
based assertion was green too. The regression lived in neither the code nor the fixtures but in the
BYTES THAT WERE PUBLISHED — a state no guard in the repo was looking at (the NF-C0e "verify the
published artifact, not the fixture" class in its purest form).

So the guard added here opens the STAGED FILES ON DISK, and the tests below drive it with
production-shaped payloads INCLUDING the two that actually shipped.

THREE FAMILIES:

  1. **THE CAUSE** — `run_league_board.load_kdst` is LOCAL-FIRST-THEN-LAKE, and both call sites use
     it. The K/DST parquet is the one artifact the box's publish chain READS but never WRITES, and
     `artifacts/.gitignore` ignores `*.parquet`, so on the box it was simply absent and the
     local-only read treated that as warn-and-continue (NF-INFRA1's class, 3rd instance).

  2. ⭐ **THE PUBLISH GUARD** — `assert_published_position_coverage` refuses a staged board missing a
     whole PROJECTABLE position. Its non-vacuity is the interesting half: `kdst_records` gap-fills an
     UNPROJECTED placeholder row per (pos, team), so a board that lost the entire K/DST projection
     still ships 32 K + 32 DST rows and a presence-only check would pass on exactly the broken
     artifact.

  3. **THE THREE CAUSES** — "we did not publish that position", "we could not resolve this name" and
     "we do not project this position" are different facts with different (or no) user actions, and
     the surface rendered all three as one word. Guarded here on the Python side of the boundary
     (`league_scoring.published_positions`) and by source-inspection of the TS classifier/copy.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.backend.services import league_scoring
from quant_sports_intel_models.football.nfl.fantasy import export_draft_board_json as EX

_ROOT = Path(__file__).resolve().parents[2]
_FANTASY = _ROOT / "quant_sports_intel_models/football/nfl/fantasy"
_FRONTEND = _ROOT / "frontend"


# ── payload builders — production SHAPES, not convenient ones ────────────────────────────────────
def _proj_row(pid: str, pos: str, pts: float | None = 100.0) -> dict:
    """A `projections.json` row. Prices its projection in `fpPpr` (the board files use `pts`)."""
    return {"id": pid, "name": f"Player {pid}", "pos": pos, "team": "DET", "fpPpr": pts}


def _board_row(pid: str, pos: str, pts: float | None = 100.0) -> dict:
    return {"id": pid, "name": f"Player {pid}", "pos": pos, "team": "DET", "pts": pts}


def _stage(tmp_path: Path, *, projections: list[dict], board: list[dict]) -> Path:
    out = tmp_path / "2026"
    out.mkdir(parents=True, exist_ok=True)
    (out / "projections.json").write_text(json.dumps({"season": 2026, "players": projections}))
    (out / "board_full_ppr_12.json").write_text(json.dumps(board))
    (out / "manifest.json").write_text(json.dumps({"season": 2026}))
    return out


def _complete(builder) -> list[dict]:
    return [builder(f"{p}-1", p) for p in EX.PROJECTABLE]


# ══ FAMILY 2: the publish guard ═════════════════════════════════════════════════════════════════
def test_a_complete_board_passes(tmp_path):
    """The positive control. Without it, a guard that refused everything would look like a pass."""
    out = _stage(tmp_path, projections=_complete(_proj_row), board=_complete(_board_row))
    EX.assert_published_position_coverage(out, 2026)  # must not raise


@pytest.mark.parametrize("missing", ["K", "DST", "TE", "QB"])
def test_a_board_missing_any_projectable_position_is_refused(tmp_path, missing):
    """⭐ THE RED PROOF THE STORY ASKS FOR: a board missing a PROJECTABLE position FAILS the guard.

    Parametrized across positions rather than pinned to K/DST — the guard's contract is about
    `PROJECTABLE`, and a version that special-cased the two positions of the day would silently stop
    covering a future one."""
    out = _stage(
        tmp_path,
        projections=[r for r in _complete(_proj_row) if r["pos"] != missing],
        board=[r for r in _complete(_board_row) if r["pos"] != missing],
    )
    with pytest.raises(SystemExit) as e:
        EX.assert_published_position_coverage(out, 2026)
    assert missing in str(e.value)
    assert "PUBLISH REFUSED" in str(e.value)


def test_the_guard_refuses_the_payload_that_actually_shipped(tmp_path):
    """The regression itself, in the shape it reached users: QB/RB/WR/TE present, K/DST absent."""
    rows = [_proj_row(f"{p}-{i}", p) for p in ("QB", "RB", "WR", "TE") for i in range(3)]
    out = _stage(tmp_path, projections=rows, board=_complete(_board_row))
    with pytest.raises(SystemExit) as e:
        EX.assert_published_position_coverage(out, 2026)
    msg = str(e.value)
    assert "projections.json" in msg
    assert "K" in msg and "DST" in msg
    # It must name the likely cause and the remedy, or the operator gets a refusal with no next step.
    assert "run_kdst_projection" in msg


def test_placeholder_rows_do_not_satisfy_the_guard(tmp_path):
    """⭐⭐ THE NON-VACUITY TEST, and the reason the guard counts PROJECTED rows rather than rows.

    `kdst_records` gap-fills a draftable-but-UNPROJECTED placeholder for every (pos, team) the
    projection did not cover, so the broken board still carried 32 K + 32 DST rows — with `pts:
    null`. A presence-only guard would have passed the exact artifact this exists to catch.

    ⚠️ If this test ever fails while `test_a_board_missing_any_projectable_position_is_refused`
    passes, the guard has been weakened to a row count and is now vacuous on the real defect."""
    board = [r for r in _complete(_board_row) if r["pos"] not in ("K", "DST")]
    board += [_board_row(f"K-{t}", "K", None) for t in ("DET", "KC")]
    board += [_board_row(f"DST-{t}", "DST", None) for t in ("DET", "KC")]
    out = _stage(tmp_path, projections=_complete(_proj_row), board=board)

    assert sum(1 for r in board if r["pos"] in ("K", "DST")) == 4, "the fixture must HAVE K/DST rows"
    with pytest.raises(SystemExit) as e:
        EX.assert_published_position_coverage(out, 2026)
    assert "board_full_ppr_12.json" in str(e.value)


def test_an_empty_staging_dir_is_a_failure_not_a_pass(tmp_path):
    """NF1.7 (a) — a check that found nothing to check did not run, and must never report clean."""
    out = tmp_path / "2026"
    out.mkdir()
    with pytest.raises(SystemExit) as e:
        EX.assert_published_position_coverage(out, 2026)
    assert "nothing to publish" in str(e.value)


def test_an_unreadable_staged_file_is_a_failure_not_a_pass(tmp_path):
    out = _stage(tmp_path, projections=_complete(_proj_row), board=_complete(_board_row))
    (out / "projections.json").write_text("{not json")
    with pytest.raises(SystemExit) as e:
        EX.assert_published_position_coverage(out, 2026)
    assert "UNREADABLE" in str(e.value)


def test_the_manifest_is_not_position_checked(tmp_path):
    """The manifest carries no player rows — checking it would fail every export for a wrong reason."""
    out = _stage(tmp_path, projections=_complete(_proj_row), board=_complete(_board_row))
    EX.assert_published_position_coverage(out, 2026)


# ── the guard is WIRED, and wired BEFORE the upload (NF-C0e: wired ≠ invoked) ────────────────────
def test_the_guard_runs_before_the_publish_decision():
    """⭐ A guard `main` never calls is decoration, and one called AFTER `_maybe_publish` would page
    about a board that had already reached users.

    ⚠️ ANCHORED ON THE CALL FORM (`…(out_dir, args.season)`), NOT THE FUNCTION NAME. The first cut
    matched `assert_published_position_coverage(out_dir`, which the DEFINITION line
    `def assert_published_position_coverage(out_dir: Path, …)` also satisfies — so deleting the call
    outright left this test GREEN, matching the def and comparing its position instead. Caught by
    `nf_k1_red_proof.py`, not by the suite (DSR-CONV #690: a name is not a call site)."""
    src = _source_without_comments(_FANTASY / "export_draft_board_json.py")
    call = "assert_published_position_coverage(out_dir, args.season)"
    assert call in src, "main() must CALL the coverage guard (wired ≠ invoked)"
    assert src.index(call) < src.index("_maybe_publish(out_dir"), \
        "the coverage guard must run BEFORE the upload decision"


def test_the_guard_has_no_env_var_escape_hatch():
    """INC-39 — an env backdoor left set turns the guard off silently and permanently. Widening
    `PROJECTABLE` is the reviewable way to publish fewer positions."""
    src = _source_without_comments(_FANTASY / "export_draft_board_json.py")
    body = src[src.index("def assert_published_position_coverage"):]
    body = body[: body.index("\ndef ")]
    assert "environ" not in body and "getenv" not in body


# ══ FAMILY 1: the cause — local-first, then the lake ═════════════════════════════════════════════
def test_load_kdst_prefers_the_local_artifact(tmp_path, monkeypatch):
    """LOCAL-FIRST is what keeps a laptop build byte-identical to what it produced before NF-K1."""
    import pandas as pd

    from quant_sports_intel_models.football.nfl.fantasy import run_league_board as RLB

    pd.DataFrame({"player_id": ["local"], "position": ["K"]}).to_parquet(
        tmp_path / "nfl_fantasy_kdst_projections_2026.parquet")
    monkeypatch.setattr(RLB, "load_kdst_lake", lambda season: pytest.fail("must not reach the lake"))
    assert RLB.load_kdst(tmp_path, 2026)["player_id"].tolist() == ["local"]


def test_load_kdst_falls_back_to_the_lake_when_the_local_artifact_is_absent(tmp_path, monkeypatch):
    """🔴 THE FIX. On the box the parquet is gitignored → absent from the image → this path is the
    ONLY one that reaches the K/DST projection, which the lake already holds."""
    import pandas as pd

    from quant_sports_intel_models.football.nfl.fantasy import run_league_board as RLB

    monkeypatch.setattr(RLB, "load_kdst_lake",
                        lambda season: pd.DataFrame({"player_id": ["lake"], "position": ["K"]}))
    assert not (tmp_path / "nfl_fantasy_kdst_projections_2026.parquet").exists()
    assert RLB.load_kdst(tmp_path, 2026)["player_id"].tolist() == ["lake"]


def test_load_kdst_honours_an_explicit_from_lake(tmp_path, monkeypatch):
    import pandas as pd

    from quant_sports_intel_models.football.nfl.fantasy import run_league_board as RLB

    pd.DataFrame({"player_id": ["local"]}).to_parquet(
        tmp_path / "nfl_fantasy_kdst_projections_2026.parquet")
    monkeypatch.setattr(RLB, "load_kdst_lake", lambda season: pd.DataFrame({"player_id": ["lake"]}))
    assert RLB.load_kdst(tmp_path, 2026, from_lake=True)["player_id"].tolist() == ["lake"]


@pytest.mark.parametrize("module", ["export_draft_board_json.py", "run_league_board.py"])
def test_every_kdst_call_site_uses_the_fallback_loader(module):
    """⭐ THE REGISTRY THAT MAKES THE FIX COMPLETE. Two call sites read this artifact and BOTH were
    local-only, so both dropped the positions. A third that reached for `load_kdst_local` would
    silently reintroduce the whole defect on its own surface (INC-38's per-caller-flag lesson).

    Matched on a CALL form, never on a bare name: this repo names things after the functions they
    describe, and a docstring mentioning `load_kdst_local` must not satisfy a guard about calls
    (DSR-CONV #690)."""
    src = _source_without_comments(_FANTASY / module)
    assert re.search(r"\bload_kdst\s*\(", src), f"{module} must load K/DST"
    local_calls = re.findall(r"\bload_kdst_local\s*\(", src)
    if module == "run_league_board.py":
        # its own definition + the delegation inside `load_kdst` are the only legitimate mentions
        assert not re.search(r"=\s*load_kdst_local\s*\(", src), "no caller may bind the local-only read"
    else:
        assert local_calls == [], f"{module} still calls the local-only K/DST read"


# ══ FAMILY 3: the three causes ══════════════════════════════════════════════════════════════════
def test_published_positions_is_read_off_the_board_not_declared():
    """⭐ Derived, never declared. Returning `PROJECTABLE_POSITIONS` would have reported K and DST as
    published for the whole outage — the "documented ≠ actually served" class."""
    board = [{"pos": p} for p in ("QB", "RB", "WR", "TE")]
    assert league_scoring.published_positions(board) == ["QB", "RB", "WR", "TE"]
    assert "K" not in league_scoring.published_positions(board)


def test_published_positions_reports_a_complete_board():
    board = [{"pos": p} for p in league_scoring.PROJECTABLE_POSITIONS]
    assert league_scoring.published_positions(board) == list(league_scoring.PROJECTABLE_POSITIONS)


def test_published_positions_folds_aliases():
    """A stored board row may carry `D/ST` or `PK`; the client compares against canonical codes."""
    assert league_scoring.published_positions([{"pos": "D/ST"}, {"pos": "PK"}]) == ["K", "DST"]


def test_the_three_projectable_declarations_agree():
    """The exporter, the API and the client each name the projectable set. A surface comparing a
    roster position against a set that has drifted from the exporter's would mis-explain every row
    at the position that drifted."""
    ts = (_FRONTEND / "lib/league-config.ts").read_text()
    m = re.search(r"export const POSITIONS = \[([^\]]*)\]", ts)
    assert m, "could not find the client's POSITIONS"
    client = tuple(x.strip().strip('"').strip("'") for x in m.group(1).split(",") if x.strip())
    assert client == EX.PROJECTABLE == league_scoring.PROJECTABLE_POSITIONS


def test_the_client_classifier_distinguishes_all_three_causes():
    """The frontend piece, source-inspected (its behaviour is covered by the Playwright spec).

    ⚠️ Each clause is asserted on its OWN, because they are `if`-chained: a fixture that trips two
    of them proves neither (NF-D17)."""
    src = _source_without_comments(_FRONTEND / "lib/league-scoring.ts")
    body = src[src.index("export function classifyUnmatched"):]
    body = body[: body.index("\nexport ", 1)] if "\nexport " in body[1:] else body
    for cause in ("not-projected", "unknown", "unresolved", "not-published"):
        assert f'"{cause}"' in body, f"classifyUnmatched cannot return {cause}"


def test_an_unknown_board_position_set_does_not_claim_a_cause():
    """⭐ THE DEPLOY-SKEW CLAUSE. An older API sends no `board_positions`; if that stood in for "no
    position is published", every unmatched row would claim "we have not published this position" —
    a confident, wrong, product-wide cause. Not knowing must report as not knowing."""
    src = _source_without_comments(_FRONTEND / "lib/league-scoring.ts")
    body = src[src.index("export function classifyUnmatched"):]
    assert 'if (!published) return "unknown"' in body

    # …and the hook must not paper over it with `?? []`, which is what would defeat the clause above.
    hook = _source_without_comments(_FRONTEND / "lib/fantasy-queries.ts")
    assert "board_positions ?? null" in hook
    assert "board_positions ?? []" not in hook


def test_the_server_reports_unknown_positions_as_null_not_empty(monkeypatch):
    """Same distinction on the server half: `[]` is a real answer ("nothing is published"), `None`
    is "we could not read it", and only the first licenses the "not published" wording downstream.

    ⚠️ BEHAVIOURAL, not source-inspected. The first cut asserted `"return None" in body` — which the
    function's OTHER `return None` satisfied, so flipping the exception path to `return []` left the
    test GREEN. Driving the real function is what distinguishes the two paths (found by the RED
    proof, not by the suite)."""
    router = pytest.importorskip("app.backend.routers.fantasy")

    def _boom(season):
        raise RuntimeError("S3 down")

    monkeypatch.setattr(router, "_full_projections", _boom)
    assert router._published_positions(2026) is None, \
        "an unreadable projections blob must report None ('unknown'), never [] ('none published')"

    # …and a board that IS readable reports what it carries, so the None above is not vacuous.
    monkeypatch.setattr(router, "_full_projections",
                        lambda season: {"players": [{"pos": "QB"}, {"pos": "K"}]})
    assert router._published_positions(2026) == ["QB", "K"]


def test_only_the_unresolved_cause_suggests_a_reimport():
    """⛔ No cell may promise a fix it cannot deliver. Telling a user to re-import a roster whose
    position we never published sends them round a loop that cannot terminate.

    ⚠️ NEGATION-AWARE, AND THAT IS NOT A DETAIL — the first cut of this test was a bare substring
    scan and it FAILED on our own honest hedge, "re-importing will not change it". The cheapest way
    to pass a negation-blind scan is to DELETE the sentence that stops the user wasting a re-import,
    i.e. the guard would have made the copy worse (the E9.61 negation-blind-denylist lesson).
    What is forbidden is an AFFIRMATIVE suggestion; a mention that explicitly negates it is the
    point of the copy."""
    copy = _load_ts_consts(_FRONTEND / "lib/fantasy-claim-copy.ts")
    detail = copy["UNMATCHED_DETAIL"]
    assert re.search(r"re-import\w*\s+(the league\s+)?usually fixes", detail["unresolved"].lower()), \
        "the one cause a re-import DOES fix must say so"
    for cause in ("not-published", "not-projected"):
        text = detail[cause].lower()
        for m in re.finditer(r"re-import\w*", text):
            tail = text[m.end(): m.end() + 40]
            assert re.match(r"\s+(will not|won't|does not|doesn't|cannot|can't)", tail), (
                f"{cause} mentions a re-import without negating it: ...{text[m.start():][:60]!r}")


def test_the_not_published_copy_owns_the_gap():
    """It must read as OUR gap. "We could not match" on a position we never shipped is the wording
    that sent two investigations at a name join that was working."""
    copy = _load_ts_consts(_FRONTEND / "lib/fantasy-claim-copy.ts")
    text = copy["UNMATCHED_DETAIL"]["not-published"].lower()
    assert "we have not published" in text
    assert "not a problem with your roster" in text


def test_the_new_copy_passes_the_claim_denylist():
    """Every claim-bearing string on a fantasy surface is screened (NF-TR1). New copy is not exempt."""
    from quant_sports_intel_models.football.nfl.fantasy import export_track_record_json as TR

    copy = _load_ts_consts(_FRONTEND / "lib/fantasy-claim-copy.ts")
    strings = list(copy["UNMATCHED_LABEL"].values()) + list(copy["UNMATCHED_DETAIL"].values())
    assert strings, "the denylist screen found no NF-K1 copy to screen (vacuous)"
    for s in strings:
        hits = [t for t in TR._CLAIM_DENYLIST if t in s.lower()]
        assert not hits, f"denylisted term(s) {hits} in NF-K1 copy: {s!r}"


def test_the_table_cell_and_the_footnote_share_one_classifier():
    """E9.61 — two renderers of one field are two rule sets. The cell and the card footnote must
    both go through `classifyUnmatched`, or they are free to disagree on the same screen."""
    src = _source_without_comments(_FRONTEND / "components/fantasy/my-teams.tsx")
    # ⚠️ The LABEL ITSELF must be derived from the classifier. A count of `classifyUnmatched(` calls
    # is not enough: the cell calls it three times (label, tooltip, `data-cause`), so replacing the
    # rendered LABEL with a hardcoded string left two calls standing and the count-based version of
    # this test GREEN — the guard passed on the exact regression it names (found by the RED proof).
    assert "UNMATCHED_LABEL[classifyUnmatched(" in src, \
        "the cell's label must come from the classifier, not a hardcoded string"
    assert "UNMATCHED_DETAIL[classifyUnmatched(" in src, "the tooltip must come from the classifier"
    assert "unmatchedFootnote(" in src
    # the bare one-size-fits-all sentence must be gone from the component
    assert "a name we could not resolve, or a player we do not" not in src


# ── helpers ─────────────────────────────────────────────────────────────────────────────────────
def _source_without_comments(path: Path) -> str:
    """Source with comments stripped.

    INC-38: a source-inspection guard a COMMENT can satisfy is vacuous — and this repo writes long
    explanatory comments directly above the code they describe, so every one of these guards would
    otherwise be satisfiable by the prose explaining it. Line comments are stripped BEFORE block
    comments (a `//` inside a block comment is not a line comment)."""
    src = path.read_text()
    if path.suffix in (".ts", ".tsx"):
        src = re.sub(r"(?m)^\s*//.*$", "", src)
        src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
        return src
    return re.sub(r"(?m)^\s*#.*$", "", src)


def _load_ts_consts(path: Path) -> dict[str, dict[str, str]]:
    """The two `Record<UnmatchedCause, string>` literals, parsed out of the TS module.

    Reads the SHIPPED strings rather than restating them here: a test that carried its own copy
    would pass while the rendered wording drifted (the NF-C0e restatement class)."""
    src = path.read_text()
    out: dict[str, dict[str, str]] = {}
    for name in ("UNMATCHED_LABEL", "UNMATCHED_DETAIL"):
        m = re.search(rf"export const {name}[^=]*= \{{(.*?)\n\}}", src, flags=re.S)
        assert m, f"could not find {name} in {path.name}"
        entries = re.findall(r'"?([a-z-]+)"?:\s*\n?\s*"((?:[^"\\]|\\.)*)"', m.group(1))
        assert entries, f"{name} parsed to nothing — the guard would be vacuous"
        out[name] = {k: v for k, v in entries}
    return out
