"""Auth endpoints.

POST /auth/refresh — exchange a Cognito refresh token for a new access token.
"""

from __future__ import annotations

import logging
import os

import boto3
from botocore.exceptions import ClientError
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

_COGNITO_CLIENT_ID = os.environ.get("COGNITO_APP_CLIENT_ID", "1qh95e78bd7g6ipqcvdcpf7ou6")
_AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")


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
