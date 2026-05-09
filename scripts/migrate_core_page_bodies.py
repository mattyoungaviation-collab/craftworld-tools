"""Move core page function bodies out of app.py.

This migrates these legacy handlers into craftworld_tools/routes/pages_core.py:

- dashboard
- boosts
- profitability
- craft_profitability
- masterpieces_view

The script first looks in the current app.py. If the functions are no longer
there, it searches app.py backup files created during earlier migrations.

Run from a local checkout:

    python scripts/migrate_core_page_bodies.py
    python -m py_compile app.py craftworld_tools/routes/pages_core.py craftworld_tools/routes/pages_core_legacy.py
    python scripts/audit_routes.py

It writes `app.py.core_bodies.bak` before changing app.py.
"""

from __future__ import annotations

import ast
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app.py"
DEST = ROOT / "craftworld_tools" / "routes" / "pages_core.py"
WRAPPER = ROOT / "craftworld_tools" / "routes" / "pages_core_legacy.py"
BACKUP = ROOT / "app.py.core_bodies.bak"

FUNCTIONS = ["dashboard", "boosts", "profitability", "craft_profitability", "masterpieces_view"]

DEST_HEADER = '''"""Core page handlers.

These handlers were migrated out of app.py.
"""

from __future__ import annotations

import json
import math
from typing import Any, Dict, List, Optional

from flask import jsonify, redirect, render_template_string, request, session, url_for

from craftworld_api import fetch_available_avatars, fetch_craftworld, fetch_masterpiece_details, fetch_masterpieces, fetch_profile_by_uid, predict_reward
from crafting_planner import CRAFTING_CHAINS, Modifiers, build_chain_report, plan_craft, rank_opportunities
from factories import FACTORIES_FROM_CSV, FACTORY_DISPLAY_INDEX, FACTORY_DISPLAY_ORDER, MASTERY_BONUSES, WORKSHOP_MODIFIERS, compute_best_setups_csv, compute_factory_result_csv
from pricing import TOKEN_ADDRESSES, fetch_buy_sell_for_profitability, fetch_live_prices_in_coin

'''

WRAPPER_CONTENT = '''"""Core page route wrappers."""

from __future__ import annotations

from typing import Any

from craftworld_tools.routes.pages_core import boosts, craft_profitability, dashboard, masterpieces_view, profitability


def register_core_page_legacy_routes(app: Any) -> None:
    """Register core page endpoints."""

    app.route("/dashboard", methods=["GET"])(dashboard)
    app.route("/boosts", methods=["GET", "POST"])(boosts)
    app.route("/profitability", methods=["GET", "POST"])(profitability)
    app.route("/craft-profitability", methods=["GET"])(craft_profitability)
    app.route("/masterpieces", methods=["GET", "POST"])(masterpieces_view)
'''


def _function_spans(text: str) -> dict[str, tuple[int, int]]:
    tree = ast.parse(text)
    spans: dict[str, tuple[int, int]] = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in FUNCTIONS:
            if getattr(node, "end_lineno", None) is None:
                raise RuntimeError("Python AST did not provide end_lineno. Use Python 3.8 or newer.")
            spans[node.name] = (node.lineno, node.end_lineno)
    return spans


def _extract_from_text(text: str, *, remove: bool) -> tuple[dict[str, str], str, list[str]]:
    lines = text.splitlines(keepends=True)
    spans = _function_spans(text)
    missing = [name for name in FUNCTIONS if name not in spans]

    extracted: dict[str, str] = {}
    for name, (start, end) in spans.items():
        block = "".join(lines[start - 1 : end])
        extracted[name] = textwrap.dedent(block).rstrip() + "\n"

    if remove:
        for start, end in sorted(spans.values(), reverse=True):
            del lines[start - 1 : end]

    return extracted, "".join(lines), missing


def _find_source_text(app_text: str) -> tuple[dict[str, str], str, str]:
    extracted, new_app, missing = _extract_from_text(app_text, remove=True)
    if not missing:
        return extracted, new_app, "app.py"

    backup_candidates = sorted(ROOT.glob("app.py*.bak"), key=lambda p: p.stat().st_mtime, reverse=True)
    for candidate in backup_candidates:
        candidate_text = candidate.read_text(encoding="utf-8")
        candidate_extracted, _unchanged, candidate_missing = _extract_from_text(candidate_text, remove=False)
        if not candidate_missing:
            return candidate_extracted, app_text, candidate.name

    raise RuntimeError(
        "Could not find all core page function bodies in app.py or backups. Missing from app.py: "
        f"{missing}. Checked backups: {[p.name for p in backup_candidates]}"
    )


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

    extracted, new_app, source_name = _find_source_text(app_text)
    new_dest = _build_destination(extracted)

    if not BACKUP.exists():
        BACKUP.write_text(original_app, encoding="utf-8")
    APP.write_text(new_app, encoding="utf-8")
    DEST.write_text(new_dest, encoding="utf-8")
    WRAPPER.write_text(WRAPPER_CONTENT, encoding="utf-8")
    print(f"Moved core page bodies using {source_name} and wrote app.py.core_bodies.bak")


if __name__ == "__main__":
    main()
