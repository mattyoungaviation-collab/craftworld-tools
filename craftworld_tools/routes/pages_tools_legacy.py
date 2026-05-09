"""Tool page route wrappers.

Transition module for existing calculation/tool pages. During this phase,
app.py keeps the legacy function bodies, but this module owns the Flask route
registration.
"""

from __future__ import annotations

from typing import Any


def register_tool_page_legacy_routes(app: Any) -> None:
    """Register tool page endpoints and delegate to legacy handlers."""

    @app.route("/calculate", methods=["GET", "POST"])
    def calculate():
        import app as legacy_app
        return legacy_app.calculate()

    @app.route("/upgrade-calculate", methods=["GET", "POST"])
    def upgrade_calculate():
        import app as legacy_app
        return legacy_app.upgrade_calculate()

    @app.route("/factory-converter", methods=["GET", "POST"])
    def factory_converter():
        import app as legacy_app
        return legacy_app.factory_converter()

    @app.route("/flex", methods=["GET", "POST"])
    def flex_planner():
        import app as legacy_app
        return legacy_app.flex_planner()

    @app.route("/snipe", methods=["GET", "POST"])
    def snipe():
        import app as legacy_app
        return legacy_app.snipe()
