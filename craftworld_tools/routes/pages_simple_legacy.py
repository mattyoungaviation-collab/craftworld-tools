"""Simple page route wrappers."""

from __future__ import annotations

from typing import Any

import craftworld_tools.routes.pages_simple as pages_simple
from craftworld_tools.routes.legacy_globals import inject_app_globals


def privacy():
    inject_app_globals(pages_simple)
    return pages_simple.privacy()


def terms():
    inject_app_globals(pages_simple)
    return pages_simple.terms()


def charts():
    inject_app_globals(pages_simple)
    return pages_simple.charts()


def trees():
    inject_app_globals(pages_simple)
    return pages_simple.trees()


def register_simple_page_legacy_routes(app: Any) -> None:
    """Register simple page endpoints."""

    app.route("/privacy", methods=["GET"])(privacy)
    app.route("/terms", methods=["GET"])(terms)
    app.route("/charts", methods=["GET"])(charts)
    app.route("/trees", methods=["GET"])(trees)
