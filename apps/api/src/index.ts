import Fastify from 'fastify';
import cors from '@fastify/cors';
import { z } from 'zod';
import {
  callGraphqlRaw,
  extractBearer,
  fetchAccountUid,
  fetchProficiencies,
  fetchWorkshopLevels,
  maskToken,
  normalizeCwToken,
} from './services/craftworldClient';
import { getAccountStatus } from './services/accountStatusCache';
import { updateMasteryLevels, updateWorkshopLevels } from './services/boostsStore';

const app = Fastify({ logger: true });

await app.register(cors, {
  origin: true,
  credentials: true,
});

const PORT = Number(process.env.PORT || 4000);
const IDENTITY_SIGNIN_URL = `https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken?key=${
  process.env.CRAFTWORLD_FIREBASE_API_KEY || 'AIzaSyDgDDykbRrhbdfWUpm1BUgj4ga7d_-wy_g'
}`;

app.get('/health', async () => ({ ok: true }));

app.post('/api/cw/get_nonce', async (request, reply) => {
  const schema = z.object({ walletAddress: z.string().min(1) });
  const parsed = schema.safeParse(request.body);
  if (!parsed.success) {
    return reply.status(400).send({ ok: false, error: 'walletAddress is required.' });
  }

  const query = `
    query($walletAddress: String!) {
      getNonce(walletAddress: $walletAddress) { nonce }
    }
  `;

  try {
    const upstream = await callGraphqlRaw(query, { walletAddress: parsed.data.walletAddress });
    const body = upstream.body as { data?: { getNonce?: { nonce?: string } }; errors?: unknown[] };
    const nonce = body?.data?.getNonce?.nonce;
    if (!upstream.ok || body?.errors?.length || !nonce) {
      return reply.status(400).send({ ok: false, error: 'Failed to fetch nonce.', rawErrors: body?.errors || [] });
    }
    return { ok: true, walletAddress: parsed.data.walletAddress, nonce };
  } catch (err) {
    return reply.status(502).send({ ok: false, error: `Failed to fetch nonce: ${String(err)}`, rawErrors: [] });
  }
});

app.post('/api/cw/login_for_custom_token', async (request, reply) => {
  const schema = z.object({ walletAddress: z.string().min(1), signature: z.string().min(1) });
  const parsed = schema.safeParse(request.body);
  if (!parsed.success) {
    return reply.status(400).send({ ok: false, error: 'walletAddress and signature are required.' });
  }

  const mutation = `
    mutation LoginForCustomToken($signature: String!, $walletAddress: String!) {
      loginForCustomToken(signature: $signature, walletAddress: $walletAddress) {
        customToken
      }
    }
  `;

  try {
    const upstream = await callGraphqlRaw(mutation, parsed.data);
    const body = upstream.body as { data?: { loginForCustomToken?: { customToken?: string } }; errors?: unknown[] };
    const customToken = body?.data?.loginForCustomToken?.customToken;
    if (!upstream.ok || body?.errors?.length || !customToken) {
      return reply.status(400).send({ ok: false, error: 'Failed to exchange signature.', rawErrors: body?.errors || [] });
    }
    return { ok: true, walletAddress: parsed.data.walletAddress, customToken };
  } catch (err) {
    return reply.status(502).send({ ok: false, error: `Failed to log in: ${String(err)}`, rawErrors: [] });
  }
});

app.post('/api/cw/signin_with_custom_token', async (request, reply) => {
  const schema = z.object({ customToken: z.string().min(1) });
  const parsed = schema.safeParse(request.body);
  if (!parsed.success) {
    return reply.status(400).send({ ok: false, error: 'customToken is required.' });
  }

  try {
    const response = await fetch(IDENTITY_SIGNIN_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token: parsed.data.customToken, returnSecureToken: true }),
    });
    const body = (await response.json()) as { idToken?: string; refreshToken?: string; expiresIn?: string; error?: unknown };
    if (!response.ok || body?.error) {
      return reply.status(400).send({ ok: false, error: 'Failed to sign in with custom token.', rawErrors: body?.error ? [body.error] : [] });
    }
    return {
      ok: true,
      idToken: body.idToken,
      refreshToken: body.refreshToken,
      expiresIn: Number(body.expiresIn || 0),
    };
  } catch (err) {
    return reply.status(502).send({ ok: false, error: `IdentityToolkit request failed: ${String(err)}`, rawErrors: [] });
  }
});

