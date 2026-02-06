# Architecture Plan (Phase 1)

## Goals
- Remove Flask and ship a Node.js + TypeScript backend.
- Migrate UI to a mobile-first React + Vite + TypeScript frontend.
- Preserve all current features, formulas, and API contracts.
- Centralize shared logic (calculations, types, constants) in `/packages/shared`.

## Target Monorepo Layout
```
/apps
  /api       # Fastify API (TypeScript)
  /web       # React + Vite frontend (TypeScript)
/packages
  /shared    # Types, schemas, calculation logic, and helpers
  /data      # CSV / JSON game data (factories, recipes, etc.)
/docs        # Contracts, QA notes, architecture, known issues
```

## Feature Mapping

| Feature | Current Source | New Location | Notes |
| --- | --- | --- | --- |
| Boosts (mastery/workshop) | `app.py`, `factories.py` | `apps/web/src/features/boosts`, `packages/shared` | Keep storage keys & sync endpoints. |
| Calculate | `app.py`, `factories.py` | `apps/web/src/features/calculate`, `packages/shared` | Reuse CSV parsing and factory math. |
| Masterpieces | `app.py`, `craftworld_api.py` | `apps/web/src/features/masterpiece`, `apps/api/src/services` | Preserve reward prediction and leaderboard logic. |
| Profitability | `app.py`, `pricing.py`, `factories.py` | `apps/web/src/features/profitability`, `packages/shared` | Preserve formula outputs; reuse buy/sell quotes. |
| Crafting chains | `crafting_planner.py` | `apps/web/src/features/chains`, `packages/shared` | Keep chain graphs + ROI calculation. |
| Wallet connect/session | JS in `app.py` template | `apps/web/src/services/wallet`, `apps/web/src/services/storage` | Preserve localStorage keys and flows. |

## API Strategy
- Re-implement all Flask routes under `/api/**` in Fastify with the same request/response shapes.
- Craft World GraphQL requests live in `apps/api/src/services/craftworldClient.ts`.
- Power/refill caching stays in API (in-memory TTL).
- Add `/health` endpoint for uptime checks.

## Frontend Strategy
- Mobile-first layout with a bottom tab bar on small screens.
- Use a single typed API client (`apps/web/src/services/apiClient.ts`).
- Use a single storage service (`apps/web/src/services/storage.ts`) with migration logic.
- Each feature lives under `apps/web/src/features/*` with dedicated UI + hooks.

## Shared Package Strategy
- Move all formulas and constants from Python into `/packages/shared`.
- Provide deterministic pure functions for calculations and unit tests.
- Export type-safe DTOs aligned with `/docs/contracts.md`.

## Data Strategy
- Store CSVs in `/packages/data`.
- Parse CSVs in shared code via a browser-friendly parser.
- Avoid duplicating data structures across features.

## QA Strategy
- For each migration step, record parity checks in `/docs/qa-notes.md`.
- Keep a manual checklist in `/docs/qa-checklist.md`.
- Log known behavioral issues (if any) in `/docs/known-issues.md` without changing formulas.
