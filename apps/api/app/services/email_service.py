"""Transactional email composition.

Delivery goes through the channel adapters in `pakjobs_core.services.notifications`, so a
provider outage is logged and retryable rather than fatal. Never raises to the caller.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from pakjobs_core.config import settings
from pakjobs_core.domain.enums import NotificationStatus
from pakjobs_core.logging import get_logger
from pakjobs_core.models import Notification, User
from pakjobs_core.services.notifications import get_email_adapter

logger = get_logger("email")


def _queue_and_send(
    session: AsyncSession, user: User, *, subject: str, text: str, html: str, notification_type: str
) -> None:
    notification = Notification(
        user_id=user.id, type=notification_type, subject=subject[:300], body=text,
        status=NotificationStatus.PENDING, attempts=1,
    )
    session.add(notification)

    adapter = get_email_adapter()
    result = adapter.send(to=user.email, subject=subject, text_body=text, html_body=html)
    if result.ok:
        from datetime import datetime, timezone

        notification.status = NotificationStatus.SENT
        notification.sent_at = datetime.now(timezone.utc)
    else:
        notification.status = NotificationStatus.FAILED
        notification.error = result.detail[:500]
        logger.error("email.delivery_failed", type=notification_type, detail=result.detail[:200])


def _shell(title: str, body_html: str, cta_label: str, cta_url: str) -> str:
    return f"""<!doctype html><html><body style="margin:0;background:#f8fafc;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif">
<div style="max-width:520px;margin:0 auto;padding:24px">
  <div style="background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:28px">
    <p style="margin:0 0 6px;font-size:13px;color:#64748b;letter-spacing:.02em">RozgarPK</p>
    <h1 style="margin:0 0 12px;font-size:20px;color:#0f172a">{title}</h1>
    {body_html}
    <p style="margin:24px 0 0">
      <a href="{cta_url}" style="display:inline-block;background:#0f766e;color:#fff;padding:11px 18px;
         border-radius:8px;text-decoration:none;font-weight:600;font-size:14px">{cta_label}</a>
    </p>
    <p style="margin:22px 0 0;font-size:12px;color:#94a3b8;word-break:break-all">
      If the button does not work, copy this link into your browser:<br>{cta_url}
    </p>
  </div>
</div></body></html>"""


def send_verification_email(session: AsyncSession, user: User, token: str) -> None:
    url = f"{settings.web_base_url}/verify-email?token={token}"
    text = (
        "Welcome to RozgarPK.\n\n"
        f"Confirm your email address to activate job alerts and recommendations:\n{url}\n\n"
        "This link expires in 48 hours. If you did not create an account, you can ignore this email."
    )
    html = _shell(
        "Confirm your email address",
        '<p style="margin:0;font-size:14px;color:#334155;line-height:1.6">Confirm your email address '
        "to activate job alerts and personalised recommendations. This link expires in 48 hours.</p>",
        "Confirm email", url,
    )
    _queue_and_send(session, user, subject="Confirm your RozgarPK email address",
                    text=text, html=html, notification_type="email_verification")


def send_password_reset_email(session: AsyncSession, user: User, token: str) -> None:
    url = f"{settings.web_base_url}/reset-password?token={token}"
    text = (
        "We received a request to reset your RozgarPK password.\n\n"
        f"Reset it here:\n{url}\n\n"
        "This link expires in 60 minutes. If you did not request this, no action is needed — "
        "your password has not changed."
    )
    html = _shell(
        "Reset your password",
        '<p style="margin:0;font-size:14px;color:#334155;line-height:1.6">We received a request to reset '
        "your password. This link expires in 60 minutes. If you did not request it, no action is needed.</p>",
        "Reset password", url,
    )
    _queue_and_send(session, user, subject="Reset your RozgarPK password",
                    text=text, html=html, notification_type="password_reset")
