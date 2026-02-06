# Contracts (Phase 1 Audit)

## API Route Table

| Method | Path | Request | Response | Notes |
| --- | --- | --- | --- | --- |
| POST | `/api/cw/get_nonce` | JSON `{ walletAddress: string }` | `{ ok: boolean, walletAddress?: string, nonce?: string, error?: string, rawErrors?: any[] }` | Craft World GraphQL `getNonce` for wallet login. Returns 400 on missing wallet or GraphQL errors. `app.py` handler `api_cw_get_nonce`. |
| POST | `/api/cw/login_for_custom_token` | JSON `{ walletAddress: string, signature: string }` | `{ ok: boolean, walletAddress?: string, customToken?: string, error?: string, rawErrors?: any[] }` | Craft World GraphQL `loginForCustomToken` exchange. Returns 400 on missing fields or errors. `app.py` handler `api_cw_login_for_custom_token`. |
| POST | `/api/cw/signin_with_custom_token` | JSON `{ customToken: string }` | `{ ok: boolean, idToken?: string, refreshToken?: string, expiresIn?: number, error?: string, rawErrors?: any[] }` | Firebase Identity Toolkit `signInWithCustomToken`. `app.py` handler `api_cw_signin_with_custom_token`. |
| GET | `/api/account_status` | Headers `Authorization: Bearer <jwt_...>` or query `cw_idToken` | `{ ok: boolean, auth: string, power?: number, msUntilRefill?: number, refillSeconds?: number, refillHMS?: string, primaryWallet?: string, powerLastRefill?: string, updatedAt?: string, error?: string, rawErrors?: any[] }` | Uses Craft World GraphQL `account` power status. `app.py` handler `api_account_status`. |
| GET | `/api/account_workshop` | Headers `Authorization: Bearer <jwt_...>` | `{ ok: boolean, auth?: string, workshop?: { symbol: string, level: number }[], updatedAt?: string, error?: string }` | Fetches workshop levels via Craft World GraphQL. `app.py` handler `api_account_workshop`. |
| GET | `/api/account_proficiencies` | Headers `Authorization: Bearer <jwt_...>` | `{ ok: boolean, auth?: string, proficiencies?: { symbol: string, collectedAmount: number, claimedLevel: number }[], updatedAt?: string, error?: string }` | Fetches mastery/proficiency levels via GraphQL. `app.py` handler `api_account_proficiencies`. |
| GET | `/api/account_uid` | Headers `Authorization: Bearer <jwt_...>` or query `cw_idToken` | `{ ok: boolean, uid?: string, error?: string, rawErrors?: any[] }` | GraphQL `account { id }` lookup. `app.py` handler `api_account_uid`. |
| POST | `/api/boosts/mastery` | JSON `{ masteryLevels: Record<string, number> }` | `{ ok: boolean, updated: number, updatedAt: string, error?: string }` | Updates mastery levels in persistent store/session. `app.py` handler `api_boosts_mastery`. |
| POST | `/api/boosts/sync` | JSON `{ masteryLevels?: Record<string, number>, workshopLevels?: Record<string, number> }` | `{ ok: boolean, masteryUpdated: number, workshopUpdated: number, updatedAt: string, error?: string }` | Updates mastery/workshop levels in persistent store/session. `app.py` handler `api_boosts_sync`. |

## LocalStorage Schema

| Key | Shape | Purpose | Source |
| --- | --- | --- | --- |
| `cw_idToken` | `string` | Firebase ID token for Craft World. | Wallet connect flow in `app.py` base template JS. |
| `cw_token` | `string` | Alias for `cw_idToken` (legacy). | Wallet connect flow in `app.py` base template JS. |
| `cw_refreshToken` | `string` | Firebase refresh token. | Wallet connect flow in `app.py` base template JS. |
| `cw_expiresAt` | `string` (millis) | Token expiry timestamp. | Wallet connect flow in `app.py` base template JS. |
| `cw_wallet` | `string` | Current wallet address. | Wallet connect flow in `app.py` base template JS. |
| `cw_sessions` | `Record<wallet, { token: string, expiresAt: number, refreshToken: string, lastLoginAt: number, idToken: string }>` | Per-wallet session index. | Wallet connect flow in `app.py` base template JS. |
| `cw_active_wallet` | `string` | Active wallet to select session. | Wallet connect flow in `app.py` base template JS. |
| `cw_account_status` | `object` | Cached power/refill status JSON. | Wallet connect flow in `app.py` base template JS. |
| `cw_connection_type` | `string` | Connection provider (`walletconnect`, `injected`, etc.). | Wallet connect flow in `app.py` base template JS. |
| `cw_boosts:<wallet>` | `{ workshopLevels: Record<string, number>, masteryLevels: Record<string, number>, syncedAt: number }` | Cached boosts per wallet. | Boosts page JS in `app.py`. |

## Calculation References (Source of Truth)

| Feature | Source Files | Key Functions |
| --- | --- | --- |
| Boosts | `factories.py`, `app.py` | `MASTERY_BONUSES`, `WORKSHOP_MODIFIERS`, boost storage + sync endpoints. |
| Calculate | `factories.py` | `FACTORIES_FROM_CSV`, `compute_factory_result_csv`, `compute_best_setups_csv`. |
| Crafting Chains | `crafting_planner.py` | `build_recipe_index`, `plan_craft`, `rank_opportunities`, `build_chain_report`. |
| Profitability | `factories.py`, `pricing.py` | `profit_per_hour`, `fetch_live_prices_in_coin`, `fetch_buy_sell_for_profitability`. |
| Masterpiece | `craftworld_api.py`, `app.py` | `fetch_masterpieces`, `fetch_masterpiece_details`, `predict_reward`, `get_mp_per_unit_rewards`. |
