"""Move Craft World auth route registration out of app.py.

This is a conservative migration. It removes only the three route decorators
from app.py and registers wrappers in craftworld_tools.routes.api_cw_auth_legacy.
The legacy function bodies remain in app.py for now.

Run from a local checkout:

    python scripts/migrate_cw_auth_routes.py
    python -m py_compile app.py
    python scripts/audit_routes.py

It writes `app.py.cw_auth.bak` before changing the file.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app.py"
BACKUP = ROOT / "app.py.cw_auth.bak"

IMPORT_LINE = "from craftworld_tools.routes.api_cw_auth_legacy import register_cw_auth_legacy_routes\n"
REGISTER_LINE = "\n# Extracted Craft World auth route registration\nregister_cw_auth_legacy_routes(app)\n"

DECORATORS = [
    '@app.route("/api/cw/get_nonce", methods=["POST"])',
    '@app.route("/api/cw/login_for_custom_token", methods=["POST"])',
    '@app.route("/api/cw/signin_with_custom_token", methods=["POST"])',
]


def add_import(text: str) -> str:
    if IMPORT_LINE in text:
        return text
    anchor = "from craftworld_tools.routes.api_account import register_account_api_routes\n"
    if anchor in text:
        return text.replace(anchor, anchor + IMPORT_LINE, 1)
    auth_anchor = "from craftworld_tools.routes.auth import register_auth_routes\n"
    if auth_anchor in text:
        return text.replace(auth_anchor, auth_anchor + IMPORT_LINE, 1)
    flask_anchor = "from flask import "
    pos = text.find(flask_anchor)
    if pos == -1:
        raise RuntimeError("Could not find import anchor.")
    line_end = text.find("\n", pos)
    return text[: line_end + 1] + IMPORT_LINE + text[line_end + 1 :]


def remove_decorators(text: str) -> str:
    for decorator in DECORATORS:
        pattern = re.escape(decorator) + r"\s*\n"
        text, count = re.subn(pattern, "", text, count=1)
        if count != 1:
            raise RuntimeError(f"Could not remove decorator: {decorator}")
    return text


def add_registration(text: str) -> str:
    if "register_cw_auth_legacy_routes(app)" in text:
        return text
    account_call = "register_account_api_routes(app, get_cached_account_status)\n"
    if account_call in text:
        return text.replace(account_call, account_call + REGISTER_LINE, 1)
    auth_call = "register_auth_routes(app, has_uid_flag)\n"
    if auth_call in text:
        return text.replace(auth_call, auth_call + REGISTER_LINE, 1)
    secret_pattern = r"(app\.secret_key\s*=\s*[^\n]+\n)"
    match = re.search(secret_pattern, text)
    if match:
        insert_at = match.end()
        return text[:insert_at] + REGISTER_LINE + text[insert_at:]
    raise RuntimeError("Could not find route registration anchor.")


def main() -> None:
    text = APP.read_text(encoding="utf-8")
    original = text

    text = add_import(text)
    text = remove_decorators(text)
    text = add_registration(text)

    if text == original:
        print("No changes made.")
        return

    if not BACKUP.exists():
        BACKUP.write_text(original, encoding="utf-8")
    APP.write_text(text, encoding="utf-8")
    print("Moved Craft World auth route registration out of app.py and wrote app.py.cw_auth.bak")


if __name__ == "__main__":
    main()
