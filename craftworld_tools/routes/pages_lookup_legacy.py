"""Lookup page route wrappers."""

from __future__ import annotations

from typing import Any

import craftworld_tools.routes.pages_lookup as pages_lookup
from craftworld_tools.routes.legacy_globals import inject_app_globals


def inventory_view():
    inject_app_globals(pages_lookup)
    return pages_lookup.inventory_view()


def mastery_view():
    inject_app_globals(pages_lookup)
    return pages_lookup.mastery_view()


def resource_view(token: str):
    inject_app_globals(pages_lookup)
    return pages_lookup.resource_view(token)


def player_view(uid: str):
    inject_app_globals(pages_lookup)
    return pages_lookup.player_view(uid)


def register_lookup_page_legacy_routes(app: Any) -> None:
    """Register lookup page endpoints."""

    app.route("/inventory", methods=["GET"])(inventory_view)
    app.route("/mastery", methods=["GET"])(mastery_view)
    app.route("/resource/<token>", methods=["GET"])(resource_view)
    app.route("/player/<uid>", methods=["GET"])(player_view)
