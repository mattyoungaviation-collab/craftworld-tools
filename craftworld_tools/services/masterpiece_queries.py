"""Masterpiece GraphQL queries.

This module holds the richer Masterpiece query that includes milestone,
leaderboard, reward, and per-user contribution data in one request.
"""

from __future__ import annotations

from typing import Any, Optional

from craftworld_tools.services.craftworld_core import call_graphql, fetch_masterpiece_details
from craftworld_tools.services.masterpiece_normalizer import normalize_masterpiece_detail


MASTERPIECE_REWARD_FIELDS = """
__typename
... on Resource {
    symbol
    amount
}
... on Avatar {
    avatarUrl
    isEns
}
... on Badge {
    badgeName
    url
    description
    displayName
    infoUrl
}
... on OnChainToken {
    symbol
    infoUrl
}
... on TradePack {
    amount
}
... on BuildingReward {
    buildingType
    buildingSubType
}
... on PowerPack {
    id
    amount
}
... on BoosterItem {
    id
    amount
}
... on Currency {
    type
    amount
}
... on EggItem {
    definitionId
    amount
}
... on ChestItem {
    definitionId
    amount
}
... on BlueprintRewardItem {
    definitionId
    amount
}
"""


MASTERPIECE_WITH_USER_QUERY = f"""
query Masterpiece($id: ID, $userId: String) {{
  masterpiece(id: $id) {{
    id
    name
    type
    eventId
    collectedPoints
    requiredPoints
    addressableLabel
    resources {{
      symbol
      amount
      target
      consumedPowerPerUnit
      powerCosts {{
        amount
        powerCostPerUnit
      }}
    }}
    leaderboard {{
      position
      masterpiecePoints
      profile {{
        uid
        walletAddress
        avatarUrl
        displayName
      }}
    }}
    rewardStages {{
      requiredMasterpiecePoints
      rewards {{
        {MASTERPIECE_REWARD_FIELDS}
      }}
      battlePassRewards {{
        {MASTERPIECE_REWARD_FIELDS}
      }}
    }}
    leaderboardRewards {{
      top
      rewards {{
        {MASTERPIECE_REWARD_FIELDS}
      }}
    }}
    milestones {{
      id
      percentage
      label
      unlocked
      resources {{
        symbol
        required
      }}
      rewardStages {{
        requiredMasterpiecePoints
        rewards {{
          {MASTERPIECE_REWARD_FIELDS}
        }}
        battlePassRewards {{
          {MASTERPIECE_REWARD_FIELDS}
        }}
      }}
      leaderboardRewards {{
        top
        rewards {{
          {MASTERPIECE_REWARD_FIELDS}
        }}
      }}
    }}
    completionPercentage
    startedAt
    endsAt
    profileByUserId(userId: $userId) {{
      position
      masterpiecePoints
      profile {{
        uid
        walletAddress
        avatarUrl
        displayName
      }}
    }}
    resourcesByUserId(userId: $userId) {{
      symbol
      amount
    }}
    dailyPowerContributionsByUserId(userId: $userId) {{
      symbol
      amount
    }}
  }}
}}
"""


def _with_normalized(masterpiece: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(masterpiece, dict):
        return {}
    enriched = dict(masterpiece)
    enriched["normalized"] = normalize_masterpiece_detail(masterpiece)
    return enriched


def fetch_masterpiece_details_for_user(
    masterpiece_id: int | str,
    user_id: Optional[str] = None,
) -> dict[str, Any]:
    """Fetch rich Masterpiece details, optionally including per-user fields."""
    if not masterpiece_id:
        return {}

    clean_user_id = str(user_id or "").strip()
    if not clean_user_id:
        return _with_normalized(fetch_masterpiece_details(masterpiece_id))

    try:
        data = call_graphql(
            MASTERPIECE_WITH_USER_QUERY,
            variables={"id": str(int(masterpiece_id)), "userId": clean_user_id},
        )
        masterpiece = data.get("masterpiece")
        if not masterpiece:
            raise RuntimeError(f"No masterpiece found for id {masterpiece_id}")
        return _with_normalized(masterpiece)
    except Exception as exc:
        # Fall back to the older stable query so the page still loads if Craft
        # World's schema changes or the user-specific fields reject null/typing.
        print(f"[WARN] rich masterpiece query failed for {masterpiece_id}: {exc}")
        return _with_normalized(fetch_masterpiece_details(masterpiece_id))
