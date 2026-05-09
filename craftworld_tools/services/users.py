"""User account storage helpers for Craft World Tools."""

from __future__ import annotations

from typing import Any, Dict, Optional

from werkzeug.security import check_password_hash, generate_password_hash

from craftworld_tools.db import get_db_connection


UserRow = Dict[str, Any]


def get_user_by_username(username: str) -> Optional[UserRow]:
    """Fetch a user by username."""
    clean_username = (username or "").strip()
    if not clean_username:
        return None

    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, username, password_hash, created_at FROM users WHERE username = ?",
            (clean_username,),
        )
        row = cur.fetchone()
    finally:
        conn.close()

    if not row:
        return None
    return {
        "id": int(row["id"]),
        "username": row["username"],
        "password_hash": row["password_hash"],
        "created_at": row["created_at"],
    }


def get_user_by_id(user_id: int) -> Optional[UserRow]:
    """Fetch a user by id."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, username, password_hash, created_at FROM users WHERE id = ?",
            (int(user_id),),
        )
        row = cur.fetchone()
    finally:
        conn.close()

    if not row:
        return None
    return {
        "id": int(row["id"]),
        "username": row["username"],
        "password_hash": row["password_hash"],
        "created_at": row["created_at"],
    }


def create_user(username: str, password: str) -> UserRow:
    """Create a new user and return the created user row."""
    clean_username = (username or "").strip()
    clean_password = password or ""
    if not clean_username:
        raise ValueError("Username is required.")
    if not clean_password:
        raise ValueError("Password is required.")
    if get_user_by_username(clean_username) is not None:
        raise ValueError("That username is already taken.")

    password_hash = generate_password_hash(clean_password)
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (clean_username, password_hash),
        )
        conn.commit()
        user_id = int(cur.lastrowid)
    finally:
        conn.close()

    created = get_user_by_id(user_id)
    if created is None:
        raise RuntimeError("User was created but could not be loaded.")
    return created


def authenticate_user(username: str, password: str) -> Optional[UserRow]:
    """Return user row if credentials are valid, otherwise None."""
    user = get_user_by_username(username)
    if user is None:
        return None
    if not check_password_hash(user["password_hash"], password or ""):
        return None
    return user
