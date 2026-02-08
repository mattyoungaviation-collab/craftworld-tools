import { NextResponse } from 'next/server';

const graphqlUrl = () => process.env.NEXT_PUBLIC_CW_GRAPHQL_URL || 'https://craft-world.gg/graphql';
const appVersion = () => process.env.NEXT_PUBLIC_CW_APP_VERSION || '1.6.4';

export async function POST(request: Request) {
  const payload = (await request.json()) as {
    operationName?: string;
    query?: string;
    variables?: Record<string, unknown>;
  };
  if (!payload.query) {
    return NextResponse.json({ error: 'Missing query.' }, { status: 400 });
  }
  const authHeader = request.headers.get('authorization');
  const response = await fetch(graphqlUrl(), {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      'x-app-version': appVersion(),
      ...(authHeader ? { authorization: authHeader } : {})
    },
    body: JSON.stringify({
      operationName: payload.operationName,
      query: payload.query,
      variables: payload.variables
    })
  });
  const data = await response.json();
  return NextResponse.json(data, { status: response.status });
}
