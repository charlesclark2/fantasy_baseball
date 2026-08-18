"""NF-C4 — the CUSTOM BIG BOARD: the server half.

The surface lets a user reorder, tier and tag our published board and keep the result. Almost all of
its *behaviour* is in the browser and is pinned there (`frontend/e2e/specs/fantasy-big-board.spec.ts`
runs the real ordering functions and drives a real drag). What is pinned HERE is everything a
browser cannot see:

  1. THE GATE. The three routes sit behind `require_fantasy_access` — the same entitlement as the
     draft and auction optimizers — and they must never reach the CDN allowlist, a public cache
     rule, or the degrade-mode floor. A saved board is paid, per-caller data.

  2. THE SHARED ITEM BUDGET, WHICH IS THE WHOLE RISK. All of a user's state — leagues, rosters,
     portfolio, platform tokens, MLB leagues and now big boards — lives in ONE 400 KB DynamoDB item.
     An overflow there is not a degraded feature: DynamoDB refuses the entire `UpdateItem`, so the
     row stops accepting every future write. The budget is therefore JOINT (both writers see both
     attributes), it is checked BEFORE the write, and a board that does not fit is REFUSED WHOLE —
     never truncated into a plausible-looking short ranking, never paid for by evicting something
     the caller did not ask us to touch.

  3. THE WRITE/READ VALIDATOR SPLIT (E9.49). A rule tightened for saves must never make an
     already-stored board unreadable — that defect blanked the entire bet log once.

⚠️ EACH AND-COMPOSED RULE GETS ITS OWN ISOLATING FIXTURE (NF-D17 §7): the fixture satisfies every
OTHER clause, so only the named one can flip the result. A fixture that trips two clauses tests
neither, because the first refusal hides the second.

⚠️ EVERY SOURCE ASSERTION STRIPS COMMENTS FIRST — otherwise the explanatory comment written above
each change satisfies the guard with the change DELETED (INC-38, shipped once in this repo).

RED-PROVEN against deliberately-broken source: `uv run python betting_ml/tests/nf_c4_red_proof.py`.

Pure/offline (fast gate): source inspection, the real Pydantic models, the real storage writer over
an in-memory table, and the real ASGI app with only its two IO boundaries stubbed. No DuckDB, no S3,
no network, no `pipeline` import.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.backend.models import fantasy as models
from app.backend.services import cost_guardrails, dynamo

_REPO = Path(__file__).resolve().parents[2]
_FRONTEND = _REPO / "frontend"
_DYNAMO_SRC = _REPO / "app/backend/services/dynamo.py"
_ROUTER_SRC = _REPO / "app/backend/routers/fantasy.py"

pytestmark = pytest.mark.skipif(not _FRONTEND.is_dir(), reason="frontend/ not present")


def _py(path: Path) -> str:
    """Python source with `#` comments and docstrings removed.

    ⚠️ THE DOCSTRING PASS IS NOT OPTIONAL HERE. Every function in this feature carries a long
    explanatory docstring naming the exact constants and calls the clauses below assert on — so
    without stripping them, `"_fits_fantasy_budget" in src` is satisfied by prose and every source
    guard in this file would pass with the code deleted.
    """
    src = re.sub(r'"""[\s\S]*?"""', "", path.read_text())
    return "\n".join(re.sub(r"#.*$", "", ln) for ln in src.splitlines())


def _ts(rel: str) -> str:
    """Frontend source with comments stripped. Line comments BEFORE block comments (E9.61)."""
    text = (_FRONTEND / rel).read_text()
    text = "\n".join(re.sub(r"//.*$", "", ln) for ln in text.splitlines())
    return re.sub(r"/\*.*?\*/", "", text, flags=re.S)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 0. Non-vacuity — the fixtures every clause below depends on
# ══════════════════════════════════════════════════════════════════════════════════════════════


def test_the_sources_this_file_inspects_are_present_and_non_trivial():
    """⚠️ ANTI-VACUITY FIRST. Nearly every clause here is a substring check against source; a file
    that had moved or emptied would make the whole suite pass on nothing — the guard-that-cannot-
    fail class arriving through the fixture rather than through the assertion."""
    for src, name in ((_py(_DYNAMO_SRC), "dynamo.py"), (_py(_ROUTER_SRC), "routers/fantasy.py")):
        assert len(src) > 5_000, f"{name} read back as {len(src)} chars — the strip pass ate it"
    assert len(_ts("lib/big-board.ts")) > 2_000
    assert hasattr(dynamo, "put_fantasy_big_board")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. The gate
# ══════════════════════════════════════════════════════════════════════════════════════════════


def test_the_board_routes_are_on_the_fantasy_gated_router():
    """⭐ THE ROUTER OBJECT IS THE GATE. This codebase's standing rule is that an exemption is a
    separate router object, never a flag inside a gated one — so what has to be asserted is that
    these three routes were written on `router` (blanket `require_fantasy_access`) and not on
    `board_router` (the public one) or `personal_router` (the free personalization quota, which a
    caller with no fantasy entitlement has)."""
    src = _py(_ROUTER_SRC)
    for verb in ("get", "put"):
        assert f'@router.{verb}("/nfl/custom-boards")' in src, (
            f"the custom-board {verb.upper()} is not on the fantasy-gated router"
        )
    assert '@router.delete("/nfl/custom-boards/{board_key}"' in src
    for wrong in ("board_router", "personal_router", "public_router"):
        assert f'@{wrong}.get("/nfl/custom-boards")' not in src
        assert f'@{wrong}.put("/nfl/custom-boards")' not in src


@pytest.mark.parametrize("prefix", cost_guardrails._DEGRADE_ALLOWED_PREFIXES)
def test_the_custom_board_routes_are_not_in_the_degrade_floor(prefix):
    """⛔ The floor's promise is the FREE board plus the account. Paid personalization is precisely
    what degrade mode is for refusing.

    ⚠️ ALSO A PREFIX-COLLISION CHECK, which is the way this would actually go wrong. Matching is by
    `startswith`, and `/fantasy/nfl/board` is on the floor — so a route named `/fantasy/nfl/boards`
    would have inherited the floor silently, with nothing to read as a mistake. `custom-boards` does
    not, and this asserts it rather than trusting the name."""
    assert not "/fantasy/nfl/custom-boards".startswith(prefix), (
        f"the custom-board route is covered by the degrade-floor prefix {prefix!r}"
    )


@pytest.mark.parametrize("prefix", [r[0] for r in cost_guardrails._PUBLIC_CACHE_RULES])
def test_the_custom_board_routes_never_get_a_public_cache_header(prefix):
    """⛔ A SHARED CACHE ENTRY HERE WOULD HAND ONE USER'S BOARD TO ANOTHER.

    ⚠️ THE SAME PREFIX-COLLISION HAZARD AS THE DEGRADE FLOOR, with a worse consequence. Matching is
    `== prefix or startswith(prefix + "/")` and `/fantasy/nfl/board` is a public-cached prefix, so a
    route named `/fantasy/nfl/board/custom` would have inherited a 900s public TTL silently. It is
    ALSO defended structurally — every request here carries `Authorization`, and
    `cache_control_for` answers `private, no-store` unconditionally when it sees one — but a naming
    accident should not have to rely on the second line of defence.
    """
    path = "/fantasy/nfl/custom-boards"
    assert not (path == prefix or path.startswith(prefix + "/")), (
        f"the custom-board route is covered by the public cache prefix {prefix!r}"
    )
    # ...and the structural guarantee, asserted rather than trusted.
    assert (
        cost_guardrails.cache_control_for(path, has_authorization=True, status_code=200)
        == cost_guardrails.PRIVATE_CACHE_CONTROL
    )


def test_the_board_depth_control_states_no_row_count_of_its_own():
    """A "Whole board" option written as today's row count (858) is a claim about the BOARD dressed
    as a choice — and a wrong one the first time an export lands on 870 rows, with nothing in the
    product to contradict it. The depth resolves against the board's own length."""
    src = _ts("components/fantasy/big-board.tsx")
    assert "858" not in src, "the board depth control hardcodes a row count"
    assert "depth === ALL_ROWS ? ordered.length : depth" in src


