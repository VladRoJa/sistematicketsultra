import os
from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required

pm_bp = Blueprint("pm", __name__)

@pm_bp.route("/mobile/ping", methods=["GET"])
@jwt_required()
def pm_mobile_ping():
    return jsonify({"ok": True, "module": "pm", "mobile": True}), 200