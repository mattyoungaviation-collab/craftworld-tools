from typing import Dict, Any, List, Optional

import json
import math
import sqlite3
import requests
from flask import Flask, request, render_template_string, session, url_for, redirect

from werkzeug.security import generate_password_hash, check_password_hash

from craftworld_api import (
    fetch_craftworld,
    fetch_masterpieces,
    fetch_masterpiece_details,
    predict_reward,
    get_jwt,
    GRAPHQL_URL,
)
# ---------------- Database setup (users + saved boosts) ----------------

import os
DB_PATH = os.environ.get("DB_PATH", "/data/craftworld_tools.db")



def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_db_connection()
    cur = conn.cursor()
    # Simple users table: username + password hash
    cur.execute(
        '''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        '''
    )
    # Per-user boosts: one row per token per user
    cur.execute(
        '''
        CREATE TABLE IF NOT EXISTS boosts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token TEXT NOT NULL,
            mastery_level INTEGER NOT NULL,
            workshop_level INTEGER NOT NULL,
            UNIQUE(user_id, token),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        '''
    )
    # Saved MP donation presets per user
    cur.execute(
        '''
        CREATE TABLE IF NOT EXISTS mp_presets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            masterpiece_id INTEGER,
            payload TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        '''
    )

    # Cache for masterpiece metadata (id -> name / label / type)
    cur.execute(
        '''
        CREATE TABLE IF NOT EXISTS mp_metadata (
            id INTEGER PRIMARY KEY,
            name TEXT,
            addressable_label TEXT,
            type TEXT,
            is_event INTEGER DEFAULT 0
        )
        '''
    )

    conn.commit()

    conn.close()



init_db()
def cache_masterpiece_metadata(mp: Dict[str, Any]) -> None:
    """
    Store basic metadata for a masterpiece so we can reuse its name/label later.
    """
    try:
        mid = int(mp.get("id") or 0)
    except (TypeError, ValueError):
        return
    if mid <= 0:
        return

    name = mp.get("name") or None
    # Some responses use "addressableLabel", but we'll store as snake_case.
    label = mp.get("addressableLabel") or mp.get("addressable_label") or None
    mtype = mp.get("type") or None
    is_event = 1 if mp.get("eventId") else 0

    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            '''
            INSERT INTO mp_metadata (id, name, addressable_label, type, is_event)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = COALESCE(excluded.name, mp_metadata.name),
                addressable_label = COALESCE(excluded.addressable_label, mp_metadata.addressable_label),
                type = COALESCE(excluded.type, mp_metadata.type),
                is_event = excluded.is_event
            ''',
            (mid, name, label, mtype, is_event),
        )
        conn.commit()
    finally:
        conn.close()


def load_masterpiece_metadata_cache() -> Dict[int, Dict[str, Any]]:
    """
    Load all cached MP metadata from the DB as a dict keyed by integer ID.
    """
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            'SELECT id, name, addressable_label, type, is_event FROM mp_metadata'
        )
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
            # keep both snake_case and camelCase so templates work
            "addressable_label": label,
            "addressableLabel": label,
            "type": row["type"],
            "is_event": is_event,
            "eventId": mid if is_event else None,
        }
    return cache



from pricing import fetch_live_prices_in_coin

from factories import (
    my_factories,
    profit_per_hour,
    FACTORIES_FROM_CSV,
    compute_factory_result_csv,
    compute_best_setups_csv,
    FACTORY_DISPLAY_ORDER,
    FACTORY_DISPLAY_INDEX,
    MASTERY_BONUSES,
    WORKSHOP_MODIFIERS,
)

# ---- Fallback mastery / workshop tables ----
# If factories.py doesn't define these yet, we provide safe defaults here.

if "MASTERY_BONUSES" not in globals():
    # Mastery level 0–10 → multiplier on output (1.00x … 1.20x as a placeholder).
    # You can tweak these later to match the exact in-game table.
    MASTERY_BONUSES = {
        0: 1.00,
        1: 1.02,
        2: 1.04,
        3: 1.06,
        4: 1.08,
        5: 1.10,
        6: 1.12,
        7: 1.14,
        8: 1.16,
        9: 1.18,
        10: 1.20,
    }




ALL_FACTORY_TOKENS = sorted(FACTORIES_FROM_CSV.keys())
# Standard display order for factories (used in "standard" sort mode)
STANDARD_FACTORY_ORDER: List[str] = [
    "MUD",
    "CLAY",
    "SAND",
    "COPPER",
    "SEAWATER",
    "HEAT",
    "ALGAE",
    "LAVA",
    "CERAMICS",
    "STEEL",
    "OXYGEN",
    "GLASS",
    "GAS",
    "STONE",
    "STEAM",
    "SCREWS",
    "FUEL",
    "CEMENT",
    "OIL",
    "ACID",
    "SULFER",
    "PLASTICS",
    "FIBERGLASS",
    "ENERGY",
    "HYDROGEN",
    "DYNAMITE",
]

STANDARD_ORDER_INDEX: Dict[str, int] = {
    name.upper(): idx for idx, name in enumerate(STANDARD_FACTORY_ORDER)
}
# Masterpiece tier thresholds (points required per tier)
MP_TIER_THRESHOLDS = [
    10_000,        # Tier 1
    35_000,        # Tier 2
    85_000,        # Tier 3
    250_000,       # Tier 4
    1_000_000,     # Tier 5
    3_250_000,     # Tier 6
    15_000_000,    # Tier 7
    50_000_000,    # Tier 8
    100_000_000,   # Tier 9
    200_000_000,   # Tier 10
]
def get_mp_per_unit_rewards(mp_id: str, symbols: List[str]) -> Dict[str, Dict[str, float]]:
    """
    Pre-compute masterpiece points, XP, and battery (required power) per 1 unit
    for each symbol in `symbols`.

    This is a thin wrapper around predict_reward(...) that calls it once per
    unique token with amount = 1.0.

    Returns a dict:
      {
        "points": { "SEAWATER": 4_200_000.0, ... },
        "xp":     { "SEAWATER":   350_000.0, ... },
        "power":  { "SEAWATER":       1_200.0, ... },
      }
    """
    unique_syms = sorted({(s or "").upper() for s in symbols if s})
    points: Dict[str, float] = {}
    xp: Dict[str, float] = {}
    power: Dict[str, float] = {}

    if not mp_id or not unique_syms:
        return {"points": points, "xp": xp, "power": power}

    for sym in unique_syms:
        try:
            pr = predict_reward(mp_id, [{"symbol": sym, "amount": 1.0}]) or {}
            points[sym] = float(pr.get("masterpiecePoints") or 0.0)
            xp[sym] = float(pr.get("experiencePoints") or 0.0)
            power[sym] = float(pr.get("requiredPower") or 0.0)
        except Exception:
            # If anything fails, just treat this token as 0 points / 0 XP / 0 power per unit
            points[sym] = 0.0
            xp[sym] = 0.0
            power[sym] = 0.0

    return {"points": points, "xp": xp, "power": power}




def compute_leaderboard_gap_for_highlight(
    rows: List[Dict[str, Any]],
    highlight_query: str,
) -> Optional[Dict[str, Any]]:
    """
    Given a leaderboard (rows) and a highlight_query (name or UID),
    find that row and compute:
      - points needed to pass the player above
      - points lead over the player below

    Returns a dict or None if the highlighted player is not found.
    """
    highlight_query = (highlight_query or "").strip()
    if not highlight_query or not rows:
        return None

    q = highlight_query.lower()

    def _get_points(r: Dict[str, Any]) -> float:
        try:
            return float(r.get("masterpiecePoints") or 0)
        except Exception:
            return 0.0

    def _get_name(r: Dict[str, Any]) -> str:
        prof = r.get("profile") or {}
        return prof.get("displayName") or prof.get("uid") or "?"

    # Find the highlighted row
    idx = None
    for i, row in enumerate(rows):
        prof = row.get("profile") or {}
        name = (prof.get("displayName") or "").lower()
        uid = (prof.get("uid") or "").lower()
        if q in name or q in uid:
            idx = i
            break

    if idx is None:
        return None

    cur_row = rows[idx]
    cur_pts = _get_points(cur_row)
    cur_pos = cur_row.get("position")

    # Player above (better rank)
    above = rows[idx - 1] if idx > 0 else None
    gap_up = None
    above_name = None
    above_pos = None
    if above is not None:
        above_pts = _get_points(above)
        gap_up = max(0.0, above_pts - cur_pts + 1.0)
        above_name = _get_name(above)
        above_pos = above.get("position")

    # Player below (worse rank)
    below = rows[idx + 1] if idx + 1 < len(rows) else None
    gap_down = None
    below_name = None
    below_pos = None
    if below is not None:
        below_pts = _get_points(below)
        gap_down = max(0.0, cur_pts - below_pts + 1.0)
        below_name = _get_name(below)
        below_pos = below.get("position")

    return {
        "position": cur_pos,
        "points": cur_pts,
        "gap_up": gap_up,
        "gap_down": gap_down,
        "above_name": above_name,
        "above_pos": above_pos,
        "below_name": below_name,
        "below_pos": below_pos,
    }


def _default_boost_levels() -> dict[str, dict[str, int]]:
    """
    Default per-token mastery/workshop levels (0–10).
    These act like your account-wide boosts for each resource.
    """
    return {
        token: {"mastery_level": 0, "workshop_level": 0}
        for token in ALL_FACTORY_TOKENS
    }


def _current_uid() -> str:
    """
    Get the current Voya UID for this session.
    Used so each UID has its own boost settings.
    """
    uid = session.get("voya_uid")
    if not uid:
        # fallback bucket if no UID set yet
        return "_NO_UID_"
    return str(uid)


def _load_boost_levels_from_db(user_id: int) -> dict[str, dict[str, int]]:
    """Return per-token levels from the database for a given user_id."""
    levels = _default_boost_levels()
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT token, mastery_level, workshop_level FROM boosts WHERE user_id = ?",
            (user_id,),
        )
        for row in cur.fetchall():
            token = row["token"]
            if token in levels:
                try:
                    m = int(row["mastery_level"])
                except (TypeError, ValueError):
                    m = 0
                try:
                    w = int(row["workshop_level"])
                except (TypeError, ValueError):
                    w = 0
                levels[token]["mastery_level"] = max(0, min(10, m))
                levels[token]["workshop_level"] = max(0, min(10, w))
    finally:
        conn.close()
    return levels


def _save_boost_levels_to_db(user_id: int, levels: dict[str, dict[str, int]]) -> None:
    """Persist per-token levels to the database for a given user_id."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        for token in ALL_FACTORY_TOKENS:
            vals = levels.get(token, {})
            try:
                m = int(vals.get("mastery_level", 0) or 0)
            except (TypeError, ValueError):
                m = 0
            try:
                w = int(vals.get("workshop_level", 0) or 0)
            except (TypeError, ValueError):
                w = 0
            m = max(0, min(10, m))
            w = max(0, min(10, w))
            cur.execute(
                '''
                INSERT INTO boosts (user_id, token, mastery_level, workshop_level)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, token) DO UPDATE SET
                    mastery_level = excluded.mastery_level,
                    workshop_level = excluded.workshop_level
                ''',
                (user_id, token, m, w),
            )
        conn.commit()
    finally:
        conn.close()


def get_boost_levels() -> dict[str, dict[str, int]]:
    """Load per-token mastery/workshop levels.

    If a user is logged in, we load from the per-account database.
    Otherwise, we fall back to the older per-UID-in-session storage so
    the tool still works anonymously and when 'spying' via another UID.
    """
    user_id = session.get("user_id")
    if user_id:
        try:
            return _load_boost_levels_from_db(int(user_id))
        except Exception:
            # If DB read fails for any reason, fall back to session-based.
            pass

    # ---- Legacy per-UID-in-session behaviour (no login) ----
    all_boosts = session.get("boost_levels_by_uid_v1", {})
    if not isinstance(all_boosts, dict):
        all_boosts = {}

    uid = _current_uid()
    raw = all_boosts.get(uid)

    levels: dict[str, dict[str, int]] = _default_boost_levels()

    if isinstance(raw, dict):
        for token, vals in raw.items():
            if token not in levels or not isinstance(vals, dict):
                continue
            try:
                m = int(vals.get("mastery_level", 0) or 0)
            except (TypeError, ValueError):
                m = 0
            try:
                w = int(vals.get("workshop_level", 0) or 0)
            except (TypeError, ValueError):
                w = 0
            levels[token]["mastery_level"] = max(0, min(10, m))
            levels[token]["workshop_level"] = max(0, min(10, w))

    return levels


def save_boost_levels(levels: dict[str, dict[str, int]]) -> None:
    """Persist per-token mastery/workshop levels.

    If a user is logged in, we store these levels in the per-account
    database. Otherwise we keep the older behaviour of storing them
    per-UID in the Flask session, so boosts still work without an
    account and while 'spying' another UID.
    """
    user_id = session.get("user_id")
    if user_id:
        # Save to DB for this account
        try:
            _save_boost_levels_to_db(int(user_id), levels)
        except Exception:
            # If DB write fails, fall back to session-based storage
            pass

    # ---- Legacy per-UID-in-session storage (kept for compatibility) ----
    all_boosts = session.get("boost_levels_by_uid_v1", {})
    if not isinstance(all_boosts, dict):
        all_boosts = {}

    uid = _current_uid()

    cleaned: dict[str, dict[str, int]] = {}
    for token in ALL_FACTORY_TOKENS:
        vals = levels.get(token, {})
        try:
            m = int(vals.get("mastery_level", 0) or 0)
        except (TypeError, ValueError):
            m = 0
        try:
            w = int(vals.get("workshop_level", 0) or 0)
        except (TypeError, ValueError):
            w = 0
        cleaned[token] = {
            "mastery_level": max(0, min(10, m)),
            "workshop_level": max(0, min(10, w)),
        }

    all_boosts[uid] = cleaned
    session["boost_levels_by_uid_v1"] = all_boosts



app = Flask(__name__)
app.secret_key = "craftworld-tools-demo-secret"  # for session


# -------- Helper: do we have a UID stored? --------
def has_uid_flag() -> bool:
    return bool(session.get("voya_uid"))


# -------- Base HTML template (dark neon UI) --------
BASE_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>CraftWorld Tools</title>
  <!-- Make it mobile friendly -->
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body {
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #050816;
      color: #f9fafb;
      margin: 0;
      padding: 0;
    }

    /* ---------- NAV ---------- */
    .nav {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 12px 20px;
      background: radial-gradient(circle at top left, #0f172a 0, #020617 50%, #020617 100%);
      border-bottom: 1px solid rgba(148,163,184,0.35);
      box-shadow: 0 10px 30px rgba(15,23,42,0.9);
      position: sticky;
      top: 0;
      z-index: 10;
    }
    .nav-title {
      font-weight: 700;
      font-size: 18px;
      letter-spacing: 0.05em;
      text-transform: uppercase;
      color: #e5e7eb;
    }
    .nav-links {
      display: flex;
      align-items: center;
      justify-content: flex-end;
      flex-wrap: wrap;
      gap: 6px;
    }
    .nav-links a,
    .nav-links span {
      text-decoration: none;
      font-size: 14px;
      padding: 6px 10px;
      border-radius: 999px;
      transition: all 0.15s ease-out;
    }
    .nav-links a {
      color: #cbd5f5;
      border: 1px solid transparent;
    }
    .nav-links a:hover {
      border-color: rgba(94,234,212,0.5);
      background: rgba(15,23,42,0.9);
    }
    .nav-links a.active {
      background: linear-gradient(135deg, #22c55e, #0ea5e9);
      color: #020617;
      border-color: transparent;
      box-shadow: 0 0 0 1px rgba(34,197,94,0.6), 0 8px 25px rgba(34,197,94,0.45);
    }
    .nav-disabled {
      color: #64748b;
      border: 1px dashed rgba(75,85,99,0.9);
      cursor: not-allowed;
    }
        .nav-user {
      font-size: 13px;
      color: #e5e7eb;
      margin-left: 8px;
      margin-right: 4px;
    }


    /* ---------- LAYOUT ---------- */
    .container {
      max-width: 1160px;
      margin: 18px auto 40px;
      padding: 0 16px 24px;
      box-sizing: border-box;
    }
    .card {
      background: radial-gradient(circle at top, #111827 0, #020617 50%, #020617 100%);
      border-radius: 16px;
      padding: 18px 20px;
      margin-bottom: 18px;
      border: 1px solid rgba(148,163,184,0.25);
      box-shadow: 0 18px 45px rgba(15,23,42,0.85);
    }
    h1, h2, h3 {
      font-weight: 600;
      margin-top: 4px;
      margin-bottom: 10px;
    }
    h1 { font-size: 22px; }
    h2 { font-size: 18px; }
    h3 { font-size: 16px; color: #e5e7eb; }

    .two-col {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 12px;
    }

    /* ---------- TABLES ---------- */
    table {
      width: 100%;
      border-collapse: collapse;
      margin-top: 8px;
      font-size: 14px;
    }
    th, td {
      padding: 6px 8px;
      border-bottom: 1px solid rgba(30,64,175,0.5);
      text-align: left;
    }
    th {
      font-weight: 600;
      color: #bfdbfe;
      background: rgba(15,23,42,0.85);
    }
    tr:nth-child(even) td {
      background: rgba(15,23,42,0.5);
    }
    tr:nth-child(odd) td {
      background: rgba(15,23,42,0.25);
    }

    /* wrapper for horizontal scroll on small screens */
    .scroll-x {
      width: 100%;
      overflow-x: auto;
    }

    .subtle {
      color: #9ca3af;
      font-size: 13px;
    }
    .error {
      margin-top: 10px;
      padding: 8px 10px;
      border-radius: 10px;
      background: rgba(248,113,113,0.15);
      color: #fecaca;
      border: 1px solid rgba(248,113,113,0.7);
      font-size: 13px;
      white-space: pre-wrap;
    }
    .pill {
      display: inline-block;
      padding: 2px 8px;
      border-radius: 999px;
      background: rgba(16,185,129,0.15);
      color: #a7f3d0;
      border: 1px solid rgba(16,185,129,0.6);
      font-size: 12px;
    }
    .pill-bad {
      display: inline-block;
      padding: 2px 8px;
      border-radius: 999px;
      background: rgba(248,113,113,0.15);
      color: #fecaca;
      border: 1px solid rgba(248,113,113,0.6);
      font-size: 12px;
    }
    button {
      background: linear-gradient(135deg, #22c55e, #0ea5e9);
      color: #020617;
      border-radius: 999px;
      padding: 7px 14px;
      border: none;
      font-weight: 600;
      cursor: pointer;
      font-size: 14px;
      box-shadow: 0 10px 25px rgba(34,197,94,0.45);
      margin-top: 6px;
    }
    button:hover {
      filter: brightness(1.05);
    }
    code {
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
      font-size: 12px;
      background: rgba(15,23,42,0.9);
      padding: 2px 4px;
      border-radius: 4px;
    }
    pre {
      background: rgba(15,23,42,0.95);
      padding: 10px;
      border-radius: 10px;
      border: 1px solid rgba(30,64,175,0.7);
      overflow-x: auto;
      font-size: 12px;
      margin-top: 8px;
      max-height: 420px;
    }
    .section {
      margin-top: 12px;
      padding-top: 8px;
      border-top: 1px dashed #374151;
      font-size: 14px;
    }
    label {
      display: block;
      font-size: 14px;
      margin-bottom: 4px;
      color: #e5e7eb;
    }
    input[type=text], input[type=number], select, textarea {
      width: 100%;
      padding: 8px 10px;
      border-radius: 10px;
      border: 1px solid rgba(75,85,99,0.9);
      background: rgba(15,23,42,0.9);
      color: #e5e7eb;
      font-size: 14px;
      box-sizing: border-box;
    }
    input[type=text]::placeholder,
    textarea::placeholder {
      color: #6b7280;
    }
    .two-col {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 12px;
    }
    .hint {
      font-size: 12px;
      color: #9ca3af;
      margin-top: 4px;
    }
        /* Mobile improvements for Masterpieces */
    @media (max-width: 768px) {

      /* Limit UID width and font */
      td.subtle {
        max-width: 110px;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        font-size: 11px;
      }

      /* Shrink MP column */
      td:last-child {
        white-space: nowrap;
        font-size: 12px;
      }

      /* Make table rows tighter */
      th, td {
        padding: 4px 6px;
      }

      /* Keep MP tables readable and scrollable */
      .mp-table-wrap table {
        min-width: 480px;
      }

    }

        /* Mobile tweaks */
    @media (max-width: 768px) {
      body {
        font-size: 14px;
      }

      .nav {
        flex-direction: column;
        align-items: flex-start;
        gap: 6px;
      }

      .nav-title {
        font-size: 16px;
      }

      .nav-links {
        display: flex;
        flex-wrap: wrap;
        width: 100%;
        gap: 6px;
      }

      .nav-links a,
      .nav-links span {
        font-size: 13px;
        padding: 5px 9px;
        margin-left: 0;
      }

      .container {
        max-width: 100%;
        padding: 0 10px 20px;
      }

      .card {
        padding: 14px 12px;
        margin-bottom: 12px;
      }

      table {
        font-size: 12px;
      }

      th, td {
        padding: 4px 6px;
      }

      /* Horizontal scroll for wide tables (like Masterpieces) */
      .mp-table-wrap {
        width: 100%;
        overflow-x: auto;
        -webkit-overflow-scrolling: touch;
      }

      .mp-table-wrap table {
        min-width: 520px; /* keeps columns readable, can tweak */
      }
    }


    /* ---------- MOBILE TWEAKS ---------- */
    @media (max-width: 768px) {
      .nav {
        flex-direction: column;
        align-items: flex-start;
        padding: 10px 12px;
        gap: 6px;
      }
      .nav-title {
        font-size: 16px;
      }
      .nav-links {
        justify-content: flex-start;
      }
      .container {
        margin: 12px auto 24px;
        padding: 0 10px 16px;
      }
      .card {
        padding: 12px 12px;
        margin-bottom: 12px;
      }
      table {
        font-size: 12px;
      }
      th, td {
        padding: 4px 6px;
      }
      button {
        width: 100%;
        text-align: center;
        margin-top: 8px;
      }
      .two-col {
        grid-template-columns: 1fr;
      }
    }
  </style>
</head>
<body>
  <div class="nav">
    <div class="nav-title">CraftWorld Tools</div>
    <div class="nav-links">
      <a href="{{ url_for('index') }}" class="{{ 'active' if active_page=='overview' else '' }}">Overview</a>
      {% if has_uid %}
        <a href="{{ url_for('profitability') }}" class="{{ 'active' if active_page=='profit' else '' }}">Profitability</a>
      {% else %}
        <span class="nav-disabled">Profitability</span>
      {% endif %}
      <a href="{{ url_for('boosts') }}" class="{{ 'active' if active_page=='boosts' else '' }}">Boosts</a>
      <a href="{{ url_for('masterpieces_view') }}" class="{{ 'active' if active_page=='masterpieces' else '' }}">Masterpieces</a>
      <a href="{{ url_for('snipe') }}" class="{{ 'active' if active_page=='snipe' else '' }}">Snipe</a>
      <a href="{{ url_for('calculate') }}" class="{{ 'active' if active_page=='calculate' else '' }}">Calculate</a>
      {% if session.get('username') %}
        <span class="nav-user">👤 {{ session['username'] }}</span>
        <a href="{{ url_for('logout') }}">Logout</a>
      {% else %}
        <a href="{{ url_for('login') }}" class="{{ 'active' if active_page=='login' else '' }}">Login</a>
      {% endif %}
    </div>
  </div>

  <div class="container">
    {{ content|safe }}
  </div>
</body>
</html>
"""



