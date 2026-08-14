#!/usr/bin/env python3
"""E9.64b — regenerate the ESPN + Yahoo import-preview E2E fixtures from the SHIPPING adapters.

    uv run python frontend/e2e/fixtures/build-import-previews.py

══ WHY GENERATED, NOT CAPTURED ═══════════════════════════════════════════════════════════════════

E9.63's rule is ⛔ do not hand-write a fixture, because a hand-written one encodes the assumption
under test — which is exactly how NF-C0e shipped (an ESPN key-map that wrote `pass_yd` where the
engine reads `pass_yds`, so every ESPN league scored ZERO yardage from the day import shipped, while
a test that read the value back under the key the code wrote stayed green).

`/fantasy/import/{espn,yahoo}/preview` cannot be captured: both require an authenticated caller and
a private league, so nothing anonymous can produce one. This is the position `build-featured-player.py`
and `build-track-record-claim.py` were in, and it follows their precedent — derive everything that
CAN be real, and say plainly what cannot.

    ESPN   ⭐ FULLY REAL, and independently sourced twice over. The inputs are three verbatim
           `?view=mSettings` responses from REAL private leagues, already in the repo as
           `betting_ml/tests/fixtures/espn_league_*`; the outputs are what the SHIPPING parser
           (`espn.parse_settings_payload`) makes of them. No byte here is authored. Two DIFFERENT
           leagues on DIFFERENT accounts are carried on purpose — the NF-C0e lesson is that a
           fixture derived from the first payload cannot disconfirm a wrong key-map, and these two
           score disjoint rule families (pinned by `test_e9_64b_import_e2e_fixtures.py`).

    Yahoo  ⚠️ THE SHAPE IS THE SHIPPING ADAPTER'S; THE PAYLOAD IS NOT REAL, AND CANNOT BE TODAY.
           Yahoo gates all Fantasy API access behind a developer-application review that has not
           cleared (`docs/nf_c0_yahoo_oauth_setup.md`: submitted 2026-08-01, still pending, SSM
           parameters unwritten) — so `yahoo_oauth.is_enabled()` is False in production and there is
           no account anywhere, ours or anyone's, that can produce a real response. The settings
           input is reused verbatim from the Python suite's `YAHOO_SETTINGS` (one spelling, written
           against Yahoo's real nested/fragmented idiom); the teams + leagues inputs are written
           here in that same idiom. ⛔ Do NOT read the Yahoo fixtures as evidence about Yahoo's real
           bytes. ⚠️ RE-GENERATE FROM A REAL LEAGUE THE DAY APPROVAL LANDS — that is the single
           outstanding item on `frontend/e2e/README.md`'s Yahoo limitation.

⭐ WHAT IS REAL EVEN ON THE YAHOO SIDE: the RESPONSE SHAPE. Every fixture below is the return value
of the adapter the API actually calls, so the frontend is rendering the server's own output rather
than this session's guess about it — which is the half of NF-C0's silent-outage class (a dropped
response key, a 200 with a dead button) that a shape-guess fixture cannot catch.

⚠️ SEASON. Every fixture is generated with `season=2026` because that is what the CLIENT sends
(`league-import.tsx`'s `SEASON`, from `NEXT_PUBLIC_NFL_FANTASY_SEASON`), and these files must be
what the server would answer THAT request. It is load-bearing for one input: the drafted capture is
a 2025 league, and the parser lets the caller's season win — so the fixture says 2026, which is
precisely what a user pasting last season's link gets today.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "betting_ml" / "tests"))

from app.backend.services.platform_import import espn, yahoo  # noqa: E402

OUT_DIR = REPO / "frontend/e2e/fixtures/api"
ESPN_CAPTURES = REPO / "betting_ml/tests/fixtures"

# What the client sends. See the module docstring.
SEASON = 2026

# ── ESPN: three real captures ────────────────────────────────────────────────────────────────────
#
# ⚠️ The KEY is `(id, seasonId)` read off the raw capture, not the league id alone: two of these are
# the SAME league in different seasons, and the E2E mock resolves a paste to its preview by exactly
# this pair. A league-id-only key would silently serve one season's settings for the other's paste —
# a mixup the spec could not see, since both are internally consistent.
ESPN_CAPTURE_FILES = (
    "espn_league_mSettings_real.json",
    "espn_league_642070_mSettings_real.json",
    "espn_league_642070_2025_drafted.json",
)


def espn_fixture_name(league_id: str, season_id: str) -> str:
    return f"fantasy-import-espn-preview-{league_id}-{season_id}.json"


def espn_previews() -> dict[str, Any]:
    """`fixture filename -> preview payload`, straight out of the shipping parser.

    Returns rather than writes so `test_e9_64b_import_e2e_fixtures.py` can compare the COMMITTED
    files against this without a temp directory — one spelling of "what the adapter produces",
    which is the whole point of pinning them.
    """
    out: dict[str, Any] = {}
    for name in ESPN_CAPTURE_FILES:
        raw = (ESPN_CAPTURES / name).read_text()
        doc = json.loads(raw)
        out[espn_fixture_name(str(doc["id"]), str(doc["seasonId"]))] = espn.parse_settings_payload(
            raw, season=SEASON
        ).to_dict()
    return out


# ── Yahoo: the adapter's own output over an idiom-faithful (NOT real) payload ────────────────────

#: Yahoo's `/league/{key}/teams/roster` resource, in its real nested idiom: numeric-keyed
#: collections with a sibling `count`, fragmented partial objects, and `is_current_login` as the
#: ONLY signal of which team belongs to the caller. That last field is why Yahoo is the one platform
#: whose preview can pre-select "my team" (`applyPreview`), and the E2E asserts exactly that — so a
#: teams payload without it would make the assertion untestable.
YAHOO_TEAMS: dict[str, Any] = {
    "fantasy_content": {
        "league": [
            {"league_key": "461.l.1000"},
            {
                "teams": {
                    "0": {
                        "team": [
                            [
                                {"team_key": "461.l.1000.t.1"},
                                {"name": "Credence FC"},
                                {
                                    "managers": [
                                        {"manager": {"nickname": "e2e-owner", "is_current_login": "1"}}
                                    ]
                                },
                            ],
                            {
                                "roster": {
                                    "0": {
                                        "players": {
                                            "0": {
                                                "player": [
                                                    [
                                                        {"player_key": "461.p.30977"},
                                                        {"name": {"full": "Ja'Marr Chase"}},
                                                        {"display_position": "WR"},
                                                        {"editorial_team_abbr": "Cin"},
                                                    ],
                                                    {"selected_position": [{"position": "WR"}]},
                                                ]
                                            },
                                            "1": {
                                                "player": [
                                                    [
                                                        {"player_key": "461.p.32671"},
                                                        {"name": {"full": "Bijan Robinson"}},
                                                        {"display_position": "RB"},
                                                        {"editorial_team_abbr": "Atl"},
                                                    ],
                                                    {"selected_position": [{"position": "RB"}]},
                                                ]
                                            },
                                            # A benched player, so the preview's roster chips render
                                            # BOTH states — a roster of starters only leaves the
                                            # bench branch unexercised.
                                            "2": {
                                                "player": [
                                                    [
                                                        {"player_key": "461.p.31002"},
                                                        {"name": {"full": "Trey McBride"}},
                                                        {"display_position": "TE"},
                                                        {"editorial_team_abbr": "Ari"},
                                                    ],
                                                    {"selected_position": [{"position": "BN"}]},
                                                ]
                                            },
                                            "count": 3,
                                        }
                                    },
                                    "count": 1,
                                }
                            },
                        ]
                    },
                    "1": {
                        "team": [
                            [
                                {"team_key": "461.l.1000.t.2"},
                                {"name": "Rivals United"},
                                {"managers": [{"manager": {"nickname": "someone-else"}}]},
                            ],
                            {
                                "roster": {
                                    "0": {
                                        "players": {
                                            "0": {
                                                "player": [
                                                    [
                                                        {"player_key": "461.p.33391"},
                                                        {"name": {"full": "Malik Nabers"}},
                                                        {"display_position": "WR"},
                                                        {"editorial_team_abbr": "NYG"},
                                                    ],
                                                    {"selected_position": [{"position": "WR"}]},
                                                ]
                                            },
                                            "count": 1,
                                        }
                                    },
                                    "count": 1,
                                }
                            },
                        ]
                    },
                    "count": 2,
                }
            },
        ]
    }
}

#: Yahoo's `/users;use_login=1/games;game_keys=nfl/leagues` resource — the league PICKER's data.
YAHOO_LEAGUES: dict[str, Any] = {
    "fantasy_content": {
        "users": {
            "0": {
                "user": [
                    {"guid": "E2EGUID"},
                    {
                        "games": {
                            "0": {
                                "game": [
                                    {"game_key": "461"},
                                    {
                                        "leagues": {
                                            "0": {
                                                "league": [
                                                    {
                                                        "league_key": "461.l.1000",
                                                        "name": "Test Yahoo League",
                                                        "season": "2025",
                                                        "num_teams": "10",
                                                    }
                                                ]
                                            },
                                            "count": 1,
                                        }
                                    },
                                ]
                            },
                            "count": 1,
                        }
                    },
                ]
            },
            "count": 1,
        }
    }
}

#: `stat_id -> human name`, used to LABEL a term we could not map. Id 9999 is the unmapped one in
#: `YAHOO_SETTINGS`, so this is what turns "yahoo_9999_some_bonus" into readable copy on the review.
YAHOO_STAT_NAMES = {"9999": "Some Bonus"}


def yahoo_payloads() -> dict[str, Any]:
    """`fixture filename -> payload`, straight out of the shipping Yahoo adapter. See `espn_previews`
    for why these are returned rather than written."""
    # Imported rather than re-spelled: the Python suite already holds ONE authoritative rendering of
    # Yahoo's settings idiom, and a second copy here would drift from it silently.
    from test_nf_c0_platform_import import YAHOO_SETTINGS  # noqa: PLC0415

    routes = {
        "/league/461.l.1000/settings": YAHOO_SETTINGS,
        "/league/461.l.1000/teams/roster": YAHOO_TEAMS,
        "/users;use_login=1/games;game_keys=nfl/leagues": YAHOO_LEAGUES,
    }

    def fake_get(path: str, access_token: str) -> object:
        for prefix, payload in routes.items():
            if path.startswith(prefix):
                return payload
        raise AssertionError(f"build-import-previews: unstubbed Yahoo path {path!r}")

    real_get, real_stat_names = yahoo._get, yahoo._stat_names
    yahoo._get = fake_get  # type: ignore[assignment]
    yahoo._stat_names = lambda *_a, **_k: YAHOO_STAT_NAMES  # type: ignore[assignment]
    try:
        # `include_draft=False`: a draft read is a THIRD Yahoo resource, and the draft panel is
        # already driven on the ESPN/Sleeper side. Modelling it here would add synthetic surface
        # without adding an assertion.
        preview = yahoo.import_league("461.l.1000", "e2e-token", include_draft=False).to_dict()
        leagues = yahoo.list_leagues("e2e-token")
    finally:
        yahoo._get, yahoo._stat_names = real_get, real_stat_names  # type: ignore[assignment]

    return {
        "fantasy-import-yahoo-preview.json": preview,
        "fantasy-import-yahoo-leagues.json": {"leagues": leagues},
    }


def all_fixtures() -> dict[str, Any]:
    """Every fixture this script owns. The pin test iterates THIS, so a fixture added here without
    a matching committed file fails rather than going unchecked."""
    return {**espn_previews(), **yahoo_payloads()}


def serialize(body: Any) -> str:
    """One spelling of the on-disk form, so the pin test compares like with like."""
    return json.dumps(body, indent=2, sort_keys=True) + "\n"


def main() -> int:
    for name, body in all_fixtures().items():
        path = OUT_DIR / name
        path.write_text(serialize(body))
        print(f"wrote {path.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
