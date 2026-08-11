"""Direct email sending via Resend.

Replaces the previous flow of publishing to RabbitMQ's ``email_queue`` for
the standalone groceror-email service to consume — email is now just
another in-process side effect of the monolith.
"""

import logging

import resend

from config import EmailConfig

logger = logging.getLogger(__name__)


class Mailer:
    def send(self, recipient: str, subject: str, body: str) -> None:
        resend.api_key = EmailConfig.RESEND_API_KEY
        resend.Emails.send({
            "from": EmailConfig.MAIL_FROM,
            "to": recipient,
            "subject": subject,
            "text": body,
        })
        logger.info("Email sent to %s subject=%r", recipient, subject)
