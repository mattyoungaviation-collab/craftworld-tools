"""Small formatting helpers used across the app."""

from __future__ import annotations

from typing import Optional


def format_hms_from_seconds(seconds: int) -> str:
    seconds = max(0, int(seconds))
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def normalize_avatar_url(raw: Optional[str]) -> Optional[str]:
    """Normalize Craft World avatar URLs so browsers can display them."""
    if not raw:
        return None
    url = raw.strip()
    if not url:
        return None
    if url.startswith("ipfs://"):
        cid_path = url[len("ipfs://"):]
        return f"https://ipfs.io/ipfs/{cid_path}"
    return url
