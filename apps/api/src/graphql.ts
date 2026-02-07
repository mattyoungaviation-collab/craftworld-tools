type GqlEnvelope<T> = {
  data?: T;
  errors?: Array<{ message: string; extensions?: unknown }>;
};

export const cwGraphqlRequest = async <T>(
  operationName: string,
  query: string,
  variables?: Record<string, unknown> | null
): Promise<T> => {
  const url = process.env.CRAFTWORLD_GQL_URL || 'https://craft-world.gg/graphql';
  const appVersion = process.env.CRAFTWORLD_APP_VERSION || '1.6.4';

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15_000);

  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        accept: 'application/json',
        'x-app-version': appVersion
      },
      body: JSON.stringify({
        operationName,
        query,
        variables: variables ?? null
      }),
      signal: controller.signal
    });

    const text = await response.text();

    if (!response.ok) {
      throw new Error(`CraftWorld GraphQL failed ${response.status}: ${text}`);
    }

    let payload: GqlEnvelope<T>;
    try {
      payload = JSON.parse(text) as GqlEnvelope<T>;
    } catch {
      throw new Error(`CraftWorld GraphQL returned non-JSON: ${text}`);
    }

    if (payload.errors?.length) {
      throw new Error(`CraftWorld GraphQL errors: ${JSON.stringify(payload.errors)}`);
    }

    if (!payload.data) {
      throw new Error(`CraftWorld GraphQL missing data: ${text}`);
    }

    return payload.data;
  } finally {
    clearTimeout(timeout);
  }
};
