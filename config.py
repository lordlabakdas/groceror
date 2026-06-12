import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar, Dict

import yaml

# Load .config.yml if present (local dev). On Render (and other cloud envs)
# the file won't exist — config comes from environment variables instead.
_cfg_path = Path(".config.yml")
_file: dict = yaml.safe_load(_cfg_path.read_text()) if _cfg_path.exists() else {}


def _cfg(*keys: str, env: str = None, default: str = "") -> str:
    """Return config value: env var > .config.yml > default."""
    if env and os.environ.get(env):
        return os.environ[env]
    val: Any = _file
    for k in keys:
        val = (val or {}).get(k)
        if val is None:
            return default
    return val or default


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
    """Database configuration — prefers DATABASE_URL env var (Render/Supabase),
    falls back to individual fields from .config.yml for local dev."""

    DB_URL: ClassVar[str] = os.environ.get("DATABASE_URL") or (
        "postgresql://"
        f"{_cfg('groceror', 'db', 'DB_USER')}:{_cfg('groceror', 'db', 'DB_PASSWORD')}"
        f"@{_cfg('groceror', 'db', 'DB_HOST')}:{_cfg('groceror', 'db', 'DB_PORT')}"
        f"/{_cfg('groceror', 'db', 'DB_NAME')}"
    )


@dataclass
class JWTConfig(object):
    """JWT related configuration"""

    JWT_ALGORITHM: ClassVar[str] = _cfg(
        "groceror", "jwt", "JWT_ALGORITHM", env="JWT_ALGORITHM", default="HS256"
    )
    JWT_SECRET_KEY: ClassVar[str] = _cfg(
        "groceror", "jwt", "JWT_SECRET_KEY", env="JWT_SECRET_KEY"
    )


@dataclass
class TwilioConfig(object):
    """Twilio SMS configuration"""

    ACCOUNT_SID: ClassVar[str] = _cfg(
        "groceror", "twilio", "account_sid", env="TWILIO_ACCOUNT_SID"
    )
    AUTH_TOKEN: ClassVar[str] = _cfg(
        "groceror", "twilio", "auth_token", env="TWILIO_AUTH_TOKEN"
    )
    FROM_NUMBER: ClassVar[str] = _cfg(
        "groceror", "twilio", "from_number", env="TWILIO_FROM_NUMBER"
    )


@dataclass
class RabbitMQConfig(object):
    """RabbitMQ connection configuration"""

    HOST: ClassVar[str] = _cfg(
        "groceror", "rabbitmq", "host", env="RABBITMQ_HOST", default="localhost"
    )
    PORT: ClassVar[int] = int(
        _cfg("groceror", "rabbitmq", "port", env="RABBITMQ_PORT", default="5672")
    )
    USER: ClassVar[str] = _cfg(
        "groceror", "rabbitmq", "user", env="RABBITMQ_USER", default="guest"
    )
    PASSWORD: ClassVar[str] = _cfg(
        "groceror", "rabbitmq", "password", env="RABBITMQ_PASSWORD", default="guest"
    )
    VHOST: ClassVar[str] = _cfg(
        "groceror", "rabbitmq", "virtual_host", env="RABBITMQ_VHOST", default="/"
    )
