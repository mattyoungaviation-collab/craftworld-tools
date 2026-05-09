"""Compatibility helpers for migrated legacy handlers.

Many handlers migrated out of app.py still reference module-level globals such as
BASE_TEMPLATE, TOKEN lists, helper functions, and cached data. During the
transition, this helper copies those names from the root app module into the
handler module right before a request is handled.
"""

from __future__ import annotations

import importlib
from types import ModuleType


SKIP_NAMES = {
    "app",
    "Flask",
}


def inject_app_globals(target_module: ModuleType) -> None:
    """Copy public-ish globals from root app.py into a migrated handler module."""
    legacy_app = importlib.import_module("app")
    for name, value in vars(legacy_app).items():
        if name in SKIP_NAMES:
            continue
        if name.startswith("__"):
            continue
        # Always refresh so mutable globals and helper replacements stay current.
        setattr(target_module, name, value)
