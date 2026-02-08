export type GraphqlRequest = {
  operationName?: string;
  query: string;
  variables?: Record<string, unknown>;
};

export const cwGraphqlRequest = async <T>(
  request: GraphqlRequest,
  options?: { idToken?: string | null }
) => {
  const res = await fetch('/api/cw/graphql', {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      ...(options?.idToken ? { authorization: `Bearer jwt_${options.idToken}` } : {})
    },
    body: JSON.stringify(request),
    cache: 'no-store'
  });

  if (!res.ok) {
    throw new Error(`Craft World GraphQL failed (${res.status})`);
  }

  const data = (await res.json()) as { data?: T; errors?: Array<{ message: string }> };
  if (data.errors?.length) {
    throw new Error(data.errors.map((err) => err.message).join('; '));
  }
  if (!data.data) {
    throw new Error('Empty GraphQL response');
  }
  return data.data;
};
