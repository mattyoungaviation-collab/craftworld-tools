"""Masterpiece JSON API routes.

Transition-ready route module for Masterpiece data endpoints. Register only
after matching inline routes are removed from app.py.
"""

from __future__ import annotations

from typing import Any

from flask import jsonify, request

from craftworld_tools.services.craftworld import fetch_masterpiece_details, fetch_masterpieces, predict_reward
from craftworld_tools.services.masterpiece_cache import cache_masterpiece_metadata, load_masterpiece_metadata_cache


def register_masterpiece_api_routes(app: Any) -> None:
    """Register Masterpiece JSON routes."""

    @app.route("/api/masterpieces", methods=["GET"])
    def api_masterpieces():
        masterpieces = fetch_masterpieces()
        for mp in masterpieces:
            cache_masterpiece_metadata(mp)
        return jsonify({"ok": True, "masterpieces": masterpieces})

    @app.route("/api/masterpieces/cache", methods=["GET"])
    def api_masterpieces_cache():
        return jsonify({"ok": True, "cache": load_masterpiece_metadata_cache()})

    @app.route("/api/masterpieces/<int:masterpiece_id>", methods=["GET"])
    def api_masterpiece_details(masterpiece_id: int):
        details = fetch_masterpiece_details(masterpiece_id)
        if details:
            cache_masterpiece_metadata(details)
        return jsonify({"ok": bool(details), "masterpiece": details})

    @app.route("/api/masterpieces/<int:masterpiece_id>/predict", methods=["POST"])
    def api_masterpiece_predict(masterpiece_id: int):
        data = request.get_json(silent=True) or {}
        resources = data.get("resources") or []
        if not isinstance(resources, list):
            return jsonify({"ok": False, "error": "resources must be a list."}), 400
        prediction = predict_reward(masterpiece_id, resources)
        return jsonify({"ok": True, "prediction": prediction})
