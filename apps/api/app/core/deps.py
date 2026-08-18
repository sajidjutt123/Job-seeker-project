"""FastAPI dependencies: sessions, authenticated principals, authorization.

Authorization is ALWAYS enforced here (server-side). Frontend checks are cosmetic only.
"""

from __future__ import annotations

import uuid
from typing import Annotated

import jwt
from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pakjobs_core.db.session import get_async_session
from pakjobs_core.domain.enums import UserRole, UserStatus
from pakjobs_core.models import User
from pakjobs_core.services.security import decode_token

from app.core.errors import ForbiddenError, UnauthorizedError

ACCESS_COOKIE = "rozgar_access"
REFRESH_COOKIE = "rozgar_refresh"

SessionDep = Annotated[AsyncSession, Depends(get_async_session)]


def _extract_token(request: Request) -> str | None:
    """Bearer header first (API clients), then the httpOnly cookie (browser)."""
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        token = header[7:].strip()
        if token:
            return token
    return request.cookies.get(ACCESS_COOKIE)


async def _load_user(session: AsyncSession, token: str) -> User:
    try:
        payload = decode_token(token)
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("Your session has expired. Please sign in again.",
                                code="token_expired") from exc
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("Invalid authentication token.") from exc

    if payload.get("type") != "access":
        raise UnauthorizedError("Invalid authentication token.")

    try:
        user_id = uuid.UUID(str(payload.get("sub")))
    except (TypeError, ValueError) as exc:
        raise UnauthorizedError("Invalid authentication token.") from exc

    user = (
        await session.execute(
            select(User).options(selectinload(User.profile)).where(User.id == user_id)
        )
    ).scalar_one_or_none()

    if user is None:
        raise UnauthorizedError("Account not found.")
    if user.status == UserStatus.SUSPENDED:
        raise ForbiddenError("This account has been suspended. Contact support if you believe this is a mistake.")
    if user.status == UserStatus.DELETED:
        raise UnauthorizedError("Account not found.")
    # Password change / global logout invalidates older tokens.
    if int(payload.get("tv", 0)) != user.token_version:
        raise UnauthorizedError("Your session is no longer valid. Please sign in again.",
                                code="token_revoked")
    return user


async def get_current_user(request: Request, session: SessionDep) -> User:
    token = _extract_token(request)
    if not token:
        raise UnauthorizedError("You must be signed in to do that.")
    return await _load_user(session, token)


async def get_optional_user(request: Request, session: SessionDep) -> User | None:
    """For endpoints that personalise when signed in but work anonymously."""
    token = _extract_token(request)
    if not token:
        return None
    try:
        return await _load_user(session, token)
    except (UnauthorizedError, ForbiddenError):
        return None


async def require_admin(user: Annotated[User, Depends(get_current_user)]) -> User:
    if user.role != UserRole.ADMIN:
        raise ForbiddenError("Administrator access is required.")
    return user


async def require_verified_user(user: Annotated[User, Depends(get_current_user)]) -> User:
    if user.email_verified_at is None and user.google_sub is None:
        raise ForbiddenError("Please verify your email address to continue.", code="email_unverified")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalUser = Annotated[User | None, Depends(get_optional_user)]
AdminUser = Annotated[User, Depends(require_admin)]
