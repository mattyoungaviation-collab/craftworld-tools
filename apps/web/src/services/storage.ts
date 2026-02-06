export const STORAGE_SCHEMA_VERSION = 1;
const SCHEMA_KEY = 'cw_storage_schema_version';

export const ID_TOKEN_KEY = 'cw_idToken';
export const CW_TOKEN_KEY = 'cw_token';
export const REFRESH_TOKEN_KEY = 'cw_refreshToken';
export const EXPIRES_AT_KEY = 'cw_expiresAt';
export const WALLET_KEY = 'cw_wallet';
export const CW_SESSION_INDEX_KEY = 'cw_sessions';
export const CW_ACTIVE_WALLET_KEY = 'cw_active_wallet';
export const ACCOUNT_STATUS_KEY = 'cw_account_status';
export const CONNECTION_TYPE_KEY = 'cw_connection_type';

export interface WalletSession {
  token: string;
  expiresAt: number;
  refreshToken: string;
  lastLoginAt: number;
  idToken: string;
}

export function normalizeWalletAddress(addr: string) {
  return String(addr || '').trim().toLowerCase();
}

export function getBoostStorageKey(wallet: string) {
  return `cw_boosts:${normalizeWalletAddress(wallet)}`;
}

export function readSessionIndex(): Record<string, WalletSession> {
  try {
    const parsed = JSON.parse(localStorage.getItem(CW_SESSION_INDEX_KEY) || '{}');
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
}

export function writeSessionIndex(index: Record<string, WalletSession>) {
  localStorage.setItem(CW_SESSION_INDEX_KEY, JSON.stringify(index || {}));
}

export function getActiveWallet() {
  return normalizeWalletAddress(localStorage.getItem(CW_ACTIVE_WALLET_KEY) || '');
}

export function setActiveWallet(wallet: string) {
  const normalized = normalizeWalletAddress(wallet);
  if (normalized) {
    localStorage.setItem(CW_ACTIVE_WALLET_KEY, normalized);
    localStorage.setItem(WALLET_KEY, normalized);
  } else {
    localStorage.removeItem(CW_ACTIVE_WALLET_KEY);
    localStorage.removeItem(WALLET_KEY);
  }
}

export function migrateStorage() {
  try {
    const current = Number(localStorage.getItem(SCHEMA_KEY) || 0);
    if (current >= STORAGE_SCHEMA_VERSION) return;

    const legacyToken = String(localStorage.getItem(CW_TOKEN_KEY) || '').trim();
    const legacyExpiresAt = Number(localStorage.getItem(EXPIRES_AT_KEY) || 0);
    const legacyRefresh = String(localStorage.getItem(REFRESH_TOKEN_KEY) || '').trim();
    const legacyIdToken = String(localStorage.getItem(ID_TOKEN_KEY) || '').trim();
    const legacyWallet = normalizeWalletAddress(localStorage.getItem(WALLET_KEY) || '');

    if (legacyToken && legacyWallet) {
      const sessions = readSessionIndex();
      sessions[legacyWallet] = {
        token: legacyToken,
        expiresAt: legacyExpiresAt,
        refreshToken: legacyRefresh,
        lastLoginAt: Date.now(),
        idToken: legacyIdToken,
      };
      writeSessionIndex(sessions);
      setActiveWallet(legacyWallet);
    }

    localStorage.setItem(SCHEMA_KEY, String(STORAGE_SCHEMA_VERSION));
  } catch {
    // ignore
  }
}

export function clearSession() {
  localStorage.removeItem(ID_TOKEN_KEY);
  localStorage.removeItem(CW_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
  localStorage.removeItem(EXPIRES_AT_KEY);
  localStorage.removeItem(WALLET_KEY);
  localStorage.removeItem(CW_ACTIVE_WALLET_KEY);
  localStorage.removeItem(CW_SESSION_INDEX_KEY);
  localStorage.removeItem(ACCOUNT_STATUS_KEY);
  localStorage.removeItem(CONNECTION_TYPE_KEY);
}
