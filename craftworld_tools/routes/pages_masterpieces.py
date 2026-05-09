"""Masterpiece page routes.

Transition-ready page module. Register only after matching inline Masterpiece
page routes are removed from app.py.
"""

from __future__ import annotations

from typing import Any, Callable

from flask import render_template


HasUidFlag = Callable[[], bool]


def register_masterpiece_page_routes(app: Any, has_uid_flag: HasUidFlag) -> None:
    """Register Masterpiece page routes."""

    @app.route("/masterpieces")
    def masterpieces_page():
        return render_template(
            "pages/masterpieces.html",
            title="Masterpieces",
            has_uid=has_uid_flag(),
        )
