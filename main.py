import logging
import sys

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.security import OAuth2PasswordBearer
from loguru import logger

from api.google_login import google_login_apis
from api.inventory_api import inventory_apis
from api.store_api import store_apis
from api.user_api import user_apis
from api.cart_api import cart_apis
from models.db import create_db_and_tables

logger.add(
    sys.stderr, format="{time} {level} {message}", filter="my_module", level="INFO"
)
logger.add("file_{time}.log")
logger.add(
    sys.stdout, colorize=True, format="<green>{time}</green> <level>{message}</level>"
)
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

# cred = credentials.Certificate("firebase_service_account.json")
# firebase_admin.initialize_app(cred)


@app.get("/")
async def welcome():
    logger.info("Welcome to Groceror!")
    return "Welcome to Groceror!"


app.include_router(user_apis, prefix="/user")
# app.include_router(firebase_api, prefix="/firebase")
app.include_router(google_login_apis, prefix="/google")
app.include_router(inventory_apis, prefix="/inventory")
app.include_router(store_apis, prefix="/store")
app.include_router(cart_apis, prefix="/cart")

create_db_and_tables()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title="Groceror API",
        version="1.0.0",
        description="Groceror API",
        routes=app.routes,
    )
    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "Enter your JWT token in the format: Bearer <token>",
        }
    }
    for path in openapi_schema["paths"].values():
        for method in path.values():
            method.setdefault("security", []).append({"BearerAuth": []})
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi

if __name__ == "__main__":
    uvicorn.run(app, port=8000)
