"""Dashboard page routes.

Transition-ready page module. Register only after the matching inline dashboard
route is removed from app.py.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from flask import render_template, session


HasUidFlag = Callable[[], bool]


def register_dashboard_routes(app: Any, has_uid_flag: HasUidFlag) -> None:
    """Register dashboard/home page routes."""

    @app.route("/")
    def index():
        uid: Optional[str] = session.get("voya_uid")
        return render_template(
            "pages/dashboard.html",
            title="Craft World Tools",
            has_uid=has_uid_flag(),
            uid=uid,
        )
