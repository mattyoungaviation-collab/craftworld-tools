"""Profitability page routes.

Transition-ready page module. Register only after the matching inline
profitability route is removed from app.py.
"""

from __future__ import annotations

from typing import Any, Callable

from flask import render_template


HasUidFlag = Callable[[], bool]


def register_profitability_page_routes(app: Any, has_uid_flag: HasUidFlag) -> None:
    """Register profitability page routes."""

    @app.route("/profitability")
    def profitability_page():
        return render_template(
            "pages/profitability.html",
            title="Profitability",
            has_uid=has_uid_flag(),
        )
