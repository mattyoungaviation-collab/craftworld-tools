# API route extraction

The API routes should be pulled out of `app.py` one small group at a time.

## Extracted modules

### Account status API

Created:

```python
craftworld_tools/routes/api_account.py
```

Provides:

```python
register_account_api_routes(app, get_cached_account_status)
```

This contains the transition-ready implementation for:

```text
/api/account_status
```

## Wire-in patch for `app.py`

Add this import near other local imports:

```python
from craftworld_tools.routes.api_account import register_account_api_routes
```

Remove the inline route for:

```python
@app.route("/api/account_status")
def api_account_status():
```

Then register the extracted route after `get_cached_account_status()` exists:

```python
register_account_api_routes(app, get_cached_account_status)
```

## Test checklist

```bash
python -m py_compile app.py craftworld_tools/routes/api_account.py
```

Smoke test:

- `/api/account_status` without browser token
- `/api/account_status` with Authorization Bearer token
- `/api/account_status?cw_idToken=...`

Expected behavior:

- Per-user token request uses live Craft World account status.
- Missing token falls back to existing server/env JWT behavior.
