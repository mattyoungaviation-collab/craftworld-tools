"""Account data API route wrappers.

Transition module for existing account data endpoints. During this phase,
app.py keeps the legacy function bodies, but this module owns the Flask route
registration.
"""

from __future__ import annotations

from typing import Any


def register_account_data_legacy_routes(app: Any) -> None:
    """Register account data endpoints and delegate to legacy handlers."""

    @app.route("/api/account_uid", methods=["GET"])
    def api_account_uid():
        import app as legacy_app
        return legacy_app.api_account_uid()

    @app.route("/api/account_proficiencies", methods=["GET"])
    def api_account_proficiencies():
        import app as legacy_app
        return legacy_app.api_account_proficiencies()

    @app.route("/api/account_workshop", methods=["GET"])
    def api_account_workshop():
        import app as legacy_app
        return legacy_app.api_account_workshop()
