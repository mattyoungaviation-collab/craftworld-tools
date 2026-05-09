"""Simple page handlers.

These handlers were migrated out of app.py.
"""

from __future__ import annotations

from typing import Any

from flask import render_template_string

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


def charts():
    """
    Live token charts, like the iOS CraftMath app:
    - Choose a token from TOKEN_ADDRESSES
    - Embed GeckoTerminal Ronin chart in an iframe
    """
    # Token symbol from query string, e.g. /charts?token=EARTH
    selected = (request.args.get("token") or "").upper().strip()

    # All tokens we know contract addresses for
    tokens = [t for t in TOKENS_CHART_ORDER if t in TOKEN_ADDRESSES]

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

