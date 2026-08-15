"""DynamoDB service for per-user bets and the users registry (OLTP).

Bets are transactional (single-row writes on log, per-user reads on page load,
point updates on settle), so they live in DynamoDB rather than Snowflake. See
infrastructure/aws_resources.md for the table specs.

Tables:
  credence-prod-dynamo-user-bets — PK user_id (Cognito sub), SK bet_id.
      Sparse GSI gsi-pending-by-game (PK pending_game_pk): only PENDING bets carry
      pending_game_pk, so the settle job (scripts/settle_user_bets.py) finds them
      there; settling REMOVEs it.
  credence-prod-dynamo-users — PK user_id; email, first_seen_at, last_seen_at.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import boto3
from boto3.dynamodb.conditions import Key

logger = logging.getLogger(__name__)

_REGION = os.getenv("AWS_REGION", "us-east-1")
_USER_BETS_TABLE = os.getenv("USER_BETS_TABLE", "credence-prod-dynamo-user-bets")
_USERS_TABLE = os.getenv("USERS_TABLE", "credence-prod-dynamo-users")

_ddb = boto3.resource("dynamodb", region_name=_REGION)


def _bets_table():
    return _ddb.Table(_USER_BETS_TABLE)


def _users_table():
    return _ddb.Table(_USERS_TABLE)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_dynamo(d: dict) -> dict:
    """Floats → Decimal (DynamoDB rejects floats); drop None-valued keys."""
    clean = {k: v for k, v in d.items() if v is not None}
    return json.loads(json.dumps(clean, default=str), parse_float=Decimal)


def _from_dynamo(item: dict) -> dict:
    """Decimal → int (when integral) or float, for clean JSON responses."""
    out: dict = {}
    for k, v in item.items():
        if isinstance(v, Decimal):
            out[k] = int(v) if v == v.to_integral_value() else float(v)
        else:
            out[k] = v
    return out


# ── Bets ─────────────────────────────────────────────────────────────────────

def put_bet(user_id: str, bet: dict) -> dict:
    """Write a new bet under user_id. Stamps bet_id/placed_at and marks it pending
    (pending_game_pk = game_pk) so the settle job picks it up via the GSI."""
    item = dict(bet)
    item["user_id"] = user_id
    item["bet_id"] = str(uuid4())
    item["placed_at"] = _now_iso()
    item["pending_game_pk"] = int(bet["game_pk"])
    _bets_table().put_item(Item=_to_dynamo(item))
    return _from_dynamo(_to_dynamo(item))


def list_bets(user_id: str) -> list[dict]:
    """All of a user's bets, newest first. Not S3-cached (per-user OLTP read)."""
    items: list[dict] = []
    kwargs = {"KeyConditionExpression": Key("user_id").eq(user_id)}
    while True:
        resp = _bets_table().query(**kwargs)
        items.extend(resp.get("Items", []))
        lek = resp.get("LastEvaluatedKey")
        if not lek:
            break
        kwargs["ExclusiveStartKey"] = lek
    bets = [_from_dynamo(it) for it in items]
    bets.sort(key=lambda b: b.get("placed_at", ""), reverse=True)
    return bets


def delete_bet(user_id: str, bet_id: str) -> None:
    """Delete a bet owned by user_id. Raises ValueError if not found."""
    table = _bets_table()
    resp = table.get_item(Key={"user_id": user_id, "bet_id": bet_id})
    if "Item" not in resp:
        raise ValueError("not_found")
    table.delete_item(Key={"user_id": user_id, "bet_id": bet_id})


_IMMUTABLE_KEYS = {"user_id", "bet_id", "placed_at", "game_pk", "pending_game_pk"}


def update_bet(user_id: str, bet_id: str, updates: dict) -> dict:
    """Update mutable fields of a bet. Returns the updated item. Raises ValueError if not found.

    Settling a bet (setting a terminal `outcome`) ALSO REMOVEs `pending_game_pk` so the bet
    drops out of the sparse gsi-pending-by-game index — mirroring settle_user_bets.py's atomic
    `SET outcome ... REMOVE pending_game_pk`. Without this, the SET-only update left auto-voided
    bets (routers/bets.py) stuck in the pending index forever (they re-scan every settle pass
    and never clear). REMOVE of an absent attribute is a harmless no-op, so this is safe for an
    already-settled bet too.

    E9.49: settling also stamps `settled_at` (if_not_exists, so the canonical close time is
    never rewritten) — mirroring settle_user_bets.py. Without it nothing recorded WHEN a bet
    closed, which is why a prop sitting open for days was unmeasurable.
    """
    table = _bets_table()
    resp = table.get_item(Key={"user_id": user_id, "bet_id": bet_id})
    if "Item" not in resp:
        raise ValueError("not_found")

    patch = _to_dynamo({k: v for k, v in updates.items() if v is not None and k not in _IMMUTABLE_KEYS})
    settling = updates.get("outcome") is not None  # a terminal outcome ⇒ drop from pending GSI
    if not patch and not settling:
        return _from_dynamo(resp["Item"])

    keys = list(patch.keys())
    vals = list(patch.values())
    names = {f"#k{i}": k for i, k in enumerate(keys)}
    values = {f":v{i}": v for i, v in enumerate(vals)}
    set_parts = [f"#k{i} = :v{i}" for i in range(len(keys))]

    if settling:
        names["#sa"] = "settled_at"
        values[":sa"] = _now_iso()
        set_parts.append("#sa = if_not_exists(#sa, :sa)")

    expr = "SET " + ", ".join(set_parts) if set_parts else ""
    if settling:
        names["#pgp"] = "pending_game_pk"
        expr = (expr + " " if expr else "") + "REMOVE #pgp"

    kwargs = {
        "Key": {"user_id": user_id, "bet_id": bet_id},
        "UpdateExpression": expr,
        "ExpressionAttributeNames": names,
        "ReturnValues": "ALL_NEW",
    }
    if values:  # boto3 rejects an empty ExpressionAttributeValues (REMOVE-only case)
        kwargs["ExpressionAttributeValues"] = values

    result = table.update_item(**kwargs)
    return _from_dynamo(result["Attributes"])


# ── Users registry ───────────────────────────────────────────────────────────

