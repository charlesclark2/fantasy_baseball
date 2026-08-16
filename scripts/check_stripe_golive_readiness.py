#!/usr/bin/env python3
"""E9.8-P2 — the Stripe go-live readiness gate, as a re-runnable instrument.

WHY THIS IS A SCRIPT AND NOT A WRITEUP. Every check below was run by hand for the pre-flip
audit, and a hand-run audit is a SNAPSHOT: it answers "was this true on 2026-08-15", which is
not the question the operator has after flipping the keys, after a redeploy, or three weeks
into taking real money. So the audit ships as the thing that produced it.

⭐ THE DISCIPLINE IT ENCODES (G100-D1): a guardrail must be shown to ENFORCE, not to look
enabled — "a check whose failure state is indistinguishable from its healthy state has not
been verified". Concretely, that shapes three checks here:

  • The cost kill switch is read from the FLAG (`Environment.Variables.COST_DEGRADE_MODE`),
    never inferred from an endpoint's status code. There is NO anonymous request that can
    reveal it: every `--authorization-type NONE` route is also degrade-allowlisted by design,
    so a token-free probe 401s at the gateway (NF3.2) with degrade on OR off. An earlier
    incident (E9.46) already drew a wrong conclusion from exactly that reasoning.

  • The billing alarm is not accepted because it EXISTS. CloudWatch dimension matching is
    EXACT rather than subset, so an alarm can sit permanently OK on a dimension set the
    account never publishes. This asserts `get-metric-statistics` returns datapoints on the
    alarm's OWN dimensions, and that `TreatMissingData` is `missing` — with `notBreaching` an
    absent metric reads as healthy, which is the failure mode being guarded against.

  • The degrade allowlist is resolved against the REAL route table, not a guessed path. The
    G100-D1 defect was an allowlist entry written from a router's MOUNT name (`/stripe/public`)
    instead of its route decorator (`/subscription/public-pricing`): a wrong allowlist entry
    does not error, it silently DENIES, and only surfaces the one time the switch is flipped.

⛔ IT READS. It never writes, never flips a flag, and never touches a Stripe key beyond the
first 8 characters of the secret — which is the whole question a go-live turns on (`sk_test_`
vs `sk_live_`) and discloses no key material.

Run it from the LAPTOP, before the flip and again after:

    env -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY -u AWS_SESSION_TOKEN \\
      uv run python scripts/check_stripe_golive_readiness.py \\
        --profile AdministratorAccess-769392325318

    # After the flip, the expected end state changes — say so, and the gate re-aims:
    ... --expect-mode live --expect-mfa on

Exit codes: 0 = GO, 1 = NO-GO (at least one blocking check failed), 2 = could not evaluate.
⚠️ An UNEVALUABLE check is never scored healthy (NF1.7 (a)) — it reports UNKNOWN and, if it
is a blocking check, it blocks.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

FUNCTION = "credence-prod-lambda-api"
REGION = "us-east-1"
USER_POOL = "us-east-1_gG9zMbwQt"
USERS_TABLE = "credence-prod-dynamo-users"
API_ID = "8dhmehjak7"
BILLING_ALARM = "credence-prod-billing-over-250"
FOUNDING_COUNTER_PK = "__stripe_meta__#founding"

GO, NO_GO, UNKNOWN = "GO", "NO-GO", "UNKNOWN"


@dataclass
class Check:
    name: str
    verdict: str
    detail: str
    blocking: bool = True
    notes: list[str] = field(default_factory=list)


def aws(args: list[str], profile: str | None) -> str:
    cmd = ["aws", *args]
    if profile:
        cmd += ["--profile", profile]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"aws {' '.join(args[:3])}: {proc.stderr.strip()[:400]}")
    return proc.stdout


def aws_json(args: list[str], profile: str | None):
    return json.loads(aws([*args, "--output", "json"], profile))


# ── 1. Stripe mode + the flags, read from the flag itself ────────────────────────────────


def check_stripe_mode(profile: str | None, expect_mode: str) -> Check:
    """`sk_test_` vs `sk_live_` — read from the env, never inferred from behaviour."""
    try:
        env = aws_json(
            ["lambda", "get-function-configuration", "--function-name", FUNCTION,
             "--region", REGION, "--query", "Environment.Variables"],
            profile,
        )
    except Exception as exc:
        return Check("Stripe key mode", UNKNOWN, f"could not read the Lambda env: {exc}")

    key = env.get("STRIPE_SECRET_KEY") or ""
    # Only the mode prefix is ever read or printed. The rest is never touched.
    mode = "live" if key.startswith("sk_live_") else "test" if key.startswith("sk_test_") else "?"
    notes = []
    for name in ("STRIPE_PRICE_FOUNDING", "STRIPE_PRICE_STANDARD", "STRIPE_WEBHOOK_SECRET"):
        if not env.get(name):
            notes.append(f"{name} is ABSENT — billing will 503")
    whsec = env.get("STRIPE_WEBHOOK_SECRET") or ""
    if whsec and not whsec.startswith("whsec_"):
        notes.append("STRIPE_WEBHOOK_SECRET does not look like a Stripe signing secret")
    # ⚠️ The variable the CODE reads is STRIPE_WEBHOOK_SECRET. A signing secret parked under
    # any other name is invisible to the handler, which then 503s every delivery — and Stripe
    # retries for days before giving up, so the money lands with no subscription behind it.
    for wrong in ("STRIPE_WEBHOOK_SIGNING_SECRET", "STRIPE_ENDPOINT_SECRET"):
        if wrong in env:
            notes.append(
                f"{wrong} is set — the code reads STRIPE_WEBHOOK_SECRET, so this name is INERT"
            )
    verdict = GO if (mode == expect_mode and not notes) else NO_GO
    return Check("Stripe key mode", verdict, f"sk_{mode}_ (expected {expect_mode})", notes=notes)


def check_flag(profile: str | None, var: str, expect_on: bool, label: str) -> Check:
    """Read a boolean-ish Lambda flag. ⛔ Never infer a flag's state from an endpoint."""
    try:
        raw = aws(
            ["lambda", "get-function-configuration", "--function-name", FUNCTION,
             "--region", REGION, "--query", f"Environment.Variables.{var}", "--output", "text"],
            profile,
        ).strip()
    except Exception as exc:
        return Check(label, UNKNOWN, f"could not read {var}: {exc}")
    on = raw in ("1", "true", "True", "TRUE", "yes")
    shown = "<absent>" if raw in ("None", "") else raw
    return Check(
        label,
        GO if on == expect_on else NO_GO,
        f"{var}={shown} -> {'ON' if on else 'OFF'} (expected {'ON' if expect_on else 'OFF'})",
    )


