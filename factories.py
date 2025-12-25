from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional
import csv

# Point this at your new, clean CSV
CSV_FILE = "Game Data - Factories - rev. v_01 +events.csv"


# ============================================================
# Mastery & Workshop modifiers
# ------------------------------------------------------------
# - Mastery: affects INPUT COST (discount)
#   We treat these as "efficiency multipliers" — inputs are divided by this.
#
# - Workshop: affects PRODUCTION SPEED (duration)
#   Values are percent speed bonus; 100% => 2x speed => half the time.
# ============================================================

MASTERY_BONUSES = {
    0: 1.0,
    1: 1.0204,
    2: 1.0286,
    3: 1.0329,
    4: 1.0372,
    5: 1.0415,
    6: 1.0437,
    7: 1.0459,
    8: 1.0481,
    9: 1.0503,
    10: 1.0525,
}

WORKSHOP_MODIFIERS = {
    "MUD":        [0, 11.11, 23.46, 35.14, 47.06, 58.73, 69.49, 78.57, 85.19, 92.31, 100],
    "CLAY":       [0, 11.11, 23.46, 35.14, 47.06, 58.73, 69.49, 78.57, 85.19, 92.31, 100],
    "SAND":       [0, 11.11, 23.46, 35.14, 47.06, 58.73, 69.49, 78.57, 85.19, 92.31, 100],

    "COPPER":     [0, 9.89, 20.48, 29.87, 38.89, 47.06, 53.85, 61.29, 69.49, 75.44, 81.82],
    "SEAWATER":   [0, 9.89, 20.48, 29.87, 38.89, 47.06, 53.85, 61.29, 69.49, 75.44, 81.82],
    "HEAT":       [0, 9.89, 20.48, 29.87, 38.89, 47.06, 53.85, 61.29, 69.49, 75.44, 81.82],
    "ALGAE":      [0, 9.89, 20.48, 29.87, 38.89, 47.06, 53.85, 61.29, 69.49, 75.44, 81.82],
    "LAVA":       [0, 9.89, 20.48, 29.87, 38.89, 47.06, 53.85, 61.29, 69.49, 75.44, 81.82],
    "CERAMICS":   [0, 9.89, 20.48, 29.87, 38.89, 47.06, 53.85, 61.29, 69.49, 75.44, 81.82],
    "STEEL":      [0, 9.89, 20.48, 29.87, 38.89, 47.06, 53.85, 61.29, 69.49, 75.44, 81.82],
    "OXYGEN":     [0, 9.89, 20.48, 29.87, 38.89, 47.06, 53.85, 61.29, 69.49, 75.44, 81.82],
    "GLASS":      [0, 9.89, 20.48, 29.87, 38.89, 47.06, 53.85, 61.29, 69.49, 75.44, 81.82],

    "STEAM":      [0, 8.7, 17.65, 25, 31.58, 38.89, 44.93, 51.52, 56.25, 61.29, 66.67],
    "GAS":        [0, 8.7, 17.65, 25, 31.58, 38.89, 44.93, 51.52, 56.25, 61.29, 66.67],
    "STONE":      [0, 8.7, 17.65, 25, 31.58, 38.89, 44.93, 51.52, 56.25, 61.29, 66.67],
    "SCREWS":     [0, 8.7, 17.65, 25, 31.58, 38.89, 44.93, 51.52, 56.25, 61.29, 66.67],
    "FUEL":       [0, 8.7, 17.65, 25, 31.58, 38.89, 44.93, 51.52, 56.25, 61.29, 66.67],
    "CEMENT":     [0, 8.7, 17.65, 25, 31.58, 38.89, 44.93, 51.52, 56.25, 61.29, 66.67],
    "OIL":        [0, 8.7, 17.65, 25, 31.58, 38.89, 44.93, 51.52, 56.25, 61.29, 66.67],
    "SULFUR":     [0, 8.7, 17.65, 25, 31.58, 38.89, 44.93, 51.52, 56.25, 61.29, 66.67],
    "ACID":       [0, 8.7, 17.65, 25, 31.58, 38.89, 44.93, 51.52, 56.25, 61.29, 66.67],

    "FIBERGLASS": [0, 7.53, 14.94, 21.95, 28.21, 33.33, 36.99, 40.85, 44.93, 49.25, 53.85],
    "PLASTICS":   [0, 7.53, 14.94, 21.95, 28.21, 33.33, 36.99, 40.85, 44.93, 49.25, 53.85],
    "ENERGY":     [0, 7.53, 14.94, 21.95, 28.21, 33.33, 36.99, 40.85, 44.93, 49.25, 53.85],
    "HYDROGEN":   [0, 7.53, 14.94, 21.95, 28.21, 33.33, 36.99, 40.85, 44.93, 49.25, 53.85],
    "DYNAMITE":   [0, 7.53, 14.94, 21.95, 28.21, 33.33, 36.99, 40.85, 44.93, 49.25, 53.85],
}


