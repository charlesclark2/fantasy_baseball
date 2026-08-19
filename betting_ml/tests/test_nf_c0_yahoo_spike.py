"""Fast-gate tests for NF-C0-Yahoo-SPIKE — what the LIVE Yahoo surface actually returns.

The NF-C0 adapter was written against Yahoo's published documentation and could not be exercised
against the real endpoints, because every Fantasy resource needs an approved developer app. This
spike probed the live OAuth surface with the real approved credentials (2026-08-19) and found two
places where the vendor's actual behaviour differs from the documented shape the code assumed.
Both are pinned here, and both are stated as MEASURED rather than as read off a spec — the NF-C0e
rule that a fixture derived from an assumption cannot disconfirm that assumption.

WHAT WAS MEASURED (`api.login.yahoo.com/oauth2/get_token`, real client id/secret from SSM):

    grant_type=authorization_code, bad code  -> 400 {"error": "INVALID_AUTHORIZATION_CODE"}
    grant_type=refresh_token,      bad token -> 400 {"error": "invalid_grant"}
    either leg,                  bad secret  -> 400 {"error": "INVALID_CLIENT_SECRET"}

The two legs disagree on BOTH spelling and casing, which is the whole point: the original mapping
listed only the RFC's `invalid_grant`, so the ordinary "the consent screen sat open too long"
case — the single most common OAuth failure there is — surfaced as a 502 blaming Yahoo.

⚠️ NOT COVERED HERE, and deliberately: nothing in this file exercises the Fantasy *payload*
parsing. That still has no real-payload verification (the handshake cannot complete until the
callback route is exempted at the API Gateway — see the memo), and writing another hand-authored
fixture would restate the parser's own assumptions rather than test them.
"""
from __future__ import annotations

import pathlib
import re

import pytest

from app.backend.routers import fantasy_import
from app.backend.services.platform_import import http as platform_http
from app.backend.services.platform_import import yahoo_oauth
from app.backend.services.platform_import.http import PlatformHTTPError

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


class TestYahooTokenErrorsAreClassifiedAsYahooActuallySpellsThem:
    """A token failure must land on the party who can actually fix it."""

    @pytest.fixture
    def creds(self, monkeypatch):
        monkeypatch.setattr(
            yahoo_oauth,
            "_get_parameter",
            lambda name: {
                yahoo_oauth.PARAM_CLIENT_ID: "cid",
                yahoo_oauth.PARAM_CLIENT_SECRET: "secret",
            }.get(name),
        )

    def _reply(self, monkeypatch, error: str):
        monkeypatch.setattr(
            yahoo_oauth,
            "post_form",
            lambda *a, **k: (400, {"error": error, "error_description": "…"}),
        )

    @pytest.mark.parametrize(
        "error",
        [
            "INVALID_AUTHORIZATION_CODE",  # ⭐ measured; was UNMAPPED and became a 502
            "invalid_grant",  # measured on the refresh leg
            "INVALID_REFRESH_TOKEN",
            "invalid_authorization_code",  # casing must not decide the verdict
        ],
    )
    def test_a_dead_user_grant_asks_for_a_reconnect(self, creds, monkeypatch, error):
        self._reply(monkeypatch, error)
        with pytest.raises(yahoo_oauth.YahooAuthError):
            yahoo_oauth.exchange_code("spent-code")

    def test_a_rejected_client_secret_is_NOT_a_reconnect(self, creds, monkeypatch):
        """⭐ THE TWO-SIDED HALF, and the reason the fix is a set rather than a catch-all.

        `INVALID_CLIENT_SECRET` means OUR credential is wrong — a broken deploy or a half-rotated
        SSM parameter. Telling the user to reconnect would ask them to fix something only the
        operator can, and would bury an outage behind a message that reads like routine token
        churn. It must stay a platform error so it reaches the logs as one.
        """
        self._reply(monkeypatch, "INVALID_CLIENT_SECRET")
        with pytest.raises(PlatformHTTPError):
            yahoo_oauth.exchange_code("code")

    def test_the_router_turns_a_dead_grant_into_401_and_a_bad_secret_into_502(self):
        assert fantasy_import._handle_platform_error(
            yahoo_oauth.YahooAuthError("x")
        ).status_code == 401
        assert fantasy_import._handle_platform_error(
            PlatformHTTPError("Yahoo rejected the token request: Invalid client secret", status=400)
        ).status_code == 502


