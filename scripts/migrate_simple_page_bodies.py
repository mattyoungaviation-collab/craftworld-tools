"""Move simple page function bodies out of app.py.

This migrates these legacy handlers from app.py into
craftworld_tools/routes/pages_simple.py:

- privacy
- terms
- charts
- trees

Route registration is already owned by pages_simple_legacy.py. This script
switches that wrapper to call the moved handlers instead of importing app.py.

Run from a local checkout:

    python scripts/migrate_simple_page_bodies.py
    python -m py_compile app.py craftworld_tools/routes/pages_simple.py craftworld_tools/routes/pages_simple_legacy.py
    python scripts/audit_routes.py

It writes `app.py.simple_bodies.bak` before changing app.py.
"""

from __future__ import annotations

import ast
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app.py"
DEST = ROOT / "craftworld_tools" / "routes" / "pages_simple.py"
WRAPPER = ROOT / "craftworld_tools" / "routes" / "pages_simple_legacy.py"
BACKUP = ROOT / "app.py.simple_bodies.bak"

FUNCTIONS = ["privacy", "terms", "charts", "trees"]

DEST_HEADER = '''"""Simple page handlers.

These handlers were migrated out of app.py.
"""

from __future__ import annotations

from typing import Any

from flask import render_template_string

'''

WRAPPER_CONTENT = '''"""Simple page route wrappers."""

from __future__ import annotations

from typing import Any

from craftworld_tools.routes.pages_simple import charts, privacy, terms, trees


def register_simple_page_legacy_routes(app: Any) -> None:
    """Register simple page endpoints."""

    app.route("/privacy", methods=["GET"])(privacy)
    app.route("/terms", methods=["GET"])(terms)
    app.route("/charts", methods=["GET"])(charts)
    app.route("/trees", methods=["GET"])(trees)
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


def _build_destination(existing_text: str, extracted: dict[str, str]) -> str:
    body_parts = []
    for name in FUNCTIONS:
        body = extracted[name]
        # Remove any decorators that somehow remained on the function.
        body_lines = [line for line in body.splitlines() if not line.lstrip().startswith("@app.route")]
        body_parts.append("\n".join(body_lines).rstrip() + "\n")
    return DEST_HEADER + "\n\n".join(body_parts) + "\n"


def main() -> None:
    app_text = APP.read_text(encoding="utf-8")
    original_app = app_text
    existing_dest = DEST.read_text(encoding="utf-8") if DEST.exists() else ""

    extracted, new_app = _extract_functions(app_text)
    new_dest = _build_destination(existing_dest, extracted)

    if not BACKUP.exists():
        BACKUP.write_text(original_app, encoding="utf-8")
    APP.write_text(new_app, encoding="utf-8")
    DEST.write_text(new_dest, encoding="utf-8")
    WRAPPER.write_text(WRAPPER_CONTENT, encoding="utf-8")
    print("Moved simple page bodies out of app.py and wrote app.py.simple_bodies.bak")


if __name__ == "__main__":
    main()
