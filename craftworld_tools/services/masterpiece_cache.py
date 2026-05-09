"""Database backed Masterpiece metadata cache helpers."""

from __future__ import annotations

from typing import Any, Dict

from craftworld_tools.db import get_db_connection


def cache_masterpiece_metadata(mp: Dict[str, Any]) -> None:
    """Store basic metadata for a masterpiece so the app can reuse name and label later."""
    try:
        mid = int(mp.get("id") or 0)
    except (TypeError, ValueError):
        return
    if mid <= 0:
        return

    name = mp.get("name") or None
    label = mp.get("addressableLabel") or mp.get("addressable_label") or None
    mtype = mp.get("type") or None
    is_event = 1 if mp.get("eventId") else 0

    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO mp_metadata (id, name, addressable_label, type, is_event)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = COALESCE(excluded.name, mp_metadata.name),
                addressable_label = COALESCE(excluded.addressable_label, mp_metadata.addressable_label),
                type = COALESCE(excluded.type, mp_metadata.type),
                is_event = excluded.is_event
            """,
            (mid, name, label, mtype, is_event),
        )
        conn.commit()
    finally:
        conn.close()


def load_masterpiece_metadata_cache() -> Dict[int, Dict[str, Any]]:
    """Load cached Masterpiece metadata keyed by integer ID."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, name, addressable_label, type, is_event FROM mp_metadata")
        rows = cur.fetchall()
    finally:
        conn.close()

    cache: Dict[int, Dict[str, Any]] = {}
    for row in rows:
        mid = int(row["id"])
        label = row["addressable_label"]
        is_event = int(row["is_event"] or 0)
        cache[mid] = {
            "id": mid,
            "name": row["name"],
            "addressable_label": label,
            "addressableLabel": label,
            "type": row["type"],
            "is_event": is_event,
            "eventId": mid if is_event else None,
        }
    return cache
