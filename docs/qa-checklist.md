# QA Checklist

## Backend Parity
- [ ] /api/cw/get_nonce returns nonce for valid wallet.
- [ ] /api/cw/login_for_custom_token returns customToken for valid signature.
- [ ] /api/cw/signin_with_custom_token returns idToken/refreshToken/expiresIn.
- [ ] /api/account_status returns power/refill data for valid token.
- [ ] /api/account_workshop returns workshop list.
- [ ] /api/account_proficiencies returns proficiencies list.
- [ ] /api/account_uid returns account id.
- [ ] /api/boosts/mastery updates mastery levels.
- [ ] /api/boosts/sync updates mastery/workshop levels.
- [ ] /health returns OK.

## Frontend Tabs
- [ ] Boosts tab renders and loads cached boosts.
- [ ] Boosts sync pulls mastery/workshop and updates storage.
- [ ] Calculate tab renders and matches legacy outputs (3 samples).
- [ ] Masterpiece tab renders, loads list, and calculates rewards.
- [ ] Profitability tab renders and matches legacy outputs (3 samples).
- [ ] Chains tab renders and matches legacy outputs (3 samples).

## Sessions & Storage
- [ ] Wallet connect flow stores cw_* keys correctly.
- [ ] Storage migration preserves existing data.
- [ ] Switching wallets updates active session and boosts cache.

