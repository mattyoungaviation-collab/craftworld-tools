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
from craftworld_tools.routes.pages_boosts import register_boost_page_routes
from craftworld_tools.routes.pages_crafting import register_crafting_page_routes
from craftworld_tools.routes.pages_dashboard import register_dashboard_routes
from craftworld_tools.routes.pages_factories import register_factory_page_routes
from craftworld_tools.routes.pages_masterpieces import register_masterpiece_page_routes
from craftworld_tools.routes.pages_profitability import register_profitability_page_routes


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
    has_uid_flag: Callable[[], bool],
    include_dashboard: bool = False,
    include_auth: bool = False,
    include_boosts: bool = False,
    include_factories: bool = False,
    include_masterpieces: bool = False,
    include_profitability: bool = False,
    include_crafting: bool = False,
) -> None:
    """Register extracted HTML/page routes after matching inline routes are removed.

    The boolean flags let app.py adopt page groups one at a time without causing
    duplicate Flask route registrations.
    """
    if include_dashboard:
        register_dashboard_routes(app, has_uid_flag)
    if include_auth:
        register_auth_routes(app, has_uid_flag)
    if include_boosts:
        register_boost_page_routes(app, has_uid_flag)
    if include_factories:
        register_factory_page_routes(app, has_uid_flag)
    if include_masterpieces:
        register_masterpiece_page_routes(app, has_uid_flag)
    if include_profitability:
        register_profitability_page_routes(app, has_uid_flag)
    if include_crafting:
        register_crafting_page_routes(app, has_uid_flag)
