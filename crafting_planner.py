from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from math import ceil
from typing import Any, Dict, List, Optional, Tuple

from factories import FACTORIES_FROM_CSV, MASTERY_BONUSES, WORKSHOP_MODIFIERS

BASE_SYMBOLS = {"EARTH", "WATER", "FIRE", "COIN"}

CANONICAL_GRAPH: Dict[str, List[str]] = {
    "MUD": ["EARTH"],
    "CLAY": ["MUD"],
    "SAND": ["CLAY"],
    "COPPER": ["SAND"],
    "STEEL": ["COPPER"],
    "SCREWS": ["STEEL"],
    "SEAWATER": ["WATER"],
    "ALGAE": ["SEAWATER"],
    "OXYGEN": ["ALGAE"],
    "GAS": ["OXYGEN"],
    "FUEL": ["GAS"],
    "OIL": ["FUEL"],
    "HEAT": ["FIRE"],
    "LAVA": ["HEAT"],
    "CERAMICS": ["CLAY", "SEAWATER"],
    "STONE": ["COPPER", "ALGAE"],
    "CEMENT": ["CERAMICS", "STONE"],
    "ACID": ["SCREWS", "FUEL"],
    "PLASTICS": ["CEMENT", "ACID"],
    "GLASS": ["SAND", "HEAT"],
    "SULFUR": ["GLASS", "LAVA"],
    "FIBERGLASS": ["GLASS", "SULFUR"],
    "DYNAMITE": ["PLASTICS", "FIBERGLASS"],
    "STEAM": ["OXYGEN", "LAVA"],
    "ENERGY": ["OIL", "HEAT"],
    "HYDROGEN": ["STEAM", "ENERGY"],
}


@dataclass
class RecipeInput:
    symbol: str
    qty: float


@dataclass
class Recipe:
    outputSymbol: str
    outputQty: float
    inputs: List[RecipeInput]
    craftSeconds: float
    powerCost: float
    level: int


@dataclass
class Modifiers:
    masteryLevelsBySymbol: Dict[str, int]
    workshopLevelsByFactoryOrTier: Dict[str, int]
    globalSpeedMultiplier: float = 1.0


DEFAULT_MODIFIERS = Modifiers({}, {}, 1.0)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def build_recipe_index() -> Tuple[Dict[str, Recipe], List[str]]:
    warnings: List[str] = []
    index: Dict[str, Recipe] = {}
    for token, levels in FACTORIES_FROM_CSV.items():
        if not levels:
            continue
        lvl = min(levels.keys())
        row = levels[lvl]
        inputs = [RecipeInput(symbol=sym.upper(), qty=_safe_float(qty, 0.0)) for sym, qty in (row.get("inputs") or {}).items()]
        recipe = Recipe(
            outputSymbol=(row.get("output_token") or token).upper(),
            outputQty=max(_safe_float(row.get("output_amount"), 1.0), 1e-9),
            inputs=inputs,
            craftSeconds=max(_safe_float(row.get("duration_min"), 0.0) * 60.0, 0.0),
            # CSV has no explicit power, use stable placeholder and mark incomplete via warnings.
            powerCost=max(sum(i.qty for i in inputs), 1.0),
            level=int(lvl),
        )
        index[recipe.outputSymbol] = recipe

    for output_symbol in CANONICAL_GRAPH.keys():
        if output_symbol not in index:
            warnings.append(f"Missing recipe for canonical symbol {output_symbol}")

    if warnings:
        for w in warnings:
            print(f"⚠️ {w}")

    return index, warnings