@dataclass
class MyFactory:
    token: str
    level: int
    duration_hours: float
    output_per_batch: float
    inputs_per_batch: List[Tuple[str, float]]


def profit_per_hour(
    factory: MyFactory,
    prices: Dict[str, float],
    speed_factor: float = 1.0,
    workers: int = 0,
) -> float:
    """
    Net profit per hour in COIN for a single factory, including:
    - global speed_factor (1x or 2x)
    - workers (0–4) each giving +0.5x on THAT factory only
    """
    workers_clamped = max(0, min(workers, 4))
    multiplier = max(speed_factor, 0.01) * (1.0 + 0.5 * workers_clamped)

    eff_duration_hours = (
        factory.duration_hours / multiplier if multiplier > 0 else factory.duration_hours
    )
    if eff_duration_hours <= 0:
        return 0.0

    crafts_per_hour = 1.0 / eff_duration_hours
    out_h = factory.output_per_batch * crafts_per_hour

    cost_in = 0.0
    for tok, amt in factory.inputs_per_batch:
        amt_h = amt * crafts_per_hour
        cost_in += amt_h * prices.get(tok, 0.0)

    val_out = out_h * prices.get(factory.token, 0.0)
    return val_out - cost_in


# ---------------------------------------------
# Static MyFactory recipes (from your calculator)
# ---------------------------------------------

my_factories: List[MyFactory] = [
    MyFactory("MUD",         40, 1.4167, 11300, [("EARTH", 32300)]),
    MyFactory("CLAY",        24, 1.219,  1510,  [("MUD",   15100)]),
    MyFactory("SAND",        27, 1.75,   2560,  [("STONE", 38400)]),
    MyFactory("COPPER",      28, 1.25,    640,  [("EARTH", 32700)]),
    MyFactory("SEAWATER",    25, 1.867,   605,  [("WATER", 33200)]),
    MyFactory("ALGAE",       13, 0.625,   120,  [("SEAWATER", 4820)]),
    MyFactory("CERAMICS",    11, 1.117,    15,  [("CLAY",  1500)]),
    MyFactory("OXYGEN",      17, 0.667,    40,  [("ALGAE", 2400)]),
    MyFactory("STONE",       39, 0.9,   10700,  [("EARTH", 53500)]),
    MyFactory("HEAT",        22, 0.5,     157,  [("FIRE",  7850)]),
    MyFactory("LAVA",        21, 1.35,    210,  [("STONE", 2100), ("HEAT", 480)]),
    MyFactory("GAS",         11, 1.117,    15,  [("OXYGEN", 1450)]),
    MyFactory("CEMENT",      21, 1.183,   180,  [("STONE", 3320)]),
    MyFactory("GLASS",       21, 1.0,     190,  [("SAND",  3800)]),
    MyFactory("STEAM",       13, 0.6,     120,  [("WATER", 3610), ("HEAT", 415)]),
    MyFactory("STEEL",       19, 1.833,   190,  [("COPPER", 3770), ("HEAT",  800)]),
    MyFactory("FUEL",        16, 1.65,    132,  [("HEAT",  910), ("OIL",  1320)]),
    MyFactory("ACID",        7,  0.6,      5,   [("GAS", 580), ("SULFUR", 150)]),
    MyFactory("SULFUR",      17, 1.0,      40,  [("GAS",  840)]),
    MyFactory("ENERGY",      8,  0.6,      6,   [("FUEL", 372), ("STEAM", 252)]),
    MyFactory("SCREWS",      15, 0.867,    60,  [("STEEL", 1060)]),
    MyFactory("OIL",         14, 1.5,      52,  [("SEAWATER", 1730)]),
    MyFactory("PLASTICS",    20, 1.1,     175,  [("ACID",  315), ("OIL", 1370)]),
    MyFactory("FIBERGLASS",  16, 0.867,    60,  [("GLASS", 1120)]),
    MyFactory("HYDROGEN",    7,  0.55,      5,  [("STEAM", 180), ("ENERGY", 30)]),
    MyFactory("DYNAMITE",    6,  0.6,       4,  [("ACID",  88), ("SULFUR", 290), ("ENERGY", 44)]),

    MyFactory("TAPE",        24, 0.475, 12600, [("PLASTICS",12700)]),
    MyFactory("PLUNGER",     19, 0.375,   163, [("TAPE",    8150)]),
    MyFactory("SPOON",       23, 0.5,    1150, [("TAPE",   13800)]),
    MyFactory("TOYHAMMER",   17, 1.117,   331, [("SPOON",   3980)]),
    MyFactory("TARGET",      18, 1.15,    159, [("PLUNGER",  954)]),
    MyFactory("NINJASTAR",    9, 0.5,      12, [("SPOON",   1380), ("TARGET", 96)]),
    MyFactory("SWORD",        6, 0.49,      5, [("TARGET",  130), ("TOYHAMMER", 80)]),
    MyFactory("MYSTICWEAPON", 3, 1.25,      3, [("SWORD",    12), ("NINJASTAR", 9)]),
]


