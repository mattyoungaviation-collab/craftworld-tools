import type { BuySellMap, PriceBook } from './types';

export const TOKEN_ADDRESSES: Record<string, string> = {
  EARTH: '0xC89384CD2970C916DC75DA8E11524EBE6D77FA07',
  WATER: '0x57A8EB80D6813AEEEB9C8E770011C016F980D581',
  FIRE: '0x0E8EDC6F5CAC5DCAE036AD77FC0DE4E72404E2FB',
  MUD: '0x1CC30B8FC5D4480B1740B1676E3636FB1270C524',
  CLAY: '0xA1AF0DFA0884C7433F82BBA89CB36E5B7B90A5C1',
  SAND: '0xAC861E0D31080E3B491747A968DF567F81BC8605',
  COPPER: '0x64AC88024E1BCC49E3EE145C165914F58998EC9B',
  SEAWATER: '0x84A162DFA5D818151BD8C8E804DAE8CD96A0E15D',
  ALGAE: '0x9ACDDDE6564924042E8ACFD5BD137374AF9DFAE5',
  CERAMICS: '0x581E54C7A521519E98D256D39852E4C214CAD697',
  OXYGEN: '0xCF2BD4CDDCE432090D6A9725BEC7A6AED77B41F0',
  STONE: '0xE7AD0FD3C832769437CC1240BFFE5DFF94FC9CF1',
  HEAT: '0x415363B5C4600AA776B6C39FED866DEE15179AB8',
  LAVA: '0x78EB25B148995A4EE373E65E93474EF0ED0FCC9A',
  GAS: '0x91720484FC3569AF94D5049835048C83A1D32FA2',
  CEMENT: '0x04A581CF47CCC244A5AB715C7A105D63BBCB57CA',
  GLASS: '0xF7604075A0ED6B4F6537BA2BAB19F1F44F5E7AA4',
  STEAM: '0x5F146DFF3B6A3E89188A3953D621637452BA4407',
  STEEL: '0x798239FEE069E2B5B3C58978AEA92A3D0E16950C',
  FUEL: '0x677203F3FCC63FE85A5ABC8E6479A88DEB86717B',
  ACID: '0xCD0C9F170E395CA1ADC16AE9AE8107D50273E2E8',
  SULFUR: '0x85120A3D815E95FB8D68129593084BF97905F543',
  ENERGY: '0xA3F0F293AEE7CE8B4A3807BF9CC07942DA4E51E8',
  SCREWS: '0xCC34D8E6A6F61358219D8E8A967ED7F191638449',
  OIL: '0x27908A7052980B7537BCB72757CD59B57D5FAE0B',
  PLASTICS: '0x8EABB6A3A05AF9FB514482A677B12008A2ED6422',
  FIBERGLASS: '0xAB6B550C661862E637249D55207125EE6AFE0AAA',
  HYDROGEN: '0xB7D11863D0D9C39764F981A95AB8AF0AED714C48',
  DYNAMITE: '0x2B918938CFDE254CC76B68A4F6992927EE779104',
  DYNOFISH: '0x739Ef71e744eE052A7b773C5b7505dA9AD8447c0',
  FISH: '0x0ad7edc6482A298b9dfbc31620aCe6A32489eF2B',
  FISHBONE: '0xBafb427ce206fA262A5E21646dFef9d219E15A69',
  BONESOUP: '0xb69af5Afbb2AEE36ab33Df2050f4352B500A48C2',
  FUGU: '0x04dA7513004C5bdD8452b3bB0AF89A5baA666AE0',
  RAWRVIOLI: '0x82915DAD2Db2c1A4Bbfd35852372318a103f7D80',
  SUSHI: '0xC146e831C137bbB2e1aF91C30844D224F4778017',
  DYNODESSERT: '0x4F0585509AaBFc9EA3146ec18F8E6d2e289F288c',
  SASHIMI: '0x6431221054B04AEFdf94b8Bc1529172ff9860d2c',
  LOBSTER: '0x869DC8b8553788Fa007BB12Ddd31442650559602',
  TAPE: '0xbb38b663bec9d1016832fb6b3565ceca01dc5cc8',
  MAGICSHARD: '',
  PLUNGER: '0xc0873c760ae381717cb64529755b5ee4bfecca3d',
  SPOON: '0x77a18414e70aa263cff8e698720b9ade8929d1ad',
  TOYHAMMER: '0x2c80f963b310ddc4c0d3f3c10836f055acd7b404',
  NINJASTAR: '0x4f212d70ede8ab0e7c3753e7812cd1368b2aa011',
  SWORD: '0x2dc1380ae5d5c8775357653cc18edfe232519137',
  MYSTICWEAPON: '0xdb1739b71ee9d8d6fda9208bee8920e6297bfa8e',
  TARGET: '0xf093b2a7b46c95379781b5169d96aa5583d582ff',
  COIN: '0x7DC167E270D5EF683CEAF4AFCDF2EFBDD667A9A7',
};

