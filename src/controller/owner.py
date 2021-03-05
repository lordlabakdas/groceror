import json

from flask import Blueprint, Response, request
from flask_jwt_extended import jwt_required, create_access_token, get_jwt_identity
from flask_api import status as HTTP_STATUS_CODE

import googlemaps

from conf.config import Config
from data_models.service.owner_registration import OwnerRegistration


owner_apis = Blueprint("owner_apis", __name__, url_prefix='/owner')

gmaps = googlemaps.Client(key=Config.google_maps_api_key)


@owner_apis.route("/home")
def home():
    return "owner apis"


@owner_apis.route("/register", methods=["POST"])
def register():
    register_params = request.json
    owner_registration_obj = OwnerRegistration()
    owner_registration_obj.register_owner(register_params)
    return Response(
        response="Inventory added",
        status=HTTP_STATUS_CODE.HTTP_200_OK,
        mimetype="application/json",
    )


@owner_apis.route("/login")
def login():
    if "phone" in request.json:
        owner_registration_obj = OwnerRegistration()
        is_owner_registered = owner_registration_obj.check_if_owner_registered(request.json["phone"])
        if not is_owner_registered:
            print("User does not exist")
            return Response(json.dumps({"user_id": None}), status=HTTP_STATUS_CODE.HTTP_403_FORBIDDEN, mimetype='application/json')
        else:
            registered_owner_obj = owner_registration_obj.get_registered_user(request.json["phone"])
            is_user_authenticated = registered_owner_obj.check_password(request.json["password"])
            if is_user_authenticated:
                access_token = create_access_token(identity=registered_owner_obj.id, expires_delta=False)
                return Response(json.dumps({**registered_owner_obj.get_user_profile(), **{"access_token": access_token}}), status=HTTP_STATUS_CODE.HTTP_200_OK, mimetype='application/json')
            else:
                print("Password is incorrect")
                return Response(json.dumps({"user_id": None}), status=HTTP_STATUS_CODE.HTTP_403_FORBIDDEN, mimetype='application/json')
    else:
        return Response(json.dumps({"user_id": None}), status=HTTP_STATUS_CODE.HTTP_404_NOT_FOUND, mimetype='application/json')


# @owner_apis.route("/nearby-stores")
# def nearby_groceries():
#     params = {
#         "key": Config.google_maps_api_key,
#         "location": Config.coords,
#         "rankby": "distance",
#         "keyword": "grocery",
#     }
#     response = requests.get(
#         "https://maps.googleapis.com/maps/api/place/nearbysearch/json", params=params
#     )
#     pprint(response.json(), stream=None, indent=2, width=80, depth=None)
#     return jsonify(response.json())


@owner_apis.route("/modify-price", methods=["POST"])
def modify_price():
    params = request.json
    return Response(
        response="Price adjusted", status=HTTP_STATUS_CODE.HTTP_200_OK, mimetype=None
    )


@owner_apis.route("modify-inventory", methods=["POST"])
def add_inventory():
    params = request.json
    return Response(
        response="Inventory added",
        status=HTTP_STATUS_CODE.HTTP_200_OK,
        mimetype="application/json",
    )
