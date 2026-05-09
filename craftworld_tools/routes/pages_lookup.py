"""Lookup page handlers.

These handlers are the destination for legacy lookup page functions that used to
live in app.py.
"""

from __future__ import annotations

from typing import Any, Callable


LegacyHandler = Callable[..., Any]


def inventory_view_handler(legacy_handler: LegacyHandler) -> Any:
    return legacy_handler()


def mastery_view_handler(legacy_handler: LegacyHandler) -> Any:
    return legacy_handler()


def resource_view_handler(legacy_handler: LegacyHandler, token: str) -> Any:
    return legacy_handler(token)


def player_view_handler(legacy_handler: LegacyHandler, uid: str) -> Any:
    return legacy_handler(uid)