def test_the_custom_board_routes_are_not_in_the_public_cdn_allowlist():
    """A per-caller payload in a shared edge cache hands one user's board to another. The CDN route
    is an allowlist, so the assertion is simply that nothing added an entry."""
    route = (_FRONTEND / "app/api/public/[...path]/route.ts").read_text()
    assert "custom-boards" not in route, (
        "a per-user saved board reached the anonymous CDN allowlist"
    )


def test_the_client_never_fetches_a_saved_board_through_the_cdn_arm():
    """⭐ THE ASYMMETRY IS THE POINT, and it is easy to break by copying the fetcher above it. Every
    generic-board fetcher in `lib/fantasy.ts` falls back to `cdnFetch` when there is no token; these
    must not, because the edge route strips `Authorization` by design — the request would arrive
    anonymous, and either 403 or (worse) pin a paid body into a public cache entry."""
    src = _ts("lib/fantasy.ts")
    block = src[src.index("export function listCustomBoards") :]
    assert "cdnFetch" not in block, "a saved-board fetcher reaches for the anonymous CDN arm"


def _call(path: str, method: str = "GET", *, body: dict | None = None, aws_event: dict | None = None):
    """Drive the REAL ASGI app. Returns (status, raw body).

    A source assertion says the routes were WRITTEN on the gated router; this says the running app
    actually refuses. Both are wanted — the first localises a mistake, the second proves it matters.
    """
    import anyio

    from app.backend.main import app

    payload = json.dumps(body or {}).encode() if body is not None else b""
    out: dict = {}
    parts: list[bytes] = []

    async def run():
        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.1"},
            "http_version": "1.1",
            "method": method,
            "scheme": "https",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "root_path": "",
            "headers": [(b"host", b"testserver"), (b"content-type", b"application/json")],
            "client": ("test", 1),
            "server": ("testserver", 443),
        }
        if aws_event is not None:
            scope["aws.event"] = aws_event

        async def receive():
            return {"type": "http.request", "body": payload, "more_body": False}

        async def send(message):
            if message["type"] == "http.response.start":
                out["status"] = message["status"]
            elif message["type"] == "http.response.body":
                parts.append(message.get("body", b""))

        await app(scope, receive, send)

    anyio.run(run)
    return out["status"], b"".join(parts)


def _event(groups: str):
    """The API Gateway authorizer context as Mangum delivers it."""
    return {
        "requestContext": {
            "authorizer": {"jwt": {"claims": {"sub": "sub-nf-c4", "cognito:groups": groups}}}
        }
    }


@pytest.fixture()
def limiter_reset():
    """⚠️ The per-IP limiter is PROCESS-GLOBAL and stateful, so it carries depletion across files and
    surfaces as payload-shape failures rather than as throttling (see `test_freemium_tier.py`)."""
    cost_guardrails.get_limiter().reset()
    return True


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("GET", "/fantasy/nfl/custom-boards", None),
        ("PUT", "/fantasy/nfl/custom-boards", {"config": "half_ppr", "size": 12}),
        ("DELETE", "/fantasy/nfl/custom-boards/half_ppr%7C12", None),
    ],
)
def test_a_caller_without_fantasy_entitlement_is_refused(method, path, body, limiter_reset):
    """Both doors: anonymous, and signed in WITHOUT the fantasy entitlement. A `beta_tester` keeps
    full betting access and has no fantasy — testing only the anonymous case would let a gate keyed
    on "is logged in" pass, which hands the paid half to every account."""
    anon, _ = _call(path, method, body=body)
    assert anon in (401, 403), f"anonymous reached {method} {path} (got {anon})"
    signed_in, _ = _call(path, method, body=body, aws_event=_event("[beta_tester]"))
    assert signed_in == 403, f"a non-fantasy account reached {method} {path} (got {signed_in})"


def test_a_subscriber_reaches_the_board_routes(table, limiter_reset):
    """⭐ THE NO-REGRESSION HALF — a gate that refused EVERYONE would satisfy the clause above."""
    status, raw = _call("/fantasy/nfl/custom-boards", aws_event=_event("[subscriber]"))
    assert status == 200, f"a subscriber lost their own saved boards (got {status})"
    assert json.loads(raw)["boards"] == []

    status, raw = _call(
        "/fantasy/nfl/custom-boards",
        "PUT",
        body={"config": "half_ppr", "size": 12, "order": ["a", "b"], "tags": {"a": "target"}},
        aws_event=_event("[subscriber]"),
    )
    assert status == 200, f"a subscriber could not save a board (got {status}: {raw[:200]!r})"
    saved = json.loads(raw)
    assert saved["board_key"] == "half_ppr|12"
    assert saved["order"] == ["a", "b"]

    status, raw = _call("/fantasy/nfl/custom-boards", aws_event=_event("[subscriber]"))
    assert [b["board_key"] for b in json.loads(raw)["boards"]] == ["half_ppr|12"], (
        "the saved board did not round-trip through the list endpoint"
    )


