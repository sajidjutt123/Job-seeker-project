from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool


class MessageResponse(BaseModel):
    message: str
    ok: bool = True


class CategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    slug: str
    name: str
    icon: str | None = None
    active_job_count: int = 0


class CityResponse(BaseModel):
    name: str
    slug: str
    province: str
    is_major: bool = False
    active_job_count: int = 0


class AlertCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=160)
    keywords: str | None = Field(default=None, max_length=300)
    cities: list[str] = Field(default_factory=list, max_length=10)
    provinces: list[str] = Field(default_factory=list, max_length=8)
    categories: list[str] = Field(default_factory=list, max_length=10)
    employment_types: list[str] = Field(default_factory=list, max_length=8)
    experience_levels: list[str] = Field(default_factory=list, max_length=8)
    remote_only: bool = False
    government_only: bool = False
    internship_only: bool = False
    salary_min: Decimal | None = Field(default=None, ge=0, le=100_000_000)
    frequency: str = Field(default="daily", pattern="^(instant|daily|weekly)$")


class AlertUpdateRequest(AlertCreateRequest):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    is_active: bool | None = None


class AlertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    keywords: str | None = None
    cities: list[str] = Field(default_factory=list)
    provinces: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    employment_types: list[str] = Field(default_factory=list)
    experience_levels: list[str] = Field(default_factory=list)
    remote_only: bool = False
    government_only: bool = False
    internship_only: bool = False
    salary_min: Decimal | None = None
    frequency: str = "daily"
    is_active: bool = True
    match_count: int = 0
    last_matched_at: datetime | None = None
    last_notified_at: datetime | None = None
    created_at: datetime | None = None


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: str
    subject: str
    body: str | None = None
    status: str
    payload: dict[str, Any] = Field(default_factory=dict)
    read_at: datetime | None = None
    created_at: datetime


class HealthComponent(BaseModel):
    status: str
    detail: str | None = None
    latency_ms: float | None = None


class HealthResponse(BaseModel):
    status: str
    environment: str
    version: str
    timestamp: datetime
    components: dict[str, HealthComponent]
    warnings: list[str] = Field(default_factory=list)


class AnalyticsEventRequest(BaseModel):
    event_type: str = Field(..., max_length=40)
    entity_type: str | None = Field(default=None, max_length=40)
    entity_id: str | None = Field(default=None, max_length=100)
    properties: dict[str, Any] = Field(default_factory=dict)
