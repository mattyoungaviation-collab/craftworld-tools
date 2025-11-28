import os
import json
from typing import Any, Dict, List, Optional

import requests

GRAPHQL_URL = "https://craft-world.gg/graphql"


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


def call_graphql(query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Low-level helper to call Craft World's GraphQL API with the JWT.
    Returns the `data` field or raises RuntimeError on errors.
    """
    headers = {
        "Authorization": f"Bearer {get_jwt()}",
        "Content-Type": "application/json",
        # IMPORTANT: must be >= minAppVersion from server (currently 1.5.1)
        "x-app-version": "1.5.1",
    }

    payload: Dict[str, Any] = {"query": query}
    if variables is not None:
        payload["variables"] = variables

    try:
        resp = requests.post(GRAPHQL_URL, json=payload, headers=headers, timeout=20)
        resp.raise_for_status()
    except requests.exceptions.HTTPError as e_http:
        # Try to include JSON error details if present
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
        data = resp.json()
    except Exception as e_json:
        raise RuntimeError(f"Invalid JSON from Craft World: {e_json}\nResponse: {resp.text}") from e_json

    if "errors" in data and data["errors"]:
        raise RuntimeError(f"GraphQL errors: {json.dumps(data['errors'], indent=2)}")

    if "data" not in data:
        raise RuntimeError(f"GraphQL response missing 'data': {json.dumps(data, indent=2)}")

    return data["data"]


def fetch_proficiencies() -> dict[str, dict]:
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
    query AccountProficiencies {
      account {
        proficiencies {
          symbol
          collectedAmount
          claimedLevel
        }
      }
    }
    """

    data = call_graphql(query, None)
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


def fetch_workshop_levels() -> dict[str, int]:
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
    query AccountWorkshop {
      account {
        workshop {
          symbol
          level
        }
      }
    }
    """

    data = call_graphql(query, None)
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


def fetch_masterpieces() -> List[Dict[str, Any]]:
    """
    Fetch current Masterpieces info + leaderboard (all entries).
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
      }
    }
    """
    data = call_graphql(query, None)
    return data.get("masterpieces") or []


def fetch_masterpiece_details(masterpiece_id: int | str) -> Dict[str, Any]:
    """
    Fetch a single masterpiece with resources + leaderboard.
    """
    query = """
    query MasterpieceDetails($id: ID!) {
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
      }
    }
    """
    data = call_graphql(query, {"id": str(masterpiece_id)})
    mp = data.get("masterpiece")
    if mp is None:
        raise RuntimeError(f"No masterpiece found for id={masterpiece_id}")
    return mp


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
