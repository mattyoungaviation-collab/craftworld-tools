"""Boost settings page routes.

Transition-ready page module. Register only after the matching inline boosts
route is removed from app.py.
"""

from __future__ import annotations

from typing import Any, Callable

from flask import render_template


HasUidFlag = Callable[[], bool]


def register_boost_page_routes(app: Any, has_uid_flag: HasUidFlag) -> None:
    """Register boost page routes."""

    @app.route("/boosts")
    def boosts():
        return render_template(
            "pages/boosts.html",
            title="Boosts",
            has_uid=has_uid_flag(),
        )
