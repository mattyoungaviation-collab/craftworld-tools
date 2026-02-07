import os
import sys
import math
import json
import requests
from typing import Dict, Any, List

GRAPHQL_ENDPOINT = "https://craft-world.gg/graphql"

# Default for you – app can override by passing user_id explicitly
DEFAULT_USER_ID = "GfUeRBCZv8OwuUKq7Tu9JVpA70l1"


# ============================================================
# Low-level helper: GraphQL request with JWT
# ============================================================

def graphql_request(query: str, variables: Dict[str, Any] | None = None) -> Dict[str, Any]:
    jwt = os.getenv("CRAFTWORLD_JWT")
    if not jwt:
        raise RuntimeError(
            "CRAFTWORLD_JWT environment variable is not set.\n"
            "Set it in PowerShell, e.g.:\n"
            '  $env:CRAFTWORLD_JWT = "jwt_eyJhbGciOi..."'
        )

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {jwt}",
    }
    payload = {"query": query, "variables": variables or {}}

    resp = requests.post(GRAPHQL_ENDPOINT, headers=headers, json=payload)
    try:
        resp.raise_for_status()
    except requests.exceptions.HTTPError as e:
        raise RuntimeError(
            f"HTTP error from Craft World: {e}\nResponse text:\n{resp.text}"
        )

    data = resp.json()
    if "errors" in data:
        raise RuntimeError(
            "GraphQL errors from Craft World:\n"
            + json.dumps(data["errors"], indent=2)
        )
    return data["data"]


# ============================================================
# Queries
# ============================================================

# Single masterpiece – includes resources, leaderboard and your profile
MASTERPIECE_DETAILS_QUERY = """
query MasterpieceDetails($id: ID!, $userId: String!) {
  masterpiece(id: $id) {
    id
    name
    type
    collectedPoints
    requiredPoints
    addressableLabel
    resources {
      symbol
      amount
      target
      consumedPowerPerUnit
    }
    leaderboard {
      position
      masterpiecePoints
      profile {
        uid
        walletAddress
        avatarUrl
        displayName
      }
    }
    profileByUserId(userId: $userId) {
      position
      masterpiecePoints
      profile {
        uid
        walletAddress
        avatarUrl
        displayName
      }
    }
    resourcesByUserId(userId: $userId) {
      symbol
      amount
    }
  }
}
"""

# predictReward – this is the one you tested:
MASTERPIECE_REWARDS_FOR_RESOURCES_QUERY = """
query MasterpieceRewardsForResources(
  $masterpieceId: ID!
  $resources: [ResourceInput!]!
) {
  masterpiece(id: $masterpieceId) {
    id
    predictReward(resources: $resources) {
      masterpiecePoints
      experiencePoints
      requiredPower
      resources {
        symbol
        amount
      }
    }
  }
}
"""

# No args – baseSymbol comes back as COIN
EXCHANGE_PRICES_QUERY = """
query ExchangePrices {
  exchangePriceList {
    baseSymbol
    prices {
      referenceSymbol
      amount
      recommendation
    }
  }
}
"""


# ============================================================
# Small helpers
# ============================================================

def _get_masterpiece_details(masterpiece_id: int, user_id: str) -> Dict[str, Any]:
    data = graphql_request(
        MASTERPIECE_DETAILS_QUERY,
        {"id": str(masterpiece_id), "userId": user_id},
    )
    mp = data.get("masterpiece")
    if mp is None:
        raise RuntimeError(f"No masterpiece found for id={masterpiece_id}")
    return mp


def _get_exchange_prices_coin() -> Dict[str, float]:
    """
    Returns { SYMBOL -> price_in_COIN_per_1_unit }.

    The response looks like:
      baseSymbol: "COIN"
      prices: [ { referenceSymbol: "EARTH", amount: 0.00229, ... }, ... ]

    We interpret `amount` as COIN per 1 unit of the resource.
    """
    data = graphql_request(EXCHANGE_PRICES_QUERY)
    ex = data.get("exchangePriceList") or {}
    prices = ex.get("prices") or []
    result: Dict[str, float] = {}
    for p in prices:
        sym = p.get("referenceSymbol")
        amt = p.get("amount")
        if sym and isinstance(amt, (int, float)):
            result[sym.upper()] = float(amt)
    return result


def _get_points_and_power_per_unit(masterpiece_id: int, symbol: str) -> tuple[float, float]:
    """
    Uses predictReward to calculate:
      points_per_unit, battery_per_unit
    for donating exactly 1 unit of `symbol` to this masterpiece.
    """
    variables = {
        "masterpieceId": str(masterpiece_id),
        "resources": [
            {"symbol": symbol.upper(), "amount": 1}
        ],
    }
    data = graphql_request(MASTERPIECE_REWARDS_FOR_RESOURCES_QUERY, variables)
    mp = data.get("masterpiece") or {}
    pr = mp.get("predictReward") or {}
    points = float(pr.get("masterpiecePoints") or 0.0)
    power = float(pr.get("requiredPower") or 0.0)
    return points, power


