# Craftworld Tools Contracts

## Entry Points

- **Backend**: `apps/api/src/index.ts` (Fastify server + API routes).【F:apps/api/src/index.ts†L1-L35】
- **Frontend**: `apps/web/src/App.tsx` (React tabs for Boosts/Calculate/Masterpiece/Profitability/Chains).【F:apps/web/src/App.tsx†L1-L56】

## API Route Inventory (existing behavior)

| Method | Path | Request | Response | Implementation |
| --- | --- | --- | --- | --- |
| POST | `/api/cw/get_nonce` | `{ walletAddress }` | `{ ok, walletAddress, nonce }` or `{ ok:false, error, rawErrors }` | `apps/api/src/routes/api.ts`.【F:apps/api/src/routes/api.ts†L39-L128】 |
| POST | `/api/cw/login_for_custom_token` | `{ walletAddress, signature }` | `{ ok, walletAddress, customToken }` or `{ ok:false, error, rawErrors }` | `apps/api/src/routes/api.ts`.【F:apps/api/src/routes/api.ts†L130-L208】 |
| POST | `/api/cw/signin_with_custom_token` | `{ customToken }` | `{ ok, idToken, refreshToken, expiresIn }` or `{ ok:false, error, rawErrors }` | `apps/api/src/routes/api.ts`.【F:apps/api/src/routes/api.ts†L210-L259】 |
| GET | `/api/account_status` | `Authorization: Bearer <jwt_...>` or `?cw_idToken=` | `{ ok, auth, power, msUntilRefill, refillSeconds, refillHMS, primaryWallet, powerLastRefill, updatedAt }` | `apps/api/src/routes/api.ts` + account status cache service.【F:apps/api/src/routes/api.ts†L261-L287】【F:apps/api/src/services/accountStatus.ts†L1-L65】 |
| GET | `/api/account_workshop` | `Authorization: Bearer <jwt_...>` | `{ ok, workshop: [{symbol, level}], updatedAt }` | `apps/api/src/routes/api.ts`.【F:apps/api/src/routes/api.ts†L289-L341】 |
| GET | `/api/account_proficiencies` | `Authorization: Bearer <jwt_...>` | `{ ok, proficiencies: [{symbol, collectedAmount, claimedLevel}], updatedAt }` | `apps/api/src/routes/api.ts`.【F:apps/api/src/routes/api.ts†L343-L395】 |
| GET | `/api/account_uid` | `Authorization: Bearer <jwt_...>` or `?cw_idToken=` | `{ ok, uid }` or `{ ok:false, error, rawErrors }` | `apps/api/src/routes/api.ts`.【F:apps/api/src/routes/api.ts†L397-L424】 |
| POST | `/api/boosts/mastery` | `{ masteryLevels: { [symbol]: number } }` | `{ ok, updated, updatedAt }` | `apps/api/src/routes/api.ts`.【F:apps/api/src/routes/api.ts†L426-L442】 |
| POST | `/api/boosts/sync` | `{ masteryLevels?, workshopLevels? }` | `{ ok, masteryUpdated, workshopUpdated, updatedAt }` | `apps/api/src/routes/api.ts`.【F:apps/api/src/routes/api.ts†L444-L469】 |
| GET | `/health` | n/a | `{ ok: true }` | `apps/api/src/index.ts`.【F:apps/api/src/index.ts†L21-L24】 |

## Frontend API Calls

| Call Site | Method | Path | Purpose |
| --- | --- | --- | --- |
| `connectWallet()` | POST | `/api/cw/get_nonce` | Get nonce for wallet signature during Ronin connect.【F:apps/web/src/services/wallet.ts†L92-L142】 |
| `connectWallet()` | POST | `/api/cw/login_for_custom_token` | Exchange signature for Firebase custom token.【F:apps/web/src/services/wallet.ts†L92-L142】 |
| `connectWallet()` | POST | `/api/cw/signin_with_custom_token` | Sign in to Firebase and get tokens.【F:apps/web/src/services/wallet.ts†L92-L142】 |
| `WalletStatus` | GET | `/api/account_status` | Fetch power/refill status for connected session.【F:apps/web/src/components/WalletStatus.tsx†L22-L70】 |
| Boosts sync | GET | `/api/account_workshop` + `/api/account_proficiencies` | Sync mastery/workshop levels from account data.【F:apps/web/src/features/BoostsPage.tsx†L49-L108】 |
| Boosts sync | POST | `/api/boosts/sync` | Persist synced boosts after wallet sync.【F:apps/web/src/features/BoostsPage.tsx†L88-L109】 |

