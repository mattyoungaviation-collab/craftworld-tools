import os
import json
import logging
from typing import Any, Dict, List, Optional

import requests

GRAPHQL_URL = "https://craft-world.gg/graphql"
LOGGER = logging.getLogger(__name__)


def _mask_token(token: Optional[str]) -> str:
    if not token:
        return "<missing>"
    if len(token) <= 16:
        return token[:4] + "..."
    return f"{token[:10]}...{token[-6:]}"




def _normalize_cw_token(token: Optional[str]) -> str:
    value = (token or "").strip()
    if not value:
        return value
    if value.startswith("jwt_"):
        return value
    if value.count(".") >= 2:
        return f"jwt_{value}"
    return value

def call_graphql_with_jwt(jwt_token: str, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Low-level helper to call Craft World's GraphQL API with a provided JWT.
    Returns the full decoded response JSON.
    """
    normalized_token = _normalize_cw_token(jwt_token)
    headers = {
        "Authorization": f"Bearer {normalized_token}",
        "Content-Type": "application/json",
        # IMPORTANT: must be >= minAppVersion from server (currently 1.6.2)
        "x-app-version": "1.6.2",
    }

    payload: Dict[str, Any] = {"query": query}
    if variables is not None:
        payload["variables"] = variables

    try:
        resp = requests.post(GRAPHQL_URL, json=payload, headers=headers, timeout=20)
        resp.raise_for_status()
    except requests.exceptions.HTTPError as e_http:
        try:
            err_json = resp.json()
            raise RuntimeError(
                f"HTTP {resp.status_code} from Craft World: {e_http}\n"
                f"Response: {json.dumps(err_json, indent=2)}"
            ) from e_http
        except Exception:
            raise RuntimeError(
                f"HTTP {resp.status_code} from Craft World: {e_http}\n"
                f"Raw response: {resp.text}"
            ) from e_http
    except Exception as e:
        raise RuntimeError(f"Network error calling Craft World GraphQL: {e}") from e

    try:
        return resp.json()
    except Exception as e_json:
        raise RuntimeError(f"Invalid JSON from Craft World: {e_json}\nResponse: {resp.text}") from e_json


def get_jwt() -> str:
    """
    Read CRAFTWORLD_JWT from the environment.
    """
    token = os.environ.get("CRAFTWORLD_JWT")
    if not token:
        raise RuntimeError(
            "CRAFTWORLD_JWT environment variable is not set.\n\n"
            "You must export your Craft World JWT first.\n"
            "Examples:\n"
            "  PowerShell:\n"
            '    $env:CRAFTWORLD_JWT = "<your-jwt-token>"\n\n'
            "  CMD:\n"
            "    set CRAFTWORLD_JWT=<your-jwt-token>\n\n"
            "  bash:\n"
            '    export CRAFTWORLD_JWT="<your-jwt-token>"\n'
        )
    return token


def call_graphql(
    query: str,
    variables: Optional[Dict[str, Any]] = None,
    bearer_token: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Low-level helper to call Craft World's GraphQL API with the JWT.
    Returns the `data` field or raises RuntimeError on errors.
    """
    jwt_token = _normalize_cw_token(bearer_token) if bearer_token else _normalize_cw_token(get_jwt())
    if bearer_token:
        LOGGER.debug(
            "call_graphql using per-user bearer token (len=%s, token=%s)",
            len(bearer_token),
            _mask_token(bearer_token),
        )
    data = call_graphql_with_jwt(jwt_token, query, variables)

    if "errors" in data and data["errors"]:
        LOGGER.warning("GraphQL upstream errors: %s", json.dumps(data["errors"], ensure_ascii=False))
        raise RuntimeError(f"GraphQL errors: {json.dumps(data['errors'], indent=2)}")

    if "data" not in data:
        raise RuntimeError(f"GraphQL response missing 'data': {json.dumps(data, indent=2)}")

    return data["data"]


def fetch_proficiencies(bearer_token: Optional[str] = None) -> dict[str, dict]:
    """
    Fetch account proficiencies (mastery) for all symbols.

    Returns a dict shaped like:
      {
        "MUD": {"collectedAmount": 15688752, "claimedLevel": 10},
        "GLASS": {"collectedAmount": 165, "claimedLevel": 3},
        ...
      }
    """
    query = """
    query {
      account {
        proficiencies { symbol collectedAmount claimedLevel }
      }
    }
    """

    data = call_graphql(query, None, bearer_token=bearer_token)
    account = data.get("account") or {}
    profs = account.get("proficiencies") or []

    result: dict[str, dict] = {}
    for p in profs:
        symbol = (p.get("symbol") or "").upper()
        if not symbol:
            continue
        result[symbol] = {
            "collectedAmount": float(p.get("collectedAmount") or 0),
            "claimedLevel": int(p.get("claimedLevel") or 0),
        }
    return result


def fetch_profile_by_uid(uid: str) -> Dict[str, Any]:
    """
    Fetch Craft World profile for a given UID (avatar, display name, badges, etc).
    """
    query = """
    query ProfileByUID($uid: ID!) {
      profileByUID(uid: $uid) {
        uid
        walletAddress
        avatarUrl
        displayName
        level
        badges {
          url
          description
          displayName
          infoUrl
        }
      }
    }
    """
    data = call_graphql(query, {"uid": uid})
    return data.get("profileByUID") or {}


# 👇👇 ADD THIS BLOCK *RIGHT HERE* 👇👇
def fetch_available_avatars(bearer_token: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Fetch the list of avatars available for the current account.

    Returns a list like:
      [
        { "avatarUrl": "...", "isEns": False },
        ...
      ]
    """
    query = """
    query AccountAvailableAvatars {
      account {
        availableAvatars {
          avatarUrl
          isEns
        }
      }
    }
    """
    data = call_graphql(query, None, bearer_token=bearer_token)
    account = data.get("account") or {}
    return account.get("availableAvatars") or []
# 👆👆 END NEW BLOCK 👆👆


def fetch_workshop_levels(bearer_token: Optional[str] = None) -> dict[str, int]:
    """
    Fetch workshop levels for all workshop-enabled resources.

    Returns a dict like:
      {
        "MUD": 2,
        "CLAY": 5,
        "SCREWS": 8,
        ...
      }
    """
    query = """
    query {
      account {
        workshop { symbol level }
      }
    }
    """

    data = call_graphql(query, None, bearer_token=bearer_token)
    account = data.get("account") or {}
    ws_list = account.get("workshop") or []

    result: dict[str, int] = {}
    for w in ws_list:
        symbol = (w.get("symbol") or "").upper()
        if not symbol:
            continue
        level = int(w.get("level") or 0)
        result[symbol] = level
    return result


def fetch_account_status(bearer_token: Optional[str] = None) -> Dict[str, Any]:
    """Fetch account power/refill status for the currently authenticated user."""
    query = """
    query AccountStatus {
      account {
        power
        powerMillisecondsUntilRefill
        powerLastRefill
        updatedAt
      }
    }
    """

    data = call_graphql(query, None, bearer_token=bearer_token)
    account = data.get("account") or {}
    return {
        "power": int(account.get("power") or 0),
        "powerMillisecondsUntilRefill": int(account.get("powerMillisecondsUntilRefill") or 0),
        "powerLastRefill": account.get("powerLastRefill"),
        "updatedAt": account.get("updatedAt"),
    }

def fetch_craftworld(uid: str) -> Dict[str, Any]:
    """
    Fetch full Craft World account data by Voya UID.
    """
    query = """
    query FetchCraftWorld($uid: ID!) {
      fetchCraftWorld(uid: $uid) {
        landPlots {
          areas {
            symbol
            factories {
              factory {
                level
                definition { id }
              }
            }
          }
        }
        mines {
          level
          definition { id }
        }
        dynos {
          meta { displayName rarity }
          production { amount symbol }
        }
        resources {
          symbol
          amount
        }
      }
    }
    """
    data = call_graphql(query, {"uid": uid})
    return data["fetchCraftWorld"]

def fetch_masterpieces() -> list[dict]:
    """
    Fetch a lightweight list of all masterpieces.
    The current masterpiece is the last with a non-null collectedPoints.
    """
    query = """
    query Masterpieces {
      masterpieces {
        id
        name
        type
        eventId
        collectedPoints
        requiredPoints
        addressableLabel
        startedAt
      }
    }
    """

    data = call_graphql(query)
    masterpieces = data.get("masterpieces") or []

    all_masterpieces: list[dict] = []
    for mp in masterpieces:
        all_masterpieces.append(
            {
                "id": int(mp.get("id") or 0),
                "name": mp.get("name"),
                "type": mp.get("type"),
                "eventId": mp.get("eventId"),
                "collectedPoints": mp.get("collectedPoints"),
                "requiredPoints": mp.get("requiredPoints"),
                "addressableLabel": mp.get("addressableLabel"),
                "startedAt": mp.get("startedAt"),
            }
        )

    # Sort newest first by startedAt
    all_masterpieces.sort(key=lambda m: m.get("startedAt") or "", reverse=True)
    return all_masterpieces





def fetch_masterpiece_details(masterpiece_id: int | str) -> dict:
    """
    Fetch full masterpiece details for the given ID safely.
    """
    if not masterpiece_id:
        return {}

    try:
        data = call_graphql(
            MASTERPIECE_DETAILS_QUERY,
            variables={"id": str(int(masterpiece_id))},
        )
        masterpiece = data.get("masterpiece")
        if not masterpiece:
            raise RuntimeError(f"No masterpiece found for id {masterpiece_id}")
        return masterpiece
    except Exception as e:
        print(f"[ERROR] fetch_masterpiece_details({masterpiece_id}): {e}")
        return {}




MASTERPIECE_DETAILS_QUERY = """
    query Masterpiece($id: ID) {
        masterpiece(id: $id) {
            id
            name
            type
            eventId
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
            rewardStages {
                requiredMasterpiecePoints
                rewards {
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
                }
                battlePassRewards {
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
                }
            }
            leaderboardRewards {
                top
                rewards {
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
                }
            }
            startedAt
        }
    }
"""




def predict_reward(masterpiece_id: int | str, resources: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Call masterpiece.predictReward for an arbitrary list of resources.

    `resources` is a list of { "symbol": SYMBOL, "amount": float }.
    Returns:
      {
        "masterpiecePoints": ...,
        "experiencePoints": ...,
        "requiredPower": ...,
        "resources": [ ... ]
      }
    """
    query = """
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
    variables = {
        "masterpieceId": str(masterpiece_id),
        "resources": resources,
    }
    data = call_graphql(query, variables)
    mp = data.get("masterpiece") or {}
    pr = mp.get("predictReward") or {}
    return pr












