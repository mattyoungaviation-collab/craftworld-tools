"""Tool page route wrappers."""

from __future__ import annotations

from typing import Any

import craftworld_tools.routes.pages_tools as pages_tools
from craftworld_tools.routes.legacy_globals import inject_app_globals


def calculate():
    inject_app_globals(pages_tools)
    return pages_tools.calculate()


def upgrade_calculate():
    inject_app_globals(pages_tools)
    return pages_tools.upgrade_calculate()


def factory_converter():
    inject_app_globals(pages_tools)
    return pages_tools.factory_converter()


def flex_planner():
    inject_app_globals(pages_tools)
    return pages_tools.flex_planner()


def snipe():
    inject_app_globals(pages_tools)
    return pages_tools.snipe()


def register_tool_page_legacy_routes(app: Any) -> None:
    """Register tool page endpoints."""

    app.route("/calculate", methods=["GET", "POST"])(calculate)
    app.route("/upgrade-calculate", methods=["GET", "POST"])(upgrade_calculate)
    app.route("/factory-converter", methods=["GET", "POST"])(factory_converter)
    app.route("/flex", methods=["GET", "POST"])(flex_planner)
    app.route("/snipe", methods=["GET", "POST"])(snipe)
