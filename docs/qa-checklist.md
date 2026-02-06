# QA Checklist

## Backend Parity
- [ ] `/api/cw/get_nonce` returns nonce for valid wallet.
- [ ] `/api/cw/login_for_custom_token` returns customToken for valid signature.
- [ ] `/api/cw/signin_with_custom_token` returns idToken/refreshToken.
- [ ] `/api/account_status` matches Flask payload shape.
- [ ] `/api/account_workshop` matches Flask payload shape.
- [ ] `/api/account_proficiencies` matches Flask payload shape.
- [ ] `/api/account_uid` matches Flask payload shape.
- [ ] `/api/boosts/mastery` updates mastery map.
- [ ] `/api/boosts/sync` updates mastery/workshop maps.
- [ ] `/health` returns OK.

## Frontend Feature Checks
### Boosts
- [ ] Tab renders and table loads.
- [ ] Auto-fill from Craft World works (requires wallet).
- [ ] Manual edits persist and rehydrate.

### Calculate
- [ ] Tab renders.
- [ ] CSV data loads.
- [ ] Output matches legacy for sample inputs.

### Masterpiece
- [ ] Tab renders list + detail views.
- [ ] Predict rewards consistent with legacy.
- [ ] Leaderboard highlight works.

### Profitability
- [ ] Tab renders.
- [ ] Live prices load.
- [ ] Output matches legacy for sample inputs.

### Crafting Chains
- [ ] Tab renders.
- [ ] Chain ROI output matches legacy for sample inputs.

## Storage & Sessions
- [ ] localStorage migration preserves legacy keys.
- [ ] Wallet session switching works.
- [ ] Auto-refresh of account status works.

## Mobile Layout
- [ ] Bottom nav renders on mobile.
- [ ] Tables degrade to cards/scroll.
- [ ] No overflow on small screens.
