"""Route registration helpers.

These functions collect extracted route modules in one place. During the
transition, call only the groups whose old inline app.py routes have already
been removed.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from craftworld_tools.routes.api_account import register_account_api_routes
from craftworld_tools.routes.api_crafting import register_crafting_api_routes
from craftworld_tools.routes.api_factories import register_factory_api_routes
from craftworld_tools.routes.api_identity import register_identity_api_routes
from craftworld_tools.routes.api_masterpieces import register_masterpiece_api_routes
from craftworld_tools.routes.api_mp_presets import register_mp_preset_api_routes
from craftworld_tools.routes.api_prices import register_price_api_routes
from craftworld_tools.routes.auth import register_auth_routes


def register_extracted_api_routes(
    app: Any,
    *,
    get_cached_account_status: Optional[Callable[[], dict[str, Any]]] = None,
    require_login: Optional[Callable[[], Optional[Any]]] = None,
) -> None:
    """Register extracted API routes after matching inline routes are removed."""
    if get_cached_account_status is not None:
        register_account_api_routes(app, get_cached_account_status)
    register_identity_api_routes(app)
    register_price_api_routes(app)
    register_masterpiece_api_routes(app)
    register_factory_api_routes(app)
    register_crafting_api_routes(app)
    register_mp_preset_api_routes(app, require_login=require_login)


def register_extracted_page_routes(
    app: Any,
    *,
    base_template: str,
    has_uid_flag: Callable[[], bool],
) -> None:
    """Register extracted HTML/page routes after matching inline routes are removed."""
    register_auth_routes(app, base_template, has_uid_flag)
