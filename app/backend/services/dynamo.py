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
    """Update mutable fields of a bet. Returns the updated item. Raises ValueError if not found."""
    table = _bets_table()
    resp = table.get_item(Key={"user_id": user_id, "bet_id": bet_id})
    if "Item" not in resp:
        raise ValueError("not_found")

    patch = _to_dynamo({k: v for k, v in updates.items() if v is not None and k not in _IMMUTABLE_KEYS})
    if not patch:
        return _from_dynamo(resp["Item"])

    keys = list(patch.keys())
    vals = list(patch.values())
    names = {f"#k{i}": k for i, k in enumerate(keys)}
    values = {f":v{i}": v for i, v in enumerate(vals)}
    set_parts = [f"#k{i} = :v{i}" for i in range(len(keys))]

    result = table.update_item(
        Key={"user_id": user_id, "bet_id": bet_id},
        UpdateExpression="SET " + ", ".join(set_parts),
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
        ReturnValues="ALL_NEW",
    )
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


def record_tos_acceptance(user_id: str, tos_version: str) -> None:
    """Record first-time ToS acceptance. Preserves the original tos_accepted_at if
    already set (if_not_exists) so re-runs don't overwrite the canonical timestamp.
    tos_version is always updated so we track the latest version agreed to."""
    now = _now_iso()
    _users_table().update_item(
        Key={"user_id": user_id},
        UpdateExpression="SET #ta = if_not_exists(#ta, :now), #tv = :ver",
        ExpressionAttributeNames={"#ta": "tos_accepted_at", "#tv": "tos_version"},
        ExpressionAttributeValues={":now": now, ":ver": tos_version},
    )


def get_user_profile(user_id: str) -> dict:
    """Return the user's mutable profile fields (initial_deposit etc.)."""
    resp = _users_table().get_item(Key={"user_id": user_id})
    item = resp.get("Item", {})
    raw_deposit = item.get("initial_deposit")
    return {
        "initial_deposit": float(raw_deposit) if raw_deposit is not None else None,
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
        bal = float((book_accounts.get(book) or {}).get("current_balance", 0))
        td, tw = f["total_deposited"], f["total_withdrawn"]
        nd = td - tw
        pnl = bal - nd
        per_book[book] = {
            "total_deposited": round(td, 2),
            "total_withdrawn": round(tw, 2),
            "net_deposits": round(nd, 2),
            "current_balance": round(bal, 2),
            "betting_pnl": round(pnl, 2),
            "growth_pct": round(pnl / td, 6) if td > 0 else None,
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
    accounts[book] = {"current_balance": current_balance}
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
