"""Account related JSON API routes.

This module is intentionally written as a registration function instead of a
Blueprint so it can share the existing app.py helper functions during the
transition. Once app.py is fully split, this can become a normal Flask
Blueprint.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from flask import jsonify, request

from craftworld_tools.services.account_status import fetch_account_status_for_token
from craftworld_tools.utils.auth import extract_bearer_token, normalize_cw_token


GetCachedAccountStatus = Callable[[], Dict[str, Any]]


def _get_request_cw_token() -> Optional[str]:
    token = extract_bearer_token(request.headers.get("Authorization"))
    if token:
        return normalize_cw_token(token)
    fallback = (request.args.get("cw_idToken") or "").strip()
    return normalize_cw_token(fallback)


def register_account_api_routes(
    app: Any,
    get_cached_account_status: GetCachedAccountStatus,
) -> None:
    """Register account status JSON routes."""

    @app.route("/api/account_status")
    def api_account_status():
        token = _get_request_cw_token()
        if token:
            payload = fetch_account_status_for_token(token, logger=app.logger)
            return jsonify(payload)

        # Fallback to the existing server/env JWT behavior during transition.
        return jsonify(get_cached_account_status())
