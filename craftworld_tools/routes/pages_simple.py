"""Simple page handlers.

These handlers are the destination for the legacy simple page functions that
used to live in app.py.
"""

from __future__ import annotations

from typing import Any, Callable


LegacyHandler = Callable[..., Any]


def privacy_handler(legacy_handler: LegacyHandler) -> Any:
    """Delegate to the existing privacy implementation during migration."""
    return legacy_handler()


def terms_handler(legacy_handler: LegacyHandler) -> Any:
    """Delegate to the existing terms implementation during migration."""
    return legacy_handler()


def charts_handler(legacy_handler: LegacyHandler) -> Any:
    """Delegate to the existing charts implementation during migration."""
    return legacy_handler()


def trees_handler(legacy_handler: LegacyHandler) -> Any:
    """Delegate to the existing trees implementation during migration."""
    return legacy_handler()