def get_effective_recipe(base_recipe: Recipe, modifiers: Modifiers) -> Recipe:
    mastery_level = max(0, min(10, int(modifiers.masteryLevelsBySymbol.get(base_recipe.outputSymbol, 0))))
    mastery_bonus = float(MASTERY_BONUSES.get(mastery_level, 1.0))

    workshop_level = max(0, min(10, int(modifiers.workshopLevelsByFactoryOrTier.get(base_recipe.outputSymbol, 0))))
    ws_table = WORKSHOP_MODIFIERS.get(base_recipe.outputSymbol, [0.0])
    ws_pct = float(ws_table[workshop_level]) if workshop_level < len(ws_table) else 0.0

    speed_multiplier = max(1e-9, float(modifiers.globalSpeedMultiplier or 1.0) * (1.0 + ws_pct / 100.0))
    eff_inputs = [RecipeInput(symbol=i.symbol, qty=i.qty / max(mastery_bonus, 1e-9)) for i in base_recipe.inputs]

    return Recipe(
        outputSymbol=base_recipe.outputSymbol,
        outputQty=base_recipe.outputQty,
        inputs=eff_inputs,
        craftSeconds=base_recipe.craftSeconds / speed_multiplier,
        powerCost=base_recipe.powerCost,
        level=base_recipe.level,
    )


def _format_hms(total_seconds: int) -> str:
    total_seconds = max(0, int(total_seconds))
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60
    s = total_seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def plan_craft(
    target_symbol: str,
    target_amount: float,
    prices: Dict[str, float],
    mode: str,
    modifiers: Optional[Modifiers] = None,
    base_cost_model: Optional[Dict[str, float]] = None,
    available_bases: Optional[List[str]] = None,
    power_now: Optional[float] = None,
    refill_seconds: Optional[int] = None,
) -> Dict[str, Any]:
    recipe_index, validation_warnings = build_recipe_index()
    modifiers = modifiers or DEFAULT_MODIFIERS
    base_cost_model = {"EARTH": 0.0, "WATER": prices.get("WATER", 0.0), "FIRE": prices.get("FIRE", 0.0), **(base_cost_model or {})}
    available_base_set = {b.upper() for b in (available_bases or ["EARTH", "WATER", "FIRE"])}

    steps_count: Dict[str, int] = {}
    external_needs: Dict[str, float] = {}
    missing_prices: set[str] = set()
    missing_recipes: set[str] = set()

    @lru_cache(maxsize=None)
    def unit_coin_cost(symbol: str) -> float:
        s = symbol.upper()
        price = prices.get(s)
        if mode == "market":
            if price is None:
                missing_prices.add(s)
                return 0.0
            return float(price)

        if s in BASE_SYMBOLS:
            if s in available_base_set:
                return float(base_cost_model.get(s, prices.get(s, 0.0)))
            p = prices.get(s)
            if p is None:
                missing_prices.add(s)
                return 0.0
            return float(p)

        recipe = recipe_index.get(s)
        if not recipe:
            p = prices.get(s)
            missing_recipes.add(s)
            if p is None:
                missing_prices.add(s)
                return 0.0
            return float(p)

        eff = get_effective_recipe(recipe, modifiers)
        total_in_cost = sum(inp.qty * unit_coin_cost(inp.symbol) for inp in eff.inputs)
        return total_in_cost / max(eff.outputQty, 1e-9)

    def expand(symbol: str, qty: float) -> None:
        s = symbol.upper()
        if qty <= 0:
            return

        if mode == "market":
            external_needs[s] = external_needs.get(s, 0.0) + qty
            if s not in prices:
                missing_prices.add(s)
            return

        if s in BASE_SYMBOLS:
            if s in available_base_set:
                external_needs[s] = external_needs.get(s, 0.0) + qty
            else:
                external_needs[s] = external_needs.get(s, 0.0) + qty
                if s not in prices and s not in base_cost_model:
                    missing_prices.add(s)
            return

        recipe = recipe_index.get(s)
        if not recipe:
            missing_recipes.add(s)
            external_needs[s] = external_needs.get(s, 0.0) + qty
            if s not in prices:
                missing_prices.add(s)
            return

        eff = get_effective_recipe(recipe, modifiers)
        crafts = int(ceil(qty / max(eff.outputQty, 1e-9)))
        steps_count[s] = steps_count.get(s, 0) + crafts
        for inp in eff.inputs:
            expand(inp.symbol, inp.qty * crafts)

    expand(target_symbol, float(target_amount))

    steps: List[Dict[str, Any]] = []
    total_power = 0.0
    total_seconds = 0.0
    total_coin_cost = 0.0

    for symbol, crafts in sorted(steps_count.items()):
        recipe = recipe_index[symbol]
        eff = get_effective_recipe(recipe, modifiers)
        input_cost = sum(inp.qty * unit_coin_cost(inp.symbol) * crafts for inp in eff.inputs)
        output_qty = eff.outputQty * crafts
        output_value = output_qty * float(prices.get(symbol, 0.0))
        total_power += eff.powerCost * crafts
        total_seconds += eff.craftSeconds * crafts
        total_coin_cost += input_cost
        steps.append({
            "outputSymbol": symbol,
            "times": crafts,
            "inputs": [{"symbol": i.symbol, "qty": i.qty * crafts} for i in eff.inputs],
            "powerCost": eff.powerCost * crafts,
            "timeCost": eff.craftSeconds * crafts,
            "coinCost": input_cost,
            "coinValue": output_value,
        })

    ext_cost = 0.0
    for sym, qty in external_needs.items():
        ext_cost += qty * unit_coin_cost(sym)

    target_price = float(prices.get(target_symbol.upper(), 0.0))
    coin_value = target_price * float(target_amount)
    gross_profit = coin_value - (total_coin_cost + ext_cost)
    profit_per_power = gross_profit / max(total_power, 1e-9)
    profit_per_hour = gross_profit / max(total_seconds / 3600.0, 1e-9)
    roi = gross_profit / max((total_coin_cost + ext_cost), 1e-9)

    deficit = 0.0
    can_afford_now = True
    eta = "00:00:00"
    if power_now is not None:
        deficit = max(0.0, total_power - float(power_now))
        can_afford_now = deficit <= 0
        eta = "00:00:00" if can_afford_now else _format_hms(int(refill_seconds or 0))

    return {
        "targetSymbol": target_symbol.upper(),
        "targetAmount": target_amount,
        "steps": steps,
        "totals": {
            "power": total_power,
            "seconds": total_seconds,
            "coinCost": total_coin_cost + ext_cost,
            "coinValue": coin_value,
            "grossProfit": gross_profit,
            "profitPerPower": profit_per_power,
            "profitPerHour": profit_per_hour,
            "ROI": roi,
        },
        "missing": {
            "prices": sorted(missing_prices),
            "recipes": sorted(set(validation_warnings) | missing_recipes),
            "modifiers": [],
        },
        "constraints": {
            "powerNow": power_now,
            "canAffordNow": can_afford_now,
            "powerDeficit": deficit,
            "etaToAffordHMS": eta,
        },
        "externalNeeds": external_needs,
    }


