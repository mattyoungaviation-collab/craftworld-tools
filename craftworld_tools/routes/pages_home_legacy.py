"""Home page route wrapper."""

from __future__ import annotations

from typing import Any

from craftworld_tools.routes.pages_home import index


def register_home_page_legacy_routes(app: Any) -> None:
    """Register home/root endpoint."""

    app.route("/", methods=["GET", "POST"])(index)
