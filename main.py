import logging

import uvicorn
from fastapi import FastAPI

from api.user import user_apis
from config import LogConfig

logging.config.dictConfig(LogConfig().dict())
logger = logging.getLogger("groceror")

app = FastAPI(debug=False)
app.logger = logger


@app.get("/")
async def welcome():
    logger.info("Welcome to Groceror!")
    return "Welcome to Groceror!"


app.mount("/user", user_apis)

if __name__ == "__main__":
    uvicorn.run(app, port=8009)
