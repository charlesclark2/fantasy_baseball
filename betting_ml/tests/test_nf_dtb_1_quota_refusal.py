"""NF-DTB-1 Half A — the free-league cap must read as a LIMIT, never as a broken save.

══ THE DIAGNOSIS, MEASURED RATHER THAN ASSUMED ═══════════════════════════════════════════════════

The report was "a league create at the free-league cap returns a generic 'Could not save league'
(400) instead of the 409 cap error", and it named two candidate paths: the backend raising the wrong
status, or the frontend collapsing a 409. It is the SECOND, and the first is exonerated by
measurement rather than by reading:

  · `POST /fantasy/leagues` at the cap was driven against the REAL ASGI app on BOTH payload shapes a
    user can produce — the manual editor's config and the importer's (which carries
    `league_rosters`, `source_platform`, the roster stamps). Both answer **409** with
    "You can save 1 league on your current plan." The 400 "Could not save league" branch is the
    NON-quota fallback and never fires here. `test_the_backend_answers_the_cap_with_409_...` below
    is that measurement, kept as a clause so a future edit to `create_league` cannot quietly move
    the status out from under the client's branch.

  · The collapse was at the FETCH BOUNDARY. `apiFetch` threw a bare `Error` carrying only the
    server's `detail` and **discarded `res.status`**, so no caller COULD distinguish a 409 from a
    400 — and both surfaces rendered every failure through one generic line ("Could not save. …" in
    the editor, the amber banner in the importer). A user who had just filled in a long form was
    told their save was broken, with nothing naming the limit and no way past it. That is E8.6's
    "saving is broken" shape pointed at a paywall, and it is the same class this file's boundary
    already records for the MESSAGE (`errorMessage`'s own docstring) one field over: the information
    was correct and complete at the source and got dropped one layer out.

⚠️ WHY THE REFUSAL IS REACHABLE AT ALL, given both surfaces disable their control at the cap. That
check is ADVISORY and reads a CACHED list — `useSavedLeagues` carries a 60s stale time and
`retry: false`, and its `data` is `undefined` both while loading and ON ERROR, each of which reads
as "0 leagues saved" and re-enables Save. The server's 409 is the real gate; what it renders as is
this story.

⭐ WHAT IS PINNED WHERE. The BEHAVIOUR a user sees is asserted in the browser
(`frontend/e2e/specs/free-league.spec.ts`, on RENDERED output per NF-C4, both halves: at-cap → the
quota notice, forced non-quota failure → the generic line). This file pins the two things a browser
cannot see — that the server still answers 409, and that the status survives the boundary — plus the
ADDITIVITY of the new error type (NF-C0: same `message`, still an `Error`, so no existing caller
changed meaning).

⭐ ONE FIXTURE PER CLAUSE (NF-D17 §7); `nf_dtb_1_red_proof.py` proves each goes red on its own break.
⭐ COMMENTS ARE STRIPPED BEFORE EVERY SOURCE MATCH (INC-38) — the modules here explain the defect by
quoting the code that caused it, so a raw substring scan would be satisfied by the prose about it.

Pure/offline (fast gate): source reads + the real ASGI app with the storage boundary stubbed.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_API_TS = _REPO / "frontend/lib/api.ts"
_ENTITLEMENTS_TS = _REPO / "frontend/lib/entitlements.ts"
_EDITOR_TSX = _REPO / "frontend/components/fantasy/league-settings-editor.tsx"
_IMPORT_TSX = _REPO / "frontend/components/fantasy/league-import.tsx"
_CLAIM_COPY_TS = _REPO / "frontend/lib/fantasy-claim-copy.ts"
_FREE_LEAGUE_SPEC = _REPO / "frontend/e2e/specs/free-league.spec.ts"

#: The two league CREATE surfaces. Both must branch, because the tier is enforced by WHICH COMPONENT
#: RENDERS — the freemium build's own lesson (#681 gated one of three renderers and looked done) and
#: the reason `LeagueQuotaNotice` is a shared component rather than a block of JSX in each editor.
#: ⚠️ PINNED AS EXHAUSTIVE below, so a THIRD create path cannot ship without joining this list.
_CREATE_SURFACES = {
    "league-settings-editor.tsx": _EDITOR_TSX,
    "league-import.tsx": _IMPORT_TSX,
}


def _without_imports(src: str) -> str:
    """⭐ THE IMPORT LINE IS NOT A USE — and this helper exists because the RED PROOF caught the
    first cut of the two surface clauses below being satisfied by it alone.

    `import { isLeagueQuotaRefusal } from "@/lib/entitlements"` contains the identifier, so a naive
    `"isLeagueQuotaRefusal" in src` stayed GREEN with the only CALL deleted — the NF-C0e
    "wired ≠ invoked" shape, in a guard written to prevent exactly this story's defect from
    regressing. Imports come off before any usage scan.
    """
    return re.sub(r"^\s*import\s[\s\S]*?from\s+[\"'][^\"']+[\"']\s*$", "", src, flags=re.M)


def _strip_ts_comments(src: str) -> str:
    """INC-38 — a source guard a COMMENT can satisfy cannot fail, and here a comment could also make
    one fire falsely: every module below quotes the retired `throw new Error(...)` line inside the
    paragraph explaining why it is gone.

    Line comments come off FIRST (carried verbatim from `test_nf_c8_availability_flag_copy`): a `//`
    comment containing a path glob opens a `/*` that a block-first stripper closes at the next
    genuine `*/`, silently deleting the live lines between. `(?<!:)` keeps `https://` intact.
    """
    src = re.sub(r"(?<!:)//[^\n]*", "", src)
    return re.sub(r"/\*.*?\*/", "", src, flags=re.S)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 1. The backend — exonerated by measurement, and pinned so it stays exonerated
# ══════════════════════════════════════════════════════════════════════════════════════════════════

#: The editor's output. Deliberately a REAL `LeagueSave` (it validates that a config has at least one
#: starting slot), so a trimmed fixture cannot fail these at the validator instead of at the cap.
_EDITOR_BODY = {
    "name": "Sunday Money",
    "n_teams": 10,
    "scoring": {"per_stat": {"rec": 0.5, "pass_yds": 0.04, "rush_yds": 0.1}},
    "roster": [
        {"name": "QB", "count": 1, "eligible": ["QB"]},
        {"name": "RB", "count": 2, "eligible": ["RB"]},
        {"name": "WR", "count": 3, "eligible": ["WR"]},
        {"name": "TE", "count": 1, "eligible": ["TE"]},
        {"name": "BENCH", "count": 6, "eligible": [], "bench": True},
    ],
}

#: The IMPORTER's output — the same config plus everything `saveImported` stamps on it. A SECOND
#: shape rather than a second copy of the first: the report could have been about a payload the
#: editor never produces, and a single-shape test could not have told those apart.
_IMPORT_BODY = {
    **_EDITOR_BODY,
    "name": "Imported league",
    "source_platform": "sleeper",
    "source_league_id": "1234567890",
    "imported_at": "2026-08-23T00:00:00Z",
    "source_team_key": "t1",
    "source_team_name": "My Team",
    "imported_roster": [{"name": "A B", "position": "RB", "team": "DET"}],
    "roster_synced_at": "2026-08-23T00:00:00Z",
    "league_rosters": [
        {
            "team_key": f"t{i}",
            "team_name": f"Team {i}",
            "players": [{"name": f"P{j}", "position": "WR", "team": "SF"} for j in range(15)],
        }
        for i in range(12)
    ],
    "league_rosters_synced_at": "2026-08-23T00:00:00Z",
}


@pytest.fixture()
def asgi(monkeypatch):
    """The real app with ONLY the storage boundary stubbed — routing, both dependencies and the
    entitlement resolver are the real thing. Reuses `test_g100_c1_free_league`'s harness rather than
    forking it: a second copy of the fake table is a second place for the cap's semantics to drift.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_nf_dtb1_g100_harness", Path(__file__).with_name("test_g100_c1_free_league.py")
    )
    harness = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(harness)

    from app.backend.services import cost_guardrails, dynamo, jwt_verify

    # The per-IP limiter is process-global and stateful; see the harness's own note.
    cost_guardrails.get_limiter().reset()

    tables: dict[str, object] = {}
    holder = {"user": None}
    real_list = dynamo.list_fantasy_leagues

    def table_for(user_id):
        return tables.setdefault(user_id, harness._FakeTable())

    def list_leagues(user_id):
        holder["user"] = user_id
        monkeypatch.setattr(dynamo, "_users_table", lambda: table_for(user_id), raising=False)
        return real_list(user_id)

    monkeypatch.setattr(dynamo, "list_fantasy_leagues", list_leagues)
    monkeypatch.setattr(dynamo, "_users_table", lambda: table_for(holder["user"] or "anon"))
    monkeypatch.setattr(jwt_verify, "_fetch_jwks", lambda: None)
    jwt_verify.reset_jwks_cache()
    return harness


