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
    fetch_proficiencies,
    fetch_workshop_levels,
    fetch_profile_by_uid,
    fetch_available_avatars,
)


def normalize_avatar_url(raw: Optional[str]) -> Optional[str]:
    """
    Normalize Craft World avatar URLs so the browser can display them.

    - If it's already http(s), return as-is.
    - If it's ipfs://CID/path, convert to https://ipfs.io/ipfs/CID/path
    """
    if not raw:
        return None
    url = raw.strip()
    if not url:
        return None

    if url.startswith("ipfs://"):
        cid_path = url[len("ipfs://"):]
        return f"https://ipfs.io/ipfs/{cid_path}"

    # already a normal URL like https://craft-world.gg/avatars/...
    return url


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



from pricing import (
    fetch_live_prices_in_coin,
    fetch_buy_sell_for_profitability,
    TOKEN_ADDRESSES,
)


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
    Get the current Account ID (Craft World UID) for this session.
    Used so each account has its own boost settings.
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

@app.context_processor
def inject_nav_user():
    """
    Provide `nav_profile` and `nav_avatar_url` to all templates.
    Uses profileByUID, which does not require the authenticated account scope.
    """
    uid = session.get("voya_uid")
    prof = None
    avatar_url = None

    if uid:
        try:
            prof = fetch_profile_by_uid(uid)
            raw = (prof.get("avatarUrl") or "").strip()
            if raw:
                avatar_url = normalize_avatar_url(raw)
        except Exception as e:
            print("[inject_nav_user] profile error:", e, flush=True)
            prof = None
            avatar_url = None

    print("[inject_nav_user] nav_avatar_url:", avatar_url, flush=True)

    return {
        "nav_profile": prof,
        "nav_avatar_url": avatar_url,
    }





# -------- Helper: do we have a UID stored? --------
def has_uid_flag() -> bool:
    return bool(session.get("voya_uid"))


# -------- Base HTML template (dark neon UI) --------
BASE_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>CraftWorld Tools.Live</title>
  <!-- Make it mobile friendly -->
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    :root {
      --bg-main: #050712;
      --bg-elevated: rgba(17, 22, 46, 0.70);
      --bg-elevated-soft: rgba(17, 22, 46, 0.60);
      --bg-chip: rgba(26, 34, 72, 0.70);
      --accent: #5cf2ff;
      --accent-soft: rgba(92, 242, 255, 0.16);
      --accent-strong: #ff7af2;
      --text-main: #f6f7ff;
      --text-soft: #9ea4d1;
      --danger: #ff5c7a;
      --success: #4ade80;
      --border-subtle: rgba(255, 255, 255, 0.03);
      --border-strong: rgba(92, 242, 255, 0.35);
      --shadow-soft: 0 18px 40px rgba(0, 0, 0, 0.55);
      --shadow-subtle: 0 10px 30px rgba(0, 0, 0, 0.40);
      --radius-lg: 18px;
      --radius-pill: 999px;
      --nav-height: 60px;
    }

    * {
      box-sizing: border-box;
    }

