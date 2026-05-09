"""Boost API route wrappers."""

from __future__ import annotations

from typing import Any

import craftworld_tools.routes.api_boosts as api_boosts
from craftworld_tools.routes.legacy_globals import inject_app_globals


def api_boosts_mastery():
    inject_app_globals(api_boosts)
    return api_boosts.api_boosts_mastery()


def api_boosts_sync():
    inject_app_globals(api_boosts)
    return api_boosts.api_boosts_sync()


def register_boosts_legacy_routes(app: Any) -> None:
    """Register boost API endpoints."""

    app.route("/api/boosts/mastery", methods=["POST"])(api_boosts_mastery)
    app.route("/api/boosts/sync", methods=["POST"])(api_boosts_sync)