# ── 2. The founding-100 counter ──────────────────────────────────────────────────────────


def check_founding_counter(profile: str | None, expect_max: int) -> Check:
    """The durable conversion counter that decides who gets the $10 grandfathered price.

    ⭐ THE PRE-FLIP HAZARD. Every conversion counted while Stripe was in TEST mode is a real
    increment of a real counter: `increment_founding_slots` is called from the webhook and
    knows nothing about which mode produced the event. Carrying those into go-live silently
    turns "the first 100 members" into the first (100 − N), and the very first paying
    customer is counted as #N+1. It is not self-correcting — the counter is never decremented
    (a freed slot is deliberately never reclaimed), so it can only be fixed BEFORE the flip.
    """
    try:
        item = aws_json(
            ["dynamodb", "get-item", "--table-name", USERS_TABLE, "--region", REGION,
             "--key", json.dumps({"user_id": {"S": FOUNDING_COUNTER_PK}})],
            profile,
        )
    except Exception as exc:
        return Check("Founding counter", UNKNOWN, f"could not read the counter: {exc}")

    used = int(item.get("Item", {}).get("slots_used", {}).get("N", 0) or 0)
    notes = []
    if used > expect_max:
        notes.append(
            f"{used} conversions already counted. Any that came from Stripe TEST mode must be "
            f"cleared BEFORE the flip or the founding-100 promise silently becomes founding-{100 - used}."
        )
    return Check(
        "Founding counter",
        GO if used <= expect_max else NO_GO,
        f"slots_used={used} (expected <= {expect_max}); {max(0, 100 - used)} founding seats would be offered",
        notes=notes,
    )


