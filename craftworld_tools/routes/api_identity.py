"""Craft World identity JSON API routes.

Transition-ready route module for identity/token related endpoints. Register only
after matching inline routes are removed from app.py.
"""

from __future__ import annotations

from typing import Any

from flask import jsonify, request, session

from craftworld_tools.services.identity import resolve_uid_from_token, sign_in_with_custom_token
from craftworld_tools.utils.auth import extract_bearer_token, normalize_cw_token


def _request_token() -> str:
    bearer = extract_bearer_token(request.headers.get("Authorization"))
    if bearer:
        return normalize_cw_token(bearer) or ""
    return normalize_cw_token((request.args.get("cw_idToken") or "").strip()) or ""


def register_identity_api_routes(app: Any) -> None:
    """Register identity/token JSON routes."""

    @app.route("/api/resolve_uid", methods=["GET", "POST"])
    def api_resolve_uid():
        data = request.get_json(silent=True) or {}
        token = _request_token() or normalize_cw_token(data.get("token")) or ""
        if not token:
            return jsonify({"ok": False, "error": "Craft World token is required."}), 400

        result = resolve_uid_from_token(token)
        if result.get("uid"):
            session["voya_uid"] = result["uid"]
        return jsonify({"ok": bool(result.get("uid")), "uid": result.get("uid"), "source": result.get("source")})

    @app.route("/api/sign_in_custom_token", methods=["POST"])
    def api_sign_in_custom_token():
        data = request.get_json(silent=True) or {}
        custom_token = str(data.get("customToken") or data.get("custom_token") or "").strip()
        if not custom_token:
            return jsonify({"ok": False, "error": "customToken is required."}), 400

        result = sign_in_with_custom_token(custom_token)
        body = result.get("body") or {}
        return jsonify({"ok": bool(result.get("ok")), "status_code": result.get("status_code"), "body": body})
