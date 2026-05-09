"""Pricing JSON API routes.

Transition-ready route module for price endpoints. Register only after matching
inline routes are removed from app.py.
"""

from __future__ import annotations

from typing import Any

from flask import jsonify, request

from craftworld_tools.services.pricing import (
    TOKEN_ADDRESSES,
    fetch_buy_sell_for_profitability,
    fetch_live_prices_in_coin,
)


def _parse_symbols(raw: str) -> list[str]:
    symbols = []
    for item in (raw or "").replace(";", ",").split(","):
        sym = item.strip().upper()
        if sym and sym not in symbols:
            symbols.append(sym)
    return symbols


def register_price_api_routes(app: Any) -> None:
    """Register pricing JSON routes."""

    @app.route("/api/prices", methods=["GET"])
    def api_prices():
        prices = fetch_live_prices_in_coin()
        return jsonify({"ok": True, "prices": prices})

    @app.route("/api/prices/buy_sell", methods=["GET"])
    def api_prices_buy_sell():
        raw_symbols = request.args.get("symbols") or ""
        symbols = _parse_symbols(raw_symbols)
        if not symbols:
            symbols = sorted([sym for sym in TOKEN_ADDRESSES.keys() if sym and not sym.startswith("_")])
        quotes = fetch_buy_sell_for_profitability(symbols)
        return jsonify({"ok": True, "quotes": quotes})
