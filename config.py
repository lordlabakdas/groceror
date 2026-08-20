import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar, Dict

from dotenv import load_dotenv

# Load .env if present (local dev). In cloud envs the vars are injected directly.
load_dotenv(Path(__file__).parent / ".env")


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


@dataclass
class LogConfig:
    """Logging configuration to be set for the server"""

    LOGGER_NAME: str = "groceror"
    LOG_FORMAT: str = "%(levelprefix)s | %(asctime)s | %(message)s"
    LOG_LEVEL: str = "DEBUG"

    version: int = 1
    disable_existing_loggers: bool = False
    formatters: Dict[str, Any] = None
    handlers: Dict[str, Any] = None
    loggers: Dict[str, Any] = None

    def __post_init__(self):
        if self.formatters is None:
            self.formatters = {
                "default": {
                    "()": "uvicorn.logging.DefaultFormatter",
                    "fmt": self.LOG_FORMAT,
                    "datefmt": "%Y-%m-%d %H:%M:%S",
                },
            }
        if self.handlers is None:
            self.handlers = {
                "default": {
                    "formatter": "default",
                    "class": "logging.StreamHandler",
                    "stream": "ext://sys.stderr",
                },
            }
        if self.loggers is None:
            self.loggers = {
                self.LOGGER_NAME: {"handlers": ["default"], "level": self.LOG_LEVEL},
            }


@dataclass
class DBConfig(object):
    """Database configuration — prefers DATABASE_URL, falls back to individual fields."""

    DB_URL: ClassVar[str] = _env("DATABASE_URL") or (
        "postgresql://"
        f"{_env('DB_USER')}:{_env('DB_PASSWORD')}"
        f"@{_env('DB_HOST')}:{_env('DB_PORT', '5432')}"
        f"/{_env('DB_NAME', 'postgres')}"
    )


@dataclass
class JWTConfig(object):
    """JWT related configuration"""

    JWT_ALGORITHM: ClassVar[str] = _env("JWT_ALGORITHM", "HS256")
    JWT_SECRET_KEY: ClassVar[str] = _env("JWT_SECRET_KEY")


@dataclass
class TwilioConfig(object):
    """Twilio SMS configuration"""

    ACCOUNT_SID: ClassVar[str] = _env("TWILIO_ACCOUNT_SID")
    AUTH_TOKEN: ClassVar[str] = _env("TWILIO_AUTH_TOKEN")
    FROM_NUMBER: ClassVar[str] = _env("TWILIO_FROM_NUMBER")


@dataclass
class AdminConfig(object):
    ADMIN_TOKEN: ClassVar[str] = _env("ADMIN_TOKEN", "groceror-admin-secret")


@dataclass
class EmailConfig(object):
    """Resend email configuration"""

    RESEND_API_KEY: ClassVar[str] = _env("RESEND_API_KEY")
    MAIL_FROM: ClassVar[str] = _env("MAIL_FROM")


@dataclass
class ShiprocketConfig(object):
    """Shiprocket Quick hyperlocal delivery configuration.

    NOTE: field names/shape are a best guess pending a real Shiprocket Quick
    business account — see SPEC_DELIVERY_DISPATCH.md §3.1. Adjust once real
    credentials and docs are in hand.
    """

    API_KEY: ClassVar[str] = _env("SHIPROCKET_API_KEY")
    API_SECRET: ClassVar[str] = _env("SHIPROCKET_API_SECRET")
    WEBHOOK_SECRET: ClassVar[str] = _env("SHIPROCKET_WEBHOOK_SECRET")
    BASE_URL: ClassVar[str] = _env(
        "SHIPROCKET_BASE_URL", "https://api.shiprocket.in/quick/v1"
    )


@dataclass
class RazorpayConfig(object):
    """Razorpay Subscriptions configuration — credentials only, not the
    price (that's SubscriptionPlan, a DB row an admin can change; see
    SPEC_SUBSCRIPTION.md §3.1, §3.5).

    NOTE: unverified against real Razorpay docs/account — see
    SPEC_SUBSCRIPTION.md §3.4. Adjust once real credentials are in hand.
    """

    KEY_ID: ClassVar[str] = _env("RAZORPAY_KEY_ID")
    KEY_SECRET: ClassVar[str] = _env("RAZORPAY_KEY_SECRET")
    WEBHOOK_SECRET: ClassVar[str] = _env("RAZORPAY_WEBHOOK_SECRET")