def test_a_board_too_large_to_store_answers_413_with_a_readable_sentence(table, limiter_reset):
    """⭐ THE REFUSAL IS PART OF THE PRODUCT, not an error to swallow. The surface renders `detail`
    verbatim in its save-status line, so it has to be a sentence written for a person and it has to
    say that nothing was changed."""
    table.item["fantasy_leagues"] = {"L1": {"blob": "x" * (dynamo.MAX_FANTASY_BYTES - 4_000)}}
    status, raw = _call(
        "/fantasy/nfl/custom-boards",
        "PUT",
        body={"config": "half_ppr", "size": 12, "order": [f"{i:010d}" for i in range(858)]},
        aws_event=_event("[subscriber]"),
    )
    assert status == 413, f"an unstorable board did not answer 413 (got {status})"
    detail = json.loads(raw)["detail"]
    assert "Nothing was changed" in detail
    assert detail.endswith("."), "the refusal is not a sentence a surface can render as-is"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. The shared item budget — the whole risk
# ══════════════════════════════════════════════════════════════════════════════════════════════


class _FakeTable:
    """The narrowest stand-in for the users table: the two fantasy attributes as plain dicts.

    `writes` counts real `SET`s so a clause can assert that a REFUSED save wrote NOTHING — which is
    the difference between "refused" and "refused after clobbering something".
    """

    def __init__(self):
        self.item: dict = {}
        self.writes = 0

    def get_item(self, Key):  # noqa: N803 — boto3's casing
        return {"Item": dict(self.item)}

    def update_item(self, Key, UpdateExpression, **kw):  # noqa: N803
        names = kw.get("ExpressionAttributeNames", {})
        values = kw.get("ExpressionAttributeValues", {})
        attr = names.get("#fl") or names.get("#bb")
        if "ConditionExpression" in kw:
            # `attribute_not_exists` — create the parent map only when it is genuinely absent.
            if attr in self.item:
                raise RuntimeError("ConditionalCheckFailedException")
            self.item[attr] = {}
            return {}
        key = names.get("#id") or names.get("#k")
        if UpdateExpression.startswith("REMOVE"):
            self.item.setdefault(attr, {}).pop(key, None)
            return {}
        self.item.setdefault(attr, {})[key] = values.get(":cfg") or values.get(":doc")
        self.writes += 1
        return {}


@pytest.fixture()
def table(monkeypatch):
    t = _FakeTable()
    monkeypatch.setattr(dynamo, "_users_table", lambda: t)
    return t


def _board_doc(n_ids: int, width: int = 10) -> dict:
    """A board document of a predictable size: `n_ids` player ids of `width` characters."""
    return {
        "config": "half_ppr",
        "size": 12,
        "order": [f"{i:0{width}d}" for i in range(n_ids)],
        "tier_breaks": [],
        "tags": {},
    }


def test_a_normal_board_is_stored_whole(table):
    """The other side of every refusal clause below — a rule that refused EVERYTHING would satisfy
    them all."""
    saved = dynamo.put_fantasy_big_board("u1", "half_ppr|12", _board_doc(858))
    assert saved["order"] == _board_doc(858)["order"], "a board that fits was altered on the way in"
    assert saved["board_key"] == "half_ppr|12"
    assert len(dynamo.list_fantasy_big_boards("u1")) == 1


def test_the_budget_is_joint_across_leagues_and_boards(table):
    """⭐⭐ THE CLAUSE THIS WHOLE STORY TURNS ON.

    Two features that each stay inside their own sub-limit can still jointly kill the row. The
    ceiling did not move when big boards were added, so BOTH writers have to see BOTH attributes —
    otherwise `MAX_FANTASY_LEAGUES_BYTES` (260 KB) plus a second 260 KB claim is 520 KB against a
    400 KB item.

    ⚠️ ITS OWN ISOLATING FIXTURE: the board being written is TINY, so nothing about this board's own
    size can refuse it. Only the pre-existing LEAGUE bytes can, which is the rule under test.
    """
    # A league that alone consumes essentially the whole joint claim.
    filler = "x" * (dynamo.MAX_FANTASY_BYTES - 4_000)
    table.item["fantasy_leagues"] = {"L1": {"name": "big", "blob": filler}}

    with pytest.raises(ValueError, match="board_too_large"):
        dynamo.put_fantasy_big_board("u1", "half_ppr|12", _board_doc(858))


def test_a_league_write_now_sees_the_stored_boards_too(table):
    """The same rule facing the other way. Without it, a user could fill the item with big boards
    and the league writer would happily push it past the ceiling — the mirror image of the clause
    above and just as fatal to the row.

    ⚠️ ISOLATING, AND ASSERTED IN BOTH DIRECTIONS. The identical league write is made twice — once
    with big boards stored and once without — so the ONLY thing that can differ is whether the board
    bytes were counted. Without the pair, a filler that merely happened to be large enough would
    "pass" against a writer that had never looked at the boards at all.
    """
    league = {"name": "L", "league_rosters": [{"team_key": "t1", "players": []}]}

    # Control: nothing else stored, so the same league keeps its rosters.
    control = dynamo.put_fantasy_league("u1", None, dict(league))
    assert control["league_rosters"] is not None, (
        "the control write already dropped its rosters — this fixture cannot isolate anything"
    )
    dynamo.delete_fantasy_league("u1", control["league_id"])

    # Now fill the claim with BIG BOARDS only, and repeat.
    filler = "x" * (dynamo.MAX_FANTASY_BYTES - 100)
    table.item["fantasy_big_boards"] = {"half_ppr|12": {"order": [filler]}}
    saved = dynamo.put_fantasy_league("u1", None, dict(league))

    assert saved["league_rosters"] is None, (
        "the league writer did not count the stored big boards — the two attributes can now "
        "jointly overflow the 400 KB item"
    )
    assert saved["league_rosters_truncated"] is True, "the drop was silent"


