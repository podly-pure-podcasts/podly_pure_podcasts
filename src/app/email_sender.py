from __future__ import annotations

import smtplib
from email.message import EmailMessage

from flask import current_app

from app.extensions import db
from app.models import EmailSettings


class EmailSendError(Exception):
    pass


def send_email(*, to_email: str, subject: str, body: str) -> None:
    settings = db.session.get(EmailSettings, 1)
    if settings is None:
        raise EmailSendError("Email settings are not configured.")

    if not settings.smtp_host or not settings.smtp_port:
        raise EmailSendError("SMTP host/port are not configured.")

    from_email = settings.from_email
    if not from_email:
        raise EmailSendError("From email is not configured.")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to_email
    msg.set_content(body)

    try:
        if settings.smtp_use_ssl:
            server: smtplib.SMTP = smtplib.SMTP_SSL(settings.smtp_host, int(settings.smtp_port), timeout=20)
        else:
            server = smtplib.SMTP(settings.smtp_host, int(settings.smtp_port), timeout=20)

        with server:
            server.ehlo()
            if settings.smtp_use_tls and not settings.smtp_use_ssl:
                server.starttls()
                server.ehlo()

            if settings.smtp_username and settings.smtp_password:
                server.login(settings.smtp_username, settings.smtp_password)

            server.send_message(msg)

    except Exception as exc:  # pragma: no cover
        current_app.logger.error("Failed to send email: %s", exc)
        raise EmailSendError("Failed to send email.") from exc
