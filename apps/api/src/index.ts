import Fastify from 'fastify';
import cors from '@fastify/cors';
import { randomBytes } from 'node:crypto';
import { verifyMessage } from 'ethers';
import { createRedisClient } from './redis.js';
import { cwGraphqlRequest } from './graphql.js';
import { readSnapshot, writeSnapshot } from './cache.js';
import { getConfigPayload, getDefsPayload } from './data.js';
import { getPrismaClient } from './db.js';
import { createCustomToken, isFirebaseConfigured, verifyIdToken } from './firebase.js';

const server = Fastify({ logger: true });

type PricesItem = { symbol: string; price: number };
type PricesPayload = { exchangePriceList: PricesItem[] };

// CraftWorld GraphQL (new nested shape)
type PricesGqlPayload = {
  exchangePriceList: {
    prices: Record<string, unknown>[];
  };
};

const PRICE_TTL_MS = 60_000;
const inMemoryCache: { prices?: { data: PricesPayload; fetchedAt: number } } = {};
const nonceStore = new Map<string, string>();

// Cache the discovered field names once we find a working combo
let discoveredPricesFields: { symbolField: string; priceField: string } | null = null;

const requireFirebase = (reply: { code: (status: number) => { send: (payload: unknown) => void } }) => {
  if (!isFirebaseConfigured()) {
    reply.code(501).send({ error: 'Firebase not configured' });
    return false;
  }
  return true;
};

const getAuthContext = async (request: { headers: Record<string, string | string[] | undefined> }) => {
  const headerValue = request.headers.authorization;
  const authHeader = Array.isArray(headerValue) ? headerValue[0] ?? '' : headerValue ?? '';
  const token = authHeader.startsWith('Bearer ') ? authHeader.slice(7) : null;
  if (!token) return null;

  const decoded = await verifyIdToken(token);
  const walletAddress = decoded.uid || (decoded as { walletAddress?: string }).walletAddress;
  if (!walletAddress) return null;

  return { walletAddress, firebaseUid: decoded.uid };
};

const normalizePrices = (rows: Record<string, unknown>[], symbolField: string, priceField: string): PricesPayload => {
  const list: PricesItem[] = rows
    .map((row) => {
      const sym = row[symbolField];
      const pr = row[priceField];

      const symbol = typeof sym === 'string' ? sym : typeof sym === 'number' ? String(sym) : '';
      const price =
        typeof pr === 'number'
          ? pr
          : typeof pr === 'string'
            ? Number(pr)
            : typeof pr === 'bigint'
              ? Number(pr)
              : NaN;

      if (!symbol || !Number.isFinite(price)) return null;
      return { symbol, price };
    })
    .filter((x): x is PricesItem => Boolean(x));

  return { exchangePriceList: list };
};

const buildPricesQuery = (symbolField: string, priceField: string) => {
  // NOTE: No introspection fields used here.
  return `query exchangePriceList {
    exchangePriceList {
      prices {
        ${symbolField}
        ${priceField}
      }
    }
  }`;
};

const probePricesFields = async (): Promise<{ symbolField: string; priceField: string }> => {
  // If we already found a working combo, reuse it.
  if (discoveredPricesFields) return discoveredPricesFields;

  // Candidates (ordered by likelihood)
  const symbolCandidates = [
    'symbol',
    'token',
    'resourceSymbol',
    'itemSymbol',
    'resource',
    'id',
    'name',
    'key'
  ];

  const priceCandidates = [
    'price',
    'prices',
    'value',
    'amount',
    'coinPrice',
    'rate',
    'exchangePrice',
    'coinValue'
  ];

  // Try all reasonable combos (small set; fast)
  for (const symbolField of symbolCandidates) {
    for (const priceField of priceCandidates) {
      const query = buildPricesQuery(symbolField, priceField);

      try {
        const gql = await cwGraphqlRequest<PricesGqlPayload>('exchangePriceList', query);
        const rows = gql?.exchangePriceList?.prices ?? [];
        const normalized = normalizePrices(rows, symbolField, priceField);

        // Accept the first combo that yields data or at least doesn’t error
        // (Even if empty, it means fields are valid and upstream schema matches.)
        discoveredPricesFields = { symbolField, priceField };
        server.log.info({ symbolField, priceField, count: normalized.exchangePriceList.length }, 'Discovered prices fields');
        return discoveredPricesFields;
      } catch (err) {
        // keep probing
        continue;
      }
    }
  }

  throw new Error('Could not determine CraftWorld price field names (all probes failed)');
};

