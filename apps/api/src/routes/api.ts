import { z } from 'zod';
import type { FastifyInstance } from 'fastify';
import { cwGraphqlRequest, extractBearerToken, getRequestToken, normalizeCwToken } from '../services/craftworldClient';
import { fetchAccountStatus } from '../services/accountStatus';

const CW_FIREBASE_API_KEY =
  process.env.CW_FIREBASE_API_KEY || 'AIzaSyDgDDykbRrhbdfWUpm1BUgj4ga7d_-wy_g';
const CW_IDENTITY_SIGNIN_URL = `https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken?key=${CW_FIREBASE_API_KEY}`;

const nonceSchema = z.object({
  walletAddress: z.string().min(1),
});

const signatureSchema = z.object({
  walletAddress: z.string().min(1),
  signature: z.string().min(1),
});

const customTokenSchema = z.object({
  customToken: z.string().min(1),
});

const masterySchema = z.object({
  masteryLevels: z.record(z.union([z.number(), z.string()])),
});

const syncSchema = z.object({
  masteryLevels: z.record(z.union([z.number(), z.string()])).optional(),
  workshopLevels: z.record(z.union([z.number(), z.string()])).optional(),
});

const GET_NONCE_QUERY = `
  query($walletAddress: String!) {
    getNonce(walletAddress: $walletAddress) { nonce }
  }
`;

const LOGIN_FOR_CUSTOM_TOKEN_MUTATION = `
  mutation LoginForCustomToken($signature: String!, $walletAddress: String!) {
    loginForCustomToken(signature: $signature, walletAddress: $walletAddress) {
      customToken
    }
  }
`;

const ACCOUNT_UID_QUERY = `
  query AccountUID {
    account { id }
  }
`;

const WORKSHOP_QUERY = `
  query {
    account { workshop { symbol level } }
  }
`;

const PROFICIENCIES_QUERY = `
  query {
    account { proficiencies { symbol collectedAmount claimedLevel } }
  }
`;

