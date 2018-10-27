from flask import Flask, request, jsonify
from controller.owner import owner_apis
from configparser import ConfigParser


owner = Flask(__name__)

# owner.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# owner.config['SQLALCHEMY_DATABASE_URI'] = "mysql+pymysql://" + DB_USERNAME + ":" + DB_PASSWORD + "@" + DB_HOST + "/" + DB_DATABASE

owner.register_blueprint(owner_apis)


@owner.route("/")
def welcome():
    return "Welcome to Grocerer!"


if __name__ == "__main__":
    owner.debug = True
    owner.run(host="127.0.0.1", port=5000)
