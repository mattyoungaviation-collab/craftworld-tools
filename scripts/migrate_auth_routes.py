"""Move auth routes out of app.py and wire the extracted auth module.

Run from a local checkout:

    python scripts/migrate_auth_routes.py
    python -m py_compile app.py
    python scripts/audit_routes.py

The script removes inline /register, /login, and /logout route blocks from
app.py, then registers `craftworld_tools.routes.auth.register_auth_routes`.
It writes `app.py.auth.bak` before changing the file.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app.py"
BACKUP = ROOT / "app.py.auth.bak"

IMPORT_LINE = "from craftworld_tools.routes.auth import register_auth_routes\n"
SESSION_IMPORT_LINE = "from craftworld_tools.session_helpers import has_uid_flag\n"
REGISTER_LINE = "\n# Extracted auth routes\nregister_auth_routes(app, has_uid_flag)\n"

ROUTE_BLOCKS = [
    r"\n@app\.route\(\"/register\", methods=\[\"GET\", \"POST\"\]\)\ndef register\(\):\n(?:(?!\n@app\.route).)*",
    r"\n@app\.route\(\"/login\", methods=\[\"GET\", \"POST\"\]\)\ndef login\(\):\n(?:(?!\n@app\.route).)*",
    r"\n@app\.route\(\"/logout\"\)\ndef logout\(\):\n(?:(?!\n@app\.route).)*",
]


def add_imports(text: str) -> str:
    if IMPORT_LINE not in text:
        anchor = "from flask import "
        pos = text.find(anchor)
        if pos == -1:
            raise RuntimeError("Could not find Flask import anchor.")
        line_end = text.find("\n", pos)
        text = text[: line_end + 1] + IMPORT_LINE + text[line_end + 1 :]

    if "def has_uid_flag" not in text and SESSION_IMPORT_LINE not in text:
        # If app.py no longer has its own has_uid_flag, import the shared helper.
        text = text.replace(IMPORT_LINE, IMPORT_LINE + SESSION_IMPORT_LINE, 1)
    return text


def remove_route_block(text: str, pattern: str, label: str) -> str:
    new_text, count = re.subn(pattern, "\n", text, count=1, flags=re.DOTALL)
    if count != 1:
        raise RuntimeError(f"Could not remove {label} route block. Pattern did not match exactly once.")
    return new_text


def add_registration(text: str) -> str:
    if "register_auth_routes(app, has_uid_flag)" in text:
        return text

    # Register immediately after app.secret_key is set if possible.
    secret_pattern = r"(app\.secret_key\s*=\s*[^\n]+\n)"
    match = re.search(secret_pattern, text)
    if match:
        insert_at = match.end()
        return text[:insert_at] + REGISTER_LINE + text[insert_at:]

    # Fallback: after app = Flask(...)
    flask_pattern = r"(app\s*=\s*Flask\([^\n]+\)\n)"
    match = re.search(flask_pattern, text)
    if match:
        insert_at = match.end()
        return text[:insert_at] + REGISTER_LINE + text[insert_at:]

    raise RuntimeError("Could not find app registration anchor.")


def main() -> None:
    text = APP.read_text(encoding="utf-8")
    original = text

    text = add_imports(text)
    text = remove_route_block(text, ROUTE_BLOCKS[0], "register")
    text = remove_route_block(text, ROUTE_BLOCKS[1], "login")
    text = remove_route_block(text, ROUTE_BLOCKS[2], "logout")
    text = add_registration(text)

    if text == original:
        print("No changes made.")
        return

    if not BACKUP.exists():
        BACKUP.write_text(original, encoding="utf-8")
    APP.write_text(text, encoding="utf-8")
    print("Moved auth routes out of app.py and wrote app.py.auth.bak")


if __name__ == "__main__":
    main()