export async function registerApiRoutes(app: FastifyInstance) {
  app.post('/api/cw/get_nonce', async (request, reply) => {
    const parsed = nonceSchema.safeParse(request.body);
    if (!parsed.success) {
      return reply.status(400).send({ ok: false, error: 'walletAddress is required.' });
    }

    const { walletAddress } = parsed.data;
    try {
      const upstream = await cwGraphqlRequest(GET_NONCE_QUERY, { walletAddress }, undefined, app.log);
      const body = upstream.body || {};
      const rawErrors = body.errors || [];
      const nonce = body.data?.getNonce?.nonce;
      if (!upstream.ok || rawErrors.length || !nonce) {
        return reply.status(400).send({ ok: false, error: 'Failed to fetch nonce.', rawErrors });
      }
      return reply.send({ ok: true, walletAddress, nonce });
    } catch (err: any) {
      return reply.status(502).send({ ok: false, error: `Failed to fetch nonce: ${err?.message || err}` });
    }
  });

  app.post('/api/cw/login_for_custom_token', async (request, reply) => {
    const parsed = signatureSchema.safeParse(request.body);
    if (!parsed.success) {
      return reply
        .status(400)
        .send({ ok: false, error: 'walletAddress and signature are required.' });
    }

    const { walletAddress, signature } = parsed.data;
    try {
      const upstream = await cwGraphqlRequest(
        LOGIN_FOR_CUSTOM_TOKEN_MUTATION,
        { signature, walletAddress },
        undefined,
        app.log,
      );
      const body = upstream.body || {};
      const rawErrors = body.errors || [];
      const customToken = body.data?.loginForCustomToken?.customToken;
      if (!upstream.ok || rawErrors.length || !customToken) {
        return reply.status(400).send({ ok: false, error: 'Failed to exchange signature.', rawErrors });
      }
      return reply.send({ ok: true, walletAddress, customToken });
    } catch (err: any) {
      return reply.status(502).send({ ok: false, error: `Failed to log in: ${err?.message || err}` });
    }
  });

  app.post('/api/cw/signin_with_custom_token', async (request, reply) => {
    const parsed = customTokenSchema.safeParse(request.body);
    if (!parsed.success) {
      return reply.status(400).send({ ok: false, error: 'customToken is required.' });
    }

    try {
      const response = await fetch(CW_IDENTITY_SIGNIN_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: parsed.data.customToken, returnSecureToken: true }),
      });
      const body = await response.json();
      if (!response.ok || body.error) {
        return reply.status(400).send({
          ok: false,
          error: 'Failed to sign in with custom token.',
          rawErrors: body.error ? [body.error] : [],
        });
      }
      return reply.send({
        ok: true,
        idToken: body.idToken,
        refreshToken: body.refreshToken,
        expiresIn: Number(body.expiresIn || 0),
      });
    } catch (err: any) {
      return reply.status(502).send({ ok: false, error: `IdentityToolkit request failed: ${err?.message || err}` });
    }
  });

  app.get('/api/account_status', async (request, reply) => {
    const token = getRequestToken(request.headers.authorization, (request.query as any)?.cw_idToken);
    if (!token) {
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
    const payload = await fetchAccountStatus(token, app.log);
    return reply.send(payload);
  });

  app.get('/api/account_workshop', async (request, reply) => {
    const token = normalizeCwToken(extractBearerToken(request.headers.authorization) || undefined);
    if (!token) {
      return reply.send({ ok: false, auth: 'missing_or_invalid', error: 'Missing token' });
    }

    try {
      const upstream = await cwGraphqlRequest(WORKSHOP_QUERY, undefined, token, app.log);
      const body = upstream.body || {};
      const errors = body.errors || [];
      if (!upstream.ok || errors.length) {
        return reply.send({ ok: false, auth: 'missing_or_invalid', error: JSON.stringify(errors) });
      }
      const workshop = (body.data?.account?.workshop || []).map((row: any) => ({
        symbol: String(row.symbol || '').toUpperCase(),
        level: Number(row.level || 0),
      }));
      return reply.send({
        ok: true,
        workshop,
        updatedAt: new Date().toISOString(),
      });
    } catch (err: any) {
      return reply.send({ ok: false, auth: 'missing_or_invalid', error: String(err?.message || err) });
    }
  });

  app.get('/api/account_proficiencies', async (request, reply) => {
    const token = normalizeCwToken(extractBearerToken(request.headers.authorization) || undefined);
    if (!token) {
      return reply.send({ ok: false, auth: 'missing_or_invalid', error: 'Missing token' });
    }

    try {
      const upstream = await cwGraphqlRequest(PROFICIENCIES_QUERY, undefined, token, app.log);
      const body = upstream.body || {};
      const errors = body.errors || [];
      if (!upstream.ok || errors.length) {
        return reply.send({ ok: false, auth: 'missing_or_invalid', error: JSON.stringify(errors) });
      }
      const proficiencies = (body.data?.account?.proficiencies || []).map((row: any) => ({
        symbol: String(row.symbol || '').toUpperCase(),
        collectedAmount: Number(row.collectedAmount || 0),
        claimedLevel: Number(row.claimedLevel || 0),
      }));
      return reply.send({
        ok: true,
        proficiencies,
        updatedAt: new Date().toISOString(),
      });
    } catch (err: any) {
      return reply.send({ ok: false, auth: 'missing_or_invalid', error: String(err?.message || err) });
    }
  });

  app.get('/api/account_uid', async (request, reply) => {
    const token = getRequestToken(request.headers.authorization, (request.query as any)?.cw_idToken);
    if (!token) {
      return reply.status(401).send({ ok: false, error: 'Missing Craft World token.' });
    }

    const upstream = await cwGraphqlRequest(ACCOUNT_UID_QUERY, undefined, token, app.log);
    const body = upstream.body || {};
    const errors = body.errors || [];
    if (errors.length) {
      return reply.status(502).send({ ok: false, error: 'Craft World returned an error.', rawErrors: errors });
    }
    const uid = body.data?.account?.id;
    if (!uid) {
      return reply.status(404).send({ ok: false, error: 'Craft World account UID not found.' });
    }
    return reply.send({ ok: true, uid });
  });

  app.post('/api/boosts/mastery', async (request, reply) => {
    const parsed = masterySchema.safeParse(request.body);
    if (!parsed.success) {
      return reply.status(400).send({ ok: false, error: 'masteryLevels map is required.' });
    }

    const updated = Object.keys(parsed.data.masteryLevels || {}).length;
    return reply.send({ ok: true, updated, updatedAt: new Date().toISOString() });
  });

  app.post('/api/boosts/sync', async (request, reply) => {
    const parsed = syncSchema.safeParse(request.body);
    if (!parsed.success) {
      return reply.status(400).send({ ok: false, error: 'JSON body is required.' });
    }

    if (!parsed.data.masteryLevels && !parsed.data.workshopLevels) {
      return reply
        .status(400)
        .send({ ok: false, error: 'masteryLevels or workshopLevels map is required.' });
    }

    const masteryUpdated = parsed.data.masteryLevels ? Object.keys(parsed.data.masteryLevels).length : 0;
    const workshopUpdated = parsed.data.workshopLevels
      ? Object.keys(parsed.data.workshopLevels).length
      : 0;

    return reply.send({
      ok: true,
      masteryUpdated,
      workshopUpdated,
      updatedAt: new Date().toISOString(),
    });
  });
}
