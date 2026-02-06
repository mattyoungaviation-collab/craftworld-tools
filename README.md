# CraftWorld Tools.Live

A modernized Craft World toolkit with a Fastify API, React + Vite frontend, and shared calculation logic.

## What it is
- Mobile-first toolbox for Boosts, Calculate, Masterpieces, Profitability, and Crafting Chains.
- Node.js + TypeScript backend (Fastify).
- React + Vite frontend.
- Shared calculations + data live in `/packages/shared` and `/packages/data`.

## Setup

### Requirements
- Node.js 20+
- npm 9+

### Install
```bash
npm install
```

### Environment Variables
Copy examples and fill values.

#### API
```
cp apps/api/.env.example apps/api/.env
```

#### Web
```
cp apps/web/.env.example apps/web/.env
```

## Running Dev Servers
```bash
npm run dev
```

- API: http://localhost:4000
- Web: http://localhost:5173

## Build
```bash
npm run build
```

## Lint / Typecheck
```bash
npm run lint
npm run typecheck
```

## Deployment (Render)

### API Service (apps/api)
- **Root Directory:** `apps/api`
- **Build Command:** `npm install && npm run build`
- **Start Command:** `node dist/index.js`
- **Environment:**
  - `PORT=4000`
  - `CRAFTWORLD_JWT` (if needed for backend-only calls)
  - `WALLETCONNECT_PROJECT_ID`
  - `RONIN_RPC_URL`
  - `RONIN_CHAIN_ID`

### Web Service (apps/web)
- **Root Directory:** `apps/web`
- **Build Command:** `npm install && npm run build`
- **Publish Directory:** `dist`
- **Environment:**
  - `VITE_API_BASE_URL=https://<your-api-service>.onrender.com`
  - `VITE_WALLETCONNECT_PROJECT_ID`
  - `VITE_RONIN_RPC_URL`
  - `VITE_RONIN_CHAIN_ID`

## Repo Layout
```
/apps
  /api       Fastify API
  /web       React + Vite frontend
/packages
  /shared    Shared calculations + types
  /data      CSV / JSON data
/docs        Contracts + architecture + QA notes
```
