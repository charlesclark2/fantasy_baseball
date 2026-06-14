"""Auth endpoints.

POST /auth/refresh — exchange a Cognito refresh token for a new access token.
"""

from __future__ import annotations

import logging
import os

import boto3
from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.backend.dependencies import get_user_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

_COGNITO_CLIENT_ID  = os.environ.get("COGNITO_APP_CLIENT_ID",  "1qh95e78bd7g6ipqcvdcpf7ou6")
_COGNITO_USER_POOL  = os.environ.get("COGNITO_USER_POOL_ID",   "us-east-1_gG9zMbwQt")
_AWS_REGION         = os.environ.get("AWS_REGION",              "us-east-1")


class RefreshRequest(BaseModel):
    refresh_token: str


class RefreshResponse(BaseModel):
    access_token: str
    id_token: str
    expires_in: int
    token_type: str


@router.post("/refresh", response_model=RefreshResponse)
def refresh_token(body: RefreshRequest) -> RefreshResponse:
    client = boto3.client("cognito-idp", region_name=_AWS_REGION)
    try:
        resp = client.initiate_auth(
            AuthFlow="REFRESH_TOKEN_AUTH",
            AuthParameters={"REFRESH_TOKEN": body.refresh_token},
            ClientId=_COGNITO_CLIENT_ID,
        )
    except client.exceptions.NotAuthorizedException as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token") from exc
    except ClientError as exc:
        logger.exception("Cognito initiate_auth failed")
        raise HTTPException(status_code=503, detail="Auth service unavailable") from exc

    result = resp.get("AuthenticationResult", {})
    return RefreshResponse(
        access_token=result["AccessToken"],
        id_token=result["IdToken"],
        expires_in=result.get("ExpiresIn", 3600),
        token_type=result.get("TokenType", "Bearer"),
    )


@router.post("/verify-email", status_code=204)
def verify_email(user_id: str = Depends(get_user_id)) -> None:
    """Mark the caller's Cognito email as verified.

    Admin-created accounts have email_verified=false by default, which blocks
    the forgotPassword() flow. The frontend calls this fire-and-forget on every
    successful login; it's a no-op once the attribute is already true.

    Requires cognito-idp:AdminUpdateUserAttributes on the Lambda execution role.
    """
    client = boto3.client("cognito-idp", region_name=_AWS_REGION)
    try:
        client.admin_update_user_attributes(
            UserPoolId=_COGNITO_USER_POOL,
            Username=user_id,
            UserAttributes=[{"Name": "email_verified", "Value": "true"}],
        )
    except ClientError:
        # Best-effort — don't fail the login flow if this call errors
        logger.warning("verify_email: admin_update_user_attributes failed for %s", user_id)
