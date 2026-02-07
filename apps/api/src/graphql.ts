export const cwGraphqlRequest = async <T>(
  operationName: string,
  query: string,
  variables?: Record<string, unknown>
): Promise<T> => {
  const url = process.env.CRAFTWORLD_GQL_URL || 'https://craft-world.gg/graphql';
  const appVersion = process.env.CRAFTWORLD_APP_VERSION || '1.6.4';

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 10_000);

  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        'x-app-version': appVersion
      },
      body: JSON.stringify({ operationName, query, variables }),
      signal: controller.signal
    });

    if (!response.ok) {
      const text = await response.text().catch(() => '');
      throw new Error(`CraftWorld GraphQL failed ${response.status}: ${text.slice(0, 800)}`);
    }

    const payload = (await response.json()) as { data?: T; errors?: { message: string }[] };
    if (payload.errors?.length) {
      throw new Error(payload.errors.map((err) => err.message).join(', '));
    }

    if (!payload.data) {
      throw new Error('CraftWorld GraphQL missing data');
    }

    return payload.data;
  } finally {
    clearTimeout(timeout);
  }
};
