const ID_TOKEN_KEY = 'cw_idToken';
const CW_TOKEN_KEY = 'cw_token';
const REFRESH_TOKEN_KEY = 'cw_refreshToken';
const EXPIRES_AT_KEY = 'cw_expiresAt';
const WALLET_KEY = 'cw_wallet';
const CW_SESSION_INDEX_KEY = 'cw_sessions';
const CW_ACTIVE_WALLET_KEY = 'cw_active_wallet';
const ACCOUNT_STATUS_KEY = 'cw_account_status';
const CONNECTION_TYPE_KEY = 'cw_connection_type';

export const STORAGE_SCHEMA_VERSION = 1;

export type WalletSessionIndex = Record<
  string,
  {
    token: string;
    expiresAt: number;
    refreshToken: string;
    lastLoginAt: number;
    idToken: string;
  }
>;

function normalizeWallet(wallet?: string): string {
  return String(wallet || '').trim().toLowerCase();
}

function readSessionIndex(): WalletSessionIndex {
  try {
    const parsed = JSON.parse(localStorage.getItem(CW_SESSION_INDEX_KEY) || '{}');
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch (_err) {
    return {};
  }
}

function writeSessionIndex(index: WalletSessionIndex) {
  localStorage.setItem(CW_SESSION_INDEX_KEY, JSON.stringify(index || {}));
}

function syncLegacyFromActiveWallet(activeWallet: string) {
  const sessions = readSessionIndex();
  const entry = sessions[activeWallet];
  if (!entry) return;
  localStorage.setItem(ID_TOKEN_KEY, entry.idToken || '');
  localStorage.setItem(CW_TOKEN_KEY, entry.token || '');
  localStorage.setItem(REFRESH_TOKEN_KEY, entry.refreshToken || '');
  localStorage.setItem(EXPIRES_AT_KEY, String(entry.expiresAt || 0));
}

export function migrateStorage(): void {
  const activeWallet = normalizeWallet(localStorage.getItem(CW_ACTIVE_WALLET_KEY) || '');
  const legacyWallet = normalizeWallet(localStorage.getItem(WALLET_KEY) || '');
  const resolvedWallet = activeWallet || legacyWallet;

  if (resolvedWallet && !activeWallet) {
    localStorage.setItem(CW_ACTIVE_WALLET_KEY, resolvedWallet);
  }

  const sessions = readSessionIndex();
  const legacyToken = localStorage.getItem(CW_TOKEN_KEY) || '';
  const legacyExpires = Number(localStorage.getItem(EXPIRES_AT_KEY) || 0);
  const legacyRefresh = localStorage.getItem(REFRESH_TOKEN_KEY) || '';
  const legacyIdToken = localStorage.getItem(ID_TOKEN_KEY) || legacyToken;

  if (resolvedWallet && legacyToken && !sessions[resolvedWallet]) {
    sessions[resolvedWallet] = {
      token: legacyToken,
      idToken: legacyIdToken,
      expiresAt: legacyExpires,
      refreshToken: legacyRefresh,
      lastLoginAt: Date.now(),
    };
    writeSessionIndex(sessions);
  }

  if (resolvedWallet) {
    syncLegacyFromActiveWallet(resolvedWallet);
  }
}

export function getAccountStatusCache() {
  try {
    const parsed = JSON.parse(localStorage.getItem(ACCOUNT_STATUS_KEY) || '{}');
    return parsed && typeof parsed === 'object' ? parsed : null;
  } catch (_err) {
    return null;
  }
}

export function clearWalletSession() {
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
