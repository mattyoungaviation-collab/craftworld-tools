"""Core page handlers.

These handlers are the destination for legacy dashboard, boosts, profitability,
and Masterpiece page functions that used to live in app.py.
"""

from __future__ import annotations

from typing import Any, Callable


LegacyHandler = Callable[..., Any]


def dashboard_handler(legacy_handler: LegacyHandler) -> Any:
    return legacy_handler()


def boosts_handler(legacy_handler: LegacyHandler) -> Any:
    return legacy_handler()


def profitability_handler(legacy_handler: LegacyHandler) -> Any:
    return legacy_handler()


def craft_profitability_handler(legacy_handler: LegacyHandler) -> Any:
    return legacy_handler()


def masterpieces_view_handler(legacy_handler: LegacyHandler) -> Any:
    return legacy_handler()
