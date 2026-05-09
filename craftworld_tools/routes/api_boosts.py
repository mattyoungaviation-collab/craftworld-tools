"""Boost API handlers.

These handlers are the destination for legacy boost API functions that used to
live in app.py.
"""

from __future__ import annotations

from typing import Any, Callable


LegacyHandler = Callable[..., Any]


def api_boosts_mastery_handler(legacy_handler: LegacyHandler) -> Any:
    return legacy_handler()


def api_boosts_sync_handler(legacy_handler: LegacyHandler) -> Any:
    return legacy_handler()