# -------- Overview tab --------
@app.route("/", methods=["GET", "POST"])
def index():
    error: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    uid = session.get("voya_uid", "")

    if request.method == "POST":
        uid = request.form.get("uid", "").strip()
        if not uid:
            error = "Please enter your Voya UID."
        else:
            session["voya_uid"] = uid
            try:
                data = fetch_craftworld(uid)
                result = data
                
            except Exception as e:
                error = f"Error fetching CraftWorld data: {e}"

    content = """
    <div class="card">
      <h1>Account Overview</h1>
      <p class="subtle">
        Enter your <strong>Voya UID</strong> and this page will fetch your land plots, factories,
        mines, dynos and resources from Craft World.
      </p>
      <form method="post">
        <label for="uid">Voya UID</label>
        <input type="text" id="uid" name="uid" value="{{ uid }}" placeholder="e.g. GfUeRBCZv8OwuUKq7Tu9JVpA70l1">
        <button type="submit">Fetch Craft World</button>
      </form>
      {% if error %}
        <div class="error">{{ error }}</div>
      {% endif %}
    </div>

    {% if result %}
      <div class="two-col">
        <div class="card">
          <h2>Land Plots & Factories</h2>
          {% if result.landPlots %}
            {% for plot in result.landPlots %}
              {% for area in plot.areas %}
                <h3>{{ area.symbol }}</h3>
                {% if area.factories %}
                  <table>
                    <tr><th>Factory</th><th>Level</th></tr>
                    {% for f in area.factories %}
                      {% if f.factory and f.factory.definition %}
                        <tr>
                          <td>{{ f.factory.definition.id }}</td>
                          <td>L{{ f.factory.level + 1 }}</td>
                        </tr>
                      {% endif %}
                    {% endfor %}
                  </table>
                {% else %}
                  <p class="subtle">No factories in this area.</p>
                {% endif %}
              {% endfor %}
            {% endfor %}
          {% else %}
            <p class="subtle">No land plots found.</p>
          {% endif %}
        </div>

        <div class="card">
          <h2>Dynos</h2>
          {% if result.dynos %}
            <table>
              <tr><th>Name</th><th>Rarity</th><th>Production</th></tr>
              {% for d in result.dynos %}
                <tr>
                  <td>{{ d.meta.displayName }}</td>
                  <td>{{ d.meta.rarity }}</td>
                  <td>
                    {% if d.production %}
                      {% for p in d.production %}
                        {{ p.amount }} {{ p.symbol }}{% if not loop.last %}, {% endif %}
                      {% endfor %}
                    {% else %}
                      <span class="subtle">none</span>
                    {% endif %}
                  </td>
                </tr>
              {% endfor %}
            </table>
          {% else %}
            <p class="subtle">No dynos found.</p>
          {% endif %}
        </div>
      </div>

      <div class="two-col">
        <div class="card">
          <h2>Mines</h2>
          <table>
            <tr><th>Token</th><th>Level</th></tr>
            {% for m in result.mines %}
              {% if m.definition %}
                <tr>
                  <td>{{ m.definition.id }}</td>
                  <td>L{{ m.level + 1 }}</td>
                </tr>
              {% endif %}
            {% endfor %}
          </table>
        </div>

        <div class="card">
          <h2>Resources</h2>
          {% if result.resources %}
            <table>
              <tr><th>Symbol</th><th>Amount</th></tr>
              {% for r in result.resources %}
                <tr>
                  <td>{{ r.symbol }}</td>
                  <td>{{ "{:,.2f}".format(r.amount) }}</td>
                </tr>
              {% endfor %}
            </table>
          {% else %}
            <p class="subtle">No resources found.</p>
          {% endif %}
        </div>
      </div>
    {% endif %}
    """

    content = render_template_string(
        content,
        uid=uid,
        error=error,
        result=result,
    )

    html = render_template_string(
        BASE_TEMPLATE,
        content=content,
        active_page="overview",
        has_uid=has_uid_flag(),
    )
    return html
    # ---------------- Authentication: register / login / logout ----------------

@app.route("/register", methods=["GET", "POST"])
def register():
    error: Optional[str] = None

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = (request.form.get("password") or "").strip()
        confirm = (request.form.get("confirm") or "").strip()

        if not username or not password:
            error = "Username and password are required."
        elif password != confirm:
            error = "Passwords do not match."
        else:
            conn = get_db_connection()
            try:
                cur = conn.cursor()
                cur.execute("SELECT id FROM users WHERE username = ?", (username,))
                existing = cur.fetchone()
                if existing:
                    error = "That username is already taken."
                else:
                    pwd_hash = generate_password_hash(password)
                    cur.execute(
                        "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                        (username, pwd_hash),
                    )
                    conn.commit()
                    user_id = cur.lastrowid
                    session["user_id"] = user_id
                    session["username"] = username
                    return redirect(url_for("boosts"))
            finally:
                conn.close()

    content = """
    <div class="card">
      <h1>Create Account</h1>
      <p class="subtle">
        Create a login so your <strong>Mastery &amp; Workshop</strong> boosts are saved
        to your account, independent of which Voya UID you're looking at.
      </p>

      <form method="post" class="section">
        <label for="username">Username</label>
        <input id="username" name="username" type="text" required maxlength="64" value="{{ request.form.get('username','') }}">
        <div class="hint">This is just for this site. It does not need to match your in-game name.</div>

        <label for="password" style="margin-top:10px;">Password</label>
        <input id="password" name="password" type="password" required>

        <label for="confirm" style="margin-top:10px;">Confirm password</label>
        <input id="confirm" name="confirm" type="password" required>

        <button type="submit">Create account</button>
      </form>

      <p class="hint" style="margin-top:10px;">
        Already have an account?
        <a href="{{ url_for('login') }}">Log in</a>.
      </p>

      {% if error %}
        <div class="error">{{ error }}</div>
      {% endif %}
    </div>
    """


    # First render the inner content template so Jinja tags inside it work
    inner = render_template_string(
        content,
        error=error,
    )

    # Then inject that rendered HTML into the base template
    html = render_template_string(
        BASE_TEMPLATE,
        content=inner,
        active_page="login",
        has_uid=has_uid_flag(),
    )
    return html



@app.route("/login", methods=["GET", "POST"])
def login():
    error: Optional[str] = None

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = (request.form.get("password") or "").strip()

        if not username or not password:
            error = "Username and password are required."
        else:
            conn = get_db_connection()
            try:
                cur = conn.cursor()
                cur.execute(
                    "SELECT id, password_hash FROM users WHERE username = ?",
                    (username,),
                )
                row = cur.fetchone()
                if not row:
                    error = "Invalid username or password."
                else:
                    user_id = row["id"]
                    pwd_hash = row["password_hash"]
                    if not check_password_hash(pwd_hash, password):
                        error = "Invalid username or password."
                    else:
                        session["user_id"] = user_id
                        session["username"] = username
                        return redirect(url_for("boosts"))
            finally:
                conn.close()

    content = """
    <div class="card">
      <h1>Log In</h1>
      <p class="subtle">
        Log into your account so your <strong>Mastery &amp; Workshop</strong> boosts
        follow you, even while you swap Voya UIDs to spy on other accounts.
      </p>

      <form method="post" class="section">
        <label for="username">Username</label>
        <input id="username" name="username" type="text" required maxlength="64" value="{{ request.form.get('username','') }}">

        <label for="password" style="margin-top:10px;">Password</label>
        <input id="password" name="password" type="password" required>

        <button type="submit">Log in</button>
      </form>

      <p class="hint" style="margin-top:10px;">
        Need an account?
        <a href="{{ url_for('register') }}">Create one</a>.
      </p>

      {% if error %}
        <div class="error">{{ error }}</div>
      {% endif %}
    </div>
    """


    inner = render_template_string(
        content,
        error=error,
    )

    html = render_template_string(
        BASE_TEMPLATE,
        content=inner,
        active_page="login",
        has_uid=has_uid_flag(),
    )
    return html



@app.route("/logout")
def logout():
    session.pop("user_id", None)
    session.pop("username", None)
    return redirect(url_for("index"))

# Helper: read either object.attribute or dict["key"]
def attr_or_key(obj, name, default=None):
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


# -------- Profitability tab (manual mastery + workshop) --------