def rank_opportunities(
    prices: Dict[str, float],
    mode: str,
    objective: str,
    power_budget: Optional[float],
    time_budget_seconds: Optional[float],
    target_amount: float,
    modifiers: Optional[Modifiers] = None,
    base_cost_model: Optional[Dict[str, float]] = None,
    available_bases: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    recipe_index, _ = build_recipe_index()
    candidates = sorted(set(CANONICAL_GRAPH.keys()) & set(recipe_index.keys()))
    plans = []
    for symbol in candidates:
        plan = plan_craft(
            symbol,
            target_amount,
            prices,
            mode,
            modifiers,
            base_cost_model,
            available_bases,
            power_now=power_budget,
            refill_seconds=0,
        )
        totals = plan["totals"]
        if power_budget is not None and totals["power"] > power_budget and objective == "total_profit":
            continue
        if time_budget_seconds is not None and totals["seconds"] > time_budget_seconds and objective == "total_profit":
            continue
        plans.append(plan)

    key_map = {
        "profit_per_power": lambda p: p["totals"]["profitPerPower"],
        "profit_per_hour": lambda p: p["totals"]["profitPerHour"],
        "total_profit": lambda p: p["totals"]["grossProfit"],
    }
    sort_key = key_map.get(objective, key_map["profit_per_power"])
    return sorted(plans, key=sort_key, reverse=True)
