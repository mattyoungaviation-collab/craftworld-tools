"""Factory calculation JSON API routes.

Transition-ready route module for factory calculation endpoints. Register only
after matching inline routes are removed from app.py.
"""

from __future__ import annotations

from typing import Any

from flask import jsonify, request

from craftworld_tools.domain.factories import (
    FACTORIES_FROM_CSV,
    compute_best_setups_csv,
    compute_factory_result_csv,
)
from craftworld_tools.services.pricing import fetch_buy_sell_for_profitability, fetch_live_prices_in_coin


def _float_arg(name: str, default: float) -> float:
    try:
        return float(request.args.get(name, default))
    except (TypeError, ValueError):
        return default


def _int_arg(name: str, default: int) -> int:
    try:
        return int(float(request.args.get(name, default)))
    except (TypeError, ValueError):
        return default


def register_factory_api_routes(app: Any) -> None:
    """Register factory calculation JSON routes."""

    @app.route("/api/factories/calculate", methods=["GET"])
    def api_factory_calculate():
        token = (request.args.get("token") or "").strip().upper()
        if not token:
            return jsonify({"ok": False, "error": "token is required."}), 400

        level = _int_arg("level", 1)
        target_level = request.args.get("target_level")
        try:
            target_level_int = int(float(target_level)) if target_level not in (None, "") else None
        except (TypeError, ValueError):
            target_level_int = None

        count = max(1, _int_arg("count", 1))
        yield_pct = _float_arg("yield_pct", 100.0)
        speed_factor = _float_arg("speed_factor", 1.0)
        workers = _int_arg("workers", 0)

        prices = fetch_live_prices_in_coin()
        symbols = sorted(set(prices.keys()) | {token})
        quotes = fetch_buy_sell_for_profitability(symbols)
        input_prices = {sym: rec.get("BUY", rec.get("SELL", prices.get(sym, 0.0))) for sym, rec in quotes.items()}

        try:
            result = compute_factory_result_csv(
                FACTORIES_FROM_CSV,
                prices,
                token,
                level,
                target_level_int,
                count,
                yield_pct,
                speed_factor,
                workers,
                input_prices_coin=input_prices,
            )
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

        return jsonify({"ok": True, "result": result})

    @app.route("/api/factories/best", methods=["GET"])
    def api_factory_best():
        prices = fetch_live_prices_in_coin()
        speed_factor = _float_arg("speed_factor", 1.0)
        workers = _int_arg("workers", 0)
        yield_pct = _float_arg("yield_pct", 100.0)
        top_n = max(1, min(100, _int_arg("top_n", 15)))
        results, combined_speed, worker_factor = compute_best_setups_csv(
            FACTORIES_FROM_CSV,
            prices,
            speed_factor,
            workers,
            yield_pct,
            top_n=top_n,
        )
        return jsonify(
            {
                "ok": True,
                "results": results,
                "combined_speed": combined_speed,
                "worker_factor": worker_factor,
            }
        )
