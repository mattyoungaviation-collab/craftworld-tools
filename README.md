# CraftWorld Companion

A production-ready monorepo for CraftWorld tooling, featuring a Fastify API, Next.js web UI, and shared TypeScript utilities.

## Monorepo Layout

```
craftworld-companion/
  apps/
    api/                # Fastify API (GraphQL + caching + Prisma)
    web/                # Next.js App Router UI
  packages/
    shared/             # Crafting chain + profitability logic
    data/               # CSV ingestion + generator scripts
    legacy/             # Legacy Python tools + original CSVs (attribution)
  render.yaml           # Render Blueprint
```

## Local Development

> Node 20+ and pnpm are required.

1. Install dependencies

```bash
pnpm install
```

2. Generate data assets

```bash
pnpm data:generate
```

3. Run Prisma migrations (optional for local dev)

```bash
pnpm --filter @craftworld/api exec prisma migrate dev
```

4. Start API + Web

```bash
pnpm dev
```

API runs at `http://localhost:3001`, Web at `http://localhost:3000`.

## Render Deployment (Blueprint)

1. Create a new Render Blueprint from `render.yaml`.
2. Confirm the two web services (API + Web), Postgres, and Redis are created.
3. Optional: set Firebase variables for auth:
   - `FIREBASE_PROJECT_ID`
   - `FIREBASE_CLIENT_EMAIL`
   - `FIREBASE_PRIVATE_KEY` (use `\n` for newlines; server normalizes)
4. Deploy and verify:
   - `GET /health` on API
   - `GET /ready` on API (should show degraded=false when DB/Redis ready)

## Render Checklist (First Deploy)

- [ ] API disk mounted at `/var/data`
- [ ] `DATABASE_URL` and `REDIS_URL` wired from resources
- [ ] `NEXT_PUBLIC_API_BASE` points to API service URL
- [ ] `pnpm -r build` succeeds in build logs
- [ ] `GET /prices`, `/config`, `/defs` respond
- [ ] Web home shows status badge

## Environment Variables

### API (required)
- `PORT` (Render sets)
- `DATABASE_URL` (Render Postgres)

### API (optional)
- `REDIS_URL`
- `DATA_DIR` (default `/var/data`)
- `CRAFTWORLD_GQL_URL` (default `https://craft-world.gg/graphql`)
- `CRAFTWORLD_APP_VERSION` (default `1.6.4`)
- `USE_REMOTE_CONFIG` (default `0`)

### Firebase Admin (optional)
- `FIREBASE_PROJECT_ID`
- `FIREBASE_CLIENT_EMAIL`
- `FIREBASE_PRIVATE_KEY`

### Web (required)
- `NEXT_PUBLIC_API_BASE`

### Web (Craft World Auth)
- `NEXT_PUBLIC_CW_GRAPHQL_URL` (default `https://craft-world.gg/graphql`)
- `NEXT_PUBLIC_CW_APP_VERSION` (default `1.6.4`)
- `NEXT_PUBLIC_FIREBASE_API_KEY` (Craft World Firebase web API key)
- `NEXT_PUBLIC_WALLETCONNECT_PROJECT_ID` (WalletConnect v2 project id for mobile)

### Firebase Web (optional)
- `NEXT_PUBLIC_FIREBASE_API_KEY`
- `NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN`
- `NEXT_PUBLIC_FIREBASE_PROJECT_ID`

## Degraded Mode + Caching

- API stores warm snapshots on disk:
  - `/var/data/cache/prices.json`
  - `/var/data/cache/config.json`
  - `/var/data/cache/defs.json`
  - `/var/data/cache/craft_index.json`
- When Redis or upstream is unavailable, API falls back to snapshots and refreshes in background.

## Troubleshooting

- **Port issues**: Ensure `PORT` is set by Render or `PORT=3001` for local API.
- **`prisma migrate deploy` failures**: Confirm `DATABASE_URL` is valid and DB is running.
- **Redis missing**: API continues in degraded mode with in-memory/disk cache.
- **Disk missing**: API falls back to memory only.
- **Firebase not configured**: Auth endpoints return `501` with a clear message.

## Scripts

- `pnpm data:generate` — generate normalized JSON assets
- `pnpm -r build` — build all packages/apps
- `pnpm dev` — run API + Web

## Notes

Legacy Python tooling and CSVs are preserved in `packages/legacy` for attribution and parity checks.

## Auth + Tabs overview

The web app now includes a mobile-first, tabbed Craft World wallet console that:

- Connects injected wallets (Ronin/MetaMask) or WalletConnect on mobile.
- Signs a deterministic login message to obtain a Firebase custom token, then exchanges it for an idToken.
- Uses a centralized Craft World API client and a `/api/cw/graphql` proxy that attaches required headers.
- Persists the authenticated session in localStorage and hydrates it on refresh.
- Provides tabs for status, API call catalog, prices, resources, wallets, deputy lookup, workshop, mastery, leaderboards, and notes.

Set the environment variables above before running the web app to enable the full auth flow.