@app.route("/profitability", methods=["GET", "POST"])
def profitability():
    # Require UID set in Overview (so we know whose factories to pull)
    if not has_uid_flag():
        content = """
        <div class="card">
          <h1>Profitability (Locked)</h1>
          <p class="subtle">
            Enter your Voya UID on the <strong>Overview</strong> tab to unlock
            automatic factory list. Mastery & Workshop are set manually here.
          </p>
        </div>
        """
        html = render_template_string(
            BASE_TEMPLATE,
            content=content,
            active_page="profit",
            has_uid=has_uid_flag(),
        )
        return html

    error = None
    uid = session.get("voya_uid")

        # 1) Load factories from Craft World (by UID)
    player_factories: List[dict] = []
    try:
        cw = fetch_craftworld(uid)
        owned: Dict[tuple, int] = {}

        # landPlots: supports both cw["landPlots"] and cw.landPlots
        land_plots = attr_or_key(cw, "landPlots", []) or []
        for plot in land_plots:
            areas = attr_or_key(plot, "areas", []) or []
            for area in areas:
                factories = attr_or_key(area, "factories", []) or []
                for facwrap in factories:
                    fac = attr_or_key(facwrap, "factory", None)
                    if not fac:
                        continue

                    definition = attr_or_key(fac, "definition", {}) or {}
                    token = attr_or_key(definition, "id", None)
                    if not token:
                        continue

                    api_level = int(attr_or_key(fac, "level", 0) or 0)
                    csv_level = api_level + 1  # API 0-based → CSV 1-based
                    key = (str(token).upper(), csv_level)
                    owned[key] = owned.get(key, 0) + 1

        for (token, level), count in owned.items():
            token = str(token).upper()
            if token in FACTORIES_FROM_CSV and level in FACTORIES_FROM_CSV[token]:
                player_factories.append(
                    {"token": token, "level": level, "count": count}
                )

    except Exception as e:
        error = f"Error fetching CraftWorld factories: {e}"
        player_factories = []


    # Fallback: if nothing from account, list everything from CSV
    if not player_factories:
        for t, lvls in FACTORIES_FROM_CSV.items():
            for lvl in sorted(lvls.keys()):
                player_factories.append({"token": t, "level": lvl, "count": 1})

    # 2) Load saved UI state from session
    saved_workers: Dict[str, int] = session.get("profit_workers_csv", {})
    saved_speed: float = float(session.get("profit_speed_csv", 1.0))
    saved_global_yield: float = float(session.get("profit_yield_csv", 100.0))
    saved_selected: Dict[str, bool] = session.get("profit_selected_csv", {})

    # NEW: per-row mastery & workshop levels (manual)
    saved_mastery: Dict[str, int] = session.get("profit_mastery_csv", {})
    saved_workshop: Dict[str, int] = session.get("profit_workshop_csv", {})
    # Sort mode: "standard", "gain_loss", "loss_gain"
    saved_sort_mode: str = session.get("profit_sort_mode", "gain_loss")
    sort_mode: str = saved_sort_mode

    # On a fresh GET, ignore any old per-row overrides so we start
    # from the per-token Boosts defaults for the logged-in user.
    if request.method == "GET":
        saved_mastery = {}
        saved_workshop = {}

    global_speed = saved_speed
    global_yield = saved_global_yield  # fallback if mastery level not in table

    # Per-token default mastery/workshop levels (Boosts tab)
    boost_levels = get_boost_levels()

    # Build row meta (key for each factory row)
    rows_meta: List[dict] = []
    for pf in player_factories:
        key = f"{pf['token']}_L{pf['level']}"
        rows_meta.append(
            {
                "key": key,
                "token": pf["token"].upper(),
                "level": pf["level"],
                "count": pf["count"],
            }
        )

    # 3) Handle POST (user updated speed, mastery, workshop, etc.)
    if request.method == "POST":
        # Global speed & global yield (used as fallback only)
        try:
            global_speed = float(request.form.get("speed_factor", global_speed))
        except ValueError:
            global_speed = saved_speed

        try:
            global_yield = float(request.form.get("yield_pct", global_yield))
        except ValueError:
            global_yield = saved_global_yield
        # Sort mode from form
        mode = (request.form.get("sort_mode") or sort_mode or "gain_loss").strip()
        if mode not in ("standard", "gain_loss", "loss_gain"):
            mode = "gain_loss"
        sort_mode = mode
        session["profit_sort_mode"] = sort_mode

        new_workers: Dict[str, int] = {}
        new_mastery: Dict[str, int] = {}
        new_workshop: Dict[str, int] = {}
        new_selected: set = set()

        for meta in rows_meta:
            key = meta["key"]

            # Workers 0–4
            w_str = request.form.get(f"workers_{key}", str(saved_workers.get(key, 0)))
            try:
                w = int(w_str)
            except ValueError:
                w = 0
            w = max(0, min(4, w))
            new_workers[key] = w

            # Mastery level 0–10
            m_str = request.form.get(
                f"mastery_{key}", str(saved_mastery.get(key, 0))
            )
            try:
                m_level = int(m_str)
            except ValueError:
                m_level = 0
            m_level = max(0, min(10, m_level))
            new_mastery[key] = m_level

            # Workshop level 0–10
            ws_str = request.form.get(
                f"workshop_{key}", str(saved_workshop.get(key, 0))
            )
            try:
                ws_level = int(ws_str)
            except ValueError:
                ws_level = 0
            ws_level = max(0, min(10, ws_level))
            new_workshop[key] = ws_level

            # Run checkbox
            if request.form.get(f"run_{key}") == "on":
                new_selected.add(key)

        # Save back to session
        session["profit_workers_csv"] = new_workers
        session["profit_speed_csv"] = global_speed
        session["profit_yield_csv"] = global_yield
        session["profit_mastery_csv"] = new_mastery
        session["profit_workshop_csv"] = new_workshop

        if new_selected:
            session["profit_selected_csv"] = {
                k: (k in new_selected) for k in [m["key"] for m in rows_meta]
            }
            saved_selected = session["profit_selected_csv"]
        else:
            # if nothing selected explicitly, assume all on
            saved_selected = {m["key"]: True for m in rows_meta}
            session["profit_selected_csv"] = saved_selected

        saved_workers = new_workers
        saved_mastery = new_mastery
        saved_workshop = new_workshop

    # 4) Compute profitability with MANUAL mastery & workshop
    rows: List[dict] = []
    total_coin_hour = 0.0
    total_coin_day = 0.0
    total_usd_hour = 0.0
    total_usd_day = 0.0
    coin_usd = 0.0

    try:
        prices = fetch_live_prices_in_coin()
        coin_usd = float(prices.get("_COIN_USD", 0.0))

        for meta in rows_meta:
            key = meta["key"]
            token = meta["token"]
            level = meta["level"]
            count = meta["count"]

            selected = saved_selected.get(key, True)
            workers = int(saved_workers.get(key, 0))

            # ----- MASTERY → INPUT COST (with per-token default) -----
            token_upper = token.upper()
            default_levels = boost_levels.get(token_upper, {"mastery_level": 0, "workshop_level": 0})
            default_mastery_level = int(default_levels.get("mastery_level", 0))

            # If user hasn't overridden this row, use per-token default from Boosts tab
            mastery_level = int(saved_mastery.get(key, default_mastery_level))
            mastery_level = max(0, min(10, mastery_level))

            mastery_factor = float(MASTERY_BONUSES.get(mastery_level, 1.0))
            yield_pct = 100.0 * mastery_factor  # compute_factory_result_csv expects %

            # Extra safety: if level not found in table, fall back to global yield
            if mastery_level not in MASTERY_BONUSES:
                yield_pct = global_yield

            # ----- WORKSHOP → SPEED (with per-token default) -----
            default_workshop_level = int(default_levels.get("workshop_level", 0))
            workshop_level = int(saved_workshop.get(key, default_workshop_level))
            workshop_level = max(0, min(10, workshop_level))

            ws_table = WORKSHOP_MODIFIERS.get(token_upper)
            workshop_pct = 0.0
            if ws_table and 0 <= workshop_level < len(ws_table):
                workshop_pct = float(ws_table[workshop_level])

            workshop_speed = 1.0 + workshop_pct / 100.0
            effective_speed_factor = global_speed * workshop_speed

            # ----- CALC PROFIT -----
            res = compute_factory_result_csv(
                FACTORIES_FROM_CSV,
                prices,
                token,
                int(level),
                target_level=None,
                count=1,
                yield_pct=yield_pct,               # mastery → input reduction
                speed_factor=effective_speed_factor,  # workshop + AD → time reduction
                workers=workers,
            )

            prof_hour_per = float(res["profit_coin_per_hour"])
            prof_hour_total = prof_hour_per * count
            prof_day_total = prof_hour_total * 24.0

            usd_hour_total = prof_hour_total * coin_usd
            usd_day_total = prof_day_total * coin_usd

            if selected:
                total_coin_hour += prof_hour_total
                total_coin_day += prof_day_total
                total_usd_hour += usd_hour_total
                total_usd_day += usd_day_total

            rows.append(
                {
                    "key": key,
                    "token": token,
                    "level": level,
                    "count": count,
                    "workers": workers,
                    "selected": selected,
                    "mastery_level": mastery_level,
                    "mastery_factor": mastery_factor,
                    "yield_pct": yield_pct,
                    "workshop_level": workshop_level,
                    "workshop_pct": workshop_pct,
                    "profit_hour_per": prof_hour_per,
                    "profit_hour_total": prof_hour_total,
                    "profit_day_total": prof_day_total,
                    "usd_hour_total": usd_hour_total,
                    "usd_day_total": usd_day_total,
                }
            )

                # sort by your fixed factory display order, then by level
        def _row_sort_key(r: dict) -> tuple[int, int]:
            token = str(r["token"]).upper()
            level = int(r["level"])
            idx = FACTORY_DISPLAY_INDEX.get(token, len(FACTORY_DISPLAY_INDEX))
            return (idx, level)

                # Apply selected sort mode
        if sort_mode == "gain_loss":
            # Highest profit/hr first (current behavior)
            rows.sort(key=lambda r: r["profit_hour_total"], reverse=True)
        elif sort_mode == "loss_gain":
            # Most negative first
            rows.sort(key=lambda r: r["profit_hour_total"])
        else:
            # "standard" → your factory order, then level
            def _std_key(r: dict) -> tuple[int, int]:
                token_u = str(r["token"]).upper()
                lvl = int(r["level"])
                idx = STANDARD_ORDER_INDEX.get(token_u, len(STANDARD_ORDER_INDEX))
                return (idx, lvl)

            rows.sort(key=_std_key)



    except Exception as e:
        error = f"{error or ''}\nProfit calculation failed: {e}"

    # 5) Render HTML
    content = """
    <div class="card">
      <h1>Factory Profitability (Manual Mastery + Workshop)</h1>
      <p class="subtle">
        Factory list is loaded from your UID via <code>fetchCraftWorld</code>.<br>
        <strong>Mastery</strong> and <strong>Workshop</strong> levels are set manually per factory (0–10),
        and applied using the official tables.
      </p>

            <form method="post" style="margin-bottom:12px;">
        <div style="display:flex;flex-wrap:wrap;gap:16px;">
          <div style="min-width:160px;">
            <label for="speed_factor">Global Speed (AD / boosts)</label>
            <input type="number" step="0.1" name="speed_factor" value="{{global_speed}}" />
            <div class="hint">Multiplies base time before workshop &amp; workers.</div>
          </div>

          <div style="min-width:160px;">
            <label for="yield_pct">Base Yield % (fallback)</label>
            <input type="number" step="0.1" name="yield_pct" value="{{global_yield}}" />
            <div class="hint">Used only if mastery level not in table.</div>
          </div>

          <div style="min-width:180px;">
            <label for="sort_mode">Sort</label>
            <select name="sort_mode" id="sort_mode">
              <option value="standard" {% if sort_mode == 'standard' %}selected{% endif %}>
                Standard (token order)
              </option>
              <option value="gain_loss" {% if sort_mode == 'gain_loss' %}selected{% endif %}>
                Gain → Loss
              </option>
              <option value="loss_gain" {% if sort_mode == 'loss_gain' %}selected{% endif %}>
                Loss → Gain
              </option>
            </select>
            <div class="hint">Changes row ordering below.</div>
          </div>

          <div style="min-width:260px;">
            <label>Totals (Selected)</label>
            <div class="hint">COIN/hr: {{ '%.6f'|format(total_coin_hour) }}</div>
            <div class="hint">COIN/day: {{ '%.6f'|format(total_coin_day) }}</div>
            <div class="hint">USD/hr: {{ '%.4f'|format(total_usd_hour) }}</div>
            <div class="hint">USD/day: {{ '%.4f'|format(total_usd_day) }}</div>
          </div>
        </div>


        {% if error %}
          <div class="error">{{error}}</div>
        {% endif %}

        <div style="margin-top:14px;overflow-x:auto;">
          <table>
            <tr>
              <th>Run</th>
              <th>Token</th>
              <th>Lvl</th>
              <th>Count</th>
              <th>Mastery Lvl</th>
              <th>Yield %</th>
              <th>Workshop Lvl</th>
              <th>WS Speed %</th>
              <th>Workers</th>
              <th>P/hr (1)</th>
              <th>P/hr (All)</th>
              <th>P/day</th>
              <th>USD/hr</th>
            </tr>

            {% for r in rows %}
            <tr>
              <td>
                <input type="checkbox" name="run_{{r.key}}" {% if r.selected %}checked{% endif %}>
              </td>
              <td>{{r.token}}</td>
              <td>{{r.level}}</td>
              <td>{{r.count}}</td>

              <td>
                <input type="number"
                       min="0" max="10"
                       name="mastery_{{r.key}}"
                       value="{{r.mastery_level}}"
                       style="width:60px;">
              </td>
              <td>{{ '%.2f'|format(r.yield_pct) }}</td>

              <td>
                <input type="number"
                       min="0" max="10"
                       name="workshop_{{r.key}}"
                       value="{{r.workshop_level}}"
                       style="width:60px;">
              </td>
              <td>{{ '%.2f'|format(r.workshop_pct) }}</td>

              <td>
                <input type="number"
                       min="0" max="4"
                       name="workers_{{r.key}}"
                       value="{{r.workers}}"
                       style="width:60px;">
              </td>

              <td>{{ '%.6f'|format(r.profit_hour_per) }}</td>
              <td>{{ '%.6f'|format(r.profit_hour_total) }}</td>
              <td>{{ '%.6f'|format(r.profit_day_total) }}</td>
              <td>{{ '%.4f'|format(r.usd_hour_total) }}</td>
            </tr>
            {% endfor %}
          </table>
        </div>

        <button type="submit" style="margin-top:12px;">Update</button>
      </form>
    </div>
    """

    html = render_template_string(
        BASE_TEMPLATE,
        content=render_template_string(
            content,
            rows=rows,
            error=error,
            global_speed=global_speed,
            global_yield=global_yield,
            total_coin_hour=total_coin_hour,
            total_coin_day=total_coin_day,
            total_usd_hour=total_usd_hour,
            total_usd_day=total_usd_day,
            coin_usd=coin_usd,
            sort_mode=sort_mode,
        ),
        active_page="profit",
        has_uid=has_uid_flag(),
    )
    return html

# -------- Boosts tab (per-token mastery / workshop levels) --------


@app.route("/boosts", methods=["GET", "POST"])
def boosts():
    """
    Per-token Mastery & Workshop levels.

    These levels act as your default boosts for each resource and are
    automatically used as the baseline in the Profitability tab. You can
    still override per factory-row there if you want to fine-tune.
    """
    factories = FACTORIES_FROM_CSV or {}
# Use your fixed display order (MUD → ... → DYNAMITE)
    tokens = FACTORY_DISPLAY_ORDER
    levels_map = get_boost_levels()

    if request.method == "POST":
        for tok in tokens:
            field_m = f"mastery_{tok}"
            field_w = f"workshop_{tok}"

            # mastery level 0–10
            if field_m in request.form:
                raw_m = (request.form.get(field_m) or "").strip()
                try:
                    m_level = int(raw_m or "0")
                except ValueError:
                    m_level = levels_map[tok]["mastery_level"]
                m_level = max(0, min(10, m_level))
                levels_map[tok]["mastery_level"] = m_level

            # workshop level 0–10
            if field_w in request.form:
                raw_w = (request.form.get(field_w) or "").strip()
                try:
                    w_level = int(raw_w or "0")
                except ValueError:
                    w_level = levels_map[tok]["workshop_level"]
                w_level = max(0, min(10, w_level))
                levels_map[tok]["workshop_level"] = w_level

        save_boost_levels(levels_map)

    content = """
    <div class="card">
      <h1>Mastery &amp; Workshop Boosts (Per Token)</h1>
      <p class="subtle">
        Set your <strong>account-wide</strong> Mastery &amp; Workshop levels per resource (0–10).<br>
        These levels are used as defaults in the <strong>Profitability</strong> tab for every factory
        that produces that token. You can still override a specific factory row there.
      </p>

      <form method="post">
        <div style="max-height:500px;overflow:auto;">
          <table>
            <tr>
              <th style="position:sticky;top:0;background:#020617;">Token</th>
              <th style="position:sticky;top:0;background:#020617;">Mastery level (0–10)</th>
              <th style="position:sticky;top:0;background:#020617;">Workshop level (0–10)</th>
            </tr>
            {% for tok in tokens %}
              {% set lvl = levels_map.get(tok, {}) %}
              <tr>
                <td>{{ tok }}</td>
                <td>
                  <input
                    type="number"
                    min="0"
                    max="10"
                    name="mastery_{{ tok }}"
                    value="{{ lvl.get('mastery_level', 0) }}"
                    style="width:80px;"
                  >
                </td>
                <td>
                  <input
                    type="number"
                    min="0"
                    max="10"
                    name="workshop_{{ tok }}"
                    value="{{ lvl.get('workshop_level', 0) }}"
                    style="width:80px;"
                  >
                </td>
              </tr>
            {% endfor %}
          </table>
        </div>

        <div style="margin-top:12px;display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;">
          <div class="hint">
            Mastery level uses the <code>MASTERY_BONUSES</code> table to reduce inputs.<br>
            Workshop level uses <code>WORKSHOP_MODIFIERS</code> per token to speed up crafts.
          </div>
          <button type="submit">Save boosts</button>
        </div>
      </form>
    </div>
    """

    html = render_template_string(
        BASE_TEMPLATE,
        content=render_template_string(
            content,
            tokens=tokens,
            levels_map=levels_map,
        ),
        active_page="boosts",
        has_uid=has_uid_flag(),
    )
    return html

# ================= MASTERPIECES TAB TEMPLATE ==================
content = """
<div class="card">
  <h1>Masterpieces</h1>

  {% if error %}
    <div class="error">{{ error }}</div>
  {% endif %}

  <div class="tabs">
    <a href="#general">General MPs</a>
    <a href="#event">Event MPs</a>
    <a href="#history">History</a>
    <a href="#planner">Donation Planner</a>
  </div>

  <div id="general">
    <h2>Current General Masterpiece</h2>
    {% if current_mp %}
      <p><strong>{{ current_mp.name }}</strong> (ID {{ current_mp.id }})</p>
      {{ current_mp_top50|safe }}
    {% else %}
      <p>No general masterpiece found.</p>
    {% endif %}
  </div>

  <div id="event">
    <h2>Current Event Masterpiece</h2>
    {% if current_event_mp %}
      <p><strong>{{ current_event_mp.name }}</strong> (ID {{ current_event_mp.id }})</p>
      {{ selected_mp_top50|safe }}
    {% else %}
      <p>No event masterpiece found.</p>
    {% endif %}
  </div>

  <div id="history">
    <h2>History & Selector</h2>
    <form method="post">
      <select name="history_mp">
        <option value="">-- Select Masterpiece --</option>
        {% for opt in history_mp_options %}
          <option value="{{ opt.id }}"
            {% if selected_mp and selected_mp.id|string == opt.id|string %}selected{% endif %}>
            {{ opt.label }}
          </option>
        {% endfor %}
      </select>
      <input type="text" name="highlight_query" placeholder="Your name or Voya ID" value="{{ highlight_query }}">
      <button type="submit">Load</button>
    </form>

    {% if selected_mp %}
      <h3>{{ selected_mp.name }} (ID {{ selected_mp.id }})</h3>
      {{ selected_mp_top50|safe }}
    {% endif %}
  </div>

  <div id="planner">
    <h2>Donation Planner</h2>
    {{ calc_result|safe }}
  </div>
</div>
"""
# ================= END MASTERPIECES TEMPLATE ==================