@pytest.mark.parametrize(
    "shape,body",
    [("editor", _EDITOR_BODY), ("importer", _IMPORT_BODY)],
)
def test_the_backend_answers_the_cap_with_409_not_the_generic_400(asgi, shape, body):
    """⭐ THE MEASUREMENT THAT EXONERATED THE BACKEND — and the clause that keeps it exonerated.

    The client now BRANCHES on this status (`isLeagueQuotaRefusal`), so `create_league` returning
    400 for the cap would silently un-fix the whole story: the refusal would fall back through the
    generic line with no test anywhere going red. That coupling is why this lives here rather than
    only in `test_g100_c1_free_league.py`, and why it is run on BOTH payload shapes a real user can
    produce — the report could have been about a payload the editor never sends.
    """
    uid = f"nf-dtb1-{shape}"
    ev = asgi._event(sub=uid)

    first, _ = asgi._call("/fantasy/leagues", method="POST", body=body, aws_event=ev)
    assert first == 201, f"the {shape} payload could not save a FIRST league — the test is vacuous"

    status, detail = asgi._call(
        "/fantasy/leagues", method="POST", body={**body, "name": "Second"}, aws_event=ev
    )
    assert status == 409, (
        f"a create at the cap ({shape} payload) answered {status}, not 409 — the client branches on "
        "409 to render the quota notice, so this silently restores the generic-failure defect"
    )
    rendered = json.dumps(detail)
    assert "Could not save league" not in rendered, (
        "the cap came back through the GENERIC 400 branch — a limit reported as a fault"
    )
    assert "1 league" in rendered, "the refusal must quote the CALLER's own quota"


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 2. The fetch boundary — the status must survive it
# ══════════════════════════════════════════════════════════════════════════════════════════════════


