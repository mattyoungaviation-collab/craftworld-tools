"""Crafting planner page routes.

Transition-ready page module. Register only after the matching inline crafting
route is removed from app.py.
"""

from __future__ import annotations

from typing import Any, Callable

from flask import render_template


HasUidFlag = Callable[[], bool]


def register_crafting_page_routes(app: Any, has_uid_flag: HasUidFlag) -> None:
    """Register crafting planner page routes."""

    @app.route("/crafting")
    def crafting_page():
        return render_template(
            "pages/crafting.html",
            title="Crafting Planner",
            has_uid=has_uid_flag(),
        )
