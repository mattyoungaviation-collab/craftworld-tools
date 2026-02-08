type CustomTokenResponse = {
  idToken: string;
  refreshToken: string;
  expiresIn: string;
};

type LookupResponse = {
  users?: Array<{ localId?: string | null }>;
};

type RefreshResponse = {
  id_token: string;
  refresh_token: string;
  expires_in: string;
};

const getFirebaseApiKey = () => {
  const key = process.env.NEXT_PUBLIC_FIREBASE_API_KEY;
  if (!key) {
    throw new Error('Missing NEXT_PUBLIC_FIREBASE_API_KEY');
  }
  return key;
};

export const exchangeCustomToken = async (customToken: string) => {
  const key = getFirebaseApiKey();
  const res = await fetch(`https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken?key=${key}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ token: customToken, returnSecureToken: true })
  });
  if (!res.ok) {
    throw new Error(`Custom token exchange failed (${res.status})`);
  }
  const data = (await res.json()) as CustomTokenResponse;
  const expiresIn = Number(data.expiresIn);
  return {
    idToken: data.idToken,
    refreshToken: data.refreshToken,
    expiresAt: Date.now() + expiresIn * 1000 - 30_000
  };
};

export const lookupAccountInfo = async (idToken: string) => {
  const key = getFirebaseApiKey();
  const res = await fetch(`https://identitytoolkit.googleapis.com/v1/accounts:lookup?key=${key}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ idToken })
  });
  if (!res.ok) {
    throw new Error(`Account lookup failed (${res.status})`);
  }
  const data = (await res.json()) as LookupResponse;
  return data.users?.[0]?.localId ?? null;
};

export const refreshIdToken = async (refreshToken: string) => {
  const key = getFirebaseApiKey();
  const res = await fetch(`https://securetoken.googleapis.com/v1/token?key=${key}`, {
    method: 'POST',
    headers: { 'content-type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ grant_type: 'refresh_token', refresh_token: refreshToken })
  });
  if (!res.ok) {
    throw new Error(`Token refresh failed (${res.status})`);
  }
  const data = (await res.json()) as RefreshResponse;
  const expiresIn = Number(data.expires_in);
  return {
    idToken: data.id_token,
    refreshToken: data.refresh_token,
    expiresAt: Date.now() + expiresIn * 1000 - 30_000
  };
};
