"""Account data API route wrappers."""

from __future__ import annotations

from typing import Any

import craftworld_tools.routes.api_account_data as api_account_data
from craftworld_tools.routes.legacy_globals import inject_app_globals


def api_account_uid():
    inject_app_globals(api_account_data)
    return api_account_data.api_account_uid()


def api_account_proficiencies():
    inject_app_globals(api_account_data)
    return api_account_data.api_account_proficiencies()


def api_account_workshop():
    inject_app_globals(api_account_data)
    return api_account_data.api_account_workshop()


def register_account_data_legacy_routes(app: Any) -> None:
    """Register account data endpoints."""

    app.route("/api/account_uid", methods=["GET"])(api_account_uid)
    app.route("/api/account_proficiencies", methods=["GET"])(api_account_proficiencies)
    app.route("/api/account_workshop", methods=["GET"])(api_account_workshop)
