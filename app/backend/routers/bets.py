"""Bets endpoints (per-user, DynamoDB-backed).

POST /bets        — log a bet for the authenticated user
GET  /bets        — list the authenticated user's bets (newest first)
POST /users/login — login-sync: upsert the caller into the users registry

user_id is the Cognito sub from the API Gateway JWT (see app.backend.dependencies).
"""

from __future__ import annotations

import logging

from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException

from app.backend.dependencies import get_user_id
from app.backend.models.bets import Bet, BetCreate, BetUpdate, BetsResponse, LoginSyncRequest
from app.backend.services.dynamo import delete_bet, list_bets, put_bet, update_bet, upsert_user
from app.backend.services.lakehouse_read import lakehouse_query

logger = logging.getLogger(__name__)
router = APIRouter(tags=["bets"])


@router.post("/bets", response_model=Bet, status_code=201)
def create_bet(body: BetCreate, user_id: str = Depends(get_user_id)) -> Bet:
    try:
        stored = put_bet(user_id, body.model_dump())
    except ClientError as exc:
        logger.exception("DynamoDB put_bet failed")
        raise HTTPException(status_code=503, detail="Could not save bet") from exc
    return Bet(**stored)


@router.get("/bets", response_model=BetsResponse)
def get_bets(user_id: str = Depends(get_user_id)) -> BetsResponse:
    try:
        bets = list_bets(user_id)
    except ClientError as exc:
        logger.exception("DynamoDB list_bets failed")
        raise HTTPException(status_code=503, detail="Bets unavailable") from exc

    # Auto-void pending bets whose games were postponed or cancelled
    pending = [b for b in bets if b.get("outcome") is None and b.get("game_pk")]
    if pending:
        game_pks = list({b["game_pk"] for b in pending})
        pks_csv = ",".join(str(pk) for pk in game_pks)
        try:
            # E11.1-W7b: zero-Snowflake request path — read stg_statsapi_games directly
            # from the S3 lakehouse via DuckDB. FRESHNESS: stg_statsapi_games (source
            # monthly_schedule) is re-flattened to the same S3 path by the 30-min intraday
            # re-export, and the helper globs the live dir (**/*.parquet), so this read
            # picks up postponements/cancellations promptly with no special-casing.
            rows = lakehouse_query(f"""
                SELECT game_pk
                FROM baseball_data.betting.stg_statsapi_games
                WHERE game_pk IN ({pks_csv})
                  AND abstract_game_state IN ('Postponed', 'Cancelled', 'Suspended')
            """)
            voided_pks = {r["GAME_PK"] for r in rows}
            for bet in pending:
                if bet["game_pk"] in voided_pks:
                    try:
                        update_bet(user_id, bet["bet_id"], {"outcome": "void", "profit_loss": 0.0})
                        bet["outcome"] = "void"
                        bet["profit_loss"] = 0.0
                    except Exception:
                        logger.warning("Could not auto-void bet %s", bet["bet_id"])
        except Exception:
            logger.warning("Could not check game statuses for auto-void", exc_info=True)

    return BetsResponse(bets=[Bet(**b) for b in bets], total=len(bets))


@router.delete("/bets/{bet_id}", status_code=204)
def delete_bet_endpoint(bet_id: str, user_id: str = Depends(get_user_id)) -> None:
    try:
        delete_bet(user_id, bet_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Bet not found")
    except ClientError as exc:
        logger.exception("DynamoDB delete_bet failed")
        raise HTTPException(status_code=503, detail="Could not delete bet") from exc


@router.put("/bets/{bet_id}", response_model=Bet)
def update_bet_endpoint(bet_id: str, body: BetUpdate, user_id: str = Depends(get_user_id)) -> Bet:
    try:
        updated = update_bet(user_id, bet_id, body.model_dump())
    except ValueError:
        raise HTTPException(status_code=404, detail="Bet not found")
    except ClientError as exc:
        logger.exception("DynamoDB update_bet failed")
        raise HTTPException(status_code=503, detail="Could not update bet") from exc
    return Bet(**updated)


@router.post("/users/login")
def login_sync(body: LoginSyncRequest, user_id: str = Depends(get_user_id)) -> dict:
    """Called once by the frontend post-login. sub is trusted (JWT); email is
    metadata supplied by the client (access-token claims don't carry email)."""
    try:
        upsert_user(user_id, body.email)
    except ClientError as exc:
        logger.exception("DynamoDB upsert_user failed")
        raise HTTPException(status_code=503, detail="Could not sync user") from exc
    return {"user_id": user_id, "status": "ok"}