export const EXCHANGE_PRICE_LIST_QUERY = `
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
`;

export const EXACT_INPUT_QUOTE_QUERY = `
  query exactInputQuoteQuery($input: ExactInputInput!) {
    exactInputQuote(input: $input) {
      type
      input { symbol amount }
      output { symbol amount }
      details { priceImpactPercentage }
    }
  }
`;

export type GraphqlFetcher = (query: string, variables?: Record<string, unknown>) => Promise<any>;

const normalizeSymbol = (raw?: string | null) => {
  const token = String(raw || '').trim().toUpperCase();
  return token.startsWith('$') ? token.slice(1) : token;
};

export async function fetchExchangePricesBuySell(fetchGraphql: GraphqlFetcher): Promise<BuySellMap> {
  const data = await fetchGraphql(EXCHANGE_PRICE_LIST_QUERY);
  const root = data.exchangePriceList || {};
  const baseSymbol = normalizeSymbol(root.baseSymbol || 'COIN');
  const perSymbol: BuySellMap = {};

  for (const item of root.prices || []) {
    const sym = normalizeSymbol(item.referenceSymbol);
    const amount = Number(item.amount || 0);
    const rec = String(item.recommendation || '').toUpperCase();
    if (!sym) continue;
    if (!perSymbol[sym]) perSymbol[sym] = {};
    perSymbol[sym][rec || 'UNKNOWN'] = amount;
  }

  if (!perSymbol[baseSymbol]) perSymbol[baseSymbol] = {};
  perSymbol[baseSymbol].SELL ??= 1.0;
  perSymbol[baseSymbol].BUY ??= 1.0;

  return perSymbol;
}

export async function fetchExactInputQuote(
  fetchGraphql: GraphqlFetcher,
  inputSymbol: string,
  outputSymbol: string,
  inputAmount: number,
) {
  try {
    const data = await fetchGraphql(EXACT_INPUT_QUOTE_QUERY, {
      input: {
        inputSymbol,
        outputSymbol,
        inputAmount: Number(inputAmount),
      },
    });
    return data.exactInputQuote || null;
  } catch {
    return null;
  }
}

