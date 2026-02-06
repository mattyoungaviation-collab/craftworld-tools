import crypto from 'node:crypto';
import type { FastifyBaseLogger } from 'fastify';
import { cwGraphqlRequest } from './craftworldClient';

const ACCOUNT_STATUS_TTL = 5_000;

const statusCache = new Map<string, { ts: number; value: any }>();

const ACCOUNT_STATUS_QUERY = `
  query AccountStatus {
    account {
      power
      powerMillisecondsUntilRefill
      powerLastRefill
      updatedAt
    }
  }
`;

const formatHmsFromSeconds = (seconds: number) => {
  const value = Math.max(0, Math.trunc(seconds));
  const h = Math.floor(value / 3600);
  const m = Math.floor((value % 3600) / 60);
  const s = value % 60;
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
};

const tokenCacheKey = (token: string) =>
  crypto.createHash('sha256').update(token, 'utf8').digest('hex');

export async function fetchAccountStatus(jwtToken: string, logger?: FastifyBaseLogger) {
  const now = Date.now();
  const key = tokenCacheKey(jwtToken || '');
  const cached = statusCache.get(key);
  if (cached && now - cached.ts < ACCOUNT_STATUS_TTL) {
    return { ...cached.value };
  }

  const upstream = await cwGraphqlRequest(ACCOUNT_STATUS_QUERY, undefined, jwtToken, logger);
  const body = upstream.body || {};
  const errors = body.errors || [];
  if (!upstream.ok || errors.length) {
    const errorMessage = errors.length ? `Craft World error: ${JSON.stringify(errors)}` : 'Craft World auth failed.';
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
      error: errorMessage,
      rawErrors: errors,
    };
    statusCache.set(key, { ts: now, value: payload });
    return payload;
  }

  const account = body.data?.account || {};
  const ms = Number(account.powerMillisecondsUntilRefill || 0);
  const refillSeconds = Math.max(0, Math.trunc(ms / 1000));

  const payload = {
    ok: true,
    auth: 'ok',
    power: Number(account.power || 0),
    msUntilRefill: ms,
    refillSeconds,
    refillHMS: formatHmsFromSeconds(refillSeconds),
    primaryWallet: null,
    powerLastRefill: account.powerLastRefill ?? null,
    updatedAt: account.updatedAt ?? null,
  };
  statusCache.set(key, { ts: now, value: payload });
  return payload;
}
