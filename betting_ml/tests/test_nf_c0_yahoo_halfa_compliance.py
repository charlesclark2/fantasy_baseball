"""NF-C0-Yahoo-ENABLE (Half A) — the four compliance items, asserted where they can actually fail.

The NF-C0-Yahoo spike measured three gaps against Yahoo's API terms and deliberately left them for
a PM decision (`docs/nf_c0_yahoo_spike_memo.md`, gaps B2–B4):

  · §2.c.vii / §6 — rosters copied from Yahoo were persisted with NO retention bound, and
    `DELETE /fantasy/import/yahoo/connection` dropped only the OAuth token, so a user who
    disconnected kept every roster we had copied, indefinitely, with no way to remove it.
  · Cover / §5 — the required attribution rendered on the import PREVIEW and nowhere else.
  · §7 — the privacy policy did not describe the import at all.

What is pinned here is the half a browser cannot see. The attribution's PRESENCE on each rendered
surface is `frontend/e2e/specs/fantasy-platform-attribution.spec.ts` — a source grep would have
passed throughout the entire outage, because the string was in the codebase and simply never
reached the screens that owed it (NF-C4). What this file asserts instead is:

  1. THE PURGE ROUND-TRIPS THROUGH THE STORE. Written, read back, purged, read back again — against
     a stand-in that implements DynamoDB's update expressions, not a dict the test mutates itself.
     A "the function pops the keys" assertion would pass on a purge whose UpdateExpression is
     malformed, which is the only way this can actually fail in production.
  2. THE RETENTION WINDOW IS ENFORCED ON EVERY READ, and an UNSTAMPED roster fails CLOSED.
  3. THE SCORING CONFIG SURVIVES BOTH. Deleting a user's own league settings because they revoked a
     platform grant would be a worse failure than the one this story fixes.
  4. THE CONSTANTS AGREE ACROSS THE THREE PLACES THEY ARE SPELLED. A policy page promising 30 days
     over a store that keeps 90 is an untrue compliance statement that renders perfectly (E9.61).

RED-PROVEN: `uv run python betting_ml/tests/nf_c0_yahoo_halfa_red_proof.py`.

Pure/offline (fast gate): a fake table, the real `dynamo` module, and committed source files. No
DynamoDB, no S3, no network, no `pipeline` import.
"""
from __future__ import annotations

import importlib
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
FRONTEND = REPO / "frontend"
TS_RETENTION = FRONTEND / "lib/platform-retention.ts"
TS_ATTRIBUTION = FRONTEND / "components/fantasy/platform-attribution.tsx"
PRIVACY = FRONTEND / "app/privacy/page.tsx"
IMPORT_ROUTER = REPO / "app/backend/routers/fantasy_import.py"


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# The store stand-in
# ══════════════════════════════════════════════════════════════════════════════════════════════════
class FakeUsersTable:
    """A users table that INTERPRETS the update expressions instead of trusting them.

    ⚠️ THIS IS THE POINT OF THE FIXTURE. The purge is not a dict `pop` — it is a
    `REMOVE #fl.#id.#f0, … SET #fl.#id.#purged = :true` against a nested map, and every way it can
    realistically be wrong (a path that names the wrong nesting level, a REMOVE and a SET colliding
    on one path, an attribute name never bound) is invisible to a test that reaches into the record
    itself. So the fake parses the expression the way DynamoDB does, and RAISES on anything it does
    not recognise rather than silently succeeding — a stand-in that shrugs at a malformed write is
    the guard-that-cannot-fail class wearing a fixture's clothes.
    """

    def __init__(self):
        self.items: dict[str, dict] = {}
        self.writes: list[str] = []

    def get_item(self, Key):  # noqa: N803 — boto3's casing
        item = self.items.get(Key["user_id"])
        return {"Item": item} if item is not None else {}

    def update_item(  # noqa: N803
        self,
        Key,
        UpdateExpression,
        ExpressionAttributeNames=None,
        ExpressionAttributeValues=None,
        ConditionExpression=None,
    ):
        names = ExpressionAttributeNames or {}
        values = ExpressionAttributeValues or {}
        item = self.items.setdefault(Key["user_id"], {})
        expr = " ".join(UpdateExpression.split())
        self.writes.append(expr)

        def resolve(path: str):
            """`#fl.#id.#f0` → the container holding the final key, plus that key."""
            parts = [names.get(p, p) for p in path.split(".")]
            node = item
            for key in parts[:-1]:
                nxt = node.get(key)
                if not isinstance(nxt, dict):
                    raise KeyError(f"no map at {key!r} while resolving {path!r}")
                node = nxt
            return node, parts[-1]

        # Split into the SET and REMOVE clauses, in either order.
        clauses: dict[str, str] = {}
        for kw in ("SET", "REMOVE"):
            m = re.search(rf"\b{kw}\b (.*?)(?=\bSET\b|\bREMOVE\b|$)", expr)
            if m:
                clauses[kw] = m.group(1).strip()
        if not clauses:
            raise AssertionError(f"unhandled UpdateExpression: {expr}")

        for assignment in filter(None, (a.strip() for a in clauses.get("SET", "").split(","))):
            path, _, val = assignment.partition("=")
            path, val = path.strip(), val.strip()
            if path.count(".") == 0 and ConditionExpression:
                # `SET #fl = :empty` guarded by attribute_not_exists — the create-the-map write.
                if names.get(path, path) in item:
                    raise RuntimeError("ConditionalCheckFailedException")
            node, key = resolve(path)
            node[key] = values[val]

        for path in filter(None, (p.strip() for p in clauses.get("REMOVE", "").split(","))):
            try:
                node, key = resolve(path)
            except KeyError:
                continue  # removing from a map that isn't there is a no-op, as in DynamoDB
            node.pop(key, None)
        return {}


