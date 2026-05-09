"""Factory page routes.

Transition-ready page module. Register only after matching inline factory page
routes are removed from app.py.
"""

from __future__ import annotations

from typing import Any, Callable

from flask import render_template


HasUidFlag = Callable[[], bool]


def register_factory_page_routes(app: Any, has_uid_flag: HasUidFlag) -> None:
    """Register factory page routes."""

    @app.route("/factories")
    def factories_page():
        return render_template(
            "pages/factories.html",
            title="Factories",
            has_uid=has_uid_flag(),
        )
