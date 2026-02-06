const GRAPHQL_URL = 'https://craft-world.gg/graphql';

const MASTERPIECES_QUERY = `
  query Masterpieces {
    masterpieces {
      id
      name
      type
      eventId
      collectedPoints
      requiredPoints
      addressableLabel
      startedAt
    }
  }
`;

const MASTERPIECE_DETAILS_QUERY = `
  query Masterpiece($id: ID) {
    masterpiece(id: $id) {
      id
      name
      type
      eventId
      collectedPoints
      requiredPoints
      addressableLabel
      resources {
        symbol
        amount
        target
        consumedPowerPerUnit
      }
      leaderboard {
        position
        masterpiecePoints
        profile {
          uid
          walletAddress
          avatarUrl
          displayName
        }
      }
    }
  }
`;

async function callGraphql(query: string, variables?: Record<string, unknown>) {
  const res = await fetch(GRAPHQL_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'x-app-version': '1.6.2' },
    body: JSON.stringify({ query, variables }),
  });
  if (!res.ok) throw new Error('Failed to call Craft World API.');
  const json = (await res.json()) as { data?: unknown; errors?: unknown[] };
  if (json.errors && json.errors.length) throw new Error('Craft World returned errors.');
  return json.data as Record<string, unknown>;
}

export async function fetchMasterpieces() {
  const data = await callGraphql(MASTERPIECES_QUERY);
  const list = (data.masterpieces || []) as Record<string, unknown>[];
  return list.sort((a, b) => String(b.startedAt || '').localeCompare(String(a.startedAt || '')));
}

export async function fetchMasterpieceDetails(id: string) {
  const data = await callGraphql(MASTERPIECE_DETAILS_QUERY, { id });
  return data.masterpiece as Record<string, unknown> | undefined;
}
