"""Application factory scaffold for the future app.py cleanup.

This file is intentionally conservative. It gives us the final target shape
without replacing the current production app.py yet.
"""

from __future__ import annotations

import os
from typing import Any, Callable, Optional

from flask import Flask

from craftworld_tools.db import init_db
from craftworld_tools.routes.registry import register_extracted_api_routes, register_extracted_page_routes


def create_app(
    *,
    secret_key: Optional[str] = None,
    register_routes: bool = False,
    has_uid_flag: Optional[Callable[[], bool]] = None,
    get_cached_account_status: Optional[Callable[[], dict[str, Any]]] = None,
    require_login: Optional[Callable[[], Optional[Any]]] = None,
) -> Flask:
    """Create a Flask app instance.

    `register_routes` defaults to False so this scaffold can exist safely while
    the old app.py still owns the live route table.
    """
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder=os.path.join(os.getcwd(), "static"),
    )
    app.secret_key = secret_key or os.environ.get("SECRET_KEY", "dev-secret-change-me")

    init_db()

    if register_routes:
        if has_uid_flag is None:
            raise RuntimeError("has_uid_flag is required when register_routes=True")
        register_extracted_api_routes(
            app,
            get_cached_account_status=get_cached_account_status,
            require_login=require_login,
        )
        register_extracted_page_routes(
            app,
            has_uid_flag=has_uid_flag,
            include_dashboard=True,
            include_auth=True,
            include_boosts=True,
            include_factories=True,
            include_masterpieces=True,
            include_profitability=True,
            include_crafting=True,
        )

    return app
