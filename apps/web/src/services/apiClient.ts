export interface ApiResponse<T> {
  ok: boolean;
  data?: T;
  error?: string;
}

const API_BASE = import.meta.env.VITE_API_BASE_URL || '';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, options);
  const data = await res.json();
  if (!res.ok) throw new Error(data?.error || 'Request failed');
  return data as T;
}

export const apiClient = {
  getNonce(walletAddress: string) {
    return request<{ ok: boolean; walletAddress: string; nonce: string }>('/api/cw/get_nonce', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ walletAddress }),
    });
  },
  loginForCustomToken(walletAddress: string, signature: string) {
    return request<{ ok: boolean; walletAddress: string; customToken: string }>(
      '/api/cw/login_for_custom_token',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ walletAddress, signature }),
      },
    );
  },
  signinWithCustomToken(customToken: string) {
    return request<{ ok: boolean; idToken: string; refreshToken: string; expiresIn: number }>(
      '/api/cw/signin_with_custom_token',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ customToken }),
      },
    );
  },
  accountStatus(token: string) {
    return request('/api/account_status', {
      headers: { Authorization: `Bearer ${token}` },
    });
  },
  accountWorkshop(token: string) {
    return request('/api/account_workshop', {
      headers: { Authorization: `Bearer ${token}` },
    });
  },
  accountProficiencies(token: string) {
    return request('/api/account_proficiencies', {
      headers: { Authorization: `Bearer ${token}` },
    });
  },
  accountUid(token: string) {
    return request<{ ok: boolean; uid: string }>('/api/account_uid', {
      headers: { Authorization: `Bearer ${token}` },
    });
  },
  syncBoosts(payload: { masteryLevels?: Record<string, number>; workshopLevels?: Record<string, number> }) {
    return request('/api/boosts/sync', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  },
  updateMastery(payload: { masteryLevels: Record<string, number> }) {
    return request('/api/boosts/mastery', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  },
};
