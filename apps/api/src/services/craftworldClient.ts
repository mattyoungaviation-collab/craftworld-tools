import type { FastifyBaseLogger } from 'fastify';

const GRAPHQL_URL = 'https://craft-world.gg/graphql';

export interface GraphqlResponse {
  statusCode: number;
  ok: boolean;
  body: any;
}

export function normalizeCwToken(token?: string | null): string | null {
  const value = String(token || '').trim();
  if (!value) return null;
  if (value.startsWith('jwt_')) return value;
  if (value.split('.').length >= 3) return `jwt_${value}`;
  return value;
}

export async function cwGraphqlRequest(
  query: string,
  variables?: Record<string, unknown>,
  bearerToken?: string | null,
  logger?: FastifyBaseLogger,
): Promise<GraphqlResponse> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'x-app-version': process.env.CW_APP_VERSION || '1.6.2',
  };
  const normalizedToken = normalizeCwToken(bearerToken || undefined);
  if (normalizedToken) {
    headers.Authorization = `Bearer ${normalizedToken}`;
  }

  const response = await fetch(GRAPHQL_URL, {
    method: 'POST',
    headers,
    body: JSON.stringify({ query, variables }),
  });

  let body: any = null;
  try {
    body = await response.json();
  } catch (err) {
    logger?.warn({ err }, 'Craft World GraphQL returned invalid JSON');
    body = { errors: [{ message: `Invalid JSON response (HTTP ${response.status})` }] };
  }

  return {
    statusCode: response.status,
    ok: response.ok,
    body,
  };
}

export function extractBearerToken(authorization?: string | null): string | null {
  const value = String(authorization || '').trim();
  if (!value) return null;
  if (value.toLowerCase().startsWith('bearer ')) {
    const token = value.slice(7).trim();
    return token || null;
  }
  return null;
}

export function getRequestToken(authHeader?: string | null, queryToken?: string | null): string | null {
  const headerToken = extractBearerToken(authHeader);
  if (headerToken) return normalizeCwToken(headerToken);
  return normalizeCwToken(queryToken || undefined);
}