# ---------------------------------------------
# CSV-driven factory data for the Calculate tab
# ---------------------------------------------

def _normalize_token(sym_raw: str) -> str:
    """Normalize token symbols from CSV rows to match pricing keys.

    The CSV uses "WORMS" for Dyno Fish inputs, but pricing derives a
    singular "WORM" price from the $FISH conversion. Normalizing keeps
    costs from showing as zero in the calculator.
    """

    token = (sym_raw or "").strip().upper()
    aliases = {
        "WORMS": "WORM",
    }
    return aliases.get(token, token)


def load_factories_from_csv(path: str) -> Dict[str, Dict[int, dict]]:
    """
    Load factory data from a normalized CSV with columns:
      token, level, duration_min, output_token, output_amount,
      input_token_1, input_amount_1, input_token_2, input_amount_2,
      upgrade_token, upgrade_amount
    """
    factories: Dict[str, Dict[int, dict]] = {}

    try:
        with open(path, newline="", encoding="utf-8-sig") as f:
            r = csv.DictReader(f)
            for row in r:
                if not row:
                    continue

                token_raw = _normalize_token(row.get("token") or "")
                if not token_raw:␊
                    continue␊
                token = token_raw

                # Level
                lvl_raw = row.get("level")
                try:
                    level = int(float(str(lvl_raw)))
                except Exception:
                    continue

                # Duration in minutes (already minutes in your CSV)
                dur_raw = row.get("duration_min")
                try:
                    duration_min = float(str(dur_raw))
                except Exception:
                    duration_min = 0.0

                # Output
                out_token_raw = _normalize_token(row.get("output_token") or token)
                out_token = out_token_raw if out_token_raw else token

                out_amt_raw = row.get("output_amount")
                try:
                    output_amount = float(str(out_amt_raw).replace(",", ""))
                except Exception:
                    output_amount = 0.0

                # Inputs
                inputs: Dict[str, float] = {}
                for idx in (1, 2):
                    t_key = f"input_token_{idx}"
                    q_key = f"input_amount_{idx}"

                    t_raw = _normalize_token(row.get(t_key) or "")
                    if not t_raw:␊
                        continue␊
                    tok_in = t_raw

                    q_raw = row.get(q_key)
                    if q_raw in (None, ""):
                        continue

                    try:
                        qty = float(str(q_raw).replace(",", ""))
                    except Exception:
                        qty = 0.0

                    inputs[tok_in] = inputs.get(tok_in, 0.0) + qty

                # Upgrade cost (single resource)
                up_token_raw = _normalize_token(row.get("upgrade_token") or "")
                upgrade_token = up_token_raw if up_token_raw else None

                up_amt_raw = row.get("upgrade_amount")
                upgrade_amount: Optional[float] = None
                if up_amt_raw not in (None, ""):
                    try:
                        upgrade_amount = float(str(up_amt_raw).replace(",", ""))
                    except Exception:
                        upgrade_amount = None

                factories.setdefault(token, {})[level] = {
                    "output_token": out_token,
                    "output_amount": output_amount,
                    "duration_min": duration_min,
                    "inputs": inputs,
                    "upgrade_token": upgrade_token,
                    "upgrade_amount": upgrade_amount,
                }

    except Exception as e:
        print("⚠️ Error loading factories from CSV:", e)
        factories = {}

    return factories


