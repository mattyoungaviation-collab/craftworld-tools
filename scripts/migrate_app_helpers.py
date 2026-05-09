"""Surgically migrate low-risk helpers out of app.py.

Run this from a local checkout:

    python scripts/migrate_app_helpers.py

What it does:

1. Adds imports for extracted helper modules.
2. Replaces simple duplicate helper functions with aliases/imported functions.
3. Leaves route blocks untouched.

This script is intentionally conservative. It creates `app.py.bak` before
writing changes and refuses to run if expected anchors are missing.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app.py"
BACKUP = ROOT / "app.py.bak"

IMPORT_BLOCK = """
from craftworld_tools.config import DB_PATH, CW_GRAPHQL_URL, CW_APP_VERSION, CW_FIREBASE_API_KEY, CW_IDENTITY_SIGNIN_URL
from craftworld_tools.db import get_db_connection, init_db
from craftworld_tools.services.account_status import fetch_account_status_for_token
from craftworld_tools.services.identity import cw_graphql_request, fetch_account_identity_payload
from craftworld_tools.services.masterpiece_cache import cache_masterpiece_metadata, load_masterpiece_metadata_cache
from craftworld_tools.services.boosts import (
    default_boost_levels,
    load_boost_levels_from_db,
    save_boost_levels_to_db,
    load_session_boost_levels,
    save_session_boost_levels,
)
from craftworld_tools.session_helpers import current_uid
from craftworld_tools.utils.auth import (
    extract_bearer_token,
    extract_uid_from_account_payload,
    extract_uid_from_identity_payload,
    extract_uid_from_jwt_payload,
    mask_token,
    normalize_cw_token,
    token_cache_key,
)
from craftworld_tools.utils.formatting import format_hms_from_seconds, normalize_avatar_url
from craftworld_tools.utils.wallets import normalize_wallet_address_for_cw, candidate_wallet_addresses_for_cw
""".strip()

ALIASES = """
# Compatibility aliases while app.py is being reduced.
_format_hms_from_seconds = format_hms_from_seconds
_token_cache_key = token_cache_key
_extract_uid_from_account_payload = extract_uid_from_account_payload
_extract_uid_from_identity_payload = extract_uid_from_identity_payload
_extract_uid_from_jwt_payload = extract_uid_from_jwt_payload
_extract_bearer_token = extract_bearer_token
_normalize_cw_token = normalize_cw_token
_normalize_wallet_address_for_cw = normalize_wallet_address_for_cw
_candidate_wallet_addresses_for_cw = candidate_wallet_addresses_for_cw
_cw_graphql_request = cw_graphql_request
_fetch_account_identity_payload = fetch_account_identity_payload
_mask_token = mask_token
_current_uid = current_uid
""".strip()


def insert_after_imports(text: str) -> str:
    if "from craftworld_tools.config import DB_PATH" in text:
        return text
    anchor = "from werkzeug.security import generate_password_hash, check_password_hash\n"
    if anchor not in text:
        raise RuntimeError("Could not find import anchor.")
    return text.replace(anchor, anchor + "\n" + IMPORT_BLOCK + "\n", 1)


def replace_function_with_alias(text: str, func_name: str) -> str:
    marker = f"def {func_name}("
    start = text.find(marker)
    if start == -1:
        return text

    # Find the next top-level def/class/import/from/comment section.
    cursor = start + len(marker)
    next_positions = []
    for needle in ["\ndef ", "\nclass ", "\nfrom ", "\nimport ", "\n# "]:
        pos = text.find(needle, cursor)
        if pos != -1:
            next_positions.append(pos + 1)
    if not next_positions:
        raise RuntimeError(f"Could not find end of function {func_name}")
    end = min(next_positions)

    return text[:start] + text[end:]


def main() -> None:
    text = APP.read_text(encoding="utf-8")
    original = text

    text = insert_after_imports(text)

    # Remove duplicate helper definitions that now come from package modules.
    for name in [
        "normalize_avatar_url",
        "_format_hms_from_seconds",
        "_token_cache_key",
        "_extract_uid_from_account_payload",
        "_extract_uid_from_identity_payload",
        "_extract_uid_from_jwt_payload",
        "_extract_bearer_token",
        "_normalize_cw_token",
        "_normalize_wallet_address_for_cw",
        "_candidate_wallet_addresses_for_cw",
        "_cw_graphql_request",
        "_fetch_account_identity_payload",
        "_mask_token",
        "_current_uid",
    ]:
        text = replace_function_with_alias(text, name)

    if ALIASES not in text:
        init_anchor = "init_db()\n"
        if init_anchor not in text:
            raise RuntimeError("Could not find init_db anchor for compatibility aliases.")
        text = text.replace(init_anchor, init_anchor + "\n" + ALIASES + "\n", 1)

    if text == original:
        print("No changes made.")
        return

    if not BACKUP.exists():
        BACKUP.write_text(original, encoding="utf-8")
    APP.write_text(text, encoding="utf-8")
    print("Updated app.py and wrote app.py.bak")


if __name__ == "__main__":
    main()
