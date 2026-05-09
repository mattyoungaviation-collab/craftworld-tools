# App factory migration

The future target is to shrink root `app.py` into a small entry point that uses:

```python
from craftworld_tools.app_factory import create_app
```

## Current scaffold

Created:

```text
craftworld_tools/app_factory.py
```

The factory currently defaults to `register_routes=False` so it can exist safely beside the old production `app.py`.

## Final target shape

Once inline routes are removed and extracted routes are wired, root `app.py` should become close to:

```python
from craftworld_tools.app_factory import create_app

app = create_app(register_routes=True, has_uid_flag=has_uid_flag, get_cached_account_status=get_cached_account_status, require_login=require_login)
```

In practice, `has_uid_flag`, `get_cached_account_status`, and `require_login` should also be moved into package modules before this final step.

## Migration order

1. Run route audit.
2. Remove one inline route group from `app.py`.
3. Enable that matching route group through `routes/registry.py`.
4. Smoke test.
5. Repeat until `app.py` only owns app startup.

## Useful commands

```bash
python scripts/audit_routes.py
python -m py_compile app.py craftworld_tools/app_factory.py
```
