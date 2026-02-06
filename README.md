# Craftworld Tools (Monorepo)

A mobile-first monorepo for Craft World planning tools. This version replaces the legacy Flask app with a Fastify API and a React + Vite frontend while preserving existing behaviors and calculations.

## Stack

- **Backend**: Node.js + TypeScript + Fastify (`/apps/api`)
- **Frontend**: React + Vite + TypeScript (`/apps/web`)
- **Shared**: `/packages/shared` for calculations and types
- **Data**: `/packages/data` for CSV resources

## Setup

```bash
npm install
```

## Environment Variables

### API (`/apps/api/.env`)

```
PORT=4000
HOST=0.0.0.0
LOG_LEVEL=info
CORS_ORIGIN=http://localhost:5173
CW_APP_VERSION=1.6.2
CW_FIREBASE_API_KEY=your_firebase_api_key
```

### Web (`/apps/web/.env`)

```
VITE_API_BASE_URL=http://localhost:4000
VITE_WALLETCONNECT_PROJECT_ID=
VITE_RONIN_RPC_URL=https://api.roninchain.com/rpc
VITE_RONIN_CHAIN_ID=2020
```

## Development

```bash
npm run dev
```

Runs both the API and web app in parallel.

## Build

```bash
npm run build
```

## Lint / Typecheck

```bash
npm run lint
npm run typecheck
```

## Testing

```bash
npm -w packages/shared run test
```

## Render Deployment

### API Service

- Root directory: `apps/api`
- Build command: `npm install && npm run build`
- Start command: `node dist/index.js`
- Env vars: see `/apps/api/.env.example`

### Web Service

- Root directory: `apps/web`
- Build command: `npm install && npm run build`
- Publish directory: `dist`
- Env vars: see `/apps/web/.env.example`

## Docs

- Contracts: `/docs/contracts.md`
- Architecture plan: `/docs/architecture-plan.md`
- QA checklist: `/docs/qa-checklist.md`
- QA notes: `/docs/qa-notes.md`
- Known issues: `/docs/known-issues.md`

