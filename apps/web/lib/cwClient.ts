import { computeExpiresAt, persistAuthState } from './cwAuth';

export type GraphqlRequest<T> = {
  operationName: string;
  query: string;
  variables?: Record<string, unknown>;
  idToken?: string;
};

export type FirebaseAuthResponse = {
  idToken: string;
  refreshToken: string;
  expiresIn: string;
};

export type FirebaseRefreshResponse = {
  access_token: string;
  expires_in: string;
  refresh_token: string;
};

export const cwGraphqlRequest = async <T>({
  operationName,
  query,
  variables,
  idToken
}: GraphqlRequest<T>): Promise<T> => {
  const res = await fetch('/api/cw/graphql', {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      ...(idToken ? { authorization: `Bearer jwt_${idToken}` } : {})
    },
    body: JSON.stringify({ operationName, query, variables })
  });
  if (!res.ok) {
    throw new Error(`CraftWorld request failed: ${res.status}`);
  }
  return (await res.json()) as T;
};

export const loginForCustomToken = async (signature: string, walletAddress: string) => {
  const response = await cwGraphqlRequest<{ data?: { loginForCustomToken?: { customToken?: string } } }>(
    {
      operationName: 'LoginForCustomToken',
      query: `mutation LoginForCustomToken($signature: String!, $walletAddress: String!) {\n  loginForCustomToken(signature: $signature, walletAddress: $walletAddress) {\n    customToken\n  }\n}`,
      variables: { signature, walletAddress }
    }
  );
  const customToken = response.data?.loginForCustomToken?.customToken;
  if (!customToken) {
    throw new Error('Custom token missing from response.');
  }
  return customToken;
};

export const exchangeCustomToken = async (customToken: string) => {
  const apiKey = process.env.NEXT_PUBLIC_FIREBASE_API_KEY;
  if (!apiKey) {
    throw new Error('Firebase API key missing.');
  }
  const res = await fetch(
    `https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken?key=${apiKey}`,
    {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ token: customToken, returnSecureToken: true })
    }
  );
  if (!res.ok) {
    throw new Error(`Firebase sign-in failed: ${res.status}`);
  }
  return (await res.json()) as FirebaseAuthResponse;
};

export const lookupAccountInfo = async (idToken: string) => {
  const apiKey = process.env.NEXT_PUBLIC_FIREBASE_API_KEY;
  if (!apiKey) {
    throw new Error('Firebase API key missing.');
  }
  const res = await fetch(`https://identitytoolkit.googleapis.com/v1/accounts:lookup?key=${apiKey}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ idToken })
  });
  if (!res.ok) {
    throw new Error(`Firebase lookup failed: ${res.status}`);
  }
  return (await res.json()) as { users?: Array<{ localId?: string }> };
};

export const refreshFirebaseToken = async (refreshToken: string) => {
  const apiKey = process.env.NEXT_PUBLIC_FIREBASE_API_KEY;
  if (!apiKey) {
    throw new Error('Firebase API key missing.');
  }
  const body = new URLSearchParams({ grant_type: 'refresh_token', refresh_token: refreshToken });
  const res = await fetch(`https://securetoken.googleapis.com/v1/token?key=${apiKey}`, {
    method: 'POST',
    headers: { 'content-type': 'application/x-www-form-urlencoded' },
    body
  });
  if (!res.ok) {
    throw new Error(`Firebase token refresh failed: ${res.status}`);
  }
  return (await res.json()) as FirebaseRefreshResponse;
};

export const ensureFreshToken = async (state: {
  idToken?: string;
  refreshToken?: string;
  expiresAt?: number;
  walletAddress?: string;
  localId?: string;
}) => {
  if (!state.idToken) {
    throw new Error('Missing id token.');
  }
  if (!state.expiresAt || Date.now() < state.expiresAt) {
    return state;
  }
  if (!state.refreshToken) {
    throw new Error('Session expired. Please login again.');
  }
  const refreshed = await refreshFirebaseToken(state.refreshToken);
  const expiresAt = computeExpiresAt(Number(refreshed.expires_in));
  const updated = {
    ...state,
    idToken: refreshed.access_token,
    refreshToken: refreshed.refresh_token,
    expiresAt
  };
  persistAuthState({
    status: 'authenticated',
    walletAddress: updated.walletAddress,
    idToken: updated.idToken,
    refreshToken: updated.refreshToken,
    expiresAt: updated.expiresAt,
    localId: updated.localId
  });
  return updated;
};

export const cwApiRequest = async <T>({
  state,
  onAuthUpdate,
  operationName,
  query,
  variables,
  requiresAuth = true
}: {
  state: {
    idToken?: string;
    refreshToken?: string;
    expiresAt?: number;
    walletAddress?: string;
    localId?: string;
  };
  onAuthUpdate?: (next: {
    idToken?: string;
    refreshToken?: string;
    expiresAt?: number;
    walletAddress?: string;
    localId?: string;
  }) => void;
  operationName: string;
  query: string;
  variables?: Record<string, unknown>;
  requiresAuth?: boolean;
}) => {
  const tokenState = requiresAuth ? await ensureFreshToken(state) : state;
  if (requiresAuth && !tokenState.idToken) {
    throw new Error('Missing id token.');
  }
  if (requiresAuth && onAuthUpdate) {
    onAuthUpdate(tokenState);
  }
  return cwGraphqlRequest<T>({
    operationName,
    query,
    variables,
    idToken: tokenState.idToken
  });
};
