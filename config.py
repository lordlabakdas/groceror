from dataclasses import dataclass

import yaml
from pydantic import BaseModel


class LogConfig(BaseModel):
    """Logging configuration to be set for the server"""

    LOGGER_NAME: str = "groceror"
    LOG_FORMAT: str = "%(levelprefix)s | %(asctime)s | %(message)s"
    LOG_LEVEL: str = "DEBUG"

    # Logging config
    version = 1
    disable_existing_loggers = False
    formatters = {
        "default": {
            "()": "uvicorn.logging.DefaultFormatter",
            "fmt": LOG_FORMAT,
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    }
    handlers = {
        "default": {
            "formatter": "default",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stderr",
        },
    }
    loggers = {
        LOGGER_NAME: {"handlers": ["default"], "level": LOG_LEVEL},
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
