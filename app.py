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


# -------------------------------------------------
# Entry point
# -------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
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

            <!-- Right: planner form & results -->
            <div class="section">
              <form method="post">
                <input type="hidden" name="calc_state" value='{{ calc_state_json }}'>

                <h2 style="margin-top:0;">Build a donation bundle</h2>
                <p class="subtle">
                  Choose resources, set amounts, and we&apos;ll predict total
                  <strong>MP points</strong>, <strong>XP</strong>, and <strong>COIN cost</strong>
                  using the current general Masterpiece.
                </p>

                <div class="two-col" style="gap:10px;">
                  <div>
                    <label for="calc_token">Resource</label>
                    <select id="calc_token" name="calc_token">
                      <option value="">-- Choose resource --</option>
                      {% for tok in ALL_FACTORY_TOKENS %}
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
                      </tr>
                      {% for row in calc_resources %}
                        <tr>
                          <td>{{ row.token }}</td>
                          <td style="text-align:right;">{{ row.amount }}</td>
                          <td style="text-align:right;">{{ row.points_str or "—" }}</td>
                          <td style="text-align:right;">{{ row.xp_str or "—" }}</td>
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
                      <div class="mp-stat-label">Total cost</div>
                      <div class="mp-stat-value">COIN {{ calc_result.total_cost_str }}</div>
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
                        <td>{{ row.masterpiecePoints | int }}</td>
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

            {% if selected_mp_top50 and selected_mp %}
              <div class="hint" style="margin-bottom:6px;">
                Showing top {{ selected_mp_top50|length }} positions for
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
                      <td>{{ row.masterpiecePoints | int }}</td>
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
        </div>
"""

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
        masterpieces=masterpieces_data,
        general_mps=general_mps,
        event_mps=event_mps,
        tier_rows=tier_rows,
        ALL_FACTORY_TOKENS=ALL_FACTORY_TOKENS,
        calc_resources=calc_resources,
        calc_result=calc_result,
        calc_state_json=calc_state_json,
        current_mp=current_mp,
        current_mp_top50=current_mp_top50,
        mp_selector_options=mp_selector_options,
        selected_mp=selected_mp,
        selected_mp_top50=selected_mp_top50,
        selected_mp_id=selected_mp_id,
        top_n=top_n,
        top_n_options=TOP_N_OPTIONS,
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





