def test_every_failed_response_throws_an_error_carrying_its_status():
    """⭐ THE ROOT DEFECT. `throw new Error(await errorMessage(res))` discards `res.status`, so a 409
    and a 400 arrive at every call site as the same object and NO caller can branch — which is why
    a component-local fix would have been the wrong shape.

    Asserted as "no bare throw survives" rather than "an ApiError appears somewhere": the second
    passes with one of the two throw sites left un-migrated, and `cdnFetch` is the one a future
    public surface would reach for.
    """
    src = _strip_ts_comments(_API_TS.read_text())
    throws = re.findall(r"if \(!res\.ok\) throw new (\w+)\(", src)
    assert throws, "no `if (!res.ok) throw` found in api.ts — this clause is pinned to nothing"
    assert set(throws) == {"ApiError"}, (
        f"a failed response is thrown as {sorted(set(throws))} — a bare Error discards res.status, "
        "and the free-league cap becomes indistinguishable from a save fault"
    )
    assert "new ApiError(res.status," in src, "ApiError was constructed without the real status"


def test_the_new_error_type_is_additive_so_no_existing_caller_changed_meaning():
    """NF-C0 additivity, at a client boundary every surface in the app already reads.

    ⚠️ THE RISK IS REAL AND WIDE. Dozens of call sites do `e instanceof Error` / `(e as Error).message`,
    and `league-import.tsx` REGEX-MATCHES the message (`/^API error \\d+$/`) to decide whether the
    server said anything useful. A subclass that changed either property would have broken error
    handling across the app while this story's own specs stayed green.
    """
    src = _strip_ts_comments(_API_TS.read_text())
    assert re.search(r"export class ApiError extends Error\b", src), (
        "ApiError must subclass Error — every existing `e instanceof Error` caller depends on it"
    )
    body = src.split("export class ApiError extends Error", 1)[1].split("\n}", 1)[0]
    assert "super(message)" in body, (
        "ApiError must pass `message` through UNCHANGED; rewriting it here would silently change "
        "what every surface in the app renders on a failure"
    )


