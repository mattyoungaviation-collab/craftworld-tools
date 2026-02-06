const API_BASE = import.meta.env.VITE_API_BASE_URL || '';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, options);
  if (!res.ok) {
    throw new Error(`Request failed (${res.status})`);
  }
  return (await res.json()) as T;
}

export async function fetchAccountStatus(token: string) {
  return request('/api/account_status', {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export async function fetchAccountWorkshop(token: string) {
  return request('/api/account_workshop', {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export async function fetchAccountProficiencies(token: string) {
  return request('/api/account_proficiencies', {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export async function syncBoosts(payload: {
  masteryLevels?: Record<string, number>;
  workshopLevels?: Record<string, number>;
}) {
  return request('/api/boosts/sync', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}
