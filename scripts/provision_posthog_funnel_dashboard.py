#!/usr/bin/env python
"""G100-D0 — the founder daily funnel dashboard, as a versioned spec.

═══════════════════════════════════════════════════════════════════════════════════════════════════
WHY THE DASHBOARD IS DEFINED HERE AND NOT CLICKED TOGETHER IN POSTHOG
═══════════════════════════════════════════════════════════════════════════════════════════════════

A conversion rate is a claim about a numerator and a denominator. Clicked into a UI, that claim is
unreviewable: nobody can diff it, nobody notices when it drifts, and the failure mode is a chart
that keeps rendering a plausible number after its meaning has changed. Defined here, every
numerator and denominator is a line in a pull request, and `test_g100_d0_funnel_telemetry.py` fails
if the event names drift from the ones the app actually emits.

⛔ THE EVENT NAMES ARE A CONTRACT with `frontend/lib/funnel-telemetry.ts` and `docs/g100_d0_funnel.md`.
A rename in one place and not the others produces a chart that reads ZERO — which looks like a
conversion collapse, not like a broken query. That is the single most expensive way this can fail.

═══════════════════════════════════════════════════════════════════════════════════════════════════
THE ONE THING TO UNDERSTAND BEFORE READING ANY NUMBER OFF THIS DASHBOARD
═══════════════════════════════════════════════════════════════════════════════════════════════════

EVERY METRIC COUNTS DISTINCT PERSONS, NEVER EVENTS.

`custom_board_viewed` — the activation marker — fires once per page MOUNT by design, and one real
user produced three in an hour during G100-C1's live testing. An activation rate computed on event
volume is inflated by revisits; an inflated activation rate reads as a CONVERSION problem; and the
next story then goes and rebuilds pricing when nothing is wrong with pricing.

So: `math="dau"` on every trend series (PostHog's unique-persons-in-period), and person-level
aggregation on every funnel. There is no series in this file that counts events, and there should
never be one.

Usage (LAPTOP):

    uv run python scripts/provision_posthog_funnel_dashboard.py --dry-run
    POSTHOG_PERSONAL_API_KEY=phx_… POSTHOG_PROJECT_ID=12345 \
        uv run python scripts/provision_posthog_funnel_dashboard.py --apply

`--apply` is idempotent by NAME: an insight already on the dashboard is updated in place rather
than duplicated, so re-running after editing a query is the normal way to change one.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field

# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. The contract — must match `frontend/lib/funnel-telemetry.ts`
# ══════════════════════════════════════════════════════════════════════════════════════════════

LANDING_VIEW = "landing_view"
SIGNUP_COMPLETED = "user_signup_completed"
LEAGUE_CONFIG_COMPLETED = "league_config_completed"
CUSTOM_BOARD_VIEWED = "custom_board_viewed"  # ⭐ ACTIVATION
CHECKOUT_STARTED = "checkout_started"
SUBSCRIPTION_STARTED = "subscription_started"

#: The ordered spine. Order is part of the contract: the funnel insight below is an ORDERED funnel,
#: so a person is counted at step n+1 only if they reached step n first.
FUNNEL_SPINE: tuple[str, ...] = (
    LANDING_VIEW,
    SIGNUP_COMPLETED,
    LEAGUE_CONFIG_COMPLETED,
    CUSTOM_BOARD_VIEWED,
    CHECKOUT_STARTED,
    SUBSCRIPTION_STARTED,
)

#: Human labels, shown on the funnel steps.
STEP_LABELS: dict[str, str] = {
    LANDING_VIEW: "1 · Visitor (acquisition surface)",
    SIGNUP_COMPLETED: "2 · Signed up",
    LEAGUE_CONFIG_COMPLETED: "3 · League configured",
    CUSTOM_BOARD_VIEWED: "4 · ACTIVATED (own board seen)",
    CHECKOUT_STARTED: "5 · Checkout started",
    SUBSCRIPTION_STARTED: "6 · Paid",
}

#: How long a person has to walk the whole funnel and still be counted as converted.
#: ⚠️ The trailing days of any cohort funnel are INCOMPLETE by construction — the last week's
#: cohorts have not finished converting yet, so a downward slope at the right-hand edge is this
#: window, not a regression. Stated on the insight so a reader cannot miss it.
FUNNEL_WINDOW_DAYS = 7

DEFAULT_DATE_FROM = "-30d"
DEFAULT_HOST = "https://us.posthog.com"
DASHBOARD_NAME = "G100 — Founder daily funnel"


@dataclass(frozen=True)
class Rate:
    """One conversion rate, with its numerator and denominator named explicitly.

    ⭐ `statement` is not decoration. It is rendered into the insight's DESCRIPTION so the
    definition travels with the chart — a rate whose denominator is not visible next to it WILL be
    misread, and the three specific misreadings this dashboard is exposed to are each written out
    in the statements below.
    """

    key: str
    title: str
    denominator: str
    numerator: str
    statement: str


RATES: tuple[Rate, ...] = (
    Rate(
        key="r1_visitor_to_signup",
        title="R1 · visitor → signup",
        denominator=LANDING_VIEW,
        numerator=SIGNUP_COMPLETED,
        statement=(
            "NUMERATOR: distinct persons with >=1 `user_signup_completed`. "
            "DENOMINATOR: distinct persons with >=1 `landing_view`. "
            "A 'visitor' is a PostHog PERSON — a de-duplicated device+storage identity, not a "
            "human: one person on a phone and a laptop counts twice, so this is a FLOOR on the "
            "true rate. "
            "WARNING: `user_signup_completed` is NOT `account_created` — it means 'clicked Sign Up, "
            "completed the OAuth round-trip, has a session', which INCLUDES a returning user who "
            "clicked Sign Up. For new-account counts use COGNITO creation dates; if the two "
            "disagree, Cognito is right."
        ),
    ),
    Rate(
        key="r2_signup_to_activation",
        title="R2 · signup → ACTIVATION",
        denominator=SIGNUP_COMPLETED,
        numerator=CUSTOM_BOARD_VIEWED,
        statement=(
            "NUMERATOR: distinct persons with >=1 `custom_board_viewed`. "
            "DENOMINATOR: distinct persons with >=1 `user_signup_completed`. "
            "Activation is G100-C1's conjunction (account_created AND league_config_completed AND "
            "custom_board_viewed); `custom_board_viewed` is its TERMINAL clause and is unreachable "
            "without a saved league, which is why it stands for the whole. "
            "WARNING: counted on PERSONS, never events — `custom_board_viewed` fires once per page "
            "mount and one user produced three in an hour."
        ),
    ),
    Rate(
        key="r3_activation_to_paid",
        title="R3 · ACTIVATION → paid",
        denominator=CUSTOM_BOARD_VIEWED,
        numerator=SUBSCRIPTION_STARTED,
        statement=(
            "NUMERATOR: distinct persons with >=1 `subscription_started`. "
            "DENOMINATOR: distinct persons with >=1 `custom_board_viewed` — ACTIVATION IS THE PAID "
            "DENOMINATOR. "
            "WARNING: `subscription_started` is client-confirmed (it fires once the Stripe webhook "
            "has granted access, on the post-checkout screen), so a buyer who closes the tab during "
            "provisioning is never counted. It is a FLOOR on paid conversions; STRIPE is the source "
            "of truth for the paid COUNT."
        ),
    ),
)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. Query builders — PostHog's HogQL query schema (`InsightVizNode`)
# ══════════════════════════════════════════════════════════════════════════════════════════════


def _unique_persons_series(event: str, label: str | None = None) -> dict:
    """One trend series counting UNIQUE PERSONS per interval.

    `math="dau"` is PostHog's name for "unique persons in the period" — it is not daily-specific
    despite the name; with `interval="day"` it is exactly distinct persons per day. ⛔ Never
    `math="total"` here: see this module's header for what event-counting does to the activation
    rate.
    """
    return {
        "kind": "EventsNode",
        "event": event,
        "name": event,
        "custom_name": label or STEP_LABELS.get(event, event),
        "math": "dau",
    }


def build_funnel_query(breakdown_property: str | None = None) -> dict:
    """The ordered, person-level funnel over the whole spine.

    ⭐ THIS IS THE COHORT-CORRECT READING of all three rates, and the one to use for LEVEL
    ("what fraction of visitors convert?"). The daily-ratio insights are for TREND only — their
    numerator and denominator are different people (see `build_rate_query`).
    """
    source: dict = {
        "kind": "FunnelsQuery",
        "series": [
            {"kind": "EventsNode", "event": e, "name": e, "custom_name": STEP_LABELS[e]}
            for e in FUNNEL_SPINE
        ],
        "dateRange": {"date_from": DEFAULT_DATE_FROM},
        "funnelsFilter": {
            "funnelVizType": "steps",
            "funnelOrderType": "ordered",
            "funnelWindowInterval": FUNNEL_WINDOW_DAYS,
            "funnelWindowIntervalUnit": "day",
        },
    }
    if breakdown_property:
        source["breakdownFilter"] = {
            "breakdown_type": "event",
            "breakdown": breakdown_property,
        }
    return {"kind": "InsightVizNode", "source": source}


def build_step_counts_query() -> dict:
    """Distinct persons per day, one series per spine step — the 'what happened today' table."""
    return {
        "kind": "InsightVizNode",
        "source": {
            "kind": "TrendsQuery",
            "series": [_unique_persons_series(e) for e in FUNNEL_SPINE],
            "interval": "day",
            "dateRange": {"date_from": DEFAULT_DATE_FROM},
            "trendsFilter": {"display": "ActionsLineGraph"},
        },
    }


def build_rate_query(rate: Rate) -> dict:
    """A rate as a per-day ratio of two unique-person counts.

    ⚠️ THIS IS A SAME-DAY RATIO, NOT A COHORT CONVERSION, and the difference is not pedantic: the
    numerator and denominator are DIFFERENT PEOPLE. Someone who signs up today may have landed a
    week ago, so on any given day this can sit above or below the true conversion rate purely from
    the shape of traffic. Right instrument for "is today unusual?", wrong one for "what fraction of
    visitors convert?" — for that, read the funnel insight.

    Series order is load-bearing: `A` is the DENOMINATOR, `B` the NUMERATOR, formula `B / A`.
    """
    return {
        "kind": "InsightVizNode",
        "source": {
            "kind": "TrendsQuery",
            "series": [
                _unique_persons_series(rate.denominator, f"A · denominator ({rate.denominator})"),
                _unique_persons_series(rate.numerator, f"B · numerator ({rate.numerator})"),
            ],
            "interval": "day",
            "dateRange": {"date_from": DEFAULT_DATE_FROM},
            "trendsFilter": {"formula": "B / A", "display": "ActionsLineGraph"},
        },
    }


def build_segment_query() -> dict:
    """Activation → paid, split by the segments most likely to hide a real difference."""
    return {
        "kind": "InsightVizNode",
        "source": {
            "kind": "FunnelsQuery",
            "series": [
                {
                    "kind": "EventsNode",
                    "event": CUSTOM_BOARD_VIEWED,
                    "name": CUSTOM_BOARD_VIEWED,
                    "custom_name": STEP_LABELS[CUSTOM_BOARD_VIEWED],
                },
                {
                    "kind": "EventsNode",
                    "event": SUBSCRIPTION_STARTED,
                    "name": SUBSCRIPTION_STARTED,
                    "custom_name": STEP_LABELS[SUBSCRIPTION_STARTED],
                },
            ],
            "dateRange": {"date_from": DEFAULT_DATE_FROM},
            "breakdownFilter": {"breakdown_type": "event", "breakdown": "device"},
            "funnelsFilter": {
                "funnelVizType": "steps",
                "funnelOrderType": "ordered",
                "funnelWindowInterval": FUNNEL_WINDOW_DAYS,
                "funnelWindowIntervalUnit": "day",
            },
        },
    }


@dataclass(frozen=True)
class Insight:
    name: str
    description: str
    query: dict = field(repr=False)


_WINDOW_NOTE = (
    f"Cohort funnel, {FUNNEL_WINDOW_DAYS}-day conversion window, person-level. "
    f"NOTE: the most recent {FUNNEL_WINDOW_DAYS} days are INCOMPLETE by construction — those "
    "cohorts have not finished converting, so a dip at the right-hand edge is the window, not a "
    "regression."
)

_RATIO_NOTE = (
    "SAME-DAY RATIO, not a cohort conversion: the numerator and denominator are different people "
    "(someone signing up today may have landed last week). Use it for TREND ('is today unusual?'); "
    "for LEVEL ('what fraction convert?') read the funnel insight."
)


def build_insights() -> list[Insight]:
    """Every insight on the dashboard, in display order."""
    insights = [
        Insight(
            name="Funnel · full spine",
            description=(
                "The G100 acquisition funnel end to end, on DISTINCT PERSONS. "
                "Step 4 is ACTIVATION and is the denominator of paid conversion. " + _WINDOW_NOTE
            ),
            query=build_funnel_query(),
        ),
        Insight(
            name="Funnel · by acquisition source",
            description=(
                "The same funnel split by first-touch `acquisition_source` (utm_source, else the "
                "external referrer host, else 'direct'; an internal referrer is never recorded). "
                + _WINDOW_NOTE
            ),
            query=build_funnel_query(breakdown_property="acquisition_source"),
        ),
        Insight(
            name="Daily distinct persons per step",
            description=(
                "Unique persons per day at each step. ⛔ Persons, never events: "
                "`custom_board_viewed` fires once per page mount, so an event count here would "
                "inflate activation with revisits and read as a conversion problem."
            ),
            query=build_step_counts_query(),
        ),
    ]
    insights += [
        Insight(name=r.title, description=f"{r.statement} {_RATIO_NOTE}", query=build_rate_query(r))
        for r in RATES
    ]
    insights.append(
        Insight(
            name="ACTIVATION → paid, by device",
            description=(
                "Where the paid drop-off differs by viewport class. Add a `free_paid_status` "
                "breakdown to separate genuinely-free accounts from comped ones (admin / "
                "beta_tester / fantasy_comp are `comped`, never `paid` — folding them in would put "
                "the operator's own account in the numerator). " + _WINDOW_NOTE
            ),
            query=build_segment_query(),
        )
    )
    return insights


def build_dashboard_spec() -> dict:
    """The whole thing as plain data — what `--dry-run` prints and what the guard test reads."""
    return {
        "dashboard": {
            "name": DASHBOARD_NAME,
            "description": (
                "G100-D0. Every metric counts DISTINCT PERSONS, never events. "
                "New-account truth is COGNITO (not `user_signup_completed`); paid-count truth is "
                "STRIPE (not `subscription_started`). Definitions: docs/g100_d0_funnel.md."
            ),
        },
        "insights": [
            {"name": i.name, "description": i.description, "query": i.query}
            for i in build_insights()
        ],
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. The PostHog API (stdlib only — no new dependency for a once-per-project script)
# ══════════════════════════════════════════════════════════════════════════════════════════════


class PostHogApi:
    def __init__(self, host: str, project_id: str, api_key: str) -> None:
        self._base = f"{host.rstrip('/')}/api/projects/{project_id}"
        self._key = api_key

    def _request(self, method: str, path: str, body: dict | None = None) -> dict:
        url = f"{self._base}{path}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {self._key}")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode() or "{}")
        except urllib.error.HTTPError as exc:  # surface PostHog's own message, not a bare 400
            detail = exc.read().decode(errors="replace")[:2000]
            raise SystemExit(f"PostHog {method} {path} failed: HTTP {exc.code}\n{detail}") from exc

    def find_dashboard(self, name: str) -> dict | None:
        page = self._request("GET", "/dashboards/?limit=500")
        for item in page.get("results", []):
            if item.get("name") == name and not item.get("deleted"):
                return item
        return None

    def create_dashboard(self, spec: dict) -> dict:
        return self._request("POST", "/dashboards/", spec)

    def insights_on(self, dashboard_id: int) -> dict[str, int]:
        page = self._request("GET", f"/insights/?dashboards={dashboard_id}&limit=500")
        return {
            i["name"]: i["id"]
            for i in page.get("results", [])
            if i.get("name") and not i.get("deleted")
        }

    def upsert_insight(self, dashboard_id: int, insight: dict, existing_id: int | None) -> dict:
        body = {**insight, "dashboards": [dashboard_id]}
        if existing_id is not None:
            return self._request("PATCH", f"/insights/{existing_id}/", body)
        return self._request("POST", "/insights/", body)


def apply(host: str, project_id: str, api_key: str) -> None:
    spec = build_dashboard_spec()
    api = PostHogApi(host, project_id, api_key)

    dashboard = api.find_dashboard(spec["dashboard"]["name"])
    if dashboard is None:
        dashboard = api.create_dashboard(spec["dashboard"])
        print(f"created dashboard {dashboard['id']} — {dashboard['name']}")
    else:
        print(f"reusing dashboard {dashboard['id']} — {dashboard['name']}")

    # Idempotent by NAME: re-running after editing a query updates in place rather than piling up a
    # second copy of every chart, which is the failure this script would otherwise have on its
    # second run — and a duplicated chart with a stale definition beside a fresh one is worse than
    # no chart, because both look authoritative.
    existing = api.insights_on(dashboard["id"])
    for insight in spec["insights"]:
        result = api.upsert_insight(dashboard["id"], insight, existing.get(insight["name"]))
        verb = "updated" if insight["name"] in existing else "created"
        print(f"  {verb} insight {result.get('id')} — {insight['name']}")

    print(f"\n{host.rstrip('/')}/project/{project_id}/dashboard/{dashboard['id']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="print the payloads, write nothing")
    mode.add_argument("--apply", action="store_true", help="create/update the dashboard")
    parser.add_argument("--host", default=os.environ.get("POSTHOG_HOST", DEFAULT_HOST))
    parser.add_argument("--project-id", default=os.environ.get("POSTHOG_PROJECT_ID"))
    args = parser.parse_args(argv)

    if args.dry_run:
        print(json.dumps(build_dashboard_spec(), indent=2))
        return 0

    api_key = os.environ.get("POSTHOG_PERSONAL_API_KEY")
    if not api_key or not args.project_id:
        print(
            "--apply needs POSTHOG_PERSONAL_API_KEY and POSTHOG_PROJECT_ID (or --project-id).\n"
            "Create a personal API key with project write scope under PostHog > Settings.",
            file=sys.stderr,
        )
        return 2

    apply(args.host, args.project_id, api_key)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
