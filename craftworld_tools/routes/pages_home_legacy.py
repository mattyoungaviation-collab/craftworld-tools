"""Home page route wrapper."""

from __future__ import annotations

from typing import Any

import craftworld_tools.routes.pages_home as pages_home
from craftworld_tools.routes.legacy_globals import inject_app_globals


def index():
    inject_app_globals(pages_home)
    return pages_home.index()


def register_home_page_legacy_routes(app: Any) -> None:
    """Register home/root endpoint."""

    app.route("/", methods=["GET", "POST"])(index)
