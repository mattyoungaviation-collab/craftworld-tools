from typing import Dict, Optional

import requests

from craftworld_api import call_graphql

# Ronin token addresses (we mainly need COIN -> USD)
TOKEN_ADDRESSES: Dict[str, str] = {
    "EARTH":      "0xC89384CD2970C916DC75DA8E11524EBE6D77FA07",
    "WATER":      "0x57A8EB80D6813AEEEB9C8E770011C016F980D581",
    "FIRE":       "0x0E8EDC6F5CAC5DCAE036AD77FC0DE4E72404E2FB",
    "MUD":        "0x1CC30B8FC5D4480B1740B1676E3636FB1270C524",
    "CLAY":       "0xA1AF0DFA0884C7433F82BBA89CB36E5B7B90A5C1",
    "SAND":       "0xAC861E0D31080E3B491747A968DF567F81BC8605",
    "COPPER":     "0x64AC88024E1BCC49E3EE145C165914F58998EC9B",
    "SEAWATER":   "0x84A162DFA5D818151BD8C8E804DAE8CD96A0E15D",
    "ALGAE":      "0x9ACDDDE6564924042E8ACFD5BD137374AF9DFAE5",
    "CERAMICS":   "0x581E54C7A521519E98D256D39852E4C214CAD697",
    "OXYGEN":     "0xCF2BD4CDDCE432090D6A9725BEC7A6AED77B41F0",
    "STONE":      "0xE7AD0FD3C832769437CC1240BFFE5DFF94FC9CF1",
    "HEAT":       "0x415363B5C4600AA776B6C39FED866DEE15179AB8",
    "LAVA":       "0x78EB25B148995A4EE373E65E93474EF0ED0FCC9A",
    "GAS":        "0x91720484FC3569AF94D5049835048C83A1D32FA2",
    "CEMENT":     "0x04A581CF47CCC244A5AB715C7A105D63BBCB57CA",
    "GLASS":      "0xF7604075A0ED6B4F6537BA2BAB19F1F44F5E7AA4",
    "STEAM":      "0x5F146DFF3B6A3E89188A3953D621637452BA4407",
    "STEEL":      "0x798239FEE069E2B5B3C58978AEA92A3D0E16950C",
    "FUEL":       "0x677203F3FCC63FE85A5ABC8E6479A88DEB86717B",
    "ACID":       "0xCD0C9F170E395CA1ADC16AE9AE8107D50273E2E8",
    "SULFUR":     "0x85120A3D815E95FB8D68129593084BF97905F543",
    "ENERGY":     "0xA3F0F293AEE7CE8B4A3807BF9CC07942DA4E51E8",
    "SCREWS":     "0xCC34D8E6A6F61358219D8E8A967ED7F191638449",
    "OIL":        "0x27908A7052980B7537BCB72757CD59B57D5FAE0B",
    "PLASTICS":   "0x8EABB6A3A05AF9FB514482A677B12008A2ED6422",
    "FIBERGLASS": "0xAB6B550C661862E637249D55207125EE6AFE0AAA",
    "HYDROGEN":   "0xB7D11863D0D9C39764F981A95AB8AF0AED714C48",
    "DYNAMITE":   "0x2B918938CFDE254CC76B68A4F6992927EE779104",

    "TAPE":         "0xbb38b663bec9d1016832fb6b3565ceca01dc5cc8",
    "MAGICSHARD":   "",  # off-chain
    "PLUNGER":      "0xc0873c760ae381717cb64529755b5ee4bfecca3d",
    "SPOON":        "0x77a18414e70aa263cff8e698720b9ade8929d1ad",
    "TOYHAMMER":    "0x2c80f963b310ddc4c0d3f3c10836f055acd7b404",
    "NINJASTAR":    "0x4f212d70ede8ab0e7c3753e7812cd1368b2aa011",
    "SWORD":        "0x2dc1380ae5d5c8775357653cc18edfe232519137",
    "MYSTICWEAPON": "0xdb1739b71ee9d8d6fda9208bee8920e6297bfa8e",
    "TARGET":       "0xf093b2a7b46c95379781b5169d96aa5583d582ff",

    "COIN": "0x7DC167E270D5EF683CEAF4AFCDF2EFBDD667A9A7",
}

GECKO_BASE = "https://api.geckoterminal.com/api/v2/networks/ronin/tokens/"


def _get_usd_price(token_address: Optional[str]) -> Optional[float]:
    """Get USD price for a Ronin token via GeckoTerminal.
    If anything fails, returns None so the app can still run (USD = 0).
    """
    if not token_address:
        return None

    url = f"{GECKO_BASE}{token_address}"
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        # Expected shape:
        # { "data": { "attributes": { "price_usd": "0.1234" } } }
        price_str = (
            data.get("data", {})
            .get("attributes", {})
            .get("price_usd")
        )
        if not price_str:
            return None
        return float(price_str)
    except Exception:
        return None


def fetch_exchange_prices_coin() -> Dict[str, float]:
    """Call Craft World's exchangePriceList and return token -> price in COIN."""
    query = """\
    query ExchangePriceList {
      exchangePriceList {
        baseSymbol
        prices {
          referenceSymbol
          amount
          recommendation
        }
      }
    }
    """

    data = call_graphql(query, None)
    root = data["exchangePriceList"]
    base_symbol = root.get("baseSymbol", "COIN")
    prices_coin: Dict[str, float] = {}

    for item in root.get("prices", []):
        sym = item.get("referenceSymbol")
        amt = item.get("amount")
        try:
            amt_f = float(amt)
        except Exception:
            amt_f = 0.0

        if sym:
            prices_coin[sym.upper()] = amt_f

    # base symbol (COIN) is 1.0 in its own units
    prices_coin[base_symbol.upper()] = 1.0
    return prices_coin


def fetch_live_prices_in_coin() -> Dict[str, float]:
    """High-level helper for the app.

    Returns a dict:
      - token -> price in COIN
      - special key "_COIN_USD" for COIN price in USD (may be 0.0 if Gecko fails)
    """
    prices_coin = fetch_exchange_prices_coin()

    coin_addr = TOKEN_ADDRESSES.get("COIN")
    coin_usd = _get_usd_price(coin_addr) if coin_addr else None
    prices_coin["_COIN_USD"] = float(coin_usd) if coin_usd else 0.0

    return prices_coin
