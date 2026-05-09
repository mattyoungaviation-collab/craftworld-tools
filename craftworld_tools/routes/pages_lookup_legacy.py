"""Lookup page route wrappers."""

from __future__ import annotations

from typing import Any

from craftworld_tools.routes.pages_lookup import inventory_view, mastery_view, player_view, resource_view


def register_lookup_page_legacy_routes(app: Any) -> None:
    """Register lookup page endpoints."""

    app.route("/inventory", methods=["GET"])(inventory_view)
    app.route("/mastery", methods=["GET"])(mastery_view)
    app.route("/resource/<token>", methods=["GET"])(resource_view)
    app.route("/player/<uid>", methods=["GET"])(player_view)
