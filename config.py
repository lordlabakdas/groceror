from dataclasses import dataclass
from typing import ClassVar, Dict, Any

import yaml


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


CONFIG = yaml.safe_load(open(".config.yml"))


@dataclass
class DBConfig(object):
    """Database configuration to be set for the server"""

    DB_USER = CONFIG.get("groceror").get("db").get("DB_USER")
    DB_PASSWORD = CONFIG.get("groceror").get("db").get("DB_PASSWORD")
    DB_HOST = CONFIG.get("groceror").get("db").get("DB_HOST")
    DB_PORT = CONFIG.get("groceror").get("db").get("DB_PORT")
    DB_NAME = CONFIG.get("groceror").get("db").get("DB_NAME")
    DB_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"


@dataclass
class JWTConfig(object):
    """JWT related configuration"""

    JWT_ALGORITHM = CONFIG.get("groceror").get("jwt").get("JWT_ALGORITHM")
    JWT_SECRET_KEY = CONFIG.get("groceror").get("jwt").get("JWT_SECRET_KEY")


@dataclass
class TwilioConfig(object):
    """Twilio SMS configuration"""

    _twilio = CONFIG.get("groceror").get("twilio", {})
    ACCOUNT_SID = _twilio.get("account_sid", "")
    AUTH_TOKEN  = _twilio.get("auth_token", "")
    FROM_NUMBER = _twilio.get("from_number", "")


@dataclass
class RabbitMQConfig(object):
    """RabbitMQ connection configuration"""

    _rmq = CONFIG.get("groceror").get("rabbitmq", {})
    HOST     = _rmq.get("host", "localhost")
    PORT     = int(_rmq.get("port", 5672))
    USER     = _rmq.get("user", "guest")
    PASSWORD = _rmq.get("password", "guest")
    VHOST    = _rmq.get("virtual_host", "/")
