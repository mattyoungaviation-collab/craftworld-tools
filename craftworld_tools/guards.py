"""Route guard helpers."""

from __future__ import annotations

from typing import Optional

from flask import redirect, request, session, url_for


def require_login_redirect() -> Optional[object]:
    """Return a redirect response if the site user is not logged in."""
    if session.get("user_id"):
        return None
    return redirect(url_for("login", next=request.path))


def require_uid_redirect() -> Optional[object]:
    """Return a redirect response if no Craft World UID is selected."""
    if session.get("voya_uid"):
        return None
    return redirect(url_for("index"))
