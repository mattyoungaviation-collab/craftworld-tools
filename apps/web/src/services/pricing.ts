import { fetchLivePricesInCoin, type GraphqlFetcher } from '@shared/pricing';

const GRAPHQL_URL = 'https://craft-world.gg/graphql';

export const fetchGraphql: GraphqlFetcher = async (query, variables) => {
  const res = await fetch(GRAPHQL_URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'x-app-version': '1.6.2',
    },
    body: JSON.stringify({ query, variables }),
  });
  const json = await res.json();
  if (json.errors) throw new Error(JSON.stringify(json.errors));
  return json.data;
};

export async function fetchCoinUsdPrice(tokenAddress?: string) {
  if (!tokenAddress) return null;
  const url = `https://api.geckoterminal.com/api/v2/networks/ronin/tokens/${tokenAddress}`;
  try {
    const res = await fetch(url);
    const data = await res.json();
    const price = data?.data?.attributes?.price_usd;
    if (!price) return null;
    return Number(price);
  } catch {
    return null;
  }
}

export async function fetchPrices() {
  return fetchLivePricesInCoin(fetchGraphql, fetchCoinUsdPrice);
}
