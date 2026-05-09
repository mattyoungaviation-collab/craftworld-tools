"""Core page handlers.

These handlers were migrated out of app.py.
"""

from __future__ import annotations

import json
import math
from typing import Any, Dict, List, Optional

from flask import jsonify, redirect, render_template_string, request, session, url_for

from craftworld_api import fetch_available_avatars, fetch_craftworld, fetch_masterpiece_details, fetch_masterpieces, fetch_profile_by_uid, predict_reward
from crafting_planner import CRAFTING_CHAINS, Modifiers, build_chain_report, plan_craft, rank_opportunities
from factories import FACTORIES_FROM_CSV, FACTORY_DISPLAY_INDEX, FACTORY_DISPLAY_ORDER, MASTERY_BONUSES, WORKSHOP_MODIFIERS, compute_best_setups_csv, compute_factory_result_csv
from pricing import TOKEN_ADDRESSES, fetch_buy_sell_for_profitability, fetch_live_prices_in_coin
from craftworld_tools.services.masterpiece_view_model import build_masterpiece_summary_html

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
        Auto-fill from your connected Craft World account or edit manually.
      </p>

      <div id="boosts-banner" class="cw-status-banner" style="display:none; margin-bottom:10px;">
        <div class="summary" id="boosts-banner-text"></div>
      </div>

      <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:12px;">
        <button type="button" id="cw-boosts-autofill">Auto-fill from Craft World</button>
        <button type="button" id="cw-boosts-refresh">Refresh</button>
        <span class="hint" id="cw-boosts-last-synced">Last synced: never</span>
      </div>

      <form method="post" id="boosts-form">
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
                  <select name="mastery_{{ tok }}" class="cw-mastery-input" data-token="{{ tok }}" style="width:100px;">
                    {% for i in range(0, 11) %}
                    <option value="{{ i }}" {% if i == (lvl.get('mastery_level', 0)|int) %}selected{% endif %}>{{ i }}</option>
                    {% endfor %}
                  </select>
                </td>
                <td>
                  <select name="workshop_{{ tok }}" class="cw-workshop-input" data-token="{{ tok }}" style="width:100px;">
                    {% for i in range(0, 11) %}
                    <option value="{{ i }}" {% if i == (lvl.get('workshop_level', 0)|int) %}selected{% endif %}>{{ i }}</option>
                    {% endfor %}
                  </select>
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

    <script>
      (function () {
        const CW_SESSION_INDEX = 'cw_sessions';
        const CW_ACTIVE_WALLET = 'cw_active_wallet';
        const CW_TOKEN_KEY = 'cw_token';

        function normalizeWallet(value) {
          return String(value || '').trim().toLowerCase();
        }

        async function detectConnectedWallet() {
          if (typeof window === 'undefined') return '';
          const provider = window.ethereum;
          if (!provider || typeof provider.request !== 'function') return '';
          try {
            const accounts = await provider.request({ method: 'eth_accounts' });
            const addr = Array.isArray(accounts) && accounts.length ? accounts[0] : '';
            return normalizeWallet(addr);
          } catch (_) {
            return '';
          }
        }

        function getStoredActiveWallet() {
          return normalizeWallet(localStorage.getItem(CW_ACTIVE_WALLET) || '');
        }

        function readSessions() {
          try {
            const parsed = JSON.parse(localStorage.getItem(CW_SESSION_INDEX) || '{}');
            return parsed && typeof parsed === 'object' ? parsed : {};
          } catch (_) {
            return {};
          }
        }

        function getStoredTokenForWallet(wallet) {
          const normalized = normalizeWallet(wallet);
          if (!normalized) return '';
          const sessions = readSessions();
          return String((sessions[normalized] && sessions[normalized].token) || '').trim();
        }

        function getLegacyToken() {
          return String(localStorage.getItem(CW_TOKEN_KEY) || '').trim();
        }

        function getTokenForWalletOrLegacy(wallet) {
          const byWallet = getStoredTokenForWallet(wallet);
          if (byWallet) return byWallet;
          return getLegacyToken();
        }

        function getBoostStorageKey(wallet) {
          return `cw_boosts:${wallet}`;
        }

        function setBanner(text) {
          const wrap = document.getElementById('boosts-banner');
          const el = document.getElementById('boosts-banner-text');
          if (!wrap || !el) return;
          if (!text) {
            wrap.style.display = 'none';
            el.textContent = '';
            return;
          }
          wrap.style.display = 'block';
          el.textContent = text;
        }

        function setLastSynced(ts) {
          const el = document.getElementById('cw-boosts-last-synced');
          if (!el) return;
          if (!ts) {
            el.textContent = 'Last synced: never';
            return;
          }
          el.textContent = `Last synced: ${new Date(Number(ts)).toLocaleString()}`;
        }

        function hydrateBoostInputs(workshopLevels, masteryLevels) {
          document.querySelectorAll('.cw-workshop-input[data-token]').forEach((input) => {
            const tok = String(input.dataset.token || '').toUpperCase();
            if (!tok) return;
            if (Object.prototype.hasOwnProperty.call(workshopLevels, tok)) {
              input.value = String(Math.max(0, Math.min(10, Number(workshopLevels[tok] || 0))));
            }
          });
          document.querySelectorAll('.cw-mastery-input[data-token]').forEach((input) => {
            const tok = String(input.dataset.token || '').toUpperCase();
            if (!tok) return;
            if (Object.prototype.hasOwnProperty.call(masteryLevels, tok)) {
              input.value = String(Math.max(0, Math.min(10, Number(masteryLevels[tok] || 0))));
            }
          });
        }

        async function syncBoostsFromCraftWorld(walletHint) {
          const storedWallet = getStoredActiveWallet();
          const wallet = normalizeWallet(walletHint || storedWallet);
          const token = getTokenForWalletOrLegacy(wallet);
          if (!token) {
            setBanner('Not connected. Connect Ronin Wallet.');
            return null;
          }

          if (wallet && wallet !== storedWallet) {
            localStorage.setItem(CW_ACTIVE_WALLET, wallet);
          }

          const headers = { Authorization: `Bearer ${token}` };
          const [wsRes, profRes] = await Promise.all([
            fetch('/api/account_workshop', { headers }),
            fetch('/api/account_proficiencies', { headers }),
          ]);

          const workshopData = await wsRes.json();
          const profData = await profRes.json();

          if (!workshopData.ok || !profData.ok) {
            if ((workshopData.auth === 'missing_or_invalid') || (profData.auth === 'missing_or_invalid')) {
              setBanner('Session expired. Reconnect.');
            } else {
              setBanner("Couldn't fetch boosts. Retry.");
            }
            return null;
          }

          const workshopLevels = {};
          const masteryLevels = {};

          (workshopData.workshop || []).forEach((row) => {
            const symbol = String(row.symbol || '').toUpperCase();
            if (symbol) workshopLevels[symbol] = Number(row.level || 0);
          });
          (profData.proficiencies || []).forEach((row) => {
            const symbol = String(row.symbol || '').toUpperCase();
            if (symbol) masteryLevels[symbol] = Number(row.claimedLevel || 0);
          });

          const payload = { workshopLevels, masteryLevels, syncedAt: Date.now() };
          if (wallet) {
            localStorage.setItem(getBoostStorageKey(wallet), JSON.stringify(payload));
          }

          const persistRes = await fetch('/api/boosts/sync', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ workshopLevels, masteryLevels }),
          });
          const persistData = await persistRes.json().catch(() => ({}));
          if (!persistRes.ok || !persistData.ok) {
            setBanner("Fetched data, but couldn't save it to your account.");
          } else {
            setBanner('');
          }

          hydrateBoostInputs(workshopLevels, masteryLevels);
          setLastSynced(payload.syncedAt);
          return payload;
        }

        window.addEventListener('DOMContentLoaded', async function () {
          const autoBtn = document.getElementById('cw-boosts-autofill');
          const refreshBtn = document.getElementById('cw-boosts-refresh');
          const storedWallet = getStoredActiveWallet();
          const wallet = normalizeWallet(storedWallet);
          const token = getTokenForWalletOrLegacy(wallet);

          if (!token) {
            setBanner('Not connected. Connect Ronin Wallet.');
          } else {
            if (wallet && wallet !== storedWallet) {
              localStorage.setItem(CW_ACTIVE_WALLET, wallet);
            }
            const cachedRaw = wallet ? localStorage.getItem(getBoostStorageKey(wallet)) : '';
            if (cachedRaw) {
              try {
                const cached = JSON.parse(cachedRaw);
                hydrateBoostInputs(cached.workshopLevels || {}, cached.masteryLevels || {});
                setLastSynced(cached.syncedAt || 0);
              } catch (_) {
                await syncBoostsFromCraftWorld();
              }
            } else {
              await syncBoostsFromCraftWorld();
            }
          }

          if (autoBtn) {
            autoBtn.addEventListener('click', async () => {
              await syncBoostsFromCraftWorld();
            });
          }
          if (refreshBtn) {
            refreshBtn.addEventListener('click', async () => {
              await syncBoostsFromCraftWorld();
            });
          }
        });
      })();
    </script>
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

        <div class="table-scroll" style="margin-top:14px;">
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
    <td class="{{ 'num-positive' if r.profit_coin_per_craft >= 0 else 'num-negative' }}">{{ '%+.6f'|format(r.profit_coin_per_craft) }}</td>
    <td class="{{ 'num-positive' if r.margin_pct >= 0 else 'num-negative' }}">{{ '%+.2f'|format(r.margin_pct) }}</td>

    <td class="{{ 'num-positive' if r.profit_hour_per >= 0 else 'num-negative' }}">{{ '%+.6f'|format(r.profit_hour_per) }}</td>
    <td class="{{ 'num-positive' if r.profit_hour_total >= 0 else 'num-negative' }}">{{ '%+.6f'|format(r.profit_hour_total) }}</td>
    <td class="{{ 'num-positive' if r.profit_day_total >= 0 else 'num-negative' }}">{{ '%+.6f'|format(r.profit_day_total) }}</td>
    <td class="{{ 'num-positive' if r.usd_hour_total >= 0 else 'num-negative' }}">{{ '%+.4f'|format(r.usd_hour_total) }}</td>
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


