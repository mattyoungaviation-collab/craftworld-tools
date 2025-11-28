import os
import sys
import math
import json
import requests

GRAPHQL_ENDPOINT = "https://craft-world.gg/graphql"

# 👇 Change this if you ever want to run it for a different account by default
DEFAULT_USER_ID = "GfUeRBCZv8OwuUKq7Tu9JVpA70l1"


# ============================================================
# Low-level helper: GraphQL request with JWT
# ============================================================

def graphql_request(query: str, variables: dict | None = None) -> dict:
    jwt = os.getenv("CRAFTWORLD_JWT")
    if not jwt:
        print("ERROR: CRAFTWORLD_JWT environment variable is not set.")
        print("Set it in PowerShell, e.g.:")
        print('  $env:CRAFTWORLD_JWT = "jwt_eyJhbGciOi..."')
        sys.exit(1)

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {jwt}",
    }
    payload = {"query": query, "variables": variables or {}}

    resp = requests.post(GRAPHQL_ENDPOINT, headers=headers, json=payload)
    try:
        resp.raise_for_status()
    except requests.exceptions.HTTPError as e:
        print(f"HTTP error from Craft World: {e}")
        print("Response text:")
        print(resp.text)
        sys.exit(1)

    data = resp.json()
    if "errors" in data:
        print("GraphQL errors from Craft World:")
        print(json.dumps(data["errors"], indent=2))
        sys.exit(1)
    return data["data"]


# ============================================================
# Queries
# ============================================================

MASTERPIECE_DETAILS_QUERY = """
query MasterpieceDetails($id: ID!, $userId: String!) {
  masterpiece(id: $id) {
    id
    name
    type
    collectedPoints
    requiredPoints
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
        displayName
      }
    }
    profileByUserId(userId: $userId) {
      position
      masterpiecePoints
      profile {
        uid
        displayName
      }
    }
  }
}
"""

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

# ✅ No arguments — baseSymbol is part of the response, not an input
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
# High-level fetchers
# ============================================================

def get_masterpiece_details(masterpiece_id: int, user_id: str) -> dict:
    data = graphql_request(
        MASTERPIECE_DETAILS_QUERY,
        {"id": str(masterpiece_id), "userId": user_id},
    )
    mp = data.get("masterpiece")
    if mp is None:
        print(f"No masterpiece found for id={masterpiece_id}")
        sys.exit(1)
    return mp


def get_exchange_prices_coin() -> dict:
    """
    Returns a dict: { SYMBOL -> price_in_COIN_per_1_unit }

    Uses exchangePriceList (baseSymbol = COIN).
    """
    data = graphql_request(EXCHANGE_PRICES_QUERY)
    ex = data.get("exchangePriceList") or {}
    prices = ex.get("prices") or []
    result = {}
    for p in prices:
        sym = p.get("referenceSymbol")
        amt = p.get("amount")
        if sym and isinstance(amt, (int, float)):
            result[sym.upper()] = float(amt)
    return result


def get_points_and_power_per_unit(masterpiece_id: int, symbol: str) -> tuple[float, float]:
    """
    Uses predictReward to calculate:
      points_per_unit, battery_per_unit
    for donating exactly 1 unit of `symbol` to this masterpiece.
    """
    vars_ = {
        "masterpieceId": str(masterpiece_id),
        "resources": [
            {"symbol": symbol.upper(), "amount": 1}
        ],
    }
    data = graphql_request(MASTERPIECE_REWARDS_FOR_RESOURCES_QUERY, vars_)
    mp = data.get("masterpiece") or {}
    pr = mp.get("predictReward") or {}
    points = float(pr.get("masterpiecePoints") or 0.0)
    power = float(pr.get("requiredPower") or 0.0)
    return points, power


# ============================================================
# Core analysis (multi-resource combo)
# ============================================================

