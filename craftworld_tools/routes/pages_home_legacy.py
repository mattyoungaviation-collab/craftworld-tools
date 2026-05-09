"""Home page route wrapper.

Transition module for the existing root page. During this phase, app.py keeps
the legacy function body, but this module owns the Flask route registration.
"""

from __future__ import annotations

from typing import Any


def register_home_page_legacy_routes(app: Any) -> None:
    """Register home/root endpoint and delegate to legacy handler."""

    @app.route("/", methods=["GET", "POST"])
    def index():
        import app as legacy_app
        return legacy_app.index()
