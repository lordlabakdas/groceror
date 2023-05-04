import logging

import firebase_admin
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from firebase_admin import credentials
from api import firebase_api

from api.inventory_api import inventory_apis
from api.user_api import user_apis
from api.google_login import google_login_apis
from config import LogConfig
from models.db import create_db_and_tables

logging.config.dictConfig(LogConfig().dict())
logger = logging.getLogger("groceror")

app = FastAPI(debug=False)
app.logger = logger

# Allow requests from any origin
origins = ["*"]

# Add the CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


cred = credentials.Certificate("firebase_service_account.json")
firebase_admin.initialize_app(cred)


@app.get("/")
async def welcome():
    logger.info("Welcome to Groceror!")
    return "Welcome to Groceror!"


app.include_router(user_apis, prefix="/user")
app.include_router(firebase_api, prefix="/firebase")
app.include_router(google_login_apis, prefix="/google")
app.include_router(inventory_apis, prefix="/inventory")

create_db_and_tables()

if __name__ == "__main__":
    uvicorn.run(app, port=8009)
