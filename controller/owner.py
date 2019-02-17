from flask import Blueprint, Response, request
import googlemaps
from conf.config import Config
from flask_api import status as HTTP_STATUS_CODE
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
    return "Logged in"

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
