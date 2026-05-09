# Cutover notes

These notes describe how to move from the current root `app.py` to the package app factory.

## Current production entry

Production should continue using root `app.py` until inline routes are removed.

## Experimental entry

Created:

```text
wsgi_new.py
```

This imports `create_app()` but does not register extracted routes yet.

## Why routes are disabled in `wsgi_new.py`

The extracted routes overlap with routes still registered in `app.py`. Enabling them before removing the inline route blocks can cause duplicate endpoint errors or unexpected route precedence.

## Safe cutover sequence

1. Run route audit.
2. Remove one inline route group from `app.py`.
3. Register the matching group in `routes/registry.py`.
4. Compile.
5. Smoke test.
6. Repeat.
7. After all route groups are extracted, point production at the app factory entry.

## Files involved

```text
craftworld_tools/app_factory.py
craftworld_tools/routes/registry.py
craftworld_tools/session_helpers.py
craftworld_tools/guards.py
wsgi_new.py
```