app.get('/api/account_status', async (request, reply) => {
  const authorization = request.headers.authorization;
  const fromHeader = extractBearer(authorization);
  const fromQuery = String((request.query as { cw_idToken?: string }).cw_idToken || '');
  const jwtToken = normalizeCwToken(fromHeader || fromQuery);

  app.log.debug({ hasToken: Boolean(jwtToken), length: jwtToken.length, token: maskToken(jwtToken) }, 'account_status');

  if (!jwtToken) {
    return reply.send({
      ok: false,
      auth: 'missing_or_invalid',
      power: null,
      msUntilRefill: null,
      refillSeconds: null,
      refillHMS: null,
      primaryWallet: null,
      error: 'Missing idToken',
      rawErrors: [],
    });
  }

  const payload = await getAccountStatus(jwtToken);
  return reply.send(payload);
});

app.get('/api/account_workshop', async (request, reply) => {
  const token = normalizeCwToken(extractBearer(request.headers.authorization));
  if (!token) {
    return reply.send({ ok: false, auth: 'missing_or_invalid', error: 'Missing token' });
  }

  try {
    const workshopMap = await fetchWorkshopLevels(token);
    const workshop = Object.entries(workshopMap)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([symbol, level]) => ({ symbol, level: Number(level) }));
    return reply.send({ ok: true, workshop, updatedAt: new Date().toISOString() });
  } catch (err) {
    return reply.send({ ok: false, auth: 'missing_or_invalid', error: String(err) });
  }
});

app.get('/api/account_proficiencies', async (request, reply) => {
  const token = normalizeCwToken(extractBearer(request.headers.authorization));
  if (!token) {
    return reply.send({ ok: false, auth: 'missing_or_invalid', error: 'Missing token' });
  }

  try {
    const profMap = await fetchProficiencies(token);
    const proficiencies = Object.entries(profMap)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([symbol, values]) => ({
        symbol,
        collectedAmount: Number(values.collectedAmount || 0),
        claimedLevel: Number(values.claimedLevel || 0),
      }));
    return reply.send({ ok: true, proficiencies, updatedAt: new Date().toISOString() });
  } catch (err) {
    return reply.send({ ok: false, auth: 'missing_or_invalid', error: String(err) });
  }
});

app.get('/api/account_uid', async (request, reply) => {
  const authorization = request.headers.authorization;
  const fromHeader = extractBearer(authorization);
  const fromQuery = String((request.query as { cw_idToken?: string }).cw_idToken || '');
  const jwtToken = normalizeCwToken(fromHeader || fromQuery);

  if (!jwtToken) {
    return reply.status(401).send({ ok: false, error: 'Missing Craft World token.' });
  }

  const { uid, errors } = await fetchAccountUid(jwtToken);
  if (errors && (errors as unknown[]).length) {
    return reply.status(502).send({ ok: false, error: 'Craft World returned an error.', rawErrors: errors });
  }
  if (!uid) {
    return reply.status(404).send({ ok: false, error: 'Craft World account UID not found.' });
  }

  return reply.send({ ok: true, uid });
});

app.post('/api/boosts/mastery', async (request, reply) => {
  const schema = z.object({ masteryLevels: z.record(z.number()) });
  const parsed = schema.safeParse(request.body);
  if (!parsed.success) {
    return reply.status(400).send({ ok: false, error: 'masteryLevels map is required.' });
  }
  const updated = updateMasteryLevels(parsed.data.masteryLevels);
  return reply.send({ ok: true, updated, updatedAt: new Date().toISOString() });
});

app.post('/api/boosts/sync', async (request, reply) => {
  const schema = z.object({
    masteryLevels: z.record(z.number()).optional(),
    workshopLevels: z.record(z.number()).optional(),
  });
  const parsed = schema.safeParse(request.body);
  if (!parsed.success) {
    return reply.status(400).send({ ok: false, error: 'JSON body is required.' });
  }
  if (!parsed.data.masteryLevels && !parsed.data.workshopLevels) {
    return reply.status(400).send({ ok: false, error: 'masteryLevels or workshopLevels map is required.' });
  }

  const masteryUpdated = parsed.data.masteryLevels ? updateMasteryLevels(parsed.data.masteryLevels) : 0;
  const workshopUpdated = parsed.data.workshopLevels ? updateWorkshopLevels(parsed.data.workshopLevels) : 0;

  return reply.send({ ok: true, masteryUpdated, workshopUpdated, updatedAt: new Date().toISOString() });
});

app.listen({ port: PORT, host: '0.0.0.0' }).catch((err) => {
  app.log.error(err);
  process.exit(1);
});