def check_stripe_customer_links(profile: str | None) -> Check:
    """Stripe customer links whose Cognito user no longer exists = test-walkthrough residue.

    Advisory: an orphan cannot grant access (the group is the entitlement) but it is the
    fingerprint of a test-mode conversion, and the count is the number to reconcile the
    founding counter against.
    """
    try:
        scan = aws_json(
            ["dynamodb", "scan", "--table-name", USERS_TABLE, "--region", REGION],
            profile,
        )
    except Exception as exc:
        return Check("Stripe customer links", UNKNOWN, f"could not scan: {exc}", blocking=False)

    links = {
        list(it["user_id"].values())[0].split("#", 1)[1]: list(it["cognito_sub"].values())[0]
        for it in scan.get("Items", [])
        if list(it["user_id"].values())[0].startswith("__stripe_customer__#") and "cognito_sub" in it
    }
    events = sum(
        1 for it in scan.get("Items", [])
        if list(it["user_id"].values())[0].startswith("__stripe_event__#")
    )
    orphans = []
    for customer, sub in links.items():
        try:
            aws(["cognito-idp", "admin-get-user", "--user-pool-id", USER_POOL,
                 "--username", sub, "--region", REGION, "--query", "Username", "--output", "text"], profile)
        except Exception:
            orphans.append(f"{customer} -> {sub[:12]}… (Cognito user deleted)")
    notes = [f"orphaned: {o}" for o in orphans]
    return Check(
        "Stripe customer links",
        GO if not orphans else UNKNOWN,
        f"{len(links)} customer link(s), {events} processed webhook event(s), {len(orphans)} orphaned",
        blocking=False,
        notes=notes,
    )


# ── 3. Who gets locked out when ENFORCE_SUBSCRIBER_MFA flips on ──────────────────────────


def check_mfa_lockout_risk(profile: str | None) -> Check:
    """Every `subscriber` who would be 403'd the moment MFA enforcement goes on.

    A subscriber is SAFE if any one holds:
      • a federated username (`google_…`) — `_username_is_federated` exempts it;
      • the `passwordless` group — `_totp_exemption` exempts it (G100-C0-MFA);
      • an enrolled SOFTWARE_TOKEN_MFA factor — they simply pass the gate.

    Anyone else is a PAYING CUSTOMER locked out of what they bought, whose only self-service
    exit asks for a credential the account may never have had. Silence here means nobody is
    lockable; a name here is a blocker, not a warning.
    """
    try:
        users = aws_json(
            ["cognito-idp", "list-users-in-group", "--user-pool-id", USER_POOL,
             "--group-name", "subscriber", "--region", REGION],
            profile,
        ).get("Users", [])
    except Exception as exc:
        return Check("MFA lockout risk", UNKNOWN, f"could not list subscribers: {exc}")

    lockable, safe = [], []
    for u in users:
        username = u["Username"]
        attrs = {a["Name"]: a["Value"] for a in u.get("Attributes", [])}
        email = attrs.get("email", "?")
        federated = username.split("_", 1)[0].lower() in (
            "google", "signinwithapple", "facebook", "loginwithamazon"
        ) and "@" not in username
        try:
            groups = aws_json(
                ["cognito-idp", "admin-list-groups-for-user", "--user-pool-id", USER_POOL,
                 "--username", username, "--region", REGION, "--query", "Groups[].GroupName"],
                profile,
            ) or []
            detail = aws_json(
                ["cognito-idp", "admin-get-user", "--user-pool-id", USER_POOL,
                 "--username", username, "--region", REGION, "--query", "UserMFASettingList"],
                profile,
            ) or []
        except Exception as exc:
            lockable.append(f"{email} ({username}) — UNREADABLE, failing closed: {exc}")
            continue
        if federated:
            safe.append(f"{email}: federated username -> exempt")
        elif "passwordless" in groups:
            safe.append(f"{email}: passwordless group -> exempt")
        elif "SOFTWARE_TOKEN_MFA" in detail:
            safe.append(f"{email}: TOTP enrolled -> passes")
        else:
            lockable.append(f"{email} ({username}) — UUID username, no passwordless, no TOTP")

    return Check(
        "MFA lockout risk",
        GO if not lockable else NO_GO,
        f"{len(users)} subscriber(s); {len(lockable)} would be locked out",
        notes=[*(f"LOCKABLE: {x}" for x in lockable), *(f"safe — {x}" for x in safe)],
    )


