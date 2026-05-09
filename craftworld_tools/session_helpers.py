"""Session helper functions shared by routes."""

from __future__ import annotations

from typing import Optional

from flask import session


def current_uid() -> str:
    """Get the current Craft World UID for this session."""
    uid = session.get("voya_uid")
    if not uid:
        return "_NO_UID_"
    return str(uid)


def has_uid_flag() -> bool:
    """Return whether the session has a usable Craft World UID."""
    uid = session.get("voya_uid")
    return bool(uid and str(uid).strip())


def current_user_id() -> Optional[int]:
    """Return logged in site user id, if available."""
    user_id = session.get("user_id")
    if not user_id:
        return None
    try:
        return int(user_id)
    except (TypeError, ValueError):
        return None


def is_logged_in() -> bool:
    return current_user_id() is not None
