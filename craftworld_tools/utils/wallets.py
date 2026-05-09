"""Wallet address normalization helpers."""

from __future__ import annotations

from typing import List, Optional


def normalize_wallet_address_for_cw(value: Optional[str]) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    if raw.lower().startswith("ronin:"):
        raw = f"0x{raw.split(':', 1)[1]}"
    return raw


def candidate_wallet_addresses_for_cw(value: Optional[str]) -> List[str]:
    raw = (value or "").strip()
    normalized = normalize_wallet_address_for_cw(raw)
    if not raw and not normalized:
        return []

    candidates: List[str] = []
    if raw:
        candidates.append(raw)
    if normalized:
        candidates.append(normalized)
    if raw.lower().startswith("ronin:") and len(raw) > 6:
        candidates.append(f"0x{raw.split(':', 1)[1]}")
    if raw.lower().startswith("0x") and len(raw) > 2:
        candidates.append(f"ronin:{raw[2:]}")
    if normalized.lower().startswith("0x") and len(normalized) > 2:
        candidates.append(f"ronin:{normalized[2:]}")

    candidates.extend([c.lower() for c in list(candidates) if c])

    deduped: List[str] = []
    for item in candidates:
        if item and item not in deduped:
            deduped.append(item)
    return deduped
