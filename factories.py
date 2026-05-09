"""Backward-compatible factory calculation entry point.

The implementation now lives in `craftworld_tools.domain.factories_core`.
This wrapper keeps existing imports working while the Flask app is gradually
moved into the package structure.
"""

from craftworld_tools.domain.factories_core import (  # noqa: F401
    CSV_FILE,
    FACTORIES_FROM_CSV,
    FACTORY_DISPLAY_INDEX,
    FACTORY_DISPLAY_ORDER,
    MASTERY_BONUSES,
    WORKSHOP_MODIFIERS,
    MyFactory,
    compute_best_setups_csv,
    compute_factory_result_csv,
    load_factories_from_csv,
    my_factories,
    profit_per_hour,
)
