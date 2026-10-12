"""Request and response schemas for the HTTP API."""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator


def _millisecond_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    utc_value = value.astimezone(UTC)
    iso_timestamp = utc_value.isoformat(timespec="milliseconds")
    return iso_timestamp.replace("+00:00", "Z")


class TenantCreate(BaseModel):
    slug: str
    name: str = Field(min_length=1)

    @field_validator("slug")
    @classmethod
    def valid_slug(cls, value: str) -> str:
        import re

        if not re.fullmatch(r"[a-z][-a-z0-9]{1,26}[a-z0-9]", value):
            raise ValueError("slug must be 3-28 lowercase DNS-compatible characters")
        return value

    @field_validator("name")
    @classmethod
    def non_blank_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("name must not be blank")
        return value.strip()


class TenantPatch(BaseModel):
    version: int = Field(ge=1, description="Version returned by the latest tenant read")
    name: str | None = Field(default=None, min_length=1)

    @field_validator("name")
    @classmethod
    def non_blank_name(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("name must not be blank")
        return value.strip() if value is not None else None


class TenantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    slug: str
    name: str
    status: str
    version: int
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at")
    def serialize_timestamps(self, value: datetime) -> str:
        return _millisecond_timestamp(value)


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    type: Literal["deploy", "update", "destroy"]
    tenant_id: str
    status: str
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at")
    def serialize_timestamps(self, value: datetime) -> str:
        return _millisecond_timestamp(value)


class Page(BaseModel):
    items: list
    limit: int
    offset: int


class ErrorBody(BaseModel):
    error: dict