def craft_profitability():
    error = None
    prices: Dict[str, float] = {}
    try:
        prices = fetch_live_prices_in_coin()
    except Exception as exc:
        error = f"Failed to fetch prices: {exc}"

    status = get_cached_account_status()
    boosts = get_boost_levels() or {}

    start_amount_raw = request.args.get("start_amount") or "1"
    try:
        start_amount = max(0.000001, float(start_amount_raw))
    except Exception:
        start_amount = 1.0

    selected_raw = request.args.get("chains") or ",".join(CRAFTING_CHAINS.keys())
    selected_chains = [c.strip() for c in selected_raw.split(",") if c.strip() in CRAFTING_CHAINS]
    if not selected_chains:
        selected_chains = list(CRAFTING_CHAINS.keys())

    mastery_levels: Dict[str, int] = {}
    workshop_levels: Dict[str, int] = {}
    for token, levels in boosts.items():
        token_u = str(token or "").upper()
        if token_u not in CRAFTING_CHAINS["EARTH ➜ SCREWS"] + CRAFTING_CHAINS["WATER ➜ OIL"] + CRAFTING_CHAINS["FIRE ➜ LAVA"]:
            continue
        try:
            mastery_levels[token_u] = max(0, min(10, int((levels or {}).get("mastery_level", 0))))
        except Exception:
            mastery_levels[token_u] = 0
        try:
            workshop_levels[token_u] = max(0, min(10, int((levels or {}).get("workshop_level", 0))))
        except Exception:
            workshop_levels[token_u] = 0

    modifiers = Modifiers(
        masteryLevelsBySymbol=mastery_levels,
        workshopLevelsByFactoryOrTier=workshop_levels,
        globalSpeedMultiplier=1.0,
    )

    chain_symbols = sorted({sym.upper() for chain in CRAFTING_CHAINS.values() for sym in chain})
    quote_map: Dict[str, Dict[str, float]] = {}
    try:
        quote_map = fetch_buy_sell_for_profitability(chain_symbols)
    except Exception:
        quote_map = {}

    input_price_book: Dict[str, float] = {}
    output_price_book: Dict[str, float] = {}
    for sym in chain_symbols:
        rec = quote_map.get(sym, {})
        sell_px = rec.get("SELL")
        buy_px = rec.get("BUY")
        fallback = prices.get(sym, 0.0)
        output_price_book[sym] = float(sell_px if sell_px is not None else (buy_px if buy_px is not None else fallback))
        input_price_book[sym] = float(buy_px if buy_px is not None else (sell_px if sell_px is not None else fallback))

    reports = []
    for name in selected_chains:
        reports.append(
            build_chain_report(
                name,
                CRAFTING_CHAINS[name],
                prices,
                modifiers=modifiers,
                start_amount=start_amount,
                input_prices=input_price_book,
                output_prices=output_price_book,
            )
        )

    leaderboard = sorted(
        [r for r in reports if not r.get("error")],
        key=lambda r: r.get("total_roi", 0.0),
        reverse=True,
    )

    def format_coin(value: Any, places: int = 6, signed: bool = False) -> str:
        num = float(value or 0)
        return f"{num:+,.{places}f}" if signed else f"{num:,.{places}f}"

    def format_number(value: Any, places: int = 4) -> str:
        return f"{float(value or 0):,.{places}f}"

    def format_pct(value: Any, places: int = 2) -> str:
        return f"{float(value or 0) * 100:,.{places}f}%"

    def format_hms(value: Any) -> str:
        total_seconds = max(0, int(float(value or 0)))
        h = total_seconds // 3600
        m = (total_seconds % 3600) // 60
        s = total_seconds % 60
        return f"{h:02d}:{m:02d}:{s:02d}"

    content = """
    <style>
      .cc-controls { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; }
      .cc-controls .field-full { grid-column: span 2; }
      .cc-card { margin-bottom:14px; }
      .cc-chip-row { display:flex; flex-wrap:wrap; gap:8px; margin-top:6px; }
      .cc-chip { border:1px solid rgba(148,163,184,.35); border-radius:999px; background:rgba(15,23,42,.7); color:var(--text-soft); padding:6px 10px; font-size:12px; cursor:pointer; }
      .cc-chip.active { border-color: rgba(92,242,255,.55); color: var(--text-main); background: rgba(30,64,175,.5); }
      .cc-summary { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:8px; margin-top:10px; }
      .cc-summary .item { background:rgba(15,23,42,.5); border:1px solid rgba(148,163,184,.22); border-radius:10px; padding:8px; }
      .cc-summary .k { display:block; font-size:11px; color:var(--text-soft); }
      .cc-summary .v { font-weight:700; }
      .cc-table th, .cc-table td { border-bottom:1px solid rgba(148,163,184,.12); }
      .num { text-align:right; font-variant-numeric:tabular-nums; }
      .profit-pos { color:var(--success); }
      .profit-neg { color:#fca5a5; }
      @media (max-width:980px){ .cc-controls,.cc-summary{grid-template-columns:1fr 1fr;} }
      @media (max-width:680px){ .cc-controls,.cc-summary{grid-template-columns:1fr;} }
    </style>

    <div class="card cc-card">
      <h1>🔗 Crafting Chains</h1>
      <p class="subtle">Track each stage in your 1-resource chain with live BUY-driven input costs and SELL-driven output values (same quote model as Profitability), plus your saved Mastery/Workshop boosts.</p>
      <form method="GET" action="{{ url_for('craft_profitability') }}">
        <div class="cc-controls">
          <div>
            <label>Starting amount</label>
            <input type="number" step="0.0001" min="0.0001" name="start_amount" value="{{ start_amount }}" />
          </div>
          <div class="field-full">
            <label>Enabled chains</label>
            <div class="cc-chip-row" id="cc-chain-chips">
              {% for name, chain in chains.items() %}
                <button type="button" class="cc-chip {{ 'active' if name in selected_chains else '' }}" data-chain="{{ name }}">{{ name }}</button>
              {% endfor %}
            </div>
            <input type="hidden" name="chains" id="chains-input" value="{{ selected_chains_csv }}" />
          </div>
          <div>
            <label>Account power</label>
            <input type="text" value="{{ format_number(status.power or 0, 0) if status.auth=='ok' else 'Not connected' }}" disabled />
          </div>
          <div>
            <label>&nbsp;</label>
            <button type="submit">Recalculate Chains</button>
          </div>
        </div>
      </form>
      {% if error %}<div class="error">{{ error }}</div>{% endif %}
    </div>

    <div class="card cc-card">
      <h2>Chain ROI ranking</h2>
      <table class="cc-table">
        <thead><tr><th>Chain</th><th class="num">Total Cost (COIN)</th><th class="num">Final Value (COIN)</th><th class="num">Profit (COIN)</th><th class="num">Total ROI</th><th class="num">Power</th><th class="num">Time</th></tr></thead>
        <tbody>
          {% for row in leaderboard %}
          <tr>
            <td>{{ row.name }}</td>
            <td class="num">{{ format_coin(row.total_cost) }}</td>
            <td class="num">{{ format_coin(row.total_value) }}</td>
            <td class="num {{ 'profit-pos' if row.total_profit >= 0 else 'profit-neg' }}">{{ format_coin(row.total_profit, signed=True) }}</td>
            <td class="num {{ 'profit-pos' if row.total_roi >= 0 else 'profit-neg' }}">{{ format_pct(row.total_roi) }}</td>
            <td class="num">{{ format_number(row.total_power, 2) }}</td>
            <td class="num">{{ format_hms(row.total_seconds) }}</td>
          </tr>
          {% endfor %}
          {% if not leaderboard %}<tr><td colspan="7" class="subtle">No chain data available.</td></tr>{% endif %}
        </tbody>
      </table>
    </div>

    {% for report in reports %}
      <div class="card cc-card">
        <h2>{{ report.name }}</h2>
        {% if report.error %}
          <div class="error">{{ report.error }}</div>
        {% else %}
          <div class="cc-summary">
            <div class="item"><span class="k">Start</span><span class="v">{{ format_number(report.start_amount, 4) }} {{ report.start_symbol }}</span></div>
            <div class="item"><span class="k">End</span><span class="v">{{ format_number(report.end_amount, 4) }} {{ report.end_symbol }}</span></div>
            <div class="item"><span class="k">Total Profit</span><span class="v {{ 'profit-pos' if report.total_profit >= 0 else 'profit-neg' }}">{{ format_coin(report.total_profit, signed=True) }} COIN</span></div>
            <div class="item"><span class="k">Total ROI</span><span class="v {{ 'profit-pos' if report.total_roi >= 0 else 'profit-neg' }}">{{ format_pct(report.total_roi) }}</span></div>
          </div>
          <table class="cc-table">
            <thead>
              <tr>
                <th>Stage</th><th class="num">Input Qty</th><th class="num">Input Px</th><th class="num">Input Cost</th><th class="num">Other Inputs Cost</th>
                <th class="num">Output Qty</th><th class="num">Output Px</th><th class="num">Output Value</th><th class="num">Stage ROI</th><th class="num">Cumulative ROI</th>
              </tr>
            </thead>
            <tbody>
              {% for s in report.stages %}
              <tr>
                <td>{{ s.from }} ➜ {{ s.to }}</td>
                <td class="num">{{ format_number(s.input_amount, 4) }}</td>
                <td class="num">{{ format_coin(s.input_price) }}</td>
                <td class="num">{{ format_coin(s.input_cost) }}</td>
                <td class="num">{{ format_coin(s.other_input_cost) }}</td>
                <td class="num">{{ format_number(s.output_amount, 4) }}</td>
                <td class="num">{{ format_coin(s.output_price) }}</td>
                <td class="num">{{ format_coin(s.output_value) }}</td>
                <td class="num {{ 'profit-pos' if s.stage_roi >= 0 else 'profit-neg' }}">{{ format_pct(s.stage_roi) }}</td>
                <td class="num {{ 'profit-pos' if s.cumulative_roi >= 0 else 'profit-neg' }}">{{ format_pct(s.cumulative_roi) }}</td>
              </tr>
              {% endfor %}
            </tbody>
          </table>
        {% endif %}
      </div>
    {% endfor %}

    <script>
      (function () {
        const chips = Array.from(document.querySelectorAll('#cc-chain-chips .cc-chip'));
        const input = document.getElementById('chains-input');
        function sync(){
          const names = chips.filter(c => c.classList.contains('active')).map(c => c.dataset.chain);
          input.value = names.join(',');
        }
        chips.forEach((chip)=>chip.addEventListener('click', ()=>{
          chip.classList.toggle('active');
          if (!chips.some(c => c.classList.contains('active'))) chip.classList.add('active');
          sync();
        }));
        sync();
      })();
    </script>
    """

    html = render_template_string(
        BASE_TEMPLATE,
        content=render_template_string(
            content,
            reports=reports,
            leaderboard=leaderboard,
            chains=CRAFTING_CHAINS,
            selected_chains=selected_chains,
            selected_chains_csv=",".join(selected_chains),
            start_amount=start_amount,
            status=status,
            error=error,
            format_coin=format_coin,
            format_number=format_number,
            format_pct=format_pct,
            format_hms=format_hms,
        ),
        active_page="craft_profit",
        has_uid=has_uid_flag(),
    )
    return html


