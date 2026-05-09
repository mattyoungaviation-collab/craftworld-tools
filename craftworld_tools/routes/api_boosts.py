"""Boost API handlers.

These handlers were migrated out of app.py.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from flask import jsonify, request, session

from factories import FACTORIES_FROM_CSV

def api_boosts_mastery():
    payload = request.get_json(silent=True) or {}
    raw_levels = payload.get("masteryLevels") if isinstance(payload, dict) else None
    if not isinstance(raw_levels, dict):
        return jsonify({"ok": False, "error": "masteryLevels map is required."}), 400

    levels_map = get_boost_levels()
    updated_count = 0

    for token, level in raw_levels.items():
        symbol = str(token or "").strip().upper()
        if symbol not in levels_map:
            continue

        try:
            clamped_level = max(0, min(10, int(level)))
        except (TypeError, ValueError):
            continue

        levels_map[symbol]["mastery_level"] = clamped_level
        updated_count += 1

    save_boost_levels(levels_map)
    return jsonify({
        "ok": True,
        "updated": updated_count,
        "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })


def api_boosts_sync():
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"ok": False, "error": "JSON body is required."}), 400

    raw_mastery = payload.get("masteryLevels")
    raw_workshop = payload.get("workshopLevels")
    if not isinstance(raw_mastery, dict) and not isinstance(raw_workshop, dict):
        return jsonify({"ok": False, "error": "masteryLevels or workshopLevels map is required."}), 400

    levels_map = get_boost_levels()
    mastery_updated = 0
    workshop_updated = 0

    if isinstance(raw_mastery, dict):
        for token, level in raw_mastery.items():
            symbol = str(token or "").strip().upper()
            if symbol not in levels_map:
                continue
            try:
                clamped_level = max(0, min(10, int(level)))
            except (TypeError, ValueError):
                continue
            levels_map[symbol]["mastery_level"] = clamped_level
            mastery_updated += 1

    if isinstance(raw_workshop, dict):
        for token, level in raw_workshop.items():
            symbol = str(token or "").strip().upper()
            if symbol not in levels_map:
                continue
            try:
                clamped_level = max(0, min(10, int(level)))
            except (TypeError, ValueError):
                continue
            levels_map[symbol]["workshop_level"] = clamped_level
            workshop_updated += 1

    save_boost_levels(levels_map)
    return jsonify({
        "ok": True,
        "masteryUpdated": mastery_updated,
        "workshopUpdated": workshop_updated,
        "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })

