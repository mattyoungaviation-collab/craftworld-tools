"""Tool page route wrappers."""

from __future__ import annotations

from typing import Any

from craftworld_tools.routes.pages_tools import calculate, factory_converter, flex_planner, snipe, upgrade_calculate


def register_tool_page_legacy_routes(app: Any) -> None:
    """Register tool page endpoints."""

    app.route("/calculate", methods=["GET", "POST"])(calculate)
    app.route("/upgrade-calculate", methods=["GET", "POST"])(upgrade_calculate)
    app.route("/factory-converter", methods=["GET", "POST"])(factory_converter)
    app.route("/flex", methods=["GET", "POST"])(flex_planner)
    app.route("/snipe", methods=["GET", "POST"])(snipe)