def masterpieces_view():
    rich_masterpiece_summary_html = ""
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

    # --- Event leaderboard data for the Event subtab ---
    event_mp_top50: List[Dict[str, Any]] = []
    event_gap = None  # optional; template guards with `is defined`

    if current_event_mp:
        lb_event = current_event_mp.get("leaderboard") or []
        try:
            event_mp_top50 = list(lb_event[:top_n])
        except Exception:
            event_mp_top50 = []


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

            # ---- Build the row for this stage ----
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
                    # full objects so template can show icons later if you want
                    "rewards": rewards_list,
                    "battlepass_rewards": bp_list,
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

    # ---------- Simple Tier Ladder (for the "Tier ladder" table) ----------
    tier_rows: List[Dict[str, Any]] = []
    prev_req = 0.0
    for idx, req in enumerate(MP_TIER_THRESHOLDS, start=1):
        try:
            req_val = float(req)
        except (TypeError, ValueError):
            continue
        tier_rows.append(
            {
                "tier": idx,
                "required": req_val,
                "delta": req_val - prev_req,
            }
        )
        prev_req = req_val

    # ---------- Per-rank totals for *your* current bracket ----------
    my_rank_totals: Dict[str, float] = {}
    my_rank_totals_list: List[Dict[str, Any]] = []

    if selected_reward_snapshot:
        pos_raw = selected_reward_snapshot.get("position")
        pos_int: Optional[int] = None
        try:
            pos_int = int(pos_raw)
        except Exception:
            pos_int = None

        if pos_int is not None:
            for blk in leaderboard_bracket_totals:
                fr = blk.get("from_rank")
                to = blk.get("to_rank")

                # Normalise rank bounds to ints when possible
                try:
                    fr_int = int(fr)
                except Exception:
                    fr_int = None
                try:
                    to_int = int(to)
                except Exception:
                    to_int = fr_int

                if fr_int is None and to_int is None:
                    continue

                if fr_int is not None and to_int is not None:
                    if fr_int <= pos_int <= to_int:
                        my_rank_totals = dict(blk.get("totals") or {})
                        break
                elif fr_int is not None:
                    if pos_int >= fr_int:
                        my_rank_totals = dict(blk.get("totals") or {})
                        break

    if my_rank_totals:
        my_rank_totals_list = _totals_to_rows(my_rank_totals)
    else:
        my_rank_totals_list = []

    # ---------- Grand totals (tiers + your rank rewards) ----------
    grand_totals: Dict[str, float] = dict(combined_totals)
    for sym, amt in my_rank_totals.items():
        grand_totals[sym] = grand_totals.get(sym, 0.0) + float(amt or 0.0)

    grand_totals_list = _totals_to_rows(grand_totals)
    grand_total_coin = sum(r["coin_value"] for r in grand_totals_list)
    grand_total_usd = grand_total_coin * coin_usd if coin_usd else 0.0

    # ---------- Render page ----------
    content_html = render_template_string(
        MASTERPIECES_TEMPLATE,
        error=error,
        # overview / current
        current_mp=current_mp,
        current_mp_top50=current_mp_top50,
        current_gap=current_gap,
        general_snapshot=general_snapshot,
        event_snapshot=event_snapshot,
        current_event_mp=current_event_mp,
        # 🔽 NEW: event tab
        event_mp_top50=event_mp_top50,
        event_gap=event_gap,
        # history
        selected_mp=selected_mp,
        selected_mp_top50=selected_mp_top50,
        selected_gap=selected_gap,
        history_mp_options=history_mp_options,
        highlight_query=highlight_query,
        top_n=top_n,
        top_n_options=TOP_N_OPTIONS,
        # rewards / totals
        src_mp=src_mp,
        tier_rows=tier_rows,
        reward_tier_rows=reward_tier_rows,
        tier_base_totals_list=tier_base_totals_list,
        tier_bp_totals_list=tier_bp_totals_list,
        tier_combined_totals_list=tier_combined_totals_list,
        tier_combined_total_coin=tier_combined_total_coin,
        tier_combined_total_usd=tier_combined_total_usd,
        my_rank_totals_list=my_rank_totals_list,
        grand_totals_list=grand_totals_list,
        grand_total_coin=grand_total_coin,
        grand_total_usd=grand_total_usd,
        coin_usd=coin_usd,
        selected_reward_snapshot=selected_reward_snapshot,
        has_battle_pass=has_battle_pass,
        # planner
        planner_mp=planner_mp,
        planner_mp_options=planner_mp_options,
        planner_tokens=planner_tokens,
        calc_resources=calc_resources,
        calc_result=calc_result,
        calc_state_json=calc_state_json,
    )

    html = render_template_string(
        BASE_TEMPLATE,
        content=content_html,
        active_page="masterpieces",
        has_uid=has_uid_flag(),
    )
    return html

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

    # ---------- Build simple tier ladder rows for planner ----------
    # Uses MP_TIER_THRESHOLDS (e.g. [10_000, 25_000, 50_000, ...])
    tier_rows: List[Dict[str, Any]] = []
    prev_req = 0
    for idx, req in enumerate(MP_TIER_THRESHOLDS, start=1):
        try:
            req_val = int(req)
        except (TypeError, ValueError):
            continue  # skip weird values

        delta = req_val - prev_req if idx > 1 else 0
        tier_rows.append(
            {
                "tier": idx,
                "required": req_val,
                "delta": delta,
            }
        )
        prev_req = req_val


    # ---------- Render page ----------
    content_html = render_template_string(
        MASTERPIECES_TEMPLATE,
        error=error,
        # overview / current
        current_mp=current_mp,
        current_mp_top50=current_mp_top50,
        current_gap=current_gap,
        general_snapshot=general_snapshot,
        event_snapshot=event_snapshot,
        # 🔽 NEW: event tab
        event_mp_top50=event_mp_top50,
        event_gap=event_gap,
        # history
        selected_mp=selected_mp,
        selected_mp_top50=selected_mp_top50,
        selected_gap=selected_gap,
        history_mp_options=history_mp_options,
        highlight_query=highlight_query,
        top_n=top_n,
        top_n_options=TOP_N_OPTIONS,
        # rewards / totals
        src_mp=src_mp,
        tier_rows=tier_rows,
        reward_tier_rows=reward_tier_rows,
        tier_base_totals_list=tier_base_totals_list,
        tier_bp_totals_list=tier_bp_totals_list,
        tier_combined_totals_list=tier_combined_totals_list,
        tier_combined_total_coin=tier_combined_total_coin,
        tier_combined_total_usd=tier_combined_total_usd,
        my_rank_totals_list=my_rank_totals_list,
        grand_totals_list=grand_totals_list,
        grand_total_coin=grand_total_coin,
        grand_total_usd=grand_total_usd,
        coin_usd=coin_usd,
        selected_reward_snapshot=selected_reward_snapshot,
        has_battle_pass=has_battle_pass,
        # planner
        planner_mp=planner_mp,
        planner_mp_options=planner_mp_options,
        planner_tokens=planner_tokens,
        calc_resources=calc_resources,
        calc_result=calc_result,
        calc_state_json=calc_state_json,
    )

    html = render_template_string(
        BASE_TEMPLATE,
        content=content_html,
        active_page="masterpieces",
        has_uid=has_uid_flag(),
    )
    return html

