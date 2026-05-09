"""Backward-compatible crafting planner entry point.

The implementation now lives in `craftworld_tools.domain.crafting_core`.
This wrapper keeps existing imports working while the Flask app is gradually
moved into the package structure.
"""

from craftworld_tools.domain.crafting_core import (  # noqa: F401
    BASE_SYMBOLS,
    CANONICAL_GRAPH,
    CRAFTING_CHAINS,
    DEFAULT_MODIFIERS,
    Modifiers,
    Recipe,
    RecipeInput,
    build_chain_report,
    build_recipe_index,
    get_effective_recipe,
    plan_craft,
    rank_opportunities,
)
