"""Crafting planner JSON API routes.

Transition-ready route module for crafting planner endpoints. Register only
after matching inline routes are removed from app.py.
"""

from __future__ import annotations

from typing import Any

from flask import jsonify, request

from craftworld_tools.domain.crafting import CRAFTING_CHAINS, Modifiers, build_chain_report, plan_craft, rank_opportunities
from craftworld_tools.services.pricing import fetch_buy_sell_for_profitability, fetch_live_prices_in_coin


def _build_modifiers(data: dict[str, Any]) -> Modifiers:
    return Modifiers(
        masteryLevelsBySymbol=data.get("masteryLevelsBySymbol") or {},
        workshopLevelsByFactoryOrTier=data.get("workshopLevelsByFactoryOrTier") or {},
        globalSpeedMultiplier=float(data.get("globalSpeedMultiplier") or 1.0),
    )


def register_crafting_api_routes(app: Any) -> None:
    """Register crafting planner JSON routes."""

    @app.route("/api/crafting/chains", methods=["GET"])
    def api_crafting_chains():
        return jsonify({"ok": True, "chains": CRAFTING_CHAINS})

    @app.route("/api/crafting/plan", methods=["POST"])
    def api_crafting_plan():
        data = request.get_json(silent=True) or {}
        target_symbol = str(data.get("targetSymbol") or data.get("target_symbol") or "").strip().upper()
        if not target_symbol:
            return jsonify({"ok": False, "error": "targetSymbol is required."}), 400
        try:
            target_amount = float(data.get("targetAmount") or data.get("target_amount") or 1.0)
        except (TypeError, ValueError):
            target_amount = 1.0

        mode = str(data.get("mode") or "craft").strip().lower()
        prices = data.get("prices") if isinstance(data.get("prices"), dict) else fetch_live_prices_in_coin()
        modifiers = _build_modifiers(data.get("modifiers") or {}) if isinstance(data.get("modifiers"), dict) else None
        plan = plan_craft(
            target_symbol,
            target_amount,
            prices,
            mode,
            modifiers=modifiers,
            base_cost_model=data.get("baseCostModel") or data.get("base_cost_model"),
            available_bases=data.get("availableBases") or data.get("available_bases"),
            power_now=data.get("powerNow") or data.get("power_now"),
            refill_seconds=data.get("refillSeconds") or data.get("refill_seconds"),
        )
        return jsonify({"ok": True, "plan": plan})

    @app.route("/api/crafting/rank", methods=["POST"])
    def api_crafting_rank():
        data = request.get_json(silent=True) or {}
        prices = data.get("prices") if isinstance(data.get("prices"), dict) else fetch_live_prices_in_coin()
        modifiers = _build_modifiers(data.get("modifiers") or {}) if isinstance(data.get("modifiers"), dict) else None
        plans = rank_opportunities(
            prices,
            str(data.get("mode") or "craft"),
            str(data.get("objective") or "profit_per_power"),
            data.get("powerBudget") or data.get("power_budget"),
            data.get("timeBudgetSeconds") or data.get("time_budget_seconds"),
            float(data.get("targetAmount") or data.get("target_amount") or 1.0),
            modifiers=modifiers,
            base_cost_model=data.get("baseCostModel") or data.get("base_cost_model"),
            available_bases=data.get("availableBases") or data.get("available_bases"),
        )
        return jsonify({"ok": True, "plans": plans})

    @app.route("/api/crafting/chain_report", methods=["POST"])
    def api_crafting_chain_report():
        data = request.get_json(silent=True) or {}
        chain_name = str(data.get("chainName") or data.get("chain_name") or "Custom Chain")
        chain_symbols = data.get("chainSymbols") or data.get("chain_symbols") or []
        if not isinstance(chain_symbols, list):
            return jsonify({"ok": False, "error": "chainSymbols must be a list."}), 400
        prices = data.get("prices") if isinstance(data.get("prices"), dict) else fetch_live_prices_in_coin()
        modifiers = _build_modifiers(data.get("modifiers") or {}) if isinstance(data.get("modifiers"), dict) else None
        quotes = fetch_buy_sell_for_profitability([str(s).upper() for s in chain_symbols if s])
        input_prices = {sym: rec.get("BUY", rec.get("SELL", prices.get(sym, 0.0))) for sym, rec in quotes.items()}
        output_prices = {sym: rec.get("SELL", rec.get("BUY", prices.get(sym, 0.0))) for sym, rec in quotes.items()}
        report = build_chain_report(
            chain_name,
            [str(s).upper() for s in chain_symbols],
            prices,
            modifiers=modifiers,
            start_amount=float(data.get("startAmount") or data.get("start_amount") or 1.0),
            input_prices=input_prices,
            output_prices=output_prices,
        )
        return jsonify({"ok": True, "report": report})