@pytest.fixture()
def dynamo(monkeypatch):
    mod = pytest.importorskip("app.backend.services.dynamo")
    table = FakeUsersTable()
    monkeypatch.setattr(mod, "_users_table", lambda: table)
    mod._table = table  # type: ignore[attr-defined]  — handy for assertions
    return mod


def _yahoo_league(**overrides) -> dict:
    """A saved Yahoo league carrying BOTH kinds of roster copy plus its own scoring config."""
    base = {
        "name": "Yahoo Night",
        "sport": "nfl",
        "n_teams": 12,
        "ppr": "half",
        "scoring": {"per_stat": {"pass_yds": 0.04, "rec": 0.5}, "position_bonuses": {}},
        "roster": [{"name": "QB", "count": 1, "eligible": ["QB"], "bench": False}],
        "source_platform": "yahoo",
        "source_league_id": "461.l.1000",
        "source_team_key": "461.l.1000.t.3",
        "source_team_name": "Credence FC",
        "imported_roster": [{"name": "Ja'Marr Chase", "position": "WR", "team": "CIN"}],
        "roster_synced_at": "2026-08-12T12:00:00Z",
        "league_rosters": [
            {"team_key": "461.l.1000.t.3", "team_name": "Credence FC", "players": []}
        ],
        "league_rosters_synced_at": "2026-08-12T12:00:00Z",
        "league_rosters_truncated": False,
    }
    base.update(overrides)
    return base


