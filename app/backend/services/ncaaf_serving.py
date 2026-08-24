"""ncaaf_serving.py — NCAAF-P3.1: the READ half of the NCAAF serving store.

Read order is **DynamoDB → S3**, the same order and the same two stores the MLB serving path uses,
under the `ncaaf/` key namespace `scripts/write_ncaaf_serving_store.py` writes. Snowflake is not in
this path at all and never will be — the whole NCAAF vertical is lake-and-serving-store only.

⭐ IT REUSES `serving_cache` FOR THE DYNAMODB HALF rather than re-implementing a GetItem. That
module already owns the pk/sk derivation, the JSON decode and — importantly — the *degradation*
contract (every failure returns None so the caller falls through to S3, rather than 500-ing a
public page). A second implementation of that would be a second rule set free to drift (E9.61).

The S3 half IS its own function, and that is not an oversight: `s3_cache` hardcodes the MLB lane's
`api-cache/{today}/…` prefix, and the whole point of this story's key scheme is that NCAAF blobs do
NOT live there. The prefix is the isolation.

⚖️ A MISS RETURNS None, AND THE ROUTER TURNS THAT INTO A 404 — never an empty-but-successful body.
"We have no projection for this game" and "we have one and some field is null" are different facts
and must not render identically (the NF-C6b lesson). Absent ⇒ 404; present-but-unknown ⇒ a declared
field carrying `null` plus, where the cause matters, a `status`/`reason` beside it.

⚠️ AN EMPTY RESULT IS NEVER CACHED OR TREATED AS AUTHORITATIVE. `lakehouse_query` returning `[]`
from a swallowed exception is the repo's recorded silent-empty class (E9.26b); here the equivalent
is a DynamoDB error decoding to None, which is precisely why the S3 fallback runs on None rather
than only on a genuine miss.
"""

from __future__ import annotations

import json
import logging
import os

from app.backend.models import ncaaf as contract
from app.backend.services import serving_cache
from betting_ml.utils.game_day import current_game_date_iso  # INC-22 — LA, never UTC

logger = logging.getLogger(__name__)

#: The same bucket the MLB serving fallback uses; a disjoint prefix inside it (see the module
#: docstring). Read at call time, not import time, so a test can set it.
_BUCKET_ENV = "CACHE_BUCKET"


def _s3_get(key: str) -> dict | None:
    bucket = os.getenv(_BUCKET_ENV)
    if not bucket:
        return None
    try:
        import boto3
        # us-east-1 pinned PER RESOURCE — never inherited from a global AWS_DEFAULT_REGION
        # (a wrong region on an S3 client is a 301 that reads as an empty result, INC-45).
        client = boto3.client("s3", region_name="us-east-1")
        body = client.get_object(Bucket=bucket, Key=key)["Body"].read()
        return json.loads(body.decode("utf-8"))
    except Exception:  # noqa: BLE001 — a miss and an error both mean "not servable from S3"
        logger.debug("ncaaf_serving: S3 miss/err for %s", key)
        return None


def read_blob(cache_key: str, s3_key: str) -> dict | None:
    """One serving blob: DynamoDB first, S3 fallback, None if neither has it.

    The DynamoDB read goes through `serving_cache.get_cache`, which checks the PERMANENT row first
    — and every NCAAF blob is written permanent, because each key already carries its own identity
    (a game id, or an LA game-day). That is deliberate: it means a reader never has to GUESS which
    date a key was written under, which removes an entire class of INC-22-shaped read bug from the
    Lambda. The date passed here only satisfies the shared signature.
    """
    blob = serving_cache.get_cache(cache_key, current_game_date_iso())
    if blob is not None:
        return blob
    return _s3_get(s3_key)


def read_manifest() -> dict | None:
    return read_blob(contract.MANIFEST_CACHE_KEY, contract.MANIFEST_S3_KEY)


def read_slate(game_day: str) -> dict | None:
    return read_blob(contract.slate_cache_key(game_day), contract.slate_s3_key(game_day))


def read_game(game_id: int) -> dict | None:
    return read_blob(contract.game_cache_key(game_id), contract.game_s3_key(game_id))


def read_futures() -> dict | None:
    return read_blob(contract.FUTURES_CACHE_KEY, contract.FUTURES_S3_KEY)
