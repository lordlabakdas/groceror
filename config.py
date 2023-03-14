from dataclasses import dataclass

from dotenv import load_dotenv
from pydantic import BaseModel

ENV_VARS = load_dotenv()


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


@dataclass
class DBConfig(object):
    """Database configuration to be set for the server"""

    DB_USER = ENV_VARS.get("DB_USER")
    DB_PASSWORD = ENV_VARS.get("DB_PASSWORD")
    DB_HOST = ENV_VARS.get("DB_HOST")
    DB_PORT = ENV_VARS.get("DB_PORT")
    DB_NAME = ENV_VARS.get("DB_NAME")
    DB_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"


@dataclass
class JWTConfig(object):
    """JWT related configuration"""

    JWT_ALGORITHM = ENV_VARS.get("JWT_ALGORITHM")
    JWT_SECRET_KEY = ENV_VARS.get("JWT_SECRET_KEY")