export async function fetchBuySellForProfitability(
  fetchGraphql: GraphqlFetcher,
  symbols: string[],
  sampleAmount = 2,
  cache?: { quotes: Record<string, Record<string, number>>; ts: Record<string, number> },
  ttlSeconds = 60,
): Promise<BuySellMap> {
  const base = await fetchExchangePricesBuySell(fetchGraphql);
  const perSymbol: BuySellMap = {};
  for (const [sym, recMap] of Object.entries(base)) {
    perSymbol[sym.toUpperCase()] = { ...recMap };
  }

  const now = Date.now() / 1000;
  for (const sym of symbols) {
    const symU = sym.toUpperCase();
    if (symU === 'COIN') continue;
    const cached = cache?.quotes?.[symU];
    const cachedTs = cache?.ts?.[symU] || 0;
    if (cached && now - cachedTs < ttlSeconds) {
      perSymbol[symU] = { ...(perSymbol[symU] || {}), ...cached };
      continue;
    }

    let sellPrice: number | null = null;
    let buyPrice: number | null = null;

    const quoteSell = await fetchExactInputQuote(fetchGraphql, symU, 'COIN', sampleAmount);
    if (quoteSell?.output && quoteSell?.input) {
      const outAmt = Number(quoteSell.output.amount || 0);
      const inAmt = Number(quoteSell.input.amount || 0);
      if (inAmt > 0) sellPrice = outAmt / inAmt;
    }

    const quoteBuy = await fetchExactInputQuote(fetchGraphql, 'COIN', symU, sampleAmount);
    if (quoteBuy?.output && quoteBuy?.input) {
      const outAmt = Number(quoteBuy.output.amount || 0);
      const inAmt = Number(quoteBuy.input.amount || 0);
      if (outAmt > 0) buyPrice = inAmt / outAmt;
    }

    if (sellPrice !== null || buyPrice !== null) {
      perSymbol[symU] = perSymbol[symU] || {};
      const toStore: Record<string, number> = {};
      if (sellPrice !== null) {
        perSymbol[symU].SELL = sellPrice;
        toStore.SELL = sellPrice;
      }
      if (buyPrice !== null) {
        perSymbol[symU].BUY = buyPrice;
        toStore.BUY = buyPrice;
      }
      if (cache) {
        cache.quotes[symU] = toStore;
        cache.ts[symU] = now;
      }
    }
  }

  perSymbol.COIN = perSymbol.COIN || {};
  perSymbol.COIN.SELL ??= 1.0;
  perSymbol.COIN.BUY ??= 1.0;

  return perSymbol;
}

export async function fetchExchangePricesCoin(fetchGraphql: GraphqlFetcher): Promise<PriceBook> {
  const perSymbol = await fetchExchangePricesBuySell(fetchGraphql);
  const prices: PriceBook = {};
  for (const [sym, recMap] of Object.entries(perSymbol)) {
    if ('SELL' in recMap) {
      prices[sym] = Number(recMap.SELL);
    } else if ('BUY' in recMap) {
      prices[sym] = Number(recMap.BUY);
    } else if (Object.keys(recMap).length) {
      prices[sym] = Number(Object.values(recMap)[0]);
    }
  }
  prices.COIN ??= 1.0;
  return prices;
}

export async function fetchLivePricesInCoin(
  fetchGraphql: GraphqlFetcher,
  fetchUsdPrice: (tokenAddress?: string) => Promise<number | null>,
): Promise<PriceBook> {
  const pricesCoin = await fetchExchangePricesCoin(fetchGraphql);

  const coinAddr = TOKEN_ADDRESSES.COIN;
  const coinUsd = await fetchUsdPrice(coinAddr);
  pricesCoin._COIN_USD = coinUsd ? Number(coinUsd) : 0.0;

  let fishPrice = pricesCoin.FISH;
  if (!fishPrice) {
    const quoteFish = await fetchExactInputQuote(fetchGraphql, 'FISH', 'COIN', 1.0);
    if (quoteFish?.output && quoteFish?.input) {
      const outAmt = Number(quoteFish.output.amount || 0);
      const inAmt = Number(quoteFish.input.amount || 0);
      if (inAmt > 0) fishPrice = outAmt / inAmt;
    }
  }

  if (!fishPrice) {
    const quoteCoinFish = await fetchExactInputQuote(fetchGraphql, 'COIN', 'FISH', 1.0);
    if (quoteCoinFish?.output && quoteCoinFish?.input) {
      const outAmt = Number(quoteCoinFish.output.amount || 0);
      const inAmt = Number(quoteCoinFish.input.amount || 0);
      if (outAmt > 0) fishPrice = inAmt / outAmt;
    }
  }

  if (!fishPrice) {
    const fishAddr = TOKEN_ADDRESSES.FISH;
    const fishUsd = await fetchUsdPrice(fishAddr);
    if (fishUsd && coinUsd) {
      fishPrice = Number(fishUsd) / Number(coinUsd);
      pricesCoin.FISH = fishPrice;
    }
  }

  if (fishPrice) {
    pricesCoin.WORM = Number(fishPrice) / 270.0;
  }

  return pricesCoin;
}
