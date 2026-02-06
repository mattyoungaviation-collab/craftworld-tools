import Fastify from 'fastify';
import cors from '@fastify/cors';
import { registerApiRoutes } from './routes/api';

const app = Fastify({
  logger: {
    level: process.env.LOG_LEVEL || 'info',
  },
});

const allowedOrigins = (process.env.CORS_ORIGIN || process.env.WEB_ORIGIN || '*')
  .split(',')
  .map((origin) => origin.trim())
  .filter(Boolean);

await app.register(cors, {
  origin: (origin, cb) => {
    if (!origin) return cb(null, true);
    if (allowedOrigins.includes('*')) return cb(null, true);
    if (allowedOrigins.includes(origin)) return cb(null, true);
    return cb(new Error('Origin not allowed'), false);
  },
});

app.get('/health', async () => ({ ok: true }));

await registerApiRoutes(app);

const port = Number(process.env.PORT || 4000);
const host = process.env.HOST || '0.0.0.0';

app
  .listen({ port, host })
  .then(() => {
    app.log.info(`API listening on ${host}:${port}`);
  })
  .catch((err) => {
    app.log.error(err, 'Failed to start server');
    process.exit(1);
  });