def test_the_status_is_interpreted_at_the_call_site_not_in_a_shared_lookup():
    """⛔ A shared status→meaning table is where a status quietly acquires a WRONG meaning: 409 on
    `POST /fantasy/leagues` is the league cap, and a 409 anywhere else is something else entirely.
    So `api.ts` reports the fact (`apiErrorStatus`) and the league module owns the reading.
    """
    api = _strip_ts_comments(_API_TS.read_text())
    assert "export function apiErrorStatus" in api
    assert "quota" not in api.lower(), (
        "api.ts named the league quota — the interpretation belongs at the call site"
    )
    ent = _strip_ts_comments(_ENTITLEMENTS_TS.read_text())
    assert re.search(r"export function isLeagueQuotaRefusal", ent), (
        "the league-cap reading of a 409 has no single owner"
    )
    assert "apiErrorStatus(e) === 409" in ent, (
        "isLeagueQuotaRefusal no longer keys on the 409 the server actually answers"
    )


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 3. Both create surfaces — and BOTH outcomes on each
# ══════════════════════════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("name", sorted(_CREATE_SURFACES))
def test_each_create_surface_separates_a_quota_refusal_from_a_save_fault(name):
    """Both halves, per surface. A surface that branched but dropped its generic line would report a
    genuine server fault as a billing limit — worse than the original bug, because it sends the user
    to checkout for an outage. The rendered behaviour is asserted in the browser; this pins that the
    branch and its fallback both still EXIST, on each door.
    """
    # ⚠️ IMPORTS STRIPPED FIRST — see `_without_imports`: the red proof found the first cut of both
    # clauses below passing on the import line alone, i.e. green with every CALL deleted.
    src = _without_imports(_strip_ts_comments(_CREATE_SURFACES[name].read_text()))
    assert "isLeagueQuotaRefusal(" in src, (
        f"{name} does not CALL isLeagueQuotaRefusal — it cannot distinguish the free-league cap "
        "from a save fault"
    )
    assert "LEAGUE_QUOTA_REFUSED_DETAIL" in src, (
        f"{name} renders the pre-emptive at-the-control wording for a refusal that already happened "
        "— it must say nothing was saved"
    )
    # The generic path survives: `quotaRefused` GATES it rather than replacing it.
    assert "quotaRefused" in src and re.search(r"!\s*quotaRefused|else\s", src), (
        f"{name} appears to have replaced its generic failure line rather than gated it"
    )


def test_the_create_surface_registry_is_still_exhaustive():
    """INC-38 — a per-surface fix fails exactly where the registry is incomplete.

    Derived from the app rather than remembered: every component calling `useSaveLeague` creates or
    updates a league, so a THIRD door added later joins `_CREATE_SURFACES` or turns this red.
    """
    components = _REPO / "frontend/components"
    callers = {
        p.name
        for p in components.rglob("*.tsx")
        if "useSaveLeague()" in _strip_ts_comments(p.read_text())
    }
    assert callers, "no `useSaveLeague()` caller found — this clause is pinned to nothing"
    assert callers == set(_CREATE_SURFACES), (
        f"the league-create surfaces moved: {sorted(callers)} vs {sorted(_CREATE_SURFACES)}. A new "
        "create path must render the quota refusal too — the tier is enforced by which component "
        "renders."
    )


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 4. The refusal copy
# ══════════════════════════════════════════════════════════════════════════════════════════════════


def test_the_refusal_says_nothing_was_saved_and_carries_no_overclaim():
    """⭐ THE SENTENCE THAT SEPARATES A LIMIT FROM A LOST FORM. The at-the-control notice is
    preventative — nothing has been attempted — so it never has to answer "did my work just
    disappear?". This one fires AFTER a round trip and does.
    """
    src = _CLAIM_COPY_TS.read_text()
    m = re.search(r'export const LEAGUE_QUOTA_REFUSED_DETAIL\s*=\s*\n?\s*"((?:[^"\\]|\\.)*)"', src)
    assert m, "LEAGUE_QUOTA_REFUSED_DETAIL is missing"
    detail = m.group(1)
    low = detail.lower()
    assert "nothing was saved" in low, (
        "the refusal does not say the save did not land — the one fact that makes it recoverable"
    )
    assert "one personalized league" in low, "the refusal does not name the limit state"

    from quant_sports_intel_models.football.nfl.fantasy import export_track_record_json as ex

    hits = [t for t in ex._CLAIM_DENYLIST if t.lower() in low]
    assert hits == [], f"the refusal copy carries denied claims: {hits}"


def test_the_browser_asserts_BOTH_outcomes_on_rendered_output():
    """NF-C4 — a frontend guard that reads source tests that someone TYPED a string. The behaviour
    clause is the browser's, and it must cover the non-quota twin too: without it, "show the quota
    notice on any save error" passes every at-cap assertion.
    """
    spec = _FREE_LEAGUE_SPEC.read_text()
    assert "reads as a LIMIT, not as a failure" in spec, (
        "the NF-DTB-1 browser specs are gone — nothing asserts the RENDERED refusal"
    )
    for clause in (
        "editor: a 409 shows the quota notice",
        "editor: a NON-quota failure still shows the generic error",
        "import: a 409 shows the quota notice",
        "import: a NON-quota failure still shows the amber error line",
    ):
        assert clause in spec, f"the browser suite lost its `{clause}` half"
