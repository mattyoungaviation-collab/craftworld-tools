"""Repair helper for auth route migration.

This fixes local app.py files where migrate_auth_routes.py registered:

    register_auth_routes(app, has_uid_flag)

but did not import has_uid_flag.

Run from repo root:

    python scripts/repair_auth_migration.py
    python -m py_compile app.py
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app.py"
BACKUP = ROOT / "app.py.auth.repair.bak"

IMPORT_LINE = "from craftworld_tools.session_helpers import has_uid_flag\n"
ANCHOR_LINE = "from craftworld_tools.routes.auth import register_auth_routes\n"


def main() -> None:
    text = APP.read_text(encoding="utf-8")
    original = text

    if IMPORT_LINE in text:
        print("has_uid_flag import already present. No changes made.")
        return

    if ANCHOR_LINE in text:
        text = text.replace(ANCHOR_LINE, ANCHOR_LINE + IMPORT_LINE, 1)
    else:
        # Fallback: add after flask import block.
        flask_anchor = "from flask import "
        pos = text.find(flask_anchor)
        if pos == -1:
            raise RuntimeError("Could not find import anchor to add has_uid_flag.")
        line_end = text.find("\n", pos)
        text = text[: line_end + 1] + IMPORT_LINE + text[line_end + 1 :]

    if not BACKUP.exists():
        BACKUP.write_text(original, encoding="utf-8")
    APP.write_text(text, encoding="utf-8")
    print("Added has_uid_flag import to app.py and wrote app.py.auth.repair.bak")


if __name__ == "__main__":
    main()
