"""Authentication endpoints.

Tokens are delivered two ways so both browsers and API clients are first-class:
  * httpOnly, SameSite cookies (browser — immune to XSS token theft)
  * the access token in the JSON body (mobile/API clients)
"""

from __future__ import annotations

import secrets
from datetime import timedelta
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Request, Response, status
from fastapi.responses import RedirectResponse

from pakjobs_core.config import settings
from pakjobs_core.domain.enums import AnalyticsEventType
from pakjobs_core.http import http_verify
from pakjobs_core.logging import get_logger
from pakjobs_core.models import User
from pakjobs_core.services.profile import next_profile_steps

from app.core.deps import ACCESS_COOKIE, REFRESH_COOKIE, CurrentUser, SessionDep
from app.core.errors import UnauthorizedError, ValidationError
from app.schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    MeResponse,
    ProfileResponse,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserResponse,
    VerifyEmailRequest,
)
from app.schemas.common import MessageResponse
from app.services.analytics_service import record_event
from app.services.auth_service import AuthService
from app.services.email_service import send_password_reset_email, send_verification_email

logger = get_logger("api.auth")
router = APIRouter(prefix="/auth", tags=["auth"])

OAUTH_STATE_COOKIE = "rozgar_oauth_state"


# --- cookie helpers ---------------------------------------------------------

def _set_auth_cookies(response: Response, access_token: str, refresh_token: str | None) -> None:
    common = {
        "httponly": True,
        "secure": settings.cookie_secure,
        "samesite": settings.cookie_samesite,
        "path": "/",
    }
    if settings.cookie_domain:
        common["domain"] = settings.cookie_domain

    response.set_cookie(
        ACCESS_COOKIE, access_token, max_age=settings.access_token_ttl_minutes * 60, **common
    )
    if refresh_token:
        response.set_cookie(
            REFRESH_COOKIE,
            refresh_token,
            max_age=settings.refresh_token_ttl_days * 86400,
            **{**common, "path": "/"},
        )


def _clear_auth_cookies(response: Response) -> None:
    for name in (ACCESS_COOKIE, REFRESH_COOKIE):
        response.delete_cookie(name, path="/", domain=settings.cookie_domain or None)


def _token_response(user: User, access_token: str) -> TokenResponse:
    return TokenResponse(
        access_token=access_token,
        expires_in=settings.access_token_ttl_minutes * 60,
        user=_user_response(user),
    )


def _user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        role=user.role,
        status=user.status,
        email_verified=user.email_verified_at is not None,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
    )


# --- endpoints --------------------------------------------------------------

@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, request: Request, response: Response, session: SessionDep):
    """Create an account. The user is signed in immediately but must verify their email."""
    service = AuthService(session)
    user, verify_token = await service.register(
        email=payload.email, password=payload.password, full_name=payload.full_name, city=payload.city
    )
    access = service.create_access_token_for(user)
    refresh = await service.issue_refresh_token(
        user, user_agent=request.headers.get("user-agent"),
        ip=request.client.host if request.client else None,
    )
    _set_auth_cookies(response, access, refresh)

    await session.flush()
    send_verification_email(session, user, verify_token)
    await record_event(session, AnalyticsEventType.SIGNUP, user_id=user.id)
    return _token_response(user, access)


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, request: Request, response: Response, session: SessionDep):
    service = AuthService(session)
    user = await service.authenticate(email=payload.email, password=payload.password)
    access = service.create_access_token_for(user)
    refresh = await service.issue_refresh_token(
        user, user_agent=request.headers.get("user-agent"),
        ip=request.client.host if request.client else None,
    )
    _set_auth_cookies(response, access, refresh)
    await record_event(session, AnalyticsEventType.LOGIN, user_id=user.id)
    return _token_response(user, access)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_session(
    payload: RefreshRequest, request: Request, response: Response, session: SessionDep
):
    raw = payload.refresh_token or request.cookies.get(REFRESH_COOKIE)
    if not raw:
        raise UnauthorizedError("No active session found. Please sign in.")
    service = AuthService(session)
    user, new_refresh = await service.rotate_refresh_token(raw)
    access = service.create_access_token_for(user)
    _set_auth_cookies(response, access, new_refresh)
    return _token_response(user, access)


@router.post("/logout", response_model=MessageResponse)
async def logout(request: Request, response: Response, session: SessionDep):
    raw = request.cookies.get(REFRESH_COOKIE)
    await AuthService(session).revoke_refresh_token(raw)
    _clear_auth_cookies(response)
    return MessageResponse(message="You have been signed out.")


@router.get("/me", response_model=MeResponse)
async def me(user: CurrentUser, session: SessionDep):
    from sqlalchemy import func, select

    from pakjobs_core.models import JobAlert, SavedJob

    saved_count = (
        await session.execute(select(func.count(SavedJob.id)).where(SavedJob.user_id == user.id))
    ).scalar_one()
    alert_count = (
        await session.execute(
            select(func.count(JobAlert.id)).where(JobAlert.user_id == user.id, JobAlert.is_active.is_(True))
        )
    ).scalar_one()

    profile_response = None
    if user.profile:
        profile_response = ProfileResponse.model_validate(user.profile)
        profile_response.next_steps = next_profile_steps(user.profile)

    return MeResponse(
        user=_user_response(user),
        profile=profile_response,
        stats={"saved_jobs": saved_count, "active_alerts": alert_count},
    )


