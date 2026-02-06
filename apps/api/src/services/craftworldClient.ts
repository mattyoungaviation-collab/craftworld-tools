import type { FastifyBaseLogger } from 'fastify';

const GRAPHQL_URL = 'https://craft-world.gg/graphql';
const APP_VERSION = '1.6.2';

export type GraphqlResponse = {
  ok: boolean;
  status: number;
  body: unknown;
};

export function normalizeCwToken(token?: string | null): string {
  const value = String(token || '').trim();
  if (!value) return '';
  if (value.startsWith('jwt_')) return value;
  if (value.split('.').length >= 3) return `jwt_${value}`;
  return value;
}

export async function callGraphqlRaw(
  query: string,
  variables?: Record<string, unknown>,
  bearerToken?: string,
): Promise<GraphqlResponse> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'x-app-version': APP_VERSION,
  };
  const normalized = normalizeCwToken(bearerToken);
  if (normalized) headers.Authorization = `Bearer ${normalized}`;

  const response = await fetch(GRAPHQL_URL, {
    method: 'POST',
    headers,
    body: JSON.stringify({ query, variables }),
  });

  let body: unknown = null;
  try {
    body = await response.json();
  } catch (_err) {
    body = { errors: [{ message: `Invalid JSON response (HTTP ${response.status})` }] };
  }

  return { ok: response.ok, status: response.status, body };
}

export function extractBearer(authorization?: string): string {
  const value = String(authorization || '').trim();
  if (!value) return '';
  if (value.toLowerCase().startsWith('bearer ')) {
    return value.slice(7).trim();
  }
  return '';
}

export function maskToken(token?: string | null): string {
  if (!token) return '<missing>';
  if (token.length <= 16) return `${token.slice(0, 4)}...`;
  return `${token.slice(0, 10)}...${token.slice(-6)}`;
}

export async function fetchAccountStatus(bearerToken: string) {
  const query = `
    query AccountStatus {
      account {
        power
        powerMillisecondsUntilRefill
        powerLastRefill
        updatedAt
      }
    }
  `;
  const data = await callGraphqlRaw(query, undefined, bearerToken);
  const body = data.body as { data?: { account?: Record<string, unknown> } };
  const account = body?.data?.account ?? {};
  return {
    power: Number(account.power || 0),
    powerMillisecondsUntilRefill: Number(account.powerMillisecondsUntilRefill || 0),
    powerLastRefill: account.powerLastRefill ?? null,
    updatedAt: account.updatedAt ?? null,
  };
}

export async function fetchWorkshopLevels(bearerToken: string) {
  const query = `
    query {
      account {
        workshop { symbol level }
      }
    }
  `;
  const data = await callGraphqlRaw(query, undefined, bearerToken);
  const body = data.body as { data?: { account?: { workshop?: { symbol?: string; level?: number }[] } } };
  const list = body?.data?.account?.workshop ?? [];
  const result: Record<string, number> = {};
  for (const row of list) {
    const symbol = String(row.symbol || '').toUpperCase();
    if (!symbol) continue;
    result[symbol] = Number(row.level || 0);
  }
  return result;
}

export async function fetchProficiencies(bearerToken: string) {
  const query = `
    query {
      account {
        proficiencies { symbol collectedAmount claimedLevel }
      }
    }
  `;
  const data = await callGraphqlRaw(query, undefined, bearerToken);
  const body = data.body as { data?: { account?: { proficiencies?: { symbol?: string; collectedAmount?: number; claimedLevel?: number }[] } } };
  const list = body?.data?.account?.proficiencies ?? [];
  const result: Record<string, { collectedAmount: number; claimedLevel: number }> = {};
  for (const row of list) {
    const symbol = String(row.symbol || '').toUpperCase();
    if (!symbol) continue;
    result[symbol] = {
      collectedAmount: Number(row.collectedAmount || 0),
      claimedLevel: Number(row.claimedLevel || 0),
    };
  }
  return result;
}

export async function fetchAccountUid(bearerToken: string) {
  const query = `
    query AccountUID {
      account { id }
    }
  `;
  const data = await callGraphqlRaw(query, undefined, bearerToken);
  const body = data.body as { data?: { account?: { id?: string } }; errors?: unknown[] };
  return {
    uid: body?.data?.account?.id ?? null,
    errors: body?.errors ?? [],
  };
}

export async function logGraphqlErrors(logger: FastifyBaseLogger, errors: unknown) {
  if (!errors) return;
  try {
    logger.warn({ errors }, 'Craft World GraphQL errors');
  } catch (_err) {
    logger.warn('Craft World GraphQL errors');
  }
}