class TestThrottlingIsRecognisedAndBackedOff:
    """Yahoo answers a throttled request with HTTP 999, not 429."""

    def _responder(self, statuses):
        """Return a fake `_request` that plays `statuses` in order, recording the call count."""
        calls = {"n": 0}

        def fake(url, **kwargs):
            i = min(calls["n"], len(statuses) - 1)
            calls["n"] += 1
            status, headers = statuses[i]
            body = b'{"ok": true}' if status == 200 else b""
            return status, body, headers

        return fake, calls

    def test_999_is_a_rate_limit_not_an_outage(self, monkeypatch):
        """Before this, 999 fell through to the generic branch and the user was told the platform
        could not be reached — an outage report for a limit that clears by waiting."""
        assert 999 in platform_http.RATE_LIMIT_STATUSES
        fake, _ = self._responder([(999, {})] * 5)
        monkeypatch.setattr(platform_http, "_request", fake)
        monkeypatch.setattr(platform_http.time, "sleep", lambda *_: None)
        with pytest.raises(PlatformHTTPError) as e:
            platform_http.get_json("https://fantasysports.yahooapis.com/fantasy/v2/x")
        assert e.value.status == 999  # the TRUE upstream status, not one we invented
        assert fantasy_import._handle_platform_error(e.value).status_code == 429

    def test_a_throttled_get_is_retried_exactly_once_and_can_succeed(self, monkeypatch):
        fake, calls = self._responder([(429, {}), (200, {})])
        monkeypatch.setattr(platform_http, "_request", fake)
        slept: list[float] = []
        monkeypatch.setattr(platform_http.time, "sleep", lambda s: slept.append(s))
        assert platform_http.get_json("https://example.test/x") == {"ok": True}
        assert calls["n"] == 2, "a throttled GET must be retried, and only once"
        assert slept and 0 < slept[0] <= platform_http._MAX_RETRY_WAIT

    def test_a_retry_after_longer_than_the_budget_fails_fast_instead_of_sleeping(self, monkeypatch):
        """⭐ Sleeping past the API Gateway's own 29s deadline converts a legible 429 into an
        unexplained edge timeout — worse for the user and undiagnosable for us. So an over-long
        `Retry-After` is honoured by NOT retrying."""
        fake, calls = self._responder([(999, {"Retry-After": "120"}), (200, {})])
        monkeypatch.setattr(platform_http, "_request", fake)
        monkeypatch.setattr(
            platform_http.time, "sleep", lambda *_: pytest.fail("must not sleep past the budget")
        )
        with pytest.raises(PlatformHTTPError):
            platform_http.get_json("https://example.test/x")
        assert calls["n"] == 1

    def test_a_token_post_is_never_retried(self, monkeypatch):
        """An authorization code is single-use: replaying a POST that may already have been
        accepted spends the grant and returns the SECOND, failing answer — a retry that
        manufactures the error it is trying to survive."""
        fake, calls = self._responder([(999, {}), (200, {})])
        monkeypatch.setattr(platform_http, "_request", fake)
        platform_http.post_form("https://example.test/token", {"a": "b"})
        assert calls["n"] == 1


class TestYahooDataNeverReachesTrainingOrTheLLM:
    """§1.c / §2.c.xii / §3.e — Yahoo Fantasy Information may not feed model training or any AI tool.

    Our models train on nflverse, never on user leagues, so this holds today. It holds by
    CONVENTION, though, and nothing stopped a future story from joining a user's imported roster
    into a training frame — so it is asserted mechanically, against the source, rather than left as
    an intention in a docstring.
    """

    # The attribute names user-league (and therefore Yahoo-derived) data is persisted under.
    PERSISTED = ("fantasy_leagues", "league_rosters", "imported_roster", "platform_tokens")
    # Everything that trains a model, builds a feature, or talks to an LLM.
    MODEL_SIDE = ("quant_sports_intel_models", "betting_ml", "pipeline", "scripts", "dbt")

    def _sources(self):
        out = []
        for top in self.MODEL_SIDE:
            root = REPO_ROOT / top
            if not root.is_dir():
                continue
            for path in root.rglob("*.py"):
                if "/tests/" in path.as_posix() or path.name.startswith("test_"):
                    continue
                out.append(path)
        return out

    def test_no_model_or_llm_module_reads_a_user_league_store(self):
        sources = self._sources()
        # Non-vacuity FIRST: a scan that found nothing to scan passes on nothing.
        assert len(sources) > 200, f"the boundary scan found only {len(sources)} modules"

        offenders = []
        for path in sources:
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            # Strip comments and docstring prose: the model-side docs legitimately REFERENCE the
            # backend module by name, and a substring scan would flag the prose, not a reader.
            code = re.sub(r"#.*", "", text)
            code = re.sub(r'""".*?"""|\'\'\'.*?\'\'\'', "", code, flags=re.S)
            for attr in self.PERSISTED:
                if attr in code:
                    offenders.append(f"{path.relative_to(REPO_ROOT)} :: {attr}")
        assert not offenders, (
            "Yahoo-derived league data must not reach model training or the LLM path:\n  "
            + "\n  ".join(offenders)
        )

    def test_the_only_llm_call_site_takes_no_league_input(self):
        """The narrative generator is the repo's one LLM caller; it must stay MLB-pick-shaped."""
        narrative = REPO_ROOT / "betting_ml" / "scripts" / "generate_pick_narratives.py"
        assert narrative.is_file(), "the known LLM call site moved — re-anchor this guard"
        code = re.sub(r"#.*", "", narrative.read_text(encoding="utf-8", errors="ignore"))
        for attr in self.PERSISTED:
            assert attr not in code, f"the LLM path reads {attr}"
