"""List @app.route decorators that still physically live in app.py.

Usage:
    python scripts/audit_app_route_decorators.py

This is different from scripts/audit_routes.py:

- audit_routes.py shows the active Flask route table.
- this script shows route decorators still written directly in app.py.

Once this script prints no app.py decorators, route registration has been fully
moved out of the monster file.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app.py"


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


def main() -> None:
    text = APP.read_text(encoding="utf-8")
    tree = ast.parse(text)

    rows: list[tuple[int, str, str]] = []
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        for dec in node.decorator_list:
            route_path = _route_path_from_decorator(dec)
            if route_path:
                rows.append((dec.lineno, route_path, node.name))

    if not rows:
        print("No @app.route decorators remain in app.py.")
        return

    print("LINE | ROUTE | FUNCTION")
    print("--- | --- | ---")
    for line, route, func_name in sorted(rows):
        print(f"{line} | {route} | {func_name}")


if __name__ == "__main__":
    main()
