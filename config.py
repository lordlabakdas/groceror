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
class RabbitMQConfig(object):
    """RabbitMQ connection configuration"""

    HOST: ClassVar[str] = _env("RABBITMQ_HOST", "localhost")
    PORT: ClassVar[int] = int(_env("RABBITMQ_PORT", "5672"))
    USER: ClassVar[str] = _env("RABBITMQ_USER", "guest")
    PASSWORD: ClassVar[str] = _env("RABBITMQ_PASSWORD", "guest")
    VHOST: ClassVar[str] = _env("RABBITMQ_VIRTUAL_HOST", "/")
