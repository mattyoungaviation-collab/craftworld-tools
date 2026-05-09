"""Core page route wrappers."""

from __future__ import annotations

from typing import Any

from craftworld_tools.routes.pages_core import boosts, craft_profitability, dashboard, masterpieces_view, profitability


def register_core_page_legacy_routes(app: Any) -> None:
    """Register core page endpoints."""

    app.route("/dashboard", methods=["GET"])(dashboard)
    app.route("/boosts", methods=["GET", "POST"])(boosts)
    app.route("/profitability", methods=["GET", "POST"])(profitability)
    app.route("/craft-profitability", methods=["GET"])(craft_profitability)
    app.route("/masterpieces", methods=["GET", "POST"])(masterpieces_view)