def analyze_masterpiece_cheapest_combo(masterpiece_id: int, target_rank: int, user_id: str = DEFAULT_USER_ID):
    # 1) Fetch base data
    mp = get_masterpiece_details(masterpiece_id, user_id)
    name = mp.get("name")
    collected_points = mp.get("collectedPoints")
    required_points = mp.get("requiredPoints")

    leaderboard = mp.get("leaderboard") or []
    profile = mp.get("profileByUserId") or {}
    your_points = float(profile.get("masterpiecePoints") or 0.0)
    your_pos = profile.get("position")

    # 2) Determine target points for chosen rank
    target_entry = None
    for row in leaderboard:
        if row.get("position") == target_rank:
            target_entry = row
            break

    if not target_entry:
        print(f"No leaderboard entry found for position {target_rank}.")
        print(f"Highest position in data: {leaderboard[-1]['position'] if leaderboard else 'none'}")
        sys.exit(1)

    target_points = float(target_entry.get("masterpiecePoints") or 0.0)
    points_needed = max(0.0, target_points - your_points)

    print("=" * 70)
    print(f"Masterpiece {masterpiece_id}: {name}")
    print("-" * 70)
    print(f"Required total masterpiece points: {required_points:,}")
    print(f"Total collected points:           {collected_points:,}")
    print(f"Your current points:              {your_points:,.0f}")
    print(f"Your current position:            {your_pos}")
    print(f"Target position:                  {target_rank}")
    print(f"Target points (pos {target_rank}): {target_points:,.0f}")
    print(f"Additional points needed:         {points_needed:,.0f}")
    print("=" * 70)

    if points_needed <= 0:
        print("You already have enough points for that position (or higher).")
        return

    # 3) Fetch COIN prices
    print("Fetching COIN-based prices (exchangePriceList)...")
    prices_coin = get_exchange_prices_coin()
    if not prices_coin:
        print("Failed to get any prices from exchangePriceList.")
        sys.exit(1)

    # 4) Build resource options: remaining capacity, points/unit, power/unit, price in COIN
    resources = mp.get("resources") or []
    options = []

    print("Analyzing each resource via predictReward (1 unit)...\n")

    for r in resources:
        sym = (r.get("symbol") or "").upper()
        donated = float(r.get("amount") or 0.0)
        target = float(r.get("target") or 0.0)
        remaining = max(0.0, target - donated)

        if remaining <= 0:
            # no room left for this resource
            continue

        price_coin = prices_coin.get(sym)
        if price_coin is None:
            # no price info, skip
            continue

        points_per_unit, power_per_unit = get_points_and_power_per_unit(masterpiece_id, sym)
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
        print("No usable resources found (no remaining donation room or no price/points data).")
        return

    # 5) Check if it's even possible with ALL resources
    max_possible_points = sum(
        o["remaining"] * o["points_per_unit"] for o in options
    )

    if max_possible_points < points_needed:
        print("❌ Not possible to reach that position with remaining donation caps.")
        print(f"Max possible points from ALL resources: {max_possible_points:,.0f}")
        print(f"Points needed:                          {points_needed:,.0f}")
        print("Try a lower position.")
        return

    # 6) Greedy cheapest-combo algorithm
    # Sort by COIN cost per point (lower = better)
    for o in options:
        o["coin_per_point"] = o["price_coin"] / o["points_per_unit"]

    options.sort(key=lambda o: o["coin_per_point"])

    remaining_points = points_needed
    combo = []

    for o in options:
        if remaining_points <= 0:
            break

        # max units needed from this resource to cover remaining points
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

    # Safety: if still not enough (shouldn’t happen with the check above, but just in case)
    if remaining_points > 0:
        print("⚠️ Greedy combo failed to fully cover points (rounding issue).")
        print(f"Still missing about {remaining_points:,.0f} points.")
        print("But you are very close — try slightly overshooting with one resource.")
        return

    total_points = sum(c["points_gain"] for c in combo)
    total_coin = sum(c["coin_cost"] for c in combo)
    total_battery = sum(c["battery_cost"] for c in combo)

    # 7) Also compute “single-resource only” scenarios for reference
    single_resource_options = []
    for o in options:
        points_per_unit = o["points_per_unit"]
        price_coin = o["price_coin"]
        remaining = o["remaining"]
        # how many units to reach points_needed if only this resource
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

    # 8) Print single-resource summary
    print("\n--- Single-resource options (if you used ONLY this one resource) ---\n")
    for s in single_resource_options:
        reachable_text = "YES" if s["reachable"] else "NO (cap-limited)"
        print("-" * 70)
        print(f"Resource:        {s['symbol']}")
        print(f"Reach target?    {reachable_text}")
        print(f"Units used:      {s['units_used']:.0f}")
        print(f"Exact units req: {s['units_needed_exact']:.3f}")
        print(f"Points gained:   {s['points_gain']:,.0f}")
        print(f"COIN cost:       {s['coin_cost']:,.4f}")
        print(f"Battery used:    {s['battery_cost']:,.2f}")

    # 9) Print combo plan
    print("\n======================================================================")
    print("💡 Cheapest multi-resource combo (greedy by COIN per point)")
    print("======================================================================\n")

    for c in combo:
        print("-" * 70)
        print(f"Donate:         {c['units']} x {c['symbol']}")
        print(f"Points / unit:  {c['points_per_unit']:.0f}")
        print(f"COIN / unit:    {c['price_coin']:.6f}")
        print(f"Battery / unit: {c['power_per_unit']:.2f}")
        print(f"Total points:   {c['points_gain']:,.0f}")
        print(f"Total COIN:     {c['coin_cost']:,.4f}")
        print(f"Total battery:  {c['battery_cost']:,.2f}")

    print("\n---------------------------------------------------------------------")
    print(f"Target rank:           {target_rank}")
    print(f"Points needed:         {points_needed:,.0f}")
    print(f"Combo total points:    {total_points:,.0f}")
    print(f"Combo total COIN:      {total_coin:,.4f}")
    print(f"Combo total battery:   {total_battery:,.2f}")
    print("---------------------------------------------------------------------")
    print("If you want to factor in battery limits (150 max, +25 per 30 minutes),")
    print("you can compare 'Combo total battery' vs what you’ll realistically have.")
    print()


# ============================================================
# Main entry point
# ============================================================

def main():
    print("=== Craft World Masterpiece Sniper (Cheapest Combo) ===")
    print("Uses CRAFTWORLD_JWT from your environment.")
    print()

    # Masterpiece ID
    mp_id_str = input("Enter masterpiece ID (e.g. 31 for Neptune Rocket): ").strip()
    try:
        mp_id = int(mp_id_str)
    except ValueError:
        print("Invalid masterpiece ID.")
        return

    # Target rank
    rank_str = input("Enter target rank (e.g. 1 for 1st, 3 for 3rd, etc.): ").strip()
    try:
        rank = int(rank_str)
    except ValueError:
        print("Invalid rank.")
        return

    # UserId (default to your UID, but allow override)
    user_id = input(f"Enter userId (press Enter to use default {DEFAULT_USER_ID}): ").strip()
    if not user_id:
        user_id = DEFAULT_USER_ID

    analyze_masterpiece_cheapest_combo(mp_id, rank, user_id)


if __name__ == "__main__":
    main()