@app.route("/masterpieces", methods=["GET", "POST"])
def masterpieces_view():
    """
    Masterpiece Hub:
      - Donation Planner (per-unit MP points, live COIN cost, tier progress)
      - Live leaderboard for the current masterpiece (top 50)
      - History & Event browser (top 50 by MP, grouped general/event)
    """
    error: Optional[str] = None
    masterpieces_data: List[Dict[str, Any]] = []

    # Load MP list from Craft World
    try:
        masterpieces_data = fetch_masterpieces()
    except Exception as e:
        error = f"Error fetching masterpieces: {e}"
        masterpieces_data = []

    # Split masterpieces into general vs event
    general_mps: List[Dict[str, Any]] = []
    event_mps: List[Dict[str, Any]] = []

    for mp in masterpieces_data:
        event_id = mp.get("eventId")
        if event_id:
            event_mps.append(mp)
        else:
            general_mps.append(mp)

    # Sort by ID so "latest" really is highest ID
    def _mp_id(m: Dict[str, Any]) -> int:
        try:
            return int(m.get("id") or 0)
        except (TypeError, ValueError):
            return 0

    general_mps = sorted(general_mps, key=_mp_id)
    event_mps = sorted(event_mps, key=_mp_id)
    
    # Identify the "active" general and event masterpieces (highest ID)
    current_general_mp: Optional[Dict[str, Any]] = general_mps[-1] if general_mps else None
    current_event_mp: Optional[Dict[str, Any]] = event_mps[-1] if event_mps else None

    # For the active ones, pull full details (including leaderboard / rewards)
    # so the "Current MP" tab and reward snapshots have data.
    try:
        if current_general_mp and not current_general_mp.get("leaderboard"):
            try:
                cg_id = int(current_general_mp.get("id") or 0)
            except Exception:
                cg_id = 0
            if cg_id:
                try:
                    detailed = fetch_masterpiece_details(cg_id)
                    current_general_mp = detailed
                    try:
                        cache_masterpiece_metadata(detailed)
                    except Exception:
                        pass
                except Exception:
                    # If this fails, we still keep the lightweight summary object.
                    pass
    except Exception:
        pass

    try:
        if current_event_mp and not current_event_mp.get("leaderboard"):
            try:
                ce_id = int(current_event_mp.get("id") or 0)
            except Exception:
                ce_id = 0
            if ce_id:
                try:
                    detailed = fetch_masterpiece_details(ce_id)
                    current_event_mp = detailed
                    try:
                        cache_masterpiece_metadata(detailed)
                    except Exception:
                        pass
                except Exception:
                    pass
    except Exception:
        pass

    # Hydrate the active masterpieces so they include leaderboard/rewards data
    def _hydrate_masterpiece(mp: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not isinstance(mp, dict):
            return None
        mp_id = mp.get("id")
        try:
            mid_int = int(mp_id or 0)
        except (TypeError, ValueError):
            return mp
        if mid_int <= 0:
            return mp
        try:
            detailed = fetch_masterpiece_details(mid_int)
        except Exception as e:
            print(f"[MP] Failed to hydrate masterpiece {mp_id}: {e}")
            return mp

        # Merge base + detailed so we keep type/eventId/addressableLabel etc.
        merged = dict(mp)
        if isinstance(detailed, dict):
            for k, v in detailed.items():
                if v not in (None, ""):
                    merged[k] = v

        # Cache basic metadata for future loads (name/label/type)
        try:
            cache_masterpiece_metadata(merged)
        except Exception:
            pass

        return merged

    current_general_mp = _hydrate_masterpiece(current_general_mp)
    current_event_mp = _hydrate_masterpiece(current_event_mp)


    # Build a lookup by ID and compute the highest MP ID we know about.
    mp_by_id: Dict[int, Dict[str, Any]] = {}
    max_mp_id = 0
    for mp in masterpieces_data:
        try:
            mid = int(mp.get("id") or 0)
        except (TypeError, ValueError):
            continue
        if mid > 0:
            mp_by_id[mid] = mp
            if mid > max_mp_id:
                max_mp_id = mid
    # Seed the metadata cache with the list we just fetched.
    for mp in masterpieces_data:
        try:
            cache_masterpiece_metadata(mp)
        except Exception:
            pass

    # Merge cached metadata back into mp_by_id and extend max_mp_id if needed.
    try:
        mp_cache = load_masterpiece_metadata_cache()
    except Exception:
        mp_cache = {}

    for mid, meta in mp_cache.items():
        if mid in mp_by_id:
            base = dict(mp_by_id[mid])
            # Overlay stored fields without blowing away other keys.
            for key, val in meta.items():
                if val not in (None, ""):
                    base[key] = val
            mp_by_id[mid] = base
        else:
            mp_by_id[mid] = dict(meta)
        if mid > max_mp_id:
            max_mp_id = mid
    # ----- How many leaderboard entries to show? (Top 10 / 25 / 50 / 100) -----
    TOP_N_OPTIONS = [10, 25, 50, 100]
    DEFAULT_TOP_N = 50

    # Try to read from query (GET/POST), then fall back to session
    top_n = session.get("mp_top_n", DEFAULT_TOP_N)
    top_n_str = (request.args.get("top_n") or request.form.get("top_n") or "").strip()

    if top_n_str:
        try:
            val = int(top_n_str)
            if val in TOP_N_OPTIONS:
                top_n = val
        except ValueError:
            pass

    if top_n not in TOP_N_OPTIONS:
        top_n = DEFAULT_TOP_N

    # Persist per logged-in browser session
    session["mp_top_n"] = top_n
    
    # Highlight name / UID across leaderboards
    highlight_query = (request.args.get("highlight") or request.form.get("highlight") or "").strip()
    if highlight_query:
        # Save to session so it sticks when you switch tabs / refresh
        session["mp_highlight"] = highlight_query
    else:
        highlight_query = session.get("mp_highlight", "") or ""

    # Which sub-tab is active: "planner", "current", or "history"?
    tab = (request.args.get("tab") or request.form.get("tab") or "").strip() or "planner"

    

    # Pick the "current" masterpiece (for the live leaderboard):
    # latest general if available, otherwise latest event.
    current_mp: Optional[Dict[str, Any]] = None
    current_mp_top50: List[Dict[str, Any]] = []

    if current_general_mp is not None:
        current_mp = current_general_mp
    elif current_event_mp is not None:
        current_mp = current_event_mp

    if current_mp:
        lb = current_mp.get("leaderboard") or []
        try:
            current_mp_top50 = list(lb[:top_n])
        except Exception:
            current_mp_top50 = []
    else:
        current_mp_top50 = []



    # ---------- Personal reward snapshots for active general & event MPs ----------
    general_snapshot: Optional[Dict[str, Any]] = None
    event_snapshot: Optional[Dict[str, Any]] = None

    # Use the same highlight_query the user entered at the top of the page.
    if highlight_query:
        # Active general MP snapshot
        if current_general_mp:
            try:
                gen_rows = list((current_general_mp.get("leaderboard") or [])[:top_n])
            except Exception:
                gen_rows = []
            general_snapshot = _build_reward_snapshot_for_mp(
                current_general_mp,
                gen_rows,
                highlight_query,
            )

        # Active event MP snapshot
        if current_event_mp:
            try:
                event_rows = list((current_event_mp.get("leaderboard") or [])[:top_n])
            except Exception:
                event_rows = []
            event_snapshot = _build_reward_snapshot_for_mp(
                current_event_mp,
                event_rows,
                highlight_query,
            )


    # Gap info for highlighted player on the current leaderboard
    current_gap: Optional[Dict[str, Any]] = compute_leaderboard_gap_for_highlight(
        current_mp_top50,
        highlight_query,
    )

    # This will be set after resolving the planner target masterpiece.
    mp_id_for_calc: Optional[str] = None

    # ----- Planner target masterpiece (Donation Planner uses this) -----
    # Build planner options as MP1 .. MP[max_mp_id], even if we haven't pulled them yet.
    planner_mp_options: List[Dict[str, Any]] = []
    if max_mp_id > 0:
        for mid in range(1, max_mp_id + 1):
            mp = mp_by_id.get(mid, {"id": mid})
            planner_mp_options.append(mp)
    else:
        # Fallback if we somehow have no IDs: just use whatever general list we have.
        planner_mp_options = list(general_mps)

    planner_mp: Optional[Dict[str, Any]] = None

    planner_mp_id: str = (request.args.get("planner_mp_id") or request.form.get("planner_mp_id") or "").strip()

    if planner_mp_id:
        for mp in planner_mp_options:
            if str(mp.get("id")) == str(planner_mp_id):
                planner_mp = mp
                break

        # If we found it but it's missing a name/label, fetch details and update.
        if planner_mp and not (
            planner_mp.get("name")
            or planner_mp.get("addressableLabel")
            or planner_mp.get("addressable_label")
            or planner_mp.get("type")
        ):
            try:
                detailed = fetch_masterpiece_details(planner_mp_id)
                # update in-place so the dropdown sees the name
                planner_mp.clear()
                planner_mp.update(detailed)
                cache_masterpiece_metadata(detailed)
            except Exception:
                pass

    # Default to the latest general masterpiece if nothing selected or invalid.
    if not planner_mp and general_mps:
        planner_mp = general_mps[-1]

    if planner_mp:
        mp_id_for_calc = str(planner_mp.get("id") or "")
        # Also store/refresh this one in the DB for future loads
        try:
            cache_masterpiece_metadata(planner_mp)
        except Exception:
            pass
    # Figure out which resources are valid for the selected planner masterpiece.
    # Default: show all factory tokens; if we can, narrow to only tokens this MP accepts.
    planner_tokens: List[str] = list(ALL_FACTORY_TOKENS)

    mp_id_for_resources: Optional[str] = None
    if planner_mp:
        try:
            mp_id_for_resources = str(planner_mp.get("id") or "") or None
        except Exception:
            mp_id_for_resources = None
    if not mp_id_for_resources and planner_mp_id:
        mp_id_for_resources = str(planner_mp_id)

    if mp_id_for_resources:
        try:
            mp_detail_for_planner = fetch_masterpiece_details(mp_id_for_resources)
            resources = mp_detail_for_planner.get("resources") or []
            symbols: List[str] = []
            for r in resources:
                sym = (r.get("symbol") or "").upper()
                if sym and sym in ALL_FACTORY_TOKENS:
                    symbols.append(sym)

            if symbols:
                # Sort using your standard factory display order when possible.
                def _sort_key(sym: str) -> int:
                    try:
                        return FACTORY_DISPLAY_INDEX.get(sym, 9999)
                    except Exception:
                        return ALL_FACTORY_TOKENS.index(sym) if sym in ALL_FACTORY_TOKENS else 9999

                planner_tokens = sorted({s for s in symbols}, key=_sort_key)
        except Exception:
            # If anything fails, just fall back to the full token list.
            planner_tokens = list(ALL_FACTORY_TOKENS)
    else:
        planner_tokens = list(ALL_FACTORY_TOKENS)




    # ----- Masterpiece selector for "History & Events" leaderboard browser -----

    # Build a simple list of MP1 .. MP[max_mp_id] for the dropdown, even if
    # we don't yet have them in `masterpieces_data`.
    history_mp_options: List[Dict[str, Any]] = []
    if max_mp_id > 0:
        for mid in range(1, max_mp_id + 1):
            mp = mp_by_id.get(mid, {"id": mid})
            history_mp_options.append(mp)
    else:
        # Fallback: just whatever masterpieces we have.
        history_mp_options = list(masterpieces_data)

    # Which masterpiece should the browser leaderboard show?
    selected_mp_id = request.args.get("mp_view_id")
    if not selected_mp_id:
        if current_mp:
            selected_mp_id = str(current_mp.get("id") or "")
        elif max_mp_id > 0:
            selected_mp_id = str(max_mp_id)

    selected_mp: Optional[Dict[str, Any]] = None
    selected_mp_top50: List[Dict[str, Any]] = []

    if selected_mp_id:
        try:
            # Always fetch fresh details so it works even for MPs we don't have
            # in the initial `masterpieces` list.
            selected_mp = fetch_masterpiece_details(selected_mp_id)
            # Cache its metadata for future loads
            try:
                cache_masterpiece_metadata(selected_mp)
            except Exception:
                pass

            # Update history_mp_options entry so the dropdown label gets the name
            try:
                mid_int = int(selected_mp.get("id") or 0)
            except (TypeError, ValueError):
                mid_int = 0
            if mid_int:
                for mp in history_mp_options:
                    try:
                        if int(mp.get("id") or 0) == mid_int:
                            mp.clear()
                            mp.update(selected_mp)
                            break
                    except Exception:
                        continue

            lb = selected_mp.get("leaderboard") or []
            try:
                selected_mp_top50 = list(lb[:top_n])
            except Exception:
                selected_mp_top50 = []
        except Exception:
            selected_mp = None
            selected_mp_top50 = []


    if not selected_mp and current_mp:
        # Fallback: show current_mp leaderboard if selector fails
        selected_mp = current_mp
        selected_mp_top50 = current_mp_top50

    # Gap info for highlighted player on the selected/history leaderboard
    selected_gap: Optional[Dict[str, Any]] = compute_leaderboard_gap_for_highlight(
        selected_mp_top50,
        highlight_query,
    )




    # ---------- Donation Planner state (list of {token, amount}) ----------
    calc_resources: List[Dict[str, Any]] = []
    calc_result: Optional[Dict[str, Any]] = None

    if request.method == "POST":
        action = (request.form.get("calc_action") or "").strip().lower()

        # Detect if the planner Masterpiece changed; if so, wipe the previous bundle.
        last_planner_mp = session.get("planner_mp_id_for_planner") or ""
        current_planner_mp = (request.form.get("planner_mp_id") or "").strip()
        changed_mp = bool(current_planner_mp and current_planner_mp != last_planner_mp)

        # Persist the latest planner MP selection so we can compare on the next POST.
        if current_planner_mp:
            session["planner_mp_id_for_planner"] = current_planner_mp
        elif planner_mp_id:
            session["planner_mp_id_for_planner"] = planner_mp_id

        state_raw = request.form.get("calc_state") or "[]"

        # Load previous state from hidden JSON field, unless the MP changed
        if not changed_mp:
            try:
                loaded = json.loads(state_raw)
                if isinstance(loaded, list):
                    for row in loaded:
                        if not isinstance(row, dict):
                            continue
                        tok = str(row.get("token", "")).upper().strip()
                        try:
                            amt = float(row.get("amount", 0) or 0)
                        except (TypeError, ValueError):
                            amt = 0.0
                        if tok and amt > 0:
                            calc_resources.append({"token": tok, "amount": amt})
            except Exception:
                calc_resources = []


        # Apply the current action
        if action == "add":
            tok = (request.form.get("calc_token") or "").upper().strip()
            amt_raw = (request.form.get("calc_amount") or "").replace(",", "").strip()
            try:
                amt = float(amt_raw or "0")
            except ValueError:
                amt = 0.0
            if tok and amt > 0:
                calc_resources.append({"token": tok, "amount": amt})

        elif action == "clear":
            calc_resources = []

        # ---------- Compute totals if we have resources ----------
        if calc_resources and not error:
            # 1) Live prices → total COIN cost
            try:
                prices = fetch_live_prices_in_coin()
            except Exception:
                prices = {}

            total_cost = 0.0
            for row in calc_resources:
                price = prices.get(row["token"], 0.0) or 0.0
                total_cost += float(row["amount"]) * float(price)

            # 2) Total points + XP + battery (requiredPower) via predict_reward
            total_points = 0.0
            total_xp = 0.0
            total_power = 0.0
            per_unit_points: Dict[str, float] = {}
            per_unit_xp: Dict[str, float] = {}
            per_unit_power: Dict[str, float] = {}

            if mp_id_for_calc:
                # First: total points / XP / power for the whole bundle
                try:
                    contrib = [
                        {"symbol": r["token"], "amount": float(r["amount"])}
                        for r in calc_resources
                    ]
                    reward = predict_reward(mp_id_for_calc, contrib) or {}
                    total_points = float(reward.get("masterpiecePoints") or 0)
                    total_xp = float(reward.get("experiencePoints") or 0)
                    total_power = float(reward.get("requiredPower") or 0)
                except Exception:
                    total_points = 0.0
                    total_xp = 0.0
                    total_power = 0.0

                # Then: per-unit cache so each row can show its own contribution
                try:
                    per_unit = get_mp_per_unit_rewards(
                        mp_id_for_calc,
                        [r.get("token", "") for r in calc_resources],
                    )
                    per_unit_points = per_unit.get("points", {}) or {}
                    per_unit_xp = per_unit.get("xp", {}) or {}
                    per_unit_power = per_unit.get("power", {}) or {}
                except Exception:
                    per_unit_points = {}
                    per_unit_xp = {}
                    per_unit_power = {}

            # Per-row points / XP / battery (safe even if we have no per-unit data)
            for row in calc_resources:
                tok = (row.get("token") or "").upper()
                try:
                    amt = float(row.get("amount") or 0.0)
                except (TypeError, ValueError):
                    amt = 0.0

                p_unit = per_unit_points.get(tok, 0.0)
                x_unit = per_unit_xp.get(tok, 0.0)
                pw_unit = per_unit_power.get(tok, 0.0)
                row_points = p_unit * amt
                row_xp = x_unit * amt
                row_power = pw_unit * amt

                row["points_str"] = f"{row_points:,.0f}" if row_points else "—"
                row["xp_str"] = f"{row_xp:,.0f}" if row_xp else "—"
                row["battery_str"] = f"{row_power:,.0f}" if row_power else "—"


            # 3) Map to tiers
            tier = 0
            next_tier_index: Optional[int] = None
            points_to_next: Optional[float] = None
            progress_to_next: Optional[float] = None

            for i, req in enumerate(MP_TIER_THRESHOLDS, start=1):
                if total_points >= req:
                    tier = i
                else:
                    next_tier_index = i
                    points_to_next = max(0.0, float(req) - total_points)
                    progress_to_next = total_points / float(req) if req > 0 else 0.0
                    break

            if tier == len(MP_TIER_THRESHOLDS):
                next_tier_index = None
                points_to_next = None
                progress_to_next = 1.0

            calc_result = {
                "total_points": total_points,
                "total_points_str": f"{total_points:,.0f}",
                "total_xp": total_xp,
                "total_xp_str": f"{total_xp:,.0f}",
                "total_power": total_power,
                "total_power_str": f"{total_power:,.0f}",
                "total_cost": total_cost,
                "total_cost_str": f"{total_cost:,.2f}",
                "tier": tier,
                "next_tier_index": next_tier_index,
                "points_to_next": points_to_next,
                "points_to_next_str": (
                    f"{points_to_next:,.0f}" if points_to_next is not None else None
                ),
                "progress_to_next_pct": (
                    round(progress_to_next * 100, 1)
                    if progress_to_next is not None
                    else None
                ),
            }

    # Serialize calculator state back into hidden JSON field
    calc_state_json = json.dumps(calc_resources)

    # ---------- Tier thresholds (static ladder) ----------
    tier_rows = []
    for i, req in enumerate(MP_TIER_THRESHOLDS, start=1):
        prev_req = MP_TIER_THRESHOLDS[i - 2] if i > 1 else 0
        tier_rows.append(
            {
                "tier": i,
                "required": req,
                "delta": req - prev_req,
            }
        )

    # ---------- Tier rewards from the Masterpiece (rewardStages) ----------
    reward_tier_rows: list[dict[str, object]] = []

    # Use the planner MP as the "source of truth" for tier rewards
    # (you can swap to selected_mp/current_mp if you want)
    src_mp = planner_mp or selected_mp or current_mp

    if isinstance(src_mp, dict):
        raw_stages = src_mp.get("rewardStages") or []

        # rewardStages can be either a list or dict; normalise to list
        if isinstance(raw_stages, dict):
            stages_iter = list(raw_stages.values())
        elif isinstance(raw_stages, list):
            stages_iter = raw_stages
        else:
            stages_iter = []

        for idx, st in enumerate(stages_iter, start=1):
            if not isinstance(st, dict):
                continue

            # Try to guess tier index and required points from common keys
            tier_num = st.get("tier") or st.get("stage") or idx
            required = (
                st.get("requiredPoints")
                or st.get("minPoints")
                or st.get("minimumPoints")
                or st.get("points")
            )

            rewards_list = st.get("rewards") or st.get("items") or []
            reward_parts: list[str] = []

            if isinstance(rewards_list, list):
                for rw in rewards_list:
                    if not isinstance(rw, dict):
                        continue

                    amount = rw.get("amount") or rw.get("quantity")
                    token = rw.get("token") or rw.get("symbol") or rw.get("resource")
                    rtype = rw.get("type") or rw.get("rewardType") or rw.get("__typename")

                    label_bits: list[str] = []
                    if amount not in (None, "", 0):
                        label_bits.append(str(amount))
                    if token:
                        label_bits.append(str(token))
                    elif rtype:
                        label_bits.append(str(rtype))

                    label = " ".join(label_bits).strip()
                    if label:
                        reward_parts.append(label)

            if not reward_parts:
                reward_parts.append("See in-game rewards")

            reward_tier_rows.append(
                {
                    "tier": tier_num,
                    "required": required,
                    "rewards_text": ", ".join(reward_parts),
                }
            )

    # ---------- Leaderboard placement rewards (leaderboardRewards) ----------
    leaderboard_reward_rows: list[dict[str, object]] = []

    if isinstance(selected_mp, dict):
        raw_lb_rewards = (
            selected_mp.get("leaderboardRewards")
            or selected_mp.get("leaderboardRewardStages")
            or []
        )

        if isinstance(raw_lb_rewards, dict):
            lb_iter = list(raw_lb_rewards.values())
        elif isinstance(raw_lb_rewards, list):
            lb_iter = raw_lb_rewards
        else:
            lb_iter = []

        for blk in lb_iter:
            if not isinstance(blk, dict):
                continue

            from_rank = blk.get("from") or blk.get("fromRank")
            to_rank = blk.get("to") or blk.get("toRank")

            rewards_list = blk.get("rewards") or blk.get("items") or []
            reward_parts: list[str] = []

            if isinstance(rewards_list, list):
                for rw in rewards_list:
                    if not isinstance(rw, dict):
                        continue
                    amount = rw.get("amount") or rw.get("quantity")
                    token = rw.get("token") or rw.get("symbol") or rw.get("resource")
                    rtype = rw.get("type") or rw.get("rewardType") or rw.get("__typename")

                    label_bits: list[str] = []
                    if amount not in (None, "", 0):
                        label_bits.append(str(amount))
                    if token:
                        label_bits.append(str(token))
                    elif rtype:
                        label_bits.append(str(rtype))

                    label = " ".join(label_bits).strip()
                    if label:
                        reward_parts.append(label)

            if not reward_parts:
                reward_parts.append("See in-game rewards")

            leaderboard_reward_rows.append(
                {
                    "from_rank": from_rank,
                    "to_rank": to_rank,
                    "rewards_text": ", ".join(reward_parts),
                }
            )


    # ---------- Render content for this tab ----------
    content = """
    <div class="card">
      <style>
        .mp-top-summary {
          margin-top: 8px;
          margin-bottom: 10px;
        }
        .mp-summary-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
          gap: 8px;
        }
        .mp-summary-tile {
          border-radius: 12px;
          padding: 8px 10px;
          background: radial-gradient(circle at top, rgba(30,64,175,0.55), rgba(15,23,42,0.95));
          border: 1px solid rgba(129,140,248,0.7);
          font-size: 13px;
        }
        .mp-summary-title {
          font-size: 12px;
          text-transform: uppercase;
          letter-spacing: 0.05em;
          color: #bfdbfe;
          margin-bottom: 2px;
        }
        .mp-summary-main {
          font-size: 14px;
          font-weight: 600;
          color: #f9fafb;
        }
        .mp-summary-sub {
          font-size: 12px;
          color: #9ca3af;
        }

        .mp-subnav {
          margin-top: 14px;
          margin-bottom: 6px;
          display: flex;
          flex-wrap: wrap;
          gap: 6px;
        }
        .mp-tab {
          border-radius: 999px;
          border: 1px solid rgba(148,163,184,0.7);
          background: rgba(15,23,42,0.9);
          padding: 5px 11px;
          font-size: 13px;
          color: #e5e7eb;
          cursor: pointer;
          display: inline-flex;
          align-items: center;
          gap: 6px;
        }
        .mp-tab span.icon {
          font-size: 14px;
        }
        .mp-tab.active {
          border-color: transparent;
          background: linear-gradient(135deg, #22c55e, #0ea5e9);
          color: #020617;
          box-shadow: 0 0 0 1px rgba(34,197,94,0.6), 0 8px 24px rgba(34,197,94,0.4);
        }

        .mp-section {
          margin-top: 10px;
        }

        .mp-pill {
          display:inline-block;
          padding: 2px 8px;
          border-radius:999px;
          font-size:11px;
          border:1px solid rgba(52,211,153,0.7);
          color:#a7f3d0;
          background:rgba(6,95,70,0.35);
        }
        .mp-pill-secondary {
          border-color: rgba(129,140,248,0.9);
          color:#c7d2fe;
          background:rgba(30,64,175,0.45);
        }

        .mp-tier-table th,
        .mp-tier-table td {
          white-space: nowrap;
        }

        .mp-planner-grid {
          display:grid;
          grid-template-columns: minmax(0, 260px) minmax(0, 1fr);
          gap: 10px;
        }

        .mp-stat-block {
          display:flex;
          flex-direction:row;
          flex-wrap:wrap;
          gap: 10px;
          font-size:13px;
        }
        .mp-stat-label {
          color:#9ca3af;
          font-size:12px;
        }
        .mp-stat-value {
          font-size:14px;
          font-weight:600;
        }
        .mp-gap-card {
          margin-top: 8px;
          margin-bottom: 8px;
          padding: 10px 12px;
          border-radius: 10px;
          background: linear-gradient(90deg, rgba(56,189,248,0.09), rgba(56,189,248,0.02));
          border: 1px solid rgba(56,189,248,0.45);
        }
        .mp-gap-title {
          font-size: 13px;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.05em;
          color: #38bdf8;
          margin-bottom: 4px;
        }
        .mp-gap-grid {
          display: flex;
          flex-wrap: wrap;
          gap: 12px;
          align-items: flex-end;
        }
        .mp-gap-block {
          min-width: 140px;
        }
        .mp-gap-label {
          font-size: 12px;
          color: #9ca3af;
          margin-bottom: 2px;
        }
        .mp-gap-number {
          font-size: 20px;
          font-weight: 800;
          line-height: 1.1;
        }
        .mp-gap-sub {
          font-size: 12px;
          color: #e5e7eb;
        }


        .mp-row-me {
          background: linear-gradient(90deg, rgba(250,204,21,0.14), transparent);
        }
        .mp-row-me td {
          border-top: 1px solid rgba(250,204,21,0.35);
          border-bottom: 1px solid rgba(250,204,21,0.18);
        }
        .me-pill {
          display:inline-block;
          margin-left:6px;
          padding:1px 6px;
          border-radius:999px;
          font-size:11px;
          border:1px solid rgba(250,204,21,0.7);
          color:#facc15;
          background:rgba(30,64,175,0.65);
        }

        @media (max-width: 768px) {
          .mp-planner-grid {

            grid-template-columns: 1fr;
          }
        }
      </style>

      <h1>🏛 Masterpiece Hub</h1>
      <p class="subtle">
        Plan donations, watch the live race, and browse past &amp; event Masterpieces —
        all wired directly to <code>predictReward</code> and live COIN prices.
      </p>

      <form method="get" class="section" style="margin-top:10px; display:flex; flex-wrap:wrap; gap:8px; align-items:center;">
        <input type="hidden" name="tab" value="{{ request.args.get('tab') or 'planner' }}">
        <label for="mp_highlight" class="subtle">Highlight my name / Voya ID (top 100 only):</label>
        <input id="mp_highlight"
               name="highlight"
               type="text"
               value="{{ highlight_query }}"
               placeholder="Your display name or Voya ID"
               style="min-width:220px;">
        <button type="submit">Apply</button>
        {% if highlight_query %}
          <span class="hint">Highlighting rows matching: <strong>{{ highlight_query }}</strong></span>
        {% else %}
          <span class="hint">Works if you&apos;re in the visible top {{ top_n }}.</span>
        {% endif %}
      </form>


      {% if current_mp %}
        <div class="mp-top-summary">
          <div class="mp-summary-grid">
            <div class="mp-summary-tile">
              <div class="mp-summary-title">Current masterpiece (used for planner)</div>
              <div class="mp-summary-main">
                MP {{ current_mp.id }} — {{ current_mp.name or current_mp.addressableLabel or current_mp.type }}
              </div>
              <div class="mp-summary-sub">
                {% if current_mp.eventId %}
                  <span class="mp-pill">Event Masterpiece</span>
                {% else %}
                  <span class="mp-pill">General Masterpiece</span>
                {% endif %}
                <span style="margin-left:6px;" class="mp-pill mp-pill-secondary">
                  Scoring source for 🧮 Planner
                </span>
              </div>
            </div>
            <div class="mp-summary-tile">
              <div class="mp-summary-title">Masterpiece pool</div>
              <div class="mp-summary-main">
                {{ general_mps|length }} general · {{ event_mps|length }} event
              </div>
              <div class="mp-summary-sub">
                History browser lets you inspect any MP&apos;s top 50 at any time.
              </div>
            </div>
            <div class="mp-summary-tile">
              <div class="mp-summary-title">Live leaderboard snapshot</div>
              <div class="mp-summary-main">
                Top {{ current_mp_top50|length }} tracked
              </div>
              <div class="mp-summary-sub">
                Switch to the <strong>📈 Current MP</strong> tab to see positions &amp; point gaps.
              </div>
            </div>
          </div>
        </div>
      {% endif %}

        {% if highlight_query and (general_snapshot or event_snapshot) %}
        <div class="section" style="margin-top:10px;">
          <h2 style="margin-top:0;">🎁 Your current MP rewards (if it ended now)</h2>
          <p class="subtle">
            Based on your <strong>current leaderboard position</strong> for the active General &amp; Event Masterpieces.
          </p>

          <div class="mp-summary-grid">
            {% if general_snapshot %}
              <div class="mp-summary-tile">
                <div class="mp-summary-title">Active General Masterpiece</div>
                <div class="mp-summary-main">
                  MP {{ general_snapshot.mp.id }} —
                  {{ general_snapshot.mp.name or general_snapshot.mp.addressableLabel or general_snapshot.mp.type }}
                </div>
                <div class="mp-summary-sub">
                  Rank <strong>#{{ general_snapshot.position }}</strong> ·
                  {{ "{:,.0f}".format(general_snapshot.points or 0) }} points<br>
                  {% if general_snapshot.tier %}
                    Completion tier: <strong>Tier {{ general_snapshot.tier }}</strong>
                    {% if general_snapshot.tier_required %}
                      (requires ≥ {{ "{:,.0f}".format(general_snapshot.tier_required or 0) }} pts)
                    {% endif %}
                    <br>
                  {% else %}
                    Completion tier: <strong>Below Tier 1</strong><br>
                  {% endif %}

                  {% if general_snapshot.leaderboard_rewards %}
                    Leaderboard rewards: {{ general_snapshot.leaderboard_rewards }}
                  {% else %}
                    Leaderboard rewards: <span class="subtle">See in-game details</span>
                  {% endif %}
                </div>
              </div>
            {% endif %}

            {% if event_snapshot %}
              <div class="mp-summary-tile">
                <div class="mp-summary-title">Active Event Masterpiece</div>
                <div class="mp-summary-main">
                  MP {{ event_snapshot.mp.id }} —
                  {{ event_snapshot.mp.name or event_snapshot.mp.addressableLabel or event_snapshot.mp.type }}
                </div>
                <div class="mp-summary-sub">
                  Rank <strong>#{{ event_snapshot.position }}</strong> ·
                  {{ "{:,.0f}".format(event_snapshot.points or 0) }} points<br>
                  {% if event_snapshot.tier %}
                    Completion tier: <strong>Tier {{ event_snapshot.tier }}</strong>
                    {% if event_snapshot.tier_required %}
                      (requires ≥ {{ "{:,.0f}".format(event_snapshot.tier_required or 0) }} pts)
                    {% endif %}
                    <br>
                  {% else %}
                    Completion tier: <strong>Below Tier 1</strong><br>
                  {% endif %}

                  {% if event_snapshot.leaderboard_rewards %}
                    Leaderboard rewards: {{ event_snapshot.leaderboard_rewards }}
                  {% else %}
                    Leaderboard rewards: <span class="subtle">See in-game details</span>
                  {% endif %}
                </div>
              </div>
            {% endif %}
          </div>
        </div>
      {% endif %}


      <div class="mp-subnav">
        <button type="button" class="mp-tab active" data-mp-tab="planner">
          <span class="icon">🧮</span> Donation Planner
        </button>
        <button type="button" class="mp-tab" data-mp-tab="current">
          <span class="icon">📈</span> Current MP leaderboard
        </button>
        <button type="button" class="mp-tab" data-mp-tab="history">
          <span class="icon">📜</span> History &amp; events
        </button>
      </div>

      <div class="mp-sections">
        <!-- 🧮 Donation Planner -->
        <div class="mp-section" data-mp-section="planner" style="display:block;">
          <div class="mp-planner-grid">
            <!-- Left: tier table -->
            <div class="section">
              <h2 style="margin-top:0;">Tier ladder</h2>
              <p class="subtle">
                Official tier thresholds for the active general Masterpiece.
              </p>
              <div class="scroll-x">
                <table class="mp-tier-table">
                  <tr>
                    <th>Tier</th>
                    <th>Required points</th>
                    <th>Delta vs previous</th>
                  </tr>
                  {% for row in tier_rows %}
                    <tr>
                      <td>Tier {{ row.tier }}</td>
                      <td>{{ "{:,}".format(row.required) }}</td>
                      <td>
                        {% if row.tier == 1 %}
                          —
                        {% else %}
                          +{{ "{:,}".format(row.delta) }}
                        {% endif %}
                      </td>
                    </tr>
                  {% endfor %}
                </table>
              </div>
            </div>
            <div class="section" style="margin-top:10px;">
              <h3 style="margin-top:0;">Tier rewards</h3>
              <p class="subtle">
                Guaranteed rewards for each completion tier (from the Masterpiece rewardStages API).
              </p>

              {% if reward_tier_rows %}
                <div class="scroll-x">
                  <table class="mp-tier-table">
                    <tr>
                      <th>Tier</th>
                      <th>Required points</th>
                      <th>Rewards</th>
                    </tr>
                    {% for row in reward_tier_rows %}
                      <tr>
                        <td>Tier {{ row.tier or loop.index }}</td>
                        <td>
                          {% if row.required %}
                            {{ "{:,}".format(row.required) }}
                          {% else %}
                            —
                          {% endif %}
                        </td>
                        <td>{{ row.rewards_text }}</td>
                      </tr>
                    {% endfor %}
                  </table>
                </div>
              {% else %}
                <p class="hint">
                  No tier reward metadata in the API for this Masterpiece yet — check in-game rewards.
                </p>
              {% endif %}
            </div>


            <!-- Right: planner form & results -->
            <div class="section">
              <form method="post">
                <input type="hidden" name="calc_state" value='{{ calc_state_json }}'>

                <div style="margin-bottom:10px;">
                  <label for="planner_mp_id">Masterpiece</label>
                  <select id="planner_mp_id" name="planner_mp_id" onchange="this.form.submit();">
                    {% if planner_mp_options %}
                      {% for mp in planner_mp_options %}
                        <option value="{{ mp.id }}"
                          {% if planner_mp and mp.id == planner_mp.id %}selected{% endif %}>
                          MP {{ mp.id }} — {{ mp.name or mp.addressableLabel or mp.type }}
                        </option>
                      {% endfor %}
                    {% else %}
                      <option value="">(no general masterpieces found)</option>
                    {% endif %}
                  </select>
                </div>

                <h2 style="margin-top:0;">Build a donation bundle</h2>

                <p class="subtle">
                  Choose resources, set amounts, and we&apos;ll predict total
                  <strong>MP points</strong>, <strong>XP</strong>, and <strong>COIN cost</strong>
                  using the selected Masterpiece above.
                </p>

                <div class="two-col" style="gap:10px;">
                  <div>
                <label for="calc_token">Resource</label>
                <select id="calc_token" name="calc_token">
                  <option value="">-- Choose resource --</option>
                  {% for tok in planner_tokens %}
                    <option value="{{ tok }}">{{ tok }}</option>
                  {% endfor %}
                </select>

                  </div>
                  <div>
                    <label for="calc_amount">Quantity</label>
                    <input id="calc_amount" name="calc_amount" type="number" step="1" min="1" placeholder="Enter amount">
                  </div>
                </div>

                <div class="two-col" style="margin-top:10px; gap:8px;">
                  <button type="submit" name="calc_action" value="add">➕ Add resource</button>
                  <button type="submit" name="calc_action" value="clear">🗑️ Clear all</button>
                </div>

                <h3 style="margin-top:16px;">📋 Current bundle</h3>
                {% if calc_resources %}
                  <div class="scroll-x">
                    <table>
                      <tr>
                        <th>Token</th>
                        <th style="text-align:right;">Quantity</th>
                        <th style="text-align:right;">Points</th>
                        <th style="text-align:right;">XP</th>
                        <th style="text-align:right;">Battery</th>

                      </tr>
                    {% for row in calc_resources %}
                      <tr>
                        <td>{{ row.token }}</td>
                        <td style="text-align:right;">{{ row.amount }}</td>
                        <td style="text-align:right;">{{ row.points_str or "—" }}</td>
                        <td style="text-align:right;">{{ row.xp_str or "—" }}</td>
                        <td style="text-align:right;">{{ row.battery_str or "—" }}</td>
                      </tr>
                    {% endfor %}

                    </table>
                  </div>
                {% else %}
                  <p class="hint">Nothing in the bundle yet. Add a resource to get started.</p>
                {% endif %}

                <h3 style="margin-top:16px;">📊 Result vs tier ladder</h3>
                {% if calc_result %}
                  <div class="mp-stat-block">
                    <div>
                      <div class="mp-stat-label">Total points</div>
                      <div class="mp-stat-value">{{ calc_result.total_points_str }}</div>
                    </div>
                    <div>
                      <div class="mp-stat-label">Total XP</div>
                      <div class="mp-stat-value">{{ calc_result.total_xp_str }}</div>
                    </div>
                    <div>
                        <div class="mp-stat-label">Total battery</div>
                        <div class="mp-stat-value">{{ calc_result.total_power_str }}</div>
                     </div>
                     <div>
                        <div class="mp-stat-label">Tier reached</div>
                      <div class="mp-stat-value">
                        {% if calc_result.tier > 0 %}
                          Tier {{ calc_result.tier }}
                        {% else %}
                          Below Tier 1
                        {% endif %}
                      </div>
                    </div>
                  </div>

                  {% if calc_result.next_tier_index %}
                    <p style="margin-top:10px;" class="subtle">
                      Progress to <strong>Tier {{ calc_result.next_tier_index }}</strong>:<br>
                      {{ calc_result.progress_to_next_pct }}% — 
                      {{ calc_result.points_to_next_str }} more points needed.
                    </p>
                  {% else %}
                    <p style="margin-top:10px;" class="subtle">
                      You&apos;re at the <strong>maximum tier</strong> for this masterpiece with this bundle.
                    </p>
                  {% endif %}
                {% else %}
                  <p class="hint">
                    Add some resources and click <strong>➕ Add resource</strong> to see points, XP, and tier progress.
                  </p>
                {% endif %}
              </form>
            </div>
          </div>
        </div>

        <!-- 📈 Current MP leaderboard -->
        <div class="mp-section" data-mp-section="current" style="display:none;">
          <div class="section" style="margin-top:4px;">
            <h2>Live leaderboard – current Masterpiece</h2>
            {% if error %}
              <div class="error">{{ error }}</div>
            {% endif %}

            {% if current_mp %}
              <p class="subtle">
                MP {{ current_mp.id }} — {{ current_mp.name or current_mp.addressableLabel or current_mp.type }}<br>
                Showing top {{ current_mp_top50|length }} players (Top {{ top_n }}).
              </p>

              <form method="get" class="section" style="margin-bottom:8px; display:flex; align-items:center; gap:8px;">
                <input type="hidden" name="tab" value="current">
                <label for="top_n" class="subtle">Show:</label>
                <select id="top_n" name="top_n">
                  {% for n in top_n_options %}
                    <option value="{{ n }}" {% if n == top_n %}selected{% endif %}>Top {{ n }}</option>
                  {% endfor %}
                </select>
                <button type="submit">Apply</button>
                <span class="hint">Only the top 100 are supported.</span>
              </form>
              
              {% if highlight_query and current_gap %}
                <div class="mp-gap-card">
                  <div class="mp-gap-title">Your position on this masterpiece</div>
                  <div class="mp-gap-grid">
                    <div class="mp-gap-block">
                      <div class="mp-gap-label">Your rank &amp; points</div>
                    <div class="mp-gap-number">
                      #{{ current_gap.position }} · {{ "{:,.0f}".format(current_gap.points or 0) }}
                    </div>

                      <div class="mp-gap-sub">
                        Highlight: <code>{{ highlight_query }}</code>
                      </div>
                    </div>
          <div class="section" style="margin-top:14px;">
            <h3 style="margin-top:0;">Leaderboard rewards</h3>
            <p class="subtle">
              Placement rewards for this Masterpiece (from the <code>leaderboardRewards</code> API field).
            </p>

            {% if leaderboard_reward_rows %}
              <div class="scroll-x">
                <table>
                  <tr>
                    <th>Rank range</th>
                    <th>Rewards</th>
                  </tr>
                  {% for row in leaderboard_reward_rows %}
                    <tr>
                      <td>
                        {% if row.from_rank and row.to_rank and row.from_rank != row.to_rank %}
                          #{{ row.from_rank }} &ndash; #{{ row.to_rank }}
                        {% elif row.from_rank %}
                          #{{ row.from_rank }}
                        {% else %}
                          (unknown)
                        {% endif %}
                      </td>
                      <td>{{ row.rewards_text }}</td>
                    </tr>
                  {% endfor %}
                </table>
              </div>
            {% else %}
              <p class="hint">
                No leaderboard reward metadata found for this Masterpiece in the API.
              </p>
            {% endif %}
          </div>


                    {% if current_gap.gap_up is not none %}
                      <div class="mp-gap-block">
                        <div class="mp-gap-label">Points to pass above</div>
                    <div class="mp-gap-number">
                      {{ "{:,.0f}".format(current_gap.gap_up or 0) }}
                    </div>

                        <div class="mp-gap-sub">
                          To pass <strong>{{ current_gap.above_name }}</strong>
                          (#{{ current_gap.above_pos }})
                        </div>
                      </div>
                    {% else %}
                      <div class="mp-gap-block">
                        <div class="mp-gap-label">Points to pass above</div>
                        <div class="mp-gap-number">
                          —
                        </div>
                        <div class="mp-gap-sub">
                          You&apos;re currently at the top 👑
                        </div>
                      </div>
                    {% endif %}

                    {% if current_gap.gap_down is not none %}
                      <div class="mp-gap-block">
                        <div class="mp-gap-label">Lead over player behind</div>
                    <div class="mp-gap-number">
                      {{ "{:,.0f}".format(current_gap.gap_down or 0) }}
                    </div>

                        <div class="mp-gap-sub">
                          Ahead of <strong>{{ current_gap.below_name }}</strong>
                          (#{{ current_gap.below_pos }})
                        </div>
                      </div>
                    {% else %}
                      <div class="mp-gap-block">
                        <div class="mp-gap-label">Lead over player behind</div>
                        <div class="mp-gap-number">
                          —
                        </div>
                        <div class="mp-gap-sub">
                          No one is listed behind you
                        </div>
                      </div>
                    {% endif %}
                  </div>
                </div>
              {% endif %}


              {% if current_mp_top50 %}
                <div class="mp-table-wrap">
                  <table>
                    <tr>
                      <th>Pos</th>
                      <th>Player</th>
                      <th>Points</th>
                    </tr>
{% for row in current_mp_top50 %}
  {% set prof = row.profile or {} %}
  {% set name = prof.displayName or "" %}
  {% set uid = prof.uid or "" %}
  {% set is_me = highlight_query and (
    highlight_query|lower in name|lower
    or highlight_query|lower in uid|lower
  ) %}
  <tr class="{% if is_me %}mp-row-me{% endif %}">
    <td>{{ row.position }}</td>
    <td class="subtle">
      {% if name %}
        {{ name }}
      {% elif uid %}
        {{ uid }}
      {% else %}
        —
      {% endif %}
      {% if is_me %}
        <span class="me-pill">← you</span>
      {% endif %}
    </td>
    <td>{{ "{:,.0f}".format(row.masterpiecePoints or 0) }}</td>
  </tr>
{% endfor %}
    </table>
  </div>

              {% else %}
                <p class="hint">No leaderboard data yet for the current masterpiece.</p>
              {% endif %}
            {% else %}
              <p class="hint">No active masterpieces detected.</p>
            {% endif %}
          </div>
        </div>


        <!-- 📜 History & events browser -->
        <div class="mp-section" data-mp-section="history" style="display:none;">
          <div class="section" style="margin-top:4px;">
            <h2>History &amp; event browser</h2>
            <p class="subtle">
              Inspect the top <strong>{{ top_n }}</strong> positions for any general or event masterpiece.
            </p>

            {% if history_mp_options %}
              <form method="get" class="mp-selector-form" style="margin-bottom:12px;">
                <label for="mp_view_id">Choose a masterpiece</label>
                <select id="mp_view_id" name="mp_view_id" style="max-width:320px;">
                  {% for mp in history_mp_options %}
                    <option value="{{ mp.id }}"
                      {% if selected_mp and mp.id == selected_mp.id %}selected{% endif %}>
                      MP {{ mp.id }}
                      {% if mp.name or mp.addressableLabel or mp.type %}
                        — {{ mp.name or mp.addressableLabel or mp.type }}
                      {% endif %}
                      {% if current_mp and mp.id == current_mp.id %}(current){% endif %}
                    </option>
                  {% endfor %}
                </select>


                <label for="history_top_n" style="margin-left:8px;">Show:</label>
                <select id="history_top_n" name="top_n">
                  {% for n in top_n_options %}
                    <option value="{{ n }}" {% if n == top_n %}selected{% endif %}>Top {{ n }}</option>
                  {% endfor %}
                </select>

                <input type="hidden" name="tab" value="history">
                <button type="submit" style="margin-left:6px;">View leaderboard</button>
              </form>

              {% if selected_mp %}
                {% if selected_mp_top50 %}

                  {% if highlight_query and selected_gap %}
                    <div class="mp-gap-card">
                      <div class="mp-gap-title">Your position on this masterpiece</div>
                      <div class="mp-gap-grid">
                        <div class="mp-gap-block">
                          <div class="mp-gap-label">Your rank &amp; points</div>
                          <div class="mp-gap-number">
                              #{{ selected_gap.position }} · {{ "{:,.0f}".format(selected_gap.points or 0) }}
                          </div>

                          <div class="mp-gap-sub">
                            Highlight: <code>{{ highlight_query }}</code>
                          </div>
                        </div>

                        {% if selected_gap.gap_up is not none %}
                          <div class="mp-gap-block">
                            <div class="mp-gap-label">Points to pass above</div>
                            <div class="mp-gap-number">
                              {{ "{:,.0f}".format(selected_gap.gap_up or 0) }}
                            </div>

                            <div class="mp-gap-sub">
                              To pass <strong>{{ selected_gap.above_name }}</strong>
                              (#{{ selected_gap.above_pos }})
                            </div>
                          </div>
                        {% else %}
                          <div class="mp-gap-block">
                            <div class="mp-gap-label">Points to pass above</div>
                            <div class="mp-gap-number">
                              —
                            </div>
                            <div class="mp-gap-sub">
                              You&apos;re currently at the top 👑
                            </div>
                          </div>
                        {% endif %}

                        {% if selected_gap.gap_down is not none %}
                          <div class="mp-gap-block">
                            <div class="mp-gap-label">Lead over player behind</div>
                            <div class="mp-gap-number">
                              {{ "{:,.0f}".format(selected_gap.gap_down or 0) }}
                            </div>

                            <div class="mp-gap-sub">
                              Ahead of <strong>{{ selected_gap.below_name }}</strong>
                              (#{{ selected_gap.below_pos }})
                            </div>
                          </div>
                        {% else %}
                          <div class="mp-gap-block">
                            <div class="mp-gap-label">Lead over player behind</div>
                            <div class="mp-gap-number">
                              —
                            </div>
                            <div class="mp-gap-sub">
                              No one is listed behind you
                            </div>
                          </div>
                        {% endif %}
                      </div>
                    </div>
                  {% endif %}


                  <div class="mp-table-wrap">
                    <table>
                      <tr>
                        <th>Pos</th>
                        <th>Player</th>
                        <th>Points</th>
                      </tr>
                      {% for row in selected_mp_top50 %}
                        {% set prof = row.profile or {} %}
                        {% set name = prof.displayName or "" %}
                        {% set uid = prof.uid or "" %}
                        {% set is_me = highlight_query and (
                          highlight_query|lower in name|lower
                          or highlight_query|lower in uid|lower
                        ) %}
                        <tr class="{% if is_me %}mp-row-me{% endif %}">
                          <td>{{ row.position }}</td>
                          <td class="subtle">
                            {% if name %}
                              {{ name }}
                            {% elif uid %}
                              {{ uid }}
                            {% else %}
                              —
                            {% endif %}
                            {% if is_me %}
                              <span class="me-pill">← you</span>
                            {% endif %}
                          </td>
                          <td>{{ "{:,.0f}".format(row.masterpiecePoints or 0) }}</td>
                        </tr>
                      {% endfor %}
                    </table>
                  </div>
                {% else %}
                  <p class="hint">No leaderboard data for this masterpiece.</p>
                {% endif %}
              {% else %}
                <p class="hint">Select a masterpiece above to view its leaderboard.</p>
              {% endif %}
            {% else %}
              <p class="hint">No masterpieces available to browse.</p>
            {% endif %}
          </div>
        </div>


<script>
  (function() {
    const tabs = document.querySelectorAll('.mp-tab');
    const sections = document.querySelectorAll('.mp-section');

    function activate(name) {
      tabs.forEach(btn => {
        const t = btn.getAttribute('data-mp-tab');
        btn.classList.toggle('active', t === name);
      });
      sections.forEach(sec => {
        const s = sec.getAttribute('data-mp-section');
        if (s === name) {
          sec.style.display = 'block';
        } else {
          sec.style.display = 'none';
        }
      });
    }

    // Read "tab" from query string (so reloads keep the same sub-tab)
    const params = new URLSearchParams(window.location.search);
    let currentTab = params.get('tab') || 'planner';
    activate(currentTab);

    // When you click a tab, update URL (no reload) and state
    tabs.forEach(btn => {
      btn.addEventListener('click', function() {
        const t = this.getAttribute('data-mp-tab') || 'planner';
        currentTab = t;
        activate(t);
        const url = new URL(window.location.href);
        url.searchParams.set('tab', t);
        window.history.replaceState({}, '', url);
      });
    });

    // Auto-refresh the page every 30s when on the "current" tab
    const REFRESH_MS = 30000;
    setInterval(() => {
      if (currentTab !== 'current') return;
      const url = new URL(window.location.href);
      url.searchParams.set('tab', 'current');
      window.location.href = url.toString();
    }, REFRESH_MS);
  })();
</script>
    """

    # Render inner content with context
    inner = render_template_string(
        content,
        error=error,
        masterpieces_data=masterpieces_data,
        general_mps=general_mps,
        event_mps=event_mps,
        general_snapshot=general_snapshot,
        event_snapshot=event_snapshot,


        # current MP leaderboard
        current_mp=current_mp,
        current_mp_top50=current_mp_top50,
        current_gap=current_gap,

        # history / selected MP leaderboard
        selected_mp=selected_mp,
        selected_mp_top50=selected_mp_top50,
        selected_gap=selected_gap,

        # planner / donation bundle state
        planner_mp=planner_mp,
        planner_mp_options=planner_mp_options,
        planner_tokens=planner_tokens,
        calc_resources=calc_resources,
        calc_result=calc_result,
        calc_state_json=calc_state_json,

        # tier + ladder info
        tier_rows=tier_rows,
        reward_tier_rows=reward_tier_rows,
        leaderboard_reward_rows=leaderboard_reward_rows,

        # leaderboard size options
        top_n=top_n,
        top_n_options=TOP_N_OPTIONS,

        # MP selector for history tab + highlight
        history_mp_options=history_mp_options,
        highlight_query=highlight_query,
    )
    # Wrap in base template
    html = render_template_string(
        BASE_TEMPLATE,
        content=inner,
        active_page="masterpieces",
        has_uid=has_uid_flag(),
    )
    return html

def _build_reward_snapshot_for_mp(
    mp: Optional[Dict[str, Any]],
    rows: List[Dict[str, Any]],
    highlight_query: str,
) -> Optional[Dict[str, Any]]:
    """
    Build a 'your current reward' snapshot for a given masterpiece:
      - Uses leaderboard rows + highlight_query to find your position & points
      - Determines your completion tier (MP_TIER_THRESHOLDS)
      - Looks up the leaderboard reward bracket you fall into.
    Returns a dict or None if we can't find you.
    """
    highlight_query = (highlight_query or "").strip()
    if not (mp and rows and highlight_query):
        return None

    gap = compute_leaderboard_gap_for_highlight(rows, highlight_query)
    if not gap or not gap.get("position"):
        return None

    my_position = gap["position"]
    try:
        my_position_int = int(str(my_position).strip())
    except Exception:
        my_position_int = None

    my_points = gap.get("points")

    # Figure out completion tier
    tier_label, tier_min, tier_max = None, None, None
    if my_points is not None:
        try:
            pts = float(my_points)
        except Exception:
            pts = None

        if pts is not None:
            tier_index = 0
            # MP_TIER_THRESHOLDS is a simple list of ints
            for i, req in enumerate(MP_TIER_THRESHOLDS, start=1):
                if pts >= req:
                    tier_index = i
                else:
                    break

            if tier_index > 0:
                tier_label = f"Tier {tier_index}"
                tier_min = MP_TIER_THRESHOLDS[tier_index - 1]
                if tier_index < len(MP_TIER_THRESHOLDS):
                    # Next tier starts at the next threshold; treat max as one less
                    tier_max = MP_TIER_THRESHOLDS[tier_index] - 1
                else:
                    # Top tier: no upper bound
                    tier_max = None


    # Figure out reward bracket we fall into
    reward_bracket: Optional[Dict[str, Any]] = None
    if my_position_int is not None:
        # mp["leaderboardRewards"] is a list of brackets like:
        # { "minRank": 1, "maxRank": 1, "reward": { "experience": 500, ... } }
        for bracket in mp.get("leaderboardRewards", []) or []:
            min_rank = bracket.get("minRank")
            max_rank = bracket.get("maxRank")
            if min_rank is None or max_rank is None:
                continue
            try:
                # Treat these as inclusive rank ranges [minRank, maxRank]
                if min_rank <= my_position_int <= max_rank:
                    reward_bracket = bracket
                    break
            except TypeError:
                continue

    reward_label = None
    if reward_bracket:
        rr = reward_bracket.get("reward") or {}
        label_parts = []
        xp = rr.get("experience")
        if xp is not None:
            label_parts.append(f"{xp:,} XP")
        mp_tokens = rr.get("masterpiecePoints")
        if mp_tokens is not None:
            label_parts.append(f"{mp_tokens:,} MP")
        coins = rr.get("coins")
        if coins is not None:
            label_parts.append(f"{coins:,} coins")

        # Add 1-based rank range label
        min_rank = reward_bracket.get("minRank")
        max_rank = reward_bracket.get("maxRank")
        if min_rank is not None and max_rank is not None:
            if min_rank == max_rank:
                label_parts.append(f"(Rank {min_rank})")
            else:
                label_parts.append(f"(Ranks {min_rank}–{max_rank})")

        reward_label = " ".join(label_parts).strip()

    # Build a snapshot dict. Include both the newer descriptive keys
    # and some backward-compatibility aliases that the Jinja template expects.
    return {
        # raw masterpiece object (used for MP id / name in the template)
        "mp": mp,

        # core position / points
        "position": my_position,
        "points": my_points,

        # detailed tier info
        "tier_label": tier_label,
        "tier_min": tier_min,
        "tier_max": tier_max,

        # leaderboard reward bracket from API
        "reward_bracket": reward_bracket,
        "reward_label": reward_label,

        # --- compatibility aliases for the template ---
        # template expects .tier and .tier_required
        "tier": tier_label,
        "tier_required": tier_min,

        # template expects .leaderboard_rewards for human-readable text
        "leaderboard_rewards": reward_label,
    }










# -------- Snipe Calculator tab --------
@app.route("/snipe", methods=["GET", "POST"])
def snipe():
    error: Optional[str] = None

    # Three possible result blocks
    rank_result: Optional[Dict[str, Any]] = None
    target_result: Optional[Dict[str, Any]] = None
    combo_result: Optional[Dict[str, Any]] = None

    # Load all masterpieces once for dropdowns
    masterpieces_data: List[Dict[str, Any]] = []
    try:
        masterpieces_data = fetch_masterpieces()
    except Exception as e:
        error = f"Error fetching masterpieces: {e}"

    mp_choices = [
        {"id": mp["id"], "label": f"{mp['name']} (ID {mp['id']})"}
        for mp in masterpieces_data
    ]

    selected_mp_id: Optional[int] = None
    target_rank: int = 25
    my_points: float = 0.0
    target_points_input: float = 0.0
    combo_text: str = ""

    mode: str = "rank"

    if request.method == "POST":
        mode = (request.form.get("mode") or "rank").strip()

        # Shared masterpiece id parsing
        mp_id_str = (request.form.get("masterpiece_id") or "").strip()
        try:
            selected_mp_id = int(mp_id_str)
        except ValueError:
            selected_mp_id = None

        if mode == "rank":
            # Existing rank-based single-resource snipe
            target_str = (request.form.get("target_rank") or "").strip()
            my_points_str = (request.form.get("my_points") or "").strip()

            try:
                target_rank = int(target_str)
                if target_rank < 1:
                    target_rank = 1
            except ValueError:
                target_rank = 1

            try:
                my_points = float(my_points_str or "0")
            except ValueError:
                my_points = 0.0

            if not selected_mp_id:
                error = "Please select a valid masterpiece."
            else:
                try:
                    mp = fetch_masterpiece_details(selected_mp_id)
                    prices = fetch_live_prices_in_coin()

                    leaderboard = mp.get("leaderboard") or []
                    target_entry = None
                    for row in leaderboard:
                        if row.get("position") == target_rank:
                            target_entry = row
                            break

                    if not target_entry:
                        if leaderboard:
                            target_entry = leaderboard[-1]
                            target_rank = target_entry.get("position", target_rank)
                        else:
                            raise RuntimeError("No leaderboard data available for this masterpiece.")

                    target_points = float(target_entry.get("masterpiecePoints") or 0.0)
                    points_needed = max(0.0, target_points + 1.0 - my_points)

                    resources = mp.get("resources") or []
                    options: List[Dict[str, Any]] = []

                    for r in resources:
                        symbol = (r.get("symbol") or "").upper()
                        current_amt = float(r.get("amount") or 0.0)
                        target_amt = float(r.get("target") or 0.0)
                        remaining = max(0.0, target_amt - current_amt)
                        if remaining <= 0:
                            continue

                        pr = predict_reward(
                            selected_mp_id,
                            [{"symbol": symbol, "amount": 1}],
                        )
                        pts_per_unit = float(pr.get("masterpiecePoints") or 0.0)
                        battery_per_unit = float(pr.get("requiredPower") or 0.0)
                        price_coin = float(prices.get(symbol, 0.0))

                        if pts_per_unit <= 0 or price_coin <= 0:
                            continue

                        units_needed = math.ceil(points_needed / pts_per_unit) if points_needed > 0 else 0
                        if units_needed <= 0:
                            units_needed = 0

                        if units_needed > remaining:
                            max_points = remaining * pts_per_unit
                            enough = False
                        else:
                            max_points = units_needed * pts_per_unit
                            enough = True

                        coin_cost = units_needed * price_coin
                        battery_cost = units_needed * battery_per_unit

                        options.append({
                            "symbol": symbol,
                            "remaining": remaining,
                            "points_per_unit": pts_per_unit,
                            "battery_per_unit": battery_per_unit,
                            "price_coin": price_coin,
                            "units_needed": units_needed,
                            "coin_cost": coin_cost,
                            "battery_cost": battery_cost,
                            "enough": enough,
                            "max_points": max_points,
                        })

                    options.sort(key=lambda o: o["coin_cost"] if o["coin_cost"] > 0 else 1e18)

                    # ----- Cheapest multi-resource mix plan (greedy by COIN/point) -----
                    mix_plan: Optional[Dict[str, Any]] = None
                    if points_needed > 0 and options:
                        enriched = []
                        for o in options:
                            pts_per_unit = o["points_per_unit"]
                            price_coin = o["price_coin"]
                            remaining_units = o["remaining"]
                            if pts_per_unit <= 0 or price_coin <= 0 or remaining_units <= 0:
                                continue
                            coin_per_point = price_coin / pts_per_unit
                            max_points_res = remaining_units * pts_per_unit
                            e = dict(o)
                            e["coin_per_point"] = coin_per_point
                            e["max_points_res"] = max_points_res
                            enriched.append(e)

                        # cheapest COIN per point first
                        enriched.sort(key=lambda e: e["coin_per_point"])

                        remaining_pts = points_needed
                        chosen_rows: List[Dict[str, Any]] = []
                        total_coin = 0.0
                        total_battery = 0.0

                        for e in enriched:
                            if remaining_pts <= 0:
                                break

                            pts_from_this = min(remaining_pts, e["max_points_res"])
                            if pts_from_this <= 0:
                                continue

                            # convert points back to units, round up
                            units = math.ceil(pts_from_this / e["points_per_unit"])
                            if units > e["remaining"]:
                                units = int(e["remaining"])
                                pts_from_this = units * e["points_per_unit"]

                            if units <= 0:
                                continue

                            coin_cost = units * e["price_coin"]
                            battery_cost = units * e["battery_per_unit"]

                            total_coin += coin_cost
                            total_battery += battery_cost
                            remaining_pts -= pts_from_this

                            chosen_rows.append({
                                "symbol": e["symbol"],
                                "units": units,
                                "points": pts_from_this,
                                "coin_cost": coin_cost,
                                "battery_cost": battery_cost,
                                "coin_per_point": e["coin_per_point"],
                            })

                        if chosen_rows:
                            achieved_points = points_needed - max(0.0, remaining_pts)
                            mix_plan = {
                                "rows": chosen_rows,
                                "target_points": points_needed,
                                "achieved_points": achieved_points,
                                "enough": remaining_pts <= 0.0,
                                "total_coin": total_coin,
                                "total_battery": total_battery,
                            }

                    rank_result = {
                        "mp": mp,
                        "target_rank": target_rank,
                        "target_points": target_points,
                        "my_points": my_points,
                        "points_needed": points_needed,
                        "options": options,
                        "mix_plan": mix_plan,
                    }



                except Exception as e:
                    error = f"Error calculating rank snipe: {e}"

        elif mode == "target":
            # Target raw points -> single-resource options
            target_pts_str = (request.form.get("target_points") or "").strip()
            try:
                target_points_input = float(target_pts_str or "0")
            except ValueError:
                target_points_input = 0.0

            if not selected_mp_id:
                error = "Please select a valid masterpiece."
            else:
                try:
                    mp = fetch_masterpiece_details(selected_mp_id)
                    prices = fetch_live_prices_in_coin()

                    points_needed = max(0.0, target_points_input)

                    resources = mp.get("resources") or []
                    options: List[Dict[str, Any]] = []

                    for r in resources:
                        symbol = (r.get("symbol") or "").upper()
                        current_amt = float(r.get("amount") or 0.0)
                        target_amt = float(r.get("target") or 0.0)
                        remaining = max(0.0, target_amt - current_amt)
                        if remaining <= 0:
                            continue

                        pr = predict_reward(
                            selected_mp_id,
                            [{"symbol": symbol, "amount": 1}],
                        )
                        pts_per_unit = float(pr.get("masterpiecePoints") or 0.0)
                        battery_per_unit = float(pr.get("requiredPower") or 0.0)
                        price_coin = float(prices.get(symbol, 0.0))

                        if pts_per_unit <= 0 or price_coin <= 0:
                            continue

                        units_needed = math.ceil(points_needed / pts_per_unit) if points_needed > 0 else 0
                        if units_needed <= 0:
                            units_needed = 0

                        if units_needed > remaining:
                            max_points = remaining * pts_per_unit
                            enough = False
                        else:
                            max_points = units_needed * pts_per_unit
                            enough = True

                        coin_cost = units_needed * price_coin
                        battery_cost = units_needed * battery_per_unit

                        options.append({
                            "symbol": symbol,
                            "remaining": remaining,
                            "points_per_unit": pts_per_unit,
                            "battery_per_unit": battery_per_unit,
                            "price_coin": price_coin,
                            "units_needed": units_needed,
                            "coin_cost": coin_cost,
                            "battery_cost": battery_cost,
                            "enough": enough,
                            "max_points": max_points,
                        })

                    options.sort(key=lambda o: o["coin_cost"] if o["coin_cost"] > 0 else 1e18)

                    # ----- Cheapest multi-resource mix plan (greedy by COIN/point) -----
                    mix_plan: Optional[Dict[str, Any]] = None
                    if points_needed > 0 and options:
                        enriched = []
                        for o in options:
                            pts_per_unit = o["points_per_unit"]
                            price_coin = o["price_coin"]
                            remaining_units = o["remaining"]
                            if pts_per_unit <= 0 or price_coin <= 0 or remaining_units <= 0:
                                continue
                            coin_per_point = price_coin / pts_per_unit
                            max_points_res = remaining_units * pts_per_unit
                            e = dict(o)
                            e["coin_per_point"] = coin_per_point
                            e["max_points_res"] = max_points_res
                            enriched.append(e)

                        # cheapest COIN per point first
                        enriched.sort(key=lambda e: e["coin_per_point"])

                        remaining_pts = points_needed
                        chosen_rows: List[Dict[str, Any]] = []
                        total_coin = 0.0
                        total_battery = 0.0

                        for e in enriched:
                            if remaining_pts <= 0:
                                break

                            pts_from_this = min(remaining_pts, e["max_points_res"])
                            if pts_from_this <= 0:
                                continue

                            # convert points back to units, round up
                            units = math.ceil(pts_from_this / e["points_per_unit"])
                            if units > e["remaining"]:
                                units = int(e["remaining"])
                                pts_from_this = units * e["points_per_unit"]

                            if units <= 0:
                                continue

                            coin_cost = units * e["price_coin"]
                            battery_cost = units * e["battery_per_unit"]

                            total_coin += coin_cost
                            total_battery += battery_cost
                            remaining_pts -= pts_from_this

                            chosen_rows.append({
                                "symbol": e["symbol"],
                                "units": units,
                                "points": pts_from_this,
                                "coin_cost": coin_cost,
                                "battery_cost": battery_cost,
                                "coin_per_point": e["coin_per_point"],
                            })

                        if chosen_rows:
                            achieved_points = points_needed - max(0.0, remaining_pts)
                            mix_plan = {
                                "rows": chosen_rows,
                                "target_points": points_needed,
                                "achieved_points": achieved_points,
                                "enough": remaining_pts <= 0.0,
                                "total_coin": total_coin,
                                "total_battery": total_battery,
                            }

                    target_result = {
                        "mp": mp,
                        "target_points": points_needed,
                        "options": options,
                        "mix_plan": mix_plan,
                    }


                except Exception as e:
                    error = f"Error calculating target-points snipe: {e}"

        elif mode == "combo":
            combo_text = (request.form.get("combo_text") or "").strip()
            if not selected_mp_id:
                error = "Please select a valid masterpiece."
            elif not combo_text:
                error = "Enter at least one donation like: MUD=100000, GAS 42000, CEMENT:69"
            else:
                try:
                    # Parse text into list of {symbol, amount}
                    donations: List[Dict[str, Any]] = []
                    parts = [p.strip() for p in combo_text.replace("\n", ",").split(",") if p.strip()]
                    for part in parts:
                        # Accept formats like "MUD=100", "MUD 100", "MUD:100"
                        for sep in ["=", ":", " "]:
                            if sep in part:
                                sym, amt_str = part.split(sep, 1)
                                break
                        else:
                            # No separator found, skip
                            continue
                        sym = sym.strip().upper()
                        try:
                            amt = float(amt_str.strip())
                        except ValueError:
                            continue
                        if amt <= 0:
                            continue
                        donations.append({"symbol": sym, "amount": amt})

                    if not donations:
                        error = "No valid symbol/amount pairs found."
                    else:
                        mp = fetch_masterpiece_details(selected_mp_id)
                        prices = fetch_live_prices_in_coin()

                        pr = predict_reward(selected_mp_id, donations)
                        total_points = float(pr.get("masterpiecePoints") or 0.0)
                        total_battery = float(pr.get("requiredPower") or 0.0)

                        per_resource: List[Dict[str, Any]] = []
                        total_coin = 0.0
                        for d in donations:
                            sym = d["symbol"].upper()
                            amt = float(d["amount"] or 0.0)
                            price_coin = float(prices.get(sym, 0.0))
                            coin_cost = price_coin * amt
                            total_coin += coin_cost
                            per_resource.append({
                                "symbol": sym,
                                "amount": amt,
                                "price_coin": price_coin,
                                "coin_cost": coin_cost,
                            })

                        combo_result = {
                            "mp": mp,
                            "total_points": total_points,
                            "total_battery": total_battery,
                            "total_coin": total_coin,
                            "per_resource": per_resource,
                            "raw_text": combo_text,
                        }

                except Exception as e:
                    error = f"Error calculating combo donation: {e}"

    # Build HTML
    content = """
    <div class="card">
      <h1>Masterpiece Snipe &amp; Donation Tools</h1>
      <p class="subtle">
        Three tools: <strong>Rank snipe</strong>, <strong>Target points</strong>, and <strong>Combo donation</strong>.
        All use <code>predictReward</code> + live COIN prices.
      </p>

      {% if error %}
        <div class="error">{{ error }}</div>
      {% endif %}

      <!-- Rank-based single-resource snipe -->
      <div class="card" style="margin-top:10px;">
        <h2>1) Rank Snipe (single resource)</h2>
        <form method="post" style="margin-bottom:12px;">
          <input type="hidden" name="mode" value="rank" />
          <div style="display:flex;flex-wrap:wrap;gap:12px;align-items:flex-end;">
            <div style="flex:2;min-width:220px;">
              <label for="masterpiece_id">Masterpiece</label>
              <select id="masterpiece_id" name="masterpiece_id" style="width:100%;">
                <option value="">(choose masterpiece)</option>
                {% for mp in mp_choices %}
                  <option value="{{ mp.id }}" {% if selected_mp_id==mp.id %}selected{% endif %}>{{ mp.label }}</option>
                {% endfor %}
              </select>
            </div>
            <div style="flex:1;min-width:120px;">
              <label for="target_rank">Target rank</label>
              <input type="number" id="target_rank" name="target_rank" value="{{ target_rank }}" />
            </div>
            <div style="flex:1;min-width:160px;">
              <label for="my_points">Your current points</label>
              <input type="number" step="1" id="my_points" name="my_points" value="{{ my_points }}" />
            </div>
            <div style="flex:1;min-width:140px;display:flex;justify-content:flex-start;">
              <button type="submit">Calc rank snipe</button>
            </div>
          </div>
        </form>

        {% if rank_result %}
          <div class="card" style="margin-top:6px;">
            <h3>{{ rank_result.mp.name }} – snipe to rank {{ rank_result.target_rank }}</h3>
            <p class="subtle">
              Target points (rank {{ rank_result.target_rank }}): {{ "{:,.0f}".format(rank_result.target_points) }}<br>
              Your current points: {{ "{:,.0f}".format(rank_result.my_points) }}<br>
              <strong>Points needed to pass:</strong> {{ "{:,.0f}".format(rank_result.points_needed) }}
            </p>

            {% if rank_result.options %}
              <h4>Single-resource options (sorted by COIN cost)</h4>
              <div class="scroll-x">
                <table>
                  <tr>
                    <th>Resource</th>
                    <th>Points / unit</th>
                    <th>COIN / unit</th>
                    <th>Battery / unit</th>
                    <th>Remaining units</th>
                    <th>Units needed</th>
                    <th>Total COIN</th>
                    <th>Total battery</th>
                    <th>Enough?</th>
                  </tr>
                  {% for o in rank_result.options %}
                    <tr>
                      <td>{{ o.symbol }}</td>
                      <td>{{ "{:,.2f}".format(o.points_per_unit) }}</td>
                      <td>{{ "{:,.6f}".format(o.price_coin) }}</td>
                      <td>{{ "{:,.2f}".format(o.battery_per_unit) }}</td>
                      <td>{{ "{:,.0f}".format(o.remaining) }}</td>
                      <td>{{ "{:,.0f}".format(o.units_needed) }}</td>
                      <td><span class="pill">{{ "{:,.4f}".format(o.coin_cost) }}</span></td>
                      <td>{{ "{:,.2f}".format(o.battery_cost) }}</td>
                      <td>{{ '✅' if o.enough else '❌' }}</td>
                    </tr>
                  {% endfor %}
                </table>
              </div>
                            {% if rank_result.mix_plan %}
                <h4 style="margin-top:12px;">Cheapest mix (multi-resource)</h4>
                <p class="subtle">
                  Target points: {{ "{:,.0f}".format(rank_result.mix_plan.target_points) }}<br>
                  Achieved points: {{ "{:,.0f}".format(rank_result.mix_plan.achieved_points) }}<br>
                  Enough to pass? {{ '✅' if rank_result.mix_plan.enough else '❌' }}<br>
                  Total COIN: {{ "{:,.4f}".format(rank_result.mix_plan.total_coin) }}<br>
                  Total battery: {{ "{:,.2f}".format(rank_result.mix_plan.total_battery) }}
                </p>
                <div class="scroll-x">
                  <table>
                    <tr>
                      <th>Resource</th>
                      <th>Units to donate</th>
                      <th>Points from this</th>
                      <th>COIN / point</th>
                      <th>Total COIN</th>
                      <th>Total battery</th>
                    </tr>
                    {% for r in rank_result.mix_plan.rows %}
                      <tr>
                        <td>{{ r.symbol }}</td>
                        <td>{{ "{:,.0f}".format(r.units) }}</td>
                        <td>{{ "{:,.0f}".format(r.points) }}</td>
                        <td>{{ "{:,.8f}".format(r.coin_per_point) }}</td>
                        <td>{{ "{:,.4f}".format(r.coin_cost) }}</td>
                        <td>{{ "{:,.2f}".format(r.battery_cost) }}</td>
                      </tr>
                    {% endfor %}
                  </table>
                </div>
              {% endif %}
            {% else %}
              <p class="subtle">No usable resources found (no remaining room or no price data).</p>
            {% endif %}
          </div>
        {% endif %}
      </div>

      <!-- Target points single-resource helper -->
      <div class="card" style="margin-top:14px;">
        <h2>2) Target Points (single resource)</h2>
        <form method="post" style="margin-bottom:10px;">
          <input type="hidden" name="mode" value="target" />
          <div style="display:flex;flex-wrap:wrap;gap:12px;align-items:flex-end;">
            <div style="flex:2;min-width:220px;">
              <label for="masterpiece_id_t">Masterpiece</label>
              <select id="masterpiece_id_t" name="masterpiece_id" style="width:100%;">
                <option value="">(choose masterpiece)</option>
                {% for mp in mp_choices %}
                  <option value="{{ mp.id }}" {% if selected_mp_id==mp.id %}selected{% endif %}>{{ mp.label }}</option>
                {% endfor %}
              </select>
            </div>
            <div style="flex:1;min-width:180px;">
              <label for="target_points">Target points</label>
              <input type="number" step="1" id="target_points" name="target_points" value="{{ '%.0f'|format(target_points_input) }}" />
            </div>
            <div style="flex:1;min-width:140px;display:flex;justify-content:flex-start;">
              <button type="submit">Calc from points</button>
            </div>
          </div>
        </form>

        {% if target_result %}
          <div class="card" style="margin-top:6px;">
            <h3>{{ target_result.mp.name }} – {{ "{:,.0f}".format(target_result.target_points) }} points</h3>
            {% if target_result.options %}
              <div class="scroll-x">
                <table>
                  <tr>
                    <th>Resource</th>
                    <th>Points / unit</th>
                    <th>COIN / unit</th>
                    <th>Battery / unit</th>
                    <th>Remaining units</th>
                    <th>Units needed</th>
                    <th>Total COIN</th>
                    <th>Total battery</th>
                    <th>Enough?</th>
                  </tr>
                  {% for o in target_result.options %}
                    <tr>
                      <td>{{ o.symbol }}</td>
                      <td>{{ "{:,.2f}".format(o.points_per_unit) }}</td>
                      <td>{{ "{:,.6f}".format(o.price_coin) }}</td>
                      <td>{{ "{:,.2f}".format(o.battery_per_unit) }}</td>
                      <td>{{ "{:,.0f}".format(o.remaining) }}</td>
                      <td>{{ "{:,.0f}".format(o.units_needed) }}</td>
                      <td><span class="pill">{{ "{:,.4f}".format(o.coin_cost) }}</span></td>
                      <td>{{ "{:,.2f}".format(o.battery_cost) }}</td>
                      <td>{{ '✅' if o.enough else '❌' }}</td>
                    </tr>
                  {% endfor %}
                </table>
              </div>
                            {% if target_result.mix_plan %}
                <h4 style="margin-top:12px;">Cheapest mix (multi-resource)</h4>
                <p class="subtle">
                  Target points: {{ "{:,.0f}".format(target_result.mix_plan.target_points) }}<br>
                  Achieved points: {{ "{:,.0f}".format(target_result.mix_plan.achieved_points) }}<br>
                  Enough to reach target? {{ '✅' if target_result.mix_plan.enough else '❌' }}<br>
                  Total COIN: {{ "{:,.4f}".format(target_result.mix_plan.total_coin) }}<br>
                  Total battery: {{ "{:,.2f}".format(target_result.mix_plan.total_battery) }}
                </p>
                <div class="scroll-x">
                  <table>
                    <tr>
                      <th>Resource</th>
                      <th>Units to donate</th>
                      <th>Points from this</th>
                      <th>COIN / point</th>
                      <th>Total COIN</th>
                      <th>Total battery</th>
                    </tr>
                    {% for r in target_result.mix_plan.rows %}
                      <tr>
                        <td>{{ r.symbol }}</td>
                        <td>{{ "{:,.0f}".format(r.units) }}</td>
                        <td>{{ "{:,.0f}".format(r.points) }}</td>
                        <td>{{ "{:,.8f}".format(r.coin_per_point) }}</td>
                        <td>{{ "{:,.4f}".format(r.coin_cost) }}</td>
                        <td>{{ "{:,.2f}".format(r.battery_cost) }}</td>
                      </tr>
                    {% endfor %}
                  </table>
                </div>
              {% endif %}

            {% else %}
              <p class="subtle">No usable resources found for that target.</p>
            {% endif %}
          </div>
        {% endif %}
      </div>

      <!-- Combo donation calculator -->
      <div class="card" style="margin-top:14px;">
        <h2>3) Combo Donation (multi-resource)</h2>
        <p class="subtle">Enter donations like <code>MUD=100000, GAS 42000, CEMENT:69</code> and we&apos;ll show total points, COIN, and battery.</p>
        <form method="post" style="margin-bottom:10px;">
          <input type="hidden" name="mode" value="combo" />
          <div style="display:flex;flex-wrap:wrap;gap:12px;align-items:flex-end;">
            <div style="flex:2;min-width:220px;">
              <label for="masterpiece_id_c">Masterpiece</label>
              <select id="masterpiece_id_c" name="masterpiece_id" style="width:100%;">
                <option value="">(choose masterpiece)</option>
                {% for mp in mp_choices %}
                  <option value="{{ mp.id }}" {% if selected_mp_id==mp.id %}selected{% endif %}>{{ mp.label }}</option>
                {% endfor %}
              </select>
            </div>
          </div>
          <div style="margin-top:8px;">
            <label for="combo_text">Donations</label>
            <textarea id="combo_text" name="combo_text" rows="3" style="width:100%;" placeholder="MUD=100000, GAS 42000, CEMENT:69">{{ combo_text }}</textarea>
          </div>
          <div style="margin-top:8px;">
            <button type="submit">Calc combo</button>
          </div>
        </form>

        {% if combo_result %}
          <div class="card" style="margin-top:6px;">
            <h3>{{ combo_result.mp.name }} – Combo result</h3>
            <p class="subtle">
              Total points: {{ "{:,.0f}".format(combo_result.total_points) }}<br>
              Total battery (power): {{ "{:,.2f}".format(combo_result.total_battery) }}<br>
              Total COIN: {{ "{:,.4f}".format(combo_result.total_coin) }}
            </p>
            {% if combo_result.per_resource %}
              <div class="scroll-x">
                <table>
                  <tr>
                    <th>Resource</th>
                    <th>Amount</th>
                    <th>COIN / unit</th>
                    <th>Total COIN</th>
                  </tr>
                  {% for r in combo_result.per_resource %}
                    <tr>
                      <td>{{ r.symbol }}</td>
                      <td>{{ "{:,.0f}".format(r.amount) }}</td>
                      <td>{{ "{:,.6f}".format(r.price_coin) }}</td>
                      <td>{{ "{:,.4f}".format(r.coin_cost) }}</td>
                    </tr>
                  {% endfor %}
                </table>
              </div>
            {% endif %}
          </div>
        {% endif %}
      </div>
    </div>
    """

    content = render_template_string(
        content,
        error=error,
        rank_result=rank_result,
        target_result=target_result,
        combo_result=combo_result,
        mp_choices=mp_choices,
        selected_mp_id=selected_mp_id,
        target_rank=target_rank,
        my_points=my_points,
        target_points_input=target_points_input,
        combo_text=combo_text,
    )

    html = render_template_string(
        BASE_TEMPLATE,
        content=content,
        active_page="snipe",
        has_uid=has_uid_flag(),
    )
    return html


# -------- Calculate tab (CSV-based) --------
@app.route("/calculate", methods=["GET", "POST"])
def calculate():
    error: Optional[str] = None
    calc_result = None
    best_rows: Optional[List[Any]] = None
    combined_speed: Optional[float] = None
    worker_factor: Optional[float] = None

    factories = FACTORIES_FROM_CSV or {}

    # Use your global display order: MUD, CLAY, SAND, ... DYNAMITE
    all_tokens = list(factories.keys())
    tokens: List[str] = [t for t in FACTORY_DISPLAY_ORDER if t in factories]
    for tok in sorted(all_tokens):
        if tok not in tokens:
            tokens.append(tok)

    selected_token = tokens[0] if tokens else ""
    selected_level = None
    target_level = None
    count = 1
    yield_pct = 100.0
    speed_factor = 1.0
    workers = 0
    action = "calculate"

    if request.method == "POST":
        action = request.form.get("action", "calculate")
        selected_token = request.form.get("factory", selected_token).strip().upper()
        count_str = request.form.get("count", "1").strip() or "1"
        yield_str = request.form.get("yield_pct", "100").strip() or "100"
        speed_str = request.form.get("speed_factor", "1.0").strip() or "1.0"
        workers_str = request.form.get("workers", "0").strip() or "0"
        level_str = request.form.get("level", "").strip()
        target_str = request.form.get("target_level", "").strip()

        try:
            count = max(int(count_str), 1)
        except ValueError:
            count = 1
        try:
            yield_pct = float(yield_str)
        except ValueError:
            yield_pct = 100.0
        try:
            speed_factor = float(speed_str)
        except ValueError:
            speed_factor = 1.0
        try:
            workers = max(0, min(int(workers_str), 4))
        except ValueError:
            workers = 0

        selected_level = None
        target_level = None

        if level_str:
            try:
                selected_level = int(level_str)
            except Exception:
                selected_level = None

        if target_str:
            try:
                target_level = int(target_str)
            except Exception:
                target_level = None

        try:
            prices = fetch_live_prices_in_coin()
            if not prices:
                raise RuntimeError("No prices returned from fetch_live_prices_in_coin().")

            if action == "calculate":
                if not selected_level:
                    lvl_keys = sorted(factories.get(selected_token, {}).keys())
                    selected_level = lvl_keys[-1] if lvl_keys else None

                if not selected_level:
                    raise RuntimeError(f"No recipe levels found for {selected_token}.")

                calc_result = compute_factory_result_csv(
                    factories,
                    prices,
                    selected_token,
                    selected_level,
                    target_level=target_level,
                    count=count,
                    yield_pct=yield_pct,
                    speed_factor=speed_factor,
                    workers=workers,
                )

            elif action == "best":
                best_rows, combined_speed, worker_factor = compute_best_setups_csv(
                    factories,
                    prices,
                    speed_factor=speed_factor,
                    workers=workers,
                    yield_pct=yield_pct,
                    top_n=10,
                )
            else:
                error = "Unknown action."
        except Exception as e:
            error = f"Error calculating: {e}"

    # Levels for currently selected token
    levels_for_selected = (
        sorted(factories.get(selected_token, {}).keys())
        if selected_token in factories
        else []
    )

    if selected_level is None and levels_for_selected:
        selected_level = levels_for_selected[-1]

    target_levels = levels_for_selected

    factory_levels = {tok: sorted(levels.keys()) for tok, levels in factories.items()}
    factory_levels_json = json.dumps(factory_levels)

    content = """
    <div class="card">
      <h1>Factory Calculator (CSV)</h1>
      <p class="subtle">
        Uses your <code>Game Data - Factories - rev. v_01 .csv</code> plus live prices in <strong>COIN</strong>
        (from <code>exchangePriceList</code>) to estimate per-factory profit and upgrade costs.
      </p>

      <form method="post" style="margin-bottom: 16px;">
        <div style="display:flex;flex-wrap:wrap;gap:12px;">
          <div style="flex:1;min-width:150px;">
            <label for="factory">Factory token</label>
            <select id="factory" name="factory" style="width:100%;">
              {% for tok in tokens %}
                <option value="{{ tok }}" {% if tok == selected_token %}selected{% endif %}>{{ tok }}</option>
              {% endfor %}
            </select>
          </div>

          <div style="flex:1;min-width:120px;">
            <label for="level">Level</label>
            <select id="level" name="level" style="width:100%;">
              <option value="">(auto)</option>
              {% for lvl in levels_for_selected %}
                <option value="{{ lvl }}" {% if selected_level == lvl %}selected{% endif %}>L{{ lvl }}</option>
              {% endfor %}
            </select>
          </div>

          <div style="flex:1;min-width:140px;">
            <label for="target_level">Target level (optional)</label>
            <select id="target_level" name="target_level" style="width:100%;">
              <option value="">(none)</option>
              {% for lvl in target_levels %}
                <option value="{{ lvl }}" {% if target_level == lvl %}selected{% endif %}>L{{ lvl }}</option>
              {% endfor %}
            </select>
          </div>

          <div style="flex:1;min-width:120px;">
            <label for="count"># of factories</label>
            <input id="count" name="count" type="number" min="1" value="{{ count }}" style="width:100%;">
          </div>

          <div style="flex:1;min-width:140px;">
            <label for="yield_pct">Yield / Mastery (%)</label>
            <input id="yield_pct" name="yield_pct" type="number" step="0.1" value="{{ yield_pct }}" style="width:100%;">
          </div>

          <div style="flex:1;min-width:140px;">
            <label for="speed_factor">Speed (1x or 2x)</label>
            <input id="speed_factor" name="speed_factor" type="number" step="0.5" value="{{ speed_factor }}" style="width:100%;">
          </div>

          <div style="flex:1;min-width:140px;">
            <label for="workers">Workers (0-4)</label>
            <input id="workers" name="workers" type="number" min="0" max="4" value="{{ workers }}" style="width:100%;">
          </div>
        </div>

        <div style="margin-top:12px; display:flex; gap:8px; flex-wrap:wrap;">
          <button type="submit" name="action" value="calculate">Calculate this setup</button>
          <button type="submit" name="action" value="best">Show top setups (1 factory each)</button>
        </div>
      </form>

      {% if error %}
        <div class="error">{{ error }}</div>
      {% endif %}

      {% if calc_result %}
        <div class="card" style="margin-top:8px;">
          <h2>
            Result for {{ calc_result.token }} L{{ calc_result.level }}
            {% if calc_result.target_level %} → L{{ calc_result.target_level }}{% endif %}
          </h2>
          <p class="subtle">
            # factories: {{ calc_result.count }}<br>
            Yield/Mastery: {{ calc_result.yield_pct }}%<br>
            Speed factor: {{ calc_result.speed_factor }}x<br>
            Workers: {{ calc_result.workers }}
          </p>

          <h3>Production</h3>
          <p>
            Duration (base): {{ "%.2f"|format(calc_result.duration_min) }} min<br>
            Effective duration (speed & workers): {{ "%.2f"|format(calc_result.effective_duration) }} min<br>
            Crafts/hour (single factory): {{ "%.4f"|format(calc_result.crafts_per_hour) }}
          </p>

          <h3>Outputs (per craft)</h3>
          <p>
            {{ "%.4f"|format(calc_result.out_amount) }} {{ calc_result.out_token }}<br>
            Value: {{ "%.6f"|format(calc_result.value_coin_per_craft) }} COIN / craft
          </p>

          <h3>Inputs (per craft – adjusted for {{ calc_result.yield_pct }}% yield)</h3>
          {% if calc_result.inputs %}
            <table>
              <tr>
                <th>Token</th>
                <th>Amount</th>
                <th>Value (COIN)</th>
              </tr>
              {% for tok, qty in calc_result.inputs.items() %}
                <tr>
                  <td>{{ tok }}</td>
                  <td>{{ "%.6f"|format(qty) }}</td>
                  <td>
                    {% set val = calc_result.inputs_value_coin[tok] %}
                    {{ "%.6f"|format(val) }}
                  </td>
                </tr>
              {% endfor %}
            </table>
          {% else %}
            <p class="subtle">No inputs found for this recipe.</p>
          {% endif %}

          <h3>Profit</h3>
          <p>
            Cost / craft: {{ "%.6f"|format(calc_result.cost_coin_per_craft) }} COIN<br>
            Value / craft: {{ "%.6f"|format(calc_result.value_coin_per_craft) }} COIN<br>
            <br>
            Profit / craft: {{ "%+.6f"|format(calc_result.profit_coin_per_craft) }} COIN<br>
            Profit / hour ({{ calc_result.count }} factory/factories):
            {{ "%+.6f"|format(calc_result.profit_coin_per_hour) }} COIN
          </p>

          <h3>Upgrade costs</h3>
          {% if calc_result.upgrade_single %}
            <p>
              <strong>Next level (single step):</strong><br>
              {{ calc_result.upgrade_single.amount_per_factory }} {{ calc_result.upgrade_single.token }} per factory<br>
              Cost per factory: {{ "%.6f"|format(calc_result.upgrade_single.coin_per_factory) }} COIN<br>
              Cost for {{ calc_result.count }} factory/factories:
              {{ "%.6f"|format(calc_result.upgrade_single.coin_total) }} COIN
            </p>
          {% else %}
            <p class="subtle">No single-step upgrade cost found.</p>
          {% endif %}

          {% if calc_result.upgrade_chain %}
            <p>
              <strong>Full chain {{ calc_result.level }} → {{ calc_result.target_level }}:</strong>
            </p>
            <table>
              <tr>
                <th>Token</th>
                <th>Amount per factory</th>
                <th>COIN / factory</th>
                <th>COIN (all factories)</th>
              </tr>
              {% for step in calc_result.upgrade_chain %}
                <tr>
                  <td>{{ step.token }}</td>
                  <td>{{ "%.6f"|format(step.amount_per_factory) }}</td>
                  <td>{{ "%.6f"|format(step.coin_per_factory) }}</td>
                  <td>{{ "%.6f"|format(step.coin_total) }}</td>
                </tr>
              {% endfor %}
            </table>
          {% endif %}
        </div>
      {% endif %}

      {% if best_rows %}
        <div class="card" style="margin-top:8px;">
          <h2>Top {{ best_rows|length }} setups (1 factory each)</h2>
          {% if combined_speed %}
            <p class="subtle">
              Combined speed: {{ "%.2f"|format(combined_speed) }}x
            </p>
          {% endif %}
          <table>
            <tr>
              <th>Factory</th>
              <th>Level</th>
              <th>Profit / hour (COIN)</th>
              <th>Profit / craft (COIN)</th>
            </tr>
            {% for r in best_rows %}
              {% set good = r.profit_coin_per_hour >= 0 %}
              <tr>
                <td>{{ r.token }}</td>
                <td>L{{ r.level }}</td>
                <td>
                  <span class="{{ 'pill' if good else 'pill-bad' }}">
                    {{ "%+.6f"|format(r.profit_coin_per_hour) }}
                  </span>
                </td>
                <td>{{ "%+.6f"|format(r.profit_coin_per_craft) }}</td>
              </tr>
            {% endfor %}
          </table>
        </div>
      {% endif %}

      <script>
        (function() {
          const factoryLevels = {{ factory_levels_json | safe }};
          const factorySelect = document.getElementById("factory");
          const levelSelect = document.getElementById("level");
          const targetSelect = document.getElementById("target_level");

          function rebuildLevelOptions(token) {
            const levels = factoryLevels[token] || [];
            const currentLevel = levelSelect.value;
            const currentTarget = targetSelect.value;

            levelSelect.innerHTML = "";
            const optAuto = document.createElement("option");
            optAuto.value = "";
            optAuto.textContent = "(auto)";
            levelSelect.appendChild(optAuto);

            targetSelect.innerHTML = "";
            const optNone = document.createElement("option");
            optNone.value = "";
            optNone.textContent = "(none)";
            targetSelect.appendChild(optNone);

            levels.forEach((lvl) => {
              const v = String(lvl);

              const opt = document.createElement("option");
              opt.value = v;
              opt.textContent = "L" + v;
              if (v === currentLevel) {
                opt.selected = true;
              }
              levelSelect.appendChild(opt);

              const opt2 = document.createElement("option");
              opt2.value = v;
              opt2.textContent = "L" + v;
              if (v === currentTarget) {
                opt2.selected = true;
              }
              targetSelect.appendChild(opt2);
            });
          }

          if (factorySelect && levelSelect && targetSelect) {
            factorySelect.addEventListener("change", function() {
              rebuildLevelOptions(this.value);
            });

            rebuildLevelOptions(factorySelect.value);
          }
        })();
      </script>
    </div>
    """

    content = render_template_string(
        content,
        tokens=tokens,
        selected_token=selected_token,
        levels_for_selected=levels_for_selected,
        target_levels=target_levels,
        count=count,
        yield_pct=yield_pct,
        speed_factor=speed_factor,
        workers=workers,
        calc_result=calc_result,
        best_rows=best_rows,
        combined_speed=combined_speed,
        worker_factor=worker_factor,
        error=error,
        factory_levels_json=factory_levels_json,
    )

    html = render_template_string(
        BASE_TEMPLATE,
        content=content,
        active_page="calculate",
        has_uid=has_uid_flag(),
    )
    return html


if __name__ == "__main__":
    app.run(debug=True)

































































