"""Normalize rich Masterpiece GraphQL responses for page rendering."""

from __future__ import annotations

from typing import Any


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def normalize_masterpiece_detail(masterpiece: dict[str, Any] | None) -> dict[str, Any]:
    """Return a display-friendly shape from a rich Masterpiece response."""
    mp = masterpiece or {}
    collected = _num(mp.get("collectedPoints"))
    required = _num(mp.get("requiredPoints"))
    completion = mp.get("completionPercentage")
    if completion is None:
        completion = (collected / required * 100.0) if required else 0.0

    resources = []
    for row in mp.get("resources") or []:
        amount = _num(row.get("amount"))
        target = _num(row.get("target"))
        pct = (amount / target * 100.0) if target else 0.0
        power_costs = []
        for pc in row.get("powerCosts") or []:
            power_costs.append(
                {
                    "amount": _int(pc.get("amount")),
                    "powerCostPerUnit": _int(pc.get("powerCostPerUnit")),
                }
            )
        resources.append(
            {
                "symbol": str(row.get("symbol") or "").upper(),
                "amount": amount,
                "target": target,
                "remaining": max(target - amount, 0.0),
                "completionPercentage": pct,
                "consumedPowerPerUnit": _int(row.get("consumedPowerPerUnit")),
                "powerCosts": power_costs,
            }
        )

    leaderboard = []
    for row in mp.get("leaderboard") or []:
        profile = row.get("profile") or {}
        leaderboard.append(
            {
                "position": _int(row.get("position")),
                "masterpiecePoints": _num(row.get("masterpiecePoints")),
                "uid": profile.get("uid"),
                "walletAddress": profile.get("walletAddress"),
                "avatarUrl": profile.get("avatarUrl"),
                "displayName": profile.get("displayName") or profile.get("walletAddress") or "Unknown",
            }
        )

    user_profile = mp.get("profileByUserId") or {}
    user_resources = []
    for row in mp.get("resourcesByUserId") or []:
        user_resources.append({"symbol": str(row.get("symbol") or "").upper(), "amount": _num(row.get("amount"))})

    daily_power = []
    for row in mp.get("dailyPowerContributionsByUserId") or []:
        daily_power.append({"symbol": str(row.get("symbol") or "").upper(), "amount": _num(row.get("amount"))})

    return {
        "id": mp.get("id"),
        "name": mp.get("name"),
        "type": mp.get("type"),
        "eventId": mp.get("eventId"),
        "addressableLabel": mp.get("addressableLabel"),
        "collectedPoints": collected,
        "requiredPoints": required,
        "completionPercentage": _num(completion),
        "startedAt": mp.get("startedAt"),
        "endsAt": mp.get("endsAt"),
        "resources": resources,
        "leaderboard": leaderboard,
        "rewardStages": mp.get("rewardStages") or [],
        "leaderboardRewards": mp.get("leaderboardRewards") or [],
        "milestones": mp.get("milestones") or [],
        "profileByUserId": user_profile,
        "resourcesByUserId": user_resources,
        "dailyPowerContributionsByUserId": daily_power,
    }
