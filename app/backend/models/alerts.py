from __future__ import annotations

import re

from pydantic import BaseModel, field_validator


class AlertPreferences(BaseModel):
    user_id: str
    email_enabled: bool = True
    sms_enabled: bool = False
    phone_number: str | None = None
    push_enabled: bool = False
    alert_threshold_edge: float = 0.05

    @field_validator("phone_number")
    @classmethod
    def validate_e164(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not re.fullmatch(r"\+1\d{10}", v):
            raise ValueError("phone_number must be E.164 format: +1XXXXXXXXXX")
        return v


class AlertPreferencesUpdate(BaseModel):
    email_enabled: bool | None = None
    sms_enabled: bool | None = None
    phone_number: str | None = None
    push_enabled: bool | None = None
    alert_threshold_edge: float | None = None

    @field_validator("phone_number")
    @classmethod
    def validate_e164(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not re.fullmatch(r"\+1\d{10}", v):
            raise ValueError("phone_number must be E.164 format: +1XXXXXXXXXX")
        return v
