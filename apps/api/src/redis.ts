import { createRequire } from 'node:module';

type RedisClient = {
  status: string;
  on: (event: string, listener: (...args: unknown[]) => void) => void;
  get: (key: string) => Promise<string | null>;
  set: (key: string, value: string, mode: 'EX', seconds: number) => Promise<'OK' | null>;
};

type RedisConstructor = new (
  url: string,
  options?: { maxRetriesPerRequest?: number; enableReadyCheck?: boolean }
) => RedisClient;

const require = createRequire(import.meta.url);
const Redis = require('ioredis') as RedisConstructor;

export const createRedisClient = () => {
  const redisUrl = process.env.REDIS_URL;
  if (!redisUrl) return null;
  const client = new Redis(redisUrl, { maxRetriesPerRequest: 1, enableReadyCheck: true });
  client.on('error', () => undefined);
  return client;
};
