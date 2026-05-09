"""Cached wrappers around expensive runtime service calls."""

from __future__ import annotations

from typing import Any, Optional

from craftworld_api import fetch_craftworld, fetch_masterpieces
from pricing import fetch_buy_sell_for_profitability, fetch_live_prices_in_coin

from craftworld_tools.services.masterpiece_queries import fetch_masterpiece_details_for_user
from craftworld_tools.services.runtime_cache import TTLCache

_cache: TTLCache[Any] = TTLCache()


def cached_live_prices(ttl_seconds: float = 45.0) -> dict[str, float]:
    """Fetch live prices with a short cache window."""
    return _cache.get_or_set(("live_prices",), ttl_seconds, fetch_live_prices_in_coin)


def cached_buy_sell(symbols: list[str] | tuple[str, ...], ttl_seconds: float = 60.0) -> dict[str, dict[str, float]]:
    """Fetch buy/sell quotes with a short cache window."""
    clean_symbols = tuple(sorted({str(sym).upper() for sym in symbols if sym}))
    return _cache.get_or_set(("buy_sell", clean_symbols), ttl_seconds, lambda: fetch_buy_sell_for_profitability(list(clean_symbols)))


def cached_craftworld(uid: str, ttl_seconds: float = 45.0) -> Any:
    """Fetch Craft World account data with a short cache window."""
    clean_uid = str(uid or "").strip()
    return _cache.get_or_set(("craftworld", clean_uid), ttl_seconds, lambda: fetch_craftworld(clean_uid))


def cached_masterpieces(ttl_seconds: float = 120.0) -> list[dict[str, Any]]:
    """Fetch Masterpiece list with a short cache window."""
    return _cache.get_or_set(("masterpieces",), ttl_seconds, fetch_masterpieces)


def cached_masterpiece_details(
    masterpiece_id: int,
    user_id: Optional[str] = None,
    ttl_seconds: float = 120.0,
) -> dict[str, Any]:
    """Fetch one Masterpiece detail payload with optional per-user fields."""
    mid = int(masterpiece_id)
    clean_user_id = str(user_id or "").strip()
    cache_key = ("masterpiece_details", mid, clean_user_id or None)
    return _cache.get_or_set(
        cache_key,
        ttl_seconds,
        lambda: fetch_masterpiece_details_for_user(mid, clean_user_id or None),
    )


def clear_runtime_cache() -> None:
    _cache.clear()
