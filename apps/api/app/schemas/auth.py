from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from pakjobs_core.services.security import MIN_PASSWORD_LENGTH


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=MIN_PASSWORD_LENGTH, max_length=200)
    full_name: str | None = Field(default=None, max_length=160)
    city: str | None = Field(default=None, max_length=120)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=200)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: "UserResponse"


class RefreshRequest(BaseModel):
    refresh_token: str | None = None  # optional: cookie is preferred


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(..., min_length=10, max_length=400)
    password: str = Field(..., min_length=MIN_PASSWORD_LENGTH, max_length=200)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=200)
    new_password: str = Field(..., min_length=MIN_PASSWORD_LENGTH, max_length=200)


class VerifyEmailRequest(BaseModel):
    token: str = Field(..., min_length=10, max_length=400)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    role: str
    status: str
    email_verified: bool = False
    created_at: datetime | None = None
    last_login_at: datetime | None = None


class ProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str | None = None
    headline: str | None = None
    phone: str | None = None
    city: str | None = None
    province: str | None = None
    education_level: str | None = None
    degree: str | None = None
    institution: str | None = None
    graduation_year: int | None = None
    years_of_experience: int | None = None
    experience_level: str | None = None
    summary: str | None = None
    skills: list[str] = Field(default_factory=list)
    preferred_locations: list[str] = Field(default_factory=list)
    preferred_categories: list[str] = Field(default_factory=list)
    preferred_job_types: list[str] = Field(default_factory=list)
    expected_salary_min: Decimal | None = None
    expected_salary_max: Decimal | None = None
    salary_currency: str = "PKR"
    remote_preference: str | None = None
    open_to_relocation: bool = False
    profile_completion: int = 0
    next_steps: list[str] = Field(default_factory=list)


class ProfileUpdateRequest(BaseModel):
    full_name: str | None = Field(default=None, max_length=160)
    headline: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=32)
    city: str | None = Field(default=None, max_length=120)
    province: str | None = Field(default=None, max_length=120)
    education_level: str | None = Field(default=None, max_length=80)
    degree: str | None = Field(default=None, max_length=160)
    institution: str | None = Field(default=None, max_length=200)
    graduation_year: int | None = Field(default=None, ge=1950, le=2100)
    years_of_experience: int | None = Field(default=None, ge=0, le=60)
    experience_level: str | None = Field(default=None, max_length=40)
    summary: str | None = Field(default=None, max_length=4000)
    skills: list[str] | None = Field(default=None, max_length=50)
    preferred_locations: list[str] | None = Field(default=None, max_length=20)
    preferred_categories: list[str] | None = Field(default=None, max_length=20)
    preferred_job_types: list[str] | None = Field(default=None, max_length=10)
    expected_salary_min: Decimal | None = Field(default=None, ge=0, le=100_000_000)
    expected_salary_max: Decimal | None = Field(default=None, ge=0, le=100_000_000)
    remote_preference: str | None = Field(default=None, max_length=20)
    open_to_relocation: bool | None = None

    @field_validator("skills", "preferred_locations", "preferred_categories", "preferred_job_types")
    @classmethod
    def _clean_list(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned = [v.strip()[:80] for v in value if v and v.strip()]
        return list(dict.fromkeys(cleaned))

    @field_validator("remote_preference")
    @classmethod
    def _valid_remote(cls, value: str | None) -> str | None:
        if value is None:
            return None
        allowed = {"remote", "hybrid", "onsite", "any"}
        if value not in allowed:
            raise ValueError(f"remote_preference must be one of: {', '.join(sorted(allowed))}")
        return value


class MeResponse(BaseModel):
    user: UserResponse
    profile: ProfileResponse | None = None
    stats: dict[str, Any] = Field(default_factory=dict)


TokenResponse.model_rebuild()
