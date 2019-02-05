from flask import Blueprint, Response, request, jsonify
import googlemaps
from conf.config import Config
import requests
from pprint import pprint
from flask_api import status as HTTP_STATUS_CODE


owner_apis = Blueprint("owner_apis", __name__)

gmaps = googlemaps.Client(key=Config.google_maps_api_key)


@owner_apis.route("/home")
def home():
    return "owner apis"


@owner_apis.route("/nearby-stores")
def nearby_groceries():
    params = {
        "key": Config.google_maps_api_key,
        "location": Config.coords,
        "rankby": "distance",
        "keyword": "grocery",
    }
    response = requests.get(
        "https://maps.googleapis.com/maps/api/place/nearbysearch/json", params=params
    )
    pprint(response.json(), stream=None, indent=2, width=80, depth=None)
    return jsonify(response.json())


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
