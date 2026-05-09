"""Simple page route wrappers."""

from __future__ import annotations

from typing import Any

from craftworld_tools.routes.pages_simple import charts, privacy, terms, trees


def register_simple_page_legacy_routes(app: Any) -> None:
    """Register simple page endpoints."""

    app.route("/privacy", methods=["GET"])(privacy)
    app.route("/terms", methods=["GET"])(terms)
    app.route("/charts", methods=["GET"])(charts)
    app.route("/trees", methods=["GET"])(trees)