# ── 4. The billing alarm — existence is not evidence ─────────────────────────────────────


def check_billing_alarm(profile: str | None) -> Check:
    try:
        alarms = aws_json(
            ["cloudwatch", "describe-alarms", "--alarm-names", BILLING_ALARM, "--region", REGION],
            profile,
        ).get("MetricAlarms", [])
    except Exception as exc:
        return Check("Billing alarm", UNKNOWN, f"could not describe alarms: {exc}")
    if not alarms:
        return Check("Billing alarm", NO_GO, f"{BILLING_ALARM} does not exist")

    a = alarms[0]
    notes, ok = [], True
    if a.get("TreatMissingData") != "missing":
        ok = False
        notes.append(
            f"TreatMissingData={a.get('TreatMissingData')} — with anything but 'missing' an "
            f"ABSENT metric reads as healthy and the alarm is blind"
        )
    if not a.get("AlarmActions"):
        ok = False
        notes.append("no AlarmActions — it would fire into nothing")
    if not a.get("ActionsEnabled", True):
        ok = False
        notes.append("ActionsEnabled=false — it would fire into nothing")

    # ⭐ The dimension proof. CloudWatch matches dimensions EXACTLY, so an alarm on a
    # dimension set the account never publishes sits permanently OK. A non-empty
    # `list-metrics` is NOT proof; only statistics on the alarm's OWN dimensions settle it.
    dims = a.get("Dimensions", [])
    try:
        end = datetime.now(timezone.utc)
        stats = aws_json(
            ["cloudwatch", "get-metric-statistics",
             "--namespace", a["Namespace"], "--metric-name", a["MetricName"],
             "--dimensions", *[f"Name={d['Name']},Value={d['Value']}" for d in dims],
             "--start-time", (end - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),
             "--end-time", end.strftime("%Y-%m-%dT%H:%M:%SZ"),
             "--period", "21600", "--statistics", "Maximum", "--region", REGION],
            profile,
        )
        points = stats.get("Datapoints", [])
    except Exception as exc:
        return Check("Billing alarm", UNKNOWN, f"could not prove the metric carries data: {exc}")

    if not points:
        ok = False
        notes.append(
            f"NO DATAPOINTS on the alarm's own dimensions {dims} — the alarm is BLIND. "
            f"(Account billing alerts may be off, or the dimension set may not be published.)"
        )
    else:
        latest = max(points, key=lambda p: p["Timestamp"])
        notes.append(
            f"metric proven live: {len(points)} datapoints, latest ${latest['Maximum']} "
            f"at {latest['Timestamp']}"
        )
    return Check(
        "Billing alarm",
        GO if ok else NO_GO,
        f"{BILLING_ALARM} thr=${a.get('Threshold')} dims={[d['Value'] for d in dims]} state={a.get('StateValue')}",
        notes=notes,
    )


# ── 5. Public routes vs the degrade allowlist ────────────────────────────────────────────