body {
  margin: 0;
  font-family: system-ui, -apple-system, BlinkMacSystemFont, "SF Pro Text",
               "Segoe UI", sans-serif;

  background-image: url('/static/backgrounds/lab_desktop.png');
  background-size: cover;
  background-position: center;
  background-repeat: no-repeat;
  background-attachment: fixed;

  background-color: #050712;
  background-blend-mode: normal;

  color: var(--text-main);
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

@media (max-width: 768px) {
  body {
    background-image: url('/static/backgrounds/lab_mobile.png');
    background-attachment: scroll;
    background-position: center top;
  }
}


    a {
      color: var(--accent);
      text-decoration: none;
    }

    a:hover {
      text-decoration: underline;
    }

    /* Top navigation */
    .nav {
      position: sticky;
      top: 0;
      z-index: 20;
      backdrop-filter: blur(16px);
      background: rgba(5, 7, 18, 0.95);
      border-bottom: 1px solid rgba(15, 23, 42, 0.9);
      box-shadow: 0 8px 18px rgba(0, 0, 0, 0.5);
    }


    .nav-inner {
      max-width: 1180px;
      margin: 0 auto;
      padding: 10px 16px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 14px;
    }

    .nav-title {
      font-weight: 700;
      letter-spacing: 0.04em;
      font-size: 18px;
      display: flex;
      align-items: center;
      gap: 8px;
      color: var(--text-main);
    }

    .nav-title span.logo-dot {
      display: inline-block;
      width: 9px;
      height: 9px;
      border-radius: 50%;
      background: radial-gradient(circle at 30% 30%, #fff, var(--accent));
      box-shadow: 0 0 14px var(--accent);
    }

    .nav-links {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      align-items: center;
      justify-content: flex-end;
      font-size: 14px;
    }

    .nav-links a,
    .nav-links span.nav-disabled {
      padding: 6px 12px;
      border-radius: var(--radius-pill);
      border: 1px solid transparent;
      background: transparent;
      color: var(--text-soft);
      display: inline-flex;
      align-items: center;
      gap: 6px;
      transition: all 0.14s ease-out;
      cursor: pointer;
    }

    .nav-links a:hover {
      border-color: var(--border-strong);
      background: radial-gradient(circle at top left, var(--accent-soft), transparent 60%);
      color: var(--text-main);
      text-decoration: none;
    }

    .nav-links a.active {
      background: rgba(37, 99, 235, 0.95);
      color: #e5e7eb;
      border-color: rgba(191, 219, 254, 0.55);
      box-shadow: 0 0 0 1px rgba(59, 130, 246, 0.7);
      font-weight: 600;
    }


    .nav-disabled {
      opacity: 0.45;
      cursor: default;
      border-color: rgba(255, 255, 255, 0.05) !important;
      background: rgba(15, 23, 42, 0.9) !important;
    }

.nav-user {
  padding-left: 8px;
  font-size: 13px;
  color: var(--text-soft);
  display: inline-flex;
  align-items: center;
  gap: 10px;
}

.mp-avatar {
  width: 66px;  
  height: 66px; 
  border-radius: 999px;
  overflow: hidden;
  border: 1px solid rgba(148, 163, 184, 0.75);
  box-shadow: 0 0 12px rgba(15, 23, 42, 0.9);
  flex-shrink: 0;
  background: radial-gradient(circle at 30% 30%, #020617, #1e293b);
  display: inline-flex;
  align-items: center;
  justify-content: center;
}


.mp-avatar img {
  width: 100%;
  height: 100%;
  display: block;
  object-fit: cover;
}

.mp-avatar-fallback {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: #e5e7eb;
}



    /* Main page layout */
    .page {
      flex: 1;
      padding: 18px 12px 40px;
    }

    .page-inner {
      max-width: 1180px;
      margin: 0 auto;
    }

.card {
  background: rgba(15, 23, 42, 0.60);  /* ~40% see-through */
  border-radius: var(--radius-lg);
  padding: 18px 18px 16px;
  border: 1px solid rgba(148, 163, 184, 0.25);
  box-shadow: 0 12px 28px rgba(0, 0, 0, 0.65);
  margin-bottom: 18px;
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
}


    h1, h2, h3 {
      margin: 0 0 6px;
      font-weight: 650;
      letter-spacing: 0.02em;
      color: var(--text-main);
    }

    h1 {
      font-size: 22px;
    }

    h2 {
      font-size: 18px;
    }

    h3 {
      font-size: 15px;
      color: #e5e7ff;
    }

    p {
      margin: 4px 0 8px;
      line-height: 1.4;
    }

    .subtle {
      color: var(--text-soft);
      font-size: 13px;
    }

    .two-col {
      display: grid;
      grid-template-columns: minmax(0, 1.1fr) minmax(0, 1fr);
      gap: 14px;
      margin-top: 6px;
    }

    @media (max-width: 900px) {
      .two-col {
        grid-template-columns: minmax(0, 1fr);
      }
    }

    /* Forms / inputs */
    label {
      display: block;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--text-soft);
      margin-bottom: 4px;
    }

    input[type="text"],
    input[type="number"],
    input[type="password"],
    select,
    textarea {
      width: 100%;
      padding: 7px 9px;
      border-radius: 10px;
      border: 1px solid rgba(148, 163, 184, 0.35);
      background: rgba(15, 23, 42, 0.88);
      color: var(--text-main);
      font-size: 13px;
      outline: none;
      transition: border-color 0.16s ease, box-shadow 0.16s ease, background 0.16s;
    }

    input::placeholder,
    textarea::placeholder {
      color: rgba(148, 163, 184, 0.65);
    }

    input:focus,
    select:focus,
    textarea:focus {
      border-color: var(--border-strong);
      box-shadow: 0 0 0 1px rgba(92, 242, 255, 0.5);
      background: rgba(15, 23, 42, 0.98);
    }

    textarea {
      resize: vertical;
      min-height: 90px;
    }

    .hint {
      font-size: 11px;
      color: var(--text-soft);
      margin-top: 2px;
    }

    button {
      border-radius: var(--radius-pill);
      border: 1px solid transparent;
      padding: 7px 16px;
      font-size: 13px;
      font-weight: 600;
      letter-spacing: 0.03em;
      text-transform: uppercase;
      cursor: pointer;
      background: linear-gradient(120deg, var(--accent), var(--accent-strong));
      color: #020617;
      box-shadow: 0 10px 26px rgba(92, 242, 255, 0.55);
      transition: transform 0.12s ease-out, box-shadow 0.12s ease-out,
                  filter 0.12s ease-out, background 0.18s ease-out;
      margin-top: 4px;
    }

    button:hover {
      transform: translateY(-1px);
      filter: brightness(1.04);
      box-shadow: 0 16px 38px rgba(92, 242, 255, 0.65);
    }

    button:active {
      transform: translateY(0);
      box-shadow: 0 12px 26px rgba(92, 242, 255, 0.45);
    }

    /* Tables */
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
  margin-top: 6px;
  border-radius: 12px;
  overflow: hidden;
  background: rgba(15, 23, 42, 0.50);  /* translucent */
  border: 1px solid rgba(51, 65, 85, 0.7);
  box-shadow: 0 10px 24px rgba(0, 0, 0, 0.6);
}

tr:nth-child(even) td {
  background: rgba(15, 23, 42, 0.45);
}

tr:nth-child(odd) td {
  background: rgba(15, 23, 42, 0.40);
}


    tr:nth-child(even) td {
      background: rgba(15, 23, 42, 0.94);
    }

    tr:nth-child(odd) td {
      background: rgba(15, 23, 42, 0.90);
    }

    tr:hover td {
      background: rgba(30, 64, 175, 0.40);
    }


    .pill,
    .pill-bad {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      padding: 2px 8px;
      border-radius: var(--radius-pill);
      font-size: 11px;
      font-weight: 600;
    }

    .pill {
      background: rgba(16, 185, 129, 0.18);
      color: var(--success);
      border: 1px solid rgba(16, 185, 129, 0.5);
      box-shadow: 0 0 12px rgba(16, 185, 129, 0.45);
    }

    .pill-bad {
      background: rgba(248, 113, 113, 0.14);
      color: var(--danger);
      border: 1px solid rgba(248, 113, 113, 0.5);
      box-shadow: 0 0 12px rgba(248, 113, 113, 0.35);
    }

    .error {
      margin-top: 8px;
      padding: 7px 10px;
      border-radius: 10px;
      border: 1px solid rgba(248, 113, 113, 0.75);
      background: rgba(127, 29, 29, 0.55);
      color: #fee2e2;
      font-size: 12px;
    }

    .success {
      margin-top: 8px;
      padding: 7px 10px;
      border-radius: 10px;
      border: 1px solid rgba(34, 197, 94, 0.8);
      background: rgba(22, 101, 52, 0.65);
      color: #dcfce7;
      font-size: 12px;
    }

    .badge-chip {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 3px 8px;
      border-radius: var(--radius-pill);
      background: var(--bg-chip);
      border: 1px solid rgba(148, 163, 184, 0.35);
      font-size: 11px;
      color: var(--text-soft);
    }

    .badge-dot {
      width: 7px;
      height: 7px;
      border-radius: 999px;
      background: radial-gradient(circle at 30% 30%, #fff, var(--accent));
      box-shadow: 0 0 8px rgba(92, 242, 255, 0.9);
    }

    /* Flex-specific tweaks (just use existing classes) */
    .flex-meta-row {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 8px;
      font-size: 12px;
    }

    .flex-meta-row > div {
      padding: 5px 10px;
      border-radius: 999px;
      background: rgba(15, 23, 42, 0.96);
      border: 1px solid rgba(75, 85, 99, 0.9);
    }


    .flex-layout-title {
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .flex-layout-title span.emoji {
      font-size: 18px;
    }

    /* --- Donate popup styles --- */
    .donate-toast {
      position: fixed;
      bottom: 16px;
      right: 16px;
      z-index: 9999;
      max-width: 360px;
      background: radial-gradient(circle at top left, rgba(92,242,255,0.18), transparent 55%),
                  rgba(15, 23, 42, 0.98);
      border-radius: 16px;
      border: 1px solid rgba(92, 242, 255, 0.35);
      box-shadow: 0 18px 40px rgba(0, 0, 0, 0.75);
      padding: 10px 12px;
      display: none; /* hidden until JS shows it after 30s */
      flex-direction: column;
      gap: 6px;
      font-size: 12px;
      color: var(--text-soft);
    }

    .donate-toast-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
    }

    .donate-toast-title {
      display: flex;
      align-items: center;
      gap: 6px;
      font-weight: 600;
      color: var(--text-main);
      font-size: 13px;
    }

    .donate-toast-title span.icon {
      font-size: 16px;
    }

    .donate-toast-body {
      display: flex;
      flex-direction: column;
      gap: 4px;
    }

    .donate-toast-code {
      font-family: monospace;
      font-size: 11px;
      padding: 4px 6px;
      border-radius: 10px;
      background: rgba(15,23,42,0.95);
      border: 1px solid rgba(148,163,184,0.45);
      word-break: break-all;
    }

    .donate-toast-actions {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 8px;
      margin-top: 2px;
      flex-wrap: wrap;
    }

    .donate-toast-small {
      font-size: 11px;
      opacity: 0.9;
    }

    .donate-toast button.donate-copy-btn {
      border-radius: var(--radius-pill);
      border: 1px solid transparent;
      padding: 5px 10px;
      font-size: 11px;
      font-weight: 600;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      cursor: pointer;
      background: linear-gradient(120deg, var(--accent), var(--accent-strong));
      color: #020617;
      box-shadow: 0 10px 26px rgba(92, 242, 255, 0.55);
      transition: transform 0.12s ease-out, box-shadow 0.12s ease-out, filter 0.12s ease-out;
      white-space: nowrap;
    }

    .donate-toast button.donate-copy-btn:hover {
      transform: translateY(-1px);
      filter: brightness(1.04);
      box-shadow: 0 16px 38px rgba(92, 242, 255, 0.65);
    }

    .donate-toast button.donate-close-btn {
      border: none;
      background: transparent;
      color: var(--text-soft);
      cursor: pointer;
      font-size: 14px;
      padding: 0 4px;
      line-height: 1;
    }
  </style>

</head>
<body>
  <div class="nav">
    <div class="nav-inner">
      <div class="nav-title">
        <span class="logo-dot"></span>
        CraftWorld Tools.Live
      </div>

      <div class="nav-links">
        <a href="{{ url_for('index') }}" class="{{ 'active' if active_page=='overview' else '' }}">Overview</a>

        {% if has_uid %}
          <a href="{{ url_for('dashboard') }}" class="{{ 'active' if active_page=='dashboard' else '' }}">Dashboard</a>
          <a href="{{ url_for('inventory_view') }}" class="{{ 'active' if active_page=='inventory' else '' }}">Inventory</a>
        {% else %}
          <span class="nav-disabled">Dashboard</span>
          <span class="nav-disabled">Inventory</span>
        {% endif %}

        {% if has_uid %}
          <a href="{{ url_for('profitability') }}" class="{{ 'active' if active_page=='profit' else '' }}">Profitability</a>
          <a href="{{ url_for('flex_planner') }}" class="{{ 'active' if active_page=='flex' else '' }}">Flex Planner</a>
        {% else %}
          <span class="nav-disabled">Profitability</span>
          <span class="nav-disabled">Flex Planner</span>
        {% endif %}

        <a href="{{ url_for('boosts') }}" class="{{ 'active' if active_page=='boosts' else '' }}">Boosts</a>
        <a href="{{ url_for('mastery_view') }}" class="{{ 'active' if active_page=='mastery' else '' }}">Mastery</a>
        <a href="{{ url_for('masterpieces_view') }}" class="{{ 'active' if active_page=='masterpieces' else '' }}">Masterpieces</a>
        <a href="{{ url_for('snipe') }}" class="{{ 'active' if active_page=='snipe' else '' }}">Snipe</a>
        <a href="{{ url_for('charts') }}" class="{{ 'active' if active_page=='charts' else '' }}">Charts</a>
        <a href="{{ url_for('calculate') }}" class="{{ 'active' if active_page=='calculate' else '' }}">Calculate</a>
        <a href="{{ url_for('charts') }}" class="{{ 'active' if active_page=='charts' else '' }}">Charts</a>


        
        {% if session.get('username') %}
          {% set uname = session['username'] %}
          {% if nav_profile and nav_profile.displayName %}
            {% set label = nav_profile.displayName %}
          {% else %}
            {% set label = uname %}
          {% endif %}
          {% set initial = (label or '?')[:1] %}

          <span class="nav-user">
            <span class="mp-avatar">
              {% if nav_avatar_url %}
                <img src="{{ nav_avatar_url }}" alt="Avatar for {{ label }}">
              {% else %}
                <span class="mp-avatar-fallback">
                  {{ initial|upper }}
                </span>
              {% endif %}
            </span>
            <span class="nav-username">{{ label }}</span>
          </span>
          <a href="{{ url_for('logout') }}">Logout</a>
        {% else %}
          <a href="{{ url_for('login') }}" class="{{ 'active' if active_page=='login' else '' }}">Login</a>
        {% endif %}
      </div>
    </div>
  </div>



  <!-- Donate popup for server support -->
  <div id="donate-toast" class="donate-toast">
    <div class="donate-toast-header">
      <div class="donate-toast-title">
        <span class="icon">💾</span>
        <span>Help keep the server online</span>
      </div>
      <button class="donate-close-btn" id="donate-close-btn" title="Hide">
        ✕
      </button>
    </div>
    <div class="donate-toast-body">
      <div class="donate-toast-small">
        If this app helps you with Craft World and you want to chip in for hosting:
      </div>
      <div class="donate-toast-code">
        0xeED0491B506C78EA7fD10988B1E98A3C88e1C630
      </div>
    </div>
    <div class="donate-toast-actions">
      <div class="donate-toast-small">
        Ronin / EVM-compatible wallet – any support is appreciated. 🦖
      </div>
      <button type="button" class="donate-copy-btn" id="donate-copy-btn">
        Copy address
      </button>
    </div>
  </div>

  <div class="container">
    {{ content|safe }}
  </div>

  <script>
    (function () {
      const WALLET_ADDR = '0xeED0491B506C78EA7fD10988B1E98A3C88e1C630';

      window.addEventListener('DOMContentLoaded', function () {
        const toast = document.getElementById('donate-toast');
        const closeBtn = document.getElementById('donate-close-btn');
        const copyBtn = document.getElementById('donate-copy-btn');

        if (!toast) return;

        // Wait 30 seconds before showing
        setTimeout(function () {
          toast.style.display = 'flex'; // appears at bottom of every page
        }, 30000); // 30,000 ms = 30 sec

        if (closeBtn) {
          closeBtn.addEventListener('click', function () {
            toast.style.display = 'none';
          });
        }

        if (copyBtn) {
          copyBtn.addEventListener('click', function () {
            if (navigator.clipboard && navigator.clipboard.writeText) {
              navigator.clipboard.writeText(WALLET_ADDR).then(function () {
                const original = copyBtn.textContent;
                copyBtn.textContent = 'Copied!';
                setTimeout(function () {
                  copyBtn.textContent = original;
                }, 1500);
              }).catch(function () {
                alert('Wallet address: ' + WALLET_ADDR);
              });
            } else {
              alert('Wallet address: ' + WALLET_ADDR);
            }
          });
        }
      });
    })();
  </script>
    <footer class="site-footer">
    <div class="footer-inner">
      <a href="{{ url_for('terms') }}">Terms of Service</a>
      &nbsp;•&nbsp;
      <a href="{{ url_for('privacy') }}">Privacy Policy</a>
    </div>
  </footer>

  <style>
    .site-footer {
      margin-top: 40px;
      padding: 14px 0;
      text-align: center;
      font-size: 12px;
      color: rgba(226, 232, 240, 0.55);
    }
    .site-footer a {
      color: rgba(226, 232, 240, 0.85);
      text-decoration: none;
    }
    .site-footer a:hover {
      text-decoration: underline;
    }
  </style>

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
        uid = (request.form.get("uid") or "").strip()
        if not uid:
            error = "Please enter your Account ID."
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
        Enter your <strong>Account ID</strong> and this page will fetch your land plots, factories,
        mines, dynos and resources from Craft World.
      </p>
      <form method="post">
        <label for="uid">Account ID</label>
        <input type="text" id="uid" name="uid" value="{{ uid }}" placeholder="e.g. GfUeRBCZv8OwuUKq7Tu9JVpA70l1">
        <button type="submit">Fetch Craft World</button>
      </form>

      {% if error %}
        <div class="error">{{ error }}</div>
      {% endif %}
    </div>

    {% if result %}
      <div class="card">
        <h2>Next steps</h2>
        <p class="subtle">
          Your Account ID is set and your account data is loaded. Where do you want to go next?
        </p>
        <div style="display:flex; flex-wrap:wrap; gap:8px;">
          <a href="{{ url_for('dashboard') }}" class="pill">📊 Dashboard</a>
          <a href="{{ url_for('inventory_view') }}" class="pill">📦 Inventory</a>
          <a href="{{ url_for('profitability') }}" class="pill">🏭 Profitability</a>
          <a href="{{ url_for('flex_planner') }}" class="pill">🧠 Flex Planner</a>
          <a href="{{ url_for('masterpieces_view') }}" class="pill">🎨 Masterpieces</a>
        </div>
      </div>

      <div class="two-col">
        <div class="card">
          <h2>Land Plots &amp; Factories</h2>
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
            <p class="subtle">No land plots found for this account.</p>
          {% endif %}
        </div>

        <div class="card">
          <h2>Resources</h2>
          {% if result.resources %}
            <table>
              <tr><th>Token</th><th>Amount</th></tr>
              {% for r in result.resources %}
                <tr>
                  <td>{{ r.symbol }}</td>
                  <td>{{ "%.6f"|format(r.amount) }}</td>
                </tr>
              {% endfor %}
            </table>
          {% else %}
            <p class="subtle">No resources found for this account.</p>
          {% endif %}
        </div>
      </div>
    {% endif %}
    """

    html = render_template_string(
        BASE_TEMPLATE,
        content=render_template_string(
            content,
            uid=uid,
            result=result,
            error=error,
        ),
        active_page="overview",
        has_uid=has_uid_flag(),
    )
    return html

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
        to your account, independent of which <strong>Account ID</strong> you're looking at.
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
        follow you, even while you swap <strong>Account IDs</strong> to spy on other accounts.
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

@app.route("/terms")
def terms():
    content = """
    <div class="card">
      <h1>Terms of Service</h1>
      <p><strong>Last Updated: December 2025</strong></p>

      <h2>1. Who We Are</h2>
      <p>
        This service is operated by <strong>CraftWorld Tools Live</strong> ("we", "us", or "our").
        These Terms of Service ("Terms") govern your access to and use of the website and tools
        provided at craftworld-tools-live.onrender.com and any related URLs (collectively, the "Service").
      </p>
      <p>Email for contact: <a href="mailto:crypto23b@gmail.com">crypto23b@gmail.com</a>.</p>
      <p style="font-size:12px; opacity:0.8;">
        This document is provided for informational purposes only and is not legal advice.
        For specific legal concerns, you should consult a licensed attorney.
      </p>

      <h2>2. Acceptance of Terms</h2>
      <p>
        By accessing or using the Service, you agree to be bound by these Terms.
        If you do not agree to these Terms, you must not access or use the Service.
      </p>

      <h2>3. Relationship to Craft World and Third Parties</h2>
      <p>
        The Service is an <strong>unofficial, third-party companion tool</strong> built for players of Craft World.
        We are <strong>not affiliated with</strong> Craft World, VOYA Games, Angry Dynomites Lab, or any other
        company that owns or operates the Craft World game or related intellectual property.
      </p>
      <p>
        Any references to "Craft World", in-game items, tokens, or NFTs are for descriptive purposes only.
        All trademarks, logos, and assets remain the property of their respective owners and do not imply
        sponsorship, endorsement, or official status.
      </p>

      <h2>4. Eligibility</h2>
      <p>
        You may use the Service only if:
      </p>
      <ul>
        <li>You are at least 13 years old; and</li>
        <li>You have the legal capacity to enter into these Terms under the laws of your jurisdiction.</li>
      </ul>

      <h2>5. Nature of the Service</h2>
      <p>
        The Service provides calculators, planners, dashboards, and other utilities intended to help players
        understand in-game economics, resources, factories, and leaderboard outcomes. All outputs
        are estimates or interpretations based on:
      </p>
      <ul>
        <li>Publicly available or authorized APIs,</li>
        <li>Static reference data, and</li>
        <li>Values you choose to input (such as your Account ID or resource amounts).</li>
      </ul>
      <p>
        The Service does <strong>not</strong> control the Craft World game, its servers, or its economy.
        Final results in-game may differ from anything shown on this site.
      </p>

      <h2>6. No Financial, Investment, or Tax Advice</h2>
      <p>
        Nothing on the Service constitutes financial, investment, legal, or tax advice. Any values,
        profitability estimates, or projections related to COIN, resources, NFTs, or other digital assets
        are purely informational and may be inaccurate, incomplete, or outdated.
      </p>
      <p>
        You are solely responsible for your own decisions regarding gameplay, purchases, trades,
        investments, and any other actions involving digital assets.
      </p>

      <h2>7. Crypto, Blockchain, and Game-Risk Disclaimer</h2>
      <p>
        Digital assets such as tokens, coins, and NFTs are volatile and risky. By using this Service,
        you acknowledge and agree that:
      </p>
      <ul>
        <li>You may lose some or all of the value of your digital assets.</li>
        <li>Smart contracts, games, or third-party platforms may contain bugs, exploits, or downtime.</li>
        <li>Regulatory changes may affect your ability to use or access certain tokens or services.</li>
        <li>We have no control over the underlying blockchain networks or game servers.</li>
      </ul>
      <p>
        You use all crypto and blockchain-related features at your own risk.
      </p>

      <h2>8. Wallets, Keys, and Security</h2>
      <p>
        The Service will <strong>never</strong> ask you for your seed phrase, private keys,
        or wallet passwords. If anyone claiming to represent this Service asks for this information,
        do not provide it.
      </p>
      <p>
        You are solely responsible for:
      </p>
      <ul>
        <li>Maintaining the security of your wallets and private keys, and</li>
        <li>Reviewing and understanding any transactions you sign in your own wallet software.</li>
      </ul>
      <p>
        We are not responsible for any loss of funds or assets resulting from your wallet usage.
      </p>

      <h2>9. User Accounts on This Service</h2>
      <p>
        The Service offers an optional login system where you can create a local account with a username
        and password so your Mastery and Workshop boosts are saved across sessions.
      </p>
      <p>
        When you create an account:
      </p>
      <ul>
        <li>You agree to provide accurate and non-misleading information.</li>
        <li>You are responsible for keeping your password confidential.</li>
        <li>You are responsible for all activity occurring under your account.</li>
      </ul>
      <p>
        We reserve the right to terminate or suspend any account at our discretion, including for:
        suspected abuse, attempts to attack the Service, or violation of these Terms.
      </p>

      <h2>10. License and Permitted Use</h2>
      <p>
        We grant you a limited, revocable, non-exclusive, non-transferable license to access and use the
        Service for personal, non-commercial purposes in accordance with these Terms.
      </p>

      <h2>11. Prohibited Uses</h2>
      <p>You agree not to:</p>
      <ul>
        <li>Use the Service in any way that violates applicable law or the Craft World game’s own terms.</li>
        <li>Automate scraping or harvesting of data from the Service at a volume that impacts performance.</li>
        <li>Reverse engineer, decompile, or attempt to extract the source code where not provided.</li>
        <li>Attempt to bypass, disable, or interfere with security or rate limiting mechanisms.</li>
        <li>Use the Service to build or train competing tools without our permission.</li>
        <li>Upload, transmit, or link to malicious code, phishing content, or spam.</li>
      </ul>

      <h2>12. User Content and Feedback</h2>
      <p>
        If you share feedback, suggestions, or bug reports (for example via Discord or other channels),
        you grant us a non-exclusive, worldwide, royalty-free license to use, modify, and incorporate
        that feedback into the Service without obligation to you.
      </p>

      <h2>13. Third-Party Services and Links</h2>
      <p>
        The Service may rely on or link to third-party services (for example Craft World APIs, blockchain
        explorers, IPFS gateways, hosting providers, or other companion tools). We do not control these
        services and are not responsible for:
      </p>
      <ul>
        <li>Availability or uptime of those services,</li>
        <li>Accuracy of data they provide, or</li>
        <li>Any damage or loss arising from your use of those services.</li>
      </ul>

      <h2>14. No Guarantee of Accuracy</h2>
      <p>
        While we try to keep data reasonably up-to-date, all values, prices, rewards, and projections are
        provided on an <strong>"as-is" and "as-available"</strong> basis. Game mechanics, balance, and
        token prices can change without notice.
      </p>
      <p>
        You should always verify important information in-game or from official sources.
      </p>

      <h2>15. Suspension and Changes to the Service</h2>
      <p>
        We may modify, suspend, or discontinue all or part of the Service at any time, with or without
        notice, including for maintenance, technical issues, abuse, or business reasons. We are not
        liable for any loss or inconvenience caused by such changes.
      </p>

      <h2>16. Indemnification</h2>
      <p>
        To the fullest extent permitted by law, you agree to indemnify, defend, and hold harmless
        CraftWorld Tools Live and its operators from and against any claims, damages, losses, liabilities,
        costs, and expenses (including reasonable attorneys’ fees) arising out of or related to:
      </p>
      <ul>
        <li>Your use or misuse of the Service;</li>
        <li>Your violation of these Terms; or</li>
        <li>Your violation of any rights of another person or entity.</li>
      </ul>

      <h2>17. Disclaimer of Warranties</h2>
      <p>
        The Service is provided on an <strong>"as-is" and "as-available"</strong> basis, without any
        warranties of any kind, express or implied, including but not limited to warranties of
        merchantability, fitness for a particular purpose, and non-infringement.
      </p>
      <p>
        We do not warrant that the Service will be uninterrupted, secure, error-free, or that bugs
        will be corrected.
      </p>

      <h2>18. Limitation of Liability</h2>
      <p>
        To the maximum extent permitted by law, in no event shall CraftWorld Tools Live or its operators
        be liable for any indirect, incidental, consequential, special, exemplary, or punitive damages,
        or any loss of profits, revenues, data, or goodwill, arising out of or related to your use
        of the Service.
      </p>
      <p>
        If we are found liable in connection with the Service, our total aggregate liability shall not
        exceed <strong>USD $50</strong>.
      </p>

      <h2>19. Governing Law and Venue</h2>
      <p>
        These Terms are governed by the laws of the State of Washington, USA, without regard to its
        conflict of laws rules. Any dispute arising from or relating to these Terms or the Service
        shall be brought exclusively in the state or federal courts located in Washington State,
        and you consent to the jurisdiction of those courts.
      </p>

      <h2>20. Changes to These Terms</h2>
      <p>
        We may update these Terms from time to time. When we do, we will update the "Last Updated" date
        at the top of this page. Your continued use of the Service after changes are posted constitutes
        your acceptance of the updated Terms.
      </p>

      <h2>21. Contact</h2>
      <p>
        If you have questions about these Terms, you can reach us at:
        <a href="mailto:crypto23b@gmail.com">crypto23b@gmail.com</a>.
      </p>
    </div>
    """

    return render_template_string(
        BASE_TEMPLATE,
        content=content,
        active_page=None,
        has_uid=has_uid_flag(),
    )


@app.route("/privacy")
def privacy():
    content = """
    <div class="card">
      <h1>Privacy Policy</h1>
      <p><strong>Last Updated: December 2025</strong></p>

      <h2>1. Overview</h2>
      <p>
        This Privacy Policy explains how CraftWorld Tools Live ("we", "us", "our") collects, uses,
        and protects information when you use the Service. We aim to collect as little data as
        reasonably necessary to run the site.
      </p>
      <p>
        This policy is informational and does not constitute legal advice.
      </p>

      <h2>2. Data Controller and Contact</h2>
      <p>
        The Service is operated by CraftWorld Tools Live.
      </p>
      <p>
        Contact email: <a href="mailto:crypto23b@gmail.com">crypto23b@gmail.com</a>.
      </p>

      <h2>3. Information We Collect</h2>

      <h3>3.1. Optional Account Data</h3>
      <p>
        If you create an account on this site, we may store:
      </p>
      <ul>
        <li>Username (as entered by you);</li>
        <li>Password hash (your password is stored in hashed form, not plaintext);</li>
        <li>Settings for Mastery and Workshop boosts and any presets you save.</li>
      </ul>

      <h3>3.2. Game-Related Identifiers</h3>
      <p>
        To show calculators and dashboards, the Service may use identifiers you provide, such as
        your Craft World <strong>Account ID</strong>. This is used to query public or authorized
        game APIs and to show relevant data back to you.
      </p>
      <p>
        We do not collect your Craft World password, private keys, or any sensitive login credentials.
      </p>

      <h3>3.3. Technical and Usage Data</h3>
      <p>
        When you access the Service, we may automatically receive:
      </p>
      <ul>
        <li>IP address and basic device or browser information;</li>
        <li>Request URLs, timestamps, and error logs;</li>
        <li>Simple usage metrics (for example which pages are accessed most often).</li>
      </ul>
      <p>
        This data is used to operate, secure, and improve the Service (for example to debug failures
        or prevent abuse).
      </p>

      <h3>3.4. Cookies and Local Storage</h3>
      <p>
        The Service may use:
      </p>
      <ul>
        <li>A session cookie to keep you logged in while you browse;</li>
        <li>Local storage or cookies to remember basic UI preferences (for example dismissing a popup).</li>
      </ul>
      <p>
        We do <strong>not</strong> use third-party advertising or cross-site tracking cookies.
      </p>

      <h2>4. What We Do NOT Collect</h2>
      <p>We do <strong>not</strong> intentionally collect:</p>
      <ul>
        <li>Seed phrases or private keys;</li>
        <li>Wallet passwords or full payment card numbers;</li>
        <li>Government-issued ID numbers;</li>
        <li>Sensitive medical or financial records.</li>
      </ul>
      <p>
        If any such data is ever sent to us accidentally (for example via a bug report), you should
        notify us so it can be removed.
      </p>

      <h2>5. How We Use the Information</h2>
      <p>
        We use the information we collect for the following purposes:
      </p>
      <ul>
        <li>To operate and maintain the Service;</li>
        <li>To save your optional account settings (boosts, presets, etc.);</li>
        <li>To debug errors and improve performance;</li>
        <li>To protect the Service from abuse, spam, and attacks;</li>
        <li>To respond to user inquiries or support requests.</li>
      </ul>
      <p>
        We do <strong>not</strong> sell your personal data or use it for targeted advertising.
      </p>

      <h2>6. Legal Bases (Where Applicable)</h2>
      <p>
        Depending on your location, our processing of your data may be based on:
      </p>
      <ul>
        <li>The necessity to provide the Service you request;</li>
        <li>Our legitimate interest in maintaining and securing the Service; and</li>
        <li>Your consent, where explicitly requested (for example, creating an account).</li>
      </ul>

      <h2>7. Data Sharing and Third Parties</h2>
      <p>
        We may share data with third parties only in limited circumstances:
      </p>
      <ul>
        <li>
          <strong>Service providers</strong> (for example cloud hosting, logging, or analytics)
          who help us operate the Service. These providers are only given the minimum data needed.
        </li>
        <li>
          <strong>Legal obligations</strong>, if we are required by law or a valid legal request
          to disclose certain information.
        </li>
        <li>
          <strong>Security or harm prevention</strong>, if necessary to detect, prevent, or address
          fraud, abuse, or security issues.
        </li>
      </ul>
      <p>
        We do not share your information with advertisers or data brokers.
      </p>

      <h2>8. International Data Transfers</h2>
      <p>
        The Service may be hosted in data centers located in the United States or other countries.
        By using the Service, you understand that your information may be processed in countries
        that may have different data protection laws than your home jurisdiction.
      </p>

      <h2>9. Data Retention</h2>
      <p>
        We keep information only for as long as necessary to operate the Service or as required
        by law. For example:
      </p>
      <ul>
        <li>
          Account data (username, password hash, boosts) is retained while your account is active.
        </li>
        <li>
          Basic logs may be kept for a limited period to help us diagnose issues and maintain security.
        </li>
      </ul>
      <p>
        If you would like your account deleted, you can contact us and we will make reasonable
        efforts to remove associated account records, subject to technical and legal constraints.
      </p>

      <h2>10. Security</h2>
      <p>
        We take reasonable technical and organizational measures to protect the information we hold,
        including:
      </p>
      <ul>
        <li>Storing passwords only in hashed form;</li>
        <li>Using HTTPS to encrypt traffic where possible;</li>
        <li>Limiting administrative access to those who need it.</li>
      </ul>
      <p>
        However, no method of transmission or storage is 100% secure, and we cannot guarantee
        absolute security.
      </p>

      <h2>11. Your Choices and Rights</h2>
      <p>
        Depending on your location, you may have certain rights regarding your data, such as the
        right to access, correct, or request deletion of certain information.
      </p>
      <p>
        Practically, you can:
      </p>
      <ul>
        <li>Choose not to create an account (you can use parts of the Service without logging in);</li>
        <li>Request account deletion by contacting us at the email below;</li>
        <li>Clear your browser cookies and local storage to remove local identifiers.</li>
      </ul>

      <h2>12. Children’s Privacy</h2>
      <p>
        The Service is not directed to children under 13, and we do not knowingly collect personal
        information from children under 13. If you believe a child has provided us with personal
        information, please contact us so we can remove it.
      </p>

      <h2>13. Third-Party Links</h2>
      <p>
        The Service may link to third-party websites or tools (for example, Craft World, IPFS
        gateways, or blockchain explorers). We are not responsible for the privacy practices or
        content of those third-party sites. You should review their privacy policies separately.
      </p>

      <h2>14. Changes to This Privacy Policy</h2>
      <p>
        We may update this Privacy Policy from time to time. When we do, we will update the
        "Last Updated" date at the top of this page. Your continued use of the Service after
        changes are posted constitutes your acceptance of the updated policy.
      </p>

      <h2>15. Contact</h2>
      <p>
        If you have any questions about this Privacy Policy, or wish to request deletion or access
        to your data, you can contact:
      </p>
      <p>
        Email: <a href="mailto:crypto23b@gmail.com">crypto23b@gmail.com</a>
      </p>
    </div>
    """

    return render_template_string(
        BASE_TEMPLATE,
        content=content,
        active_page=None,
        has_uid=has_uid_flag(),
    )



# Helper: read either object.attribute or dict["key"]
def attr_or_key(obj, name, default=None):
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)

# -------- Dashboard (CraftWorld.tips mode) --------

@app.route("/dashboard", methods=["GET"])
def dashboard():
    error = None
    prices = {}
    coin_usd = 0.0
    uid = session.get("voya_uid")

    # --- 1) Live prices (COIN + USD) ---
    try:
        prices = fetch_live_prices_in_coin()
        coin_usd = float(prices.get("_COIN_USD", 0.0))
    except Exception as e:
        error = f"Error fetching live prices: {e}"
        prices = {}

    price_rows = []
    for token, val in sorted(prices.items()):
        if token.startswith("_"):
            continue  # skip metadata like _COIN_USD
        v = float(val)
        price_rows.append(
            {
                "token": token,
                "price": v,
                "usd": v * coin_usd if coin_usd else 0.0,
            }
        )

    # --- 2) Account snapshot (inventory + factories) ---
    inventory_rows = []
    factory_rows = []

    if uid:
        try:
            cw = fetch_craftworld(uid)

            # 2a) Inventory / resources
            resources = attr_or_key(cw, "resources", []) or []
            for r in resources:
                sym = attr_or_key(r, "symbol", None)
                if not sym:
                    continue
                try:
                    amt = float(attr_or_key(r, "amount", 0) or 0.0)
                except Exception:
                    amt = 0.0

                price_coin = float(prices.get(sym, 0.0))
                value_coin = amt * price_coin
                value_usd = value_coin * coin_usd if coin_usd else 0.0

                inventory_rows.append(
                    {
                        "token": str(sym),
                        "amount": amt,
                        "price_coin": price_coin,
                        "value_coin": value_coin,
                        "value_usd": value_usd,
                    }
                )

            # Sort inventory by token name
            inventory_rows.sort(key=lambda row: row["token"])

            # 2b) Factories from landPlots
            land_plots = attr_or_key(cw, "landPlots", []) or []
            for plot in land_plots:
                plot_name = attr_or_key(plot, "symbol", "") or str(
                    attr_or_key(plot, "id", "")
                )
                areas = attr_or_key(plot, "areas", []) or []
                for area in areas:
                    area_symbol = attr_or_key(area, "symbol", "") or ""
                    factories = attr_or_key(area, "factories", []) or []
                    for facwrap in factories:
                        fac = attr_or_key(facwrap, "factory", None)
                        if not fac:
                            continue

                        definition = attr_or_key(fac, "definition", {}) or {}
                        token = attr_or_key(definition, "id", None)
                        if not token:
                            continue

                        try:
                            api_level = int(attr_or_key(fac, "level", 0) or 0)
                        except Exception:
                            api_level = 0
                        csv_level = api_level + 1  # API is 0-based → CSV 1-based

                        factory_rows.append(
                            {
                                "plot": plot_name,
                                "area": area_symbol,
                                "token": str(token),
                                "level": csv_level,
                            }
                        )

            # Sort factories by token then level
            factory_rows.sort(
                key=lambda row: (row["token"], int(row["level"]))
            )

        except Exception as e:
            # Append account-data error to any existing price error
            if error:
                error = f"{error}\nError fetching account data: {e}"
            else:
                error = f"Error fetching account data: {e}"

    # --- 3) Global profit summary (COIN/hr, USD/hr) ---

    global_coin_hour = 0.0
    global_coin_day = 0.0
    global_usd_hour = 0.0
    global_usd_day = 0.0
    best_factory = None
    worst_factory = None

    # Also build upgrade suggestions
    upgrade_suggestions: List[dict] = []

    if prices and factory_rows:
        boost_levels = get_boost_levels()
        for row in factory_rows:
            token = str(row["token"]).upper()
            level = int(row["level"])

            # Ensure CSV data exists
            if token not in FACTORIES_FROM_CSV:
                continue
            if level not in FACTORIES_FROM_CSV[token]:
                continue

            # Defaults from Boosts tab
            defaults = boost_levels.get(
                token, {"mastery_level": 0, "workshop_level": 0}
            )

            # Mastery → yield multiplier
            try:
                mastery_level = int(defaults.get("mastery_level", 0))
            except Exception:
                mastery_level = 0
            mastery_level = max(0, min(10, mastery_level))
            mastery_factor = float(MASTERY_BONUSES.get(mastery_level, 1.0))
            yield_pct = 100.0 * mastery_factor

            # Workshop → speed multiplier
            try:
                workshop_level = int(defaults.get("workshop_level", 0))
            except Exception:
                workshop_level = 0
            workshop_level = max(0, min(10, workshop_level))
            ws_table = WORKSHOP_MODIFIERS.get(token)
            workshop_pct = 0.0
            if ws_table and 0 <= workshop_level < len(ws_table):
                workshop_pct = float(ws_table[workshop_level])
            speed_factor_eff = 1.0 + workshop_pct / 100.0

            # --- Base profit at current level ---
            try:
                res_cur = compute_factory_result_csv(
                    FACTORIES_FROM_CSV,
                    prices,
                    token,
                    level,
                    target_level=None,
                    count=1,
                    yield_pct=yield_pct,
                    speed_factor=speed_factor_eff,
                    workers=0,
                )
            except Exception:
                continue

            prof_hour = float(res_cur.get("profit_coin_per_hour", 0.0))
            prof_day = prof_hour * 24.0
            usd_hour = prof_hour * coin_usd
            usd_day = prof_day * coin_usd

            # Attach per-factory profit to row for the table
            row["profit_coin_hour"] = prof_hour
            row["profit_coin_day"] = prof_day
            row["profit_usd_hour"] = usd_hour
            row["profit_usd_day"] = usd_day

            # Add to global totals
            global_coin_hour += prof_hour
            global_coin_day += prof_day
            global_usd_hour += usd_hour
            global_usd_day += usd_day

            # Track best / worst single-factory COIN/hr
            if best_factory is None or prof_hour > best_factory["profit_coin_hour"]:
                best_factory = {
                    "token": row["token"],
                    "level": level,
                    "profit_coin_hour": prof_hour,
                    "profit_usd_hour": usd_hour,
                }
            if worst_factory is None or prof_hour < worst_factory["profit_coin_hour"]:
                worst_factory = {
                    "token": row["token"],
                    "level": level,
                    "profit_coin_hour": prof_hour,
                    "profit_usd_hour": usd_hour,
                }

            # --- Upgrade suggestion: level -> level+1 ---
            next_level = level + 1
            if next_level in FACTORIES_FROM_CSV.get(token, {}):
                # Upgrade cost from current level (single-step)
                up_info = res_cur.get("upgrade_single")
                if up_info:
                    try:
                        upgrade_cost_coin = float(up_info.get("coin_per_factory", 0.0))
                    except Exception:
                        upgrade_cost_coin = 0.0
                else:
                    upgrade_cost_coin = 0.0

                # Profit at next level
                try:
                    res_next = compute_factory_result_csv(
                        FACTORIES_FROM_CSV,
                        prices,
                        token,
                        next_level,
                        target_level=None,
                        count=1,
                        yield_pct=yield_pct,
                        speed_factor=speed_factor_eff,
                        workers=0,
                    )
                    prof_hour_next = float(
                        res_next.get("profit_coin_per_hour", 0.0)
                    )
                except Exception:
                    prof_hour_next = prof_hour

                delta_hour = prof_hour_next - prof_hour
                if upgrade_cost_coin > 0 and delta_hour > 0:
                    roi = delta_hour / upgrade_cost_coin  # COIN/hr gained per COIN spent
                    payback_hours = upgrade_cost_coin / delta_hour

                    upgrade_suggestions.append(
                        {
                            "token": row["token"],
                            "from_level": level,
                            "to_level": next_level,
                            "delta_hour": delta_hour,
                            "upgrade_cost_coin": upgrade_cost_coin,
                            "roi": roi,
                            "payback_hours": payback_hours,
                        }
                    )

    # Sort upgrade suggestions by ROI (best first) and keep top 10
    upgrade_suggestions.sort(key=lambda u: u["roi"], reverse=True)
    upgrade_suggestions = upgrade_suggestions[:10]

    content = """
    <div class="card">
      <h1>Dashboard</h1>
      <p class="subtle">
        Live overview of your account, token prices, factory profits, and suggested upgrades.
      </p>
    </div>

    <div class="two-col">
      <!-- LEFT COLUMN: Prices + Inventory -->
      <div>

        <!-- Live Resource Prices -->
        <div class="card">
          <h2>Live Resource Prices</h2>
          {% if price_rows %}
            <table>
              <tr>
                <th>Resource</th>
                <th>Price (COIN)</th>
                <th>Price (USD)</th>
              </tr>

              {% for pr in price_rows %}
                <tr>
                  <td>
                    {% set addr = token_addresses.get(pr.token) %}
                    {% if addr %}
                      <a href="https://katana.roninchain.com/tokens/{{ addr }}"
                         target="_blank"
                         rel="noopener">
                        {{ pr.token }}
                      </a>
                    {% else %}
                      {{ pr.token }}
                    {% endif %}
                  </td>
                  <td>{{ '%.8f'|format(pr.price) }}</td>
                  <td>{{ '%.6f'|format(pr.usd) }}</td>
                </tr>
              {% endfor %}
            </table>
          {% else %}
            <p class="subtle">No live price data available right now.</p>
          {% endif %}
        </div>

        <!-- Inventory Snapshot -->
        <div class="card">
          <h2>📦 Inventory Snapshot</h2>
          {% if inventory_rows %}
            <table>
              <tr>
                <th>Token</th>
                <th>Amount</th>
                <th>Price (COIN)</th>
                <th>Value (COIN)</th>
                <th>Value (USD)</th>
              </tr>
              {% for item in inventory_rows %}
                <tr>
                  <td>{{ item.token }}</td>
                  <td>{{ '%.4f'|format(item.amount) }}</td>
                  <td>{{ '%.8f'|format(item.price_coin) }}</td>
                  <td>{{ '%.6f'|format(item.value_coin) }}</td>
                  <td>{{ '%.6f'|format(item.value_usd) }}</td>
                </tr>
              {% endfor %}
            </table>
          {% else %}
            <p class="subtle">No inventory data available.</p>
          {% endif %}
        </div>


      </div>

      <!-- RIGHT COLUMN: Profit + Upgrades / Factories -->
      <div>

        <!-- Global Profit Summary -->
        <div class="card">
          <h2>💰 Estimated Profit</h2>
          {% if global_coin_hour is not none %}
            <p class="subtle">
              <strong>COIN / hour:</strong>
              {{ '%+.6f'|format(global_coin_hour) }}<br>
              <strong>COIN / day:</strong>
              {{ '%+.6f'|format(global_coin_day) }}<br><br>
              <strong>USD / hour:</strong>
              {{ '%+.6f'|format(global_usd_hour) }}<br>
              <strong>USD / day:</strong>
              {{ '%+.6f'|format(global_usd_day) }}
            </p>
          {% else %}
            <p class="subtle">
              No profit estimates yet. Make sure factories and prices are loaded.
            </p>
          {% endif %}
        </div>

        <!-- Upgrade Suggestions -->
        <div class="card">
          <h2>✨ Suggested Upgrades</h2>
          {% if upgrade_suggestions %}
            <table>
              <tr>
                <th>Factory</th>
                <th>From L</th>
                <th>To L</th>
                <th>Δ COIN/hr</th>
                <th>Upgrade Cost (COIN)</th>
                <th>ROI (Δ/hr per COIN)</th>
                <th>Payback (hours)</th>
              </tr>
              {% for up in upgrade_suggestions %}
                <tr>
                  <td>{{ up.token }}</td>
                  <td>L{{ up.from_level }}</td>
                  <td>L{{ up.to_level }}</td>
                  <td>{{ '%+.6f'|format(up.delta_hour) }}</td>
                  <td>{{ '%.6f'|format(up.upgrade_cost_coin) }}</td>
                  <td>{{ '%.6f'|format(up.roi) }}</td>
                  <td>{{ '%.2f'|format(up.payback_hours) }}</td>
                </tr>
              {% endfor %}
            </table>
          {% else %}
            <p class="subtle">
              No upgrade suggestions right now. You might already be well-optimized
              at current prices.
            </p>
          {% endif %}
        </div>

      </div>
    </div>

    <!-- FACTORY SNAPSHOT OR UID PROMPT -->
    {% if uid %}
      <div class="card">
        <h2>🏭 Factory Snapshot</h2>
        {% if factory_rows %}
          <table>
            <tr>
              <th>Plot</th>
              <th>Area</th>
              <th>Factory</th>
              <th>Level</th>
              <th>COIN/hr (est.)</th>
              <th>USD/hr (est.)</th>
            </tr>
            {% for fac in factory_rows %}
              <tr>
                <td>{{ fac.plot }}</td>
                <td>{{ fac.area }}</td>
                <td>{{ fac.token }}</td>
                <td>L{{ fac.level }}</td>
                <td>
                  {% if fac.profit_coin_hour is defined %}
                    {{ '%+.6f'|format(fac.profit_coin_hour) }}
                  {% else %}
                    —
                  {% endif %}
                </td>
                <td>
                  {% if fac.profit_usd_hour is defined %}
                    {{ '%+.6f'|format(fac.profit_usd_hour) }}
                  {% else %}
                    —
                  {% endif %}
                </td>
              </tr>
            {% endfor %}
          </table>
        {% else %}
          <p class="subtle">No factories found for this account.</p>
        {% endif %}
      </div>
    {% else %}
      <div class="card">
        <h2>Account Snapshot</h2>
        <p class="subtle">
          Enter your Account UID on the <strong>Overview</strong> tab, then come back here
          to see your inventory, factories, profit estimates, and suggested upgrades.
        </p>
      </div>
    {% endif %}
    """


    html = render_template_string(
        BASE_TEMPLATE,
        content=render_template_string(
            content,
            uid=uid,
            price_rows=price_rows,
            coin_usd=coin_usd,
            error=error,
            inventory_rows=inventory_rows,
            factory_rows=factory_rows,
            global_coin_hour=global_coin_hour,
            global_coin_day=global_coin_day,
            global_usd_hour=global_usd_hour,
            global_usd_day=global_usd_day,
            best_factory=best_factory,
            worst_factory=worst_factory,  # <-- fix this
            upgrade_suggestions=upgrade_suggestions,
            token_addresses=TOKEN_ADDRESSES,
        ),
        active_page="dashboard",
        has_uid=has_uid_flag(),
    )

    return html


# -------- Live Token Charts (GeckoTerminal-style) --------
@app.route("/charts", methods=["GET"])
def charts():
    """
    Live token charts, like the iOS CraftMath app:
    - Choose a token from TOKEN_ADDRESSES
    - Embed GeckoTerminal Ronin chart in an iframe
    """
    # Token symbol from query string, e.g. /charts?token=EARTH
    selected = (request.args.get("token") or "").upper().strip()

    # All tokens we know contract addresses for
    tokens = sorted(TOKEN_ADDRESSES.keys())

    # Contract address (if any) for the selected token
    addr = TOKEN_ADDRESSES.get(selected) if selected else None

    content = """
    <div class="card">
      <h1>📈 Live Token Charts</h1>
      <p class="subtle">
        Choose a token to load its live price chart from
        GeckoTerminal (Ronin network), similar to the iOS CraftMath app.
      </p>

      <form method="get" style="margin-bottom:12px; max-width:320px;">
        <label for="token">Token</label>
        <select id="token" name="token" style="width:100%;">
          <option value="">-- select token --</option>
          {% for t in tokens %}
            <option value="{{ t }}" {% if t == selected %}selected{% endif %}>{{ t }}</option>
          {% endfor %}
        </select>
        <div style="margin-top:8px;">
          <button type="submit">Load chart</button>
        </div>
      </form>

      {% if selected and not addr %}
        <div class="error" style="margin-top:10px;">
          No contract address known for <strong>{{ selected }}</strong>.
        </div>
      {% elif selected and addr %}
        <h2 style="margin-top:18px;">{{ selected }} chart</h2>
        <p class="subtle">
          Data source: GeckoTerminal · Ronin network<br>
          You can also
          <a href="https://www.geckoterminal.com/ronin/tokens/{{ addr }}"
             target="_blank" rel="noopener">
            open this chart in a new tab ↗
          </a>.
        </p>

        <div style="
          margin-top:10px;
          border-radius:12px;
          overflow:hidden;
          border:1px solid rgba(148,163,184,0.35);
          box-shadow: 0 10px 30px rgba(0,0,0,0.6);
        ">
          <iframe
            src="https://www.geckoterminal.com/ronin/tokens/{{ addr }}"
            style="width:100%; height:560px; border:0;"
            loading="lazy"
            referrerpolicy="no-referrer-when-downgrade">
          </iframe>
        </div>
      {% endif %}
    </div>
    """

    content = render_template_string(
        content,
        tokens=tokens,
        selected=selected,
        addr=addr,
    )

    html = render_template_string(
        BASE_TEMPLATE,
        content=content,
        active_page="charts",
        has_uid=has_uid_flag(),
    )
    return html




@app.route("/resource/<token>", methods=["GET"])
def resource_view(token: str):
    """
    Detail view for a single resource token:
    - current price (COIN + USD)
    - how much you own (if UID set) and % of total bag
    - which factories produce it
    - which factories consume it
    """
    error = None
    sym_raw = token or ""
    sym = sym_raw.upper()

    prices = {}
    coin_usd = 0.0
    uid = session.get("voya_uid")

    # 1) Prices
    try:
        prices = fetch_live_prices_in_coin()
        coin_usd = float(prices.get("_COIN_USD", 0.0))
    except Exception as e:
        error = f"Error fetching live prices: {e}"
        prices = {}

    price_coin = float(prices.get(sym, 0.0)) if prices else 0.0
    price_usd = price_coin * coin_usd if coin_usd else 0.0

    # 2) Inventory snapshot: this token + total bag
    holding_amount = None
    holding_value_coin = 0.0
    holding_value_usd = 0.0
    total_bag_coin = 0.0
    percent_of_bag = None

    if uid:
        try:
            cw = fetch_craftworld(uid)
            resources = attr_or_key(cw, "resources", []) or []
            for r in resources:
                rsym = str(attr_or_key(r, "symbol", "")).upper()
                try:
                    amt = float(attr_or_key(r, "amount", 0) or 0.0)
                except Exception:
                    amt = 0.0

                p_coin = float(prices.get(rsym, 0.0))
                val_coin = amt * p_coin
                total_bag_coin += val_coin

                if rsym == sym:
                    holding_amount = amt
                    holding_value_coin = val_coin
                    holding_value_usd = val_coin * coin_usd if coin_usd else 0.0

            if holding_value_coin > 0 and total_bag_coin > 0:
                percent_of_bag = 100.0 * holding_value_coin / total_bag_coin

        except Exception as e:
            if error:
                error = f"{error}\nError fetching inventory: {e}"
            else:
                error = f"Error fetching inventory: {e}"

    # 3) Find producers & consumers from FACTORIES_FROM_CSV
    producers: List[dict] = []
    consumers: List[dict] = []

    for fac_name, levels in FACTORIES_FROM_CSV.items():
        for lvl, data in levels.items():
            out_token = str(data.get("output_token", "")).upper()
            duration_min = float(data.get("duration_min", 0.0) or 0.0)
            inputs = data.get("inputs") or {}

            # Producers = factories whose output_token == sym
            if out_token == sym:
                prof_hour = 0.0
                prof_craft = 0.0
                crafts_per_hour = 0.0
                try:
                    res = compute_factory_result_csv(
                        FACTORIES_FROM_CSV,
                        prices,
                        fac_name,
                        int(lvl),
                        target_level=None,
                        count=1,
                        yield_pct=100.0,
                        speed_factor=1.0,
                        workers=0,
                    )
                    prof_hour = float(res.get("profit_coin_per_hour", 0.0))
                    prof_craft = float(res.get("profit_coin_per_craft", 0.0))
                    eff_dur = float(res.get("effective_duration", duration_min))
                    if eff_dur > 0:
                        crafts_per_hour = 60.0 / eff_dur
                except Exception:
                    pass

                out_amount = float(data.get("output_amount", 0.0) or 0.0)
                producers.append(
                    {
                        "factory": fac_name,
                        "level": int(lvl),
                        "duration_min": duration_min,
                        "out_amount": out_amount,
                        "profit_hour": prof_hour,
                        "profit_craft": prof_craft,
                        "crafts_per_hour": crafts_per_hour,
                    }
                )

            # Consumers = factories that list sym in their inputs
            uses_it = False
            total_per_craft = 0.0
            for in_tok, qty in inputs.items():
                if str(in_tok).upper() == sym:
                    uses_it = True
                    total_per_craft += float(qty or 0.0)

            if uses_it:
                crafts_per_hour = 0.0
                amount_per_hour = 0.0
                cost_coin_per_craft = 0.0
                if duration_min > 0:
                    crafts_per_hour = 60.0 / duration_min
                    amount_per_hour = crafts_per_hour * total_per_craft
                cost_coin_per_craft = total_per_craft * price_coin
                consumers.append(
                    {
                        "factory": fac_name,
                        "level": int(lvl),
                        "duration_min": duration_min,
                        "amount_per_craft": total_per_craft,
                        "amount_per_hour": amount_per_hour,
                        "cost_coin_per_craft": cost_coin_per_craft,
                    }
                )

    # Sort producers by profit/hr desc; consumers by amount/hr desc
    producers.sort(key=lambda r: r["profit_hour"], reverse=True)
    consumers.sort(key=lambda r: r["amount_per_hour"], reverse=True)

    content = """
    <div class="card">
      <h1>🔍 Resource: {{ sym }}</h1>
      <p class="subtle">
        Price, holdings, and which factories produce or consume this resource
        (baseline: 100% yield, 1x speed, 0 workers).
      </p>

      <div style="display:flex; flex-wrap:wrap; gap:16px;">
        <div>
          <strong>Price:</strong><br>
          {{ '%.8f'|format(price_coin) }} COIN<br>
          {{ '%.6f'|format(price_usd) }} USD
        </div>
        <div>
          <strong>COIN → USD:</strong><br>
          {{ '%.6f'|format(coin_usd) }} USD / COIN
        </div>
        <div>
          {% if uid %}
            <strong>Your holdings:</strong><br>
            {% if holding_amount is not none %}
              {{ '%.6f'|format(holding_amount) }} {{ sym }}<br>
              {{ '%.6f'|format(holding_value_coin) }} COIN<br>
              {{ '%.6f'|format(holding_value_usd) }} USD<br>
              {% if percent_of_bag is not none %}
                <span class="subtle">
                  (~{{ '%.2f'|format(percent_of_bag) }}% of your total inventory value in COIN)
                </span>
              {% endif %}
            {% else %}
              <span class="subtle">No {{ sym }} found in inventory.</span>
            {% endif %}
          {% else %}
            <span class="subtle">Set your UID on Overview to see your holdings.</span>
          {% endif %}
        </div>
        <div>
          <a href="{{ url_for('dashboard') }}" class="pill">⬅ Back to Dashboard</a><br>
          <a href="{{ url_for('trees') }}" class="pill" style="margin-top:6px;">🌳 View Trees</a>
        </div>
      </div>
    </div>

    {% if error %}
      <div class="card">
        <div class="error" style="margin:0; white-space:pre-wrap;">{{ error }}</div>
      </div>
    {% endif %}

    <div class="card">
      <h2>🏭 Factories that PRODUCE {{ sym }}</h2>
      {% if producers %}
        <table>
          <tr>
            <th>Factory</th>
            <th>Level</th>
            <th>Output / craft</th>
            <th>Duration (min)</th>
            <th>Crafts / hour</th>
            <th>Profit / craft (COIN)</th>
            <th>Profit / hour (COIN)</th>
          </tr>
          {% for p in producers %}
            <tr>
              <td>{{ p.factory }}</td>
              <td>L{{ p.level }}</td>
              <td>{{ '%.4f'|format(p.out_amount) }}</td>
              <td>{{ '%.2f'|format(p.duration_min) }}</td>
              <td>{{ '%.4f'|format(p.crafts_per_hour) }}</td>
              <td>{{ '%+.6f'|format(p.profit_craft) }}</td>
              <td>{{ '%+.6f'|format(p.profit_hour) }}</td>
            </tr>
          {% endfor %}
        </table>
      {% else %}
        <p class="subtle">No factories found that output {{ sym }} directly.</p>
      {% endif %}
    </div>

    <div class="card">
      <h2>⚙️ Factories that CONSUME {{ sym }}</h2>
      {% if consumers %}
        <table>
          <tr>
            <th>Factory</th>
            <th>Level</th>
            <th>Uses / craft</th>
            <th>Uses / hour</th>
            <th>Cost / craft (COIN)</th>
          </tr>
          {% for c in consumers %}
            <tr>
              <td>{{ c.factory }}</td>
              <td>L{{ c.level }}</td>
              <td>{{ '%.4f'|format(c.amount_per_craft) }}</td>
              <td>{{ '%.4f'|format(c.amount_per_hour) }}</td>
              <td>{{ '%.6f'|format(c.cost_coin_per_craft) }}</td>
            </tr>
          {% endfor %}
        </table>
      {% else %}
        <p class="subtle">No factories found that use {{ sym }} as an input.</p>
      {% endif %}
    </div>
    """

    html = render_template_string(
        BASE_TEMPLATE,
        content=render_template_string(
            content,
            sym=sym,
            uid=uid,
            price_coin=price_coin,
            price_usd=price_usd,
            coin_usd=coin_usd,
            holding_amount=holding_amount,
            holding_value_coin=holding_value_coin,
            holding_value_usd=holding_value_usd,
            percent_of_bag=percent_of_bag,
            error=error,
            producers=producers,
            consumers=consumers,
        ),
        active_page="dashboard",  # keep Dashboard highlighted
        has_uid=has_uid_flag(),
    )
    return html




# -------- Profitability tab (manual mastery + workshop) --------

@app.route("/profitability", methods=["GET", "POST"])
def profitability():
    # Require UID set in Overview (so we know whose factories to pull)
    if not has_uid_flag():
        content = """
        <div class="card">
          <h1>Profitability (Locked)</h1>
          <p class="subtle">
            Enter your Account UID on the <strong>Overview</strong> tab to unlock
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

    # Input price mode: "sell" (default) or "buy"
    saved_input_price_mode: str = session.get("profit_input_price_mode", "sell")
    input_price_mode: str = saved_input_price_mode



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

        # Input price mode from form ("sell" or "buy")
        pmode = (request.form.get("input_price_mode") or input_price_mode or "sell").strip()
        if pmode not in ("sell", "buy"):
            pmode = "sell"
        input_price_mode = pmode
        session["profit_input_price_mode"] = input_price_mode


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
    debug_earth_sell = 0.0
    debug_earth_buy = 0.0

    try:
        # 1) Flat SELL-focused prices + COIN → USD
        prices_flat = fetch_live_prices_in_coin()
        coin_usd = float(prices_flat.get("_COIN_USD", 0.0))

        # 2) BUY / SELL matrix for relevant symbols using exactInputQuote
        #    Only refine prices for factories the player actually has rows for.
        relevant_symbols = sorted({m["token"].upper() for m in rows_meta})
        per_symbol = fetch_buy_sell_for_profitability(relevant_symbols)


        prices_sell: Dict[str, float] = {}
        prices_buy: Dict[str, float] = {}

        for sym_u, rec_map in per_symbol.items():
            sym_u = sym_u.upper()
            # SELL map: prefer SELL, then BUY, then any
            if "SELL" in rec_map:
                prices_sell[sym_u] = float(rec_map["SELL"])
            elif "BUY" in rec_map:
                prices_sell[sym_u] = float(rec_map["BUY"])
            elif rec_map:
                prices_sell[sym_u] = float(next(iter(rec_map.values())))

            # BUY map: prefer BUY, then SELL, then any
            if "BUY" in rec_map:
                prices_buy[sym_u] = float(rec_map["BUY"])
            elif "SELL" in rec_map:
                prices_buy[sym_u] = float(rec_map["SELL"])
            elif rec_map:
                prices_buy[sym_u] = float(next(iter(rec_map.values())))

        # Ensure COIN present as 1.0 in both maps
        prices_sell.setdefault("COIN", 1.0)
        prices_buy.setdefault("COIN", 1.0)


        # Debug: capture one token's BUY vs SELL for display (EARTH)
        debug_earth_sell = float(prices_sell.get("EARTH", 0.0))
        debug_earth_buy = float(prices_buy.get("EARTH", 0.0))

        # Which map should input costs use?
        if input_price_mode == "buy":
            input_prices = prices_buy

        else:
            # SELL mode: value inputs the same way as outputs
            input_prices = None  # let factories fall back to SELL map

        # Main output price map is always SELL-focused
        prices = prices_sell


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
                yield_pct=yield_pct,                  # mastery → input reduction
                speed_factor=effective_speed_factor,  # workshop + AD → time reduction
                workers=workers,
                input_prices_coin=input_prices,       # NEW: BUY vs SELL input costs
            )

            cost_coin_per_craft = float(res.get("cost_coin_per_craft", 0.0))
            value_coin_per_craft = float(res.get("value_coin_per_craft", 0.0))
            profit_coin_per_craft = float(res.get("profit_coin_per_craft", 0.0))

            margin_pct = 0.0
            if value_coin_per_craft > 0:
                margin_pct = (profit_coin_per_craft / value_coin_per_craft) * 100.0



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

                    # exact quote per craft for this factory at this level
                    "cost_coin_per_craft": cost_coin_per_craft,
                    "value_coin_per_craft": value_coin_per_craft,
                    "profit_coin_per_craft": profit_coin_per_craft,
                    "margin_pct": margin_pct,

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
            rows.sort(key=lambda r: r["profit_hour_total"], reverse=True)
        elif sort_mode == "loss_gain":
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

      <form method="post" style="margin-bottom:12px;" id="profit_form">
        <div style="display:flex;flex-wrap:wrap;gap:16px;">
          <div style="min-width:160px;">
            <label for="speed_factor">Global Speed (AD / boosts)</label>
            <input
              type="number"
              step="0.1"
              name="speed_factor"
              value="{{global_speed}}"
              class="auto-calc"
            />
            <div class="hint">Multiplies base time before workshop &amp; workers.</div>
          </div>

          <div style="min-width:160px;">
            <label for="yield_pct">Base Yield % (fallback)</label>
            <input
              type="number"
              step="0.1"
              name="yield_pct"
              value="{{global_yield}}"
              class="auto-calc"
            />
            <div class="hint">Used only if mastery level not in table.</div>
          </div>


          <div style="min-width:180px;">
            <label for="sort_mode">Sort</label>
            <select name="sort_mode" id="sort_mode" onchange="this.form.submit()">
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

          <div style="min-width:220px;">
            <label for="input_price_mode">Value inputs using</label>
            <select name="input_price_mode" id="input_price_mode" onchange="this.form.submit()">
              <option value="sell" {% if input_price_mode == 'sell' %}selected{% endif %}>
                Sell price (what you'd get selling them)
              </option>
              <option value="buy" {% if input_price_mode == 'buy' %}selected{% endif %}>
                Buy price (what you'd pay to buy them)
              </option>
            </select>
            <div class="hint">Outputs are always valued at SELL price.</div>
            <div class="hint">
              Debug EARTH: SELL {{ '%.8f'|format(debug_earth_sell) }},
              BUY {{ '%.8f'|format(debug_earth_buy) }}
            </div>
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

    <!-- NEW QUOTE COLUMNS -->
    <th>Cost/craft (COIN)</th>
    <th>Value/craft (COIN)</th>
    <th>Profit/craft (COIN)</th>
    <th>Margin %</th>

    <th>P/hr (1)</th>
    <th>P/hr (All)</th>
    <th>P/day</th>
    <th>USD/hr</th>
  </tr>

  {% for r in rows %}
  <tr>
    <td>
      <input type="checkbox"
          name="run_{{r.key}}"
          {% if r.selected %}checked{% endif %}>
    </td>

    <td>{{ r.token }}</td>
    <td>{{ r.level }}</td>
    <td>{{ r.count }}</td>

    <td>
      <input type="number"
        min="0" max="10"
        name="mastery_{{ r.key }}"
        value="{{ r.mastery_level }}"
        style="width:60px;">
    </td>

    <td>{{ '%.2f'|format(r.yield_pct) }}</td>

    <td>
      <input type="number"
        min="0" max="10"
        name="workshop_{{ r.key }}"
        value="{{ r.workshop_level }}"
        style="width:60px;">
    </td>

    <td>{{ '%.2f'|format(r.workshop_pct) }}</td>

    <td>
      <input type="number"
        min="0" max="4"
        name="workers_{{ r.key }}"
        value="{{ r.workers }}"
        style="width:60px;">
    </td>

    <!-- NEW QUOTE VALUES -->
    <td>{{ '%.6f'|format(r.cost_coin_per_craft) }}</td>
    <td>{{ '%.6f'|format(r.value_coin_per_craft) }}</td>
    <td>{{ '%.6f'|format(r.profit_coin_per_craft) }}</td>
    <td>{{ '%.2f'|format(r.margin_pct) }}</td>

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

      <script>
      document.addEventListener('DOMContentLoaded', function () {
        // Any input with class "auto-calc" will auto-submit its form on change
        const inputs = document.querySelectorAll('.auto-calc');
        let timer = null;

        inputs.forEach(function (input) {
          input.addEventListener('input', function () {
            if (timer) {
              clearTimeout(timer);
            }
            const form = input.form;
            if (!form) return;

            timer = setTimeout(function () {
              form.submit();
            }, 400); // debounce a bit so holding the arrow doesn't spam
          });
        });
      });
      </script>
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
            input_price_mode=input_price_mode,
            debug_earth_sell=debug_earth_sell,
            debug_earth_buy=debug_earth_buy,
        ),
        active_page="profit",
        has_uid=has_uid_flag(),
    )
    return html


# -------- Flex Planner tab (smart flex-plot suggestions) --------

@app.route("/flex", methods=["GET", "POST"])
def flex_planner():
    # Require UID so we can pull your inventory.
    if not has_uid_flag():
        content = """
        <div class="card">
          <h1>Flex Planner (Locked)</h1>
          <p class="subtle">
            Enter your Account UID on the <strong>Overview</strong> tab to unlock
            automatic inventory loading for the Flex Planner.
          </p>
        </div>
        """
        html = render_template_string(
            BASE_TEMPLATE,
            content=content,
            active_page="flex",
            has_uid=has_uid_flag(),
        )
        return html

    error = None
    uid = session.get("voya_uid")

    # Defaults / saved state
    saved_yield_pct = float(session.get("flex_yield_pct", 100.0))
    saved_speed_factor = float(session.get("flex_speed_factor", 1.0))
    saved_workers = int(session.get("flex_workers", 0))
    saved_budget_coin = float(session.get("flex_upgrade_budget_coin", 0.0))
    saved_sim_token = session.get("flex_sim_token", "")
    saved_sim_amount = float(session.get("flex_sim_amount", 0.0))

    yield_pct = saved_yield_pct
    speed_factor = saved_speed_factor
    workers = saved_workers
    upgrade_budget_coin = saved_budget_coin

    sim_token = saved_sim_token
    sim_amount = saved_sim_amount
    
    # On first GET, auto-populate yield/speed from your Boosts tab
    if request.method == "GET" and "flex_yield_pct" not in session:
        try:
            boost_levels = get_boost_levels() or {}
            mastery_levels = []
            workshop_levels = []

            for _tok, lvls in boost_levels.items():
                try:
                    mastery_levels.append(int(lvls.get("mastery_level", 0)))
                    workshop_levels.append(int(lvls.get("workshop_level", 0)))
                except Exception:
                    continue

            if mastery_levels:
                avg_m = sum(mastery_levels) / len(mastery_levels)
                m_level = max(0, min(10, int(round(avg_m))))
                mastery_factor = float(MASTERY_BONUSES.get(m_level, 1.0))
                # Convert mastery multiplier (e.g. 1.12) → yield% (112%)
                yield_pct = 100.0 * mastery_factor

            if workshop_levels and WORKSHOP_MODIFIERS:
                avg_w = sum(workshop_levels) / len(workshop_levels)
                w_level = max(0, min(10, int(round(avg_w))))

                # Pick any token's WS table as a generic reference
                some_tok = next(iter(WORKSHOP_MODIFIERS.keys()), None)
                if some_tok:
                    ws_table = WORKSHOP_MODIFIERS.get(some_tok) or []
                    if 0 <= w_level < len(ws_table):
                        ws_pct = float(ws_table[w_level])
                        # WS % is extra speed on top of 1.0x
                        speed_factor = 1.0 + ws_pct / 100.0
        except Exception:
            # If anything fails, just keep the manual defaults
            pass


    if request.method == "POST":
        y_str = request.form.get("yield_pct", str(yield_pct)).strip() or str(yield_pct)
        s_str = request.form.get("speed_factor", str(speed_factor)).strip() or str(speed_factor)
        w_str = request.form.get("workers", str(workers)).strip() or str(workers)
        b_str = request.form.get("upgrade_budget_coin", str(upgrade_budget_coin)).strip() or str(upgrade_budget_coin)
        sim_tok_str = (request.form.get("sim_token", sim_token) or "").strip().upper()
        sim_amt_str = (request.form.get("sim_amount", str(sim_amount)).strip() or "0")


        try:
            yield_pct = float(y_str)
        except ValueError:
            yield_pct = saved_yield_pct

        try:
            speed_factor = float(s_str)
        except ValueError:
            speed_factor = saved_speed_factor

        try:
            workers = max(0, min(int(w_str), 4))
        except ValueError:
            workers = saved_workers

        try:
            upgrade_budget_coin = max(0.0, float(b_str))
        except ValueError:
            upgrade_budget_coin = saved_budget_coin

        try:
            sim_amount = max(0.0, float(sim_amt_str))
        except ValueError:
            sim_amount = saved_sim_amount

        sim_token = sim_tok_str if sim_tok_str else ""

        session["flex_yield_pct"] = yield_pct
        session["flex_speed_factor"] = speed_factor
        session["flex_workers"] = workers
        session["flex_upgrade_budget_coin"] = upgrade_budget_coin
        session["flex_sim_token"] = sim_token
        session["flex_sim_amount"] = sim_amount


    # 1) Load CraftWorld account data for inventory
    inventory: Dict[str, float] = {}
    try:
        cw = fetch_craftworld(uid)
        resources = attr_or_key(cw, "resources", []) or []
        for r in resources:
            symbol = attr_or_key(r, "symbol", None)
            amount = float(attr_or_key(r, "amount", 0) or 0)
            if symbol:
                symbol = str(symbol).upper()
                inventory[symbol] = inventory.get(symbol, 0.0) + amount
    except Exception as e:
        error = f"Error fetching inventory: {e}"

    # Inventory used for affordability logic (includes simulation)
    logic_inventory: Dict[str, float] = dict(inventory)
    if sim_token and sim_amount > 0:
        logic_inventory[sim_token] = logic_inventory.get(sim_token, 0.0) + sim_amount


    # Helper: full upgrade chain requirements for token + level, for `count` factories.
    def calc_upgrade_chain(token_u: str, level: int, count: int = 1) -> Dict[str, float]:
        token_u = str(token_u).upper()
        chain: Dict[str, float] = {}
        levels = FACTORIES_FROM_CSV.get(token_u, {})
        # Levels in CSV are 1..N, each row's upgrade_x is cost from previous → this level
        for lvl in range(1, level + 1):
            data = levels.get(lvl)
            if not data:
                continue
            up_tok = data.get("upgrade_token")
            up_amt = data.get("upgrade_amount")
            if up_tok and up_amt and up_amt > 0:
                u = str(up_tok).upper()
                chain[u] = chain.get(u, 0.0) + float(up_amt) * count
        return chain

    candidates: List[Dict[str, Any]] = []
    bands: List[Dict[str, Any]] = []
    summary_rows: List[Dict[str, Any]] = []
    combined_speed: Optional[float] = None
    coin_usd: float = 0.0
    total_coin_hour: float = 0.0
    total_usd_hour: float = 0.0
    total_shortfall_coin_layout: float = 0.0
    flex_share_text: str = ""


    # Tokens that can appear as upgrade resources (for simulation dropdown)
    sim_tokens_set = set()
    for _fac_name, _levels in FACTORIES_FROM_CSV.items():
        for _lvl, _data in _levels.items():
            up_tok = _data.get("upgrade_token")
            if up_tok:
                sim_tokens_set.add(str(up_tok).upper())
    sim_tokens = sorted(sim_tokens_set)


    try:
        prices = fetch_live_prices_in_coin()
        coin_usd = float(prices.get("_COIN_USD", 0.0))

        # 2) Get a big list of best setups (1 factory each, no flex shape yet)
        best_rows, combined_speed, _worker_factor = compute_best_setups_csv(
            FACTORIES_FROM_CSV,
            prices,
            speed_factor=speed_factor,
            workers=workers,
            yield_pct=yield_pct,
            top_n=300,   # plenty of headroom to filter down
        )

        # 3) Build per-factory candidates that are individually affordable
        #    (upgrade shortfall for ONE factory <= budget).
        for r in best_rows:
            token = str(r["token"]).upper()
            lvl = int(r["level"])
            profit_h = float(r["profit_coin_per_hour"])
            profit_craft = float(r["profit_coin_per_craft"])

            # Upgrade chain for ONE factory
            chain_1 = calc_upgrade_chain(token, lvl, count=1)

            # Compute shortfall vs inventory and cost of that shortfall in COIN.
            indiv_shortfall_coin = 0.0
            impossible = False
            for res_tok, needed in chain_1.items():
                have = logic_inventory.get(res_tok, 0.0)
                short = max(0.0, needed - have)
                if short <= 0:
                    continue
                price_res = float(prices.get(res_tok, 0.0))
                if price_res <= 0.0:
                    # Can't price or buy this resource; if we don't have enough, it's impossible.
                    impossible = True
                    break
                indiv_shortfall_coin += short * price_res

            if impossible:
                continue

            # If one factory is already way beyond budget, skip.
            if indiv_shortfall_coin > upgrade_budget_coin + 1e-9:
                continue

            candidates.append(
                {
                    "token": token,
                    "level": lvl,
                    "profit_coin_per_hour": profit_h,
                    "profit_coin_per_craft": profit_craft,
                    "upgrade_chain_one": chain_1,
                    "upgrade_shortfall_coin_one": indiv_shortfall_coin,
                }
            )

        # Sort candidates by profit/hr (single factory)
        candidates.sort(key=lambda r: r["profit_coin_per_hour"], reverse=True)

        # 4) Build the flex layout bands with counts [3, 2, 2, 1]
        #    We simulate spending inventory + COIN budget as we pick each band.
        counts_pattern = [3, 2, 2, 1]
        inv_left = dict(logic_inventory)
        budget_left = upgrade_budget_coin

        for band_idx, slots in enumerate(counts_pattern, start=1):
            chosen = None

            for cand in candidates:
                token = cand["token"]
                lvl = cand["level"]

                # Upgrade requirements for THIS band (slots copies).
                req_band = calc_upgrade_chain(token, lvl, count=slots)

                band_coin_needed = 0.0
                impossible = False
                for res_tok, needed in req_band.items():
                    have = inv_left.get(res_tok, 0.0)
                    short = max(0.0, needed - have)
                    if short <= 0:
                        continue
                    price_res = float(prices.get(res_tok, 0.0))
                    if price_res <= 0.0:
                        impossible = True
                        break
                    band_coin_needed += short * price_res

                if impossible:
                    continue
                if band_coin_needed > budget_left + 1e-9:
                    # Too expensive given remaining budget.
                    continue

                # We can afford this band; commit it.
                chosen = {
                    "band_index": band_idx,
                    "count": slots,
                    "token": token,
                    "level": lvl,
                    "profit_coin_per_hour": cand["profit_coin_per_hour"],
                    "profit_coin_per_craft": cand["profit_coin_per_craft"],
                    "upgrade_requirements": req_band,
                    "upgrade_cost_coin": band_coin_needed,
                }

                # Deduct resources and budget
                for res_tok, needed in req_band.items():
                    have = inv_left.get(res_tok, 0.0)
                    inv_left[res_tok] = max(0.0, have - needed)
                budget_left -= band_coin_needed
                break  # stop scanning candidates for this band

            if chosen:
                bands.append(chosen)
            else:
                # Can't fill this band under current budget/inventory; stop.
                break

        # 5) Totals for layout profitability
        total_coin_hour = sum(
            b["profit_coin_per_hour"] * b["count"] for b in bands
        )
        total_usd_hour = total_coin_hour * coin_usd

        # NEW: per-row (band) breakdown against your ORIGINAL inventory.
        # This annotates each band with `breakdown_rows` and `band_shortfall_coin`.
        for b in bands:
            band_rows = []
            band_shortfall_coin = 0.0
            for res_tok, needed in sorted(b["upgrade_requirements"].items()):
                have = logic_inventory.get(res_tok, 0.0)
                short = max(0.0, needed - have)
                price_res = float(prices.get(res_tok, 0.0))
                coin_cost = short * price_res if price_res > 0 else 0.0
                band_shortfall_coin += coin_cost
                band_rows.append(
                    {
                        "token": res_tok,
                        "needed": needed,
                        "have": have,
                        "shortfall": short,
                        "shortfall_coin": coin_cost,
                    }
                )
            b["breakdown_rows"] = band_rows
            b["band_shortfall_coin"] = band_shortfall_coin


        # 6) Aggregate upgrade requirements for the whole layout (3+2+2+1),
        #    and compute shortfall vs ORIGINAL inventory + cost in COIN.
        agg_req: Dict[str, float] = {}
        for b in bands:
            for res_tok, amt in b["upgrade_requirements"].items():
                agg_req[res_tok] = agg_req.get(res_tok, 0.0) + float(amt)

        summary_rows = []
        total_shortfall_coin_layout = 0.0
        for res_tok, needed in sorted(agg_req.items()):
            have = logic_inventory.get(res_tok, 0.0)
            short = max(0.0, needed - have)
            price_res = float(prices.get(res_tok, 0.0))
            coin_cost = short * price_res if price_res > 0 else 0.0
            total_shortfall_coin_layout += coin_cost
            summary_rows.append(
                {
                    "token": res_tok,
                    "needed": needed,
                    "have": have,
                    "shortfall": short,
                    "shortfall_coin": coin_cost,
                }
            )

        # NEW: upgrade priority list – which resources are your biggest bottlenecks.
        priority_rows = sorted(
            [row for row in summary_rows if row["shortfall"] > 0],
            key=lambda r: r["shortfall_coin"],
            reverse=True,
        )

        # 7) Build shareable summary text for Discord / notes
        lines: List[str] = []

        lines.append("Flex Planner 3–2–2–1 layout")
        lines.append(f"Upgrade budget: {upgrade_budget_coin:.6f} COIN")

        if total_coin_hour:
            if coin_usd:
                lines.append(
                    f"Layout profit: {total_coin_hour:.6f} COIN/hr "
                    f"(~{total_usd_hour:.4f} USD/hr)"
                )
            else:
                lines.append(f"Layout profit: {total_coin_hour:.6f} COIN/hr")

        if total_shortfall_coin_layout > 0 and total_coin_hour:
            roi = total_coin_hour / total_shortfall_coin_layout
            payback = total_shortfall_coin_layout / total_coin_hour
            lines.append(
                f"Total upgrade shortfall: {total_shortfall_coin_layout:.6f} COIN"
            )
            lines.append(
                f"ROI: {roi:.4f} COIN/hr per COIN; payback: {payback:.2f} hours"
            )
        elif total_shortfall_coin_layout <= 0:
            lines.append(
                "You already have enough upgrade resources for this layout "
                "(no extra COIN needed)."
            )

        lines.append("")
        lines.append("Rows:")
        for b in bands:
            row_profit = b["profit_coin_per_hour"] * b["count"]
            lines.append(
                f"Row {b['band_index']}: {b['count']}x {b['token']} L{b['level']} "
                f"– profit {row_profit:.6f} COIN/hr, "
                f"upgrade cost {b['upgrade_cost_coin']:.6f} COIN"
            )

        if summary_rows:
            lines.append("")
            lines.append("Upgrade resources needed (total):")
            for r in summary_rows:
                if r["shortfall"] > 0:
                    lines.append(
                        f"{r['token']}: need {r['needed']:.6f}, "
                        f"have {r['have']:.6f}, "
                        f"short {r['shortfall']:.6f} "
                        f"(cost {r['shortfall_coin']:.6f} COIN)"
                    )

        flex_share_text = "\n".join(lines)


    
    except Exception as e:
        error = f"{error or ''}\nFlex Planner calculation failed: {e}"

    # Sort inventory for display
    inventory_rows = sorted(
        [{"token": t, "amount": amt} for t, amt in inventory.items()],
        key=lambda row: row["token"],
    )

    content = """
    <div class="card">
      <h1 class="flex-layout-title">
        <span class="emoji">🧠</span>
        <span>Flex Planner (8-slot smart layout)</span>
      </h1>
      <p class="subtle">
        This tab tries to act like a mini AI for your <strong>Flex Plot</strong>:
        it looks at your <strong>current inventory</strong>, your
        <strong>DINO COIN upgrade budget</strong> and live prices,
        then builds a 3–2–2–1 layout:
        <br>
        Row 1: 3× same factory, Row 2: 2× same, Row 3: 2× same, Row 4: 1×.
        <br><br>
        It only considers factories and levels that you can afford to
        upgrade to using your current resources plus the COIN budget.
      </p>


      <form method="post" style="margin-bottom:12px;">
        <div style="display:flex;flex-wrap:wrap;gap:12px;">
          <div style="flex:1;min-width:140px;">
            <label for="yield_pct">Yield / Mastery (%)</label>
            <input id="yield_pct" name="yield_pct" type="number" step="0.1"
                   value="{{ yield_pct }}" style="width:100%;">
          </div>

          <div style="flex:1;min-width:140px;">
            <label for="speed_factor">Speed (1x or 2x)</label>
            <input id="speed_factor" name="speed_factor" type="number" step="0.5"
                   value="{{ speed_factor }}" style="width:100%;">
          </div>

          <div style="flex:1;min-width:140px;">
            <label for="workers">Workers (0–4 per factory)</label>
            <input id="workers" name="workers" type="number" min="0" max="4"
                   value="{{ workers }}" style="width:100%;">
          </div>

          <div style="flex:1;min-width:160px;">
            <label for="upgrade_budget_coin">Upgrade budget (COIN)</label>
            <input id="upgrade_budget_coin" name="upgrade_budget_coin"
                   type="number" step="0.000001" min="0"
          <div style="flex:1;min-width:180px;">
            <label for="sim_token">Simulate buying resource</label>
            <select id="sim_token" name="sim_token" style="width:100%;">
              <option value="">(none)</option>
              {% for tok in sim_tokens %}
                <option value="{{ tok }}" {% if tok == sim_token %}selected{% endif %}>{{ tok }}</option>
              {% endfor %}
            </select>
            <div class="hint">Adds this resource on top of your inventory for planning only.</div>
          </div>

          <div style="flex:1;min-width:160px;">
            <label for="sim_amount">Simulated extra amount</label>
            <input id="sim_amount" name="sim_amount" type="number" step="0.000001"
                   value="{{ sim_amount }}" style="width:100%;">
            <div class="hint">E.g. 10000 STEEL to see what unlocks.</div>
          </div>

        </div>

        <button type="submit" style="margin-top:10px;">Recalculate Flex Layout</button>
      </form>

      {% if error %}
        <div class="error">{{ error }}</div>
      {% endif %}

      <div class="two-col">
        <div class="card">
          <h2>Your inventory snapshot</h2>
          {% if inventory_rows %}
            <table>
              <tr><th>Token</th><th>Amount</th></tr>
              {% for r in inventory_rows %}
                <tr>
                  <td>{{ r.token }}</td>
                  <td>{{ "%.3f"|format(r.amount) }}</td>
                </tr>
              {% endfor %}
            </table>
          {% else %}
            <p class="subtle">No resources detected – is your UID correct?</p>
          {% endif %}
        </div>

          <div class="flex-meta-row">
            <div>
              <strong>Slots:</strong> 3–2–2–1
            </div>
            <div>
              <strong>Workers:</strong> {{ workers }}
            </div>
            <div>
              <strong>Speed x:</strong> {{ "%.2f"|format(speed_factor) }}
            </div>
            <div>
              <strong>Yield:</strong> {{ "%.1f"|format(yield_pct) }}%
            </div>
          </div>


        <div class="card">
          <p class="subtle">
            Total profit: {{ "%+.6f"|format(total_coin_hour) }} COIN / hr
            {% if coin_usd and total_coin_hour %}
              (≈ {{ "%+.4f"|format(total_usd_hour) }} USD / hr)
            {% endif %}
            {% if combined_speed %}
              <br>Effective speed: {{ "%.2f"|format(combined_speed) }}x
            {% endif %}
            <br>
            Upgrade shortfall (after inventory) for this layout:
            {{ "%+.6f"|format(total_shortfall_coin_layout) }} COIN
            (Budget: {{ "%+.6f"|format(upgrade_budget_coin) }} COIN)
            {% if total_shortfall_coin_layout > 0 and total_coin_hour %}
              <br>
              ROI: {{ "%.4f"|format(total_coin_hour / total_shortfall_coin_layout) }} COIN/hr per COIN spent
              <br>
              Payback time: {{ "%.2f"|format(total_shortfall_coin_layout / total_coin_hour) }} hours
            {% endif %}
          </p>

          {% if bands %}
            <table>
              <tr>
                <th>Flex row</th>
                <th>Slots</th>
                <th>Factory</th>
                <th>Level</th>
                <th>Profit / hr (per)</th>
                <th>Profit / hr (row)</th>
                <th>Upgrade cost (COIN)</th>
                <th>ROI (hr⁻¹)</th>
              </tr>
              {% for b in bands %}
                {% set good = b.profit_coin_per_hour >= 0 %}
                {% set row_profit = b.profit_coin_per_hour * b.count %}
                <tr>
                  <td>{{ b.band_index }}</td>
                  <td>{{ b.count }}</td>
                  <td>{{ b.token }}</td>
                  <td>L{{ b.level }}</td>
                  <td>
                    <span class="{{ 'pill' if good else 'pill-bad' }}">
                      {{ "%+.6f"|format(b.profit_coin_per_hour) }}
                    </span>
                  </td>
                  <td>
                    <span class="{{ 'pill' if good else 'pill-bad' }}">
                      {{ "%+.6f"|format(row_profit) }}
                    </span>
                  </td>
                  <td>{{ "%.6f"|format(b.upgrade_cost_coin) }}</td>
                  <td>
                    {% if b.upgrade_cost_coin > 0 and row_profit %}
                      {{ "%.6f"|format(row_profit / b.upgrade_cost_coin) }}
                    {% else %}
                      —
                    {% endif %}
                  </td>
                </tr>
              {% endfor %}
            </table>
          {% else %}
            <p class="subtle">
              No flex layout could be built with the current budget and inventory.
              Try increasing the COIN budget or adjusting yield/speed.
            </p>
          {% endif %}
        </div>
      </div>

      <!-- NEW: per-row upgrade breakdown card -->
      <div class="card" style="margin-top:10px;">
        <h2>Per-row upgrade breakdown</h2>
        {% if bands %}
          {% for b in bands %}
            <h3>
              Row {{ b.band_index }} – {{ b.count }}× {{ b.token }} L{{ b.level }}
            </h3>
            {% if b.breakdown_rows %}
              <table>
                <tr>
                  <th>Resource</th>
                  <th>Needed</th>
                  <th>You have</th>
                  <th>Shortfall</th>
                  <th>Shortfall value (COIN)</th>
                </tr>
                {% for r in b.breakdown_rows %}
                  <tr>
                    <td>{{ r.token }}</td>
                    <td>{{ "%.6f"|format(r.needed) }}</td>
                    <td>{{ "%.6f"|format(r.have) }}</td>
                    <td>{{ "%.6f"|format(r.shortfall) }}</td>
                    <td>{{ "%.6f"|format(r.shortfall_coin) }}</td>
                  </tr>
                {% endfor %}
              </table>
              <p class="subtle">
                Shortfall for this row:
                {{ "%.6f"|format(b.band_shortfall_coin) }} COIN
              </p>
            {% else %}
              <p class="subtle">
                No upgrade requirements for this row.
              </p>
            {% endif %}
          {% endfor %}
        {% else %}
          <p class="subtle">No flex layout calculated yet.</p>
        {% endif %}
      </div>

      <!-- NEW: Upgrade priority – answers "what to upgrade / buy first" -->
      <div class="card" style="margin-top:10px;">
        <h2>What to upgrade / buy first</h2>
        {% if priority_rows %}
          <p class="subtle">
            These resources are currently limiting this flex layout the most.
            Buying / farming them first unlocks the full 3–2–2–1 setup.
          </p>
          <table>
            <tr>
              <th>Resource</th>
              <th>Shortfall</th>
              <th>Shortfall value (COIN)</th>
            </tr>
            {% for r in priority_rows[:10] %}
              <tr>
                <td>{{ r.token }}</td>
                <td>{{ "%.6f"|format(r.shortfall) }}</td>
                <td>{{ "%.6f"|format(r.shortfall_coin) }}</td>
              </tr>
            {% endfor %}
          </table>
        {% else %}
          <p class="subtle">
            You already have enough upgrade resources for this flex layout – nothing to buy 🎉
          </p>
        {% endif %}
      </div>

      <div class="card" style="margin-top:10px;">
        <h2>Upgrade requirements for this flex layout</h2>
        {% if summary_rows %}
          <table>
            <tr>
              <th>Resource</th>
              <th>Needed</th>
              <th>You have</th>
              <th>Shortfall</th>
              <th>Shortfall value (COIN)</th>
            </tr>
            {% for r in summary_rows %}
              <tr>
                <td>{{ r.token }}</td>
                <td>{{ "%.6f"|format(r.needed) }}</td>
                <td>{{ "%.6f"|format(r.have) }}</td>
                <td>{{ "%.6f"|format(r.shortfall) }}</td>
                <td>{{ "%.6f"|format(r.shortfall_coin) }}</td>
              </tr>
            {% endfor %}
          </table>
        {% else %}
          <p class="subtle">No upgrade requirements (empty layout).</p>
        {% endif %}
      </div>
      <div class="card" style="margin-top:10px;">
        <h2>Share / export summary</h2>
        <p class="subtle">
          Copy this text into Discord, notes, or wherever you want to share your flex setup.
        </p>
        <textarea
          readonly
          rows="10"
          style="width:100%;font-family:monospace;font-size:12px;"
        >{{ flex_share_text }}</textarea>
      </div>


      <div class="card" style="margin-top:10px;">
        <h2>Other affordable candidates (per-factory)</h2>
        {% if candidates %}
          <table>
            <tr>
              <th>Factory</th>
              <th>Level</th>
              <th>Profit / hr (COIN)</th>
              <th>Profit / craft (COIN)</th>
              <th>Upgrade shortfall for 1 factory (COIN)</th>
            </tr>
            {% for r in candidates[:40] %}
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
                <td>{{ "%.6f"|format(r.upgrade_shortfall_coin_one) }}</td>
              </tr>
            {% endfor %}
          </table>
        {% else %}
          <p class="subtle">
            No other factories are individually affordable given your upgrade budget.
          </p>
        {% endif %}
      </div>
    </div>
    """

    html = render_template_string(
        BASE_TEMPLATE,
        content=render_template_string(
            content,
            error=error,
            inventory_rows=inventory_rows,
            bands=bands,
            candidates=candidates,
            yield_pct=yield_pct,
            speed_factor=speed_factor,
            workers=workers,
            upgrade_budget_coin=upgrade_budget_coin,
            total_coin_hour=total_coin_hour,
            total_usd_hour=total_usd_hour,
            combined_speed=combined_speed,
            coin_usd=coin_usd,
            summary_rows=summary_rows,
            total_shortfall_coin_layout=total_shortfall_coin_layout,
            priority_rows=priority_rows,
            sim_tokens=sim_tokens,
            sim_token=sim_token,
            sim_amount=sim_amount,
            flex_share_text=flex_share_text,


        ),
        active_page="flex",
        has_uid=has_uid_flag(),
    )
    return html

# -------- Mastery & Workshop overview (CraftWorld.tips-style) --------

@app.route("/mastery")
def mastery_view():
    """
    Read your account proficiencies (mastery) + workshop levels via GraphQL
    and show a combined table, similar to craftworld.tips.
    Handles unauthenticated / missing JWT with a friendly message.
    """
    error = None
    rows: List[dict] = []

    try:
        profs = fetch_proficiencies()       # { "MUD": {"collectedAmount": ..., "claimedLevel": ...}, ... }
        ws_levels = fetch_workshop_levels() # { "MUD": 2, "CLAY": 5, ... }

        symbols = sorted(set(list(profs.keys()) + list(ws_levels.keys())))

        for sym in symbols:
            p = profs.get(sym, {})
            collected = float(p.get("collectedAmount") or 0.0)
            mastery = int(p.get("claimedLevel") or 0)
            workshop = int(ws_levels.get(sym, 0))

            rows.append(
                {
                    "symbol": sym,
                    "collected": collected,
                    "mastery": mastery,
                    "workshop": workshop,
                }
            )

    except Exception as e:
        msg = str(e)
        # Friendly handling for unauthenticated / no JWT cases
        if "UNAUTHENTICATED" in msg.upper() or "JWT" in msg.upper():
            error = (
                "This page needs a valid Craft World login / JWT to load your "
                "mastery and workshop levels.<br>"
                "Go to the <strong>Login</strong> tab, log in, then come back here."
            )
        else:
            error = f"Error fetching mastery/workshop data: {msg}"

    content = """
    <div class="card">
      <h1>Mastery & Workshop</h1>
      <p class="subtle">
        Data is pulled live from Craft World's GraphQL API using your JWT:
        <code>account.proficiencies</code> and <code>account.workshop</code>.
        This matches the core information shown on <strong>craftworld.tips</strong>.
      </p>

      {% if error %}
        <div class="error" style="white-space:normal;">{{ error|safe }}</div>
        <p class="subtle" style="margin-top:8px;">
          If you just logged in, try refreshing this page.
        </p>
      {% else %}
        <div style="overflow-x:auto; margin-top: 10px;">
          <table>
            <tr>
              <th>Token</th>
              <th>Collected</th>
              <th>Mastery Lvl</th>
              <th>Workshop Lvl</th>
            </tr>
            {% for r in rows %}
              {% set mastery_max = (r.mastery >= 10) %}
              {% set ws_max = (r.workshop >= 10) %}
              <tr>
                <td>{{ r.symbol }}</td>
                <td>{{ "{:,.0f}".format(r.collected) }}</td>
                <td>
                  <span class="{{ 'pill' if mastery_max else 'pill-soft' }}">
                    L{{ r.mastery }}
                  </span>
                </td>
                <td>
                  <span class="{{ 'pill' if ws_max else 'pill-soft' }}">
                    L{{ r.workshop }}
                  </span>
                </td>
              </tr>
            {% endfor %}
          </table>
        </div>
      {% endif %}
    </div>
    """

    html = render_template_string(
        BASE_TEMPLATE,
        content=render_template_string(content, rows=rows, error=error),
        active_page="mastery",
        has_uid=has_uid_flag(),
    )
    return html

# -------- Inventory overview (craftworld.tips-style) --------

@app.route("/inventory")
def inventory_view():
    """
    Full inventory page:
    - Shows all tokens from account.resources
    - Uses live prices in COIN + USD
    - Sorts by total COIN value (highest first)
    - Includes a Discord-ready summary block
    """
    error = None
    uid = session.get("voya_uid")
    if not uid:
        content = """
        <div class="card">
          <h1>Inventory</h1>
          <p class="subtle">
            Enter your Account UID on the <strong>Overview</strong> tab to unlock
            the Inventory view.
          </p>
        </div>
        """
        html = render_template_string(
            BASE_TEMPLATE,
            content=content,
            active_page="inventory",
            has_uid=has_uid_flag(),
        )
        return html

    prices = {}
    coin_usd = 0.0
    inventory_rows: List[dict] = []
    total_coin_value = 0.0
    total_usd_value = 0.0

    try:
        # Prices
        prices = fetch_live_prices_in_coin()
        coin_usd = float(prices.get("_COIN_USD", 0.0))

        # Account data
        cw = fetch_craftworld(uid)
        resources = attr_or_key(cw, "resources", []) or []

        for r in resources:
            sym = str(attr_or_key(r, "symbol", "")).upper()
            if not sym:
                continue
            try:
                amt = float(attr_or_key(r, "amount", 0) or 0.0)
            except Exception:
                amt = 0.0

            price_coin = float(prices.get(sym, 0.0))
            value_coin = amt * price_coin
            value_usd = value_coin * coin_usd if coin_usd else 0.0

            total_coin_value += value_coin
            total_usd_value += value_usd

            inventory_rows.append(
                {
                    "token": sym,
                    "amount": amt,
                    "price_coin": price_coin,
                    "value_coin": value_coin,
                    "value_usd": value_usd,
                }
            )

        # Sort by COIN value (highest first)
        inventory_rows.sort(key=lambda row: row["value_coin"], reverse=True)

    except Exception as e:
        error = f"Error fetching inventory: {e}"

    # Build a Discord-style summary string
    top_rows = inventory_rows[:5]
    summary_lines = []
    summary_lines.append(
        f"Inventory value: {total_coin_value:.4f} COIN (~${total_usd_value:.2f} USD at {coin_usd:.6f} USD/COIN)"
    )
    if top_rows:
        summary_lines.append("Top holdings:")
        for r in top_rows:
            summary_lines.append(
                f"- {r['token']}: {r['amount']:.0f} (≈ {r['value_coin']:.4f} COIN)"
            )
    summary_text = "\n".join(summary_lines)

    content = """
    <div class="card">
      <h1>Inventory</h1>
      <p class="subtle">
        Live snapshot of your resources from <code>account.resources</code>, valued using live prices
        (same source as Dashboard). This mirrors the inventory view concept from <strong>craftworld.tips</strong>.
      </p>

      <div style="display:flex; flex-wrap:wrap; gap:16px;">
        <div>
          <strong>UID:</strong><br>
          {{ uid }}
        </div>
        <div>
          <strong>COIN → USD:</strong><br>
          {{ '%.6f'|format(coin_usd) }} USD / COIN
        </div>
        <div>
          <strong>Total Inventory Value:</strong><br>
          {{ '%.6f'|format(total_coin_value) }} COIN<br>
          {{ '%.2f'|format(total_usd_value) }} USD
        </div>
      </div>

      {% if error %}
        <div class="error" style="margin-top:10px; white-space:pre-wrap;">{{ error }}</div>
      {% endif %}
    </div>

    <div class="card">
      <h2>📤 Copy summary for Discord</h2>
      <p class="subtle">
        Quick text summary you can paste in chat or your notes.
      </p>
      <textarea readonly
                style="width:100%;min-height:120px;font-family:monospace;font-size:12px;"
                onclick="this.select();">
{{ summary_text }}
      </textarea>
    </div>

    <div class="card">
      <h2>📦 Inventory Details</h2>
      {% if inventory_rows %}
        <div style="overflow-x:auto;">
          <table>
            <tr>
              <th>Token</th>
              <th>Amount</th>
              <th>Price (COIN)</th>
              <th>Value (COIN)</th>
              <th>Value (USD)</th>
            </tr>
            {% for r in inventory_rows %}
              <tr>
                <td>
                  <a href="{{ url_for('resource_view', token=r.token) }}">{{ r.token }}</a>
                </td>
                <td>{{ "{:,.6f}".format(r.amount) }}</td>
                <td>{{ "%.8f"|format(r.price_coin) }}</td>
                <td>{{ "%.6f"|format(r.value_coin) }}</td>
                <td>{{ "%.4f"|format(r.value_usd) }}</td>
              </tr>
            {% endfor %}
          </table>
        </div>
      {% else %}
        <p class="subtle">No resources found for this account.</p>
      {% endif %}
    </div>
    """

    html = render_template_string(
        BASE_TEMPLATE,
        content=render_template_string(
            content,
            uid=uid,
            coin_usd=coin_usd,
            inventory_rows=inventory_rows,
            total_coin_value=total_coin_value,
            total_usd_value=total_usd_value,
            summary_text=summary_text,
            error=error,
        ),
        active_page="inventory",
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
<div class=\"card\">
  <h1>Masterpieces</h1>

  {% if error %}
    <div class=\"error\">{{ error }}</div>
  {% endif %}

  <div class=\"tabs\">
    <a href=\"#overview\">Current MPs</a>
    <a href=\"#rewards\">Rewards &amp; Totals</a>
    <a href=\"#history\">History</a>
    <a href=\"#planner\">Donation Planner</a>
  </div>

  <!-- ================= OVERVIEW / CURRENT ================= -->
  <div id=\"overview\">
    <h2>Current Masterpieces</h2>

    <div style=\"display:flex; gap:1rem; flex-wrap:wrap; margin-bottom:1rem;\">
      <!-- General MP card -->
      <div style=\"flex:1 1 260px; border:1px solid #444; border-radius:8px; padding:0.75rem;\">
        <h3>General Masterpiece</h3>
        {% if general_snapshot %}
          <p>
            <strong>{{ general_snapshot.mp.name }}</strong>
            (ID {{ general_snapshot.mp.id }})
          </p>
          <p>
            Rank: <strong>#{{ general_snapshot.position }}</strong><br>
            Points:
            <strong>{{ \"{:,.0f}\".format(general_snapshot.points or 0) }}</strong><br>
            {% if general_snapshot.tier %}
              Completion tier: <strong>{{ general_snapshot.tier }}</strong><br>
            {% else %}
              Completion tier: <strong>Below Tier 1</strong><br>
            {% endif %}
            {% if general_snapshot.leaderboard_rewards %}
              Bracket rewards: {{ general_snapshot.leaderboard_rewards }}
            {% endif %}
          </p>
        {% elif current_mp and not current_mp.eventId %}
          <p>
            <strong>{{ current_mp.name }}</strong> (ID {{ current_mp.id }})<br>
        <span class="hint">
          Enter your name or Account ID in the History tab to see your personal snapshot.
        </span>

          </p>
        {% else %}
          <p>No active general masterpiece found.</p>
        {% endif %}
      </div>

      <!-- Event MP card -->
      <div style=\"flex:1 1 260px; border:1px solid #444; border-radius:8px; padding:0.75rem;\">
        <h3>Event Masterpiece</h3>
        {% if event_snapshot %}
          <p>
            <strong>{{ event_snapshot.mp.name }}</strong>
            (ID {{ event_snapshot.mp.id }})
          </p>
          <p>
            Rank: <strong>#{{ event_snapshot.position }}</strong><br>
            Points:
            <strong>{{ \"{:,.0f}\".format(event_snapshot.points or 0) }}</strong><br>
            {% if event_snapshot.tier %}
              Completion tier: <strong>{{ event_snapshot.tier }}</strong><br>
            {% else %}
              Completion tier: <strong>Below Tier 1</strong><br>
            {% endif %}
            {% if event_snapshot.leaderboard_rewards %}
              Bracket rewards: {{ event_snapshot.leaderboard_rewards }}
            {% endif %}
          </p>
        {% else %}
          <p>No active event masterpiece found.</p>
        {% endif %}
      </div>
    </div>

    <h2>Live leaderboard (Top {{ top_n }})</h2>
    {% if current_mp %}
      <p>
        Showing <strong>{{ current_mp.name }}</strong>
        (ID {{ current_mp.id }}) leaderboard.
      </p>
      {{ current_mp_top50|safe }}

      {% if current_gap %}
        <div style=\"margin-top:0.5rem; font-size:0.9rem;\">
          <strong>Your gap:</strong>
          You are currently <strong>#{{ current_gap.position }}</strong>
          with
          <strong>{{ \"{:,.0f}\".format(current_gap.points or 0) }}</strong>
          points.
          {% if current_gap.above_name %}
            <br>
            Need
            <strong>{{ \"{:,.0f}\".format(current_gap.gap_up or 0) }}</strong>
            points to pass {{ current_gap.above_name }}
            (#{{ current_gap.above_pos }}).
          {% endif %}
          {% if current_gap.below_name %}
            <br>
            You are ahead of {{ current_gap.below_name }}
            (#{{ current_gap.below_pos }}) by
            <strong>{{ \"{:,.0f}\".format(current_gap.gap_down or 0) }}</strong>
            points.
          {% endif %}
        </div>
      {% else %}
        <p class="hint">
          To see your personal gap, enter your in-game name or Account ID
          in the History tab and reload.
        </p>
      {% endif %}
    {% else %}
      <p>No current masterpiece leaderboard available.</p>
    {% endif %}
  </div>

  <!-- ================= REWARDS & TOTALS ================= -->
  <div id=\"rewards\" style=\"margin-top:1.5rem;\">
    <h2>Rewards &amp; Totals</h2>

    {% if src_mp %}
      <p>
        Showing rewards for
        <strong>{{ src_mp.name }}</strong>
        (ID {{ src_mp.id }}).
      </p>
    {% else %}
      <p class=\"hint\">
        No masterpiece selected yet. Use the History selector or Donation Planner
        to choose one.
      </p>
    {% endif %}

    <!-- Your snapshot on selected MP (if any) -->
    {% if selected_reward_snapshot %}
      <div style=\"border:1px solid #444; border-radius:8px; padding:0.75rem; margin-bottom:1rem;\">
        <h3>Your position on this masterpiece</h3>
        <p>
          Rank: <strong>#{{ selected_reward_snapshot.position }}</strong><br>
          Points:
          <strong>{{ \"{:,.0f}\".format(selected_reward_snapshot.points or 0) }}</strong><br>
          {% if selected_reward_snapshot.tier %}
            Completion tier:
            <strong>{{ selected_reward_snapshot.tier }}</strong><br>
          {% endif %}
          {% if selected_reward_snapshot.leaderboard_rewards %}
            Rank rewards: {{ selected_reward_snapshot.leaderboard_rewards }}
          {% endif %}
        </p>
      </div>
    {% endif %}

    <!-- Tier ladder table -->
    <h3>Tier ladder</h3>
    <table class=\"table\">
      <thead>
        <tr>
          <th>Tier</th>
          <th>Required MP</th>
          <th>MP delta</th>
        </tr>
      </thead>
      <tbody>
        {% for row in tier_rows %}
          <tr>
            <td>Tier {{ row.tier }}</td>
            <td>{{ \"{:,.0f}\".format(row.required) }}</td>
            <td>{{ \"{:,.0f}\".format(row.delta) }}</td>
          </tr>
        {% endfor %}
      </tbody>
    </table>

    <!-- Reward stages from rewardStages -->
    <h3 style=\"margin-top:1rem;\">Tier rewards (per stage)</h3>
    {% if reward_tier_rows %}
      <table class=\"table\">
        <thead>
          <tr>
            <th>Tier</th>
            <th>Required MP</th>
            <th>Base rewards</th>
            <th>RawrPass rewards</th>
          </tr>
        </thead>
        <tbody>
          {% for row in reward_tier_rows %}
            <tr>
              <td>{{ row.tier }}</td>
              <td>{{ row.required }}</td>
              <td>{{ row.rewards_text }}</td>
              <td>{{ row.battlepass_text }}</td>
            </tr>
          {% endfor %}
        </tbody>
      </table>
    {% else %}
      <p class=\"hint\">
        This masterpiece does not expose detailed rewardStages via the API.
        Check in-game for full details.
      </p>
    {% endif %}

    <!-- Totals (base / BP / combined) -->
    <h3 style=\"margin-top:1rem;\">Total resource rewards</h3>

    <div style=\"display:flex; gap:1rem; flex-wrap:wrap;\">
      <div style=\"flex:1 1 240px;\">
        <h4>Base track only</h4>
        {% if tier_base_totals_list %}
          <table class=\"table\">
            <thead>
              <tr>
                <th>Token</th>
                <th>Amount</th>
                <th>Value (COIN)</th>
                <th>Value (USD)</th>
              </tr>
            </thead>
            <tbody>
              {% for row in tier_base_totals_list %}
                <tr>
                  <td>{{ row.symbol }}</td>
                  <td>{{ \"{:,.0f}\".format(row.amount) }}</td>
                  <td>{{ \"{:,.2f}\".format(row.coin_value) }}</td>
                  <td>{{ \"{:,.2f}\".format(row.usd_value) }}</td>
                </tr>
              {% endfor %}
            </tbody>
          </table>
        {% else %}
          <p class=\"hint\">No numeric base rewards detected.</p>
        {% endif %}
      </div>

      <div style=\"flex:1 1 240px;\">
        <h4>RawrPass track only</h4>
        {% if tier_bp_totals_list %}
          <table class=\"table\">
            <thead>
              <tr>
                <th>Token</th>
                <th>Amount</th>
                <th>Value (COIN)</th>
                <th>Value (USD)</th>
              </tr>
            </thead>
            <tbody>
              {% for row in tier_bp_totals_list %}
                <tr>
                  <td>{{ row.symbol }}</td>
                  <td>{{ \"{:,.0f}\".format(row.amount) }}</td>
                  <td>{{ \"{:,.2f}\".format(row.coin_value) }}</td>
                  <td>{{ \"{:,.2f}\".format(row.usd_value) }}</td>
                </tr>
              {% endfor %}
            </tbody>
          </table>
        {% else %}
          <p class=\"hint\">No numeric RawrPass rewards detected.</p>
        {% endif %}
      </div>

      <div style=\"flex:1 1 240px;\">
        <h4>Combined (Base + RawrPass)</h4>
        {% if tier_combined_totals_list %}
          <table class=\"table\">
            <thead>
              <tr>
                <th>Token</th>
                <th>Amount</th>
                <th>Value (COIN)</th>
                <th>Value (USD)</th>
              </tr>
            </thead>
            <tbody>
              {% for row in tier_combined_totals_list %}
                <tr>
                  <td>{{ row.symbol }}</td>
                  <td>{{ \"{:,.0f}\".format(row.amount) }}</td>
                  <td>{{ \"{:,.2f}\".format(row.coin_value) }}</td>
                  <td>{{ \"{:,.2f}\".format(row.usd_value) }}</td>
                </tr>
              {% endfor %}
            </tbody>
          </table>
          <p>
            <strong>Total value:</strong>
            {{ \"{:,.2f}\".format(tier_combined_total_coin or 0) }} COIN
            (~{{ \"{:,.2f}\".format(tier_combined_total_usd or 0) }} USD,
            using COIN ≈ {{ \"{:,.3f}\".format(coin_usd or 0) }} USD).
          </p>
        {% else %}
          <p class=\"hint\">No combined rewards detected.</p>
        {% endif %}
      </div>
    </div>

    <!-- Rank-based grand totals if available -->
    {% if my_rank_totals_list %}
      <h3 style=\"margin-top:1.5rem;\">Your total rewards at current rank</h3>
      <table class=\"table\">
        <thead>
          <tr>
            <th>Token</th>
            <th>Amount</th>
            <th>Value (COIN)</th>
            <th>Value (USD)</th>
          </tr>
        </thead>
        <tbody>
          {% for row in my_rank_totals_list %}
            <tr>
              <td>{{ row.symbol }}</td>
              <td>{{ \"{:,.0f}\".format(row.amount) }}</td>
              <td>{{ \"{:,.2f}\".format(row.coin_value) }}</td>
              <td>{{ \"{:,.2f}\".format(row.usd_value) }}</td>
            </tr>
          {% endfor %}
        </tbody>
      </table>
    {% endif %}

    {% if grand_totals_list %}
      <h3 style=\"margin-top:1.5rem;\">Grand totals (all tiers + rank rewards)</h3>
      <table class=\"table\">
        <thead>
          <tr>
            <th>Token</th>
            <th>Amount</th>
            <th>Value (COIN)</th>
            <th>Value (USD)</th>
          </tr>
        </thead>
        <tbody>
          {% for row in grand_totals_list %}
            <tr>
              <td>{{ row.symbol }}</td>
              <td>{{ \"{:,.0f}\".format(row.amount) }}</td>
              <td>{{ \"{:,.2f}\".format(row.coin_value) }}</td>
              <td>{{ \"{:,.2f}\".format(row.usd_value) }}</td>
            </tr>
          {% endfor %}
        </tbody>
      </table>
      <p>
        <strong>Grand total:</strong>
        {{ \"{:,.2f}\".format(grand_total_coin or 0) }} COIN
        (~{{ \"{:,.2f}\".format(grand_total_usd or 0) }} USD).
      </p>
    {% endif %}
  </div>

  <!-- ================= HISTORY ================= -->
  <div id=\"history\" style=\"margin-top:1.5rem;\">
    <h2>History &amp; Selector</h2>

    <form method=\"get\" style=\"margin-bottom:1rem;\">
      <label>
        Masterpiece:
        <select name=\"mp_view_id\">
          {% for opt in history_mp_options %}
            <option value=\"{{ opt.id }}\"
              {% if selected_mp and selected_mp.id|string == opt.id|string %}selected{% endif %}>
              {% if opt.name %}
                {{ opt.name }} (ID {{ opt.id }})
              {% elif opt.addressable_label %}
                {{ opt.addressable_label }} (ID {{ opt.id }})
              {% else %}
                MP #{{ opt.id }}
              {% endif %}
            </option>
          {% endfor %}
        </select>
      </label>

      <label style=\"margin-left:0.5rem;\">
        Highlight (name or Voya ID):
        <input type=\"text\" name=\"highlight\" value=\"{{ highlight_query }}\" placeholder=\"Your name or Voya ID\">
      </label>

      <label style=\"margin-left:0.5rem;\">
        Leaderboard size:
        <select name=\"top_n\">
          {% for n in top_n_options %}
            <option value=\"{{ n }}\" {% if n == top_n %}selected{% endif %}>
              Top {{ n }}
            </option>
          {% endfor %}
        </select>
      </label>

      <label style=\"margin-left:0.5rem;\">
        RawrPass:
        <input type=\"checkbox\" name=\"has_battle_pass\"
          {% if has_battle_pass %}checked{% endif %}>
      </label>

      <button type=\"submit\" style=\"margin-left:0.5rem;\">Load</button>
    </form>

    {% if selected_mp %}
      <h3>{{ selected_mp.name or (\"MP #\" ~ selected_mp.id) }} (ID {{ selected_mp.id }})</h3>
      {{ selected_mp_top50|safe }}

      {% if selected_gap %}
        <div style=\"margin-top:0.5rem; font-size:0.9rem;\">
          <strong>Your gap on this MP:</strong>
          You are <strong>#{{ selected_gap.position }}</strong>
          with
          <strong>{{ \"{:,.0f}\".format(selected_gap.points or 0) }}</strong>
          points.
          {% if selected_gap.above_name %}
            <br>
            Need
            <strong>{{ \"{:,.0f}\".format(selected_gap.gap_up or 0) }}</strong>
            points to pass {{ selected_gap.above_name }}
            (#{{ selected_gap.above_pos }}).
          {% endif %}
          {% if selected_gap.below_name %}
            <br>
            You are ahead of {{ selected_gap.below_name }}
            (#{{ selected_gap.below_pos }}) by
            <strong>{{ \"{:,.0f}\".format(selected_gap.gap_down or 0) }}</strong>
            points.
          {% endif %}
        </div>
      {% endif %}
    {% else %}
      <p>No masterpiece selected.</p>
    {% endif %}
  </div>

  <!-- ================= DONATION PLANNER ================= -->
  <div id=\"planner\" style=\"margin-top:1.5rem;\">
    <h2>Donation Planner</h2>

    <form method=\"post\">
      <input type=\"hidden\" name=\"calc_state\" value=\"{{ calc_state_json|e }}\">

      <div style=\"display:flex; flex-wrap:wrap; gap:1rem; margin-bottom:1rem;\">
        <div>
          <label>
            Masterpiece:
            <select name=\"planner_mp_id\">
              {% for opt in planner_mp_options %}
                <option value=\"{{ opt.id }}\"
                  {% if planner_mp and planner_mp.id|string == opt.id|string %}selected{% endif %}>
                  {% if opt.name %}
                    {{ opt.name }} (ID {{ opt.id }})
                  {% elif opt.addressable_label %}
                    {{ opt.addressable_label }} (ID {{ opt.id }})
                  {% else %}
                    MP #{{ opt.id }}
                  {% endif %}
                </option>
              {% endfor %}
            </select>
          </label>
        </div>

        <div>
          <label>
            Token:
            <select name=\"calc_token\">
              {% for sym in planner_tokens %}
                <option value=\"{{ sym }}\">{{ sym }}</option>
              {% endfor %}
            </select>
          </label>
        </div>

        <div>
          <label>
            Amount:
            <input type=\"number\" step=\"0.0001\" min=\"0\" name=\"calc_amount\">
          </label>
        </div>

        <div style=\"align-self:flex-end; display:flex; gap:0.5rem;\">
          <button type=\"submit\" name=\"calc_action\" value=\"add\">Add</button>
          <button type=\"submit\" name=\"calc_action\" value=\"clear\">Clear</button>
        </div>
      </div>

      {% if calc_resources %}
        <h3>Your bundle</h3>
        <table class=\"table\">
          <thead>
            <tr>
              <th>Token</th>
              <th>Amount</th>
              <th>MP points</th>
              <th>XP</th>
              <th>Battery</th>
            </tr>
          </thead>
          <tbody>
            {% for row in calc_resources %}
              <tr>
                <td>{{ row.token }}</td>
                <td>{{ row.amount }}</td>
                <td>{{ row.points_str or \"—\" }}</td>
                <td>{{ row.xp_str or \"—\" }}</td>
                <td>{{ row.battery_str or \"—\" }}</td>
              </tr>
            {% endfor %}
          </tbody>
        </table>
      {% endif %}

      {% if calc_result %}
        <h3>Summary</h3>
        <p>
          Total MP:
          <strong>{{ calc_result.total_points_str }}</strong><br>
          Total XP:
          <strong>{{ calc_result.total_xp_str }}</strong><br>
          Required power:
          <strong>{{ calc_result.total_power_str }}</strong><br>
          COIN cost:
          <strong>{{ calc_result.total_cost_str }}</strong><br>
          Current tier:
          <strong>Tier {{ calc_result.tier }}</strong>
          {% if calc_result.next_tier_index %}
            <br>
            To Tier {{ calc_result.next_tier_index }}:
            need
            <strong>{{ calc_result.points_to_next_str }}</strong>
            MP
            ({{ calc_result.progress_to_next_pct }}% of the way).
          {% endif %}
        </p>
      {% else %}
        <p class=\"hint\">
          Build a bundle and click \"Add\" to see points, XP, battery, and COIN cost.
        </p>
      {% endif %}
    </form>
  </div>
</div>
"""
# ================= END MASTERPIECES TEMPLATE ==================

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
    
    # Live prices for reward valuation
    prices: Dict[str, float] = {}
    coin_usd: float = 0.0
    try:
        prices = fetch_live_prices_in_coin()
        coin_usd = float(prices.get("_COIN_USD", 0.0) or 0.0)
    except Exception:
        prices = {}
        coin_usd = 0.0


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

    # ---- Battle pass toggle (RawrPass) ----
    # Start from whatever we remembered last time:
    has_battle_pass = bool(session.get("mp_has_battle_pass", False))

    # If this is a POST from the Rewards tab's RawrPass form,
    # treat the checkbox as authoritative:
    if request.method == "POST" and (request.form.get("tab") == "rewards"):
        # In HTML, an unchecked checkbox is *not* sent at all.
        # So:
        #   - present => checked => True
        #   - missing => unchecked => False
        has_battle_pass = "has_battle_pass" in request.form
    else:
        # Optional query-string override for shareable links:
        #   ?has_battle_pass=1   or   ?has_battle_pass=0
        bp_flag = (request.args.get("has_battle_pass") or "").strip().lower()
        if bp_flag in ("1", "true", "on", "yes", "y", "checked"):
            has_battle_pass = True
        elif bp_flag in ("0", "false", "off", "no"):
            has_battle_pass = False

    # Persist per session so it sticks when you reload/switch tabs
    session["mp_has_battle_pass"] = has_battle_pass


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
    src_mp: Optional[Dict[str, Any]] = None


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
    # Snapshot of your current tier / rewards on the selected masterpiece (for Rewards tab)
    selected_reward_snapshot: Optional[Dict[str, Any]] = None
    if highlight_query and selected_mp and selected_mp_top50:
        try:
            selected_reward_snapshot = _build_reward_snapshot_for_mp(
                selected_mp,
                selected_mp_top50,
                highlight_query,
            )
        except Exception:
            selected_reward_snapshot = None





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

    # Totals across all tiers (cumulative)
    tier_base_totals: Dict[str, float] = {}
    tier_bp_totals: Dict[str, float] = {}

    # Use the selected MP for History first, then planner, then current
    src_mp = selected_mp or planner_mp or current_mp

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
                or st.get("requiredMasterpiecePoints")
            )

            # --- base (free) rewards ---
            rewards_list = st.get("rewards") or st.get("items") or []
            base_parts: list[str] = []

            if isinstance(rewards_list, list):
                for rw in rewards_list:
                    if not isinstance(rw, dict):
                        continue
                    amount = rw.get("amount") or rw.get("quantity")
                    token = rw.get("token") or rw.get("symbol") or rw.get("resource")
                    rtype = rw.get("type") or rw.get("rewardType") or rw.get("__typename")

                    # Aggregate numeric resource rewards for totals
                    try:
                        amt_val = float(amount or 0)
                    except (TypeError, ValueError):
                        amt_val = 0.0

                    if token and amt_val > 0 and (not rtype or str(rtype).lower() == "resource"):
                        t_sym = str(token).upper()
                        tier_base_totals[t_sym] = tier_base_totals.get(t_sym, 0.0) + amt_val

                    # Text label for the table
                    label_bits: list[str] = []
                    if amount not in (None, "", 0):
                        label_bits.append(str(amount))
                    if token:
                        label_bits.append(str(token))
                    elif rtype:
                        label_bits.append(str(rtype))

                    label = " ".join(label_bits).strip()
                    if label:
                        base_parts.append(label)

            # --- RawrPass / battle pass rewards ---
            bp_list = st.get("battlePassRewards") or []
            bp_parts: list[str] = []

            if isinstance(bp_list, list):
                for rw in bp_list:
                    if not isinstance(rw, dict):
                        continue
                    amount = rw.get("amount") or rw.get("quantity")
                    token = rw.get("token") or rw.get("symbol") or rw.get("resource")
                    rtype = rw.get("type") or rw.get("rewardType") or rw.get("__typename")

                    # Aggregate numeric resource rewards for RawrPass totals
                    try:
                        amt_val = float(amount or 0)
                    except (TypeError, ValueError):
                        amt_val = 0.0

                    if token and amt_val > 0 and (not rtype or str(rtype).lower() == "resource"):
                        t_sym = str(token).upper()
                        tier_bp_totals[t_sym] = tier_bp_totals.get(t_sym, 0.0) + amt_val

                    # Text label for the table
                    label_bits: list[str] = []
                    if amount not in (None, "", 0):
                        label_bits.append(str(amount))
                    if token:
                        label_bits.append(str(token))
                    elif rtype:
                        label_bits.append(str(rtype))

                    label = " ".join(label_bits).strip()
                    if label:
                        bp_parts.append(label)

            base_text = ", ".join(base_parts) if base_parts else ""
            bp_text = ", ".join(bp_parts) if bp_parts else ""

            if not base_text and not bp_text:
                base_text = "See in-game rewards"

            reward_tier_rows.append(
                {
                    "tier": tier_num,
                    "required": required,
                    "rewards_text": base_text,
                    "battlepass_text": bp_text,
                }
            )

    # Turn totals into lists with value in COIN / USD
    def _totals_to_rows(totals: Dict[str, float]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for sym, amt in sorted(totals.items()):
            price_coin = float(prices.get(sym, 0.0) or 0.0)
            coin_value = amt * price_coin
            usd_value = coin_value * coin_usd if coin_usd else 0.0
            rows.append(
                {
                    "symbol": sym,
                    "amount": amt,
                    "coin_value": coin_value,
                    "usd_value": usd_value,
                }
            )
        return rows

    # Tier totals as lists
    tier_base_totals_list = _totals_to_rows(tier_base_totals)
    tier_bp_totals_list = _totals_to_rows(tier_bp_totals)

    # Combined totals:
    # - If you DON'T have RawrPass, combined == base-only
    # - If you DO have RawrPass, combined = base + RawrPass
    if has_battle_pass:
        combined_totals: Dict[str, float] = dict(tier_base_totals)
        for sym, amt in tier_bp_totals.items():
            combined_totals[sym] = combined_totals.get(sym, 0.0) + amt
    else:
        combined_totals = dict(tier_base_totals)

    tier_combined_totals_list = _totals_to_rows(combined_totals)
    tier_combined_total_coin = sum(r["coin_value"] for r in tier_combined_totals_list)
    tier_combined_total_usd = tier_combined_total_coin * coin_usd if coin_usd else 0.0

    # ---------- Leaderboard placement rewards (leaderboardRewards) ----------
    leaderboard_reward_rows: List[Dict[str, Any]] = []
    # Per-bracket numeric resource totals: [{from_rank, to_rank, totals:{SYM:amount}}]
    leaderboard_bracket_totals: List[Dict[str, Any]] = []

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

            # Rank range for this reward bracket
            from_rank = (
                blk.get("from")
                or blk.get("fromRank")
                or blk.get("minRank")
                or blk.get("top")  # "top" is used for single-rank brackets
            )
            to_rank = (
                blk.get("to")
                or blk.get("toRank")
                or blk.get("maxRank")
            )

            # Normalise to ints when possible for internal use
            from_int: Optional[int] = None
            to_int: Optional[int] = None
            try:
                if from_rank is not None:
                    from_int = int(from_rank)
            except Exception:
                from_int = None
            try:
                if to_rank is not None:
                    to_int = int(to_rank)
            except Exception:
                to_int = from_int

            totals_for_blk: Dict[str, float] = {}
            rewards_list = blk.get("rewards") or blk.get("items") or []
            reward_parts: List[str] = []

            if isinstance(rewards_list, list):
                for rw in rewards_list:
                    if not isinstance(rw, dict):
                        continue
                    amount = rw.get("amount") or rw.get("quantity")
                    token = rw.get("token") or rw.get("symbol") or rw.get("resource")
                    rtype = rw.get("type") or rw.get("rewardType") or rw.get("__typename")

                    # Aggregate numeric *resource* rewards for this bracket
                    try:
                        amt_val = float(amount or 0)
                    except (TypeError, ValueError):
                        amt_val = 0.0

                    if token and amt_val > 0 and (not rtype or str(rtype).lower() == "resource"):
                        sym = str(token).upper()
                        totals_for_blk[sym] = totals_for_blk.get(sym, 0.0) + amt_val

                    # Text label for the table
                    label_bits: List[str] = []
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
                    "from_rank": from_int or from_rank,
                    "to_rank": to_int or to_rank,
                    "rewards_text": ", ".join(reward_parts),
                }
            )

            if totals_for_blk:
                leaderboard_bracket_totals.append(
                    {
                        "from_rank": from_int or from_rank,
                        "to_rank": to_int or to_rank,
                        "totals": totals_for_blk,
                    }
                )

    # ---------- My rank rewards (from leaderboard bracket) ----------
    my_rank_totals: Dict[str, float] = {}
    my_rank_totals_list: List[Dict[str, Any]] = []
    grand_totals_list: List[Dict[str, Any]] = []
    grand_total_coin = 0.0
    grand_total_usd = 0.0

    my_rank_int: Optional[int] = None
    if selected_reward_snapshot and selected_reward_snapshot.get("position") is not None:
        try:
            my_rank_int = int(str(selected_reward_snapshot["position"]).strip())
        except Exception:
            my_rank_int = None

    # Cumulative leaderboard rewards:
    # sum all brackets whose threshold rank is >= my rank
    # (e.g. if you're rank 5, you get #5, #6, #7, ..., #1000)
    if my_rank_int is not None and leaderboard_bracket_totals:
        for b in leaderboard_bracket_totals:
            fr = b.get("from_rank")
            to = b.get("to_rank")

            # Choose a "threshold" rank for this bracket: the higher of from/to
            thr: Optional[int] = None
            try:
                if fr is not None:
                    thr = int(fr)
            except Exception:
                thr = None

            try:
                if to is not None:
                    to_i = int(to)
                    if thr is None or to_i > thr:
                        thr = to_i
            except Exception:
                # ignore bad to_rank, keep whatever thr we had
                pass

            if thr is None:
                continue

            # If your rank is better or equal than this threshold,
            # you earn this bracket's bag as well.
            if thr >= my_rank_int:
                blk_totals = b.get("totals") or {}
                for sym, amt in blk_totals.items():
                    try:
                        val = float(amt or 0.0)
                    except (TypeError, ValueError):
                        val = 0.0
                    if val <= 0:
                        continue
                    sym_u = str(sym).upper()
                    my_rank_totals[sym_u] = my_rank_totals.get(sym_u, 0.0) + val


    if my_rank_totals:
        # Rank-only rewards (for your bracket)
        my_rank_totals_list = _totals_to_rows(my_rank_totals)

        # Grand total = all tier rewards (base + RawrPass) + your rank bracket bag
        combined_plus_rank: Dict[str, float] = dict(combined_totals)
        for sym, amt in my_rank_totals.items():
            combined_plus_rank[sym] = combined_plus_rank.get(sym, 0.0) + amt

        grand_totals_list = _totals_to_rows(combined_plus_rank)
        grand_total_coin = sum(r["coin_value"] for r in grand_totals_list)
        grand_total_usd = grand_total_coin * coin_usd if coin_usd else 0.0


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
        <button type="button" class="mp-tab" data-mp-tab="rewards">
          <span class="icon">🎁</span> Rewards
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
    Base tier rewards are available to all players. If you’ve purchased the RawrPass
    for this Masterpiece, you also get additional rewards on each tier.
  </p>

  <div style="margin-bottom:6px;">
    <label style="font-size:13px; cursor:pointer;">
      <input type="checkbox"
             name="has_battle_pass"
             value="1"
             onchange="this.form.submit()"
             {% if has_battle_pass %}checked{% endif %}>
      I have the RawrPass for this Masterpiece
    </label>
  </div>

  {% if reward_tier_rows %}
    <div class="scroll-x">
      <table class="mp-tier-table">
        <tr>
          <th>Tier</th>
          <th>Required points</th>
          <th>Rewards{% if has_battle_pass %} (base + RawrPass){% endif %}</th>
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
            <td>
              {{ row.rewards_text }}
              {% if has_battle_pass and row.battlepass_text %}
                <br>
                <span class="subtle">+ RawrPass: {{ row.battlepass_text }}</span>
              {% endif %}
            </td>
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
  <td class="subtle">
    {% if name %}
      {{ name }}
      {% if uid %}
        <br>
        <span style="font-size:11px; opacity:0.8;">
          {{ uid }}
        </span>
      {% endif %}
    {% elif uid %}
      {{ uid }}
    {% else %}
      —
    {% endif %}
    {% if is_me %}
      <span class="me-pill">← you</span>
    {% endif %}
  </td>
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

        <!-- 🎁 Rewards overview -->
        <div class="mp-section" data-mp-section="rewards" style="display:none;">
          <div class="section" style="margin-top:4px;">
            <h2>Rewards overview</h2>
            {% if src_mp %}
              <p class="subtle">
                MP {{ src_mp.id }} — {{ src_mp.name or src_mp.addressableLabel or src_mp.type }}<br>
                Tier completion rewards{% if leaderboard_reward_rows %} + leaderboard placement rewards{% endif %}.
              </p>
            {% else %}
              <p class="hint">
                No masterpiece selected yet. Use the History selector or Donation Planner to choose one.
              </p>
            {% endif %}

            <!-- RawrPass toggle on Rewards tab -->
            <form method="post" style="margin-top:4px; margin-bottom:10px;">
              <input type="hidden" name="tab" value="rewards">
              <label style="font-size:13px; cursor:pointer;">
                <input type="checkbox"
                       name="has_battle_pass"
                       value="1"
                       onchange="this.form.submit()"
                       {% if has_battle_pass %}checked{% endif %}>
                I have the RawrPass for this Masterpiece
              </label>
            </form>

            {% if selected_reward_snapshot %}
              <div class="mp-gap-card">
                <div class="mp-gap-title">Your current reward level</div>
                <div class="mp-gap-grid">
                  <div class="mp-gap-block">
                    <div class="mp-gap-label">Leaderboard position</div>
                    <div class="mp-gap-number">
                      #{{ selected_reward_snapshot.position }}
                    </div>
                    <div class="mp-gap-sub">
                      {{ "{:,.0f}".format(selected_reward_snapshot.points or 0) }} points
                    </div>
                  </div>
                  {% if selected_reward_snapshot.tier_index %}
                    <div class="mp-gap-block">
                      <div class="mp-gap-label">Completion tier</div>
                      <div class="mp-gap-number">
                        Tier {{ selected_reward_snapshot.tier_index }}
                      </div>
                      {% if selected_reward_snapshot.tier_min %}
                        <div class="mp-gap-sub">
                          ≥ {{ "{:,.0f}".format(selected_reward_snapshot.tier_min or 0) }} points
                        </div>
                      {% endif %}
                    </div>
                  {% endif %}
                  {% if selected_reward_snapshot.leaderboard_rewards %}
                    <div class="mp-gap-block">
                      <div class="mp-gap-label">Leaderboard rewards</div>
                      <div class="mp-gap-sub">
                        {{ selected_reward_snapshot.leaderboard_rewards }}
                      </div>
                    </div>
                  {% endif %}
                </div>
              </div>
            {% elif highlight_query %}
              <p class="hint">
                We couldn't find <code>{{ highlight_query }}</code> in the visible leaderboard for this masterpiece.
                Make sure you're in the top {{ top_n }} and that the name / UID matches exactly.
              </p>
            {% else %}
              <p class="hint">
                Enter your name or Voya ID in the highlight box at the top of this page to see your own tier highlighted.
              </p>
            {% endif %}

            <div class="two-col" style="margin-top:10px; gap:12px;">
              <div>
                <h3 style="margin-top:0;">Tier rewards</h3>
                {% if reward_tier_rows %}
                  {% set my_tier = selected_reward_snapshot.tier_index if selected_reward_snapshot else None %}
                  <div class="scroll-x">
                    <table class="mp-tier-table">
                      <tr>
                        <th>Tier</th>
                        <th>Required points</th>
                        <th>Rewards{% if has_battle_pass %} (base + RawrPass){% endif %}</th>
                      </tr>
                      {% for row in reward_tier_rows %}
                        {% set tier_num = row.tier or loop.index %}
                        <tr class="{% if my_tier and tier_num == my_tier %}mp-row-me{% endif %}">
                          <td>Tier {{ tier_num }}</td>
                          <td>
                            {% if row.required %}
                              {{ "{:,}".format(row.required) }}
                            {% else %}
                              —
                            {% endif %}
                          </td>
                          <td>
                            {{ row.rewards_text }}
                            {% if has_battle_pass and row.battlepass_text %}
                              <br>
                              <span class="subtle">+ RawrPass: {{ row.battlepass_text }}</span>
                            {% endif %}
                          </td>
                        </tr>
                      {% endfor %}
                    </table>
                  </div>
                {% else %}
                  <p class="hint">
                    No tier reward metadata in the API for this masterpiece yet — check in-game rewards.
                  </p>
                {% endif %}
              </div>
              <div class="section" style="margin-top:8px;">
  <h4 style="margin-top:0;">📦 Total estimated tier rewards (full completion)</h4>
  <p class="subtle">
    Sums all tier rewards for this masterpiece. Values use live market prices
    (<code>fetch_live_prices_in_coin</code>).
  </p>

  {% if tier_base_totals_list or tier_bp_totals_list %}
    <div class="two-col" style="gap:10px;">
      <div>
        <h3 style="margin-top:4px;font-size:14px;">Base rewards</h3>
        {% if tier_base_totals_list %}
          <div class="scroll-x">
            <table>
              <tr>
                <th>Token</th>
                <th style="text-align:right;">Amount</th>
                <th style="text-align:right;">Value (COIN)</th>
                <th style="text-align:right;">Value (USD)</th>
              </tr>
              {% for r in tier_base_totals_list %}
                <tr>
                  <td>{{ r.symbol }}</td>
                  <td style="text-align:right;">{{ "{:,.0f}".format(r.amount) }}</td>
                  <td style="text-align:right;">{{ "{:,.4f}".format(r.coin_value) }}</td>
                  <td style="text-align:right;">
                    {% if coin_usd %}
                      ${{ "{:,.2f}".format(r.usd_value) }}
                    {% else %}
                      —
                    {% endif %}
                  </td>
                </tr>
              {% endfor %}
            </table>
          </div>
        {% else %}
          <p class="hint">No numeric base resource rewards found.</p>
        {% endif %}
      </div>

      <div>
        <h3 style="margin-top:4px;font-size:14px;">RawrPass rewards</h3>
        {% if tier_bp_totals_list %}
          <div class="scroll-x">
            <table>
              <tr>
                <th>Token</th>
                <th style="text-align:right;">Amount</th>
                <th style="text-align:right;">Value (COIN)</th>
                <th style="text-align:right;">Value (USD)</th>
              </tr>
              {% for r in tier_bp_totals_list %}
                <tr>
                  <td>{{ r.symbol }}</td>
                  <td style="text-align:right;">{{ "{:,.0f}".format(r.amount) }}</td>
                  <td style="text-align:right;">{{ "{:,.4f}".format(r.coin_value) }}</td>
                  <td style="text-align:right;">
                    {% if coin_usd %}
                      ${{ "{:,.2f}".format(r.usd_value) }}
                    {% else %}
                      —
                    {% endif %}
                  </td>
                </tr>
              {% endfor %}
            </table>
          </div>
        {% else %}
          <p class="hint">
            No numeric RawrPass resource rewards found in the API for this masterpiece.
          </p>
        {% endif %}
      </div>
    </div>

    <div style="margin-top:10px;">
      <div class="mp-stat-label">
        Total estimated tier rewards
        {% if tier_bp_totals_list %}(Base + RawrPass){% endif %}
      </div>
      <div class="mp-stat-value">
        ≈ {{ "%.4f"|format(tier_combined_total_coin) }} COIN
        {% if coin_usd and tier_combined_total_usd %}
          (≈ ${{ "%.2f"|format(tier_combined_total_usd) }})
        {% endif %}
      </div>
      <div class="hint">
        This is your <strong>full completion bag</strong> if you hit every tier.
      </div>
    </div>

    {% if my_rank_totals_list %}
      <div style="margin-top:16px;">
        <h4 style="margin-top:0;">🎯 Your cumulative rank rewards (all brackets up to your position)</h4>
        <p class="subtle">
          Uses your highlighted position
          {% if selected_reward_snapshot %}
            (#{{ selected_reward_snapshot.position }})
          {% endif %}
          on the leaderboard for this masterpiece.
        </p>
        <div class="scroll-x">
          <table>
            <tr>
              <th>Token</th>
              <th style="text-align:right;">Amount</th>
              <th style="text-align:right;">Value (COIN)</th>
              <th style="text-align:right;">Value (USD)</th>
            </tr>
            {% for r in my_rank_totals_list %}
              <tr>
                <td>{{ r.symbol }}</td>
                <td style="text-align:right;">{{ "{:,.0f}".format(r.amount) }}</td>
                <td style="text-align:right;">{{ "{:,.4f}".format(r.coin_value) }}</td>
                <td style="text-align:right;">
                  {% if coin_usd %}
                    ${{ "{:,.2f}".format(r.usd_value) }}
                  {% else %}
                    —
                  {% endif %}
                </td>
              </tr>
            {% endfor %}
          </table>
        </div>

        {% if grand_totals_list %}
          <div style="margin-top:10px;">
            <div class="mp-stat-label">Total estimated rewards (tiers + rank)</div>
            <div class="mp-stat-value">
              ≈ {{ "%.4f"|format(grand_total_coin) }} COIN
              {% if coin_usd and grand_total_usd %}
                (≈ ${{ "%.2f"|format(grand_total_usd) }})
              {% endif %}
            </div>
            <div class="hint">
              This combines the full tier completion bag above with your current
              leaderboard bracket rewards.
            </div>
          </div>
        {% endif %}
      </div>
    {% elif selected_reward_snapshot %}
      <p class="hint" style="margin-top:10px;">
        We found your leaderboard bracket, but it doesn't include numeric resource
        rewards we can price. Totals above show completion tiers only.
      </p>
    {% endif %}
  {% else %}
    <p class="hint">
      No numeric resource rewards available to estimate totals for this masterpiece.
    </p>
  {% endif %}
</div>



              <div>
                <h3 style="margin-top:0;">Leaderboard placement rewards</h3>
                {% if leaderboard_reward_rows %}
                  {% set my_rank = selected_reward_snapshot.position if selected_reward_snapshot else None %}
                  <div class="scroll-x">
                    <table>
                      <tr>
                        <th>Rank range</th>
                        <th>Rewards</th>
                      </tr>
                      {% for row in leaderboard_reward_rows %}
                        {% set from_rank = row.from_rank %}
                        {% set to_rank = row.to_rank or row.from_rank %}
                        {% set is_me = my_rank and from_rank and to_rank and (my_rank >= from_rank and my_rank <= to_rank) %}
                        <tr class="{% if is_me %}mp-row-me{% endif %}">
                          <td>
                            {% if from_rank and to_rank and from_rank != to_rank %}
                              #{{ from_rank }} – #{{ to_rank }}
                            {% elif from_rank %}
                              #{{ from_rank }}
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
                    No leaderboard reward metadata found for this masterpiece in the API.
                  </p>
                {% endif %}
              </div>
            </div>
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
                              {% if uid %}
                                <br>
                                <span style="font-size:11px; opacity:0.8;">
                                  {{ uid }}
                                </span>
                              {% endif %}
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
        selected_reward_snapshot=selected_reward_snapshot,
        src_mp=src_mp,

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

        # tier reward totals + valuation
        tier_base_totals_list=tier_base_totals_list,
        tier_bp_totals_list=tier_bp_totals_list,
        tier_combined_totals_list=tier_combined_totals_list,
        tier_combined_total_coin=tier_combined_total_coin,
        tier_combined_total_usd=tier_combined_total_usd,
        coin_usd=coin_usd,

        # rank + grand totals
        my_rank_totals_list=my_rank_totals_list,
        grand_totals_list=grand_totals_list,
        grand_total_coin=grand_total_coin,
        grand_total_usd=grand_total_usd,


        # leaderboard size options
        top_n=top_n,
        top_n_options=TOP_N_OPTIONS,

        # MP selector for history tab + highlight
        history_mp_options=history_mp_options,
        highlight_query=highlight_query,
        has_battle_pass=has_battle_pass,
    )

    # Wrap in the global base template (same pattern as other tabs)
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
    tier_index: Optional[int] = None
    if my_points is not None:
        try:
            pts = float(my_points)
        except Exception:
            pts = None

        if pts is not None:
            t_index = 0
            # MP_TIER_THRESHOLDS is a simple list of ints
            for i, req in enumerate(MP_TIER_THRESHOLDS, start=1):
                if pts >= req:
                    t_index = i
                else:
                    break

            if t_index > 0:
                tier_index = t_index
                tier_label = f"Tier {t_index}"
                tier_min = MP_TIER_THRESHOLDS[t_index - 1]
                if t_index < len(MP_TIER_THRESHOLDS):
                    # Next tier starts at the next threshold; treat max as one less
                    tier_max = MP_TIER_THRESHOLDS[t_index] - 1
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
        "tier_index": tier_index,

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

    # ----- Load masterpieces for dropdowns -----
    masterpieces_data: List[Dict[str, Any]] = []
    try:
        masterpieces_data = fetch_masterpieces()
    except Exception as e:
        error = f"Error fetching masterpieces: {e}"
        masterpieces_data = []

    # Build a lookup by ID and compute the highest MP ID we know about,
    # just like the Masterpiece Hub does.
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

    # Finally, build MP choices as MP 1..max_mp_id so Snipe sees *all* MPs.
    mp_choices: List[Dict[str, Any]] = []
    if max_mp_id > 0:
        for mid in range(1, max_mp_id + 1):
            mp = mp_by_id.get(mid, {"id": mid})
            name = (
                mp.get("name")
                or mp.get("addressable_label")
                or mp.get("addressableLabel")
                or mp.get("type")
                or f"MP {mid}"
            )
            mp_choices.append({"id": mid, "label": f"{name} (ID {mid})"})
    else:
        # Fallback: if for some reason we have no max_mp_id, use raw list.
        for mp in masterpieces_data:
            mid = mp.get("id")
            if not mid:
                continue
            name = mp.get("name") or mp.get("type") or f"MP {mid}"
            mp_choices.append({
                "id": mid,
                "label": f"{name} (ID {mid})",
            })



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

                    # Base resources from the masterpiece
                    resources = mp.get("resources") or []

                    # NEW: if this masterpiece doesn’t expose resources (e.g. event MP),
                    # build a synthetic list from ALL_FACTORY_TOKENS so we still
                    # get names + per-unit battery/points via predictReward.
                    if not resources:
                        resources = [
                            {"symbol": sym, "amount": 0.0, "target": float("inf")}
                            for sym in ALL_FACTORY_TOKENS
                        ]

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

                        # Require the resource to give MP points,
                        # but allow price_coin == 0 (no price data).
                        if pts_per_unit <= 0:
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

                    # Base resources from the masterpiece
                    resources = mp.get("resources") or []

                    # NEW: fallback for event MPs with no explicit resources list
                    if not resources:
                        resources = [
                            {"symbol": sym, "amount": 0.0, "target": float("inf")}
                            for sym in ALL_FACTORY_TOKENS
                        ]

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

                        # ALLOW price_coin == 0 (event resources without price data)
                        if pts_per_unit <= 0:
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

        <!-- SUMMARY CARD -->
        <div class="card" style="margin-top:8px; margin-bottom:16px;">
          <h2>
            {{ calc_result.token }} L{{ calc_result.level }}
            {% if calc_result.target_level %} → L{{ calc_result.target_level }}{% endif %}
          </h2>
          <p class="subtle">
            Factories: <strong>{{ calc_result.count }}</strong> •
            Yield / Mastery: <strong>{{ "%.1f"|format(calc_result.yield_pct) }}%</strong> •
            Speed: <strong>{{ "%.2f"|format(calc_result.speed_factor) }}x</strong> •
            Workers: <strong>{{ calc_result.workers }}</strong>
          </p>
        </div>

        <!-- PRODUCTION -->
        <div class="card" style="margin-bottom:12px;">
          <h3>Production</h3>
          <p class="subtle">
            <strong>Base duration:</strong>
            {{ "%.2f"|format(calc_result.duration_min) }} min<br>
            <strong>Effective duration (speed &amp; workers):</strong>
            {{ "%.2f"|format(calc_result.effective_duration) }} min<br>
            <strong>Crafts / hour (per factory):</strong>
            {{ "%.4f"|format(calc_result.crafts_per_hour) }}
          </p>
        </div>

        <!-- OUTPUTS -->
        <div class="card" style="margin-bottom:12px;">
          <h3>Outputs (per craft)</h3>
          <p class="subtle">
            <strong>Amount:</strong>
            {{ "%.4f"|format(calc_result.out_amount) }} {{ calc_result.out_token }}<br>
            <strong>Value:</strong>
            {{ "%.6f"|format(calc_result.value_coin_per_craft) }} COIN / craft
          </p>
        </div>

        <!-- INPUTS -->
        <div class="card" style="margin-bottom:12px;">
          <h3>Inputs (per craft — adjusted for {{ calc_result.yield_pct }}% yield)</h3>
          {% if calc_result.inputs %}
            <table>
              <thead>
                <tr>
                  <th>Token</th>
                  <th>Amount</th>
                  <th>Value (COIN)</th>
                </tr>
              </thead>
              <tbody>
              {% for tok, qty in calc_result.inputs.items() %}
                <tr>
                  <td>{{ tok }}</td>
                  <td>{{ "%.6f"|format(qty) }}</td>
                  <td>{{ "%.6f"|format(calc_result.inputs_value_coin[tok]) }}</td>
                </tr>
              {% endfor %}
              </tbody>
            </table>
          {% else %}
            <p class="subtle">No inputs found for this recipe.</p>
          {% endif %}
        </div>

        <!-- PROFIT -->
        <div class="card" style="margin-bottom:12px;">
          <h3>Profit</h3>
          <p class="subtle">
            <strong>Cost / craft:</strong>
            {{ "%.6f"|format(calc_result.cost_coin_per_craft) }} COIN<br>
            <strong>Value / craft:</strong>
            {{ "%.6f"|format(calc_result.value_coin_per_craft) }} COIN<br><br>

            <strong>Profit / craft:</strong>
            {{ "%+.6f"|format(calc_result.profit_coin_per_craft) }} COIN<br>
            <strong>Profit / hour ({{ calc_result.count }} factory/factories):</strong>
            {{ "%+.6f"|format(calc_result.profit_coin_per_hour) }} COIN
          </p>
        </div>

        <!-- UPGRADES -->
        <div class="card">
          <h3>Upgrade Costs</h3>

          {% if calc_result.upgrade_single %}
            <h4>Next level (single step)</h4>
            <p class="subtle">
              <strong>Resource:</strong>
              {{ calc_result.upgrade_single.amount_per_factory }} {{ calc_result.upgrade_single.token }} per factory<br>
              <strong>Cost / factory:</strong>
              {{ "%.6f"|format(calc_result.upgrade_single.coin_per_factory) }} COIN<br>
              <strong>Total for {{ calc_result.count }} factories:</strong>
              {{ "%.6f"|format(calc_result.upgrade_single.coin_total) }} COIN
            </p>
          {% else %}
            <p class="subtle">No single-step upgrade cost found.</p>
          {% endif %}

          {% if calc_result.upgrade_chain %}
            <hr style="border:none;border-top:1px solid rgba(255,255,255,0.15);margin:10px 0 8px;">
            <h4>Full upgrade chain L{{ calc_result.level }} → L{{ calc_result.target_level }}</h4>
            <table>
              <thead>
                <tr>
                  <th>Token</th>
                  <th>Amount / factory</th>
                  <th>COIN / factory</th>
                  <th>COIN (all factories)</th>
                </tr>
              </thead>
              <tbody>
              {% for step in calc_result.upgrade_chain %}
                <tr>
                  <td>{{ step.token }}</td>
                  <td>{{ "%.6f"|format(step.amount_per_factory) }}</td>
                  <td>{{ "%.6f"|format(step.coin_per_factory) }}</td>
                  <td>{{ "%.6f"|format(step.coin_total) }}</td>
                </tr>
              {% endfor %}
              </tbody>
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

# -------- Trees tab (Earth / Water / Fire / Special) --------

@app.route("/trees", methods=["GET"])
def trees():
    """
    Tree-style overview similar to Craftworld.tips:
    - Earth / Water / Fire / Special
    - Each row uses a single level 1 factory
      with 100% yield, 1x speed, 0 workers.
    """
    error = None
    trees_data = []
    prices = {}
    coin_usd = 0.0

    try:
        prices = fetch_live_prices_in_coin()
        coin_usd = float(prices.get("_COIN_USD", 0.0))
    except Exception as e:
        error = f"Error fetching prices: {e}"

    # You can tweak this mapping any time – tiers, order, tokens, labels.
    TREE_LAYOUT = {
        "Earth": [
            {"tier": 1, "token": "EARTH",      "label": "Earth Mine"},
            {"tier": 2, "token": "MUD",        "label": "Mud"},
            {"tier": 3, "token": "CLAY",       "label": "Clay"},
            {"tier": 4, "token": "SAND",       "label": "Sand"},
            {"tier": 5, "token": "COPPER",     "label": "Copper"},
            {"tier": 6, "token": "STEEL",      "label": "Steel"},
            {"tier": 7, "token": "SCREWS",     "label": "Screws"},
        ],
        "Water": [
            {"tier": 1, "token": "WATER",      "label": "Water Mine"},
            {"tier": 2, "token": "SEAWATER",   "label": "Seawater"},
            {"tier": 3, "token": "ALGAE",      "label": "Algae"},
            {"tier": 4, "token": "OXYGEN",     "label": "Oxygen"},
            {"tier": 5, "token": "GAS",        "label": "Gas"},
        ],
        "Fire": [
            {"tier": 1, "token": "FIRE",       "label": "Fire Mine"},
            {"tier": 2, "token": "HEAT",       "label": "Heat"},
            {"tier": 3, "token": "LAVA",       "label": "Lava"},
            {"tier": 4, "token": "FUEL",       "label": "Fuel"},
            {"tier": 5, "token": "OIL",        "label": "Oil"},
            {"tier": 6, "token": "SULFUR",     "label": "Sulfur"},
            {"tier": 7, "token": "ACID",       "label": "Acid"},
        ],
        "Special": [
            {"tier": 1, "token": "PLASTICS",   "label": "Plastics"},
            {"tier": 2, "token": "FIBERGLASS", "label": "Fiberglass"},
            {"tier": 3, "token": "ENERGY",     "label": "Energy"},
            {"tier": 4, "token": "HYDROGEN",   "label": "Hydrogen"},
            {"tier": 5, "token": "DYNAMITE",   "label": "Dynamite"},
        ],
    }

    # Build data for each tree
    for tree_name, tiers in TREE_LAYOUT.items():
        rows = []
        total_volume_hour = 0.0
        total_profit_hour = 0.0
        best = None
        worst = None

        for node in tiers:
            token = node["token"]
            tier = node["tier"]
            label = node["label"]

            price_coin = float(prices.get(token, 0.0)) if prices else 0.0
            price_usd = price_coin * coin_usd if coin_usd else 0.0

            duration_min = None
            volume_hour = None
            profit_hour = None

            try:
                # Only calculate if this token exists as a factory in the CSV at L1
                if FACTORIES_FROM_CSV.get(token) and 1 in FACTORIES_FROM_CSV[token]:
                    res = compute_factory_result_csv(
                        FACTORIES_FROM_CSV,
                        prices or {},
                        token,
                        level=1,
                        target_level=None,
                        count=1,
                        yield_pct=100.0,
                        speed_factor=1.0,
                        workers=0,
                    )
                    duration_min = float(res.get("duration_min", 0.0))
                    crafts_per_hour = float(res.get("crafts_per_hour", 0.0))
                    out_amount = float(res.get("out_amount", 0.0))
                    volume_hour = crafts_per_hour * out_amount
                    profit_hour = float(res.get("profit_coin_per_hour", 0.0))
            except Exception as ex:
                # Don't explode the whole page if one token is weird
                if not error:
                    error = f"Some tree rows could not be calculated: {ex}"

            if profit_hour is not None:
                total_profit_hour += profit_hour
                if best is None or profit_hour > best["profit_hour"]:
                    best = {"token": token, "profit_hour": profit_hour}
                if worst is None or profit_hour < worst["profit_hour"]:
                    worst = {"token": token, "profit_hour": profit_hour}

            if volume_hour is not None:
                total_volume_hour += volume_hour

            rows.append(
                {
                    "tier": tier,
                    "label": label,
                    "token": token,
                    "price_coin": price_coin,
                    "price_usd": price_usd,
                    "duration_min": duration_min,
                    "volume_hour": volume_hour,
                    "profit_hour": profit_hour,
                }
            )

        trees_data.append(
            {
                "name": tree_name,
                "rows": rows,
                "total_volume_hour": total_volume_hour,
                "total_profit_hour": total_profit_hour,
                "best": best,
                "worst": worst,
            }
        )

    content = """
    <div class="card">
      <h1>Production Trees</h1>
      <p class="subtle">
        Tree view similar to <strong>Craftworld.tips</strong>.<br>
        Each row uses a single <strong>level 1 factory</strong>, 100% yield, 1x speed, 0 workers.
      </p>
      {% if error %}
        <div class="error">{{ error }}</div>
      {% endif %}
    </div>

    <div class="two-col">
      {% for tree in trees %}
        <div class="card">
          <h2>{{ tree.name }} Tree</h2>
          <p class="subtle">
            Total output/hr (L1, 1 each): {{ "%.4f"|format(tree.total_volume_hour or 0.0) }}<br>
            Total profit/hr: {{ "%+.6f"|format(tree.total_profit_hour or 0.0) }} COIN
            {% if tree.best %}
              <br>Best: {{ tree.best.token }} ({{ "%+.6f"|format(tree.best.profit_hour) }} COIN/hr)
            {% endif %}
            {% if tree.worst %}
              <br>Worst: {{ tree.worst.token }} ({{ "%+.6f"|format(tree.worst.profit_hour) }} COIN/hr)
            {% endif %}
          </p>

          <div style="overflow-x:auto;">
            <table>
              <tr>
                <th>Tier</th>
                <th>Resource</th>
                <th>Price (COIN)</th>
                <th>Price (USD)</th>
                <th>Duration (min)</th>
                <th>Output/hr</th>
                <th>Profit/hr (COIN)</th>
              </tr>
              {% for r in tree.rows %}
                <tr>
                  <td>T{{ r.tier }}</td>
                <td>
                  <a href="{{ url_for('resource_view', token=r.token) }}">
                    {{ r.label }}{% if r.token != r.label %} ({{ r.token }}){% endif %}
                  </a>
                </td>
                  <td>{{ "%.6f"|format(r.price_coin or 0.0) }}</td>
                  <td>{{ "%.4f"|format(r.price_usd or 0.0) }}</td>
                  <td>
                    {% if r.duration_min is not none %}
                      {{ "%.2f"|format(r.duration_min) }}
                    {% else %}
                      &mdash;
                    {% endif %}
                  </td>
                  <td>
                    {% if r.volume_hour is not none %}
                      {{ "%.4f"|format(r.volume_hour) }}
                    {% else %}
                      &mdash;
                    {% endif %}
                  </td>
                  <td>
                    {% if r.profit_hour is not none %}
                      <span class="{{ 'pill' if r.profit_hour >= 0 else 'pill-bad' }}">
                        {{ "%+.6f"|format(r.profit_hour) }}
                      </span>
                    {% else %}
                      &mdash;
                    {% endif %}
                  </td>
                </tr>
              {% endfor %}
            </table>
          </div>
        </div>
      {% endfor %}
    </div>
    """

    html = render_template_string(
        BASE_TEMPLATE,
        content=render_template_string(
            content,
            trees=trees_data,
            error=error,
        ),
        active_page="trees",
        has_uid=has_uid_flag(),
    )
    return html



if __name__ == "__main__":
    app.run(debug=True)


























































































































































