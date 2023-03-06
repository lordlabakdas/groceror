import logging

import uvicorn
from fastapi import FastAPI

from api.user import user_apis
from config import LogConfig
from models.db import create_db_and_tables

logging.config.dictConfig(LogConfig().dict())
logger = logging.getLogger("groceror")

app = FastAPI(debug=False)
app.logger = logger


@app.get("/")
async def welcome():
    logger.info("Welcome to Groceror!")
    return "Welcome to Groceror!"


app.mount("/user", user_apis)
create_db_and_tables()

if __name__ == "__main__":
    uvicorn.run(app, port=8009)
