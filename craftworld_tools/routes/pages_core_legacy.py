"""Core page route wrappers."""

from __future__ import annotations

from typing import Any

import craftworld_tools.routes.pages_core as pages_core
from craftworld_tools.routes.legacy_globals import inject_app_globals


def dashboard():
    inject_app_globals(pages_core)
    return pages_core.dashboard()


def boosts():
    inject_app_globals(pages_core)
    return pages_core.boosts()


def profitability():
    inject_app_globals(pages_core)
    return pages_core.profitability()


def craft_profitability():
    inject_app_globals(pages_core)
    return pages_core.craft_profitability()


def masterpieces_view():
    inject_app_globals(pages_core)
    return pages_core.masterpieces_view()


def register_core_page_legacy_routes(app: Any) -> None:
    """Register core page endpoints."""

    app.route("/dashboard", methods=["GET"])(dashboard)
    app.route("/boosts", methods=["GET", "POST"])(boosts)
    app.route("/profitability", methods=["GET", "POST"])(profitability)
    app.route("/craft-profitability", methods=["GET"])(craft_profitability)
    app.route("/masterpieces", methods=["GET", "POST"])(masterpieces_view)
