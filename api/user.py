import logging

from fastapi import FastAPI

from api.validators.uservalidation import (RegistrationPayload,
                                           RegistrationResponse)
from models.service.registration import UserRegistration

logger = logging.getLogger("groceror")
user_apis = FastAPI()


@user_apis.post("/register", response_model=RegistrationResponse)
async def register(registration_payload: RegistrationPayload):
    logger.info(f"Registering user with payload: {registration_payload}")
    user_registration_obj = UserRegistration()
    new_user_id = user_registration_obj.register(registration_payload)
    return {"id": new_user_id}
