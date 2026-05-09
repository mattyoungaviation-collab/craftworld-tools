"""Core page route wrappers.

Transition module for larger existing pages. During this phase, app.py keeps the
legacy function bodies, but this module owns the Flask route registration.
"""

from __future__ import annotations

from typing import Any


def register_core_page_legacy_routes(app: Any) -> None:
    """Register core page endpoints and delegate to legacy handlers."""

    @app.route("/dashboard", methods=["GET"])
    def dashboard():
        import app as legacy_app
        return legacy_app.dashboard()

    @app.route("/boosts", methods=["GET", "POST"])
    def boosts():
        import app as legacy_app
        return legacy_app.boosts()

    @app.route("/profitability", methods=["GET", "POST"])
    def profitability():
        import app as legacy_app
        return legacy_app.profitability()

    @app.route("/craft-profitability", methods=["GET"])
    def craft_profitability():
        import app as legacy_app
        return legacy_app.craft_profitability()

    @app.route("/masterpieces", methods=["GET", "POST"])
    def masterpieces_view():
        import app as legacy_app
        return legacy_app.masterpieces_view()