FACTORIES_FROM_CSV = load_factories_from_csv(CSV_FILE)
# ---------------------------------------------
# Standard display order for factory tokens
# (used by Overview, Profitability, Calculate, Boosts, etc.)
# ---------------------------------------------

# Base order you requested
_FACTORY_DISPLAY_ORDER_BASE = [
    "MUD",
    "CLAY",
    "SAND",
    "COPPER",
    "SEAWATER",
    "HEAT",
    "ALGAE",
    "LAVA",
    "CERAMICS",
    "STEEL",
    "OXYGEN",
    "GLASS",
    "GAS",
    "STONE",
    "STEAM",
    "SCREWS",
    "FUEL",
    "CEMENT",
    "OIL",
    "ACID",
    "SULFUR",     # <- you wrote SULFER, token is SULFUR in game/code
    "PLASTICS",
    "FIBERGLASS",
    "ENERGY",
    "HYDROGEN",
    "DYNAMITE",
]

# Filter to only factories that actually exist in the CSV,
# and then append any extra CSV factories that weren't in the base list.
FACTORY_DISPLAY_ORDER: list[str] = [
    tok for tok in _FACTORY_DISPLAY_ORDER_BASE if tok in FACTORIES_FROM_CSV
]
for tok in sorted(FACTORIES_FROM_CSV.keys()):
    if tok not in FACTORY_DISPLAY_ORDER:
        FACTORY_DISPLAY_ORDER.append(tok)

# Quick lookup: token -> index for sorting
FACTORY_DISPLAY_INDEX: dict[str, int] = {
    tok: idx for idx, tok in enumerate(FACTORY_DISPLAY_ORDER)
}


