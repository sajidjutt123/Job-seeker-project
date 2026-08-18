"""Authentication business logic (async, used by the API layer).

Security properties enforced here:
  * Argon2id password hashing; automatic rehash when parameters change.
  * Login responses are indistinguishable for "unknown email" and "wrong password".
  * Refresh tokens are opaque, stored hashed, single-use (rotated on every refresh).
  * Password reset / email verification tokens are hashed, single-use and time-limited.
  * `token_version` bumping revokes every outstanding session on password change.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from pakjobs_core.domain.enums import UserRole, UserStatus
from pakjobs_core.logging import get_logger
from pakjobs_core.models import Profile, RefreshToken, User, VerificationToken
from pakjobs_core.services.profile import compute_profile_completion
from pakjobs_core.services.security import (
    PasswordPolicyError,
    create_access_token,
    generate_opaque_token,
    hash_ip,
    hash_password,
    hash_token,
    needs_rehash,
    refresh_token_expiry,
    verify_password,
)

from app.core.errors import ConflictError, ForbiddenError, UnauthorizedError, ValidationError

logger = get_logger("auth")

EMAIL_VERIFY_TTL_HOURS = 48
PASSWORD_RESET_TTL_MINUTES = 60
MAX_ACTIVE_SESSIONS = 10


class AuthService:
    def __init__(self, session: AsyncSession):
        self.session = session

    # --- registration -------------------------------------------------------
    async def register(
        self, *, email: str, password: str, full_name: str | None = None, city: str | None = None
    ) -> tuple[User, str]:
        """Create a user + empty profile. Returns (user, email_verification_token)."""
        normalized = email.strip().lower()
        existing = await self._get_by_email(normalized)
        if existing is not None:
            raise ConflictError("An account with this email already exists.")

        try:
            password_hash = hash_password(password)
        except PasswordPolicyError as exc:
            raise ValidationError(str(exc), details={"fields": {"password": str(exc)}}) from exc

        user = User(
            email=normalized,
            password_hash=password_hash,
            role=UserRole.USER,
            status=UserStatus.PENDING_VERIFICATION,
        )
        self.session.add(user)
        await self.session.flush()

        profile = Profile(user_id=user.id, full_name=full_name, city=city)
        profile.profile_completion = compute_profile_completion(profile)
        self.session.add(profile)

        token = await self.issue_verification_token(user, purpose="email_verify",
                                                    ttl=timedelta(hours=EMAIL_VERIFY_TTL_HOURS))
        logger.info("auth.registered", user_id=str(user.id))
        return user, token

    # --- login --------------------------------------------------------------
    async def authenticate(self, *, email: str, password: str) -> User:
        user = await self._get_by_email(email.strip().lower())
        if user is None or not user.password_hash:
            # Spend comparable time so timing cannot enumerate accounts.
            verify_password(password, "$argon2id$v=19$m=65536,t=3,p=2$c29tZXNhbHR2YWx1ZQ$"
                                      "0000000000000000000000000000000000000000000")
            raise UnauthorizedError("Incorrect email or password.")
        if not verify_password(password, user.password_hash):
            raise UnauthorizedError("Incorrect email or password.")
        if user.status == UserStatus.SUSPENDED:
            raise ForbiddenError("This account has been suspended.")
        if user.status == UserStatus.DELETED:
            raise UnauthorizedError("Incorrect email or password.")

        if needs_rehash(user.password_hash):
            user.password_hash = hash_password(password)

        user.last_login_at = datetime.now(timezone.utc)
        return user

    async def authenticate_google(self, *, google_sub: str, email: str, full_name: str | None) -> User:
        """Link or create an account from a verified Google identity."""
        normalized = email.strip().lower()
        user = (
            await self.session.execute(select(User).where(User.google_sub == google_sub))
        ).scalar_one_or_none()

        if user is None:
            user = await self._get_by_email(normalized)
            if user is not None:
                # Existing password account: link the Google identity to it.
                user.google_sub = google_sub
            else:
                user = User(
                    email=normalized,
                    google_sub=google_sub,
                    role=UserRole.USER,
                    status=UserStatus.ACTIVE,
                    email_verified_at=datetime.now(timezone.utc),
                )
                self.session.add(user)
                await self.session.flush()
                profile = Profile(user_id=user.id, full_name=full_name)
                profile.profile_completion = compute_profile_completion(profile)
                self.session.add(profile)

        if user.status == UserStatus.SUSPENDED:
            raise ForbiddenError("This account has been suspended.")
        # Google has already verified the address.
        if user.email_verified_at is None:
            user.email_verified_at = datetime.now(timezone.utc)
        if user.status == UserStatus.PENDING_VERIFICATION:
            user.status = UserStatus.ACTIVE
        user.last_login_at = datetime.now(timezone.utc)
        return user

    # --- tokens -------------------------------------------------------------
    def create_access_token_for(self, user: User) -> str:
        return create_access_token(user_id=user.id, role=user.role, token_version=user.token_version)

    async def issue_refresh_token(
        self, user: User, *, user_agent: str | None = None, ip: str | None = None
    ) -> str:
        token = generate_opaque_token()
        self.session.add(
            RefreshToken(
                user_id=user.id,
                token_hash=hash_token(token),
                expires_at=refresh_token_expiry(),
                user_agent=(user_agent or "")[:400] or None,
                ip_hash=hash_ip(ip),
            )
        )
        await self._prune_sessions(user)
        return token

    async def rotate_refresh_token(self, raw_token: str) -> tuple[User, str]:
        """Single-use rotation: the presented token is revoked and a new one issued."""
        token_hash = hash_token(raw_token)
        record = (
            await self.session.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
        ).scalar_one_or_none()

        now = datetime.now(timezone.utc)
        if record is None or record.revoked_at is not None or record.expires_at < now:
            raise UnauthorizedError("Your session has expired. Please sign in again.")

        user = (
            await self.session.execute(
                select(User).options(selectinload(User.profile)).where(User.id == record.user_id)
            )
        ).scalar_one_or_none()
        if user is None or user.status in (UserStatus.SUSPENDED, UserStatus.DELETED):
            raise UnauthorizedError("Your session is no longer valid.")

        record.revoked_at = now
        new_token = await self.issue_refresh_token(user, user_agent=record.user_agent)
        return user, new_token

    async def revoke_refresh_token(self, raw_token: str | None) -> None:
        if not raw_token:
            return
        await self.session.execute(
            update(RefreshToken)
            .where(RefreshToken.token_hash == hash_token(raw_token), RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(timezone.utc))
        )

    async def revoke_all_sessions(self, user: User) -> None:
        await self.session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(timezone.utc))
        )
        user.token_version += 1

    async def _prune_sessions(self, user: User) -> None:
        """Keep the newest N sessions per user so the table cannot grow without bound."""
        stmt = (
            select(RefreshToken)
            .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
            .order_by(RefreshToken.created_at.desc())
        )
        tokens = list((await self.session.execute(stmt)).scalars().all())
        for stale in tokens[MAX_ACTIVE_SESSIONS:]:
            stale.revoked_at = datetime.now(timezone.utc)

    # --- verification / reset ----------------------------------------------
    async def issue_verification_token(
        self, user: User, *, purpose: str, ttl: timedelta
    ) -> str:
        token = generate_opaque_token(24)
        self.session.add(
            VerificationToken(
                user_id=user.id,
                purpose=purpose,
                token_hash=hash_token(token),
                expires_at=datetime.now(timezone.utc) + ttl,
            )
        )
        return token

    async def consume_verification_token(self, raw_token: str, *, purpose: str) -> User:
        record = (
            await self.session.execute(
                select(VerificationToken).where(
                    VerificationToken.token_hash == hash_token(raw_token),
                    VerificationToken.purpose == purpose,
                )
            )
        ).scalar_one_or_none()

        now = datetime.now(timezone.utc)
        if record is None or record.used_at is not None or record.expires_at < now:
            raise ValidationError("This link is invalid or has expired. Please request a new one.")

        record.used_at = now
        user = (await self.session.execute(select(User).where(User.id == record.user_id))).scalar_one_or_none()
        if user is None:
            raise ValidationError("This link is invalid or has expired. Please request a new one.")
        return user

    async def verify_email(self, raw_token: str) -> User:
        user = await self.consume_verification_token(raw_token, purpose="email_verify")
        user.email_verified_at = datetime.now(timezone.utc)
        if user.status == UserStatus.PENDING_VERIFICATION:
            user.status = UserStatus.ACTIVE
        return user

    async def start_password_reset(self, email: str) -> tuple[User, str] | None:
        """Returns None for unknown accounts — the caller must still respond with success."""
        user = await self._get_by_email(email.strip().lower())
        if user is None or user.status == UserStatus.DELETED:
            return None
        token = await self.issue_verification_token(
            user, purpose="password_reset", ttl=timedelta(minutes=PASSWORD_RESET_TTL_MINUTES)
        )
        return user, token

    async def complete_password_reset(self, raw_token: str, new_password: str) -> User:
        user = await self.consume_verification_token(raw_token, purpose="password_reset")
        try:
            user.password_hash = hash_password(new_password)
        except PasswordPolicyError as exc:
            raise ValidationError(str(exc), details={"fields": {"password": str(exc)}}) from exc
        if user.status == UserStatus.PENDING_VERIFICATION:
            user.status = UserStatus.ACTIVE
            user.email_verified_at = user.email_verified_at or datetime.now(timezone.utc)
        await self.revoke_all_sessions(user)
        logger.info("auth.password_reset", user_id=str(user.id))
        return user

    async def change_password(self, user: User, *, current: str, new: str) -> None:
        if not verify_password(current, user.password_hash):
            raise UnauthorizedError("Your current password is incorrect.")
        try:
            user.password_hash = hash_password(new)
        except PasswordPolicyError as exc:
            raise ValidationError(str(exc), details={"fields": {"new_password": str(exc)}}) from exc
        await self.revoke_all_sessions(user)

    # --- helpers ------------------------------------------------------------
    async def _get_by_email(self, email: str) -> User | None:
        return (
            await self.session.execute(
                select(User).options(selectinload(User.profile)).where(User.email == email)
            )
        ).scalar_one_or_none()
