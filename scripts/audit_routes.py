"""Print Flask routes registered by the current app.

Usage:
    python scripts/audit_routes.py

This helps compare app.py inline routes against extracted route modules before
wiring the new registry into production.
"""

from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> None:
    app_module = import_module("app")
    flask_app = getattr(app_module, "app")

    rows = []
    for rule in flask_app.url_map.iter_rules():
        methods = ",".join(sorted(m for m in rule.methods if m not in {"HEAD", "OPTIONS"}))
        rows.append((str(rule.rule), methods, rule.endpoint))

    rows.sort(key=lambda r: (r[0], r[2]))
    print("ROUTE | METHODS | ENDPOINT")
    print("--- | --- | ---")
    for rule, methods, endpoint in rows:
        print(f"{rule} | {methods} | {endpoint}")


if __name__ == "__main__":
    main()
