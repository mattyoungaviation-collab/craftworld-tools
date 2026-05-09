"""Account status cache and response shaping helpers."""

from __future__ import annotations

import time
from typing import Any, Dict

from craftworld_api import fetch_account_status

from craftworld_tools.utils.auth import mask_token, normalize_cw_token, token_cache_key
from craftworld_tools.utils.formatting import format_hms_from_seconds

ACCOUNT_STATUS_CACHE: Dict[str, Dict[str, Any]] = {}
ACCOUNT_STATUS_CACHE_TTL = 5.0


def fetch_account_status_for_token(jwt_token: str, logger: Any = None) -> Dict[str, Any]:
    jwt_token = normalize_cw_token(jwt_token) or ""
    now = time.time()
    key = token_cache_key(jwt_token)
    cached_entry = ACCOUNT_STATUS_CACHE.get(key) or {}
    cached_payload = cached_entry.get("value")
    cached_ts = float(cached_entry.get("ts") or 0.0)
    if cached_payload and (now - cached_ts) < ACCOUNT_STATUS_CACHE_TTL:
        return dict(cached_payload)

    if logger is not None:
        logger.debug(
            "Account status token present=%s len=%s token=%s",
            bool(jwt_token),
            len(jwt_token or ""),
            mask_token(jwt_token),
        )

    try:
        account = fetch_account_status(bearer_token=jwt_token)
    except Exception as exc:
        err_text = str(exc)
        if logger is not None and "GraphQL errors:" in err_text:
            logger.warning("Craft World GraphQL error for /api/account_status: %s", err_text)
        response_payload = {
            "ok": False,
            "auth": "missing_or_invalid",
            "power": None,
            "msUntilRefill": None,
            "refillSeconds": None,
            "refillHMS": None,
            "primaryWallet": None,
            "powerLastRefill": None,
            "updatedAt": None,
            "error": f"Craft World auth failed: {err_text}",
            "rawErrors": [],
        }
        ACCOUNT_STATUS_CACHE[key] = {"ts": now, "value": dict(response_payload)}
        return response_payload

    ms = int(account.get("powerMillisecondsUntilRefill") or 0)
    refill_seconds = max(0, ms // 1000)

    response_payload = {
        "ok": True,
        "auth": "ok",
        "power": int(account.get("power") or 0),
        "msUntilRefill": ms,
        "refillSeconds": refill_seconds,
        "refillHMS": format_hms_from_seconds(refill_seconds),
        "primaryWallet": None,
        "powerLastRefill": account.get("powerLastRefill"),
        "updatedAt": account.get("updatedAt"),
    }
    ACCOUNT_STATUS_CACHE[key] = {"ts": now, "value": dict(response_payload)}
    return response_payload
