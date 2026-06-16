"""Feedback endpoints — data quality reports from users."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from uuid import uuid4

import boto3
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(tags=["feedback"])

_REGION = os.getenv("AWS_REGION", "us-east-1")
_DATA_QUALITY_TABLE = os.getenv("DATA_QUALITY_TABLE", "credence-prod-dynamo-data-quality-reports")

_ddb = boto3.resource("dynamodb", region_name=_REGION)


def _reports_table():
    return _ddb.Table(_DATA_QUALITY_TABLE)


class DataQualityReportRequest(BaseModel):
    page_url: str
    game_pk: int | None = None
    user_email: str
    description: str


@router.get("/admin/data-quality-reports")
def list_data_quality_reports(limit: int = 50) -> list[dict]:
    try:
        response = _reports_table().scan(Limit=limit)
        items = response.get("Items", [])
        items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return items
    except Exception:
        logger.exception("Failed to scan data_quality_reports")
        raise HTTPException(status_code=503, detail="Could not fetch reports")


@router.post("/feedback/data-quality", status_code=201)
def create_data_quality_report(body: DataQualityReportRequest) -> dict:
    report_id = str(uuid4())
    item = {
        "report_id": report_id,
        "page_url": body.page_url,
        "user_email": body.user_email,
        "description": body.description,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if body.game_pk is not None:
        item["game_pk"] = body.game_pk

    try:
        _reports_table().put_item(Item=item)
    except Exception:
        logger.exception("DynamoDB put_item failed for data_quality_reports")
        raise HTTPException(status_code=503, detail="Could not save report")

    # TODO (A0.4.15): send SES email to support@credencesports.com once SES is provisioned
    logger.info("Data quality report %s saved (user=%s)", report_id, body.user_email)
    return {"report_id": report_id}