def _only(records: list[dict], league_id: str) -> dict:
    hit = [r for r in records if r["league_id"] == league_id]
    assert len(hit) == 1, f"expected exactly one league {league_id}, got {len(hit)}"
    return hit[0]


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 1. Deletion on disconnect — the round trip
# ══════════════════════════════════════════════════════════════════════════════════════════════════
class TestDisconnectDeletesTheRostersAndKeepsTheLeague:
    def test_a_stored_yahoo_roster_reads_back_before_the_purge(self, dynamo):
        """NON-VACUITY FIRST. Every clause below asserts that something is GONE, and 'gone' is what
        a store that never held it looks like. If this fails, nothing after it means anything."""
        saved = dynamo.put_fantasy_league("u1", None, _yahoo_league())
        back = _only(dynamo.list_fantasy_leagues("u1"), saved["league_id"])
        assert back["imported_roster"], "the roster never reached the store"
        assert back["league_rosters"], "the league rosters never reached the store"

    def test_the_purge_round_trips_the_rosters_out_of_the_store(self, dynamo):
        saved = dynamo.put_fantasy_league("u1", None, _yahoo_league())

        result = dynamo.purge_platform_league_data("u1", "yahoo")
        assert result["leagues_purged"] == 1
        assert result["league_ids"] == [saved["league_id"]]

        back = _only(dynamo.list_fantasy_leagues("u1"), saved["league_id"])
        for field in dynamo.PLATFORM_ROSTER_FIELDS:
            assert not back.get(field), f"{field} survived the purge: {back.get(field)!r}"

    def test_the_bytes_are_gone_from_the_stored_item_not_merely_masked_on_read(self, dynamo):
        """⚠️ A READ MASK IS NOT A DELETION. The terms say we may not STORE the data past the
        window; a reader that hides it while the row still holds it satisfies the product and not
        the contract. So this asserts against the raw stored item, underneath every reader."""
        saved = dynamo.put_fantasy_league("u1", None, _yahoo_league())
        dynamo.purge_platform_league_data("u1", "yahoo")

        stored = dynamo._table.items["u1"]["fantasy_leagues"][saved["league_id"]]
        for field in dynamo.PLATFORM_ROSTER_FIELDS:
            assert field not in stored, f"{field} is still on the stored item after the purge"

    def test_the_league_the_user_configured_survives(self, dynamo):
        """The half that must NOT happen. Disconnecting is a privacy control, not a way to lose the
        settings you typed in — and a purge that took them would present as the app deleting your
        league for you."""
        saved = dynamo.put_fantasy_league("u1", None, _yahoo_league())
        dynamo.purge_platform_league_data("u1", "yahoo")

        back = _only(dynamo.list_fantasy_leagues("u1"), saved["league_id"])
        assert back["name"] == "Yahoo Night"
        assert back["n_teams"] == 12
        assert back["scoring"]["per_stat"]["rec"] == 0.5
        assert back["roster"], "the roster SLOTS (our config) were deleted with the roster DATA"

    def test_the_purge_marks_the_league_so_the_deletion_can_be_explained(self, dynamo):
        """`roster_retention_purged` is what stops My Teams telling the user their league has not
        drafted yet — a confident wrong explanation for something we did (NF-C6b)."""
        saved = dynamo.put_fantasy_league("u1", None, _yahoo_league())
        dynamo.purge_platform_league_data("u1", "yahoo")
        assert _only(dynamo.list_fantasy_leagues("u1"), saved["league_id"])["roster_retention_purged"]

    def test_only_the_disconnected_platform_is_purged(self, dynamo):
        """⭐ The clause that makes the purge a Yahoo disconnect rather than an account wipe. Its own
        fixture: a Sleeper league in the SAME account, so nothing else can explain a survivor."""
        yahoo = dynamo.put_fantasy_league("u1", None, _yahoo_league())
        sleeper = dynamo.put_fantasy_league(
            "u1", None, _yahoo_league(source_platform="sleeper", name="Sleeper Night")
        )

        dynamo.purge_platform_league_data("u1", "yahoo")

        records = dynamo.list_fantasy_leagues("u1")
        assert not _only(records, yahoo["league_id"]).get("imported_roster")
        assert _only(records, sleeper["league_id"])["imported_roster"], (
            "disconnecting Yahoo deleted a roster imported from Sleeper"
        )

    def test_a_purge_with_nothing_to_delete_is_a_no_op_and_writes_nothing(self, dynamo):
        dynamo.put_fantasy_league("u1", None, _yahoo_league(source_platform="sleeper"))
        before = len(dynamo._table.writes)
        assert dynamo.purge_platform_league_data("u1", "yahoo") == {
            "leagues_purged": 0,
            "league_ids": [],
        }
        assert len(dynamo._table.writes) == before


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 2. The disconnect ROUTE actually calls it — and in the order that matters
# ══════════════════════════════════════════════════════════════════════════════════════════════════
class TestTheDisconnectRouteDeletesBeforeItForgets:
    """⭐ WIRED IS NOT INVOKED (NF-C0e). A purge function nothing calls is exactly as compliant as no
    purge at all, and the endpoint would keep returning 204 either way."""

    def _call(self, monkeypatch, purge_raises: bool = False):
        router = importlib.import_module("app.backend.routers.fantasy_import")
        order: list[str] = []

        def fake_purge(user_id, platform):
            order.append(f"purge:{platform}")
            if purge_raises:
                raise RuntimeError("dynamo unavailable")
            return {"leagues_purged": 1, "league_ids": ["l1"]}

        monkeypatch.setattr(router.dynamo, "purge_platform_league_data", fake_purge)
        monkeypatch.setattr(
            router.dynamo,
            "delete_platform_token",
            lambda user_id, platform: order.append(f"token:{platform}"),
        )
        return router, order

    def test_disconnect_purges_the_rosters_and_drops_the_token(self, monkeypatch):
        router, order = self._call(monkeypatch)
        router.yahoo_disconnect(user_id="u1")
        assert order == ["purge:yahoo", "token:yahoo"]

    def test_a_failed_purge_fails_the_disconnect_rather_than_dropping_the_token(self, monkeypatch):
        """⚠️ THE ORDER IS THE CONTRACT. Dropping the token first would leave the rosters behind
        with the connection already gone — and this endpoint is the user's only handle on them, so
        a half-done disconnect is one they cannot retry into completion. Deletion is the red line,
        so the fail-closed direction is to not report a success we did not achieve."""
        router, order = self._call(monkeypatch, purge_raises=True)
        with pytest.raises(RuntimeError):
            router.yahoo_disconnect(user_id="u1")
        assert order == ["purge:yahoo"], "the token was dropped even though the purge failed"


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 3. The retention window
# ══════════════════════════════════════════════════════════════════════════════════════════════════
def _age_stored_roster(dynamo, user_id: str, league_id: str, days: int) -> None:
    """Move one stored league's retention stamp `days` into the past, in the store."""
    stored = dynamo._table.items[user_id]["fantasy_leagues"][league_id]
    stored["roster_retention_expires_at"] = (
        datetime.now(timezone.utc) - timedelta(days=days)
    ).isoformat()


