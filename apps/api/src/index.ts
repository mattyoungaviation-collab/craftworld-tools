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

// What our API returns (flat list) — stable contract for the web
type PricesPayload = {
  exchangePriceList: PricesItem[];
};

// GraphQL introspection types
type GqlTypeRef = {
  kind: string;
  name: string | null;
  ofType?: GqlTypeRef | null;
};

type GqlField = {
  name: string;
  type: GqlTypeRef;
};

type IntrospectionType = {
  __type: {
    name: string;
    fields: GqlField[];
  } | null;
};

const PRICE_TTL_MS = 60_000;
const inMemoryCache: { prices?: { data: PricesPayload; fetchedAt: number } } = {};
const nonceStore = new Map<string, string>();

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

const unwrapNamedType = (t: GqlTypeRef | null | undefined): string | null => {
  let cur: GqlTypeRef | null | undefined = t;
  while (cur) {
    if (cur.name) return cur.name;
    cur = cur.ofType ?? null;
  }
  return null;
};

const introspectType = async (name: string) => {
  return cwGraphqlRequest<IntrospectionType>(
    'TypeInfo',
    `query TypeInfo($name: String!) {
      __type(name: $name) {
        name
        fields {
          name
          type {
            kind
            name
            ofType {
              kind
              name
              ofType {
                kind
                name
              }
            }
          }
        }
      }
    }`,
    { name }
  );
};

const pickFirst = (fields: string[], preferred: string[]) => {
  for (const p of preferred) {
    if (fields.includes(p)) return p;
  }
  return null;
};

/**
 * Robust price fetch that adapts to schema changes:
 * - exchangePriceList is an object
 * - it has a field "prices"
 * - items inside "prices" may not be {symbol, price} anymore
 *   so we introspect the item type and pick likely field names.
 */
const fetchPricesFromCraftWorld = async (): Promise<PricesPayload> => {
  // 1) Introspect ExchangePriceList to find the "prices" field item type
  const exchangeType = await introspectType('ExchangePriceList');
  if (!exchangeType.__type) throw new Error('Introspection failed for ExchangePriceList');

  const exchangeFields = exchangeType.__type.fields.map((f) => f.name);
  if (!exchangeFields.includes('prices')) {
    throw new Error(`ExchangePriceList missing "prices" field. Has: ${exchangeFields.join(', ')}`);
  }

  const pricesField = exchangeType.__type.fields.find((f) => f.name === 'prices');
  const pricesItemTypeName = unwrapNamedType(pricesField?.type);
  if (!pricesItemTypeName) {
    throw new Error('Could not resolve prices item type');
  }

  // 2) Introspect item type to discover field names
  const itemType = await introspectType(pricesItemTypeName);
  if (!itemType.__type) throw new Error(`Introspection failed for ${pricesItemTypeName}`);

  const itemFields = itemType.__type.fields.map((f) => f.name);

  // Common candidates we might see in the wild
  const symbolField =
    pickFirst(itemFields, ['symbol', 'token', 'resourceSymbol', 'itemSymbol', 'resource', 'id']) ??
    null;

  // For price, CraftWorld literally suggested "prices" at the ExchangePriceList level,
  // but inside each item it could be "price", "value", etc.
  const priceField =
    pickFirst(itemFields, ['price', 'value', 'amount', 'coinPrice', 'prices', 'priceInCoin']) ?? null;

  if (!symbolField || !priceField) {
    throw new Error(
      `Could not infer symbol/price fields from ${pricesItemTypeName}. Fields: ${itemFields.join(', ')}`
    );
  }

  // 3) Query using discovered field names
  // Note: We must build the selection set dynamically.
  const query = `query exchangePriceList {
    exchangePriceList {
      prices {
        ${symbolField}
        ${priceField}
      }
    }
  }`;

  const data = await cwGraphqlRequest<{
    exchangePriceList: { prices: Record<string, unknown>[] };
  }>('exchangePriceList', query);

  const raw = data?.exchangePriceList?.prices ?? [];

  // 4) Normalize to our stable API contract
  const normalized: PricesItem[] = raw
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

  return { exchangePriceList: normalized };
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

  // Debug endpoints so you can inspect schema quickly if it changes again
  server.get('/debug/prices-schema', async () => introspectType('ExchangePriceList'));

  server.get('/debug/prices-item-schema', async () => {
    const exchangeType = await introspectType('ExchangePriceList');
    if (!exchangeType.__type) return exchangeType;

    const pricesField = exchangeType.__type.fields.find((f) => f.name === 'prices');
    const pricesItemTypeName = unwrapNamedType(pricesField?.type);
    if (!pricesItemTypeName) return { error: 'Could not resolve prices item type' };

    return introspectType(pricesItemTypeName);
  });

  server.get('/debug/prices-raw', async () => {
    // returns what CraftWorld sends before normalization
    const exchangeType = await introspectType('ExchangePriceList');
    if (!exchangeType.__type) throw new Error('Introspection failed for ExchangePriceList');

    const pricesField = exchangeType.__type.fields.find((f) => f.name === 'prices');
    const pricesItemTypeName = unwrapNamedType(pricesField?.type);
    if (!pricesItemTypeName) throw new Error('Could not resolve prices item type');

    const itemType = await introspectType(pricesItemTypeName);
    if (!itemType.__type) throw new Error(`Introspection failed for ${pricesItemTypeName}`);

    const itemFields = itemType.__type.fields.map((f) => f.name);
    const symbolField = pickFirst(itemFields, ['symbol', 'token', 'resourceSymbol', 'itemSymbol', 'resource', 'id']);
    const priceField = pickFirst(itemFields, ['price', 'value', 'amount', 'coinPrice', 'prices', 'priceInCoin']);
    if (!symbolField || !priceField) {
      return { error: `Could not infer fields`, pricesItemTypeName, itemFields };
    }

    const query = `query exchangePriceList {
      exchangePriceList {
        prices {
          ${symbolField}
          ${priceField}
        }
      }
    }`;

    const data = await cwGraphqlRequest<{
      exchangePriceList: { prices: Record<string, unknown>[] };
    }>('exchangePriceList', query);

    return { pricesItemTypeName, symbolField, priceField, data };
  });

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
