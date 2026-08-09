#!/usr/bin/env python
"""G100-D0 — what actually arrived in PostHog, and whether it arrived on ONE person.

═══════════════════════════════════════════════════════════════════════════════════════════════════
WHY THIS EXISTS SEPARATELY FROM THE DASHBOARD
═══════════════════════════════════════════════════════════════════════════════════════════════════

A funnel that reads "everyone dropped off after step 2" has at least four causes that look
IDENTICAL on the chart, and the chart cannot tell them apart:

  1. The event genuinely never fired (broken instrumentation).
  2. The event fired, but on a DIFFERENT PERSON than the earlier steps — an identity-stitching
     failure. An ORDERED funnel drops anyone who is missing an earlier step, so a visitor whose
     anonymous `landing_view` never merged into their account appears to abandon at exactly the
     step where identification happens. ⭐ THIS IS THE ONE MOST OFTEN MISREAD AS A PRODUCT PROBLEM.
  3. The event fired correctly and the walker did not qualify for it — e.g.
     `league_config_completed` only fires on a CREATE, so an operator who already had a league
     saved produces no event and the funnel is telling the truth about a walk that never happened.
  4. The event fired outside the funnel's conversion WINDOW.

So this reports the raw facts the dashboard abstracts away: which events exist at all, how many
distinct persons each has, and — the load-bearing one — the full ordered timeline of the most
recent walker, so a broken stitch is visible as two person ids where there should be one.

⛔ NEEDS `query:read`, WHICH THE PROVISIONING KEY DELIBERATELY DOES NOT HAVE. The provisioning key
carries `dashboard:write` + `insight:write` and nothing else, so it cannot read a single event or
person. Add `query:read` to run this, and remove it afterwards — this is a debugging instrument, not
a scheduled job, and nothing in the shipped app reads events through the API.

Usage (LAPTOP):

    set -a; . ./.env; set +a
    uv run python scripts/diagnose_posthog_funnel.py            # last 24h
    uv run python scripts/diagnose_posthog_funnel.py --hours 72
    uv run python scripts/diagnose_posthog_funnel.py --person someone@example.com
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

from scripts.provision_posthog_funnel_dashboard import DEFAULT_HOST, FUNNEL_SPINE


def run_query(host: str, project_id: str, api_key: str, hogql: str) -> list[list]:
    body = json.dumps({"query": {"kind": "HogQLQuery", "query": hogql}}).encode()
    req = urllib.request.Request(
        f"{host.rstrip('/')}/api/projects/{project_id}/query/", data=body, method="POST"
    )
    req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode()).get("results", [])
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:600]
        if "query:read" in detail:
            raise SystemExit(
                "This key cannot read events. Add the `query:read` scope to the personal API key "
                "(PostHog > Settings > Personal API keys), re-run, then remove it again.\n"
                f"{detail}"
            ) from exc
        raise SystemExit(f"PostHog query failed: HTTP {exc.code}\n{detail}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--person", help="email / distinct_id to trace; default = most recent")
    parser.add_argument("--host", default=os.environ.get("POSTHOG_HOST", DEFAULT_HOST))
    parser.add_argument("--project-id", default=os.environ.get("POSTHOG_PROJECT_ID"))
    args = parser.parse_args(argv)

    api_key = os.environ.get("POSTHOG_PERSONAL_API_KEY")
    if not api_key or not args.project_id:
        print("needs POSTHOG_PERSONAL_API_KEY and POSTHOG_PROJECT_ID", file=sys.stderr)
        return 2

    def q(sql: str) -> list[list]:
        return run_query(args.host, args.project_id, api_key, sql)

    window = f"timestamp > now() - interval {args.hours} hour"

    # ── 1. Did each spine step arrive AT ALL? ─────────────────────────────────────────────────
    # `event IN (…)` rather than a group-by-everything, so a step with ZERO rows is reported as a
    # zero rather than silently missing from the output — an absent row and a zero look the same in
    # a leaderboard and mean completely different things here.
    spine = "', '".join(FUNNEL_SPINE)
    rows = q(
        f"select event, count() as events, count(distinct person_id) as persons, "
        f"max(timestamp) as latest from events "
        f"where {window} and event in ('{spine}') group by event"
    )
    seen = {r[0]: (r[1], r[2], r[3]) for r in rows}
    print(f"\n══ SPINE, last {args.hours}h ══")
    print(f"  {'step':<26} {'events':>7} {'persons':>8}  latest")
    for i, event in enumerate(FUNNEL_SPINE, 1):
        events, persons, latest = seen.get(event, (0, 0, "—"))
        flag = "  " if events else "⛔"
        print(f"{flag}{i}. {event:<24} {events:>7} {persons:>8}  {latest}")

    # ── 1b. WHICH AUTH DOOR was used, and what the round-trip carried. ────────────────────────
    #
    # ⭐ THE DECISIVE CHECK WHEN STEP 2 IS ZERO, and the two causes it separates are completely
    # different problems:
    #
    #   · `user_signup_started` never fired  ⇒ nobody clicked a SIGN-UP affordance. They used the
    #     sign-in door (or password login). `user_signup_completed` is correctly silent; the walk
    #     simply did not exercise signup.
    #   · `user_signup_started` fired but `user_signup_completed` did not, and `user_signed_in`
    #     carries `intent: "unknown"`  ⇒ THE SIGN-IN CONTEXT WAS LOST ACROSS THE COGNITO REDIRECT.
    #     That is a real defect and it breaks signup measurement for EVERY user, not just this walk.
    #
    # The `intent` / `surface` / `method` properties are what tell those apart, so they are printed
    # rather than summarised — a count here would collapse the exact distinction being drawn.
    print(f"\n══ AUTH DOOR ══")
    auth = q(
        f"select timestamp, event, properties.intent, properties.surface, properties.method, "
        f"person_id from events where {window} and event in "
        f"('user_signup_started', 'user_signup_completed', 'user_signin_started', 'user_signed_in') "
        f"order by timestamp desc limit 30"
    )
    if not auth:
        print("  no auth events at all in the window — nobody signed in or up.")
    for ts, event, intent, surface, method, person_id in auth:
        print(f"  {ts}  {event:<24} intent={intent or '—'} surface={surface or '—'} "
              f"method={method or '—'}  {person_id}")
    started = [r for r in auth if r[1] == "user_signup_started"]
    completed = [r for r in auth if r[1] == "user_signup_completed"]
    if not started and not completed:
        print(
            "\n  ⇒ NO SIGN-UP INTENT was recorded. `user_signup_completed` fires only when the "
            "round-trip\n     began at a SIGN-UP affordance, so a sign-in (or a password login) "
            "correctly produces\n     nothing. The funnel is telling the truth about a walk that "
            "never signed up."
        )
    elif started and not completed:
        print(
            "\n  ⛔ SIGN-UP STARTED BUT NEVER COMPLETED. If `user_signed_in` above reads "
            "intent=unknown,\n     the context was LOST across the Cognito redirect — a real defect "
            "that silently zeroes\n     step 2 for every user. If it reads intent=signup, the "
            "round-trip itself failed."
        )

    # ── 2. THE STITCH. One walker should be ONE person across the whole spine. ─────────────────
    print(f"\n══ IDENTITY STITCH ══")
    stitch = q(
        f"select person_id, count(distinct event) as steps, "
        f"arraySort(groupUniqArray(event)) as which, min(timestamp) as first, max(timestamp) as last "
        f"from events where {window} and event in ('{spine}') "
        f"group by person_id order by last desc limit 10"
    )
    if not stitch:
        print("  no spine events in the window at all — nothing to stitch.")
    for person_id, steps, which, first, last in stitch:
        print(f"  {person_id}  {steps} step(s)  {first} → {last}")
        print(f"      {', '.join(which)}")
    if len(stitch) > 1:
        print(
            "\n  ⚠️ MORE THAN ONE PERSON carries spine events. If one of them holds only\n"
            "     `landing_view` and another holds the post-signup steps, that is a BROKEN STITCH,\n"
            "     not a drop-off: an ORDERED funnel discards anyone missing an earlier step, so the\n"
            "     chart will read 'abandoned at signup' when the visitor completed everything."
        )

    # ── 3. The walker's full timeline, in order. ──────────────────────────────────────────────
    who = args.person
    if not who:
        latest_person = q(
            f"select distinct_id from events where {window} and event in ('{spine}') "
            f"order by timestamp desc limit 1"
        )
        who = latest_person[0][0] if latest_person else None
    if who:
        print(f"\n══ TIMELINE for {who} ══")
        # EVERY event, not just the spine: what a walker did INSTEAD of the missing step is the
        # thing that explains the gap (e.g. `league_import_started` with no `league_config_completed`
        # is an import that failed; no league event at all is a walk that never reached the editor).
        for ts, event, person_id in q(
            f"select timestamp, event, person_id from events where {window} "
            f"and (distinct_id = '{who}' or person_id in "
            f"(select person_id from events where {window} and distinct_id = '{who}')) "
            f"order by timestamp asc limit 200"
        ):
            mark = "⭐" if event in FUNNEL_SPINE else "  "
            print(f"  {mark} {ts}  {event:<32} {person_id}")

    print(
        "\nReading it: a spine step at 0 events never fired. A step with events but a DIFFERENT\n"
        "person_id from the earlier steps is a stitch failure. `league_config_completed` fires only\n"
        "on a league CREATE — an account that already had one produces nothing, correctly.\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
