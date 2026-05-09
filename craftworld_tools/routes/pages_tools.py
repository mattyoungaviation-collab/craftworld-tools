"""Tool page handlers.

These handlers were migrated out of app.py.
"""

from __future__ import annotations

import json
import math
from typing import Any, Dict, List, Optional

from flask import jsonify, redirect, render_template_string, request, session, url_for

from crafting_planner import CRAFTING_CHAINS, Modifiers, build_chain_report, plan_craft, rank_opportunities
from factories import FACTORIES_FROM_CSV, FACTORY_DISPLAY_INDEX, FACTORY_DISPLAY_ORDER, compute_best_setups_csv, compute_factory_result_csv
from pricing import TOKEN_ADDRESSES, fetch_buy_sell_for_profitability, fetch_live_prices_in_coin

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


def upgrade_calculate():
    error: Optional[str] = None
    result = None

    factories = FACTORIES_FROM_CSV or {}
    all_tokens = list(factories.keys())
    tokens: List[str] = [t for t in FACTORY_DISPLAY_ORDER if t in factories]
    for tok in sorted(all_tokens):
        if tok not in tokens:
            tokens.append(tok)

    selected_token = tokens[0] if tokens else ""
    mode = "next"
    count = 1
    current_level: Optional[int] = None
    target_level: Optional[int] = None

    def get_highest_owned_levels() -> Dict[str, int]:
        uid = session.get("voya_uid")
        if not uid:
            return {}

        highest: Dict[str, int] = {}
        try:
            cw = fetch_craftworld(uid)
            land_plots = attr_or_key(cw, "landPlots", []) or []
            for plot in land_plots:
                areas = attr_or_key(plot, "areas", []) or []
                for area in areas:
                    factories_wrapped = attr_or_key(area, "factories", []) or []
                    for facwrap in factories_wrapped:
                        fac = attr_or_key(facwrap, "factory", None)
                        if not fac:
                            continue
                        definition = attr_or_key(fac, "definition", {}) or {}
                        token = str(attr_or_key(definition, "id", "") or "").upper()
                        if not token:
                            continue
                        api_level = int(attr_or_key(fac, "level", 0) or 0)
                        csv_level = api_level + 1
                        if csv_level > int(highest.get(token, 0)):
                            highest[token] = csv_level
        except Exception:
            return {}

        return highest

    owned_highest_levels = get_highest_owned_levels()

    def get_default_current_level(token: str, levels: List[int]) -> Optional[int]:
        if not levels:
            return None
        owned_level = int(owned_highest_levels.get(token, 0) or 0)
        if owned_level in levels:
            return owned_level
        if session.get("voya_uid"):
            return 1 if 1 in levels else levels[0]
        return 1 if 1 in levels else levels[0]

    def get_upgrade_cost_for_level(token: str, level: int) -> Dict[str, float]:
        token_u = str(token or "").upper()
        if level <= 1:
            return {}

        level_data = factories.get(token_u, {}).get(level) or {}
        if not isinstance(level_data, dict):
            return {}

        out: Dict[str, float] = {}

        def _add_resource(res_token: Any, res_amount: Any) -> None:
            sym = str(res_token or "").strip().upper()
            if not sym:
                return
            try:
                amt = float(res_amount or 0.0)
            except Exception:
                return
            if amt <= 0:
                return
            out[sym] = out.get(sym, 0.0) + amt

        if isinstance(level_data.get("upgrade"), dict):
            for sym, amt in level_data["upgrade"].items():
                _add_resource(sym, amt)

        for key in ("upgrade_inputs", "upgrade_cost"):
            value = level_data.get(key)
            if isinstance(value, dict):
                for sym, amt in value.items():
                    _add_resource(sym, amt)
            elif isinstance(value, list):
                for row in value:
                    if isinstance(row, dict):
                        _add_resource(
                            row.get("token") or row.get("symbol") or row.get("resource"),
                            row.get("amount") or row.get("qty") or row.get("value"),
                        )

        _add_resource(level_data.get("upgrade_token"), level_data.get("upgrade_amount"))

        for key, value in level_data.items():
            if not (isinstance(key, str) and key.startswith("upgrade_") and key.endswith("_token")):
                continue
            mid = key[len("upgrade_") : -len("_token")]
            if not mid:
                continue
            amount_key = f"upgrade_{mid}_amount"
            _add_resource(value, level_data.get(amount_key))

        return out

    def get_buy_prices_in_coin(symbols: List[str]) -> Dict[str, float]:
        symbols_u = sorted({str(sym or "").upper() for sym in symbols if str(sym or "").strip()})
        if not symbols_u:
            return {"COIN": 1.0}

        price_map: Dict[str, float] = {}
        try:
            quote_map = fetch_buy_sell_for_profitability(symbols_u)
            for sym in symbols_u:
                rec = quote_map.get(sym, {}) or {}
                if "BUY" in rec:
                    price_map[sym] = float(rec.get("BUY", 0.0) or 0.0)
                elif "SELL" in rec:
                    price_map[sym] = float(rec.get("SELL", 0.0) or 0.0)
                else:
                    price_map[sym] = 0.0
        except Exception:
            for sym in symbols_u:
                price_map[sym] = 0.0

        price_map.setdefault("COIN", 1.0)
        return price_map

    def sum_upgrade_cost(token: str, start_level: int, end_level: int, count_n: int, prices: Dict[str, Any]) -> Any:
        totals: Dict[str, float] = {}
        steps: List[Dict[str, Any]] = []

        for to_level in range(start_level + 1, end_level + 1):
            step_resources = get_upgrade_cost_for_level(token, to_level)
            scaled: Dict[str, float] = {}
            step_rows: List[Dict[str, Any]] = []
            coin_subtotal = 0.0

            for sym, amt in step_resources.items():
                total_amt = float(amt) * count_n
                scaled[sym] = scaled.get(sym, 0.0) + total_amt
                totals[sym] = totals.get(sym, 0.0) + total_amt

                price_coin = float(prices.get(sym, 0.0) or 0.0)
                coin_total = total_amt * price_coin
                coin_subtotal += coin_total
                step_rows.append(
                    {
                        "resource": sym,
                        "amount": total_amt,
                        "price_coin": price_coin,
                        "coin_total": coin_total,
                    }
                )

            steps.append(
                {
                    "from_level": to_level - 1,
                    "to_level": to_level,
                    "resources": scaled,
                    "coin_subtotal": coin_subtotal,
                    "coin_breakdown_rows": sorted(step_rows, key=lambda r: r["resource"]),
                }
            )

        return totals, steps

    levels_for_selected = sorted(factories.get(selected_token, {}).keys()) if selected_token in factories else []
    if levels_for_selected:
        current_level = get_default_current_level(selected_token, levels_for_selected)
        next_default = (current_level or 0) + 1
        target_level = next_default if next_default in levels_for_selected else current_level

    if request.method == "POST":
        selected_token = request.form.get("factory", selected_token).strip().upper()
        mode = (request.form.get("mode", "next").strip() or "next").lower()
        if mode not in {"next", "range"}:
            mode = "next"

        try:
            count = max(1, int(request.form.get("count", "1").strip() or "1"))
        except Exception:
            count = 1

        if selected_token in factories:
            levels_for_selected = sorted(factories.get(selected_token, {}).keys())
        else:
            levels_for_selected = []

        if levels_for_selected:
            default_current = get_default_current_level(selected_token, levels_for_selected)
        else:
            default_current = None

        try:
            current_level = int((request.form.get("current_level", "").strip() or "0"))
        except Exception:
            current_level = default_current

        if current_level is None and default_current is not None:
            current_level = default_current

        fallback_target = None
        if current_level is not None:
            fallback_target = current_level + 1 if (current_level + 1) in levels_for_selected else current_level
        try:
            target_level = int((request.form.get("target_level", "").strip() or "0"))
        except Exception:
            target_level = fallback_target
        if target_level is None and fallback_target is not None:
            target_level = fallback_target

        try:
            live_prices = fetch_live_prices_in_coin() or {}
            _coin_usd = float(live_prices.get("_COIN_USD", 0.0))

            if selected_token not in factories:
                raise RuntimeError("Selected factory token was not found.")
            if not levels_for_selected:
                raise RuntimeError(f"No level data found for {selected_token}.")
            if current_level not in levels_for_selected:
                raise RuntimeError("Please choose a valid current level.")

            if mode == "next":
                next_level = current_level + 1
                if next_level not in levels_for_selected:
                    raise RuntimeError(f"No next level exists after L{current_level} for {selected_token}.")
                target_level = next_level
            else:
                if target_level not in levels_for_selected:
                    raise RuntimeError("Please choose a valid target level.")
                if target_level <= current_level:
                    raise RuntimeError("For range mode, target level must be greater than current level.")

            requested_symbols = set()
            for lvl in range(current_level + 1, target_level + 1):
                requested_symbols.update(get_upgrade_cost_for_level(selected_token, lvl).keys())
            prices = get_buy_prices_in_coin(sorted(requested_symbols))

            totals, steps = sum_upgrade_cost(selected_token, current_level, target_level, count, prices)
            resource_rows: List[Dict[str, Any]] = []
            total_coin = 0.0
            for sym in sorted(totals.keys()):
                amount = float(totals.get(sym, 0.0))
                price_coin = float(prices.get(sym, 0.0) or 0.0)
                coin_total = amount * price_coin
                total_coin += coin_total
                resource_rows.append(
                    {
                        "resource": sym,
                        "amount": amount,
                        "price_coin": price_coin,
                        "coin_total": coin_total,
                    }
                )

            breakdown_resources = sorted({r["resource"] for s in steps for r in s["coin_breakdown_rows"]})
            result = {
                "factory": selected_token,
                "count": count,
                "from_level": current_level,
                "to_level": target_level,
                "total_coin": total_coin,
                "resource_rows": resource_rows,
                "steps": steps,
                "breakdown_resources": breakdown_resources,
            }
        except Exception as e:
            error = str(e)

    levels_for_selected = sorted(factories.get(selected_token, {}).keys()) if selected_token in factories else []
    if current_level is None and levels_for_selected:
        current_level = get_default_current_level(selected_token, levels_for_selected)
    if target_level is None and current_level is not None:
        target_level = current_level + 1 if (current_level + 1) in levels_for_selected else current_level

    factory_levels = {tok: sorted(levels.keys()) for tok, levels in factories.items()}
    factory_levels_json = json.dumps(factory_levels)
    default_levels_json = json.dumps({tok: get_default_current_level(tok, lvls) for tok, lvls in factory_levels.items()})

    content = """
    <div class="card">
      <h1>Upgrade Calculate</h1>
      <p class="subtle">Calculate factory upgrade resources and COIN cost from one level to the next or across a full level range.</p>

      {% if error %}
        <div class="pill-bad" style="display:inline-block;margin-bottom:10px;">{{ error }}</div>
      {% endif %}

      <form method="post" style="margin-bottom: 12px;">
        <div style="display:flex;flex-wrap:wrap;gap:12px;align-items:flex-end;">
          <div style="flex:1;min-width:160px;">
            <label for="factory">Factory token</label>
            <select id="factory" name="factory" style="width:100%;">
              {% for tok in tokens %}
                <option value="{{ tok }}" {% if tok == selected_token %}selected{% endif %}>{{ tok }}</option>
              {% endfor %}
            </select>
          </div>

          <div style="flex:1;min-width:140px;">
            <label for="current_level">Current level</label>
            <select id="current_level" name="current_level" style="width:100%;">
              {% for lvl in levels_for_selected %}
                <option value="{{ lvl }}" {% if lvl == current_level %}selected{% endif %}>L{{ lvl }}</option>
              {% endfor %}
            </select>
          </div>

          <div style="flex:1;min-width:140px;">
            <label for="target_level">Target level</label>
            <select id="target_level" name="target_level" style="width:100%;">
              {% for lvl in levels_for_selected %}
                <option value="{{ lvl }}" {% if lvl == target_level %}selected{% endif %}>L{{ lvl }}</option>
              {% endfor %}
            </select>
          </div>

          <div style="min-width:110px;">
            <label for="count"># of factories</label>
            <input id="count" name="count" type="number" min="1" value="{{ count }}" style="width:100%;">
          </div>

          <div style="min-width:150px;">
            <label for="mode">Calculation mode</label>
            <select id="mode" name="mode" style="width:100%;">
              <option value="next" {% if mode == 'next' %}selected{% endif %}>Next level only</option>
              <option value="range" {% if mode == 'range' %}selected{% endif %}>Current to target range</option>
            </select>
          </div>

          <div>
            <button class="btn" type="submit">Calculate</button>
          </div>
        </div>
      </form>
    </div>

    {% if result %}
      <div class="card" style="margin-top:10px;">
        <h2>Upgrade Summary</h2>
        <p class="subtle">
          <strong>{{ result.factory }}</strong> × <strong>{{ result.count }}</strong><br>
          L{{ result.from_level }} → L{{ result.to_level }}
        </p>
        <p class="num" style="font-size:1.1rem;">Total COIN: {{ '%.6f'|format(result.total_coin) }}</p>

        <table>
          <thead>
            <tr>
              <th>Resource</th>
              <th>Amount</th>
              <th>Price (COIN)</th>
              <th>COIN Total</th>
            </tr>
          </thead>
          <tbody>
          {% for row in result.resource_rows %}
            <tr>
              <td>{{ row.resource }}</td>
              <td>{{ '%.6f'|format(row.amount) }}</td>
              <td>{{ '%.6f'|format(row.price_coin) }}</td>
              <td>{{ '%.6f'|format(row.coin_total) }}</td>
            </tr>
          {% endfor %}
          </tbody>
        </table>
      </div>

      <div class="card" style="margin-top:10px;">
        <button id="toggle-breakdown" class="btn" type="button">Show breakdown</button>
        <div id="breakdown-wrap" style="display:none;margin-top:10px;">
          <table>
            <thead>
              <tr>
                <th>Step</th>
                {% for sym in result.breakdown_resources %}
                  <th>{{ sym }}</th>
                {% endfor %}
                <th>COIN Subtotal</th>
              </tr>
            </thead>
            <tbody>
            {% for step in result.steps %}
              <tr>
                <td>L{{ step.from_level }}→L{{ step.to_level }}</td>
                {% for sym in result.breakdown_resources %}
                  <td>{{ '%.6f'|format(step.resources.get(sym, 0.0)) }}</td>
                {% endfor %}
                <td>{{ '%.6f'|format(step.coin_subtotal) }}</td>
              </tr>
            {% endfor %}
            </tbody>
          </table>
        </div>
      </div>
    {% endif %}

    <script>
      (function() {
        const factoryLevels = {{ factory_levels_json | safe }};
        const defaultLevels = {{ default_levels_json | safe }};
        const factorySelect = document.getElementById("factory");
        const currentSelect = document.getElementById("current_level");
        const targetSelect = document.getElementById("target_level");
        const modeSelect = document.getElementById("mode");

        function rebuildLevelOptions(token) {
          const levels = factoryLevels[token] || [];
          const currentValue = currentSelect.value;
          const targetValue = targetSelect.value;

          currentSelect.innerHTML = "";
          targetSelect.innerHTML = "";

          levels.forEach((lvl) => {
            const v = String(lvl);
            const cOpt = document.createElement("option");
            cOpt.value = v;
            cOpt.textContent = "L" + v;
            if (v === currentValue) cOpt.selected = true;
            currentSelect.appendChild(cOpt);

            const tOpt = document.createElement("option");
            tOpt.value = v;
            tOpt.textContent = "L" + v;
            if (v === targetValue) tOpt.selected = true;
            targetSelect.appendChild(tOpt);
          });

          if (levels.length) {
            const hasPriorCurrent = Array.from(currentSelect.options).some((o) => o.value === currentValue);
            if (hasPriorCurrent && currentValue) {
              currentSelect.value = currentValue;
            } else {
              const defaultCurrent = String(defaultLevels[token] || levels[0]);
              const hasDefault = Array.from(currentSelect.options).some((o) => o.value === defaultCurrent);
              currentSelect.value = hasDefault ? defaultCurrent : String(levels[0]);
            }
          }
          if (!targetSelect.value && levels.length) {
            const cur = Number(currentSelect.value || 0);
            targetSelect.value = levels.includes(cur + 1) ? String(cur + 1) : String(cur);
          }
        }

        function syncTargetForNextMode() {
          if (modeSelect.value !== "next") return;
          const cur = Number(currentSelect.value || 0);
          const candidate = String(cur + 1);
          const opt = Array.from(targetSelect.options).find((o) => o.value === candidate);
          if (opt) {
            targetSelect.value = candidate;
          }
        }

        if (factorySelect && currentSelect && targetSelect) {
          factorySelect.addEventListener("change", function() {
            rebuildLevelOptions(this.value);
            syncTargetForNextMode();
          });
          currentSelect.addEventListener("change", syncTargetForNextMode);
          modeSelect.addEventListener("change", syncTargetForNextMode);
          rebuildLevelOptions(factorySelect.value);
          syncTargetForNextMode();
        }

        const toggleBtn = document.getElementById("toggle-breakdown");
        const breakdown = document.getElementById("breakdown-wrap");
        if (toggleBtn && breakdown) {
          toggleBtn.addEventListener("click", function() {
            const show = breakdown.style.display === "none";
            breakdown.style.display = show ? "block" : "none";
            toggleBtn.textContent = show ? "Hide breakdown" : "Show breakdown";
          });
        }
      })();
    </script>
    """

    content = render_template_string(
        content,
        error=error,
        result=result,
        tokens=tokens,
        selected_token=selected_token,
        levels_for_selected=levels_for_selected,
        current_level=current_level,
        target_level=target_level,
        mode=mode,
        count=count,
        factory_levels_json=factory_levels_json,
        default_levels_json=default_levels_json,
    )

    html = render_template_string(
        BASE_TEMPLATE,
        content=content,
        active_page="upgrade_calculate",
        has_uid=has_uid_flag(),
    )
    return html


