#!/usr/bin/env python
"""NF-C0-Yahoo-SPIKE — exercise the REAL Yahoo Fantasy payload against the REAL parser.

The NF-C0 Yahoo adapter is code-complete but its response parsing has never met a live payload
(every Fantasy resource needs an approved app). This script is the sixth E2E step: it drives the
SHIPPING adapter functions against a real token and reports, field by field, what Yahoo actually
sent versus what `yahoo.STAT_ID_MAP` / `yahoo.ROSTER_SLOT_MAP` know how to read.

⭐ IT RUNS THE REAL ADAPTER, NOT A COPY. `list_leagues` / `import_league` / `fetch_draft_state` are
imported from `app.backend.services.platform_import.yahoo`. A reconciliation against a
re-implementation would prove the re-implementation right (the NF-C0e "a test that reads a value
back under the key the code wrote" trap), so the only thing this adds is the REPORT.

🔒 IT DOES NOT KEEP YAHOO FANTASY INFORMATION. The signed Yahoo agreement (§2.c.vii) forbids
storing/caching/indexing Yahoo Fantasy Information, so the capture written to disk is a SHAPE
report — JSON key skeletons, stat ids, roster tokens, counts — with every value redacted. Player
names, team names and manager nicknames never reach the file. `--keep-values` exists for a genuine
parsing dead end only; it prints a warning and the operator is expected to delete the file after.

🔑 IT PRINTS NO SECRETS. The client id/secret come from SSM, the tokens stay in memory, and both
are redacted everywhere they could otherwise surface.

## Running it

⚠️ RUN IT WITH THE SSM-CAPABLE PROFILE AND NO STATIC KEYS IN THE ENVIRONMENT. This repo's shell
usually exports `AWS_ACCESS_KEY_ID` for `baseball-access-user`, which CANNOT read the Yahoo
parameters — and static keys WIN over `AWS_PROFILE`, so the script reports "Yahoo import is not
configured yet" while looking as though it used the profile you named. Hence the `env -u` prefix in
every command below (the repo's documented-≠-actual class, on the credential chain).

    # 1. get the consent URL (opens Yahoo's own screen — sign in with a TEST league account)
    env -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY -u AWS_SESSION_TOKEN \
      AWS_PROFILE=AdministratorAccess-769392325318 \
      uv run python scripts/probe_yahoo_fantasy_live.py --authorize-url

    # 2. approve. The browser is redirected to our callback, which currently returns a 401 JSON
    #    page (the API Gateway authorizer — see the memo). THAT IS FINE FOR THIS PROBE: the code
    #    is in the address bar. Copy the WHOLE URL.
    # 3a. ⭐ IF THE BROWSER LANDED ON `…/fantasy/import?yahoo=connected`, THE HANDSHAKE ALREADY
    #     SUCCEEDED and the deployed callback SPENT the code. There is nothing left to exchange —
    #     resume from the stored grant instead:
    #        …probe_yahoo_fantasy_live.py --from-stored-grant nf-c0-yahoo-spike
    # 3b. if the callback route is not reachable yet, the browser stops on the 401 page with the
    #     code still in the address bar — exchange it here:
    env -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY -u AWS_SESSION_TOKEN \
      AWS_PROFILE=AdministratorAccess-769392325318 \
      uv run python scripts/probe_yahoo_fantasy_live.py \
        --callback-url 'https://api.credencesports.com/...?code=...&state=...'

    # 4. ⭐ CLEAN UP. A successful consent leaves a REAL Yahoo grant in the PRODUCTION users table
    #    under the synthetic id above, which no UI surfaces:
    #        …probe_yahoo_fantasy_live.py --forget nf-c0-yahoo-spike

⚠️ An authorization code is single-use and short-lived. If step 3b reports
INVALID_AUTHORIZATION_CODE, redo step 1 — the code was already spent or it aged out.

⚠️ IF EVERY FANTASY CALL RETURNS `YahooNotEntitled` (measured 2026-08-19), the handshake is FINE and
the APP lacks Fantasy Sports data access — Yahoo answers `oauth_problem="additional_authorization_
required"` on a bare 401 while `openid/v1/userinfo` returns 200 for the same token. That is an
operator/Yahoo fix (the app's API permissions), not a reconnect, and it needs a FRESH consent
afterwards because a granted permission set is bound at consent time.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.backend.services.platform_import import yahoo, yahoo_oauth  # noqa: E402
from app.backend.services.platform_import.http import PlatformHTTPError  # noqa: E402

REDACTED = "<redacted>"
# Keys whose VALUES are Yahoo Fantasy Information about a person or a team. The shape report keeps
# the KEY (that is what the parser reads) and drops the value.
_VALUE_KEYS = {
    "name", "full", "first", "last", "ascii_first", "ascii_last", "nickname", "team_name",
    "manager_id", "guid", "email", "image_url", "url", "editorial_player_key", "player_id",
    "player_key", "team_key", "league_key", "league_id", "team_id", "manager", "logo",
}


def _shape(node: Any, depth: int = 0, keep_values: bool = False) -> Any:
    """A structural skeleton of a payload: keys and types, values redacted.

    Collections are collapsed to their FIRST element plus a count — the parser's problem is which
    idiom a resource used (array vs numeric-keyed object) and which keys it carries, not how many
    teams a league has, so one exemplar answers the question the whole list would.
    """
    if depth > 12:
        return "<deep>"
    if isinstance(node, dict):
        numeric = sorted((k for k in node if str(k).isdigit()), key=lambda k: int(k))
        if numeric:
            first = _shape(node[numeric[0]], depth + 1, keep_values)
            return {"<collection>": first, "<count>": len(numeric)}
        out = {}
        for k, v in node.items():
            if not keep_values and k in _VALUE_KEYS and not isinstance(v, (dict, list)):
                out[k] = REDACTED
            else:
                out[k] = _shape(v, depth + 1, keep_values)
        return out
    if isinstance(node, list):
        if not node:
            return []
        # ⚠️ EVERY element up to a small cap, NOT just the first. Yahoo's signature idiom is a
        # HETEROGENEOUS array — `league` arrives as `[<meta>, {"settings": …}]` — so collapsing a
        # list to its first element hides exactly the half the parser is being checked against.
        # The genuinely long collections are numeric-keyed and were already folded above.
        head = [_shape(v, depth + 1, keep_values) for v in node[:4]]
        return head + ([f"<+{len(node) - 4} more>"] if len(node) > 4 else [])
    if isinstance(node, str):
        return node if (keep_values or len(node) <= 24) else f"<str len={len(node)}>"
    return node


def _authorize_url() -> str:
    return yahoo_oauth.authorize_url("nf-c0-yahoo-spike")


def _tokens_from_callback(url: str) -> dict:
    q = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
    if q.get("error"):
        raise SystemExit(f"Yahoo returned an error on the callback: {q['error'][0]}")
    code = (q.get("code") or [""])[0].strip()
    if not code:
        raise SystemExit("No `code` in that URL. Paste the FULL address-bar URL from step 2.")
    return yahoo_oauth.exchange_code(code)


def _tokens_from_stored_grant(user_id: str) -> dict:
    """Resume from the grant the REAL callback already stored (the normal path once O1 is done).

    ⭐ WHY THIS MODE EXISTS. An authorization code is single-use, and the deployed callback spends
    it — correctly — the moment Yahoo redirects the browser. So after a successful consent there is
    no code left for this script to exchange, and `--callback-url` reports "no code in that URL"
    on the very run that PROVED the handshake works. The grant is in DynamoDB; read it from there.

    Uses the SHIPPING `dynamo` + `yahoo_oauth` code path, so a bug in the refresh/write-back would
    show up here rather than being masked by a re-implementation.
    """
    from app.backend.services import dynamo

    record = dynamo.get_platform_token(user_id, yahoo.PLATFORM)
    if not record or not record.get("refresh_token"):
        raise SystemExit(
            f"No stored Yahoo grant for user_id={user_id!r}. Complete the consent first "
            f"(--authorize-url), or pass the user id the state was issued for."
        )
    print(f"  stored grant   : found for user_id={user_id!r}, "
          f"connected_at={record.get('connected_at')}")
    return {
        "access_token": str(record.get("access_token") or ""),
        "refresh_token": yahoo_oauth.decrypt_token(str(record["refresh_token"])),
        "expires_at": int(record.get("expires_at") or 0),
        "guid": None,
        "_user_id": user_id,
    }


def _write_back(user_id: str, refreshed: dict) -> None:
    """Persist a rotated refresh token. Yahoo revokes the previous one when it issues a new one, so
    skipping this would leave the stored grant dead after the first refresh."""
    from app.backend.services import dynamo

    existing = dynamo.get_platform_token(user_id, yahoo.PLATFORM) or {}
    dynamo.put_platform_token(
        user_id,
        yahoo.PLATFORM,
        {
            "refresh_token": yahoo_oauth.encrypt_token(refreshed["refresh_token"]),
            "access_token": refreshed["access_token"],
            "expires_at": refreshed["expires_at"],
            "connected_at": existing.get("connected_at"),
        },
    )


def _report_oauth(tokens: dict) -> dict:
    """Record what the grant actually is — scopes and lifetime — then prove refresh works."""
    remaining = max(0, int(tokens["expires_at"]) - int(time.time()))
    print("\n=== 1. OAUTH ===")
    print(f"  access_token   : present ({REDACTED}), ~{remaining}s ({remaining // 60} min) left on it")
    print(f"  refresh_token  : {'present' if tokens.get('refresh_token') else '⛔ ABSENT'} ({REDACTED})")
    print(f"  xoauth_yahoo_guid: {'present' if tokens.get('guid') else 'absent'}")
    print("  scopes         : Yahoo's token response carries no `scope` field for Fantasy — the")
    print("                   permission is a property of the APPROVED APP, not of the request.")
    refreshed = yahoo_oauth.refresh_access_token(tokens["refresh_token"])
    rotated = refreshed["refresh_token"] != tokens["refresh_token"]
    new_life = max(0, int(refreshed["expires_at"]) - int(time.time())) + 60  # undo the safety margin
    print(f"  refresh works  : ✅ yes — new token lifetime {new_life}s ({new_life // 60} min)")
    print(f"  rotation       : refresh token {'ROTATED (write-back is required)' if rotated else 'unchanged'}")
    if tokens.get("_user_id"):
        _write_back(tokens["_user_id"], refreshed)
        print(f"  write-back     : ✅ stored (so the next read does not use a revoked token)")
    return refreshed


def _reconcile(league_key: str, token: str, capture: dict, keep_values: bool) -> None:
    """Field-by-field: what Yahoo sent vs what the parser knows."""
    print("\n=== 3. PARSER RECONCILIATION (the real adapter, on the real payload) ===")

    settings_payload = yahoo._get(f"/league/{league_key}/settings", token)
    capture["league_settings"] = _shape(settings_payload, keep_values=keep_values)
    settings = yahoo._merge_fragments(yahoo._find_first(settings_payload, "settings"))

    # -- scoring: every stat id Yahoo actually sent, vs STAT_ID_MAP -------------------------------
    modifiers = yahoo._find_first(settings.get("stat_modifiers"), "stats")
    sent: dict[str, float] = {}
    for entry in yahoo._collection(modifiers) or yahoo._collection(settings.get("stat_modifiers")):
        stat = yahoo._merge_fragments(yahoo._find_first(entry, "stat") or entry)
        sid = str(stat.get("stat_id") or "")
        if sid:
            sent[sid] = yahoo._num(stat.get("value"))
    names = yahoo._stat_names(token, league_key.split(".", 1)[0])
    known = {s for s in sent if s in yahoo.STAT_ID_MAP}
    unknown = {s: sent[s] for s in sent if s not in yahoo.STAT_ID_MAP}
    print(f"  stat_modifiers sent : {len(sent)}  mapped: {len(known)}  UNMAPPED: {len(unknown)}")
    for sid, weight in sorted(unknown.items(), key=lambda kv: -abs(kv[1])):
        flag = "⚠️ SCORES" if abs(weight) > 1e-12 else "  (0.0)  "
        print(f"    {flag} stat_id {sid:>4} = {weight:>7} · {names.get(sid, '?')}")
    capture["stat_ids_sent"] = sorted(sent)
    capture["stat_ids_unmapped"] = {k: names.get(k, "?") for k in sorted(unknown)}
    capture["stat_categories_seen"] = {k: names[k] for k in sorted(names)} if names else {}

    # -- roster slots ----------------------------------------------------------------------------
    tokens_sent, unknown_slots = [], []
    positions = settings.get("roster_positions")
    for entry in yahoo._collection(positions) or yahoo._collection(
        yahoo._find_first(positions, "roster_positions")
    ):
        slot = yahoo._merge_fragments(yahoo._find_first(entry, "roster_position") or entry)
        tok = str(slot.get("position") or "").strip()
        if tok:
            tokens_sent.append(tok)
            if tok not in yahoo.ROSTER_SLOT_MAP:
                unknown_slots.append(tok)
    print(f"  roster tokens sent  : {len(tokens_sent)}  UNMAPPED: {sorted(set(unknown_slots)) or 'none'}")
    capture["roster_tokens_sent"] = sorted(set(tokens_sent))
    capture["roster_tokens_unmapped"] = sorted(set(unknown_slots))

    # -- the whole import, through the shipping code path ------------------------------------------
    imported = yahoo.import_league(league_key, token, include_draft=True)
    cfg = imported.config
    print("\n  --- import_league() verdict ---")
    print(f"  n_teams        : {cfg.get('n_teams')}")
    print(f"  ppr label      : {cfg.get('ppr')}   (derived from the real reception weight)")
    print(f"  roster slots   : {[(s['name'], s['count']) for s in cfg.get('roster', [])]}")
    print(f"  teams parsed   : {len(imported.teams)}"
          f"  · with players: {sum(1 for t in imported.teams if t.players)}"
          f"  · owner identified: {sum(1 for t in imported.teams if t.is_owner)}")
    if imported.teams:
        t = imported.teams[0]
        print(f"  first team     : {len(t.players)} players, "
              f"{sum(1 for p in t.players if p.starter)} starters, "
              f"positions={sorted({p.position for p in t.players if p.position})}")
    draft = imported.draft
    print(f"  draft          : {draft.pick_count if draft else 0} picks"
          f" · rounds={getattr(draft, 'rounds', None)} · note={getattr(draft, 'note', '') or '—'}")
    print(f"  warnings       : {list(imported.warnings) or 'none'}")
    print(f"  unmapped keys  : {list(imported.unmapped_scoring_keys) or 'none'}")

    # 🚩 The checks that actually decide GO/NO-GO on the payload.
    problems = []
    if not imported.teams:
        problems.append("teams parsed as EMPTY — `_fetch_teams` did not read the real shape")
    elif not any(t.players for t in imported.teams):
        problems.append("no team carried players — the roster sub-resource did not parse")
    if imported.teams and not any(t.is_owner for t in imported.teams):
        problems.append("no team flagged is_owner — `is_current_login` did not parse "
                        "(the 'which is your team?' picker would have no default)")
    if not cfg.get("roster"):
        problems.append("roster slots EMPTY — `_translate_roster` did not read the real shape")
    if not any(k in cfg.get("scoring", {}).get("per_stat", {}) for k in ("pass_yds", "rec", "rush_yds")):
        problems.append("no core offensive scoring term mapped — `_translate_scoring` did not parse")
    capture["problems"] = problems
    print("\n  VERDICT: " + ("✅ the real payload reconciles" if not problems else "⛔ MISMATCHES:"))
    for p in problems:
        print(f"    ⛔ {p}")

    capture["teams_shape"] = _shape(yahoo._get(f"/league/{league_key}/teams/roster", token),
                                    keep_values=keep_values)
    capture["draft_shape"] = _shape(yahoo._get(f"/league/{league_key}/draftresults", token),
                                    keep_values=keep_values)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--authorize-url", action="store_true", help="print the consent URL and exit")
    ap.add_argument("--callback-url", help="the FULL URL Yahoo redirected your browser to")
    ap.add_argument(
        "--forget",
        metavar="USER_ID",
        help="delete the stored Yahoo grant for USER_ID and exit. ⭐ RUN THIS WHEN YOU ARE DONE: a "
             "successful consent leaves a REAL, live Yahoo grant in the PRODUCTION users table "
             "under the synthetic id this script issues, which no UI would ever show you.",
    )
    ap.add_argument(
        "--from-stored-grant",
        metavar="USER_ID",
        help="resume from the grant the deployed callback already stored (use this after a "
             "successful consent — the code is already spent). USER_ID is what the state was "
             "issued for; this script issues 'nf-c0-yahoo-spike'.",
    )
    ap.add_argument("--league-key", help="a specific league (default: every league found)")
    ap.add_argument("--out", default="yahoo_live_shape_report.json", help="where to write the SHAPE report")
    ap.add_argument("--keep-values", action="store_true",
                    help="⚠️ keep raw values in the capture — Yahoo Fantasy Information; delete after use")
    args = ap.parse_args()

    if args.forget:
        from app.backend.services import dynamo

        dynamo.delete_platform_token(args.forget, yahoo.PLATFORM)
        left = dynamo.get_platform_token(args.forget, yahoo.PLATFORM)
        print(f"Deleted the stored Yahoo grant for {args.forget!r}. Still present: {bool(left)}")
        print("⚠️  This deletes OUR copy only. The authoritative revocation is the Yahoo account's "
              "own security settings — https://login.yahoo.com/account/security")
        return 0

    if args.authorize_url:
        print(_authorize_url())
        print("\nOpen that, approve, then copy the FULL address-bar URL you land on (a 401 page is "
              "expected today — the code is still in the URL) and re-run with --callback-url '<url>'.")
        return 0
    if not args.callback_url and not args.from_stored_grant:  # --authorize-url/--forget returned above
        ap.error("pass --authorize-url first, then --callback-url or --from-stored-grant USER_ID")

    if args.keep_values:
        print("⚠️  --keep-values: the capture will contain Yahoo Fantasy Information. Delete it "
              "when you are done; do not commit it.")

    capture: dict[str, Any] = {"probed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    tokens = _report_oauth(
        _tokens_from_stored_grant(args.from_stored_grant)
        if args.from_stored_grant
        else _tokens_from_callback(args.callback_url)
    )
    token = tokens["access_token"]

    print("\n=== 2. LEAGUES (`/users;use_login=1/games;game_keys=nfl/leagues`) ===")
    leagues = yahoo.list_leagues(token)
    print(f"  leagues found: {len(leagues)}")
    for lg in leagues:
        print(f"    {lg['league_id']:>16}  season={lg['season']:>4}  teams={lg['total_rosters']:>2}  "
              f"status={lg['status']}  name={REDACTED if not args.keep_values else lg['name']}")
    capture["league_count"] = len(leagues)
    capture["league_keys_wellformed"] = all(yahoo._LEAGUE_KEY_RE.match(l["league_id"]) for l in leagues)
    if not leagues:
        print("  ⛔ EMPTY. Either this account has no NFL league this season, or the app's Fantasy")
        print("     access is not approved (both look identical here — check with a known league).")
        return 2

    targets = [args.league_key] if args.league_key else [lg["league_id"] for lg in leagues]
    for key in targets:
        print(f"\n{'=' * 78}\nLEAGUE {key}")
        per: dict[str, Any] = {}
        try:
            _reconcile(key, token, per, args.keep_values)
        except PlatformHTTPError as e:
            print(f"  ⛔ {key}: {e} (status={e.status})")
            per["error"] = str(e)
        except Exception as e:  # noqa: BLE001 - a probe reports, it does not crash
            print(f"  ⛔ {key}: {type(e).__name__}: {e}")
            per["error"] = f"{type(e).__name__}: {e}"
        capture.setdefault("leagues", {})[key] = per

    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(capture, fh, indent=2, sort_keys=True)
    print(f"\nShape report written to {args.out} "
          f"({'RAW VALUES — delete after use' if args.keep_values else 'values redacted'}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
