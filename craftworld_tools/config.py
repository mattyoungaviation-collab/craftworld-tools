"""Central configuration values for Craft World Tools."""

from __future__ import annotations

import os


def resolve_db_path() -> str:
    """Resolve the SQLite DB path, creating the target directory when possible."""
    configured = os.environ.get("DB_PATH", "/data/craftworld_tools.db")
    configured = str(configured or "").strip() or "/data/craftworld_tools.db"
    target_dir = os.path.dirname(os.path.abspath(configured)) or "."
    try:
        os.makedirs(target_dir, exist_ok=True)
        return configured
    except Exception:
        fallback = os.path.join(os.getcwd(), "craftworld_tools.db")
        fallback_dir = os.path.dirname(os.path.abspath(fallback)) or "."
        os.makedirs(fallback_dir, exist_ok=True)
        return fallback


DB_PATH = resolve_db_path()
CW_GRAPHQL_URL = "https://craft-world.gg/graphql"
CW_APP_VERSION = "1.11.0"
CW_FIREBASE_API_KEY = "AIzaSyDgDDykbRrhbdfWUpm1BUgj4ga7d_-wy_g"
CW_IDENTITY_SIGNIN_URL = (
    "https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken"
    f"?key={CW_FIREBASE_API_KEY}"
)
