"""Saved Mastery and Workshop boost helpers."""

from __future__ import annotations

from typing import Dict, List

from flask import session

from craftworld_tools.db import get_db_connection


BoostLevels = Dict[str, Dict[str, int]]


def default_boost_levels(tokens: List[str]) -> BoostLevels:
    """Default per-token mastery/workshop levels."""
    return {token: {"mastery_level": 0, "workshop_level": 0} for token in tokens}


def load_boost_levels_from_db(user_id: int, tokens: List[str]) -> BoostLevels:
    """Return per-token levels from the database for a given user_id."""
    levels = default_boost_levels(tokens)
    token_set = set(tokens)
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT token, mastery_level, workshop_level FROM boosts WHERE user_id = ?",
            (user_id,),
        )
        for row in cur.fetchall():
            token = row["token"]
            if token in token_set:
                try:
                    mastery = int(row["mastery_level"])
                except (TypeError, ValueError):
                    mastery = 0
                try:
                    workshop = int(row["workshop_level"])
                except (TypeError, ValueError):
                    workshop = 0
                levels[token]["mastery_level"] = max(0, min(10, mastery))
                levels[token]["workshop_level"] = max(0, min(10, workshop))
    finally:
        conn.close()
    return levels


def save_boost_levels_to_db(user_id: int, tokens: List[str], levels: BoostLevels) -> None:
    """Persist per-token levels to the database for a given user_id."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        for token in tokens:
            vals = levels.get(token, {})
            try:
                mastery = int(vals.get("mastery_level", 0) or 0)
            except (TypeError, ValueError):
                mastery = 0
            try:
                workshop = int(vals.get("workshop_level", 0) or 0)
            except (TypeError, ValueError):
                workshop = 0
            mastery = max(0, min(10, mastery))
            workshop = max(0, min(10, workshop))
            cur.execute(
                """
                INSERT INTO boosts (user_id, token, mastery_level, workshop_level)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, token) DO UPDATE SET
                    mastery_level = excluded.mastery_level,
                    workshop_level = excluded.workshop_level
                """,
                (user_id, token, mastery, workshop),
            )
        conn.commit()
    finally:
        conn.close()


def load_session_boost_levels(tokens: List[str], current_uid: str) -> BoostLevels:
    """Legacy no-login boost storage backed by Flask session."""
    levels = default_boost_levels(tokens)
    all_boosts = session.get("boost_levels_by_uid_v1", {})
    if not isinstance(all_boosts, dict):
        all_boosts = {}

    raw = all_boosts.get(current_uid)
    if isinstance(raw, dict):
        for token, vals in raw.items():
            if token not in levels or not isinstance(vals, dict):
                continue
            try:
                mastery = int(vals.get("mastery_level", 0) or 0)
            except (TypeError, ValueError):
                mastery = 0
            try:
                workshop = int(vals.get("workshop_level", 0) or 0)
            except (TypeError, ValueError):
                workshop = 0
            levels[token]["mastery_level"] = max(0, min(10, mastery))
            levels[token]["workshop_level"] = max(0, min(10, workshop))
    return levels


def save_session_boost_levels(current_uid: str, levels: BoostLevels) -> None:
    """Persist legacy no-login boost storage into Flask session."""
    all_boosts = session.get("boost_levels_by_uid_v1", {})
    if not isinstance(all_boosts, dict):
        all_boosts = {}
    all_boosts[current_uid] = levels
    session["boost_levels_by_uid_v1"] = all_boosts
    session.modified = True
