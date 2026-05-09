"""Boost API route wrappers."""

from __future__ import annotations

from typing import Any

from craftworld_tools.routes.api_boosts import api_boosts_mastery, api_boosts_sync


def register_boosts_legacy_routes(app: Any) -> None:
    """Register boost API endpoints."""

    app.route("/api/boosts/mastery", methods=["POST"])(api_boosts_mastery)
    app.route("/api/boosts/sync", methods=["POST"])(api_boosts_sync)