## Local Storage Schema

| Key | Shape | Purpose |
| --- | --- | --- |
| `cw_idToken` | `string` | Firebase ID token (legacy key).【F:apps/web/src/services/storage.ts†L4-L16】 |
| `cw_token` | `string` | Craft World session token (same as Firebase ID token).【F:apps/web/src/services/storage.ts†L4-L16】 |
| `cw_refreshToken` | `string` | Firebase refresh token.【F:apps/web/src/services/storage.ts†L4-L16】 |
| `cw_expiresAt` | `number` (ms epoch) | Expiration for current token session.【F:apps/web/src/services/storage.ts†L4-L16】 |
| `cw_wallet` | `string` | Active wallet address (lowercased).【F:apps/web/src/services/storage.ts†L4-L16】 |
| `cw_sessions` | `{ [wallet]: { token, expiresAt, refreshToken, lastLoginAt, idToken } }` | Wallet-indexed session store (multi-wallet support).【F:apps/web/src/services/storage.ts†L18-L45】 |
| `cw_active_wallet` | `string` | Explicit active wallet (lowercased).【F:apps/web/src/services/storage.ts†L4-L16】 |
| `cw_account_status` | `{ ok, auth, power, msUntilRefill, refillSeconds, refillHMS, ... }` | Cached account status response for UI refresh/polling.【F:apps/web/src/services/storage.ts†L4-L16】 |
| `cw_connection_type` | `'injected' | 'walletconnect'` | Wallet connection strategy hint.【F:apps/web/src/services/storage.ts†L4-L16】 |
| `cw_boosts:<wallet>` | `{ workshopLevels, masteryLevels, syncedAt }` | Per-wallet cached boosts in Boosts tab sync flow.【F:apps/web/src/features/BoostsPage.tsx†L34-L117】 |

## Calculation References (formula sources)

- **Factory profitability**: `computeFactoryResultCsv()` and `computeBestSetupsCsv()` in shared factories module.【F:packages/shared/src/factories.ts†L206-L360】
- **Crafting chain planner**: `planCraft()`, `rankOpportunities()`, and `buildChainReport()` in shared crafting module.【F:packages/shared/src/crafting.ts†L119-L373】
- **Mastery/workshop modifiers**: `MASTERY_BONUSES` + `WORKSHOP_MODIFIERS` in shared factories module.【F:packages/shared/src/factories.ts†L23-L120】
- **Pricing**: exchange price list and exact quote logic in shared pricing module.【F:packages/shared/src/pricing.ts†L1-L234】

## Feature Map (implementation files)

| Feature | Primary Source Files |
| --- | --- |
| Boosts tab | `apps/web/src/features/BoostsPage.tsx` + shared boost tables.【F:apps/web/src/features/BoostsPage.tsx†L1-L169】【F:packages/shared/src/factories.ts†L23-L120】 |
| Calculate tab | `apps/web/src/features/CalculatePage.tsx` + shared factory calc logic.【F:apps/web/src/features/CalculatePage.tsx†L1-L120】【F:packages/shared/src/factories.ts†L206-L360】 |
| Masterpiece tab | `apps/web/src/features/MasterpiecePage.tsx` (GraphQL queries + UI).【F:apps/web/src/features/MasterpiecePage.tsx†L1-L155】 |
| Profitability tab | `apps/web/src/features/ProfitabilityPage.tsx` + shared calc logic.【F:apps/web/src/features/ProfitabilityPage.tsx†L1-L79】【F:packages/shared/src/factories.ts†L294-L360】 |
| Crafting chains | `apps/web/src/features/ChainsPage.tsx` + shared chain logic.【F:apps/web/src/features/ChainsPage.tsx†L1-L116】【F:packages/shared/src/crafting.ts†L267-L373】 |
| Wallet connect/auth/session | `apps/web/src/services/wallet.ts` + storage service + API routes.【F:apps/web/src/services/wallet.ts†L1-L155】【F:apps/web/src/services/storage.ts†L1-L80】【F:apps/api/src/routes/api.ts†L39-L469】 |
