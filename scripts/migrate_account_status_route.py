"""Move /api/account_status out of app.py and wire the extracted account API module.

Run from a local checkout:

    python scripts/migrate_account_status_route.py
    python -m py_compile app.py
    python scripts/audit_routes.py

The script removes the inline /api/account_status route block from app.py,
then registers `craftworld_tools.routes.api_account.register_account_api_routes`.
It writes `app.py.account_status.bak` before changing the file.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app.py"
BACKUP = ROOT / "app.py.account_status.bak"

IMPORT_LINE = "from craftworld_tools.routes.api_account import register_account_api_routes\n"
REGISTER_LINE = "\n# Extracted account status API route\nregister_account_api_routes(app, get_cached_account_status)\n"

ROUTE_PATTERN = (
    r"\n@app\.route\(\"/api/account_status\"\)\n"
    r"def api_account_status\(\):\n"
    r"(?:(?!\n@app\.route).)*"
)


def add_import(text: str) -> str:
    if IMPORT_LINE in text:
        return text
    anchor = "from craftworld_tools.routes.auth import register_auth_routes\n"
    if anchor in text:
        return text.replace(anchor, anchor + IMPORT_LINE, 1)

    flask_anchor = "from flask import "
    pos = text.find(flask_anchor)
    if pos == -1:
        raise RuntimeError("Could not find import anchor.")
    line_end = text.find("\n", pos)
    return text[: line_end + 1] + IMPORT_LINE + text[line_end + 1 :]


def remove_route(text: str) -> str:
    new_text, count = re.subn(ROUTE_PATTERN, "\n", text, count=1, flags=re.DOTALL)
    if count != 1:
        raise RuntimeError("Could not remove /api/account_status route block. Pattern did not match exactly once.")
    return new_text


def add_registration(text: str) -> str:
    if "register_account_api_routes(app, get_cached_account_status)" in text:
        return text

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
    text = remove_route(text)
    text = add_registration(text)

    if text == original:
        print("No changes made.")
        return

    if not BACKUP.exists():
        BACKUP.write_text(original, encoding="utf-8")
    APP.write_text(text, encoding="utf-8")
    print("Moved /api/account_status out of app.py and wrote app.py.account_status.bak")


if __name__ == "__main__":
    main()
