"""Patch Masterpiece page calls to pass current UID into cached details.

Run from repo root:

    python scripts/patch_masterpiece_user_query.py
    python -m py_compile craftworld_tools/routes/pages_core.py

This lets the Masterpiece page use the richer query fields:
profileByUserId, resourcesByUserId, and dailyPowerContributionsByUserId.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "craftworld_tools" / "routes" / "pages_core.py"

REPLACEMENTS = {
    "cached_masterpiece_details(selected_mp_id)": "cached_masterpiece_details(selected_mp_id, user_id=session.get(\"voya_uid\"))",
    "cached_masterpiece_details(masterpiece_id)": "cached_masterpiece_details(masterpiece_id, user_id=session.get(\"voya_uid\"))",
    "cached_masterpiece_details(mp_id)": "cached_masterpiece_details(mp_id, user_id=session.get(\"voya_uid\"))",
    "cached_masterpiece_details(int(selected_mp_id))": "cached_masterpiece_details(int(selected_mp_id), user_id=session.get(\"voya_uid\"))",
    "cached_masterpiece_details(int(masterpiece_id))": "cached_masterpiece_details(int(masterpiece_id), user_id=session.get(\"voya_uid\"))",
    "cached_masterpiece_details(int(mp_id))": "cached_masterpiece_details(int(mp_id), user_id=session.get(\"voya_uid\"))",
}


def main() -> None:
    text = TARGET.read_text(encoding="utf-8")
    original = text

    for old, new in REPLACEMENTS.items():
        text = text.replace(old, new)

    if text == original:
        print("No matching cached_masterpiece_details(...) call was changed. Check pages_core.py manually.")
        return

    TARGET.write_text(text, encoding="utf-8")
    print("Patched Masterpiece details calls to include session voya_uid.")


if __name__ == "__main__":
    main()
