"""Authentication and token normalization helpers."""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any, Optional


def token_cache_key(jwt_token: str) -> str:
    return hashlib.sha256(jwt_token.encode("utf-8")).hexdigest()


def mask_token(token: Optional[str]) -> str:
    if not token:
        return "<missing>"
    if len(token) <= 16:
        return token[:4] + "..."
    return f"{token[:10]}...{token[-6:]}"


def normalize_cw_token(token: Optional[str]) -> Optional[str]:
    value = (token or "").strip()
    if not value:
        return None
    if value.startswith("jwt_"):
        return value
    if value.count(".") >= 2:
        return f"jwt_{value}"
    return value


def extract_bearer_token(authorization_value: Optional[str]) -> Optional[str]:
    if not authorization_value:
        return None
    value = authorization_value.strip()
    if not value:
        return None
    if value.lower().startswith("bearer "):
        token = value[7:].strip()
        return token or None
    return None


def extract_uid_from_account_payload(account_payload: Any) -> Optional[str]:
    if not isinstance(account_payload, dict):
        return None

    linked_accounts = account_payload.get("linkedAccounts")
    if not isinstance(linked_accounts, list):
        return None

    for entry in linked_accounts:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("type") or "").strip().lower() != "custom_jwt":
            continue
        details = entry.get("details")
        if isinstance(details, str):
            try:
                details = json.loads(details)
            except Exception:
                details = {}
        if isinstance(details, dict):
            candidate = str(details.get("id") or details.get("user_id") or "").strip()
            if candidate:
                return candidate

    return None


def extract_uid_from_identity_payload(identity_payload: Any) -> Optional[str]:
    if not isinstance(identity_payload, dict):
        return None

    direct_uid_value = str(identity_payload.get("uid") or identity_payload.get("id") or "").strip()
    if direct_uid_value:
        return direct_uid_value

    direct_uid = extract_uid_from_account_payload(identity_payload)
    if direct_uid:
        return direct_uid

    trade_account = identity_payload.get("tradeAccount")
    if isinstance(trade_account, dict):
        trade_uid_value = str(trade_account.get("uid") or trade_account.get("id") or "").strip()
        if trade_uid_value:
            return trade_uid_value
        trade_uid = extract_uid_from_account_payload(trade_account)
        if trade_uid:
            return trade_uid

    return None


def extract_uid_from_jwt_payload(jwt_token: Optional[str]) -> Optional[str]:
    raw = str(jwt_token or "").strip()
    if not raw:
        return None
    if raw.startswith("jwt_"):
        raw = raw[4:]
    parts = raw.split(".")
    if len(parts) < 2:
        return None

    payload_b64 = parts[1]
    padding = "=" * (-len(payload_b64) % 4)
    try:
        decoded = base64.urlsafe_b64decode(payload_b64 + padding)
        payload = json.loads(decoded.decode("utf-8"))
    except Exception:
        return None

    for key in ("uid", "user_id", "sub"):
        candidate = str(payload.get(key) or "").strip()
        if candidate:
            return candidate
    return None