def check_public_routes_and_degrade(profile: str | None) -> Check:
    """Two properties in one read, because they are two halves of one contract.

    (a) The billing routes that CANNOT carry a Cognito token — `POST /stripe/webhook`
        (Stripe presents no token; the signature is its auth) and `GET
        /subscription/public-pricing` (a logged-out visitor) — must be
        `--authorization-type NONE`, or the JWT authorizer 401s them in front of the Lambda
        and the code's own public-ness is irrelevant (NF3.2).

    (b) EVERY public route must survive degrade mode. If the kill switch can 503 a route no
        caller can authenticate to, flipping it during a cost event blacks out an anonymous
        surface — and for `/stripe/webhook` it would silently drop real payment events.
    """
    try:
        routes = aws_json(
            ["apigatewayv2", "get-routes", "--api-id", API_ID, "--region", REGION,
             "--max-results", "200"],
            profile,
        ).get("Items", [])
    except Exception as exc:
        return Check("Public routes / degrade", UNKNOWN, f"could not read routes: {exc}")

    try:
        # Anchor on THIS FILE's location, not the CWD. A go-live gate that only works when
        # invoked from the repo root would report UNKNOWN — and therefore BLOCK — for a reason
        # that has nothing to do with the system under test, which during a flip reads as a
        # real defect. It fails closed either way; this makes it fail closed for true reasons.
        repo_root = str(Path(__file__).resolve().parents[1])
        if repo_root not in sys.path:
            sys.path.insert(0, repo_root)
        from app.backend.services.cost_guardrails import is_allowed_in_degrade
    except Exception as exc:
        return Check("Public routes / degrade", UNKNOWN, f"could not import the allowlist: {exc}")

    by_key = {r["RouteKey"]: r.get("AuthorizationType") for r in routes}
    notes, ok = [], True
    for required in ("POST /stripe/webhook", "GET /subscription/public-pricing"):
        if by_key.get(required) != "NONE":
            ok = False
            notes.append(f"{required} is {by_key.get(required)!r}, not NONE — it will 401 at the gateway")

    blacked_out = []
    for key, auth in sorted(by_key.items()):
        if auth != "NONE":
            continue
        method, _, path = key.partition(" ")
        if method == "OPTIONS":
            continue  # preflight bypasses the degrade check by design
        probe = path.replace("{proxy+}", "x").replace("{id}", "1").replace("{season}", "2025")
        if not is_allowed_in_degrade(probe):
            blacked_out.append(key)
    if blacked_out:
        ok = False
        notes.append(f"public routes the kill switch would 503: {blacked_out}")
    else:
        notes.append(
            f"all {sum(1 for a in by_key.values() if a == 'NONE')} public routes stay up in degrade mode"
        )
    return Check("Public routes / degrade", GO if ok else NO_GO, f"{len(routes)} routes on {API_ID}", notes=notes)


# ── report ───────────────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="E9.8-P2 Stripe go-live readiness gate (read-only).")
    p.add_argument("--profile", default=None)
    p.add_argument("--expect-mode", choices=("test", "live"), default="test",
                   help="the Stripe mode you expect RIGHT NOW (pre-flip: test; post-flip: live)")
    p.add_argument("--expect-mfa", choices=("on", "off"), default="off")
    p.add_argument("--expect-degrade", choices=("on", "off"), default="off")
    p.add_argument("--max-founding-used", type=int, default=0,
                   help="how many conversions may already be counted (pre-flip this should be 0)")
    args = p.parse_args(argv)

    checks = [
        check_stripe_mode(args.profile, args.expect_mode),
        check_flag(args.profile, "ENFORCE_SUBSCRIBER_MFA", args.expect_mfa == "on", "Subscriber MFA flag"),
        check_flag(args.profile, "COST_DEGRADE_MODE", args.expect_degrade == "on", "Cost kill switch"),
        check_founding_counter(args.profile, args.max_founding_used),
        check_stripe_customer_links(args.profile),
        check_mfa_lockout_risk(args.profile),
        check_billing_alarm(args.profile),
        check_public_routes_and_degrade(args.profile),
    ]

    print("=" * 92)
    print("E9.8-P2 — STRIPE GO-LIVE READINESS")
    print(f"expecting: mode={args.expect_mode}  mfa={args.expect_mfa}  degrade={args.expect_degrade}"
          f"  founding_used<={args.max_founding_used}")
    print("=" * 92)
    for c in checks:
        tag = {GO: "  GO  ", NO_GO: "NO-GO ", UNKNOWN: "UNKNWN"}[c.verdict]
        print(f"[{tag}] {c.name}: {c.detail}")
        for n in c.notes:
            print(f"           - {n}")
    print("=" * 92)

    # An UNEVALUABLE blocking check is never scored healthy (NF1.7 (a)).
    blockers = [c for c in checks if c.blocking and c.verdict != GO]
    if blockers:
        print(f"VERDICT: NO-GO — {len(blockers)} blocking check(s) not GO:")
        for c in blockers:
            print(f"  • {c.name} [{c.verdict}]")
        return 1
    advisory = [c for c in checks if not c.blocking and c.verdict != GO]
    print("VERDICT: GO" + (f" (with {len(advisory)} advisory item(s))" if advisory else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
