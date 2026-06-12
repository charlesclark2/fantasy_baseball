"""migrate_placed_bets_to_dynamo.py
--------------------
One-time migration (story B1): copy the legacy Snowflake placed_bets rows into
the DynamoDB per-user bets table, attributing every existing row to the owner
account, and seed the owner into the users table.

Source : baseball_data.betting_ml.placed_bets (read-only/legacy after this)
Target : DynamoDB credence-{env}-dynamo-user-bets  +  credence-{env}-dynamo-users

Pending bets (outcome IS NULL) get a `pending_game_pk` attribute so the settle
job (settle_user_bets.py) picks them up via the gsi-pending-by-game index.
Already-settled rows are written with their outcome/profit_loss and no pending
marker. Idempotent: put_item on the same (user_id, bet_id) overwrites cleanly.

Env vars:
    SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_WAREHOUSE
    SNOWFLAKE_PRIVATE_KEY_PATH or SNOWFLAKE_PRIVATE_KEY
    AWS_REGION         (default us-east-1)
    USER_BETS_TABLE    (default credence-prod-dynamo-user-bets)
    USERS_TABLE        (default credence-prod-dynamo-users)
    OWNER_USER_ID      (default the owner Cognito sub below)
    OWNER_EMAIL        (default ctcb57@gmail.com)
"""

from __future__ import annotations

import base64
import logging
import os
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import boto3
import snowflake.connector
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from dotenv import load_dotenv

# Local runs read creds from the repo-root .env (pipeline runs set env directly).
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

_AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
_USER_BETS_TABLE = os.environ.get("USER_BETS_TABLE", "credence-prod-dynamo-user-bets")
_USERS_TABLE = os.environ.get("USERS_TABLE", "credence-prod-dynamo-users")
_OWNER_USER_ID = os.environ.get("OWNER_USER_ID", "14187448-c091-705c-1199-63858b12c986")
_OWNER_EMAIL = os.environ.get("OWNER_EMAIL", "ctcb57@gmail.com")

# Numeric placed_bets columns that map to DynamoDB N attributes.
_INT_COLS = {"game_pk", "american_odds"}
_FLOAT_COLS = {"stake", "total_line", "model_prob", "market_prob", "ev", "kelly_capped", "profit_loss"}
_STR_COLS = {"bet_id", "matchup", "market", "bookmaker", "outcome", "notes"}


def _aws_session() -> boto3.Session:
    """Build a boto3 Session, preferring an explicit AWS_PROFILE over any AWS_*
    keys pulled in from .env.

    botocore ranks env-var credentials above named profiles, so a profile alone
    wouldn't beat the .env keys. When AWS_PROFILE is set we drop the .env-injected
    static keys so the profile's creds (e.g. the power-user in ~/.aws/credentials)
    are used — lets a one-time admin run use elevated creds without editing .env.
    """
    profile = os.environ.get("AWS_PROFILE")
    if profile:
        for k in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
            os.environ.pop(k, None)
        return boto3.Session(profile_name=profile)
    return boto3.Session()


def _load_private_key() -> bytes:
    pk_path = os.environ.get("SNOWFLAKE_PRIVATE_KEY_PATH")
    if pk_path:
        with open(pk_path, "rb") as fh:
            pem_bytes = fh.read()
    else:
        key_val = os.environ.get("SNOWFLAKE_PRIVATE_KEY", "").strip()
        if not key_val:
            raise RuntimeError("Neither SNOWFLAKE_PRIVATE_KEY_PATH nor SNOWFLAKE_PRIVATE_KEY is set")
        if not key_val.startswith("-----"):
            key_val = base64.b64decode(key_val).decode("utf-8")
        pem_bytes = key_val.encode("utf-8")
    p_key = serialization.load_pem_private_key(pem_bytes, password=None, backend=default_backend())
    return p_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def _connect_snowflake() -> snowflake.connector.SnowflakeConnection:
    kwargs = dict(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
        database="baseball_data",
        private_key=_load_private_key(),
    )
    role = os.environ.get("SNOWFLAKE_ROLE")
    if role:
        kwargs["role"] = role
    return snowflake.connector.connect(**kwargs)


def _to_item(row: dict) -> dict:
    """Map a placed_bets row (UPPERCASE keys from Snowflake) to a DynamoDB item."""
    r = {k.lower(): v for k, v in row.items()}
    item: dict = {
        "user_id": _OWNER_USER_ID,
        "user_email": _OWNER_EMAIL,
    }
    for col in _STR_COLS:
        if r.get(col) is not None:
            item[col] = str(r[col])
    for col in _INT_COLS:
        if r.get(col) is not None:
            item[col] = int(r[col])
    for col in _FLOAT_COLS:
        if r.get(col) is not None:
            item[col] = Decimal(str(r[col]))
    for col in ("score_date", "placed_at"):
        v = r.get(col)
        if isinstance(v, (date, datetime)):
            item[col] = v.isoformat()
        elif v is not None:
            item[col] = str(v)

    # Pending bets carry pending_game_pk so the settle job finds them via the GSI.
    if r.get("outcome") is None:
        item["pending_game_pk"] = int(r["game_pk"])
        item.pop("outcome", None)
        item.pop("profit_loss", None)
    return item


def main() -> int:
    try:
        conn = _connect_snowflake()
    except Exception:
        log.exception("Failed to connect to Snowflake")
        return 1
    try:
        cur = conn.cursor(snowflake.connector.DictCursor)
        cur.execute("SELECT * FROM baseball_data.betting_ml.placed_bets")
        rows = cur.fetchall()
    except Exception:
        log.exception("Failed to read placed_bets")
        return 1
    finally:
        conn.close()

    ddb = _aws_session().resource("dynamodb", region_name=_AWS_REGION)
    bets_table = ddb.Table(_USER_BETS_TABLE)
    users_table = ddb.Table(_USERS_TABLE)

    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        users_table.put_item(Item={
            "user_id": _OWNER_USER_ID,
            "email": _OWNER_EMAIL,
            "first_seen_at": now_iso,
            "last_seen_at": now_iso,
        })
    except Exception:
        log.exception("Failed to seed owner into users table")
        return 1

    written = 0
    try:
        with bets_table.batch_writer() as bw:
            for row in rows:
                bw.put_item(Item=_to_item(row))
                written += 1
    except Exception:
        log.exception("Failed during batch write (wrote %s before error)", written)
        return 1

    log.info("Migrated %s placed_bets into %s under user %s", written, _USER_BETS_TABLE, _OWNER_USER_ID)
    return 0


if __name__ == "__main__":
    sys.exit(main())