def upsert_user(user_id: str, email: str | None) -> None:
    """Idempotent login-sync. Sets last_seen_at (+ email) every call; first_seen_at
    only on the first write. `sub` is trusted (from the JWT); email is metadata."""
    now = _now_iso()
    names = {"#ls": "last_seen_at", "#fs": "first_seen_at"}
    values = {":now": now}
    set_parts = ["#ls = :now", "#fs = if_not_exists(#fs, :now)"]
    if email is not None:
        names["#em"] = "email"
        values[":em"] = email
        set_parts.append("#em = :em")
    _users_table().update_item(
        Key={"user_id": user_id},
        UpdateExpression="SET " + ", ".join(set_parts),
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
    )


def record_tos_acceptance(user_id: str, tos_version: str) -> bool:
    """Record first-time ToS acceptance. Returns True iff THIS call was the first one.

    Preserves the original tos_accepted_at if already set (if_not_exists) so re-runs don't
    overwrite the canonical timestamp. tos_version is always updated so we track the latest
    version agreed to.

    ⭐ G100-D0-R1 — WHY THE RETURN VALUE EXISTS, AND WHY `ALL_OLD` RATHER THAN A READ.
    The signup funnel needs to know whether a sign-in CREATED an account, and the client
    cannot know: Google federation auto-provisions at either door, so a first-time visitor
    who clicks *Sign In* gets a brand-new account and looks byte-identical to a returning
    one. This write is the only thing in the request path that already knows — `if_not_exists`
    makes the FIRST acceptance distinguishable from every later one.

    `ReturnValues="ALL_OLD"` returns the item AS IT WAS BEFORE this update, in the SAME atomic
    operation. That is what makes the answer exactly-once under concurrency: two simultaneous
    calls are serialised by DynamoDB, so precisely one of them sees no prior `tos_accepted_at`.
    A read-then-write (or a follow-up get_item) would let both callers report `created` and
    double-count the signup — which is worse than the under-count this replaces, because
    nothing downstream would ever question a number that is too high.

    ⚠️ IT MEANS "FIRST ACCEPTANCE", WHICH IS A PROXY FOR "ACCOUNT CREATED", NOT A SYNONYM.
    It is exact for every account created since E9.58b (acceptance is written on every
    sign-in, so the first one lands on the account's first session). It can be late by one
    session for an account that predates that record — see the caller in routers/auth.py and
    docs/g100_d0_funnel.md §3 for the bound, which is one-time and historical.
    """
    now = _now_iso()
    resp = _users_table().update_item(
        Key={"user_id": user_id},
        UpdateExpression="SET #ta = if_not_exists(#ta, :now), #tv = :ver",
        ExpressionAttributeNames={"#ta": "tos_accepted_at", "#tv": "tos_version"},
        ExpressionAttributeValues={":now": now, ":ver": tos_version},
        ReturnValues="ALL_OLD",
    )
    # No `Attributes` at all ⇒ the item did not exist ⇒ this is the first acceptance. An item
    # that existed WITHOUT the attribute (a profile created by some other write) is equally a
    # first acceptance, so the test is on the attribute, never on the item.
    return (resp.get("Attributes") or {}).get("tos_accepted_at") is None


def get_user_profile(user_id: str) -> dict:
    """Return the user's mutable profile fields (initial_deposit etc.).

    E9.58b: also returns the ToS acceptance record. Since E9.58 opened public self-serve
    signup, this is the evidence that a given account agreed to the Terms — so the client
    needs to be able to READ it, not just write it, in order to notice an account that has
    none and re-prompt. `tos_accepted_at` is None for an account with no record.
    """
    resp = _users_table().get_item(Key={"user_id": user_id})
    item = resp.get("Item", {})
    raw_deposit = item.get("initial_deposit")
    return {
        "initial_deposit": float(raw_deposit) if raw_deposit is not None else None,
        "tos_accepted_at": item.get("tos_accepted_at"),
        "tos_version": item.get("tos_version"),
    }


def update_user_profile(user_id: str, initial_deposit: float | None) -> dict:
    """Update mutable profile fields. Only initial_deposit for now."""
    if initial_deposit is not None:
        _users_table().update_item(
            Key={"user_id": user_id},
            UpdateExpression="SET #id = :v",
            ExpressionAttributeNames={"#id": "initial_deposit"},
            ExpressionAttributeValues={":v": Decimal(str(initial_deposit))},
        )
    return get_user_profile(user_id)


# ── Bankroll bookkeeping (E9.17) ─────────────────────────────────────────────