class TestTheRetentionWindow:
    def test_a_fresh_save_is_stamped_with_an_expiry(self, dynamo):
        saved = dynamo.put_fantasy_league("u1", None, _yahoo_league())
        stored = dynamo._table.items["u1"]["fantasy_leagues"][saved["league_id"]]
        stamp = stored.get("roster_retention_expires_at")
        assert stamp, "a stored roster carries no expiry — nothing bounds how long we keep it"
        due = datetime.fromisoformat(str(stamp))
        expected = datetime.now(timezone.utc) + timedelta(
            days=dynamo.PLATFORM_ROSTER_RETENTION_DAYS
        )
        assert abs((due - expected).total_seconds()) < 300

    def test_a_roster_inside_the_window_still_reads(self, dynamo):
        """The control. Without it, an implementation that expired EVERYTHING would pass every
        other clause in this class."""
        saved = dynamo.put_fantasy_league("u1", None, _yahoo_league())
        _age_stored_roster(dynamo, "u1", saved["league_id"], days=-1)  # expires tomorrow
        assert _only(dynamo.list_fantasy_leagues("u1"), saved["league_id"])["imported_roster"]

    def test_a_roster_past_the_window_is_unreadable(self, dynamo):
        saved = dynamo.put_fantasy_league("u1", None, _yahoo_league())
        _age_stored_roster(dynamo, "u1", saved["league_id"], days=1)

        back = _only(dynamo.list_fantasy_leagues("u1"), saved["league_id"])
        for field in dynamo.PLATFORM_ROSTER_FIELDS:
            assert not back.get(field), f"{field} was served past the retention window"
        assert back["roster_retention_purged"] is True
        assert back["scoring"]["per_stat"]["rec"] == 0.5, "expiry took the league's own settings"

    def test_the_expiry_sweep_removes_the_bytes_too(self, dynamo):
        """The read mask is the guarantee; this is the half that satisfies 'do not STORE it'."""
        saved = dynamo.put_fantasy_league("u1", None, _yahoo_league())
        _age_stored_roster(dynamo, "u1", saved["league_id"], days=1)
        dynamo.list_fantasy_leagues("u1")

        stored = dynamo._table.items["u1"]["fantasy_leagues"][saved["league_id"]]
        for field in dynamo.PLATFORM_ROSTER_FIELDS:
            assert field not in stored, f"{field} is still stored after its window closed"

    def test_an_unstamped_roster_fails_closed(self, dynamo):
        """⚠️ THE ONLY WAY TO HOLD AN UNSTAMPED ROSTER IS TO HAVE STORED IT BEFORE THIS SHIPPED —
        i.e. under no retention bound at all. Treating a missing stamp as 'not expired yet' would
        exempt exactly the records the story exists to bound."""
        saved = dynamo.put_fantasy_league("u1", None, _yahoo_league())
        dynamo._table.items["u1"]["fantasy_leagues"][saved["league_id"]].pop(
            "roster_retention_expires_at"
        )
        assert not _only(dynamo.list_fantasy_leagues("u1"), saved["league_id"]).get(
            "imported_roster"
        )

    def test_an_ordinary_read_of_live_data_writes_nothing(self, dynamo):
        """The sweep is conditional on an expiry actually being observed. A read path that wrote on
        every call would put a DynamoDB write behind every page load of every fantasy surface."""
        dynamo.put_fantasy_league("u1", None, _yahoo_league())
        before = len(dynamo._table.writes)
        dynamo.list_fantasy_leagues("u1")
        assert len(dynamo._table.writes) == before

    def test_a_league_that_never_held_a_roster_is_never_marked_purged(self, dynamo):
        """A hand-entered league has no roster and no stamp, and must not be reported as one we
        deleted something from — that notice names an event that did not happen."""
        cfg = _yahoo_league(source_platform=None, imported_roster=None, league_rosters=None)
        saved = dynamo.put_fantasy_league("u1", None, cfg)
        back = _only(dynamo.list_fantasy_leagues("u1"), saved["league_id"])
        assert not back.get("roster_retention_purged")


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 4. The numbers and strings agree everywhere they are spelled
# ══════════════════════════════════════════════════════════════════════════════════════════════════
class TestTheComplianceCopyMatchesWhatTheCodeEnforces:
    def test_the_retention_window_is_the_same_number_on_both_sides(self, dynamo):
        """A policy page promising 30 days over a store that keeps 90 is an untrue compliance
        statement, and nothing about the rendered page would look wrong (E9.61)."""
        src = TS_RETENTION.read_text()
        m = re.search(r"PLATFORM_ROSTER_RETENTION_DAYS\s*=\s*(\d+)", src)
        assert m, f"{TS_RETENTION} no longer declares the constant — re-anchor this guard"
        assert int(m.group(1)) == dynamo.PLATFORM_ROSTER_RETENTION_DAYS

    def test_the_privacy_policy_states_the_window_from_the_constant(self):
        """⚠️ NOT a check that '30' appears. A literal typed into the prose is a second spelling that
        drifts the moment the enforced window changes; the retention copy has to READ the constant.

        ⚠️ SCOPED TO THE ROSTER COPY, and the first cut was not — it scanned the whole page and went
        red on two pre-existing, unrelated 30-day SLAs (how long we take to process a deletion
        request, and to answer a rights request). A guard that fires on prose it has no opinion about
        gets loosened or deleted by the next author, which is how a real one dies.
        """
        src = PRIVACY.read_text()
        start = src.index('title="5. Fantasy League Import')
        chunk = src[start : src.index('title="6. Data Retention')]
        # The roster line inside Data Retention states the same window, so it is scoped in too.
        retention_line = next(
            line for line in src.splitlines() if "Fantasy rosters imported from a third-party" in line
        )
        for name, text in (("the import section", chunk), ("the retention list", retention_line)):
            assert "PLATFORM_ROSTER_RETENTION_DAYS" in text, (
                f"{name} does not render the enforced retention constant"
            )
            assert re.search(r"\b\d+[- ]day", text) is None, (
                f"{name} hardcodes a retention figure instead of rendering the constant"
            )

    def test_the_privacy_policy_covers_the_league_import(self):
        """§7 — gap B4. The policy had ZERO occurrences of 'league', 'import', 'Yahoo', 'Sleeper' or
        'ESPN': it did not describe this data flow at all."""
        src = PRIVACY.read_text()
        for phrase in ("Yahoo", "Sleeper", "ESPN", "league", "import"):
            assert phrase in src, f"the privacy policy never mentions {phrase!r}"
        for promise in (
            "Disconnecting deletes the rosters immediately",
            "train, fit or evaluate any predictive model",
            "large language model",
        ):
            assert promise in src, f"the policy no longer states: {promise!r}"

    def test_the_client_credits_yahoo_with_the_exact_string_the_server_declares(self):
        """The wording and the link are the requirement, and the server already holds both
        (`GET /fantasy/import/platforms` serves them). Two independent spellings of a contractual
        string is the E9.61 two-renderers shape on a compliance statement."""
        yahoo = importlib.import_module("app.backend.services.platform_import.yahoo")
        src = TS_ATTRIBUTION.read_text()
        assert yahoo.ATTRIBUTION in src, (
            f"the shared attribution component does not carry {yahoo.ATTRIBUTION!r}"
        )
        assert yahoo.ATTRIBUTION_URL in src, (
            f"the shared attribution component does not link to {yahoo.ATTRIBUTION_URL!r}"
        )


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 5. Every surface that can render a saved league renders the credit
# ══════════════════════════════════════════════════════════════════════════════════════════════════
class TestNoLeagueAwareSurfaceIsMissingTheCredit:
    """⭐ THE GAP WAS NEVER 'THE COMPONENT IS WRONG' — IT WAS 'NOBODY ENUMERATED THE SCREENS'.

    The E2E proves the credit RENDERS on the surfaces someone remembered to list. This proves the
    LIST is complete, by deriving it: any fantasy component that can resolve one of the caller's
    saved leagues can put platform-derived data on screen, so it owes the credit. A new surface
    added without one turns this red instead of shipping a silent compliance gap (INC-38's
    exhaustive-registry rule).
    """

    COMPONENTS = REPO / "frontend/components/fantasy"
    #: How a component gets hold of the caller's own league. Either is enough to owe a credit.
    LEAGUE_READERS = ("useSavedLeagues", "useMyTeams")

    @staticmethod
    def _strip_ts_comments(src: str) -> str:
        """Line comments BEFORE block comments — a `//` inside a `/* */` is prose (E9.61).

        This is what stops the guard being satisfied by a COMMENT mentioning the component (INC-38).
        """
        src = re.sub(r"//[^\n]*", "", src)
        return re.sub(r"/\*.*?\*/", "", src, flags=re.S)

    def test_every_league_aware_component_renders_the_shared_attribution(self):
        offenders, checked = [], []
        for path in sorted(self.COMPONENTS.glob("*.tsx")):
            if path.name == "platform-attribution.tsx":
                continue
            code = self._strip_ts_comments(path.read_text())
            if not any(reader in code for reader in self.LEAGUE_READERS):
                continue
            checked.append(path.name)
            if "<PlatformAttribution" not in code:
                offenders.append(path.name)

        # NON-VACUITY FIRST: a scan that matched nothing passes on nothing, and this one is a glob
        # over a directory that could be moved or renamed out from under it.
        assert len(checked) >= 8, f"only {len(checked)} league-aware surfaces found: {checked}"
        assert not offenders, (
            "these surfaces can render one of the caller's saved leagues and owe its platform's "
            "attribution: " + ", ".join(offenders)
        )

    def test_the_e2e_registry_names_a_surface_for_every_route_the_story_listed(self):
        """The browser test's SURFACES table is the deliverable, not a convenience — a screen absent
        from it is a screen nobody is checking. Pinned so it cannot quietly shrink."""
        spec = (FRONTEND / "e2e/specs/fantasy-platform-attribution.spec.ts").read_text()
        for name in (
            "My League",
            "My Teams",
            "Roster report",
            "League board",
            "Draft optimizer",
            "Auction optimizer",
            "League settings",
        ):
            assert f'name: "{name}"' in spec, f"the attribution E2E no longer covers {name!r}"


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 6. The red line that was already PASSING, kept passing
# ══════════════════════════════════════════════════════════════════════════════════════════════════
def test_the_purged_flag_is_outbound_only_and_a_save_cannot_assert_it():
    """A client must not be able to tell us its roster was deleted for retention: that field is our
    record of what WE did. `LeagueSave` ignoring it is the E9.49 read/write model split — a rule
    that belongs to one direction must not be inherited by the other."""
    models = importlib.import_module("app.backend.models.fantasy")
    assert "roster_retention_purged" in models.League.model_fields
    assert "roster_retention_purged" not in models.LeagueSave.model_fields
    assert "roster_retention_purged" not in models._LeagueFields.model_fields


def test_the_disconnect_route_still_names_both_halves_of_what_it_can_do():
    """We can delete our copy; only Yahoo can revoke the grant. The docstring is what a future
    author reads before changing this, and the overstatement it guards against is the reason the
    endpoint is worded the way it is."""
    src = IMPORT_ROUTER.read_text()
    body = src[src.index("def yahoo_disconnect") : src.index("def record_import_telemetry")]
    assert "purge_platform_league_data" in body
    assert "delete_platform_token" in body
