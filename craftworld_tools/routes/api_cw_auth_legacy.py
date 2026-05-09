"""Craft World auth API route wrappers.

Transition module for existing Craft World auth endpoints. During this phase,
app.py keeps the legacy function bodies, but this module owns the Flask route
registration. That lets us remove route decorators from app.py without changing
endpoint behavior yet.
"""

from __future__ import annotations

from typing import Any


def register_cw_auth_legacy_routes(app: Any) -> None:
    """Register Craft World auth endpoints and delegate to legacy handlers."""

    @app.route("/api/cw/get_nonce", methods=["POST"])
    def api_cw_get_nonce():
        import app as legacy_app
        return legacy_app.api_cw_get_nonce()

    @app.route("/api/cw/login_for_custom_token", methods=["POST"])
    def api_cw_login_for_custom_token():
        import app as legacy_app
        return legacy_app.api_cw_login_for_custom_token()

    @app.route("/api/cw/signin_with_custom_token", methods=["POST"])
    def api_cw_signin_with_custom_token():
        import app as legacy_app
        return legacy_app.api_cw_signin_with_custom_token()
