"""Backward-compatible pricing entry point.

The pricing implementation now lives in `craftworld_tools.services.pricing_core`.
This file remains so existing imports like `from pricing import ...` keep working
while the rest of the app is gradually moved into the package structure.
"""

from craftworld_tools.services.pricing_core import (  # noqa: F401
    TOKEN_ADDRESSES,
    fetch_buy_sell_for_profitability,
    fetch_exchange_prices_buy_sell,
    fetch_exchange_prices_coin,
    fetch_live_prices_in_coin,
)
