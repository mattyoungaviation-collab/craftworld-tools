import crypto from 'node:crypto';
import { fetchAccountStatus, normalizeCwToken } from './craftworldClient';

const CACHE_TTL_MS = 5000;
const cache = new Map<string, { ts: number; payload: Record<string, unknown> }>();

function tokenKey(token: string): string {
  return crypto.createHash('sha256').update(token).digest('hex');
}

function formatHms(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

export async function getAccountStatus(jwtToken: string): Promise<Record<string, unknown>> {
  const normalized = normalizeCwToken(jwtToken) || '';
  const key = tokenKey(normalized);
  const now = Date.now();
  const cached = cache.get(key);
  if (cached && now - cached.ts < CACHE_TTL_MS) {
    return { ...cached.payload };
  }

  try {
    const account = await fetchAccountStatus(normalized);
    const ms = Number(account.powerMillisecondsUntilRefill || 0);
    const refillSeconds = Math.max(0, Math.floor(ms / 1000));
    const payload = {
      ok: true,
      auth: 'ok',
      power: Number(account.power || 0),
      msUntilRefill: ms,
      refillSeconds,
      refillHMS: formatHms(refillSeconds),
      primaryWallet: null,
      powerLastRefill: account.powerLastRefill ?? null,
      updatedAt: account.updatedAt ?? null,
    };
    cache.set(key, { ts: now, payload });
    return payload;
  } catch (err) {
    const payload = {
      ok: false,
      auth: 'missing_or_invalid',
      power: null,
      msUntilRefill: null,
      refillSeconds: null,
      refillHMS: null,
      primaryWallet: null,
      powerLastRefill: null,
      updatedAt: null,
      error: `Craft World auth failed: ${String(err)}`,
      rawErrors: [],
    };
    cache.set(key, { ts: now, payload });
    return payload;
  }
}