def test_an_oversized_board_is_refused_whole_and_never_truncated(table):
    """⭐ REFUSE, DO NOT SHORTEN. There is no 'enhancement' half of a big board to shed: the ranking
    IS the board, and a cheat sheet quietly missing its bottom third is a plausible wrong answer
    read at the pick — the exact class NF-C6P3 chose whole-team truncation to avoid.

    Asserted on the STORED state rather than on the raised error, because "raised and also wrote a
    shortened copy" would satisfy a `pytest.raises` on its own.

    ⭐ `table.writes == 0` IS ALSO THE OBSERVABLE FORM OF "THE BUDGET IS CHECKED BEFORE THE WRITE".
    A check made afterwards cannot help — DynamoDB has already refused the item by then, and the
    code would be reasoning about a write that never landed. Stated as behaviour rather than as a
    source-order assertion, because a source guard on statement order is satisfied by any edit that
    keeps the two lines in place (measured: `if False:` left it green).
    """
    table.item["fantasy_leagues"] = {"L1": {"blob": "x" * (dynamo.MAX_FANTASY_BYTES - 4_000)}}
    with pytest.raises(ValueError, match="board_too_large"):
        dynamo.put_fantasy_big_board("u1", "half_ppr|12", _board_doc(858))
    assert dynamo.list_fantasy_big_boards("u1") == [], (
        "a refused save left a partial board behind"
    )
    assert table.writes == 0, "a refused save still issued the write — the budget is checked too late"


def test_a_refused_save_evicts_nothing_that_was_already_stored(table):
    """⭐ NEVER PAY FOR THIS WRITE WITH SOMEONE ELSE'S DATA. Evicting another board to make room
    mutates data the caller did not ask us to touch, on a write they experience as saving one thing.

    ⚠️ ISOLATING FIXTURE: the pre-existing board is a normal, VALID one and the incoming write is
    refused purely on size — so an eviction would be visible as that board disappearing, and nothing
    else in the flow can remove it.
    """
    keeper = dynamo.put_fantasy_big_board("u1", "full_ppr|10", _board_doc(50))
    table.item["fantasy_leagues"] = {"L1": {"blob": "x" * (dynamo.MAX_FANTASY_BYTES - 4_000)}}
    before_writes = table.writes

    with pytest.raises(ValueError, match="board_too_large"):
        dynamo.put_fantasy_big_board("u1", "half_ppr|12", _board_doc(858))

    still = dynamo.list_fantasy_big_boards("u1")
    assert [b["board_key"] for b in still] == ["full_ppr|10"], "a refusal evicted another board"
    assert still[0]["order"] == keeper["order"], "a refusal mutated another board"
    assert table.writes == before_writes, "a refused save still wrote to the item"


def test_replacing_a_board_does_not_count_its_own_old_bytes_twice(table):
    """⚠️ THE OFF-BY-ONE THAT WOULD MAKE A BIG BOARD UNSAVABLE THE SECOND TIME. An overwrite frees
    the bytes it replaces; counting them would mean the first save of a large board succeeds and
    every subsequent save of the SAME board is refused, which presents as "saving broke"."""
    big = _board_doc(858, width=40)
    dynamo.put_fantasy_big_board("u1", "half_ppr|12", big)
    # Fill the rest of the claim so only the double-count could tip it over.
    room = dynamo.MAX_FANTASY_BYTES - dynamo._big_boards_bytes("u1") - 6_000
    table.item["fantasy_leagues"] = {"L1": {"blob": "x" * max(room, 0)}}
    again = dynamo.put_fantasy_big_board("u1", "half_ppr|12", big)
    assert again["order"] == big["order"]


def test_the_per_user_board_cap_refuses_a_new_key_but_never_an_edit(table):
    """⭐ THE E8.6 SHAPE. Applying a create-cap to updates as well reads as symmetric and freezes a
    user's existing board at whatever they first saved — a failure that presents as "saving is
    broken"."""
    for i in range(dynamo.MAX_BIG_BOARDS_PER_USER):
        dynamo.put_fantasy_big_board("u1", f"cfg{i}|12", _board_doc(5))
    with pytest.raises(ValueError, match="too_many_boards"):
        dynamo.put_fantasy_big_board("u1", "one_too_many|12", _board_doc(5))
    edited = dynamo.put_fantasy_big_board("u1", "cfg0|12", _board_doc(9))
    assert len(edited["order"]) == 9, "a caller at the cap could not edit a board they already had"


def test_one_malformed_stored_board_does_not_blank_the_collection(table):
    """E9.49, verbatim: a single un-representable row must cost only itself. That defect returned a
    500 for the entire bet log."""
    dynamo.put_fantasy_big_board("u1", "half_ppr|12", _board_doc(3))
    table.item["fantasy_big_boards"]["broken|12"] = ["not", "a", "map"]
    keys = [b["board_key"] for b in dynamo.list_fantasy_big_boards("u1")]
    assert "half_ppr|12" in keys, "one malformed board blanked the whole collection"


def test_a_read_failure_returns_an_empty_list_rather_than_raising(monkeypatch):
    """Non-raising on read, like every sibling: a transient storage problem must not take the
    surface down."""
    class _Broken:
        def get_item(self, Key):  # noqa: N803
            raise RuntimeError("boom")

    monkeypatch.setattr(dynamo, "_users_table", lambda: _Broken())
    assert dynamo.list_fantasy_big_boards("u1") == []
    assert dynamo.get_fantasy_big_board("u1", "half_ppr|12") is None


def test_deleting_a_board_the_caller_does_not_own_raises_not_found(table):
    dynamo.put_fantasy_big_board("u1", "half_ppr|12", _board_doc(3))
    with pytest.raises(ValueError, match="not_found"):
        dynamo.delete_fantasy_big_board("u1", "someone_else|12")
    dynamo.delete_fantasy_big_board("u1", "half_ppr|12")
    assert dynamo.list_fantasy_big_boards("u1") == []


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. The payload contract
# ══════════════════════════════════════════════════════════════════════════════════════════════


def test_a_duplicate_player_id_is_dropped_rather_than_stored():
    """A duplicate would render the same player twice, colliding on his React key — two rows for one
    man, one of which cannot be acted on."""
    saved = models.BigBoardSave(config="half_ppr", size=12, order=["a", "b", "a", "c", "b"])
    assert saved.order == ["a", "b", "c"]


def test_an_unrecognised_tag_is_dropped_rather_than_persisted():
    """⚠️ These models set no `extra="forbid"` (see `_LeagueFields`), so an unknown VALUE would
    otherwise be stored and every consumer would have to defend against it forever. Two states is
    the contract, and it is enforced at the boundary."""
    saved = models.BigBoardSave(
        config="half_ppr", size=12, tags={"a": "target", "b": "sell-high", "c": "avoid"}
    )
    assert saved.tags == {"a": "target", "c": "avoid"}
    assert set(models.BIG_BOARD_TAGS) == {"target", "avoid"}


