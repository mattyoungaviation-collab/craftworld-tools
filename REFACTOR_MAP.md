# Craft World Tools Refactor Map

This app started as a single-file Flask app. The goal is to split it into clean, boring, easy-to-maintain pieces without breaking production.

## Current safe structure

```text
craftworld_tools/
  __init__.py
  config.py
  db.py
  domain/
    __init__.py
    crafting.py
    factories.py
  routes/
    __init__.py
  services/
    __init__.py
    craftworld.py
    pricing.py
  templates/
    __init__.py
```

## What belongs where

### `craftworld_tools/config.py`
App constants and environment-driven settings.

Examples:

- Database path
- Craft World GraphQL URL
- App version
- Firebase identity URL

### `craftworld_tools/db.py`
SQLite connection helpers and database table initialization.

Examples:

- `get_db_connection()`
- `init_db()`
- Future migrations

### `craftworld_tools/services/`
External API and service-facing code.

Examples:

- Craft World GraphQL calls
- Pricing calls
- GeckoTerminal calls
- Account status fetches

### `craftworld_tools/domain/`
Pure game/math logic.

Examples:

- Factory calculations
- Crafting chain calculations
- Profitability calculations
- Masterpiece scoring helpers

### `craftworld_tools/routes/`
Flask blueprints.

Future route files should be split by feature:

```text
routes/
  auth.py
  dashboard.py
  factories.py
  masterpieces.py
  pricing.py
  api.py
```

### `craftworld_tools/templates/`
Jinja templates.

Inline `render_template_string(...)` HTML should eventually move here as real `.html` files.

Suggested future layout:

```text
templates/
  base.html
  dashboard.html
  factories.html
  masterpieces.html
  pricing.html
  partials/
    nav.html
    resource_table.html
    leaderboard.html
```

## Refactor order

### Pass 1: Safe foundation
Done.

- Add app package
- Add config module
- Add database module
- Add service wrappers
- Add domain wrappers
- Add route/template placeholders

### Pass 2: Low-risk imports
Next.

- Point new code at `craftworld_tools.config`
- Point new code at `craftworld_tools.db`
- Keep old functions in `app.py` until route extraction is done

### Pass 3: Split routes
Move routes one feature at a time into blueprints.

Recommended order:

1. Auth routes
2. API JSON routes
3. Pricing routes
4. Factory routes
5. Masterpiece routes
6. Main dashboard route

### Pass 4: Split templates
Move the largest inline HTML strings into Jinja templates.

Do this after route extraction so template context is easier to see.

### Pass 5: Remove compatibility wrappers
After everything imports from `craftworld_tools.*`, root-level wrappers can be deleted or kept as thin entry points.

## Rules for future cleanup

1. Do not move everything at once.
2. Keep the app deployable after every commit.
3. Move one feature area per pass.
4. Preserve old imports until all callers are updated.
5. Prefer boring names over clever names.
6. Keep pricing logic consistent with Profitability price modeling.
