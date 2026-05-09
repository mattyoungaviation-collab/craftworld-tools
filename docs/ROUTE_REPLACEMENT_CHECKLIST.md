# Route replacement checklist

Use this checklist each time a route group moves from inline `app.py` into `craftworld_tools/routes`.

## 1. Audit live routes

```bash
python scripts/audit_routes.py
```

Save the output before changing anything.

## 2. Pick one route group

Suggested order:

1. Auth routes
2. Account API routes
3. Price API routes
4. Identity API routes
5. Factory API routes
6. Crafting API routes
7. Masterpiece API routes
8. Masterpiece preset API routes
9. Simple page routes
10. Dashboard route last

## 3. Remove old inline route block

Remove the matching `@app.route(...)` block from `app.py`.

Do not leave duplicate endpoints.

## 4. Register extracted route group

Use `craftworld_tools.routes.registry`.

For APIs:

```python
register_extracted_api_routes(...)
```

For pages:

```python
register_extracted_page_routes(..., include_auth=True)
```

Turn on only the flags for routes whose old inline blocks are removed.

## 5. Compile

```bash
python -m py_compile app.py craftworld_tools/routes/*.py craftworld_tools/services/*.py craftworld_tools/domain/*.py
```

## 6. Smoke test

Visit or curl the moved endpoints.

## 7. Re-run route audit

```bash
python scripts/audit_routes.py
```

Compare against the before snapshot.

The route URL and methods should stay the same unless intentionally changed.