def test_the_order_and_tag_bounds_hold_above_any_real_board():
    """The bounds exist to stop ONE board consuming the shared item, not to police taste — so they
    must sit above the size of any board we publish (858 rows on the 2026 export), or a legitimate
    whole-board ranking would be silently shortened."""
    assert models.MAX_BIG_BOARD_ORDER > 858
    assert models.MAX_BIG_BOARD_TAGS > 858
    over = models.BigBoardSave(
        config="half_ppr", size=12, order=[f"p{i}" for i in range(models.MAX_BIG_BOARD_ORDER + 50)]
    )
    assert len(over.order) == models.MAX_BIG_BOARD_ORDER


@pytest.mark.parametrize("config", ["half_ppr", "custom:0a1b-2c3d", "full_ppr_3wr"])
def test_every_real_board_selection_is_accepted(config):
    """⚠️ THE NO-REGRESSION HALF of the charset rule below. A `config` pattern that refused
    `custom:<uuid>` would make every saved LEAGUE's board unsavable — and the failure would look
    like a validation bug in the league, not in this regex."""
    assert models.BigBoardSave(config=config, size=12).config == config


@pytest.mark.parametrize("config", ["", "has space", "a/b", "x" * 61])
def test_an_implausible_board_selection_is_refused(config):
    with pytest.raises(Exception):
        models.BigBoardSave(config=config, size=12)


def test_the_response_model_carries_no_save_time_validators():
    """⭐ E9.49, AND IT IS THE REASON THE FIELDS LIVE IN A SHARED BASE. A response model that
    subclassed the request model would make every future tightening RETROACTIVE over stored rows —
    the defect that blanked the whole bet log on a single legacy record.

    Proven by ROUND-TRIPPING a stored board that the SAVE rules would now reject: it must read back
    unchanged rather than raise.
    """
    stored = {
        "board_key": "half_ppr|12",
        "config": "a config the save rules would refuse",  # spaces — `BigBoardSave` rejects this
        "size": 12,
        "order": ["a", "a"],  # a duplicate — `BigBoardSave` would strip it
        "tier_breaks": [],
        "tags": {"a": "some-retired-tag"},  # `BigBoardSave` would drop it
    }
    out = models.BigBoard(**stored).model_dump()
    assert out["config"] == stored["config"]
    assert out["order"] == ["a", "a"]
    assert out["tags"] == {"a": "some-retired-tag"}
    # ...and the same values genuinely DO trip the save model, or the clause above proves nothing.
    with pytest.raises(Exception):
        models.BigBoardSave(**{k: v for k, v in stored.items() if k != "board_key"})


def test_the_storage_key_is_derived_by_the_server_not_supplied_by_the_caller():
    """A caller-chosen attribute name on an item whose SIZE is the binding constraint is how a row
    grows keys nothing will ever read. `config`/`size` are validated, so a key derived from them is
    a function of two already-clean values."""
    from app.backend.routers.fantasy import _BOARD_KEY_RE, _big_board_key

    assert _big_board_key("half_ppr", 12) == "half_ppr|12"
    assert _BOARD_KEY_RE.match("half_ppr|12")
    assert _BOARD_KEY_RE.match("custom:0a1b-2c3d|10")
    for bad in ("half_ppr", "half_ppr|1", "half_ppr|33", "half ppr|12", "a" * 61 + "|12"):
        assert not _BOARD_KEY_RE.match(bad), f"{bad!r} passed the stored-key check"
    # The PUT signature takes no key — the identity of a board IS its (config, size).
    src = _py(_ROUTER_SRC)
    assert '@router.put("/nfl/custom-boards")' in src, (
        "the save route grew a caller-supplied key in its path"
    )


def test_the_ceiling_has_exactly_one_owner():
    """⭐ ONE LOGICAL THING, ONE OWNER — this repo's recurring defect is the opposite (INC-30's two
    crontabs, INC-36's two deploys, INC-38's four callers). The number of boards a user may keep is
    a STORAGE fact and lives beside its sibling in `dynamo`; nothing restates it."""
    assert "MAX_BIG_BOARDS_PER_USER" not in _py(_REPO / "app/backend/models/fantasy.py")
    assert isinstance(dynamo.MAX_BIG_BOARDS_PER_USER, int)
    # And it is SERVED, so the surface never hardcodes a number the server owns.
    assert "max_boards" in _py(_ROUTER_SRC)
    assert "max_boards" in _ts("lib/fantasy.ts")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4. What the surface must show, and must not claim
# ══════════════════════════════════════════════════════════════════════════════════════════════


def test_the_save_surface_renders_all_four_states():
    """E8.6 — a save with no feedback is the silent-save class: a dropped field or a refusal presents
    as a phantom revert with no error anywhere.

    ⚠️ ASSERTED ON THE RENDERED TEXT INSIDE THE STATUS LINE, not on the state union. The first cut
    checked for `"saving"` anywhere in the file and stayed GREEN with the render branch DELETED,
    because the string still appeared in the `SaveState` type — a guard satisfied by a type
    declaration for a thing the user never sees (found by the red proof, not by the suite).
    """
    src = _ts("components/fantasy/big-board.tsx")
    start = src.index('data-testid="big-board-save-status"')
    block = src[start : src.index("</span>", src.index("saveState.kind === \"error\"", start))]
    for shown in ("Unsaved changes", "Saving", "Saved at", "saveState.message"):
        assert shown in block, f"the save-status line never renders {shown!r}"


