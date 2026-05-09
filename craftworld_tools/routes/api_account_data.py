"""Account data API handlers.

These handlers were migrated out of app.py.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from flask import jsonify, request, session

from craftworld_api import fetch_proficiencies, fetch_workshop_levels

def api_account_uid():
    jwt_token = _get_request_cw_token()
    if not jwt_token:
        return jsonify({"ok": False, "error": "Missing Craft World token."}), 401

    requested_wallet = (request.args.get("wallet") or "").strip().lower()

    query = """
    query AccountUID {
      account {
        id
        primaryWallet
      }
    }
    """
    upstream = _cw_graphql_request(query=query, bearer_token=jwt_token)
    body = upstream.get("body") or {}
    errors = body.get("errors") or []
    if errors:
        return jsonify({"ok": False, "error": "Craft World returned an error.", "rawErrors": errors}), 502

    account = (body.get("data") or {}).get("account") or {}
    uid = account.get("id")
    primary_wallet = str(account.get("primaryWallet") or "").strip().lower()
    if not uid:
        return jsonify({"ok": False, "error": "Craft World custom_jwt UID not found."}), 404

    requested_wallet = str(request.args.get("walletAddress") or "").strip().lower()
    if requested_wallet:
        wallets = account_payload.get("wallets") if isinstance(account_payload, dict) else None
        wallet_addresses = {
            str((w or {}).get("address") or "").strip().lower()
            for w in (wallets or [])
            if isinstance(w, dict)
        }
        trade_account = account_payload.get("tradeAccount") if isinstance(account_payload, dict) else None
        trade_wallets = trade_account.get("wallets") if isinstance(trade_account, dict) else None
        wallet_addresses.update({
            str((w or {}).get("address") or "").strip().lower()
            for w in (trade_wallets or [])
            if isinstance(w, dict)
        })

        if requested_wallet not in wallet_addresses:
            return jsonify({
                "ok": False,
                "error": "Authenticated account does not include the signed wallet.",
                "uid": uid,
                "walletAddress": requested_wallet,
            }), 409

    if requested_wallet and primary_wallet and requested_wallet != primary_wallet:
        return jsonify({
            "ok": False,
            "error": "Wallet session mismatch. Reconnect wallet to refresh your Craft World sign-in.",
            "auth": "wallet_mismatch",
            "wallet": primary_wallet,
        }), 409

    return jsonify({"ok": True, "uid": uid, "wallet": primary_wallet or None})


def api_account_proficiencies():
    jwt_token = _extract_bearer_token(request.headers.get("Authorization"))
    jwt_token = _normalize_cw_token(jwt_token)
    if not jwt_token:
        return jsonify({"ok": False, "auth": "missing_or_invalid", "error": "Missing token"})

    try:
        profs_map = fetch_proficiencies(bearer_token=jwt_token)
    except Exception as exc:
        return jsonify({"ok": False, "auth": "missing_or_invalid", "error": str(exc)})

    proficiencies = [
        {
            "symbol": symbol,
            "collectedAmount": float(values.get("collectedAmount") or 0),
            "claimedLevel": int(values.get("claimedLevel") or 0),
        }
        for symbol, values in sorted(profs_map.items())
    ]
    return jsonify({"ok": True, "proficiencies": proficiencies, "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})


def api_account_workshop():
    jwt_token = _extract_bearer_token(request.headers.get("Authorization"))
    jwt_token = _normalize_cw_token(jwt_token)
    if not jwt_token:
        return jsonify({"ok": False, "auth": "missing_or_invalid", "error": "Missing token"})

    try:
        workshop_map = fetch_workshop_levels(bearer_token=jwt_token)
    except Exception as exc:
        return jsonify({"ok": False, "auth": "missing_or_invalid", "error": str(exc)})

    workshop = [
        {"symbol": symbol, "level": int(level)}
        for symbol, level in sorted(workshop_map.items())
    ]
    return jsonify({"ok": True, "workshop": workshop, "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})

