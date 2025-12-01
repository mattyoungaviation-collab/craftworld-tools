from __future__ import annotations

import json
import math
import os
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from flask import (
    Flask,
    request,
    render_template_string,
    session,
    redirect,
    url_for,
)

from craftworld_api import (
    fetch_craftworld,
    fetch_masterpieces,
    fetch_masterpiece_details,
    predict_reward,
)
from factories import (
    FACTORIES_FROM_CSV,
    compute_factory_result_csv,
)
from pricing import fetch_live_prices_in_coin

# -------------------------------------------------
# Flask app + config
# -------------------------------------------------

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-please-change")

DB_PATH = os.environ.get("DB_PATH", "craftworld_tools.db")

# -------------------------------------------------
# Helpers: DB for boosts (mastery/workshop per token)
# -------------------------------------------------


def _ensure_db() -> None:
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS boost_levels (
                user_id TEXT PRIMARY KEY,
                data    TEXT NOT NULL
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def _load_boost_levels(user_id: str) -> Dict[str, Dict[str, int]]:
    _ensure_db()
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute("SELECT data FROM boost_levels WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
        if not row or not row[0]:
            return {}
        return json.loads(row[0])
    except Exception:
        return {}
    finally:
        conn.close()


def _save_boost_levels(user_id: str, payload: Dict[str, Dict[str, int]]) -> None:
    _ensure_db()
    encoded = json.dumps(payload)
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO boost_levels (user_id, data)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET data = excluded.data
            """,
            (user_id, encoded),
        )
        conn.commit()
    finally:
        conn.close()


def _current_uid() -> Optional[str]:
    uid = session.get("voya_uid")
    if uid and isinstance(uid, str) and uid.strip():
        return uid.strip()
    return None


def _has_uid() -> bool:
    return _current_uid() is not None


def _get_boost_levels_for_uid(uid: str) -> Dict[str, Dict[str, int]]:
    """Return dict like {TOKEN: {"mastery": int, "workshop": int}}."""
    return _load_boost_levels(uid)


def _set_boost_levels_for_uid(uid: str, levels: Dict[str, Dict[str, int]]) -> None:
    _save_boost_levels(uid, levels)


# -------------------------------------------------
# Constants
# -------------------------------------------------

ALL_FACTORY_TOKENS: List[str] = sorted(FACTORIES_FROM_CSV.keys())

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
    "CEMENT",
    "STEAM",
    "SCREWS",
    "FUEL",
    "OIL",
    "PLASTICS",
    "FIBERGLASS",
    "ENERGY",
    "HYDROGEN",
    "DYNAMITE",
    "TAPE",
    "MAGICSHARD",
    "PLUNGER",
    "SPOON",
    "TOYHAMMER",
    "NINJASTAR",
    "SWORD",
    "MYSTICWEAPON",
    "TARGET",
]
STANDARD_ORDER_INDEX: Dict[str, int] = {
    name.upper(): idx for idx, name in enumerate(STANDARD_FACTORY_ORDER)
}

MP_TIER_THRESHOLDS: List[int] = [
    10_000,
    35_000,
    85_000,
    200_000,
    500_000,
    1_000_000,
    2_000_000,
    5_000_000,
    10_000_000,
    20_000_000,
]

# -------------------------------------------------
# Base template
# -------------------------------------------------

BASE_TEMPLATE = """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8"/>
    <title>CraftMath — Tools</title>
    <style>
      body {
        background:#020617;
        color:#e5e7eb;
        font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
        margin:0;
        padding:0;
      }
      a { color:#60a5fa; text-decoration:none; }
      a:hover { text-decoration:underline; }

      header {
        background:#020617;
        border-bottom:1px solid rgba(148,163,184,0.3);
        padding:10px 16px;
        position:sticky;
        top:0;
        z-index:10;
      }
      .nav {
        display:flex;
        gap:16px;
        align-items:center;
      }
      .nav-title {
        font-weight:700;
        letter-spacing:0.03em;
      }
      .nav-links a {
        padding:4px 8px;
        border-radius:999px;
        font-size:14px;
        color:#9ca3af;
      }
      .nav-links a.active {
        background:#1d4ed8;
        color:#e5e7eb;
      }

      main {
        max-width:1100px;
        margin:16px auto 32px auto;
        padding:0 16px;
      }

      .card {
        background:rgba(15,23,42,0.9);
        border-radius:16px;
        border:1px solid rgba(148,163,184,0.4);
        padding:16px 20px;
        box-shadow:0 18px 45px rgba(15,23,42,0.95);
      }

      h1 { margin:0 0 6px 0; font-size:22px; }
      h2 { margin-top:18px; font-size:18px; }
      .subtle { color:#9ca3af; font-size:14px; }
      .hint { color:#a5b4fc; font-size:13px; }

      label { font-size:14px; }
      input, select, button, textarea {
        font-family:inherit;
        font-size:14px;
      }
      input[type="text"], input[type="number"], select, textarea {
        background:#020617;
        border:1px solid rgba(148,163,184,0.5);
        color:#e5e7eb;
        border-radius:8px;
        padding:6px 8px;
      }
      button {
        border-radius:999px;
        border:none;
        padding:6px 12px;
        background:#1d4ed8;
        color:white;
        cursor:pointer;
      }
      button:hover { background:#2563eb; }

      table {
        width:100%;
        border-collapse:collapse;
        margin-top:8px;
      }
      th, td {
        padding:4px 6px;
        border-bottom:1px solid rgba(30,64,175,0.4);
        text-align:left;
        font-size:13px;
      }
      th {
        font-size:12px;
        text-transform:uppercase;
        letter-spacing:0.05em;
        color:#9ca3af;
      }

      .error {
        background:rgba(185,28,28,0.1);
        border:1px solid rgba(185,28,28,0.5);
        color:#fecaca;
        padding:8px 10px;
        border-radius:8px;
        margin-bottom:10px;
      }

      .mp-tab-bar {
        display:flex;
        gap:8px;
        margin-top:12px;
        margin-bottom:10px;
        border-bottom:1px solid rgba(30,64,175,0.5);
        padding-bottom:6px;
      }
      .mp-tab {
        padding:4px 10px;
        border-radius:999px;
        font-size:13px;
        color:#9ca3af;
        cursor:pointer;
      }
      .mp-tab.active {
        background:#1d4ed8;
        color:#f9fafb;
      }
      .mp-section { margin-top:4px; }

      .mp-table-wrap { max-height:420px; overflow:auto; border-radius:8px; border:1px solid rgba(30,64,175,0.5); }

      .mp-stat-label { font-size:11px; text-transform:uppercase; color:#9ca3af; letter-spacing:0.08em; }
      .mp-stat-value { font-size:14px; font-weight:600; }

      .mp-row-me {
        background: linear-gradient(90deg, rgba(250,204,21,0.14), transparent);
      }
      .mp-row-me td {
        border-top: 1px solid rgba(250,204,21,0.35);
        border-bottom: 1px solid rgba(250,204,21,0.18);
      }
      .me-pill {
        display: inline-block;
        margin-left: 6px;
        padding: 1px 6px;
        border-radius: 999px;
        font-size: 11px;
        border: 1px solid rgba(250,204,21,0.7);
        color: #facc15;
        background: rgba(30,64,175,0.65);
      }

      @media (max-width: 768px) {
        main { padding:0 10px; }
      }
    </style>
  </head>
  <body>
    <header>
      <div class="nav">
        <div class="nav-title">CraftMath</div>
        <div class="nav-links">
          <a href="{{ url_for('overview') }}" class="{% if active_page == 'overview' %}active{% endif %}">Overview</a>
          <a href="{{ url_for('profitability') }}" class="{% if active_page == 'profitability' %}active{% endif %}">Profitability</a>
          <a href="{{ url_for('boosts') }}" class="{% if active_page == 'boosts' %}active{% endif %}">Boosts</a>
          <a href="{{ url_for('masterpieces_view') }}" class="{% if active_page == 'masterpieces' %}active{% endif %}">Masterpieces</a>
          <a href="{{ url_for('snipe') }}" class="{% if active_page == 'snipe' %}active{% endif %}">Snipe</a>

        </div>
      </div>
    </header>
    <main>
      <div class="card">
        {{ content|safe }}
      </div>
    </main>
  </body>
</html>
"""

# -------------------------------------------------
# Index / UID handling
# -------------------------------------------------


@app.route("/", methods=["GET", "POST"])
def index():
    return redirect(url_for("overview"))


@app.route("/overview", methods=["GET", "POST"])
def overview():
    error: Optional[str] = None
    account: Optional[Dict[str, Any]] = None
    uid = _current_uid()

    if request.method == "POST":
        new_uid = (request.form.get("uid") or "").strip()
        if new_uid:
            session["voya_uid"] = new_uid
            uid = new_uid

    if uid:
        try:
            account = fetch_craftworld(uid)
        except Exception as e:
            error = f"Error fetching account: {e}"

    content = """
    <h1>Account overview</h1>
    <p class="subtle">Enter your Voya ID to load your Craft World account.</p>

    <form method="post" style="margin-top:8px; display:flex; flex-wrap:wrap; gap:8px; align-items:center;">
      <label for="uid">Voya ID / UID</label>
      <input id="uid" name="uid" type="text" value="{{ uid or '' }}" style="min-width:260px;">
      <button type="submit">Load</button>
    </form>

    {% if error %}
      <div class="error">{{ error }}</div>
    {% endif %}

    {% if account %}
      <h2>Land plots</h2>
      <table>
        <tr><th>Name</th><th>Area</th><th>Factories</th></tr>
        {% for lp in account.landPlots or [] %}
          <tr>
            <td>{{ lp.name or '-' }}</td>
            <td>{{ lp.area or '-' }}</td>
            <td>{{ (lp.factories or [])|length }}</td>
          </tr>
        {% endfor %}
      </table>

      <h2>Resources</h2>
      <table>
        <tr><th>Symbol</th><th>Amount</th></tr>
        {% for r in account.resources or [] %}
          <tr>
            <td>{{ r.symbol }}</td>
            <td>{{ "%.3f"|format(r.amount or 0) }}</td>
          </tr>
        {% endfor %}
      </table>
    {% elif uid %}
      <p class="hint">No account data available. Double-check your UID.</p>
    {% endif %}
    """
    inner = render_template_string(content, uid=uid, account=account, error=error)
    return render_template_string(
        BASE_TEMPLATE,
        content=inner,
        active_page="overview",
    )


# -------------------------------------------------
# Profitability
# -------------------------------------------------


@app.route("/profitability", methods=["GET", "POST"])
def profitability():
    uid = _current_uid()
    error: Optional[str] = None
    rows: List[Dict[str, Any]] = []
    prices: Dict[str, float] = {}
    speed_factor = float(request.form.get("speed") or 1.0)
    workers_default = int(request.form.get("workers") or 0)

    if not uid:
        content = """
        <h1>Profitability</h1>
        <p class="subtle">You need to set your Voya ID in Overview first.</p>
        <p class="hint"><a href="{{ url_for('overview') }}">Go to Overview</a> and enter your UID.</p>
        """
        inner = render_template_string(content)
        return render_template_string(BASE_TEMPLATE, content=inner, active_page="profitability")

    try:
        account = fetch_craftworld(uid)
    except Exception as e:
        account = None
        error = f"Error fetching account: {e}"

    if account:
        try:
            prices = fetch_live_prices_in_coin()
        except Exception as e:
            prices = {}
            error = error or f"Error fetching prices: {e}"

        coin_usd = float(prices.get("_COIN_USD", 0.0) or 0.0)
        boosts = _get_boost_levels_for_uid(uid)

        # Iterate over factories reported by API
        for lp in account.get("landPlots") or []:
            for f in lp.get("factories") or []:
                token = (f.get("token") or "").upper()
                level = int(f.get("level") or 0) + 1  # API level is 0-based
                count = int(f.get("count") or 1)

                levels = boosts.get(token, {})
                mastery = int(levels.get("mastery", 0))
                workshop = int(levels.get("workshop", 0))

                try:
                    result = compute_factory_result_csv(
                        FACTORIES_FROM_CSV,
                        prices,
                        token,
                        level,
                        None,
                        count,
                        yield_pct=100.0,
                        speed_factor=speed_factor,
                        workers=workers_default,
                    )
                except Exception:
                    continue

                rows.append(
                    {
                        "token": token,
                        "level": level,
                        "count": count,
                        "mastery": mastery,
                        "workshop": workshop,
                        "profit_hour": result.get("profit_per_hour_coin", 0.0),
                        "profit_hour_usd": result.get("profit_per_hour_coin", 0.0) * coin_usd,
                    }
                )

        # Sort by profit descending
        rows.sort(key=lambda r: r["profit_hour"], reverse=True)

    content = """
    <h1>Profitability</h1>
    <p class="subtle">Live profit per hour for your factories using current exchange prices.</p>

    <form method="post" style="margin-top:8px; display:flex; flex-wrap:wrap; gap:8px; align-items:center;">
      <label for="speed">Global speed factor</label>
      <input id="speed" name="speed" type="number" step="0.01" value="{{ speed_factor }}">
      <label for="workers">Workers per factory</label>
      <input id="workers" name="workers" type="number" step="1" value="{{ workers_default }}">
      <button type="submit">Recalculate</button>
    </form>

    {% if error %}
      <div class="error">{{ error }}</div>
    {% endif %}

    {% if rows %}
      <table>
        <tr>
          <th>Token</th>
          <th>Level</th>
          <th>Count</th>
          <th>Profit / h (COIN)</th>
          <th>Profit / h (USD)</th>
        </tr>
        {% for r in rows %}
          <tr>
            <td>{{ r.token }}</td>
            <td>L{{ r.level }}</td>
            <td>{{ r.count }}</td>
            <td>{{ "%.4f"|format(r.profit_hour) }}</td>
            <td>{{ "%.4f"|format(r.profit_hour_usd) }}</td>
          </tr>
        {% endfor %}
      </table>
    {% elif uid %}
      <p class="hint">No factories found for your account.</p>
    {% endif %}
    """
    inner = render_template_string(
        content,
        rows=rows,
        error=error,
        speed_factor=speed_factor,
        workers_default=workers_default,
    )
    return render_template_string(
        BASE_TEMPLATE,
        content=inner,
        active_page="profitability",
    )


# -------------------------------------------------
# Boosts editor
# -------------------------------------------------


@app.route("/boosts", methods=["GET", "POST"])
def boosts():
    uid = _current_uid()
    if not uid:
        content = """
        <h1>Boosts</h1>
        <p class="subtle">You need to set your Voya ID in Overview first.</p>
        <p class="hint"><a href="{{ url_for('overview') }}">Go to Overview</a>.</p>
        """
        inner = render_template_string(content)
        return render_template_string(BASE_TEMPLATE, content=inner, active_page="boosts")

    current_levels = _get_boost_levels_for_uid(uid)

    if request.method == "POST":
        new_levels: Dict[str, Dict[str, int]] = {}
        for token in ALL_FACTORY_TOKENS:
            key_m = f"mastery_{token}"
            key_w = f"workshop_{token}"
            try:
                m = int(request.form.get(key_m, "0") or 0)
                w = int(request.form.get(key_w, "0") or 0)
            except ValueError:
                m = 0
                w = 0
            m = max(0, min(10, m))
            w = max(0, min(10, w))
            if m or w:
                new_levels[token] = {"mastery": m, "workshop": w}
        _set_boost_levels_for_uid(uid, new_levels)
        current_levels = new_levels

    # Build a simple list in standard order
    rows: List[Dict[str, Any]] = []
    for token in sorted(ALL_FACTORY_TOKENS, key=lambda t: STANDARD_ORDER_INDEX.get(t.upper(), 9999)):
        levels = current_levels.get(token, {})
        rows.append(
            {
                "token": token,
                "mastery": int(levels.get("mastery", 0)),
                "workshop": int(levels.get("workshop", 0)),
            }
        )

    content = """
    <h1>Boosts</h1>
    <p class="subtle">Set your per-token Mastery and Workshop levels (0–10). These are used in Profitability.</p>

    <form method="post">
      <table>
        <tr>
          <th>Token</th>
          <th>Mastery</th>
          <th>Workshop</th>
        </tr>
        {% for r in rows %}
          <tr>
            <td>{{ r.token }}</td>
            <td>
              <input type="number" name="mastery_{{ r.token }}" min="0" max="10" value="{{ r.mastery }}" style="width:60px;">
            </td>
            <td>
              <input type="number" name="workshop_{{ r.token }}" min="0" max="10" value="{{ r.workshop }}" style="width:60px;">
            </td>
          </tr>
        {% endfor %}
      </table>
      <div style="margin-top:10px;">
        <button type="submit">Save boosts</button>
      </div>
    </form>
    """
    inner = render_template_string(content, rows=rows)
    return render_template_string(
        BASE_TEMPLATE,
        content=inner,
        active_page="boosts",
    )


# -------------------------------------------------
# Masterpieces hub (planner + leaderboards)
# -------------------------------------------------


def _pick_current_mp(masterpieces: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    general = [m for m in masterpieces if not m.get("eventId")]
    event = [m for m in masterpieces if m.get("eventId")]

    def _id(m: Dict[str, Any]) -> int:
        try:
            return int(m.get("id") or 0)
        except Exception:
            return 0

    if general:
        return sorted(general, key=_id)[-1]
    if event:
        return sorted(event, key=_id)[-1]
    return None


def _get_mp_per_unit_rewards(mp_id: str, symbols: List[str]) -> Dict[str, Dict[str, float]]:
    """Call predictReward once per token with amount=1 to get MP/XP per unit."""
    results: Dict[str, Dict[str, float]] = {}
    for sym in symbols:
        resources = [{"symbol": sym, "amount": 1}]
        try:
            data = predict_reward(mp_id, resources)
            results[sym] = {
                "mp": float(data.get("masterpiecePoints", 0) or 0.0),
                "xp": float(data.get("experiencePoints", 0) or 0.0),
            }
        except Exception:
            results[sym] = {"mp": 0.0, "xp": 0.0}
    return results


@app.route("/masterpieces", methods=["GET", "POST"])
def masterpieces_view():
    error: Optional[str] = None
    try:
        all_mps = fetch_masterpieces()
    except Exception as e:
        all_mps = []
        error = f"Error fetching masterpieces: {e}"

    # Split into general / event
    general_mps = [m for m in all_mps if not m.get("eventId")]
    event_mps = [m for m in all_mps if m.get("eventId")]

    def _id(m: Dict[str, Any]) -> int:
        try:
            return int(m.get("id") or 0)
        except Exception:
            return 0

    general_mps = sorted(general_mps, key=_id)
    event_mps = sorted(event_mps, key=_id)

    # ----- Top N settings -----
    TOP_N_OPTIONS = [10, 25, 50, 100]
    DEFAULT_TOP_N = 50
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
    session["mp_top_n"] = top_n

    # ----- Highlight name / UID -----
    highlight_query = (request.args.get("highlight") or request.form.get("highlight") or "").strip()
    if highlight_query:
        session["mp_highlight"] = highlight_query
    else:
        highlight_query = session.get("mp_highlight", "") or ""

    # Pick "current" MP
    current_mp = _pick_current_mp(all_mps)
    current_mp_top: List[Dict[str, Any]] = []
    if current_mp:
        lb = current_mp.get("leaderboard") or []
        current_mp_top = list(lb[:top_n])

    # History selector
    mp_selector_options = general_mps + event_mps
    selected_mp_id = request.args.get("mp_view_id") or request.form.get("mp_view_id") or ""
    selected_mp = None
    selected_mp_top: List[Dict[str, Any]] = []
    if selected_mp_id:
        for mp in mp_selector_options:
            if str(mp.get("id")) == str(selected_mp_id):
                selected_mp = mp
                lb = mp.get("leaderboard") or []
                selected_mp_top = list(lb[:top_n])
                break
    if not selected_mp and current_mp:
        selected_mp = current_mp
        selected_mp_top = current_mp_top

    # Donation planner state (very simple version – just show totals)
    planner_state_json = "[]"
    planner_result: Optional[Dict[str, Any]] = None
    if request.method == "POST" and (request.form.get("calc_action") == "recalc"):
        planner_state_json = request.form.get("calc_state") or "[]"
        try:
            rows = json.loads(planner_state_json)
        except Exception:
            rows = []
        resources = [
            {"symbol": r.get("token"), "amount": float(r.get("amount") or 0.0)}
            for r in rows
            if r.get("token") and float(r.get("amount") or 0.0) > 0
        ]
        if resources and current_mp:
            try:
                data = predict_reward(str(current_mp["id"]), resources)
                planner_result = {
                    "mp": float(data.get("masterpiecePoints", 0) or 0.0),
                    "xp": float(data.get("experiencePoints", 0) or 0.0),
                }
            except Exception as e:
                error = error or f"Error predicting reward: {e}"

    content = """
    <h1>🏛 Masterpiece Hub</h1>
    <p class="subtle">
      Plan donations, watch the live race, and browse past &amp; event Masterpieces —
      all wired directly to <code>predictReward</code>.
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

    {% if error %}
      <div class="error">{{ error }}</div>
    {% endif %}

    <div class="mp-tab-bar">
      <div class="mp-tab" data-mp-tab="planner">Planner</div>
      <div class="mp-tab" data-mp-tab="current">Current</div>
      <div class="mp-tab" data-mp-tab="history">History</div>
    </div>

    <!-- Planner (very simple for now) -->
    <div class="mp-section" data-mp-section="planner">
      {% if current_mp %}
        <p class="subtle">
          Current MP: <strong>MP {{ current_mp.id }}</strong> —
          {{ current_mp.name or current_mp.addressableLabel or current_mp.type }}
        </p>
        <p class="hint">
          (Planner UI is simplified here; you can extend it later with full per-resource rows.)
        </p>
      {% else %}
        <p class="hint">No active masterpiece detected.</p>
      {% endif %}
      {% if planner_result %}
        <p class="hint">
          Bundle total: <strong>{{ planner_result.mp|round(2) }}</strong> MP points,
          <strong>{{ planner_result.xp|round(2) }}</strong> XP.
        </p>
      {% endif %}
    </div>

    <!-- Current leaderboard -->
    <div class="mp-section" data-mp-section="current" style="display:none;">
      {% if current_mp %}
        <h2>Live leaderboard — current masterpiece</h2>
        <p class="subtle">
          MP {{ current_mp.id }} — {{ current_mp.name or current_mp.addressableLabel or current_mp.type }}<br>
          Showing top {{ current_mp_top|length }} players (Top {{ top_n }}).
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
          <span class="hint">Up to Top 100.</span>
        </form>

        {% if current_mp_top %}
          <div class="mp-table-wrap">
            <table>
              <tr>
                <th>Pos</th>
                <th>Player</th>
                <th>Points</th>
              </tr>
              {% for row in current_mp_top %}
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
                  <td>{{ row.masterpiecePoints|int }}</td>
                </tr>
              {% endfor %}
            </table>
          </div>
        {% else %}
          <p class="hint">No leaderboard data yet.</p>
        {% endif %}
      {% else %}
        <p class="hint">No active masterpiece detected.</p>
      {% endif %}
    </div>

    <!-- History -->
    <div class="mp-section" data-mp-section="history" style="display:none;">
      <h2>History &amp; events</h2>
      <p class="subtle">
        Inspect the top <strong>{{ top_n }}</strong> positions for any general or event masterpiece.
      </p>

      {% if general_mps or event_mps %}
        <form method="get" class="mp-selector-form" style="margin-bottom:12px;">
          <label for="mp_view_id">Choose a masterpiece</label>
          <select id="mp_view_id" name="mp_view_id" style="max-width:320px;">
            {% if general_mps %}
              <optgroup label="General masterpieces">
                {% for mp in general_mps %}
                  <option value="{{ mp.id }}"
                    {% if selected_mp and mp.id == selected_mp.id %}selected{% endif %}>
                    MP {{ mp.id }} — {{ mp.name or mp.addressableLabel or mp.type }}
                    {% if current_mp and mp.id == current_mp.id %}(current){% endif %}
                  </option>
                {% endfor %}
              </optgroup>
            {% endif %}
            {% if event_mps %}
              <optgroup label="Event masterpieces">
                {% for mp in event_mps %}
                  <option value="{{ mp.id }}"
                    {% if selected_mp and mp.id == selected_mp.id %}selected{% endif %}>
                    MP {{ mp.id }} — {{ mp.name or mp.addressableLabel or mp.type }}
                  </option>
                {% endfor %}
              </optgroup>
            {% endif %}
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
      {% else %}
        <p class="hint">No masterpieces available to browse.</p>
      {% endif %}

      {% if selected_mp_top and selected_mp %}
        <div class="hint" style="margin-bottom:6px;">
          Showing top {{ selected_mp_top|length }} positions for
          <strong>
            MP {{ selected_mp.id }} — {{ selected_mp.name or selected_mp.addressableLabel or selected_mp.type }}
          </strong>.
        </div>
        <div class="mp-table-wrap">
          <table>
            <tr>
              <th>Pos</th>
              <th>Player</th>
              <th>Points</th>
            </tr>
            {% for row in selected_mp_top %}
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
                <td>{{ row.masterpiecePoints|int }}</td>
              </tr>
            {% endfor %}
          </table>
        </div>
      {% elif general_mps or event_mps %}
        <p class="hint">Select a masterpiece above to view its leaderboard.</p>
      {% else %}
        <p class="hint">No leaderboard data available.</p>
      {% endif %}
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
            sec.style.display = (s === name) ? 'block' : 'none';
          });
        }

        const params = new URLSearchParams(window.location.search);
        let currentTab = params.get('tab') || 'planner';
        activate(currentTab);

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

    inner = render_template_string(
        content,
        error=error,
        current_mp=current_mp,
        current_mp_top=current_mp_top,
        general_mps=general_mps,
        event_mps=event_mps,
        selected_mp=selected_mp,
        selected_mp_top=selected_mp_top,
        mp_selector_options=mp_selector_options,
        top_n=top_n,
        top_n_options=TOP_N_OPTIONS,
        highlight_query=highlight_query,
    )
    return render_template_string(
        BASE_TEMPLATE,
        content=inner,
        active_page="masterpieces",
    )
@app.route("/snipe", methods=["GET", "POST"])
def snipe():
    """
    Simple Masterpiece snipe helper.

    - Pick a masterpiece
    - Pick a single resource token
    - Enter target rank + your current points
    - We read the live leaderboard and use predictReward + live COIN prices
      to estimate how much you need.
    """
    error: Optional[str] = None
    rank_result: Optional[Dict[str, Any]] = None

    # Load masterpieces list for dropdown
    try:
        all_mps = fetch_masterpieces()
    except Exception as e:
        all_mps = []
        error = f"Error fetching masterpieces list: {e}"

    # Sort newest first by id
    def _mp_id(mp: Dict[str, Any]) -> int:
        try:
            return int(mp.get("id") or 0)
        except Exception:
            return 0

    all_mps = sorted(all_mps, key=_mp_id, reverse=True)

    mp_choices = [
        {
            "id": str(mp.get("id")),
            "label": f"MP{mp.get('id')} – {mp.get('name') or 'unknown'}",
        }
        for mp in all_mps
    ]

    selected_mp_id = ""
    selected_symbol = ""
    target_rank_str = ""
    my_points_str = ""

    if request.method == "POST":
        selected_mp_id = (request.form.get("masterpiece_id") or "").strip()
        selected_symbol = (request.form.get("symbol") or "").strip().upper()
        target_rank_str = (request.form.get("target_rank") or "").strip()
        my_points_str = (request.form.get("my_points") or "").strip()

        if not selected_mp_id:
            error = "Please choose a masterpiece."
        elif not selected_symbol:
            error = "Please enter a resource symbol (e.g. MUD, GAS)."
        else:
            # Parse numeric inputs
            try:
                target_rank = int(target_rank_str or "0")
            except ValueError:
                target_rank = 0
            try:
                my_points = float(my_points_str or "0")
            except ValueError:
                my_points = 0.0

            if target_rank <= 0:
                error = "Enter a target rank (e.g. 10)."
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
                        error = f"Could not find rank {target_rank} on this leaderboard."
                    else:
                        target_points = float(target_entry.get("masterpiecePoints") or 0.0)
                        # Add +1 so you actually pass them
                        points_needed = max(0.0, target_points - my_points + 1.0)

                        # Use predictReward for 1 unit of this resource to get points per unit
                        reward = predict_reward(
                            str(selected_mp_id),
                            [{"symbol": selected_symbol, "amount": 1}],
                        )
                        points_per_unit = float(reward.get("masterpiecePoints") or 0.0)
                        battery_per_unit = float(reward.get("requiredPower") or 0.0)
                        price_coin = float(prices.get(selected_symbol, 0.0))

                        if points_per_unit <= 0:
                            error = (
                                f"predictReward returned 0 pts for 1 {selected_symbol}. "
                                "This resource may not be valid for this masterpiece."
                            )
                        else:
                            units_needed = math.ceil(points_needed / points_per_unit)
                            total_points = units_needed * points_per_unit
                            total_battery = units_needed * battery_per_unit
                            total_coin = units_needed * price_coin

                            rank_result = {
                                "mp": mp,
                                "target_rank": target_rank,
                                "target_points": target_points,
                                "my_points": my_points,
                                "points_needed": points_needed,
                                "symbol": selected_symbol,
                                "points_per_unit": points_per_unit,
                                "battery_per_unit": battery_per_unit,
                                "price_coin": price_coin,
                                "units_needed": units_needed,
                                "total_points": total_points,
                                "total_battery": total_battery,
                                "total_coin": total_coin,
                            }

                except Exception as e:
                    error = f"Error calculating snipe: {e}"

    content = """
    <h1>🎯 Masterpiece Rank Snipe (single resource)</h1>
    <p class="subtle">
      Pick a masterpiece, a resource token, and a target rank. We read the live leaderboard
      and use <code>predictReward</code> + live COIN prices to estimate how much you need.
    </p>

    <form method="post" style="margin-top:12px;margin-bottom:16px;">
      <div style="display:flex;flex-wrap:wrap;gap:12px;align-items:flex-end;">
        <div style="flex:2;min-width:220px;">
          <label for="masterpiece_id">Masterpiece</label>
          <select id="masterpiece_id" name="masterpiece_id" style="width:100%;">
            <option value="">(choose masterpiece)</option>
            {% for mp in mp_choices %}
              <option value="{{ mp.id }}" {% if mp.id == selected_mp_id %}selected{% endif %}>
                {{ mp.label }}
              </option>
            {% endfor %}
          </select>
        </div>
        <div style="flex:1;min-width:120px;">
          <label for="symbol">Resource symbol</label>
          <input id="symbol" name="symbol" value="{{ selected_symbol }}" placeholder="MUD, GAS, CEMENT…" />
        </div>
        <div style="flex:1;min-width:120px;">
          <label for="target_rank">Target rank</label>
          <input type="number" id="target_rank" name="target_rank" value="{{ target_rank_str }}" />
        </div>
        <div style="flex:1;min-width:160px;">
          <label for="my_points">Your current points</label>
          <input type="number" step="1" id="my_points" name="my_points" value="{{ my_points_str }}" />
        </div>
        <div style="flex:0;min-width:140px;display:flex;justify-content:flex-start;">
          <button type="submit">Calc snipe</button>
        </div>
      </div>
    </form>

    {% if error %}
      <div class="error">{{ error }}</div>
    {% endif %}

    {% if rank_result %}
      <div class="card" style="margin-top:10px;">
        <h2>{{ rank_result.mp.name }} – snipe to rank {{ rank_result.target_rank }}</h2>
        <p class="subtle">
          Target points (rank {{ rank_result.target_rank }}):
          {{ "{:,0f}".format(rank_result.target_points) }}<br>
          Your current points:
          {{ "{:,0f}".format(rank_result.my_points) }}<br>
          <strong>Points needed to pass:</strong>
          {{ "{:,0f}".format(rank_result.points_needed) }}
        </p>

        <h3>Resource choice</h3>
        <p>
          Resource: <code>{{ rank_result.symbol }}</code><br>
          Points per 1 {{ rank_result.symbol }}:
          {{ "{:.4f}".format(rank_result.points_per_unit) }} pts<br>
          Battery per 1 {{ rank_result.symbol }}:
          {{ "{:.4f}".format(rank_result.battery_per_unit) }}<br>
          Price:
          {{ "{:.6f}".format(rank_result.price_coin) }} COIN / unit
        </p>

        <h3>Totals</h3>
        <p>
          Units needed:
          {{ "{:,}".format(rank_result.units_needed) }} {{ rank_result.symbol }}<br>
          Total points gained:
          {{ "{:,0f}".format(rank_result.total_points) }}<br>
          Total battery:
          {{ "{:,0f}".format(rank_result.total_battery) }}<br>
          Total COIN cost:
          {{ "{:.4f}".format(rank_result.total_coin) }} COIN
        </p>
      </div>
    {% endif %}
    """

    inner = render_template_string(
        content,
        error=error,
        mp_choices=mp_choices,
        selected_mp_id=selected_mp_id,
        selected_symbol=selected_symbol,
        target_rank_str=target_rank_str,
        my_points_str=my_points_str,
        rank_result=rank_result,
    )
    return render_template_string(
        BASE_TEMPLATE,
        content=inner,
        active_page="snipe",
    )


# -------------------------------------------------
# Entry point
# -------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)

