"""Home page handler.

This handler is the destination for the legacy root index function that used to
live in app.py.
"""

from __future__ import annotations

from typing import Any, Callable


LegacyHandler = Callable[..., Any]


def index_handler(legacy_handler: LegacyHandler) -> Any:
    return legacy_handler()
