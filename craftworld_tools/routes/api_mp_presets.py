"""Masterpiece preset JSON API routes.

This module is transition-ready. It can be registered from app.py after the
existing inline Masterpiece preset routes are removed.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from flask import jsonify, request, session

from craftworld_tools.services.mp_presets import (
    create_mp_preset,
    delete_mp_preset,
    get_mp_preset,
    list_mp_presets,
    update_mp_preset,
)


RequireLogin = Callable[[], Optional[Any]]


def _current_user_id() -> Optional[int]:
    user_id = session.get("user_id")
    if not user_id:
        return None
    try:
        return int(user_id)
    except (TypeError, ValueError):
        return None


def _parse_optional_int(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def register_mp_preset_api_routes(app: Any, require_login: Optional[RequireLogin] = None) -> None:
    """Register Masterpiece preset JSON routes."""

    def _auth_error_response():
        if require_login is not None:
            response = require_login()
            if response is not None:
                return response
        if _current_user_id() is None:
            return jsonify({"ok": False, "error": "Login required."}), 401
        return None

    @app.route("/api/mp_presets", methods=["GET"])
    def api_list_mp_presets():
        auth_error = _auth_error_response()
        if auth_error is not None:
            return auth_error

        user_id = _current_user_id()
        masterpiece_id = _parse_optional_int(request.args.get("masterpiece_id"))
        presets = list_mp_presets(int(user_id), masterpiece_id=masterpiece_id)
        return jsonify({"ok": True, "presets": presets})

    @app.route("/api/mp_presets", methods=["POST"])
    def api_create_mp_preset():
        auth_error = _auth_error_response()
        if auth_error is not None:
            return auth_error

        user_id = _current_user_id()
        data = request.get_json(silent=True) or {}
        name = str(data.get("name") or "").strip()
        payload = data.get("payload") or {}
        masterpiece_id = _parse_optional_int(data.get("masterpiece_id"))

        if not name:
            return jsonify({"ok": False, "error": "Preset name is required."}), 400
        if not isinstance(payload, dict):
            return jsonify({"ok": False, "error": "Preset payload must be an object."}), 400

        try:
            preset_id = create_mp_preset(
                int(user_id),
                name=name,
                payload=payload,
                masterpiece_id=masterpiece_id,
            )
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

        preset = get_mp_preset(int(user_id), preset_id)
        return jsonify({"ok": True, "preset": preset})

    @app.route("/api/mp_presets/<int:preset_id>", methods=["GET"])
    def api_get_mp_preset(preset_id: int):
        auth_error = _auth_error_response()
        if auth_error is not None:
            return auth_error

        user_id = _current_user_id()
        preset = get_mp_preset(int(user_id), int(preset_id))
        if preset is None:
            return jsonify({"ok": False, "error": "Preset not found."}), 404
        return jsonify({"ok": True, "preset": preset})

    @app.route("/api/mp_presets/<int:preset_id>", methods=["PUT", "PATCH"])
    def api_update_mp_preset(preset_id: int):
        auth_error = _auth_error_response()
        if auth_error is not None:
            return auth_error

        user_id = _current_user_id()
        data = request.get_json(silent=True) or {}
        name = data.get("name") if "name" in data else None
        payload = data.get("payload") if "payload" in data else None
        masterpiece_id = _parse_optional_int(data.get("masterpiece_id")) if "masterpiece_id" in data else None

        if payload is not None and not isinstance(payload, dict):
            return jsonify({"ok": False, "error": "Preset payload must be an object."}), 400

        try:
            updated = update_mp_preset(
                int(user_id),
                int(preset_id),
                name=name,
                payload=payload,
                masterpiece_id=masterpiece_id,
            )
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

        if not updated:
            return jsonify({"ok": False, "error": "Preset not found."}), 404
        preset = get_mp_preset(int(user_id), int(preset_id))
        return jsonify({"ok": True, "preset": preset})

    @app.route("/api/mp_presets/<int:preset_id>", methods=["DELETE"])
    def api_delete_mp_preset(preset_id: int):
        auth_error = _auth_error_response()
        if auth_error is not None:
            return auth_error

        user_id = _current_user_id()
        deleted = delete_mp_preset(int(user_id), int(preset_id))
        if not deleted:
            return jsonify({"ok": False, "error": "Preset not found."}), 404
        return jsonify({"ok": True})
