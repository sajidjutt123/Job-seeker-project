"""Notification service.

Channel-agnostic by design: `NotificationChannelAdapter` is the seam. Email ships in v1; push,
WhatsApp and Telegram adapters can be registered later without touching callers.

A `Notification` row is always persisted first, then delivery is attempted — so a provider outage
is visible and retryable instead of silently losing the message.
"""

from __future__ import annotations

import abc
import smtplib
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Any, Sequence

import httpx
from sqlalchemy.orm import Session

from pakjobs_core.config import settings
from pakjobs_core.domain.enums import NotificationChannel, NotificationStatus
from pakjobs_core.http import http_verify
from pakjobs_core.logging import get_logger
from pakjobs_core.models import Job, Notification, User

logger = get_logger("notifications")


@dataclass(slots=True)
class DeliveryResult:
    ok: bool
    detail: str = ""


class NotificationChannelAdapter(abc.ABC):
    channel: str

    @abc.abstractmethod
    def send(self, *, to: str, subject: str, text_body: str, html_body: str | None = None) -> DeliveryResult: ...


class ConsoleEmailAdapter(NotificationChannelAdapter):
    """Development sink — writes the message to the structured log, never to the network."""

    channel = NotificationChannel.EMAIL

    def send(self, *, to: str, subject: str, text_body: str, html_body: str | None = None) -> DeliveryResult:
        logger.info("email.console", to=to, subject=subject, body_preview=text_body[:400])
        return DeliveryResult(ok=True, detail="logged to console (EMAIL_PROVIDER=console)")


class SMTPEmailAdapter(NotificationChannelAdapter):
    channel = NotificationChannel.EMAIL

    def send(self, *, to: str, subject: str, text_body: str, html_body: str | None = None) -> DeliveryResult:
        if not settings.smtp_host:
            return DeliveryResult(ok=False, detail="SMTP_HOST is not configured")
        message = EmailMessage()
        message["From"] = settings.email_from
        message["To"] = to
        message["Subject"] = subject
        message.set_content(text_body)
        if html_body:
            message.add_alternative(html_body, subtype="html")
        try:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as server:
                if settings.smtp_starttls:
                    server.starttls()
                if settings.smtp_username:
                    server.login(settings.smtp_username, settings.smtp_password)
                server.send_message(message)
        except Exception as exc:  # noqa: BLE001 - provider failures must not crash the worker
            logger.error("email.smtp_failed", error=str(exc), to=to)
            return DeliveryResult(ok=False, detail=str(exc))
        return DeliveryResult(ok=True, detail="sent via SMTP")


class ResendEmailAdapter(NotificationChannelAdapter):
    channel = NotificationChannel.EMAIL

    def send(self, *, to: str, subject: str, text_body: str, html_body: str | None = None) -> DeliveryResult:
        if not settings.resend_api_key:
            return DeliveryResult(ok=False, detail="RESEND_API_KEY is not configured")
        try:
            response = httpx.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {settings.resend_api_key}"},
                json={
                    "from": settings.email_from,
                    "to": [to],
                    "subject": subject,
                    "text": text_body,
                    **({"html": html_body} if html_body else {}),
                },
                timeout=20,
                verify=http_verify(),
            )
        except httpx.HTTPError as exc:
            return DeliveryResult(ok=False, detail=f"network error: {exc}")
        if response.status_code >= 300:
            return DeliveryResult(ok=False, detail=f"HTTP {response.status_code}: {response.text[:200]}")
        return DeliveryResult(ok=True, detail="sent via Resend")


# Future channels: implement the adapter and register the key here.
_EMAIL_ADAPTERS = {
    "console": ConsoleEmailAdapter,
    "smtp": SMTPEmailAdapter,
    "resend": ResendEmailAdapter,
}


def get_email_adapter() -> NotificationChannelAdapter:
    return _EMAIL_ADAPTERS.get(settings.email_provider, ConsoleEmailAdapter)()


class NotificationService:
    def __init__(self, session: Session):
        self.session = session
        self.email = get_email_adapter()

    def queue(
        self,
        *,
        user: User,
        subject: str,
        body: str,
        notification_type: str = "job_alert",
        channel: str = NotificationChannel.EMAIL,
        payload: dict[str, Any] | None = None,
    ) -> Notification:
        notification = Notification(
            user_id=user.id,
            channel=channel,
            type=notification_type,
            subject=subject[:300],
            body=body,
            payload=payload or {},
            status=NotificationStatus.PENDING,
        )
        self.session.add(notification)
        self.session.flush()
        return notification

    def deliver(self, notification: Notification, *, to_email: str, html_body: str | None = None) -> bool:
        notification.attempts += 1
        if notification.channel != NotificationChannel.EMAIL:
            notification.status = NotificationStatus.FAILED
            notification.error = f"Channel '{notification.channel}' has no adapter yet"
            return False

        result = self.email.send(
            to=to_email, subject=notification.subject, text_body=notification.body or "", html_body=html_body
        )
        if result.ok:
            notification.status = NotificationStatus.SENT
            notification.sent_at = datetime.now(timezone.utc)
            notification.error = None
        else:
            notification.status = NotificationStatus.FAILED
            notification.error = result.detail[:500]
        return result.ok


# --- message rendering ------------------------------------------------------

def render_alert_email(alert_name: str, jobs: Sequence[Job], web_base_url: str) -> tuple[str, str, str]:
    """Return (subject, text_body, html_body) for a job-alert digest."""
    count = len(jobs)
    subject = f"{count} new job{'s' if count != 1 else ''} for “{alert_name}”"

    text_lines = [f"New matches for your alert “{alert_name}”:", ""]
    html_rows = []
    for job in jobs:
        url = f"{web_base_url}/jobs/{job.slug}"
        location = job.location or ("Remote" if job.is_remote else "Pakistan")
        company = job.company_name_raw or "Company not stated"
        text_lines.append(f"• {job.title} — {company} — {location}\n  {url}")
        html_rows.append(
            f'<tr><td style="padding:12px 0;border-bottom:1px solid #e5e7eb">'
            f'<a href="{url}" style="font-weight:600;color:#0f172a;text-decoration:none;font-size:15px">'
            f"{_escape(job.title)}</a><br>"
            f'<span style="color:#475569;font-size:13px">{_escape(company)} · {_escape(location)}</span>'
            f"</td></tr>"
        )
    text_lines += ["", f"Manage your alerts: {web_base_url}/dashboard/alerts"]

    html_body = f"""<!doctype html><html><body style="margin:0;background:#f8fafc;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif">
<div style="max-width:560px;margin:0 auto;padding:24px">
  <div style="background:#ffffff;border:1px solid #e2e8f0;border-radius:12px;padding:24px">
    <p style="margin:0 0 4px;font-size:13px;color:#64748b">RozgarPK job alert</p>
    <h1 style="margin:0 0 16px;font-size:19px;color:#0f172a">{count} new match{'es' if count != 1 else ''} for “{_escape(alert_name)}”</h1>
    <table style="width:100%;border-collapse:collapse">{''.join(html_rows)}</table>
    <p style="margin:20px 0 0;font-size:12px;color:#64748b">
      You are receiving this because you created a job alert on RozgarPK.
      <a href="{web_base_url}/dashboard/alerts" style="color:#2563eb">Manage alerts</a>.
    </p>
  </div>
</div></body></html>"""
    return subject, "\n".join(text_lines), html_body


def _escape(value: str | None) -> str:
    import html

    return html.escape(value or "")
