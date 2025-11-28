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

DB_PATH = "craftworld_tools.db"


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
    conn.commit()
    conn.close()


init_db()


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



# -------- Profitability tab (manual mastery + workshop) --------

def attr_or_key(obj, name, default=None):
    """
    Safely get obj.name OR obj['name'], with a default.
    Works for both dicts and simple objects.
    """
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


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
            default_levels = boost_levels.get(
                token_upper, {"mastery_level": 0, "workshop_level": 0}
            )
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
                yield_pct=yield_pct,                 # mastery → input reduction
                speed_factor=effective_speed_factor, # workshop + AD → time reduction
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

# -------- Masterpieces tab --------
@app.route("/masterpieces")
def masterpieces_view():
    error: Optional[str] = None
    masterpieces_data: List[Dict[str, Any]] = []

    try:
        masterpieces_data = fetch_masterpieces()
    except Exception as e:
        error = f"Error fetching masterpieces: {e}"

    content = """
    <div class="card">
      <h1>Masterpieces</h1>
      <p class="subtle">
        Live <code>masterpieces</code> data from Craft World with top 25 and event MP at the bottom of each.
      </p>
      {% if error %}
        <div class="error">{{ error }}</div>
      {% endif %}

      {% if masterpieces %}
        {% for mp in masterpieces %}
          <div class="card" style="margin-top:12px;">
            <h2>{{ mp.name }} <span class="subtle">({{ mp.addressableLabel or mp.id }})</span></h2>
            <p class="subtle">
              Type: {{ mp.type }} · Event: {{ mp.eventId }}<br>
              Event MP: {{ mp.collectedPoints | int }} / {{ mp.requiredPoints | int }}
            </p>

            <h3>Top 25 leaderboard</h3>
            {% set lb = mp.leaderboard or [] %}
{% if lb %}
  <div class="mp-table-wrap">
    <table>
      <tr>
        <th>#</th>
        <th>Player</th>
        <th>UID</th>
        <th>MP</th>
      </tr>
      {% for entry in lb[:25] %}
        <tr>
          <td>{{ entry.position }}</td>
          <td>{{ entry.profile.displayName or '—' }}</td>
          <td class="subtle">{{ entry.profile.uid }}</td>
          <td>{{ "{:,.0f}".format(entry.masterpiecePoints) }}</td>
        </tr>
      {% endfor %}
    </table>
  </div>

  <p class="subtle" style="margin-top:6px;">
    Event MP total (bottom):
    <strong>{{ "{:,.0f}".format(mp.collectedPoints) }}</strong>
    of {{ "{:,.0f}".format(mp.requiredPoints) }} required.
  </p>
{% endif %}


            <p class="subtle" style="margin-top:6px;">
              Event MP total (bottom):
              <strong>{{ "{:,.0f}".format(mp.collectedPoints) }}</strong>
              of {{ "{:,.0f}".format(mp.requiredPoints) }} required.
            </p>
          </div>
        {% endfor %}
      {% else %}
        <p class="subtle">No masterpieces data returned.</p>
      {% endif %}
    </div>
    """

    content = render_template_string(
        content,
        masterpieces=masterpieces_data,
        error=error,
    )

    html = render_template_string(
        BASE_TEMPLATE,
        content=content,
        active_page="masterpieces",
        has_uid=has_uid_flag(),
    )
    return html


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









