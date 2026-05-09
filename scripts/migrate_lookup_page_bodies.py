"""Move lookup page function bodies out of app.py.

This migrates these legacy handlers from app.py into
craftworld_tools/routes/pages_lookup.py:

- inventory_view
- mastery_view
- resource_view
- player_view

Route registration is already owned by pages_lookup_legacy.py. This script
switches that wrapper to call the moved handlers instead of importing app.py.

Run from a local checkout:

    python scripts/migrate_lookup_page_bodies.py
    python -m py_compile app.py craftworld_tools/routes/pages_lookup.py craftworld_tools/routes/pages_lookup_legacy.py
    python scripts/audit_routes.py

It writes `app.py.lookup_bodies.bak` before changing app.py.
"""

from __future__ import annotations

import ast
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app.py"
DEST = ROOT / "craftworld_tools" / "routes" / "pages_lookup.py"
WRAPPER = ROOT / "craftworld_tools" / "routes" / "pages_lookup_legacy.py"
BACKUP = ROOT / "app.py.lookup_bodies.bak"

FUNCTIONS = ["inventory_view", "mastery_view", "resource_view", "player_view"]

DEST_HEADER = '''"""Lookup page handlers.

These handlers were migrated out of app.py.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from flask import jsonify, redirect, render_template_string, request, session, url_for

from craftworld_api import fetch_craftworld, fetch_profile_by_uid
from pricing import fetch_live_prices_in_coin

'''

WRAPPER_CONTENT = '''"""Lookup page route wrappers."""

from __future__ import annotations

from typing import Any

from craftworld_tools.routes.pages_lookup import inventory_view, mastery_view, player_view, resource_view


def register_lookup_page_legacy_routes(app: Any) -> None:
    """Register lookup page endpoints."""

    app.route("/inventory", methods=["GET"])(inventory_view)
    app.route("/mastery", methods=["GET"])(mastery_view)
    app.route("/resource/<token>", methods=["GET"])(resource_view)
    app.route("/player/<uid>", methods=["GET"])(player_view)
'''


def _extract_functions(text: str) -> tuple[dict[str, str], str]:
    tree = ast.parse(text)
    lines = text.splitlines(keepends=True)
    spans: dict[str, tuple[int, int]] = {}

    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in FUNCTIONS:
            if getattr(node, "end_lineno", None) is None:
                raise RuntimeError("Python AST did not provide end_lineno. Use Python 3.8 or newer.")
            spans[node.name] = (node.lineno, node.end_lineno)

    missing = [name for name in FUNCTIONS if name not in spans]
    if missing:
        raise RuntimeError(f"Could not find function bodies in app.py: {missing}")

    extracted: dict[str, str] = {}
    for name, (start, end) in spans.items():
        block = "".join(lines[start - 1 : end])
        extracted[name] = textwrap.dedent(block).rstrip() + "\n"

    for start, end in sorted(spans.values(), reverse=True):
        del lines[start - 1 : end]

    return extracted, "".join(lines)


def _build_destination(extracted: dict[str, str]) -> str:
    body_parts = []
    for name in FUNCTIONS:
        body = extracted[name]
        body_lines = [line for line in body.splitlines() if not line.lstrip().startswith("@app.route")]
        body_parts.append("\n".join(body_lines).rstrip() + "\n")
    return DEST_HEADER + "\n\n".join(body_parts) + "\n"


def main() -> None:
    app_text = APP.read_text(encoding="utf-8")
    original_app = app_text

    extracted, new_app = _extract_functions(app_text)
    new_dest = _build_destination(extracted)

    if not BACKUP.exists():
        BACKUP.write_text(original_app, encoding="utf-8")
    APP.write_text(new_app, encoding="utf-8")
    DEST.write_text(new_dest, encoding="utf-8")
    WRAPPER.write_text(WRAPPER_CONTENT, encoding="utf-8")
    print("Moved lookup page bodies out of app.py and wrote app.py.lookup_bodies.bak")


if __name__ == "__main__":
    main()