@router.post("/verify-email", response_model=MessageResponse)
async def verify_email(payload: VerifyEmailRequest, session: SessionDep):
    await AuthService(session).verify_email(payload.token)
    return MessageResponse(message="Your email address has been verified.")


@router.post("/resend-verification", response_model=MessageResponse)
async def resend_verification(user: CurrentUser, session: SessionDep):
    if user.email_verified_at is not None:
        return MessageResponse(message="Your email address is already verified.")
    service = AuthService(session)
    token = await service.issue_verification_token(
        user, purpose="email_verify", ttl=timedelta(hours=48)
    )
    await session.flush()
    send_verification_email(session, user, token)
    return MessageResponse(message="A new verification link has been sent to your email.")


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(payload: ForgotPasswordRequest, session: SessionDep):
    """Always returns success — the response must not reveal whether an account exists."""
    result = await AuthService(session).start_password_reset(payload.email)
    if result:
        user, token = result
        await session.flush()
        send_password_reset_email(session, user, token)
    return MessageResponse(
        message="If an account exists for that email, we have sent a password reset link."
    )


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(payload: ResetPasswordRequest, response: Response, session: SessionDep):
    await AuthService(session).complete_password_reset(payload.token, payload.password)
    _clear_auth_cookies(response)
    return MessageResponse(message="Your password has been reset. Please sign in with your new password.")


@router.post("/change-password", response_model=MessageResponse)
async def change_password(payload: ChangePasswordRequest, user: CurrentUser,
                          response: Response, session: SessionDep):
    await AuthService(session).change_password(
        user, current=payload.current_password, new=payload.new_password
    )
    _clear_auth_cookies(response)
    return MessageResponse(message="Password updated. Please sign in again.")


# --- Google OAuth -----------------------------------------------------------

@router.get("/google/config")
async def google_config():
    """Lets the frontend hide the Google button when OAuth is not configured."""
    return {"enabled": bool(settings.google_client_id and settings.google_client_secret)}


@router.get("/google/start")
async def google_start(response: Response):
    if not (settings.google_client_id and settings.google_client_secret):
        raise ValidationError(
            "Google sign-in is not configured on this deployment. "
            "Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET to enable it.",
            code="google_not_configured",
        )
    state = secrets.token_urlsafe(24)
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "offline",
        "prompt": "select_account",
    }
    redirect = RedirectResponse(
        f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}",
        status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    )
    # CSRF protection for the OAuth round-trip.
    redirect.set_cookie(
        OAUTH_STATE_COOKIE, state, max_age=600, httponly=True,
        secure=settings.cookie_secure, samesite="lax", path="/",
    )
    return redirect


@router.get("/google/callback")
async def google_callback(request: Request, session: SessionDep, code: str | None = None,
                          state: str | None = None, error: str | None = None):
    failure_url = f"{settings.web_base_url}/login?error=google_failed"
    if error or not code:
        return RedirectResponse(failure_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    expected_state = request.cookies.get(OAUTH_STATE_COOKIE)
    if not expected_state or not state or not secrets.compare_digest(expected_state, state):
        logger.warning("auth.google_state_mismatch")
        return RedirectResponse(failure_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    try:
        async with httpx.AsyncClient(timeout=20, verify=http_verify()) as client:
            token_response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "redirect_uri": settings.google_redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
            if token_response.status_code >= 300:
                logger.error("auth.google_token_exchange_failed", status=token_response.status_code)
                return RedirectResponse(failure_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
            access_token = token_response.json().get("access_token")

            info_response = await client.get(
                "https://www.googleapis.com/oauth2/v3/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if info_response.status_code >= 300:
                return RedirectResponse(failure_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
            info = info_response.json()
    except httpx.HTTPError as exc:
        logger.error("auth.google_network_error", error=str(exc))
        return RedirectResponse(failure_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    if not info.get("email_verified"):
        return RedirectResponse(f"{settings.web_base_url}/login?error=email_unverified",
                                status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    service = AuthService(session)
    user = await service.authenticate_google(
        google_sub=str(info["sub"]), email=info["email"], full_name=info.get("name")
    )
    await session.flush()
    access = service.create_access_token_for(user)
    refresh = await service.issue_refresh_token(user, user_agent=request.headers.get("user-agent"))

    redirect = RedirectResponse(f"{settings.web_base_url}/dashboard",
                                status_code=status.HTTP_307_TEMPORARY_REDIRECT)
    _set_auth_cookies(redirect, access, refresh)
    redirect.delete_cookie(OAUTH_STATE_COOKIE, path="/")
    await record_event(session, AnalyticsEventType.LOGIN, user_id=user.id, properties={"provider": "google"})
    return redirect