# ============================================================
# Core entry point for the APP
# ============================================================

def plan_cheapest_combo(masterpiece_id: int, target_rank: int, user_id: str | None = None) -> str:
    """
    Main function your GUI can call.

    Inputs:
      - masterpiece_id: e.g. 31
      - target_rank: rank you want to snipe (1, 3, 10, etc.)
      - user_id: your Voya UID (if None, uses DEFAULT_USER_ID)

    Returns:
      - A big multi-line string explaining:
          * points gap
          * single-resource options
          * cheapest multi-resource combo
          * COIN + battery usage
      - Or an error string starting with "Error:" if something goes wrong
    """
    if user_id is None or user_id.strip() == "":
        user_id = DEFAULT_USER_ID

    try:
        mp = _get_masterpiece_details(masterpiece_id, user_id)
        name = mp.get("name")
        collected_points = mp.get("collectedPoints")
        required_points = mp.get("requiredPoints")

        leaderboard: List[Dict[str, Any]] = mp.get("leaderboard") or []
        profile = mp.get("profileByUserId") or {}
        your_points = float(profile.get("masterpiecePoints") or 0.0)
        your_pos = profile.get("position")

        # Find target entry on leaderboard
        target_entry = None
        for row in leaderboard:
            if row.get("position") == target_rank:
                target_entry = row
                break

        lines: List[str] = []

        if not target_entry:
            max_pos = leaderboard[-1]["position"] if leaderboard else "none"
            lines.append(f"Error: No leaderboard entry found for position {target_rank}.")
            lines.append(f"Highest position in current data: {max_pos}")
            return "\n".join(lines)

        target_points = float(target_entry.get("masterpiecePoints") or 0.0)
        points_needed = max(0.0, target_points - your_points)

        lines.append("=" * 70)
        lines.append(f"Masterpiece {masterpiece_id}: {name}")
        lines.append("-" * 70)
        lines.append(f"Required total masterpiece points: {required_points:,}")
        lines.append(f"Total collected points:           {collected_points:,}")
        lines.append(f"Your current points:              {your_points:,.0f}")
        lines.append(f"Your current position:            {your_pos}")
        lines.append(f"Target position:                  {target_rank}")
        lines.append(f"Target points (pos {target_rank}): {target_points:,.0f}")
        lines.append(f"Additional points needed:         {points_needed:,.0f}")
        lines.append("=" * 70)

        if points_needed <= 0:
            lines.append("")
            lines.append("You already have enough points for that position (or higher).")
            return "\n".join(lines)

        # 2) COIN prices
        lines.append("Fetching COIN-based prices (exchangePriceList)...")
        prices_coin = _get_exchange_prices_coin()
        if not prices_coin:
            lines.append("Error: Failed to get any prices from exchangePriceList.")
            return "\n".join(lines)

        # 3) Build resource options with remaining capacity
        resources = mp.get("resources") or []
        options = []

        lines.append("")
        lines.append("Analyzing each resource via predictReward(1 unit)...")
        lines.append("")

        for r in resources:
            sym = (r.get("symbol") or "").upper()
            donated = float(r.get("amount") or 0.0)
            target_amt = float(r.get("target") or 0.0)
            remaining = max(0.0, target_amt - donated)

            if remaining <= 0:
                continue  # no room left for this resource

            price_coin = prices_coin.get(sym)
            if price_coin is None:
                continue  # no price info

            points_per_unit, power_per_unit = _get_points_and_power_per_unit(masterpiece_id, sym)
            if points_per_unit <= 0:
                continue

            options.append({
                "symbol": sym,
                "remaining": remaining,
                "points_per_unit": points_per_unit,
                "power_per_unit": power_per_unit,
                "price_coin": price_coin,
            })

        if not options:
            lines.append("Error: No usable resources found (no remaining caps, price or points).")
            return "\n".join(lines)

        # 4) Check if it's even possible with ALL resources
        max_possible_points = sum(o["remaining"] * o["points_per_unit"] for o in options)

        if max_possible_points < points_needed:
            lines.append("")
            lines.append("❌ Not possible to reach that position with remaining donation caps.")
            lines.append(f"Max possible points from ALL resources: {max_possible_points:,.0f}")
            lines.append(f"Points needed:                          {points_needed:,.0f}")
            lines.append("Try another position.")
            return "\n".join(lines)

        # 5) Greedy cheapest combo: sort by COIN per point
        for o in options:
            o["coin_per_point"] = o["price_coin"] / o["points_per_unit"]

        options.sort(key=lambda o: o["coin_per_point"])

        remaining_points = points_needed
        combo = []

        for o in options:
            if remaining_points <= 0:
                break

            max_units_for_points = math.ceil(remaining_points / o["points_per_unit"])
            units = min(max_units_for_points, int(o["remaining"]))

            if units <= 0:
                continue

            gain = units * o["points_per_unit"]
            coin_cost = units * o["price_coin"]
            battery_cost = units * o["power_per_unit"]

            combo.append({
                "symbol": o["symbol"],
                "units": units,
                "points_gain": gain,
                "coin_cost": coin_cost,
                "battery_cost": battery_cost,
                "points_per_unit": o["points_per_unit"],
                "power_per_unit": o["power_per_unit"],
                "price_coin": o["price_coin"],
            })

            remaining_points -= gain

        if remaining_points > 0:
            # Should only happen due to rounding, but we handle it anyway.
            lines.append("")
            lines.append("⚠️ Greedy combo didn’t quite cover all points (rounding issue).")
            lines.append(f"Still missing ≈ {remaining_points:,.0f} points.")
            lines.append("You’re very close — try slightly overshooting with one resource.")
            return "\n".join(lines)

        total_points = sum(c["points_gain"] for c in combo)
        total_coin = sum(c["coin_cost"] for c in combo)
        total_battery = sum(c["battery_cost"] for c in combo)

        # 6) Single-resource scenarios for reference
        single_resource_options = []
        for o in options:
            points_per_unit = o["points_per_unit"]
            price_coin = o["price_coin"]
            remaining = o["remaining"]

            units_needed_exact = points_needed / points_per_unit
            units_needed = math.ceil(units_needed_exact)

            if units_needed > remaining:
                reachable = False
                units_used = remaining
                points_gain = remaining * points_per_unit
            else:
                reachable = True
                units_used = units_needed
                points_gain = units_used * points_per_unit

            total_coin_cost = units_used * price_coin
            total_battery_cost = units_used * o["power_per_unit"]

            single_resource_options.append({
                "symbol": o["symbol"],
                "reachable": reachable,
                "units_used": units_used,
                "units_needed_exact": units_needed_exact,
                "points_gain": points_gain,
                "coin_cost": total_coin_cost,
                "battery_cost": total_battery_cost,
            })

        single_resource_options.sort(key=lambda x: x["coin_cost"])

        # 7) Single-resource block
        lines.append("")
        lines.append("--- Single-resource options (if you used ONLY this resource) ---")
        lines.append("")
        for s in single_resource_options:
            reachable_text = "YES" if s["reachable"] else "NO (cap-limited)"
            lines.append("-" * 70)
            lines.append(f"Resource:        {s['symbol']}")
            lines.append(f"Reach target?    {reachable_text}")
            lines.append(f"Units used:      {s['units_used']:.0f}")
            lines.append(f"Exact units req: {s['units_needed_exact']:.3f}")
            lines.append(f"Points gained:   {s['points_gain']:,.0f}")
            lines.append(f"COIN cost:       {s['coin_cost']:,.4f}")
            lines.append(f"Battery used:    {s['battery_cost']:,.2f}")

        # 8) Combo block
        lines.append("")
        lines.append("=" * 70)
        lines.append("💡 Cheapest multi-resource combo (greedy by COIN per point)")
        lines.append("=" * 70)
        lines.append("")

        for c in combo:
            lines.append("-" * 70)
            lines.append(f"Donate:         {c['units']} x {c['symbol']}")
            lines.append(f"Points / unit:  {c['points_per_unit']:.0f}")
            lines.append(f"COIN / unit:    {c['price_coin']:.6f}")
            lines.append(f"Battery / unit: {c['power_per_unit']:.2f}")
            lines.append(f"Total points:   {c['points_gain']:,.0f}")
            lines.append(f"Total COIN:     {c['coin_cost']:,.4f}")
            lines.append(f"Total battery:  {c['battery_cost']:,.2f}")

        lines.append("")
        lines.append("-" * 70)
        lines.append(f"Target rank:           {target_rank}")
        lines.append(f"Points needed:         {points_needed:,.0f}")
        lines.append(f"Combo total points:    {total_points:,.0f}")
        lines.append(f"Combo total COIN:      {total_coin:,.4f}")
        lines.append(f"Combo total battery:   {total_battery:,.2f}")
        lines.append("-" * 70)
        lines.append("Battery note: you have 150 max, +25 every 30 minutes in-game;")
        lines.append("compare 'Combo total battery' to what you’ll actually have.")
        lines.append("")

        return "\n".join(lines)

    except Exception as e:
        return "Error while planning masterpiece snipe:\n" + str(e)


# ============================================================
# Optional CLI for quick testing
# ============================================================

if __name__ == "__main__":
    print("=== Masterpiece Sniper Planner (standalone) ===")
    mp_str = input("Masterpiece ID (e.g. 31): ").strip()
    rank_str = input("Target rank (e.g. 1 or 3): ").strip()
    user_str = input(f"UserId (blank for default {DEFAULT_USER_ID}): ").strip()

    try:
        mp_id = int(mp_str)
        rank = int(rank_str)
    except ValueError:
        print("Invalid masterpiece ID or rank.")
        sys.exit(1)

    if not user_str:
        user_str = DEFAULT_USER_ID

    out = plan_cheapest_combo(mp_id, rank, user_str)
    print()
    print(out)
