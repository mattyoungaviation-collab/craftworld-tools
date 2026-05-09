"""Lookup page handlers.

These handlers were migrated out of app.py.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from flask import jsonify, redirect, render_template_string, request, session, url_for

from craftworld_api import fetch_craftworld, fetch_profile_by_uid
from pricing import fetch_live_prices_in_coin

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


def mastery_view():
    """
    Read your account proficiencies (mastery) + workshop levels via GraphQL
    and show a combined table, similar to craftworld.tips.
    Handles unauthenticated / missing JWT with a friendly message.
    """
    error = None
    rows: List[dict] = []

    try:
        bearer_token = _get_request_cw_token()
        profs = fetch_proficiencies(bearer_token=bearer_token)       # { "MUD": {"collectedAmount": ..., "claimedLevel": ...}, ... }
        ws_levels = fetch_workshop_levels(bearer_token=bearer_token) # { "MUD": 2, "CLAY": 5, ... }

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


def player_view(uid: str):
    """
    Simple player dashboard:
      - Profile info (name, wallet, ENS, avatar)
      - Land plots (event plots first, then standard)
      - Inventory
      - Masterpiece position + point detector for the selected MP (if mp_id is provided)
    """
    error: Optional[str] = None
    profile: Optional[Dict[str, Any]] = None
    account: Optional[Dict[str, Any]] = None
    mp: Optional[Dict[str, Any]] = None
    gap: Optional[Dict[str, Any]] = None

    # These are for the template
    event_plots: List[Dict[str, Any]] = []
    standard_plots: List[Dict[str, Any]] = []
    donation_rows: List[Dict[str, Any]] = []
    donation_summary: Optional[Dict[str, Any]] = None
    battery_plan_rows: List[Dict[str, Any]] = []

    mp_id = (request.args.get("mp_id") or "").strip() or None

    # 1) Profile (name, avatar, wallet, etc.)
    try:
        profile = fetch_profile_by_uid(uid)
    except Exception as e:
        error = f"Error fetching profile: {e}"

    # 2) Full account data (resources, land, etc.)
    try:
        account = fetch_craftworld(uid)
    except Exception as e:
        if error:
            error += f" | Error fetching account: {e}"
        else:
            error = f"Error fetching account: {e}"

    # 2a) Split land plots into event vs standard and flatten factories/levels
    if account:
        try:
            from math import isnan  # just in case we ever need it, safe import

            land_plots = attr_or_key(account, "landPlots", []) or []
            for plot in land_plots:
                plot_name = attr_or_key(plot, "symbol", "") or str(
                    attr_or_key(plot, "id", "")
                )
                # Heuristic: treat any plot with eventId / isEvent as an event plot
                is_event_plot = bool(
                    attr_or_key(plot, "eventId", None)
                    or attr_or_key(plot, "isEvent", False)
                )

                areas_raw = attr_or_key(plot, "areas", []) or []
                areas: List[Dict[str, Any]] = []

                for area in areas_raw:
                    area_symbol = attr_or_key(area, "symbol", "") or ""
                    factories_raw = attr_or_key(area, "factories", []) or []
                    factories_list: List[Dict[str, Any]] = []

                    for facwrap in factories_raw:
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
                        csv_level = api_level + 1  # API level is 0-based

                        factories_list.append(
                            {
                                "token": str(token),
                                "level": csv_level,
                            }
                        )

                    areas.append(
                        {
                            "symbol": area_symbol,
                            "factories": factories_list,
                        }
                    )

                row = {
                    "name": plot_name,
                    "is_event": is_event_plot,
                    "areas": areas,
                }
                if is_event_plot:
                    event_plots.append(row)
                else:
                    standard_plots.append(row)

            # Sort plots by name for a clean display
            event_plots.sort(key=lambda p: p["name"])
            standard_plots.sort(key=lambda p: p["name"])
        except Exception as e:
            if error:
                error += f" | Error processing land plots: {e}"
            else:
                error = f"Error processing land plots: {e}"

    # 3) Position on a specific masterpiece, if mp_id provided
    if mp_id:
        try:
            mp = fetch_masterpiece_details(mp_id)
            lb = mp.get("leaderboard") or []
            gap = compute_leaderboard_gap_for_highlight(lb, uid)
        except Exception as e:
            if error:
                error += f" | Error fetching masterpiece stats: {e}"
            else:
                error = f"Error fetching masterpiece stats: {e}"

    # 4) Point detector: compute points / battery from inventory for this MP
    if mp_id and account:
        try:
            resources = attr_or_key(account, "resources", []) or []
            symbols: List[str] = []
            for r in resources:
                sym = (attr_or_key(r, "symbol", "") or "").upper()
                if sym:
                    symbols.append(sym)

            per_unit = get_mp_per_unit_rewards(mp_id, symbols)
            pts_per = per_unit.get("points", {}) or {}
            power_per = per_unit.get("power", {}) or {}

            total_points_all = 0.0
            total_battery_all = 0.0

            # Build base rows for each resource that actually gives MP points
            for r in resources:
                sym = (attr_or_key(r, "symbol", "") or "").upper()
                if not sym:
                    continue
                try:
                    amt = float(attr_or_key(r, "amount", 0.0) or 0.0)
                except Exception:
                    amt = 0.0
                if amt <= 0:
                    continue

                ppu = float(pts_per.get(sym, 0.0) or 0.0)          # points per unit
                bpu = float(power_per.get(sym, 0.0) or 0.0)        # battery per unit
                if ppu <= 0 or bpu <= 0:
                    continue

                total_pts = amt * ppu
                total_batt = amt * bpu
                eff = ppu / bpu if bpu > 0 else 0.0  # points per battery

                total_points_all += total_pts
                total_battery_all += total_batt

                donation_rows.append(
                    {
                        "symbol": sym,
                        "amount": amt,
                        "points_per_unit": ppu,
                        "battery_per_unit": bpu,
                        "efficiency": eff,
                        "total_points": total_pts,
                        "total_battery": total_batt,
                    }
                )

            # Sort by efficiency (points per battery), best first
            donation_rows.sort(key=lambda row: row["efficiency"], reverse=True)

            # Now create a simple battery-budget plan for 15,000 battery
            BATTERY_BUDGET = 15_000.0
            remaining_batt = BATTERY_BUDGET
            points_15000 = 0.0
            battery_used_15000 = 0.0

            for row in donation_rows:
                if remaining_batt <= 0:
                    break
                bpu = row["battery_per_unit"]
                if bpu <= 0:
                    continue

                max_batt_for_token = bpu * row["amount"]
                use_batt = min(remaining_batt, max_batt_for_token)
                if use_batt <= 0:
                    continue

                units = use_batt / bpu
                pts = units * row["points_per_unit"]

                battery_used_15000 += use_batt
                points_15000 += pts
                remaining_batt -= use_batt

                battery_plan_rows.append(
                    {
                        "symbol": row["symbol"],
                        "units": units,
                        "battery": use_batt,
                        "points": pts,
                        "efficiency": row["efficiency"],
                    }
                )

            if donation_rows:
                donation_summary = {
                    "total_points_all": total_points_all,
                    "total_battery_all": total_battery_all,
                    "battery_budget": BATTERY_BUDGET,
                    "battery_used_15000": battery_used_15000,
                    "points_15000": points_15000,
                }
        except Exception as e:
            if error:
                error += f" | Error computing donation stats: {e}"
            else:
                error = f"Error computing donation stats: {e}"

    # Render inner content
    content_html = render_template_string(
        PLAYER_VIEW_TEMPLATE,
        error=error,
        uid=uid,
        profile=profile or {},
        account=account or {},
        mp=mp,
        gap=gap,
        event_plots=event_plots,
        standard_plots=standard_plots,
        donation_rows=donation_rows,
        donation_summary=donation_summary,
        battery_plan_rows=battery_plan_rows,
    )

    # Wrap in your base layout
    html = render_template_string(
        BASE_TEMPLATE,
        content=content_html,
        active_page="player",
        has_uid=has_uid_flag(),
    )
    return html