def test_an_unreadable_saved_board_list_is_not_reported_as_an_empty_one():
    """⭐ E9.46's class, pointed at the user's OWN data. "You have nothing saved for this board" and
    "we could not read what you have saved" are different facts, and only the first is ours to
    state — a 503 gives us no standing to make it. Collapsing them tells someone their work is gone
    on any transient read failure, which is the one message most likely to make them rebuild a board
    that is sitting there intact.

    The two branches are asserted separately, so a state that rendered the same words for both would
    fail here even though it renders something for each."""
    src = _ts("components/fantasy/big-board.tsx")
    assert '"unreadable"' in src, "the failed-read state does not exist"
    load = src[src.index("const loadedFor") : src.index("const edit = useCallback")]
    # ⚠️ THE BRANCH, NOT THE NAME. A first cut asserted `"savedError" in load` and stayed GREEN with
    # the branch disabled, because the identifier still appears in the effect's DEPENDENCY ARRAY —
    # a guard satisfied by a declaration for a thing that no longer acts (the same shape that let
    # the `SaveState` union satisfy the save-status clause). Found by the red proof.
    assert "if (savedError)" in load, (
        "the loader does not branch on a failed read — it falls through to an empty document"
    )
    idle = src[src.index('saveState.kind === "idle"') :]
    idle = idle[: idle.index('saveState.kind === "dirty"')]
    assert "Nothing saved" in idle, "the genuinely-empty branch stopped saying so"
    unreadable = src[src.index('saveState.kind === "unreadable"') :]
    unreadable = " ".join(unreadable[: unreadable.index("saveState.kind === \"dirty\"")].split())
    assert "Nothing saved" not in unreadable, "a failed read still claims nothing is saved"
    assert "Nothing has been lost" in unreadable


def test_a_failed_save_renders_the_servers_own_sentence():
    """⚠️ NOT A GENERIC MESSAGE. `apiFetch` goes to the trouble of preserving FastAPI's `detail`
    precisely so a refusal arrives already written for a person and already saying that nothing was
    changed; replacing it here is how a precise explanation becomes an unexplained failure."""
    src = _ts("components/fantasy/big-board.tsx")
    block = src[src.index("const onSave") : src.index("const resetBoard")]
    assert "e instanceof Error" in block and "e.message" in block, (
        "the save error is not read off the server's response"
    )
    assert 'kind: "error"' in block


def test_the_refusal_says_nothing_was_changed():
    """The one sentence that turns a refusal from alarming into actionable. A user whose save is
    refused has to know their existing boards are intact before they will trust the tool again."""
    src = _py(_ROUTER_SRC)
    block = src[src.index('status_code=413') : src.index('@router.delete("/nfl/custom-boards')]
    assert "Nothing was changed" in block


def test_the_board_stores_no_model_output():
    """⭐ THE PROPERTY THAT MAKES A SAVED BOARD CHEAP AND SAFE AT ONCE. Only player ids and the
    user's own annotations are persisted, so a saved board (a) can never serve a stale projection,
    because it holds none, and (b) is not a second copy of the paywalled data.

    Asserted on the STORAGE CONTRACT, which is the only place it can be enforced: the model declares
    exactly these fields and every one of them is the USER'S — an id, a tier break, a tag, a note
    they typed — with none of ours among them.

    ⚠️ EQUALITY, NOT A SUBSET CHECK. A field ADDED here is exactly how a projection would arrive on
    the storage contract by accident, so a new field has to be argued for in this test rather than
    passing silently.
    """
    fields = set(models.BigBoardSave.model_fields)
    assert fields == {"config", "size", "order", "tier_breaks", "tags", "notes"}
    for ours in ("pts", "vor", "adp", "ovrRank", "posRank", "ptsP10", "ptsP90"):
        assert ours not in fields


def test_the_ordering_starts_from_the_shared_function_not_a_local_sort():
    """⭐ E9.61's two-renderers class, in the form that would hurt most: the optimizer would
    recommend one order and the cheat sheet printed from it would show another, and neither screen
    would say which was ours. `baseOrder` must BE `sortAvailable`, and the component must not sort
    at all."""
    lib = _ts("lib/big-board.ts")
    body = lib[lib.index("export function baseOrder") :]
    body = body[: body.index("\n}")]
    assert "sortAvailable(board" in body, "the base order is no longer the shared ranking function"
    comp = _ts("components/fantasy/big-board.tsx")
    assert ".sort(" not in comp, "the big-board component sorts the board itself"


def test_the_surface_makes_no_claim_about_who_is_right():
    """`best_alpha = 0`. The divergence column describes a difference; it must never grade one. A
    word list is a weak instrument, so this names the specific claims this surface could plausibly
    make and does not."""
    src = (_FRONTEND / "components/fantasy/big-board.tsx").read_text()
    for claim in ("beat the market", "edge", "win rate", "sharper than", "more accurate"):
        assert claim not in src.lower(), f"the big board claims {claim!r}"

    # ⚠️ THE CAVEAT IS STATED IN TWO PLACES AND EACH IS SCOPED SEPARATELY. The first cut searched
    # the WHOLE FILE and stayed green with the standing note gutted, because the column tooltip
    # still carried the phrase — an `or`-shaped guard that only one of two independent surfaces has
    # to satisfy. They are different promises to different readers (a tooltip is opened; the note is
    # always on screen), so both are named.
    note = " ".join(src[src.index("function HonestNote") :].split())
    assert "which of us is right" in note, (
        "the standing note no longer states that a difference is not a verdict"
    )


def test_the_divergence_column_explains_itself_without_grading_the_difference():
    """The "vs us" number is the one thing on this screen a reader could take as a score. Its own
    tooltip has to say what it is and what it is not — separately from the standing note, because a
    tooltip is read at the moment the number is."""
    src = (_FRONTEND / "components/fantasy/big-board.tsx").read_text()
    tip = src[src.index("How far you have moved") :]
    # ⚠️ WHITESPACE-NORMALISED. JSX wraps prose across lines wherever the formatter chose, so a raw
    # substring match against a sentence longer than a line is a false negative that reads as a
    # missing caveat — the repo's own "a match across a newline gives a false zero" lesson.
    tip = " ".join(tip[: tip.index("</InfoTip>")].split())
    assert "not a score of it" in tip, "the divergence column no longer disclaims being a score"
    assert "which of us is right" in tip


def test_the_layout_cannot_scroll_the_whole_page_sideways():
    """NF-C2.1 — the row grid declares a 720px minimum, wider than a phone, so the board must scroll
    inside its OWN container or that width reaches the document and the whole page scrolls sideways.

    ⚠️ THE TWO TOKENS DO DIFFERENT AMOUNTS OF WORK AND THE DIFFERENCE IS MEASURED, NOT ASSUMED.
    `overflow-x-auto` is load-bearing today: removing it makes the E2E's phone-width page-overflow
    check go red. `min-w-0` is NOT — this container's parent is an ordinary block, and removing it
    changes nothing a browser can see (verified by breaking it and watching the E2E stay green). It
    is pinned anyway, as a tripwire: a flex/grid item's automatic minimum is its MIN-CONTENT width
    and `truncate` makes that the whole string, so the day anyone wraps this board in a side-panel
    layout — which is exactly what the draft and auction surfaces have — it becomes the thing
    standing between a 720px board and a 2129px page.

    ⇒ this clause is a STRUCTURE pin. The clause that can fail on a real render is in the E2E.
    """
    src = _ts("components/fantasy/big-board.tsx")
    block = src[src.index('data-testid="big-board-scroller"') :]
    block = block[: block.index(">")]
    assert "overflow-x-auto" in block, "the wide board has no scrolling container of its own"
    assert "min-w-0" in block, "the scroll container lost the `min-w-0` tripwire"


