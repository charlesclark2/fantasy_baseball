"""Users profile endpoints.

GET /users/profile — read mutable profile fields (initial_deposit) from DynamoDB
PUT /users/profile — update mutable profile fields

user_id is extracted from the Cognito JWT sub claim passed by API Gateway.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.backend.dependencies import get_user_id
from app.backend.services.dynamo import get_user_profile, update_user_profile

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/users", tags=["users"])


class UserProfile(BaseModel):
    initial_deposit: float | None = Field(None, description="Starting bankroll in USD for growth-% calculation")


class UserProfileUpdate(BaseModel):
    initial_deposit: float | None = Field(None, ge=0)


@router.get("/profile", response_model=UserProfile)
def get_profile(user_id: str = Depends(get_user_id)) -> UserProfile:
    try:
        data = get_user_profile(user_id)
    except Exception as exc:
        logger.exception("get_user_profile failed for %s", user_id)
        raise HTTPException(status_code=503, detail="Profile unavailable") from exc
    return UserProfile(**data)


@router.put("/profile", response_model=UserProfile)
def update_profile(
    body: UserProfileUpdate, user_id: str = Depends(get_user_id)
) -> UserProfile:
    try:
        data = update_user_profile(user_id, body.initial_deposit)
    except Exception as exc:
        logger.exception("update_user_profile failed for %s", user_id)
        raise HTTPException(status_code=503, detail="Could not save profile") from exc
    return UserProfile(**data)
