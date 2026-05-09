"""Home page handler.

This handler was migrated out of app.py.
"""

from __future__ import annotations

import json
import math
from typing import Any, Dict, List, Optional

from flask import jsonify, redirect, render_template_string, request, session, url_for

from craftworld_api import fetch_available_avatars, fetch_craftworld, fetch_profile_by_uid
from factories import FACTORIES_FROM_CSV
from pricing import fetch_live_prices_in_coin

def index():
    error: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    uid = session.get("voya_uid", "")
    did_submit = request.method == "POST"

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
      <form method="post" id="overview-form" data-has-result="{{ 'true' if result else 'false' }}" data-has-attempted="{{ 'true' if did_submit else 'false' }}" data-auto-fetch="true">
        <label for="uid">Account ID</label>
        <input type="text" id="uid" name="uid" value="{{ uid }}" placeholder="e.g. GfUeRBCZv8OwuUKq7Tu9JVpA70l1">
        <button type="submit">Fetch Craft World</button>
        <div id="overview-auto-status" class="hint">Sign in with your wallet to auto-fill your Account ID.</div>
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
          <a href="{{ url_for('charts', token='DYNOFISH') }}" class="pill">🐟 Dyno Fish price</a>
        </div>
        <p class="subtle" style="margin-top:8px;">
          New to these tools? Click “Dyno Fish price” to jump straight to the live chart, or open <strong>Charts</strong> in the top navigation and pick <strong>DYNOFISH</strong> from the dropdown. Your latest changes are saved here automatically; no extra steps are needed.
        </p>
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