def compute_factory_result_csv(
    factories: Dict[str, Dict[int, dict]],
    prices_coin: Dict[str, float],
    token: str,
    level: int,
    target_level: Optional[int],
    count: int,
    yield_pct: float,
    speed_factor: float,
    workers: int,
    input_prices_coin: Optional[Dict[str, float]] = None,
):

    if token not in factories:
        raise RuntimeError(f"No CSV data for factory token {token}.")
    if level not in factories[token]:
        raise RuntimeError(f"No CSV data for {token} level {level}.")

    levels_dict = factories[token]
    data = levels_dict[level]
    out_token = data["output_token"]
    out_amount = data["output_amount"]
    duration_min = data["duration_min"]
    base_inputs = data["inputs"] or {}

    # Yield/mastery factor
    yield_factor = max(yield_pct, 0.0001) / 100.0
    inputs_adj = {t: q / yield_factor for t, q in base_inputs.items()}

    # Multi-step upgrade chain (level → target_level)
    multi_upgrade_tokens: Dict[str, float] = {}
    if target_level and target_level > level:
        for step_level in range(level + 1, target_level + 1):
            row_step = levels_dict.get(step_level)
            if not row_step:
                continue
            step_tok = row_step.get("upgrade_token")
            step_amt = row_step.get("upgrade_amount", 0.0) or 0.0
            if step_tok and step_amt > 0:
                multi_upgrade_tokens[step_tok] = multi_upgrade_tokens.get(step_tok, 0.0) + step_amt

    # Single-step upgrade (just next level)
    next_row = levels_dict.get(level + 1)
    if next_row is not None:
        up_token = next_row.get("upgrade_token")
        up_amount = next_row.get("upgrade_amount", 0.0)
    else:
        up_token = data.get("upgrade_token")
        up_amount = data.get("upgrade_amount", 0.0)

    # Speed + workers
    workers_clamped = max(0, min(workers, 4))
    worker_factor = 1.0 + 0.5 * workers_clamped
    combined_speed = max(speed_factor, 0.01) * worker_factor
    effective_duration = duration_min / combined_speed if combined_speed > 0 else duration_min
    crafts_per_hour = 60.0 / effective_duration if effective_duration > 0 else 0.0

    # Pricing helpers
    def p_out(tok: str) -> float:
        """Price used for outputs (always SELL map)."""
        return float(prices_coin.get(tok, 0.0))

    def p_in(tok: str) -> float:
        """
        Price used for inputs / upgrade costs.
        If a separate input_prices_coin dict is provided, use that first;
        otherwise fall back to the main prices_coin.
        """
        if input_prices_coin is not None:
            return float(input_prices_coin.get(tok, prices_coin.get(tok, 0.0)))
        return float(prices_coin.get(tok, 0.0))

    # Costs & values
    inputs_value_coin = {t: q * p_in(t) for t, q in inputs_adj.items()}
    cost_coin_per_craft = sum(inputs_value_coin.values())
    value_coin_per_craft = out_amount * p_out(out_token)

    profit_coin_per_craft = value_coin_per_craft - cost_coin_per_craft
    profit_coin_per_hour = profit_coin_per_craft * crafts_per_hour * count

    # Upgrade cost (single step)
    upgrade_single = None
    if up_token and up_amount and up_amount > 0:
        up_coin_one = up_amount * p_in(up_token)
        up_coin_total = up_coin_one * count
        upgrade_single = {
            "token": up_token,
            "amount_per_factory": up_amount,
            "coin_per_factory": up_coin_one,
            "coin_total": up_coin_total,
        }

    # Upgrade chain (level → target_level)
    upgrade_chain = []

    # Upgrade chain (level → target_level)
    upgrade_chain = []
    if multi_upgrade_tokens and target_level and target_level > level:
        for tok, amt in multi_upgrade_tokens.items():
            coin_per_factory = amt * p_in(tok)
            coin_all = coin_per_factory * count
            upgrade_chain.append(
                {
                    "token": tok,
                    "amount_per_factory": amt,
                    "coin_per_factory": coin_per_factory,
                    "coin_total": coin_all,
                }
            )

    return {
        "token": token,
        "level": level,
        "target_level": target_level,
        "count": count,
        "yield_pct": yield_pct,
        "speed_factor": speed_factor,
        "workers": workers,
        "duration_min": duration_min,
        "effective_duration": effective_duration,
        "crafts_per_hour": crafts_per_hour,
        "out_token": out_token,
        "out_amount": out_amount,
        "inputs": inputs_adj,
        "inputs_value_coin": inputs_value_coin,
        "cost_coin_per_craft": cost_coin_per_craft,
        "value_coin_per_craft": value_coin_per_craft,
        "profit_coin_per_craft": profit_coin_per_craft,
        "profit_coin_per_hour": profit_coin_per_hour,
        "upgrade_single": upgrade_single,
        "upgrade_chain": upgrade_chain,
    }


def compute_best_setups_csv(
    factories: Dict[str, Dict[int, dict]],
    prices_coin: Dict[str, float],
    speed_factor: float,
    workers: int,
    yield_pct: float,
    top_n: int = 15,
):
    results = []
    yield_factor = max(yield_pct, 0.0001) / 100.0
    workers_clamped = max(0, min(workers, 4))
    worker_factor = 1.0 + 0.5 * workers_clamped
    combined_speed = max(speed_factor, 0.01) * worker_factor

    def p(tok: str) -> float:
        return float(prices_coin.get(tok, 0.0))

    for fac_name, levels in factories.items():
        for lvl, data in levels.items():
            out_token = data["output_token"]
            out_amount = data["output_amount"]
            duration_min = data["duration_min"]
            base_inputs = data["inputs"] or {}

            eff_dur = duration_min / combined_speed if combined_speed > 0 else duration_min
            crafts_per_hour = 60.0 / eff_dur if eff_dur > 0 else 0.0

            inputs_adj = {t: q / yield_factor for t, q in base_inputs.items()}
            cost_coin = sum(q * p(t) for t, q in inputs_adj.items())
            value_coin = out_amount * p(out_token)
            profit_coin_per_craft = value_coin - cost_coin
            profit_coin_per_hour = profit_coin_per_craft * crafts_per_hour

            results.append(
                {
                    "token": fac_name,
                    "level": lvl,
                    "profit_coin_per_hour": profit_coin_per_hour,
                    "profit_coin_per_craft": profit_coin_per_craft,
                }
            )

    results.sort(key=lambda r: r["profit_coin_per_hour"], reverse=True)
    return results[:top_n], combined_speed, worker_factor





