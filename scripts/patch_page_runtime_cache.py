"""Patch migrated page modules to use cached runtime calls.

Run from repo root:

    python scripts/patch_page_runtime_cache.py
    python -m py_compile craftworld_tools/routes/pages_core.py craftworld_tools/routes/pages_tools.py craftworld_tools/routes/pages_home.py

This reduces slow page loads by replacing direct expensive calls with short TTL
cached wrappers.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    ROOT / "craftworld_tools" / "routes" / "pages_core.py",
    ROOT / "craftworld_tools" / "routes" / "pages_tools.py",
    ROOT / "craftworld_tools" / "routes" / "pages_home.py",
    ROOT / "craftworld_tools" / "routes" / "pages_lookup.py",
]

IMPORT_LINE = (
    "from craftworld_tools.services.cached_runtime import "
    "cached_buy_sell, cached_craftworld, cached_live_prices, cached_masterpiece_details, cached_masterpieces\n"
)

REPLACEMENTS = {
    "fetch_live_prices_in_coin()": "cached_live_prices()",
    "fetch_buy_sell_for_profitability(": "cached_buy_sell(",
    "fetch_craftworld(uid)": "cached_craftworld(uid)",
    "fetch_craftworld(voya_uid)": "cached_craftworld(voya_uid)",
    "fetch_craftworld(current_uid)": "cached_craftworld(current_uid)",
    "fetch_masterpieces()": "cached_masterpieces()",
    "fetch_masterpiece_details(": "cached_masterpiece_details(",
}


def patch_file(path: Path) -> bool:
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    original = text

    if IMPORT_LINE not in text:
        lines = text.splitlines(keepends=True)
        insert_at = 0
        for idx, line in enumerate(lines):
            if line.startswith("from ") or line.startswith("import "):
                insert_at = idx + 1
        lines.insert(insert_at, IMPORT_LINE)
        text = "".join(lines)

    for old, new in REPLACEMENTS.items():
        text = text.replace(old, new)

    if text != original:
        path.write_text(text, encoding="utf-8")
        return True
    return False


def main() -> None:
    changed = []
    for path in FILES:
        if patch_file(path):
            changed.append(str(path.relative_to(ROOT)))
    if changed:
        print("Patched cached runtime calls in:")
        for name in changed:
            print(f"- {name}")
    else:
        print("No changes made.")


if __name__ == "__main__":
    main()
