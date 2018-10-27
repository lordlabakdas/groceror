from flask import Blueprint,jsonify
import googlemaps
from conf.config import Config
import requests
from pprint import pprint

owner_apis = Blueprint("owner_apis", __name__)

gmaps = googlemaps.Client(key=Config.google_maps_api_key)


@owner_apis.route("/home")
def home():
    return "owner apis"


@owner_apis.route("/nearby-stores")
def nearby_groceries():
    params = {"key": Config.google_maps_api_key,
              "location": Config.coords,
              "rankby": "distance",
              "keyword": "grocery"}
    response = requests.get(
        "https://maps.googleapis.com/maps/api/place/nearbysearch/json", params=params)
    pprint(response.json(), stream=None, indent=2, width=80, depth=None)
    return jsonify(response.json())