def test_the_cheat_sheet_prints_the_users_decisions_not_our_numbers():
    """The editing view exists to show our read beside theirs; the PRINTED sheet is read at the pick,
    where a column of projections beside a ranking the user deliberately overrode is noise that
    invites second-guessing. Tier, order and tag are the decisions; those print."""
    src = _ts("components/fantasy/big-board.tsx")
    block = src[src.index("function CheatSheet") :]
    for ours in ("p.pts", "p.vor", "p.adp", "player.pts", "player.vor", "player.adp"):
        assert ours not in block, f"the printed cheat sheet renders {ours}"
    assert 'data-testid="big-board-sheet-row"' in block


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 5. The live-surface corrections — notes, legible icons, real tiers, and a sheet fit to print
#
# Every clause below exists because the shipped surface was WRONG about it in a way no test caught:
# reported from the deployed page, not from CI. They are grouped here rather than folded into the
# sections above so the next reader can see what the first cut got wrong.
# ══════════════════════════════════════════════════════════════════════════════════════════════


def test_every_row_control_is_explained_in_words_somewhere_a_phone_can_read():
    """⭐ AN ICON IS NOT A LABEL, AND THE SCISSORS PROVED IT. A star and a no-entry sign can be
    inferred; a pair of scissors meaning "start a new tier here" cannot, and it sat in a column
    headed "Tag" while not being a tag. Reported on the live board.

    ⚠️ A `title` ALONE DOES NOT SATISFY THIS. There is no hover on a phone, which is exactly where a
    draft board is read, so the explanation has to be rendered text.
    """
    src = _ts("components/fantasy/big-board.tsx")
    legend = src[src.index("function IconLegend") : src.index("function IconToggle")]
    for word in ("tier", "target", "avoid", "note", "drag"):
        assert word in legend.lower(), f"the legend never says what the {word} control does"
    assert 'data-testid="big-board-legend"' in legend
    # ...and it is actually rendered. A component nobody mounts is the wired-≠-invoked class
    # (NF-C0e), and it would satisfy every assertion above.
    assert "<IconLegend />" in src, "the legend is defined but never rendered"


def test_the_column_header_no_longer_calls_a_tier_break_a_tag():
    """The other half of the same defect: three different kinds of control under one word. The
    header names all three, so the column heading and the buttons under it agree."""
    src = _ts("components/fantasy/big-board.tsx")
    header = src[src.index("Our #") : src.index("{visible.length === 0")]
    assert "Tier · tag · note" in header


def test_the_sheet_does_not_invent_a_tier_the_user_never_drew():
    """⭐ THE "EVERY PLAYER IS TIER 1" REPORT. With no breaks drawn, `cheatSheet` correctly returns
    ONE section numbered 1 — and printing "TIER 1" over two hundred names reads as a broken tiering
    rather than as "you have not drawn any". The heading is therefore conditional on the USER'S
    document, and the state says so in words with the one-click way out beside it.
    """
    src = _ts("components/fantasy/big-board.tsx")
    assert "const hasTiers = doc.tier_breaks.length > 0" in src, (
        "whether the user has tiers is no longer read from their own document"
    )
    sheet = src[src.index("function CheatSheet") :]
    assert "{hasTiers && (" in sheet, "the tier heading is rendered unconditionally"
    assert 'data-testid="big-board-no-tiers"' in sheet


def test_whether_the_user_has_tiers_is_not_derived_from_the_section_count():
    """⚠️ THE TEMPTING WRONG TEST. `sections.length > 1` looks equivalent and is not: ONE section is
    what BOTH "no tiers at all" and "one tier covering the whole board" produce, and the second is a
    real, deliberate user state whose heading must print."""
    src = _ts("components/fantasy/big-board.tsx")
    sheet = src[src.index("function CheatSheet") :]
    assert "sections.length" not in sheet, (
        "the sheet infers the user's tiers from how many sections it happened to build"
    )


def test_the_print_stylesheet_turns_dark_theme_text_into_ink():
    """⭐ BROWSERS DO NOT PRINT BACKGROUND COLOURS. On a dark-themed site that means every printed
    page came out as pale grey on white — rendered, unreadable, and looking deliberate. One global
    rule fixes it and cannot be missed by the next component added; a `print:text-black` per span
    always can be.
    """
    css = (_FRONTEND / "app/globals.css").read_text()
    block = css[css.index("@media print") :]
    assert "color: #000 !important" in block, "printed text is not forced to ink"
    assert "background: #fff !important" in block
    # ⚠️ `!important` is load-bearing: Tailwind's colour utilities are single-class specificity and
    # land later in the cascade, so without it every `text-gray-400` on the page wins.
    assert "@page" in block and "margin" in block
    assert "break-inside: avoid" in block, "a tier can still be split across two pages"


def test_the_page_chrome_does_not_print():
    """`window.print()` prints the PAGE, not the sheet. Before this, a printed cheat sheet opened
    with the nav bar, the sign-out link, the format pickers and the save bar."""
    page = _ts("app/fantasy/big-board/page.tsx")
    nav = page[page.index("<div") : page.index("<BigBoard")]
    assert "print:hidden" in nav, "the nav bar still prints above the cheat sheet"

    src = _ts("components/fantasy/big-board.tsx")
    editor = src[: src.index("function IconLegend")]
    assert editor.count("print:hidden") >= 4, "the editing chrome still prints with the sheet"


def test_the_printed_sheet_names_the_league_and_the_day_it_was_printed():
    """On screen the league is in a picker two inches above the sheet. On paper there is no picker,
    and a cheat sheet that does not say which league it is for is the one you take to the wrong
    draft."""
    src = _ts("components/fantasy/big-board.tsx")
    sheet = src[src.index("function CheatSheet") :]
    header = sheet[sheet.index("print:flex") :]
    header = header[: header.index("</div>")]
    assert "{title}" in header, "the print-only header does not name the board"
    assert "toLocaleDateString" in header, "the printed sheet is undated"


