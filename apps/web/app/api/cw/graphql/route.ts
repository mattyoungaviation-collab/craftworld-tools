const CW_GRAPHQL_URL = process.env.NEXT_PUBLIC_CW_GRAPHQL_URL || 'https://craft-world.gg/graphql';
const CW_APP_VERSION = process.env.NEXT_PUBLIC_CW_APP_VERSION || '1.6.4';

export async function POST(request: Request) {
  const body = await request.text();
  const authHeader = request.headers.get('authorization') ?? '';

  const res = await fetch(CW_GRAPHQL_URL, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      'x-app-version': CW_APP_VERSION,
      ...(authHeader ? { authorization: authHeader } : {})
    },
    body
  });

  const responseBody = await res.text();
  return new Response(responseBody, {
    status: res.status,
    headers: {
      'content-type': res.headers.get('content-type') ?? 'application/json'
    }
  });
}
