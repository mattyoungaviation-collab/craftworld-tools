"""Craft World identity helpers.

This module groups the account identity request and UID extraction flow that is
used when the browser provides a Craft World token.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import requests

from craftworld_tools.config import CW_APP_VERSION, CW_GRAPHQL_URL, CW_IDENTITY_SIGNIN_URL
from craftworld_tools.utils.auth import (
    extract_uid_from_identity_payload,
    extract_uid_from_jwt_payload,
    normalize_cw_token,
)


def cw_graphql_request(
    query: str,
    variables: Optional[Dict[str, Any]] = None,
    bearer_token: Optional[str] = None,
) -> Dict[str, Any]:
    """Make a raw Craft World GraphQL request and return status/body metadata."""
    headers = {
        "Content-Type": "application/json",
        "x-app-version": CW_APP_VERSION,
    }
    normalized_token = normalize_cw_token(bearer_token)
    if normalized_token:
        headers["Authorization"] = f"Bearer {normalized_token}"

    payload: Dict[str, Any] = {"query": query}
    if variables is not None:
        payload["variables"] = variables

    resp = requests.post(CW_GRAPHQL_URL, json=payload, headers=headers, timeout=20)
    try:
        body = resp.json()
    except Exception:
        body = {"errors": [{"message": f"Invalid JSON response (HTTP {resp.status_code})"}]}

    return {
        "status_code": resp.status_code,
        "ok": resp.ok,
        "body": body,
    }


def fetch_account_identity_payload(bearer_token: str) -> Dict[str, Any]:
    """Fetch account identity payload using schema variants seen in Craft World."""
    queries = [
        """
        query AccountIdentity {
          account {
            uid
            id
            linkedAccounts {
              type
              details
            }
          }
        }
        """,
        """
        query AccountIdentity {
          account {
            uid
            id
            tradeAccount {
              uid
              id
              linkedAccounts {
                type
                details
              }
            }
          }
        }
        """,
    ]

    last_errors: list[Any] = []
    for query in queries:
        upstream = cw_graphql_request(query=query, bearer_token=bearer_token)
        body = upstream.get("body") or {}
        errors = body.get("errors") or []
        if errors:
            last_errors = errors
            validation_only = all(
                isinstance(err, dict)
                and isinstance(err.get("extensions"), dict)
                and err.get("extensions", {}).get("code") == "GRAPHQL_VALIDATION_FAILED"
                for err in errors
            )
            if validation_only:
                continue
            return {"ok": False, "body": body, "errors": errors}

        return {"ok": True, "body": body, "errors": []}

    return {"ok": False, "body": {"errors": last_errors}, "errors": last_errors}


def resolve_uid_from_token(bearer_token: str) -> Dict[str, Any]:
    """Resolve a Craft World UID from a token using API payload, then JWT fallback."""
    token = normalize_cw_token(bearer_token) or ""
    identity_result = fetch_account_identity_payload(token)
    body = identity_result.get("body") or {}
    account_payload = (body.get("data") or {}).get("account") or body.get("account") or {}
    uid = extract_uid_from_identity_payload(account_payload)
    source = "account_identity"

    if not uid:
        uid = extract_uid_from_jwt_payload(token)
        source = "jwt_payload" if uid else "missing"

    return {
        "ok": bool(uid),
        "uid": uid,
        "source": source,
        "identity": identity_result,
    }


def sign_in_with_custom_token(custom_token: str) -> Dict[str, Any]:
    """Exchange a custom token through Firebase Identity Toolkit."""
    payload = {
        "token": custom_token,
        "returnSecureToken": True,
    }
    resp = requests.post(CW_IDENTITY_SIGNIN_URL, json=payload, timeout=20)
    try:
        body = resp.json()
    except Exception:
        body = {"error": {"message": f"Invalid JSON response (HTTP {resp.status_code})"}}
    return {
        "status_code": resp.status_code,
        "ok": resp.ok,
        "body": body,
    }