def factory_converter():
    error: Optional[str] = None
    result: Optional[Dict[str, Any]] = None

    factories = FACTORIES_FROM_CSV or {}
    all_tokens = list(factories.keys())
    tokens: List[str] = [t for t in FACTORY_DISPLAY_ORDER if t in factories]
    for tok in sorted(all_tokens):
        if tok not in tokens:
            tokens.append(tok)

    selected_token = tokens[0] if tokens else ""
    selected_level: Optional[int] = None
    mode = "input_to_output"
    quantity_value = 1.0
    selected_input_token = ""

    if request.method == "POST":
        selected_token = (request.form.get("factory") or selected_token).strip().upper()
        mode = (request.form.get("mode") or "input_to_output").strip()
        quantity_raw = (request.form.get("quantity") or "1").strip() or "1"
        level_str = (request.form.get("level") or "").strip()
        selected_input_token = (request.form.get("input_token") or "").strip().upper()

        try:
            quantity_value = float(quantity_raw)
        except Exception:
            quantity_value = 1.0
        quantity_value = max(0.0, quantity_value)

        try:
            if level_str:
                selected_level = int(level_str)
        except Exception:
            selected_level = None

        try:
            levels = sorted((factories.get(selected_token) or {}).keys())
            if not levels:
                raise RuntimeError(f"No recipe levels found for {selected_token}.")
            if selected_level is None:
                selected_level = levels[-1]

            recipe = (factories.get(selected_token) or {}).get(selected_level) or {}
            inputs: Dict[str, float] = dict(recipe.get("inputs") or {})
            if not inputs:
                raise RuntimeError("This factory has no input recipe in CSV data.")

            if selected_input_token not in inputs:
                selected_input_token = sorted(inputs.keys())[0]

            output_token = str(recipe.get("output_token") or selected_token).upper()
            output_amount = float(recipe.get("output_amount") or 0.0)
            input_amount = float(inputs.get(selected_input_token) or 0.0)
            if output_amount <= 0 or input_amount <= 0:
                raise RuntimeError("Invalid recipe amounts in CSV for selected factory/level.")

            ratio_out_per_in = output_amount / input_amount

            if mode == "output_to_input":
                output_qty = quantity_value
                input_qty = output_qty / ratio_out_per_in
            else:
                input_qty = quantity_value
                output_qty = input_qty * ratio_out_per_in

            prices = fetch_live_prices_in_coin() or {}
            in_price = float(prices.get(selected_input_token, 0.0) or 0.0)
            out_price = float(prices.get(output_token, 0.0) or 0.0)

            input_value_coin = input_qty * in_price
            output_value_coin = output_qty * out_price
            pnl_coin = output_value_coin - input_value_coin

            result = {
                "token": selected_token,
                "level": selected_level,
                "input_token": selected_input_token,
                "output_token": output_token,
                "input_qty": input_qty,
                "output_qty": output_qty,
                "ratio_out_per_in": ratio_out_per_in,
                "input_value_coin": input_value_coin,
                "output_value_coin": output_value_coin,
                "pnl_coin": pnl_coin,
                "input_price": in_price,
                "output_price": out_price,
            }
        except Exception as e:
            error = f"Error: {e}"

    levels_for_selected = (
        sorted(factories.get(selected_token, {}).keys())
        if selected_token in factories else []
    )
    if selected_level is None and levels_for_selected:
        selected_level = levels_for_selected[-1]

    recipe_for_selection = ((factories.get(selected_token) or {}).get(selected_level or -1) or {})
    input_options = sorted((recipe_for_selection.get("inputs") or {}).keys())
    if input_options and selected_input_token not in input_options:
        selected_input_token = input_options[0]

    factory_levels_json = json.dumps({tok: sorted(levels.keys()) for tok, levels in factories.items()})
    factory_inputs_json = json.dumps({
        tok: {str(lvl): sorted((data.get("inputs") or {}).keys()) for lvl, data in levels.items()}
        for tok, levels in factories.items()
    })

    content = render_template_string("""
    <div class="card">
      <h1>Factory Input/Output Converter + PnL</h1>
      <p class="subtle">Select a factory/level and convert either direction: input → output or output → required input. PnL is based on live COIN prices.</p>

      <form method="post">
        <div style="display:flex;flex-wrap:wrap;gap:12px;">
          <div style="flex:1;min-width:170px;">
            <label>Factory</label>
            <select id="factory" name="factory" style="width:100%;">
              {% for tok in tokens %}<option value="{{ tok }}" {% if tok == selected_token %}selected{% endif %}>{{ tok }}</option>{% endfor %}
            </select>
          </div>
          <div style="flex:1;min-width:120px;">
            <label>Level</label>
            <select id="level" name="level" style="width:100%;">
              {% for lvl in levels_for_selected %}<option value="{{ lvl }}" {% if lvl == selected_level %}selected{% endif %}>L{{ lvl }}</option>{% endfor %}
            </select>
          </div>
          <div style="flex:1;min-width:170px;">
            <label>Input token</label>
            <select id="input_token" name="input_token" style="width:100%;">
              {% for tok in input_options %}<option value="{{ tok }}" {% if tok == selected_input_token %}selected{% endif %}>{{ tok }}</option>{% endfor %}
            </select>
          </div>
          <div style="flex:1;min-width:190px;">
            <label>Conversion mode</label>
            <select name="mode" style="width:100%;">
              <option value="input_to_output" {% if mode=='input_to_output' %}selected{% endif %}>Input → Output</option>
              <option value="output_to_input" {% if mode=='output_to_input' %}selected{% endif %}>Output → Required Input</option>
            </select>
          </div>
          <div style="flex:1;min-width:160px;">
            <label>Quantity</label>
            <input name="quantity" type="number" step="0.000001" min="0" value="{{ quantity_value }}" style="width:100%;">
          </div>
        </div>
        <div style="margin-top:12px;">
          <button type="submit">Convert</button>
        </div>
      </form>

      {% if error %}<div class="error" style="margin-top:10px;">{{ error }}</div>{% endif %}

      {% if result %}
      <div class="card" style="margin-top:12px;">
        <h2>{{ result.token }} L{{ result.level }}</h2>
        <p class="subtle">
          Ratio: <strong>{{ "%.6f"|format(result.ratio_out_per_in) }}</strong> {{ result.output_token }} per 1 {{ result.input_token }}.
        </p>
        <p class="subtle">
          <strong>Input:</strong> {{ "%.6f"|format(result.input_qty) }} {{ result.input_token }}<br>
          <strong>Output:</strong> {{ "%.6f"|format(result.output_qty) }} {{ result.output_token }}
        </p>
        <p class="subtle">
          <strong>Input value:</strong> {{ "%.6f"|format(result.input_value_coin) }} COIN ({{ "%.6f"|format(result.input_price) }} each)<br>
          <strong>Output value:</strong> {{ "%.6f"|format(result.output_value_coin) }} COIN ({{ "%.6f"|format(result.output_price) }} each)<br>
          <strong>PnL:</strong>
          <span class="{{ 'pill' if result.pnl_coin >= 0 else 'pill-bad' }}">{{ "%+.6f"|format(result.pnl_coin) }} COIN</span>
        </p>
      </div>
      {% endif %}

      <script>
        (function() {
          const factoryLevels = {{ factory_levels_json | safe }};
          const factoryInputs = {{ factory_inputs_json | safe }};
          const factorySel = document.getElementById("factory");
          const levelSel = document.getElementById("level");
          const inputSel = document.getElementById("input_token");

          function rebuildLevelsAndInputs() {
            const tok = factorySel.value;
            const oldLevel = levelSel.value;
            const levels = factoryLevels[tok] || [];
            levelSel.innerHTML = "";
            levels.forEach((lvl) => {
              const o = document.createElement("option");
              o.value = String(lvl);
              o.textContent = "L" + lvl;
              if (String(lvl) === oldLevel) o.selected = true;
              levelSel.appendChild(o);
            });
            if (!levelSel.value && levels.length) levelSel.value = String(levels[levels.length - 1]);
            rebuildInputs();
          }
          function rebuildInputs() {
            const tok = factorySel.value;
            const lvl = levelSel.value;
            const oldInput = inputSel.value;
            const inputs = ((factoryInputs[tok] || {})[String(lvl)] || []);
            inputSel.innerHTML = "";
            inputs.forEach((inp) => {
              const o = document.createElement("option");
              o.value = inp;
              o.textContent = inp;
              if (inp === oldInput) o.selected = true;
              inputSel.appendChild(o);
            });
          }
          if (factorySel && levelSel && inputSel) {
            factorySel.addEventListener("change", rebuildLevelsAndInputs);
            levelSel.addEventListener("change", rebuildInputs);
          }
        })();
      </script>
    </div>
    """,
    tokens=tokens,
    selected_token=selected_token,
    levels_for_selected=levels_for_selected,
    selected_level=selected_level,
    input_options=input_options,
    selected_input_token=selected_input_token,
    mode=mode,
    quantity_value=quantity_value,
    result=result,
    error=error,
    factory_levels_json=factory_levels_json,
    factory_inputs_json=factory_inputs_json)

    html = render_template_string(
        BASE_TEMPLATE,
        content=content,
        active_page="factory_converter",
        has_uid=has_uid_flag(),
    )
    return html


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


