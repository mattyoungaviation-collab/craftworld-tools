"""Simple page route wrappers.

Transition module for simple existing pages. During this phase, app.py keeps the
legacy function bodies, but this module owns the Flask route registration.
"""

from __future__ import annotations

from typing import Any


def register_simple_page_legacy_routes(app: Any) -> None:
    """Register simple page endpoints and delegate to legacy handlers."""

    @app.route("/privacy", methods=["GET"])
    def privacy():
        import app as legacy_app
        return legacy_app.privacy()

    @app.route("/terms", methods=["GET"])
    def terms():
        import app as legacy_app
        return legacy_app.terms()

    @app.route("/charts", methods=["GET"])
    def charts():
        import app as legacy_app
        return legacy_app.charts()

    @app.route("/trees", methods=["GET"])
    def trees():
        import app as legacy_app
        return legacy_app.trees()
