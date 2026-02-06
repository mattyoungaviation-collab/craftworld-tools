# Architecture Plan (Monorepo, Fastify + React)

## Goals

- Replace Flask with **Node.js + TypeScript** (Fastify) while preserving API behavior.
- Move to a **React + Vite + TypeScript** web app with mobile-first UX.
- Centralize business logic in `/packages/shared` and data in `/packages/data`.
- Maintain localStorage semantics and session behavior (wallet-indexed sessions, boosts cache, etc.).
- Preserve calculations/formulas exactly as implemented in Python.

## Target Repository Structure

```
/apps
  /api
    /src
      /routes
      /services
      /storage
      /utils
  /web
    /src
      /app
      /features
      /services
      /styles
      /components
/packages
  /shared
    /src
      /calculations
      /pricing
      /crafting
      /types
  /data
    /factories
/docs
```

## Mapping From Existing Features

| Feature | Old Location | New Location |
| --- | --- | --- |
| Boosts tab | `app.py` (Boosts route, localStorage sync) | `apps/web/src/features/boosts` + shared calculations in `packages/shared/src/calculations` |
| Calculate tab | `app.py` + `factories.py` | `apps/web/src/features/calculate` + shared factory parser/compute in `packages/shared` |
| Masterpiece tab | `app.py` + `craftworld_api.py` | `apps/web/src/features/masterpiece` + shared GraphQL client in `apps/api/src/services` |
| Profitability tab | `app.py` + `pricing.py` | `apps/web/src/features/profitability` + shared pricing logic in `packages/shared` |
| Crafting chains | `crafting_planner.py` | `apps/web/src/features/chains` + shared craft planner in `packages/shared` |
| Wallet connect/session | Base template JS in `app.py` | `apps/web/src/services/wallet` + `apps/web/src/services/storage` |
| API endpoints | Flask routes in `app.py` | Fastify routes in `apps/api/src/routes` (same paths + payloads) |

## API Strategy

- Re-implement **all existing `/api/*` endpoints** 1:1 in Fastify with the same methods, request/response shapes, and error semantics.
- Keep Craft World GraphQL requests behind `apps/api/src/services/craftworldClient.ts`.
- Add `GET /health`.
- CORS configured to allow the web app origin.

## Frontend Strategy

- Single React app with tabs for Boosts / Calculate / Masterpiece / Profitability / Chains.
- Mobile-first layout: bottom nav on small screens, sidebar/top nav on desktop.
- Use a single API client (`apps/web/src/services/apiClient.ts`) and storage service (`apps/web/src/services/storage.ts`) with schema migration.
- Preserve localStorage key names; introduce versioning with `STORAGE_SCHEMA_VERSION` and a migration path for legacy keys.

## Shared Packages

- `/packages/shared` contains exact ports of:
  - `factories.py` (factory CSV parsing, calculate/profitability math).
  - `crafting_planner.py` (chain planner, ranker, etc.).
  - `pricing.py` (exchange price list + exact input quotes).
- `/packages/data` contains the raw CSVs used by calculations.

## QA/Parity Plan

- Document endpoint parity with manual requests in `/docs/qa-notes.md`.
- For each feature, verify:
  - Tab renders
  - No console errors
  - Data loads
  - Outputs match old behavior on 3 sample inputs
  - localStorage migration preserves user data
- Add unit tests for profitability math, crafting chain generation, and boosts application in `packages/shared`.

