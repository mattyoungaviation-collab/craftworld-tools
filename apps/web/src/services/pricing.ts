const GRAPHQL_URL = 'https://craft-world.gg/graphql';

const EXCHANGE_PRICES_QUERY = `
  query ExchangePrices {
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

function normalizeSymbol(raw: string) {
  let token = String(raw || '').trim().toUpperCase();
  if (token.startsWith('$')) token = token.slice(1);
  return token;
}

export async function fetchExchangePricesCoin(): Promise<Record<string, number>> {
  const res = await fetch(GRAPHQL_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'x-app-version': '1.6.2' },
    body: JSON.stringify({ query: EXCHANGE_PRICES_QUERY }),
  });
  if (!res.ok) throw new Error('Failed to fetch exchange prices.');
  const data = (await res.json()) as { data?: { exchangePriceList?: { baseSymbol?: string; prices?: { referenceSymbol?: string; amount?: number }[] } } };
  const list = data.data?.exchangePriceList;
  const prices: Record<string, number> = {};
  (list?.prices || []).forEach((row) => {
    const symbol = normalizeSymbol(row.referenceSymbol || '');
    if (!symbol) return;
    if (typeof row.amount === 'number') prices[symbol] = row.amount;
  });
  prices.COIN = 1;
  return prices;
}
