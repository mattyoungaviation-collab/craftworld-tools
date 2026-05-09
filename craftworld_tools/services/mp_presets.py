"""Saved Masterpiece donation preset helpers."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from craftworld_tools.db import get_db_connection


PresetPayload = Dict[str, Any]


def create_mp_preset(
    user_id: int,
    name: str,
    payload: PresetPayload,
    masterpiece_id: Optional[int] = None,
) -> int:
    """Create a saved Masterpiece preset and return its database id."""
    clean_name = (name or "").strip()
    if not clean_name:
        raise ValueError("Preset name is required.")

    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO mp_presets (user_id, name, masterpiece_id, payload)
            VALUES (?, ?, ?, ?)
            """,
            (int(user_id), clean_name, masterpiece_id, json.dumps(payload or {})),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def list_mp_presets(user_id: int, masterpiece_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """List saved presets for a user, optionally filtered by Masterpiece id."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        if masterpiece_id is None:
            cur.execute(
                """
                SELECT id, user_id, name, masterpiece_id, payload, created_at
                FROM mp_presets
                WHERE user_id = ?
                ORDER BY created_at DESC, id DESC
                """,
                (int(user_id),),
            )
        else:
            cur.execute(
                """
                SELECT id, user_id, name, masterpiece_id, payload, created_at
                FROM mp_presets
                WHERE user_id = ? AND (masterpiece_id = ? OR masterpiece_id IS NULL)
                ORDER BY created_at DESC, id DESC
                """,
                (int(user_id), int(masterpiece_id)),
            )
        rows = cur.fetchall()
    finally:
        conn.close()

    presets: List[Dict[str, Any]] = []
    for row in rows:
        try:
            payload = json.loads(row["payload"] or "{}")
        except Exception:
            payload = {}
        presets.append(
            {
                "id": int(row["id"]),
                "user_id": int(row["user_id"]),
                "name": row["name"],
                "masterpiece_id": row["masterpiece_id"],
                "payload": payload,
                "created_at": row["created_at"],
            }
        )
    return presets


def get_mp_preset(user_id: int, preset_id: int) -> Optional[Dict[str, Any]]:
    """Fetch one saved preset that belongs to the user."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, user_id, name, masterpiece_id, payload, created_at
            FROM mp_presets
            WHERE id = ? AND user_id = ?
            """,
            (int(preset_id), int(user_id)),
        )
        row = cur.fetchone()
    finally:
        conn.close()

    if not row:
        return None

    try:
        payload = json.loads(row["payload"] or "{}")
    except Exception:
        payload = {}

    return {
        "id": int(row["id"]),
        "user_id": int(row["user_id"]),
        "name": row["name"],
        "masterpiece_id": row["masterpiece_id"],
        "payload": payload,
        "created_at": row["created_at"],
    }


def delete_mp_preset(user_id: int, preset_id: int) -> bool:
    """Delete a saved preset that belongs to the user. Returns True if deleted."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM mp_presets WHERE id = ? AND user_id = ?",
            (int(preset_id), int(user_id)),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def update_mp_preset(
    user_id: int,
    preset_id: int,
    *,
    name: Optional[str] = None,
    payload: Optional[PresetPayload] = None,
    masterpiece_id: Optional[int] = None,
) -> bool:
    """Update a saved preset. Omitted fields are left alone."""
    existing = get_mp_preset(user_id, preset_id)
    if existing is None:
        return False

    new_name = existing["name"] if name is None else (name or "").strip()
    if not new_name:
        raise ValueError("Preset name is required.")

    new_payload = existing["payload"] if payload is None else (payload or {})
    new_masterpiece_id = existing["masterpiece_id"] if masterpiece_id is None else masterpiece_id

    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE mp_presets
            SET name = ?, masterpiece_id = ?, payload = ?
            WHERE id = ? AND user_id = ?
            """,
            (
                new_name,
                new_masterpiece_id,
                json.dumps(new_payload),
                int(preset_id),
                int(user_id),
            ),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()
