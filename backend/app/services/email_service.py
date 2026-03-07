"""Email service for sending transactional emails (password reset, etc.)."""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import settings

logger = logging.getLogger(__name__)


class EmailService:
    """Sends transactional emails via SMTP.

    Falls back to logging the email content when SMTP is not configured,
    which is useful during development.
    """

    def send_password_reset(self, to_email: str, reset_url: str) -> None:
        """Send a password reset email.

        Args:
            to_email: Recipient email address.
            reset_url: Full URL with token for the password reset page.
        """
        subject = f"{settings.PROJECT_NAME} - Password Reset Request"
        html_body = f"""
        <html>
        <body style="font-family: sans-serif; max-width: 600px; margin: 0 auto;">
            <h2>Password Reset Request</h2>
            <p>You requested a password reset for your {settings.PROJECT_NAME} account.</p>
            <p>Click the link below to reset your password. This link expires in 1 hour.</p>
            <p><a href="{reset_url}" style="display: inline-block; padding: 12px 24px;
                background-color: #4f46e5; color: white; text-decoration: none;
                border-radius: 6px;">Reset Password</a></p>
            <p>If you didn't request this, you can safely ignore this email.</p>
            <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 24px 0;">
            <p style="color: #6b7280; font-size: 12px;">
                This is an automated message from {settings.PROJECT_NAME}.
            </p>
        </body>
        </html>
        """
        text_body = (
            f"Password Reset Request\n\n"
            f"You requested a password reset for your {settings.PROJECT_NAME} account.\n\n"
            f"Visit this link to reset your password (expires in 1 hour):\n{reset_url}\n\n"
            f"If you didn't request this, you can safely ignore this email."
        )

        self._send_email(to_email, subject, html_body, text_body)

    def _send_email(self, to: str, subject: str, html_body: str, text_body: str) -> None:
        """Send an email via SMTP, or log it if SMTP is not configured."""
        if not settings.SMTP_HOST:
            logger.info(f"[DEV] Email to {to}: {subject}")
            logger.info(f"[DEV] Body: {text_body}")
            return

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = settings.SMTP_FROM
        msg["To"] = to
        msg.attach(MIMEText(text_body, "plain"))
        msg.attach(MIMEText(html_body, "html"))

        try:
            if settings.SMTP_USE_TLS:
                server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT)
                server.ehlo()
                server.starttls()
            else:
                server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT)

            if settings.SMTP_USER:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)

            server.sendmail(settings.SMTP_FROM, [to], msg.as_string())
            server.quit()
            logger.info(f"Password reset email sent to {to}")
        except Exception as e:
            logger.error(f"Failed to send email to {to}: {e}")
            # Log the reset URL as fallback so user isn't locked out
            logger.info(f"[FALLBACK] Email to {to}: {subject}")
            logger.info(f"[FALLBACK] Body: {text_body}")


email_service = EmailService()
