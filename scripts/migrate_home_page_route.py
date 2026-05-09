"""Move home page route registration out of app.py.

This is a conservative migration. It removes only the root route decorator from
app.py and registers a wrapper in craftworld_tools.routes.pages_home_legacy.
The legacy function body remains in app.py for now.

Run from a local checkout:

    python scripts/migrate_home_page_route.py
    python -m py_compile app.py
    python scripts/audit_routes.py

It writes `app.py.home_page.bak` before changing the file.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app.py"
BACKUP = ROOT / "app.py.home_page.bak"

IMPORT_LINE = "from craftworld_tools.routes.pages_home_legacy import register_home_page_legacy_routes\n"
REGISTER_LINE = "\n# Extracted home page route registration\nregister_home_page_legacy_routes(app)\n"
TARGET_ROUTE = "/"
TARGET_ENDPOINT = "index"


def add_import(text: str) -> str:
    if IMPORT_LINE in text:
        return text
    anchors = [
        "from craftworld_tools.routes.pages_core_legacy import register_core_page_legacy_routes\n",
        "from craftworld_tools.routes.pages_tools_legacy import register_tool_page_legacy_routes\n",
        "from craftworld_tools.routes.pages_lookup_legacy import register_lookup_page_legacy_routes\n",
        "from craftworld_tools.routes.pages_simple_legacy import register_simple_page_legacy_routes\n",
        "from craftworld_tools.routes.api_boosts_legacy import register_boosts_legacy_routes\n",
        "from craftworld_tools.routes.api_account_data_legacy import register_account_data_legacy_routes\n",
        "from craftworld_tools.routes.api_cw_auth_legacy import register_cw_auth_legacy_routes\n",
        "from craftworld_tools.routes.api_account import register_account_api_routes\n",
        "from craftworld_tools.routes.auth import register_auth_routes\n",
    ]
    for anchor in anchors:
        if anchor in text:
            return text.replace(anchor, anchor + IMPORT_LINE, 1)
    flask_anchor = "from flask import "
    pos = text.find(flask_anchor)
    if pos == -1:
        raise RuntimeError("Could not find import anchor.")
    line_end = text.find("\n", pos)
    return text[: line_end + 1] + IMPORT_LINE + text[line_end + 1 :]


def _route_path_from_decorator(decorator: ast.AST) -> str | None:
    if not isinstance(decorator, ast.Call):
        return None
    func = decorator.func
    if not isinstance(func, ast.Attribute):
        return None
    if func.attr != "route":
        return None
    if not isinstance(func.value, ast.Name) or func.value.id != "app":
        return None
    if not decorator.args:
        return None
    first_arg = decorator.args[0]
    if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
        return first_arg.value
    return None


def remove_route_decorator(text: str) -> str:
    tree = ast.parse(text)
    lines = text.splitlines(keepends=True)
    decorators_to_remove: list[int] = []

    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        if node.name != TARGET_ENDPOINT:
            continue
        for dec in node.decorator_list:
            route_path = _route_path_from_decorator(dec)
            if route_path == TARGET_ROUTE:
                decorators_to_remove.append(dec.lineno)

    if len(decorators_to_remove) != 1:
        raise RuntimeError(f"Expected exactly one root route decorator, found {len(decorators_to_remove)}")

    del lines[decorators_to_remove[0] - 1]
    return "".join(lines)


def add_registration(text: str) -> str:
    if "register_home_page_legacy_routes(app)" in text:
        return text
    anchors = [
        "register_core_page_legacy_routes(app)\n",
        "register_tool_page_legacy_routes(app)\n",
        "register_lookup_page_legacy_routes(app)\n",
        "register_simple_page_legacy_routes(app)\n",
        "register_boosts_legacy_routes(app)\n",
        "register_account_data_legacy_routes(app)\n",
        "register_cw_auth_legacy_routes(app)\n",
        "register_account_api_routes(app, get_cached_account_status)\n",
        "register_auth_routes(app, has_uid_flag)\n",
    ]
    for anchor in anchors:
        if anchor in text:
            return text.replace(anchor, anchor + REGISTER_LINE, 1)
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
    text = remove_route_decorator(text)
    text = add_registration(text)
    if text == original:
        print("No changes made.")
        return
    if not BACKUP.exists():
        BACKUP.write_text(original, encoding="utf-8")
    APP.write_text(text, encoding="utf-8")
    print("Moved home page route registration out of app.py and wrote app.py.home_page.bak")


if __name__ == "__main__":
    main()
