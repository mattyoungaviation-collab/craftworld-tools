"""Experimental WSGI entry point for the package app factory.

Do not point production at this until the inline routes in app.py have been
removed and the extracted route registry has been fully wired.
"""

from __future__ import annotations

from craftworld_tools.app_factory import create_app
from craftworld_tools.session_helpers import has_uid_flag


app = create_app(
    register_routes=False,
    has_uid_flag=has_uid_flag,
)
