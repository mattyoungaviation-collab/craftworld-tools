"""Pricing service compatibility layer.

The implementation still lives in the root-level pricing.py module so existing
imports keep working. New code should import from this module and, in a later
pass, the implementation can be moved here fully.
"""

from pricing import (  # noqa: F401
    TOKEN_ADDRESSES,
    fetch_buy_sell_for_profitability,
    fetch_exchange_prices_buy_sell,
    fetch_exchange_prices_coin,
    fetch_live_prices_in_coin,
)
