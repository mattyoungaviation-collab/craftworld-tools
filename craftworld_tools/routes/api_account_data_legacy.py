"""Account data API route wrappers."""

from __future__ import annotations

from typing import Any

from craftworld_tools.routes.api_account_data import api_account_proficiencies, api_account_uid, api_account_workshop


def register_account_data_legacy_routes(app: Any) -> None:
    """Register account data endpoints."""

    app.route("/api/account_uid", methods=["GET"])(api_account_uid)
    app.route("/api/account_proficiencies", methods=["GET"])(api_account_proficiencies)
    app.route("/api/account_workshop", methods=["GET"])(api_account_workshop)
