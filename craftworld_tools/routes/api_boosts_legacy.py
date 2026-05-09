"""Boost API route wrappers.

Transition module for existing boost endpoints. During this phase, app.py keeps
the legacy function bodies, but this module owns the Flask route registration.
"""

from __future__ import annotations

from typing import Any


def register_boosts_legacy_routes(app: Any) -> None:
    """Register boost API endpoints and delegate to legacy handlers."""

    @app.route("/api/boosts/mastery", methods=["POST"])
    def api_boosts_mastery():
        import app as legacy_app
        return legacy_app.api_boosts_mastery()

    @app.route("/api/boosts/sync", methods=["POST"])
    def api_boosts_sync():
        import app as legacy_app
        return legacy_app.api_boosts_sync()