def _deep_from_dynamo(obj):
    """Recursively convert Decimal → int/float in nested dicts and lists."""
    if isinstance(obj, Decimal):
        return int(obj) if obj == obj.to_integral_value() else float(obj)
    if isinstance(obj, dict):
        return {k: _deep_from_dynamo(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_deep_from_dynamo(v) for v in obj]
    return obj


def _to_ddb(obj):
    """Convert any JSON-serialisable object for DynamoDB storage (floats → Decimal)."""
    return json.loads(json.dumps(obj, default=str), parse_float=Decimal)


def compute_bankroll_growth(
    book_accounts: dict,
    bankroll_events: list,
) -> dict:
    """Pure function: compute per-book and overall growth from accounts + events.

    Growth math (honest: cash-flow neutral)
        net_deposits  = Σ deposits − Σ withdrawals   (per book / overall)
        betting_pnl   = current_balance − net_deposits
        growth_pct    = betting_pnl / Σ deposits      (None until first deposit)

    A deposit is NOT growth; a withdrawal is NOT a loss — both net out so the
    percentage reflects only betting performance.

    Per-book baseline reset (E9.17 Phase 2): a book's account entry may carry a
    ``baseline`` marker ({basis, deposited_offset, withdrawn_offset, reset_at}).
    When present the prior cash-flow history is re-based out and the snapshot
    balance (``basis``) is treated as a fresh deposit, so growth_pct restarts at
    0% from the current balance. Events themselves are never deleted.
    """
    flows: dict = {}
    for evt in bankroll_events:
        book = evt.get("book", "Unspecified")
        if book not in flows:
            flows[book] = {"total_deposited": 0.0, "total_withdrawn": 0.0}
        amt = float(evt.get("amount", 0))
        if evt.get("type") == "deposit":
            flows[book]["total_deposited"] += amt
        elif evt.get("type") == "withdrawal":
            flows[book]["total_withdrawn"] += amt

    for book in book_accounts:
        if book not in flows:
            flows[book] = {"total_deposited": 0.0, "total_withdrawn": 0.0}

    per_book: dict = {}
    for book, f in flows.items():
        info = book_accounts.get(book) or {}
        bal = float(info.get("current_balance", 0))
        td, tw = f["total_deposited"], f["total_withdrawn"]

        baseline = info.get("baseline")
        reset_at = None
        if baseline:
            basis = float(baseline.get("basis", 0))
            dep_off = float(baseline.get("deposited_offset", 0))
            wd_off = float(baseline.get("withdrawn_offset", 0))
            reset_at = baseline.get("reset_at")
            # Re-base: drop cash-flow recorded up to the reset, then inject the
            # snapshot balance as the fresh cost basis. max() guards against an
            # event deleted after the reset dragging a total below its offset.
            td = max(0.0, td - dep_off) + basis
            tw = max(0.0, tw - wd_off)

        nd = td - tw
        pnl = bal - nd
        per_book[book] = {
            "total_deposited": round(td, 2),
            "total_withdrawn": round(tw, 2),
            "net_deposits": round(nd, 2),
            "current_balance": round(bal, 2),
            "betting_pnl": round(pnl, 2),
            "growth_pct": round(pnl / td, 6) if td > 0 else None,
            "baseline_reset_at": reset_at,
        }

    td_total = sum(v["total_deposited"] for v in per_book.values())
    tw_total = sum(v["total_withdrawn"] for v in per_book.values())
    nd_total = td_total - tw_total
    bal_total = sum(v["current_balance"] for v in per_book.values())
    pnl_total = bal_total - nd_total
    overall = {
        "total_deposited": round(td_total, 2),
        "total_withdrawn": round(tw_total, 2),
        "net_deposits": round(nd_total, 2),
        "current_balance": round(bal_total, 2),
        "betting_pnl": round(pnl_total, 2),
        "growth_pct": round(pnl_total / td_total, 6) if td_total > 0 else None,
    }
    return {"overall": overall, "per_book": per_book}


def get_bankroll(user_id: str) -> dict:
    """Return bankroll state; auto-migrates legacy initial_deposit on first call."""
    resp = _users_table().get_item(Key={"user_id": user_id})
    item = resp.get("Item", {})

    accounts_raw = dict(item.get("book_accounts") or {})
    events_raw = list(item.get("bankroll_events") or [])

    # One-time auto-migration: initial_deposit → seed deposit on "Unspecified"
    legacy = item.get("initial_deposit")
    if legacy is not None and not events_raw:
        amount = float(legacy)
        if amount > 0:
            seed = {
                "event_id": str(uuid4()),
                "book": "Unspecified",
                "type": "deposit",
                "amount": amount,
                "date": "2026-01-01",
            }
            accounts_raw.setdefault("Unspecified", {"current_balance": amount})
            events_raw = [seed]
            _users_table().update_item(
                Key={"user_id": user_id},
                UpdateExpression="SET #ba = :ba, #be = :be",
                ExpressionAttributeNames={"#ba": "book_accounts", "#be": "bankroll_events"},
                ExpressionAttributeValues={":ba": _to_ddb(accounts_raw), ":be": _to_ddb(events_raw)},
            )

    accounts = _deep_from_dynamo(accounts_raw)
    events = _deep_from_dynamo(events_raw)
    growth = compute_bankroll_growth(accounts, events)

    books_list = [
        {"book": b, "current_balance": float((info or {}).get("current_balance", 0))}
        for b, info in accounts.items()
    ]

    return {
        "book_accounts": books_list,
        "bankroll_events": sorted(events, key=lambda e: e.get("date", ""), reverse=True),
        "overall_growth": growth["overall"],
        "per_book_growth": growth["per_book"],
    }


def upsert_book_balance(user_id: str, book: str, current_balance: float) -> dict:
    """Create or update a sportsbook's current balance."""
    resp = _users_table().get_item(Key={"user_id": user_id})
    item = resp.get("Item", {})
    accounts = _deep_from_dynamo(dict(item.get("book_accounts") or {}))
    prev = accounts.get(book) or {}
    new_entry = {"current_balance": current_balance}
    # Preserve any baseline reset marker across balance edits.
    if prev.get("baseline"):
        new_entry["baseline"] = prev["baseline"]
    accounts[book] = new_entry
    _users_table().update_item(
        Key={"user_id": user_id},
        UpdateExpression="SET #ba = :ba",
        ExpressionAttributeNames={"#ba": "book_accounts"},
        ExpressionAttributeValues={":ba": _to_ddb(accounts)},
    )
    return get_bankroll(user_id)


def add_bankroll_event(
    user_id: str, book: str, event_type: str, amount: float, date: str
) -> dict:
    """Append a deposit or withdrawal event; auto-creates the book entry if absent."""
    resp = _users_table().get_item(Key={"user_id": user_id})
    item = resp.get("Item", {})
    events = _deep_from_dynamo(list(item.get("bankroll_events") or []))
    accounts = _deep_from_dynamo(dict(item.get("book_accounts") or {}))

    events.append({
        "event_id": str(uuid4()),
        "book": book,
        "type": event_type,
        "amount": amount,
        "date": date,
    })
    if book not in accounts:
        accounts[book] = {"current_balance": amount if event_type == "deposit" else 0.0}

    _users_table().update_item(
        Key={"user_id": user_id},
        UpdateExpression="SET #ba = :ba, #be = :be",
        ExpressionAttributeNames={"#ba": "book_accounts", "#be": "bankroll_events"},
        ExpressionAttributeValues={":ba": _to_ddb(accounts), ":be": _to_ddb(events)},
    )
    return get_bankroll(user_id)


def remove_book(user_id: str, book: str) -> dict:
    """Remove a book account (events are preserved for history)."""
    resp = _users_table().get_item(Key={"user_id": user_id})
    item = resp.get("Item", {})
    accounts = _deep_from_dynamo(dict(item.get("book_accounts") or {}))
    accounts.pop(book, None)
    _users_table().update_item(
        Key={"user_id": user_id},
        UpdateExpression="SET #ba = :ba",
        ExpressionAttributeNames={"#ba": "book_accounts"},
        ExpressionAttributeValues={":ba": _to_ddb(accounts)},
    )
    return get_bankroll(user_id)


def reassign_book(user_id: str, from_book: str, to_book: str) -> dict:
    """Rename from_book → to_book in accounts and all events (read-modify-write)."""
    resp = _users_table().get_item(Key={"user_id": user_id})
    item = resp.get("Item", {})
    accounts = _deep_from_dynamo(dict(item.get("book_accounts") or {}))
    events = _deep_from_dynamo(list(item.get("bankroll_events") or []))

    if from_book not in accounts:
        raise ValueError(f"Book '{from_book}' not found")
    if to_book in accounts:
        raise ValueError(f"Book '{to_book}' already exists — remove it first or choose a different name")

    accounts[to_book] = accounts.pop(from_book)
    for evt in events:
        if evt.get("book") == from_book:
            evt["book"] = to_book

    _users_table().update_item(
        Key={"user_id": user_id},
        UpdateExpression="SET #ba = :ba, #be = :be",
        ExpressionAttributeNames={"#ba": "book_accounts", "#be": "bankroll_events"},
        ExpressionAttributeValues={":ba": _to_ddb(accounts), ":be": _to_ddb(events)},
    )
    return get_bankroll(user_id)


def delete_bankroll_event(user_id: str, event_id: str) -> dict:
    """Remove a single event by event_id (read-modify-write)."""
    resp = _users_table().get_item(Key={"user_id": user_id})
    item = resp.get("Item", {})
    events = _deep_from_dynamo(list(item.get("bankroll_events") or []))
    original_len = len(events)
    events = [e for e in events if e.get("event_id") != event_id]
    if len(events) == original_len:
        raise ValueError(f"Event '{event_id}' not found")
    _users_table().update_item(
        Key={"user_id": user_id},
        UpdateExpression="SET #be = :be",
        ExpressionAttributeNames={"#be": "bankroll_events"},
        ExpressionAttributeValues={":be": _to_ddb(events)},
    )
    return get_bankroll(user_id)


def reset_book_baseline(user_id: str, book: str) -> dict:
    """Reset a single book's cost basis to its current balance (fresh start).

    Opt-in, idempotent, and non-destructive: the book's deposit/withdrawal
    events are preserved. We only snapshot a ``baseline`` marker on the account
    that re-bases compute_bankroll_growth so growth_pct restarts at 0% from the
    current balance. Calling it again recomputes the same offsets from the
    (unchanged) events, so a repeat reset is a no-op on an unchanged book.
    """
    resp = _users_table().get_item(Key={"user_id": user_id})
    item = resp.get("Item", {})
    accounts = _deep_from_dynamo(dict(item.get("book_accounts") or {}))
    events = _deep_from_dynamo(list(item.get("bankroll_events") or []))

    if book not in accounts:
        raise ValueError(f"Book '{book}' not found")

    dep = sum(
        float(e.get("amount", 0))
        for e in events
        if e.get("book") == book and e.get("type") == "deposit"
    )
    wd = sum(
        float(e.get("amount", 0))
        for e in events
        if e.get("book") == book and e.get("type") == "withdrawal"
    )
    bal = float((accounts[book] or {}).get("current_balance", 0))

    accounts[book] = {
        "current_balance": bal,
        "baseline": {
            "basis": bal,
            "deposited_offset": dep,
            "withdrawn_offset": wd,
            "reset_at": datetime.now(timezone.utc).isoformat(),
        },
    }
    _users_table().update_item(
        Key={"user_id": user_id},
        UpdateExpression="SET #ba = :ba",
        ExpressionAttributeNames={"#ba": "book_accounts"},
        ExpressionAttributeValues={":ba": _to_ddb(accounts)},
    )
    return get_bankroll(user_id)


# ── Portfolio preferences (INC-16-P2: migrated off the Railway PG) ─────────────
# Per-user portfolio settings used by GET /portfolio/preferences and the
# /picks/today?apply_portfolio=true server-side filter. Stored as a nested
# `portfolio` map on the user item (PK user_id) so it rides the existing users
# table — no new table, no PG dependency. Replaces pg.get_user_portfolio /
# pg.upsert_user_portfolio (the serving Postgres is decommissioned in P2).

_DEFAULT_PORTFOLIO = {
    "min_ev_threshold": 0.02,
    "markets": ["h2h", "totals"],
    "bankroll": None,
    "max_kelly_fraction": 0.05,
}


def get_user_portfolio(user_id: str) -> dict:
    """Return the user's portfolio preferences, or defaults if not yet saved.

    Non-raising — returns defaults on any DynamoDB error so the picks/portfolio
    routers keep serving (matches the old pg.get_user_portfolio contract).
    """
    try:
        resp = _users_table().get_item(Key={"user_id": user_id})
        pf = resp.get("Item", {}).get("portfolio")
        if pf:
            # Merge over defaults so a field dropped at write time (e.g. a None
            # bankroll — _to_dynamo strips None) still resolves to its default.
            return {"user_id": user_id, **_DEFAULT_PORTFOLIO, **_from_dynamo(pf)}
    except Exception:
        logger.warning("dynamo.get_user_portfolio failed for user=%s", user_id)
    return {"user_id": user_id, **_DEFAULT_PORTFOLIO}


def upsert_user_portfolio(user_id: str, prefs: dict) -> dict:
    """Save portfolio preferences as the `portfolio` map on the user item.

    Returns the saved prefs (with user_id). Non-raising: on error returns the
    requested prefs so the caller still gets a coherent response.
    """
    pf = {
        "min_ev_threshold": prefs.get("min_ev_threshold", _DEFAULT_PORTFOLIO["min_ev_threshold"]),
        "markets": prefs.get("markets", _DEFAULT_PORTFOLIO["markets"]),
        "bankroll": prefs.get("bankroll"),
        "max_kelly_fraction": prefs.get("max_kelly_fraction", _DEFAULT_PORTFOLIO["max_kelly_fraction"]),
    }
    try:
        _users_table().update_item(
            Key={"user_id": user_id},
            UpdateExpression="SET #pf = :pf",
            ExpressionAttributeNames={"#pf": "portfolio"},
            ExpressionAttributeValues={":pf": _to_dynamo(pf)},
        )
    except Exception:
        logger.warning("dynamo.upsert_user_portfolio failed for user=%s", user_id)
    return {"user_id": user_id, **pf}


# ── Fantasy league settings (NF-C0b) ─────────────────────────────────────────
# Per-user hand-entered (or imported) league configs, stored as a `fantasy_leagues`
# map {league_id: config} on the user item (PK user_id) — the same "ride the existing
# users table" pattern as portfolio preferences above.
#
# ⭐ WHY NO NEW TABLE. A league config is a couple of KB and a user keeps a handful,
# so the whole map sits far inside the 400 KB item limit; a dedicated table would buy
# nothing and would cost a provisioning step + an IAM grant. This repo's own landmine
# list records the failure mode there: `aws_resources.md` has documented a table that
# was never actually created. Reusing the users table means this ships with ZERO new
# infrastructure — the existing GetItem/UpdateItem grant already covers it.
MAX_LEAGUES_PER_USER = 25

# ── NF-C6P3: the item budget that "a league config is a couple of KB" no longer covers ───────────
#
# ⚠️ THE PREMISE ABOVE HAS AN EXPIRY DATE AND NF-C6P3 REACHED IT. Storing every team's roster (not
# just the user's own) takes a league from ~2 KB to ~13 KB — measured on the real captured ESPN
# league, 10 teams / 172 players — and a 14-team league to ~18 KB. Twenty-five of those is ~450 KB,
# past the 400 KB item ceiling ON ITS OWN, before the portfolio / platform tokens / scoring ledger /
# MLB leagues that share the row.
#
# ⭐ AND AN OVERFLOW HERE IS NOT A DEGRADED FEATURE — IT IS A DEAD USER ROW. DynamoDB refuses the
# whole `UpdateItem`, so once the item is at the ceiling EVERY subsequent write for that user fails:
# no new league, no bet, no preference. A silent product limit is a bad trade for that, so the
# budget is enforced HERE, at the one place that can see the whole item.
#
# ⭐ WHAT GETS DROPPED, AND WHY IT IS THE INCOMING LEAGUE'S ROSTERS. The alternative — evicting
# rosters from OTHER, already-stored leagues to make room — mutates data the caller did not ask us
# to touch, on a write they experience as saving one league. First-come-first-served instead: the
# league being written loses its `league_rosters` and keeps everything else, which degrades that
# league EXACTLY to the pre-NF-C6P3 product (your own roster, the pool-size waiver definition) and
# says so through `league_rosters_truncated`. Never a raise: a save must not fail over an
# enhancement.
#
# Sized from the ceiling, not guessed: 400 KB total, of which the fantasy map may claim 260 KB. The
# remaining ~140 KB is for every other attribute on the row plus DynamoDB's own per-key overhead,
# which the JSON estimate below does not model and which is why the reserve is generous.
DYNAMO_ITEM_LIMIT_BYTES = 400 * 1024
MAX_FANTASY_LEAGUES_BYTES = 260 * 1024


def _estimated_bytes(value) -> int:
    """A conservative stand-in for DynamoDB's item-size accounting.

    ⚠️ NOT EXACT, AND IT DOES NOT NEED TO BE. DynamoDB counts attribute NAMES plus values plus a
    per-element overhead this cannot see, so the real size is somewhat LARGER than the JSON length.
    That is the safe direction for a budget check — we under-estimate what we are storing and
    therefore refuse slightly earlier than strictly necessary — and it is why the reserve above is
    140 KB rather than a few. An exact serializer would be a second implementation of DynamoDB's
    accounting rules with no way to test it against the real thing.
    """
    try:
        return len(json.dumps(value, default=str).encode("utf-8"))
    except Exception:  # noqa: BLE001
        # An unserializable value is not a reason to fail a save; treat it as large so the budget
        # errs toward dropping the enhancement rather than toward overflowing the item.
        return MAX_FANTASY_LEAGUES_BYTES


def _fits_fantasy_budget(user_id: str, league_id: str, record: dict) -> bool:
    """Would storing `record` keep the whole `fantasy_leagues` map inside its budget?

    Reads the caller's OTHER leagues (the same read `put_fantasy_league` already does) and adds this
    record to them. A read failure answers True: `list_fantasy_leagues` is non-raising and returns
    `[]` on failure, so a transient read problem would otherwise look like an empty account and
    permit the write anyway — being explicit about it here is cheaper than a subtle one.
    """
    others = sum(
        _estimated_bytes(league)
        for league in list_fantasy_leagues(user_id)
        if str(league.get("league_id") or "") != league_id
    )
    return others + _estimated_bytes(record) <= MAX_FANTASY_LEAGUES_BYTES


def list_fantasy_leagues(user_id: str) -> list[dict]:
    """Every league the user has saved, newest-updated first.

    Non-raising: a read failure returns [] so the fantasy surfaces still render (a user
    with no leagues and a user whose read failed both just see the preset path).

    ⚠️ Each stored league is converted INDEPENDENTLY and a malformed one is SKIPPED, never
    raised (E9.49): one un-representable row must never blank the whole collection.
    """
    try:
        resp = _users_table().get_item(Key={"user_id": user_id})
        raw = resp.get("Item", {}).get("fantasy_leagues") or {}
    except Exception:
        logger.warning("dynamo.list_fantasy_leagues failed for user=%s", user_id)
        return []

    out: list[dict] = []
    for league_id, cfg in raw.items():
        try:
            item = _deep_from_dynamo(cfg)
            if not isinstance(item, dict):
                continue
            item["league_id"] = league_id
            out.append(item)
        except Exception:
            logger.warning(
                "dynamo.list_fantasy_leagues: skipping malformed league %s for user=%s",
                league_id, user_id,
            )
    out.sort(key=lambda c: str(c.get("updated_at") or ""), reverse=True)
    return out


def get_fantasy_league(user_id: str, league_id: str) -> dict | None:
    for league in list_fantasy_leagues(user_id):
        if league.get("league_id") == league_id:
            return league
    return None


def put_fantasy_league(
    user_id: str, league_id: str | None, config: dict, max_leagues: int | None = None
) -> dict:
    """Create or overwrite one league. Returns the stored record.

    Writes a SINGLE map entry (`SET #fl.#id = :cfg`) rather than the whole map, so two
    browser tabs saving different leagues cannot clobber each other. That needs the parent
    map to exist, so a missing `fantasy_leagues` is created first with an
    attribute_not_exists guard.

    ⭐ G100-C1 — `max_leagues` is THE CALLER'S QUOTA, not this module's storage ceiling.
    `MAX_LEAGUES_PER_USER` is what the ITEM can hold; how many a given caller may keep is an
    ENTITLEMENT question (`entitlement.personalized_league_quota`) and is now passed in. It is
    optional and defaults to the storage ceiling purely so existing callers keep their exact
    behaviour (NF-C0 additivity) — the router always passes the real value.

    ⚠️ THE CAP IS CHECKED ON CREATE ONLY, and that is deliberate rather than an oversight: a caller
    who is AT their quota must still be able to EDIT the league they have. Making an update fail at
    the cap would leave a free user's one league permanently frozen at whatever they first typed —
    the failure would present as "saving is broken", which is exactly the shape E8.6 was about.
    """
    is_new = not league_id
    league_id = league_id or str(uuid4())
    now = _now_iso()

    cap = MAX_LEAGUES_PER_USER if max_leagues is None else int(max_leagues)
    # Clamped to the storage ceiling so an entitlement bug can never authorise an item-size overflow:
    # the quota may only ever be MORE restrictive than what this table can physically hold.
    cap = min(cap, MAX_LEAGUES_PER_USER)

    existing = get_fantasy_league(user_id, league_id) if not is_new else None
    if is_new and len(list_fantasy_leagues(user_id)) >= cap:
        raise ValueError("too_many_leagues")

    record = dict(config)
    record.pop("league_id", None)
    record["created_at"] = (existing or {}).get("created_at") or now
    record["updated_at"] = now

    # NF-C6P3 — the shared-item budget (see MAX_FANTASY_LEAGUES_BYTES). Only the all-team rosters
    # are ever dropped, and only from the league being written; everything else is stored verbatim.
    if record.get("league_rosters") and not _fits_fantasy_budget(user_id, league_id, record):
        record["league_rosters"] = None
        record["league_rosters_truncated"] = True
        logger.warning(
            "[METRIC] fantasy_league_rosters_dropped_for_size=1 user=%s league=%s — the user item "
            "is near its 400 KB ceiling; this league keeps its own roster only",
            user_id, league_id,
        )

    table = _users_table()
    try:
        table.update_item(
            Key={"user_id": user_id},
            UpdateExpression="SET #fl = :empty",
            ExpressionAttributeNames={"#fl": "fantasy_leagues"},
            ExpressionAttributeValues={":empty": {}},
            ConditionExpression="attribute_not_exists(#fl)",
        )
    except Exception:
        pass  # already present — the normal path

    table.update_item(
        Key={"user_id": user_id},
        UpdateExpression="SET #fl.#id = :cfg",
        ExpressionAttributeNames={"#fl": "fantasy_leagues", "#id": league_id},
        ExpressionAttributeValues={":cfg": _to_ddb(record)},
    )
    return {**record, "league_id": league_id}


def delete_fantasy_league(user_id: str, league_id: str) -> None:
    """Remove one league. Raises ValueError('not_found') when the user does not own it."""
    if get_fantasy_league(user_id, league_id) is None:
        raise ValueError("not_found")
    _users_table().update_item(
        Key={"user_id": user_id},
        UpdateExpression="REMOVE #fl.#id",
        ExpressionAttributeNames={"#fl": "fantasy_leagues", "#id": league_id},
    )


# ── NF-LEAK1: the scoring-change ledger ──────────────────────────────────────
# The per-ACCOUNT token bucket that prices paid-stat reconstruction through the
# league scorer. Same "ride the users table" pattern as the league configs above.
#
# ⭐ WHY IT LIVES ON THE USER ITEM AND NOT ON THE LEAGUE. A free account may hold
# only one league, but it may DELETE and RE-CREATE that league without limit — a
# per-league counter would hand back a full bucket on every recreate, which is the
# whole bypass this ledger exists to close. Keyed on `user_id`, delete+create is
# just another charged change.
#
# ⚠️ AND WHY IT IS DURABLE RATHER THAN THE EXISTING IN-MEMORY LIMITER.
# `cost_guardrails.RateLimiter` is per-Lambda-CONTAINER by its own docstring, so it
# cannot count 38 changes spread across days, and it is keyed on an address the
# attacker can change rather than on the identity they had to create.
_SCORING_LEDGER_ATTR = "fantasy_scoring_ledger"


def get_fantasy_scoring_ledger(user_id: str) -> dict | None:
    """The user's scoring-change ledger, or None when there is none (or the read failed).

    Non-raising, and `scoring_probe_guard._coerce` turns None into a FULL bucket. That
    direction is deliberate: the failure being guarded against is our own storage, and
    failing closed would present to a real user as their league becoming permanently
    unsavable — much worse than one attacker getting one extra bucket.
    """
    try:
        resp = _users_table().get_item(Key={"user_id": user_id})
        raw = resp.get("Item", {}).get(_SCORING_LEDGER_ATTR)
        record = _deep_from_dynamo(raw)
    except Exception:
        logger.warning("dynamo.get_fantasy_scoring_ledger failed for user=%s", user_id)
        return None
    return record if isinstance(record, dict) else None


def put_fantasy_scoring_ledger(user_id: str, ledger: dict) -> bool:
    """Persist the ledger. Returns whether it landed.

    ⚠️ RETURNS A VERDICT RATHER THAN RAISING, and the caller LOGS a failure loudly instead
    of refusing the save. A dropped ledger write means one change went uncounted; refusing
    the save instead would turn a DynamoDB blip into "saving is broken" for a real user
    (E8.6's silent-save class, pointed the other way). The bool exists so the miss is
    reported rather than silently scored healthy (NF1.7 (a)).
    """
    try:
        _users_table().update_item(
            Key={"user_id": user_id},
            UpdateExpression="SET #sl = :led",
            ExpressionAttributeNames={"#sl": _SCORING_LEDGER_ATTR},
            ExpressionAttributeValues={":led": _to_ddb(ledger)},
        )
        return True
    except Exception:
        logger.warning("dynamo.put_fantasy_scoring_ledger failed for user=%s", user_id)
        return False


# ── Fantasy platform OAuth tokens (NF-C0) ────────────────────────────────────
# A user's per-platform OAuth grant, stored as a `platform_tokens` map
# {platform: {refresh_token, access_token, expires_at, connected_at}} on the user
# item — the same "ride the existing users table" pattern as the league configs.
#
# 🚨 WHAT IS AND IS NOT STORED. This holds a REVOCABLE, READ-SCOPED grant the user
# issued on the platform's OWN consent screen. It NEVER holds a password: that is
# the story's hard red line, and it is the reason Yahoo (OAuth) is buildable while
# ESPN (session cookies) is not.
#
# 🔐 The refresh token arrives ALREADY ENCRYPTED (Fernet, key in SSM — see
# `platform_import/yahoo_oauth.py`). This layer deliberately does no crypto of its
# own so there is exactly ONE place that can decrypt, and reading the DynamoDB item
# is not sufficient to use the grant — an attacker needs the SSM/KMS grant too.
_PLATFORM_TOKENS_ATTR = "platform_tokens"


def get_platform_token(user_id: str, platform: str) -> dict | None:
    """The user's stored grant for one platform, or None.

    Non-raising on a read failure (returns None) so a Dynamo blip degrades to
    "you are not connected" — which the UI already handles with a connect button —
    rather than 500-ing a page that also serves the password-free Sleeper path.
    """
    try:
        resp = _users_table().get_item(Key={"user_id": user_id})
        raw = resp.get("Item", {}).get(_PLATFORM_TOKENS_ATTR) or {}
        record = _deep_from_dynamo(raw.get(platform))
    except Exception:
        logger.warning("dynamo.get_platform_token failed for user=%s platform=%s", user_id, platform)
        return None
    return record if isinstance(record, dict) else None


def put_platform_token(user_id: str, platform: str, record: dict) -> None:
    """Store/replace one platform grant. `record["refresh_token"]` must already be ciphertext.

    Writes a SINGLE map entry so two concurrent connects (two tabs, two platforms)
    cannot clobber each other — the same concurrency reasoning as the league writer
    above, which needs the parent map to exist first.
    """
    table = _users_table()
    try:
        table.update_item(
            Key={"user_id": user_id},
            UpdateExpression="SET #pt = :empty",
            ExpressionAttributeNames={"#pt": _PLATFORM_TOKENS_ATTR},
            ExpressionAttributeValues={":empty": {}},
            ConditionExpression="attribute_not_exists(#pt)",
        )
    except Exception:
        pass  # already present — the normal path
    table.update_item(
        Key={"user_id": user_id},
        UpdateExpression="SET #pt.#p = :rec",
        ExpressionAttributeNames={"#pt": _PLATFORM_TOKENS_ATTR, "#p": platform},
        ExpressionAttributeValues={":rec": _to_ddb(dict(record))},
    )


def delete_platform_token(user_id: str, platform: str) -> None:
    """Disconnect a platform. Idempotent — REMOVE on an absent key is a no-op, which is
    the behaviour a 'disconnect' button wants (clicking twice is not an error)."""
    try:
        _users_table().update_item(
            Key={"user_id": user_id},
            UpdateExpression="REMOVE #pt.#p",
            ExpressionAttributeNames={"#pt": _PLATFORM_TOKENS_ATTR, "#p": platform},
        )
    except Exception:
        logger.warning(
            "dynamo.delete_platform_token failed for user=%s platform=%s", user_id, platform
        )


# ── Stripe subscription billing state (E9.8) ─────────────────────────────────
# Reuses the users table with namespaced synthetic PKs so no new infra is needed.
# The rows are invisible to the app's per-user reads (they never key on these PKs)
# and to the owner-scan in finances.py (which filters on `email`, absent here).
#
#   __stripe_event__#<event_id>   idempotency ledger — one row per processed webhook
#   __stripe_meta__#founding      durable atomic counter of paid conversions
#   __stripe_customer__#<cust_id> reverse map Stripe customer → Cognito sub
#
# The user's OWN row also gets `stripe_customer_id` on conversion so
# GET /subscription/status can surface a manage-billing link.

_FOUNDING_COUNTER_PK = "__stripe_meta__#founding"


def stripe_event_already_processed(event_id: str) -> bool:
    """Idempotency gate keyed on the Stripe event id.

    Records the event id with a conditional put. Returns True if this event was
    ALREADY processed (caller should no-op), False if it is newly recorded (caller
    should process). Stripe retries and sends duplicates, so a replayed
    subscription.created must not double-promote or double-count.
    """
    try:
        _users_table().put_item(
            Item={"user_id": f"__stripe_event__#{event_id}", "processed_at": _now_iso()},
            ConditionExpression="attribute_not_exists(user_id)",
        )
        return False
    except _ddb.meta.client.exceptions.ConditionalCheckFailedException:
        return True


def founding_slots_used() -> int:
    """How many paid conversions have been recorded (the durable founding counter)."""
    resp = _users_table().get_item(Key={"user_id": _FOUNDING_COUNTER_PK})
    raw = resp.get("Item", {}).get("slots_used")
    return int(raw) if raw is not None else 0


def increment_founding_slots() -> int:
    """Atomically increment the founding-conversion counter; return the new total.

    Called from the webhook on a genuine (idempotency-gated) new conversion. Not
    decremented on churn — "first 100 to convert" is a permanent grandfather, so a
    freed slot is never reclaimed. The #100 boundary race is accepted (no lock)."""
    resp = _users_table().update_item(
        Key={"user_id": _FOUNDING_COUNTER_PK},
        UpdateExpression="ADD slots_used :one",
        ExpressionAttributeValues={":one": Decimal(1)},
        ReturnValues="UPDATED_NEW",
    )
    return int(resp["Attributes"]["slots_used"])


_PRICE_SNAPSHOT_PK_PREFIX = "__stripe_meta__#price#"


def read_price_snapshot(price_id: str) -> dict | None:
    """The last-known-good Stripe Price snapshot for `price_id`, or None.

    E9.59 — the DURABLE half of the pricing cache. An in-memory cache alone is per
    warm Lambda container, so a cold start during a Stripe outage would have nothing
    to fall back on and the public pricing page would blank. This row is written by
    the last container that DID reach Stripe, so the only state with no fallback is
    "this Price has never once been read since it was configured".

    Values come back as `Decimal`; the caller coerces. Never raises — a fallback read
    that itself fails must not be worse than having no fallback."""
    try:
        item = _users_table().get_item(Key={"user_id": f"{_PRICE_SNAPSHOT_PK_PREFIX}{price_id}"}).get("Item")
    except Exception:  # noqa: BLE001
        logger.exception("Could not read the last-known-good price snapshot (price=%s)", price_id)
        return None
    if not item:
        return None
    return {k: v for k, v in item.items() if k != "user_id"}


def write_price_snapshot(price_id: str, snapshot: dict) -> None:
    """Persist a freshly-read Stripe Price as the last-known-good. Never raises —
    failing to CACHE a price must never fail the request that successfully read it."""
    try:
        _users_table().put_item(
            Item={
                "user_id": f"{_PRICE_SNAPSHOT_PK_PREFIX}{price_id}",
                **{k: (Decimal(str(v)) if isinstance(v, (int, float)) and not isinstance(v, bool) else v)
                   for k, v in snapshot.items()},
                "updated_at": _now_iso(),
            }
        )
    except Exception:  # noqa: BLE001
        logger.exception("Could not persist the price snapshot (price=%s)", price_id)


def link_stripe_customer(user_id: str, customer_id: str) -> None:
    """Record the Stripe customer id on the user's row + a reverse-lookup row.

    The reverse row lets webhook events that carry only a customer id
    (invoice.payment_failed) resolve back to the Cognito sub."""
    _users_table().update_item(
        Key={"user_id": user_id},
        UpdateExpression="SET stripe_customer_id = :c",
        ExpressionAttributeValues={":c": customer_id},
    )
    _users_table().put_item(
        Item={"user_id": f"__stripe_customer__#{customer_id}", "cognito_sub": user_id}
    )


def user_id_for_stripe_customer(customer_id: str) -> str | None:
    """Resolve a Stripe customer id back to a Cognito sub via the reverse-lookup row."""
    resp = _users_table().get_item(Key={"user_id": f"__stripe_customer__#{customer_id}"})
    sub = resp.get("Item", {}).get("cognito_sub")
    return str(sub) if sub else None


def stripe_customer_for_user(user_id: str) -> str | None:
    """The Stripe customer id stored on the user's row, if any."""
    resp = _users_table().get_item(Key={"user_id": user_id})
    cid = resp.get("Item", {}).get("stripe_customer_id")
    return str(cid) if cid else None


# ── MLB dynasty league rosters (E8.2) ────────────────────────────────────────
# A user's fantasy-BASEBALL league: its name, its AL/NL scope, the current roster
# snapshot, the manual name fixes, and the in-draft picks. Stored as an
# `mlb_leagues` map {league_id: league} on the user item — the same "ride the
# existing users table, zero new infrastructure" pattern as the NFL league configs
# above, and for the same reason (this repo has already documented a table that was
# never actually created; a schema that needs no provisioning step cannot repeat it).
#
# 🔒 PRIVACY: WHAT IS AND IS NOT STORED. This is the USER'S league data, so it holds
# the minimum the availability overlay needs — team names, and per rostered player a
# name, slot and status. It NEVER stores the raw uploaded file, and there is no
# credential of any kind to store: E8.2a found no compliant CBS read, so nothing here
# ever talks to a platform. `delete_mlb_league` is a real delete, not a soft flag.
#
# ⚖️ SIZE. The operator's real 12-team export is 442 players ≈ 30 KB stored, well
# inside DynamoDB's 400 KB item limit but not free — hence the low per-user cap and
# the entry cap enforced by the parser.
MAX_MLB_LEAGUES_PER_USER = 5


def list_mlb_leagues(user_id: str) -> list[dict]:
    """Every MLB league the user has saved, newest-updated first.

    Non-raising, and each league is converted INDEPENDENTLY so one malformed record can
    never blank the whole collection (E9.49 — a single un-representable row took down an
    entire list endpoint once already).
    """
    try:
        resp = _users_table().get_item(Key={"user_id": user_id})
        raw = resp.get("Item", {}).get("mlb_leagues") or {}
    except Exception:
        logger.warning("dynamo.list_mlb_leagues failed for user=%s", user_id)
        return []

    out: list[dict] = []
    for league_id, cfg in raw.items():
        try:
            item = _deep_from_dynamo(cfg)
            if not isinstance(item, dict):
                continue
            item["league_id"] = league_id
            out.append(item)
        except Exception:
            logger.warning(
                "dynamo.list_mlb_leagues: skipping malformed league %s for user=%s",
                league_id, user_id,
            )
    out.sort(key=lambda c: str(c.get("updated_at") or ""), reverse=True)
    return out


def get_mlb_league(user_id: str, league_id: str) -> dict | None:
    for league in list_mlb_leagues(user_id):
        if league.get("league_id") == league_id:
            return league
    return None


def put_mlb_league(user_id: str, league_id: str | None, league: dict) -> dict:
    """Create or overwrite one MLB league. Returns the stored record.

    Writes a SINGLE map entry so two tabs (or a draft-pick write racing a roster
    re-upload) cannot clobber each other's league.
    """
    is_new = not league_id
    league_id = league_id or str(uuid4())
    now = _now_iso()

    existing = None if is_new else get_mlb_league(user_id, league_id)
    if is_new and len(list_mlb_leagues(user_id)) >= MAX_MLB_LEAGUES_PER_USER:
        raise ValueError("too_many_leagues")

    record = dict(league)
    record.pop("league_id", None)
    record["created_at"] = (existing or {}).get("created_at") or now
    record["updated_at"] = now

    table = _users_table()
    try:
        table.update_item(
            Key={"user_id": user_id},
            UpdateExpression="SET #ml = :empty",
            ExpressionAttributeNames={"#ml": "mlb_leagues"},
            ExpressionAttributeValues={":empty": {}},
            ConditionExpression="attribute_not_exists(#ml)",
        )
    except Exception:
        pass  # already present — the normal path

    table.update_item(
        Key={"user_id": user_id},
        UpdateExpression="SET #ml.#id = :cfg",
        ExpressionAttributeNames={"#ml": "mlb_leagues", "#id": league_id},
        ExpressionAttributeValues={":cfg": _to_ddb(record)},
    )
    return {**record, "league_id": league_id}


def delete_mlb_league(user_id: str, league_id: str) -> None:
    """Remove one MLB league. Raises ValueError('not_found') when the user does not own it."""
    if get_mlb_league(user_id, league_id) is None:
        raise ValueError("not_found")
    _users_table().update_item(
        Key={"user_id": user_id},
        UpdateExpression="REMOVE #ml.#id",
        ExpressionAttributeNames={"#ml": "mlb_leagues", "#id": league_id},
    )
