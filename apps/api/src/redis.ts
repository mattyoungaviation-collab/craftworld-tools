import Redis from 'ioredis';

export const createRedisClient = () => {
  const redisUrl = process.env.REDIS_URL;
  if (!redisUrl) return null;
  const client = new Redis(redisUrl, { maxRetriesPerRequest: 1, enableReadyCheck: true });
  client.on('error', () => undefined);
  return client;
};
