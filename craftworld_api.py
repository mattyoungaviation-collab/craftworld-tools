"""Backward-compatible Craft World API entry point.

The implementation now lives in `craftworld_tools.services.craftworld_core`.
This wrapper keeps existing imports working while the Flask app is gradually
moved into the package structure.
"""

from craftworld_tools.services.craftworld_core import (  # noqa: F401
    MASTERPIECE_DETAILS_QUERY,
    call_graphql,
    call_graphql_with_jwt,
    fetch_account_status,
    fetch_available_avatars,
    fetch_craftworld,
    fetch_masterpiece_details,
    fetch_masterpieces,
    fetch_profile_by_uid,
    fetch_proficiencies,
    fetch_workshop_levels,
    get_jwt,
    predict_reward,
)
