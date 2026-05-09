"""Tool page handlers.

These handlers are the destination for legacy calculation and planning page
functions that used to live in app.py.
"""

from __future__ import annotations

from typing import Any, Callable


LegacyHandler = Callable[..., Any]


def calculate_handler(legacy_handler: LegacyHandler) -> Any:
    return legacy_handler()


def upgrade_calculate_handler(legacy_handler: LegacyHandler) -> Any:
    return legacy_handler()


def factory_converter_handler(legacy_handler: LegacyHandler) -> Any:
    return legacy_handler()


def flex_planner_handler(legacy_handler: LegacyHandler) -> Any:
    return legacy_handler()


def snipe_handler(legacy_handler: LegacyHandler) -> Any:
    return legacy_handler()
