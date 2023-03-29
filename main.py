import logging

import uvicorn
from fastapi import FastAPI
import firebase_admin
from firebase_admin import credentials

from api.inventory_api import inventory_apis
from api.user_api import user_apis
from config import LogConfig
from models.db import create_db_and_tables

logging.config.dictConfig(LogConfig().dict())
logger = logging.getLogger("groceror")

app = FastAPI(debug=False)
app.logger = logger

cred = credentials.Certificate("firebase_service_account.json")
firebase_admin.initialize_app(cred)


@app.get("/")
async def welcome():
    logger.info("Welcome to Groceror!")
    return "Welcome to Groceror!"


app.mount("/user", user_apis)
app.mount("/inventory", inventory_apis)

create_db_and_tables()

if __name__ == "__main__":
    uvicorn.run(app, port=8009)