const fetchPricesFromCraftWorld = async (): Promise<PricesPayload> => {
  const { symbolField, priceField } = await probePricesFields();
  const query = buildPricesQuery(symbolField, priceField);
  const gql = await cwGraphqlRequest<PricesGqlPayload>('exchangePriceList', query);
  const rows = gql?.exchangePriceList?.prices ?? [];
  return normalizePrices(rows, symbolField, priceField);
};

const start = async () => {
  const redis = createRedisClient();

  await server.register(cors, {
    origin: process.env.NEXT_PUBLIC_WEB_ORIGIN ? [process.env.NEXT_PUBLIC_WEB_ORIGIN] : true
  });

  server.get('/health', async () => ({
    ok: true,
    service: 'craftworld-companion-api',
    version: process.env.SERVICE_VERSION ?? 'local',
    uptime: process.uptime(),
    time: new Date().toISOString()
  }));

  server.get('/ready', async () => {
    const dbReady = Boolean(process.env.DATABASE_URL);
    const redisReady = Boolean(redis && redis.status === 'ready');
    const firebaseReady = isFirebaseConfigured();
    const degraded = !dbReady || (redis && !redisReady);

    return {
      ok: true,
      deps: {
        db: dbReady,
        redis: redisReady,
        firebase: firebaseReady
      },
      degraded
    };
  });

  server.get('/config', async () => {
    const payload = getConfigPayload();
    await writeSnapshot('config', payload);
    return payload;
  });

  server.get('/defs', async () => {
    const payload = getDefsPayload();
    await writeSnapshot('defs', payload);
    return payload;
  });

  // Optional: a quick endpoint to see what combo was discovered
  server.get('/debug/prices-fields', async () => ({
    discovered: discoveredPricesFields
  }));

  // IMPORTANT: never throw from /prices (avoid crashing Next pages)
  server.get('/prices', async (req, reply) => {
    const now = Date.now();

    try {
      // in-memory cache
      if (inMemoryCache.prices && now - inMemoryCache.prices.fetchedAt < PRICE_TTL_MS) {
        return inMemoryCache.prices.data;
      }

      const redisKey = 'prices';

      // redis cache
      if (redis) {
        try {
          const cached = await redis.get(redisKey);
          if (cached) {
            const parsed = JSON.parse(cached) as PricesPayload;
            inMemoryCache.prices = { data: parsed, fetchedAt: now };
            return parsed;
          }
        } catch (error) {
          server.log.warn({ err: error }, 'Redis cache unavailable for prices');
        }
      }

      // disk snapshot fallback
      const snapshot = await readSnapshot('prices');
      if (snapshot) {
        inMemoryCache.prices = { data: snapshot as PricesPayload, fetchedAt: now };
        server.log.warn('Serving prices from disk snapshot');

        // refresh snapshot in background
        void (async () => {
          try {
            const fresh = await fetchPricesFromCraftWorld();
            inMemoryCache.prices = { data: fresh, fetchedAt: Date.now() };
            if (redis) await redis.set(redisKey, JSON.stringify(fresh), 'EX', 60);
            await writeSnapshot('prices', fresh);
          } catch (error) {
            server.log.error({ err: error }, 'Failed to refresh prices snapshot');
          }
        })();

        return snapshot as PricesPayload;
      }

      // live fetch
      const data = await fetchPricesFromCraftWorld();

      inMemoryCache.prices = { data, fetchedAt: now };
      if (redis) await redis.set(redisKey, JSON.stringify(data), 'EX', 60);
      await writeSnapshot('prices', data);

      return data;
    } catch (err) {
      server.log.error({ err }, 'prices failed');
      // safe fallback so UI still loads
      return reply.code(200).send({
        exchangePriceList: [],
        ok: false,
        error: 'prices_unavailable'
      });
    }
  });

  server.get('/masterpieces', async () => {
    const snapshot = await readSnapshot('masterpieces');
    try {
      const data = await cwGraphqlRequest<{ masterpieces: unknown[] }>(
        'Masterpieces',
        'query Masterpieces { masterpieces { id name type collectedPoints requiredPoints addressableLabel } }'
      );
      await writeSnapshot('masterpieces', data);
      return data;
    } catch (error) {
      if (snapshot) {
        server.log.warn({ err: error }, 'Serving masterpieces from snapshot');
        return snapshot;
      }
      throw error;
    }
  });

  server.get('/masterpieces/:id', async (request, reply) => {
    const { id } = request.params as { id: string };
    const snapshot = await readSnapshot(`masterpiece_${id}`);
    try {
      const data = await cwGraphqlRequest<{ masterpiece: unknown }>(
        'Masterpiece',
        'query Masterpiece($id: ID!) { masterpiece(id: $id) { id name type collectedPoints requiredPoints addressableLabel resources { symbol amount target consumedPowerPerUnit } leaderboard { position masterpiecePoints profile { uid walletAddress avatarUrl displayName } } } }',
        { id }
      );
      await writeSnapshot(`masterpiece_${id}`, data);
      return data;
    } catch (error) {
      if (snapshot) {
        server.log.warn({ err: error }, 'Serving masterpiece from snapshot');
        return snapshot;
      }
      reply.code(502).send({ error: 'Upstream error' });
    }
  });

  server.post('/api/auth/nonce', async (request, reply) => {
    if (!requireFirebase(reply)) return;

    const body = request.body as { walletAddress?: string } | undefined;
    const walletAddress = body?.walletAddress?.toLowerCase();
    if (!walletAddress) {
      reply.code(400).send({ error: 'walletAddress required' });
      return;
    }

    const nonce = randomBytes(16).toString('hex');
    nonceStore.set(walletAddress, nonce);

    reply.send({ nonce, messageToSign: `CraftWorld Companion login nonce: ${nonce}` });
  });

  server.post('/api/auth/exchange', async (request, reply) => {
    if (!requireFirebase(reply)) return;

    const body = request.body as { walletAddress?: string; signature?: string } | undefined;
    const walletAddress = body?.walletAddress?.toLowerCase();
    const signature = body?.signature;

    if (!walletAddress || !signature) {
      reply.code(400).send({ error: 'walletAddress and signature required' });
      return;
    }

    const nonce = nonceStore.get(walletAddress);
    if (!nonce) {
      reply.code(400).send({ error: 'nonce missing for wallet' });
      return;
    }

    const message = `CraftWorld Companion login nonce: ${nonce}`;
    const recovered = verifyMessage(message, signature).toLowerCase();
    if (recovered !== walletAddress) {
      reply.code(401).send({ error: 'signature mismatch' });
      return;
    }

    const customToken = await createCustomToken(walletAddress, { walletAddress });
    reply.send({ customToken });
  });

  server.get('/me', async (request, reply) => {
    if (!requireFirebase(reply)) return;

    const auth = await getAuthContext(request);
    if (!auth) {
      reply.code(401).send({ error: 'Unauthorized' });
      return;
    }

    const prisma = getPrismaClient();
    if (!prisma) {
      reply.code(503).send({ error: 'Database unavailable' });
      return;
    }

    const user = await prisma.user.upsert({
      where: { firebaseUid: auth.firebaseUid },
      update: { walletAddress: auth.walletAddress },
      create: { firebaseUid: auth.firebaseUid, walletAddress: auth.walletAddress }
    });

    reply.send({ user });
  });

  server.get('/profile', async (request, reply) => {
    if (!requireFirebase(reply)) return;

    const auth = await getAuthContext(request);
    if (!auth) {
      reply.code(401).send({ error: 'Unauthorized' });
      return;
    }

    const prisma = getPrismaClient();
    if (!prisma) {
      reply.code(503).send({ error: 'Database unavailable' });
      return;
    }

    const user = await prisma.user.findUnique({ where: { firebaseUid: auth.firebaseUid } });
    if (!user) {
      reply.send({ profile: null });
      return;
    }

    const profile = await prisma.profile.findUnique({ where: { userId: user.id } });
    reply.send({ profile: profile?.profile ?? null });
  });

  server.post('/profile', async (request, reply) => {
    if (!requireFirebase(reply)) return;

    const auth = await getAuthContext(request);
    if (!auth) {
      reply.code(401).send({ error: 'Unauthorized' });
      return;
    }

    const prisma = getPrismaClient();
    if (!prisma) {
      reply.code(503).send({ error: 'Database unavailable' });
      return;
    }

    const body = request.body as { profile?: unknown } | undefined;

    const user = await prisma.user.upsert({
      where: { firebaseUid: auth.firebaseUid },
      update: { walletAddress: auth.walletAddress },
      create: { firebaseUid: auth.firebaseUid, walletAddress: auth.walletAddress }
    });

    const profile = await prisma.profile.upsert({
      where: { userId: user.id },
      update: { profile: body?.profile ?? {} },
      create: { userId: user.id, profile: body?.profile ?? {} }
    });

    reply.send({ profile: profile.profile });
  });

  server.get('/favorites', async (request, reply) => {
    if (!requireFirebase(reply)) return;

    const auth = await getAuthContext(request);
    if (!auth) {
      reply.code(401).send({ error: 'Unauthorized' });
      return;
    }

    const prisma = getPrismaClient();
    if (!prisma) {
      reply.code(503).send({ error: 'Database unavailable' });
      return;
    }

    const user = await prisma.user.findUnique({ where: { firebaseUid: auth.firebaseUid } });
    if (!user) {
      reply.send({ favorites: [] });
      return;
    }

    const favorites = await prisma.favorite.findMany({ where: { userId: user.id } });
    reply.send({ favorites: favorites.map((fav: { symbol: string }) => fav.symbol) });
  });

  server.post('/favorites', async (request, reply) => {
    if (!requireFirebase(reply)) return;

    const auth = await getAuthContext(request);
    if (!auth) {
      reply.code(401).send({ error: 'Unauthorized' });
      return;
    }

    const prisma = getPrismaClient();
    if (!prisma) {
      reply.code(503).send({ error: 'Database unavailable' });
      return;
    }

    const body = request.body as { symbol?: string } | undefined;
    const symbol = body?.symbol?.toUpperCase();
    if (!symbol) {
      reply.code(400).send({ error: 'symbol required' });
      return;
    }

    const user = await prisma.user.upsert({
      where: { firebaseUid: auth.firebaseUid },
      update: { walletAddress: auth.walletAddress },
      create: { firebaseUid: auth.firebaseUid, walletAddress: auth.walletAddress }
    });

    await prisma.favorite.upsert({
      where: { userId_symbol: { userId: user.id, symbol } },
      update: {},
      create: { userId: user.id, symbol }
    });

    reply.send({ ok: true });
  });

  const port = Number(process.env.PORT || 3001);
  const host = '0.0.0.0';
  await server.listen({ port, host });
};

start().catch((err) => {
  server.log.error(err);
  process.exit(1);
});
