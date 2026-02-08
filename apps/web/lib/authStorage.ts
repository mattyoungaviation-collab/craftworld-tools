export type StoredSession = {
  walletAddress?: string | null;
  idToken?: string | null;
  refreshToken?: string | null;
  expiresAt?: number | null;
  localId?: string | null;
};

export const STORAGE_KEYS = {
  walletAddress: 'cw_wallet_address',
  idToken: 'cw_id_token',
  refreshToken: 'cw_refresh_token',
  expiresAt: 'cw_expires_at',
  localId: 'cw_local_id',
  workshopCache: 'cw_workshop_cache'
};

const readString = (key: string) => {
  if (typeof window === 'undefined') return null;
  return window.localStorage.getItem(key);
};

const readNumber = (key: string) => {
  const value = readString(key);
  if (!value) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

export const readStoredSession = (): StoredSession => ({
  walletAddress: readString(STORAGE_KEYS.walletAddress),
  idToken: readString(STORAGE_KEYS.idToken),
  refreshToken: readString(STORAGE_KEYS.refreshToken),
  expiresAt: readNumber(STORAGE_KEYS.expiresAt),
  localId: readString(STORAGE_KEYS.localId)
});

export const writeStoredSession = (session: StoredSession) => {
  if (typeof window === 'undefined') return;
  const { walletAddress, idToken, refreshToken, expiresAt, localId } = session;
  const entries: Array<[string, string | null | undefined]> = [
    [STORAGE_KEYS.walletAddress, walletAddress],
    [STORAGE_KEYS.idToken, idToken],
    [STORAGE_KEYS.refreshToken, refreshToken],
    [STORAGE_KEYS.localId, localId]
  ];
  for (const [key, value] of entries) {
    if (value) {
      window.localStorage.setItem(key, value);
    } else {
      window.localStorage.removeItem(key);
    }
  }
  if (expiresAt) {
    window.localStorage.setItem(STORAGE_KEYS.expiresAt, String(expiresAt));
  } else {
    window.localStorage.removeItem(STORAGE_KEYS.expiresAt);
  }
};

export const clearStoredSession = () => {
  if (typeof window === 'undefined') return;
  Object.values(STORAGE_KEYS).forEach((key) => window.localStorage.removeItem(key));
};

export const writeWorkshopCache = (payload: unknown) => {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(STORAGE_KEYS.workshopCache, JSON.stringify({ payload, storedAt: Date.now() }));
};

export const readWorkshopCache = () => {
  if (typeof window === 'undefined') return null;
  const raw = window.localStorage.getItem(STORAGE_KEYS.workshopCache);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as { payload: unknown; storedAt: number };
  } catch {
    return null;
  }
};