def snipe():
    error: Optional[str] = None

    # Three possible result blocks
    rank_result: Optional[Dict[str, Any]] = None
    target_result: Optional[Dict[str, Any]] = None
    combo_result: Optional[Dict[str, Any]] = None
    analyze_result: Optional[Dict[str, Any]] = None

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

        elif mode == "analyze":
            if not selected_mp_id:
                error = "Please select a valid masterpiece."
            else:
                try:
                    mp = fetch_masterpiece_details(selected_mp_id)
                    prices = fetch_live_prices_in_coin()
                    rows = _build_resource_efficiency_rows(selected_mp_id, mp, prices)
                    analyze_result = {
                        "mp": mp,
                        "rows": rows,
                    }
                except Exception as e:
                    error = f"Error calculating efficiency snapshot: {e}"

        elif mode == "combo":
            combo_text = (request.form.get("combo_text") or "").strip()
            if not selected_mp_id:
                error = "Please select a valid masterpiece."
            elif not combo_text:
                error = "Enter at least one donation like: MUD=100000, GAS 42000, CEMENT:69"
            else:
                try:
                    # Parse text into list of {symbol, amount}
                    donations = _parse_donation_text(combo_text)

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
        Four tools: <strong>Rank snipe</strong>, <strong>Target points</strong>, <strong>Resource efficiency snapshot</strong>, and <strong>Combo donation</strong>.
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


      <!-- Resource efficiency snapshot -->
      <div class="card" style="margin-top:14px;">
        <h2>3) Resource Efficiency Snapshot</h2>
        <p class="subtle">Quickly compare COIN/point, battery usage, and remaining donation cap across all resources for a masterpiece.</p>
        <form method="post" style="margin-bottom:10px;">
          <input type="hidden" name="mode" value="analyze" />
          <div style="display:flex;flex-wrap:wrap;gap:12px;align-items:flex-end;">
            <div style="flex:2;min-width:220px;">
              <label for="masterpiece_id_a">Masterpiece</label>
              <select id="masterpiece_id_a" name="masterpiece_id" style="width:100%;">
                <option value="">(choose masterpiece)</option>
                {% for mp in mp_choices %}
                  <option value="{{ mp.id }}" {% if selected_mp_id==mp.id %}selected{% endif %}>{{ mp.label }}</option>
                {% endfor %}
              </select>
            </div>
            <div style="flex:1;min-width:140px;display:flex;justify-content:flex-start;">
              <button type="submit">Analyze efficiency</button>
            </div>
          </div>
        </form>

        {% if analyze_result %}
          <div class="card" style="margin-top:6px;">
            <h3>{{ analyze_result.mp.name }} – Efficiency snapshot</h3>
            {% if analyze_result.rows %}
              <div class="scroll-x">
                <table>
                  <tr>
                    <th>Resource</th>
                    <th>Points / unit</th>
                    <th>COIN / unit</th>
                    <th>COIN / point</th>
                    <th>Battery / unit</th>
                    <th>Remaining units</th>
                  </tr>
                  {% for r in analyze_result.rows %}
                    <tr>
                      <td>{{ r.symbol }}</td>
                      <td>{{ "{:,.2f}".format(r.points_per_unit) }}</td>
                      <td>{{ "{:,.6f}".format(r.price_coin) }}</td>
                      <td>
                        {% if r.coin_per_point is not none %}
                          {{ "{:,.8f}".format(r.coin_per_point) }}
                        {% else %}
                          N/A
                        {% endif %}
                      </td>
                      <td>{{ "{:,.2f}".format(r.battery_per_unit) }}</td>
                      <td>{{ "{:,.0f}".format(r.remaining) }}</td>
                    </tr>
                  {% endfor %}
                </table>
              </div>
            {% else %}
              <p class="subtle">No eligible resources found for this masterpiece.</p>
            {% endif %}
          </div>
        {% endif %}
      </div>

      <!-- Combo donation calculator -->
      <div class="card" style="margin-top:14px;">
        <h2>4) Combo Donation (multi-resource)</h2>
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
        analyze_result=analyze_result,
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

