"""Account data API handlers.

These handlers are the destination for legacy account data API functions that
used to live in app.py.
"""

from __future__ import annotations

from typing import Any, Callable


LegacyHandler = Callable[..., Any]


def api_account_uid_handler(legacy_handler: LegacyHandler) -> Any:
    return legacy_handler()


def api_account_proficiencies_handler(legacy_handler: LegacyHandler) -> Any:
    return legacy_handler()


def api_account_workshop_handler(legacy_handler: LegacyHandler) -> Any:
    return legacy_handler()