def test_the_intro_does_not_depend_on_jsx_whitespace_around_an_expression():
    """🐛 THE DEPLOYED PAGE READ "our 2026board". A space between a JSX expression and the text after
    it is whitespace the compiler is entitled to reason about; a template literal is not. This is
    the source-level half — the E2E asserts the RENDERED sentence, which is the one that can fail
    for a reason this clause cannot see.
    """
    src = _ts("components/fantasy/big-board.tsx")
    intro = src[src.index("<h1") :]
    intro = intro[: intro.index("</p>")]
    assert "${SEASON}" in intro, "the season is a JSX child again, not part of the string"
    # ⚠️ THE NEGATIVE HAS TO EXCLUDE THE INTERPOLATION ITSELF — `${SEASON}` CONTAINS `{SEASON}`, so
    # a plain substring check here passes on nothing (this file's own vacuous-guard rule, caught
    # while writing it). A bare `{SEASON}` not preceded by `$` is the JSX child we are forbidding.
    assert re.search(r"(?<!\$)\{SEASON\}", intro) is None, (
        "the season is rendered as a JSX child beside text again"
    )


def test_the_note_length_cap_is_one_number_with_one_owner():
    """⚠️ THE SERVER OWNS IT; THE CLIENT MIRRORS IT. The textarea has to stop the user where the
    server truncates, or a note is silently shortened after they have typed it — but two numbers for
    one rule is this repo's most-repeated defect (INC-30 / INC-36 / INC-38), so they are pinned
    equal here. Change one and this goes red."""
    client = _ts("lib/big-board.ts")
    m = re.search(r"export const MAX_NOTE_LEN = (\d+)", client)
    assert m, "the client no longer declares a note cap"
    assert int(m.group(1)) == models.MAX_BIG_BOARD_NOTE_LEN
    assert "maxLength={MAX_NOTE_LEN}" in _ts("components/fantasy/big-board.tsx"), (
        "the textarea does not enforce the cap it imports"
    )


def test_a_whitespace_only_note_is_dropped_rather_than_stored():
    """An empty string is bytes in the shared item that mean nothing, and every reader would have to
    treat it as absent anyway."""
    saved = models.BigBoardSave(
        config="half_ppr", size=12, notes={"a": "   ", "b": "\n", "c": "real"}
    )
    assert saved.notes == {"c": "real"}


def test_an_over_long_note_is_truncated_not_refused():
    """⚠️ THE DIRECTION MATTERS. A save refused because one note ran three characters long would
    cost a user a whole curated board; the textarea already stops them at the same limit, so a note
    arriving over-length is an out-of-date client rather than a person mid-sentence."""
    long_note = "x" * (models.MAX_BIG_BOARD_NOTE_LEN + 500)
    saved = models.BigBoardSave(config="half_ppr", size=12, notes={"a": long_note})
    assert len(saved.notes["a"]) == models.MAX_BIG_BOARD_NOTE_LEN


def test_notes_are_weighed_against_the_shared_item_budget_like_everything_else(table):
    """⭐ NOTES ARE THE ONE FIELD THAT GROWS FROM TYPING ALONE — an id is ten fixed bytes, a note is
    whatever a person writes. So the clause that matters is not a per-note cap but that the WHOLE
    record is weighed: a board of notes too big for the shared item is refused WHOLE, and nothing is
    written.

    ⚠️ ISOLATING FIXTURE (NF-D17): the order is short and there are no tags, so the notes are the
    only thing that can push this over — no other clause can be what refuses it.
    """
    doc = _board_doc(0)
    doc["notes"] = {f"{i:010d}": "x" * models.MAX_BIG_BOARD_NOTE_LEN for i in range(2000)}
    with pytest.raises(ValueError, match="board_too_large"):
        dynamo.put_fantasy_big_board("u1", "half_ppr|12", doc)
    assert table.writes == 0, "a refused board of notes still issued the write"
    # ...and the control: the identical board with the notes removed is stored.
    dynamo.put_fantasy_big_board("u1", "half_ppr|12", _board_doc(0))
    assert table.writes == 1


def test_a_board_stored_before_notes_existed_still_reads(table):
    """E9.49, the same rule the write/read split exists for: a field added to the model must never
    make an already-stored board unreadable. A record written by the previous version has no `notes`
    key at all."""
    legacy = {
        "board_key": "half_ppr|12",
        "config": "half_ppr",
        "size": 12,
        "order": ["a", "b"],
        "tier_breaks": [],
        "tags": {"a": "target"},
    }
    out = models.BigBoard(**legacy).model_dump()
    assert out["notes"] == {}
    assert out["order"] == ["a", "b"]


def test_the_save_notices_a_backend_that_accepted_the_notes_and_stored_none():
    """⭐ E8.6 / NF-C0, THE EXACT SHAPE THAT BIT E8.6: `frontend/` auto-deploys on merge while the API
    Lambda ships only via a manual `deploy.sh`, and the request models do not set `extra="forbid"` —
    so a backend that predates `notes` ACCEPTS the field, IGNORES it, and returns 200. The user
    types a note, reads "✓ Saved", reloads, and it is gone with no error anywhere.

    The response carries the stored record, so one comparison turns that phantom revert into a
    sentence.
    """
    src = _ts("components/fantasy/big-board.tsx")
    block = src[src.index("const onSave") : src.index("const resetBoard")]
    assert "saved?.notes" in block and "doc.notes" in block, (
        "the save never compares what came back with what it sent"
    )
    assert "warning:" in block
    status = src[src.index('data-testid="big-board-save-status"') : src.index("<div className=\"ml-auto")]
    assert "saveState.warning" in status, "the warning is computed but never rendered"


def test_a_player_link_opens_in_a_new_tab_and_severs_the_opener():
    """⭐ THIS BOARD HOLDS UNSAVED WORK IN COMPONENT STATE. Navigating away in the same tab throws
    away every drag since the last save — and a player card is exactly the thing you glance at
    mid-edit. `rel="noopener noreferrer"` because `target="_blank"` otherwise hands the opened page
    a live `window.opener` handle back to this one.
    """
    src = _ts("components/fantasy/big-board.tsx")
    link = src[src.index("/fantasy/player/") - 200 : src.index("/fantasy/player/") + 500]
    assert 'target="_blank"' in link
    assert "noopener" in link and "noreferrer" in link
