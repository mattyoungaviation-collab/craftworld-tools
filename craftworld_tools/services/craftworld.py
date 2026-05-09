"""Craft World GraphQL service compatibility layer.

The root craftworld_api.py module remains the runtime implementation for now.
This wrapper gives the app a cleaner service import path without breaking
existing code during the large app.py split.
"""

from craftworld_api import (  # noqa: F401
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
