export type AuthStatus =
  | 'disconnected'
  | 'connecting'
  | 'connected'
  | 'logging_in'
  | 'authenticated'
  | 'error';

export type AuthState = {
  status: AuthStatus;
  walletAddress?: string;
  idToken?: string;
  refreshToken?: string;
  expiresAt?: number;
  localId?: string;
  error?: string;
};

export const authStorageKeys = {
  walletAddress: 'cw_wallet_address',
  idToken: 'cw_id_token',
  refreshToken: 'cw_refresh_token',
  expiresAt: 'cw_expires_at',
  localId: 'cw_local_id'
};

export const playerProfileKey = 'cw_player_profile';

export const emptyAuthState = (): AuthState => ({
  status: 'disconnected'
});

export const loadAuthState = (): AuthState => {
  if (typeof window === 'undefined') {
    return emptyAuthState();
  }
  const walletAddress = window.localStorage.getItem(authStorageKeys.walletAddress) || undefined;
  const idToken = window.localStorage.getItem(authStorageKeys.idToken) || undefined;
  const refreshToken = window.localStorage.getItem(authStorageKeys.refreshToken) || undefined;
  const expiresAtRaw = window.localStorage.getItem(authStorageKeys.expiresAt);
  const localId = window.localStorage.getItem(authStorageKeys.localId) || undefined;
  const expiresAt = expiresAtRaw ? Number(expiresAtRaw) : undefined;
  if (idToken && expiresAt && Date.now() < expiresAt) {
    return {
      status: 'authenticated',
      walletAddress,
      idToken,
      refreshToken,
      expiresAt,
      localId
    };
  }
  if (walletAddress) {
    return {
      status: 'connected',
      walletAddress,
      idToken,
      refreshToken,
      expiresAt,
      localId
    };
  }
  return emptyAuthState();
};

export const persistAuthState = (state: AuthState) => {
  if (typeof window === 'undefined') {
    return;
  }
  if (state.walletAddress) {
    window.localStorage.setItem(authStorageKeys.walletAddress, state.walletAddress);
  } else {
    window.localStorage.removeItem(authStorageKeys.walletAddress);
  }
  if (state.idToken) {
    window.localStorage.setItem(authStorageKeys.idToken, state.idToken);
  } else {
    window.localStorage.removeItem(authStorageKeys.idToken);
  }
  if (state.refreshToken) {
    window.localStorage.setItem(authStorageKeys.refreshToken, state.refreshToken);
  } else {
    window.localStorage.removeItem(authStorageKeys.refreshToken);
  }
  if (state.expiresAt) {
    window.localStorage.setItem(authStorageKeys.expiresAt, String(state.expiresAt));
  } else {
    window.localStorage.removeItem(authStorageKeys.expiresAt);
  }
  if (state.localId) {
    window.localStorage.setItem(authStorageKeys.localId, state.localId);
  } else {
    window.localStorage.removeItem(authStorageKeys.localId);
  }
};

export const clearAuthState = () => {
  if (typeof window === 'undefined') {
    return;
  }
  Object.values(authStorageKeys).forEach((key) => window.localStorage.removeItem(key));
};

export const buildLoginMessage = (walletAddress: string, nonce: string, issuedAt: string) =>
  `CraftWorld login\nwallet: ${walletAddress}\nnonce: ${nonce}\nissuedAt: ${issuedAt}`;

export const computeExpiresAt = (expiresInSeconds: number) =>
  Date.now() + expiresInSeconds * 1000 - 30_000;

export const redactTokens = <T>(value: T): T => {
  if (value === null || value === undefined) {
    return value;
  }
  if (Array.isArray(value)) {
    return value.map((item) => redactTokens(item)) as T;
  }
  if (typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>).map(([key, val]) => {
      if (key.toLowerCase().includes('token')) {
        return [key, '[redacted]'];
      }
      if (key.toLowerCase().includes('refresh')) {
        return [key, '[redacted]'];
      }
      return [key, redactTokens(val)];
    });
    return Object.fromEntries(entries) as T;
  }
  return value;
};

export const shortenAddress = (address?: string) => {
  if (!address) return '—';
  return `${address.slice(0, 6)}...${address.slice(-4)}`;
};
