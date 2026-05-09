"""Lookup page route wrappers.

Transition module for existing read-only lookup pages. During this phase,
app.py keeps the legacy function bodies, but this module owns the Flask route
registration.
"""

from __future__ import annotations

from typing import Any


def register_lookup_page_legacy_routes(app: Any) -> None:
    """Register lookup page endpoints and delegate to legacy handlers."""

    @app.route("/inventory", methods=["GET"])
    def inventory_view():
        import app as legacy_app
        return legacy_app.inventory_view()

    @app.route("/mastery", methods=["GET"])
    def mastery_view():
        import app as legacy_app
        return legacy_app.mastery_view()

    @app.route("/resource/<token>", methods=["GET"])
    def resource_view(token: str):
        import app as legacy_app
        return legacy_app.resource_view(token)

    @app.route("/player/<uid>", methods=["GET"])
    def player_view(uid: str):
        import app as legacy_app
        return legacy_app.player_view(uid)
