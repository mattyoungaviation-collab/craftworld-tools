const CW_GRAPHQL_URL = process.env.CW_GRAPHQL_URL || 'https://craft-world.gg/graphql';

// CraftWorld expects this header (you mentioned 1.6.4)
const CW_APP_VERSION = process.env.CW_APP_VERSION || '1.6.4';

type GqlRequestBody = {
  operationName?: string;
  query: string;
  variables?: Record<string, unknown> | null;
};

export async function cwGraphqlRequest<T>(
  operationName: string,
  query: string,
  variables?: Record<string, unknown> | null
): Promise<T> {
  const body: GqlRequestBody = {
    operationName,
    query,
    variables: variables ?? null
  };

  const res = await fetch(CW_GRAPHQL_URL, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      accept: 'application/json',
      'x-app-version': CW_APP_VERSION
    },
    body: JSON.stringify(body)
  });

  const text = await res.text();

  if (!res.ok) {
    throw new Error(`CraftWorld GraphQL failed ${res.status}: ${text}`);
  }

  let json: any;
  try {
    json = JSON.parse(text);
  } catch {
    throw new Error(`CraftWorld GraphQL returned non-JSON: ${text}`);
  }

  if (json?.errors?.length) {
    throw new Error(`CraftWorld GraphQL failed 400: ${JSON.stringify({ errors: json.errors })}`);
  }

  return json.data as T;
}
