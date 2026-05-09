# Auth route extraction

The auth routes have been extracted into:

```python
craftworld_tools/routes/auth.py
```

## Current status

The module is ready, but `app.py` still owns the live `/register`, `/login`, and `/logout` routes.

Do not register the new auth routes until the old inline route functions are removed from `app.py`, or Flask may either keep the old routes first or raise an endpoint conflict depending on how it is wired.

## Wire-in patch for `app.py`

Add this import near the other local imports:

```python
from craftworld_tools.routes.auth import register_auth_routes
```

Remove the inline block beginning at:

```python
@app.route("/register", methods=["GET", "POST"])
def register():
```

And ending after:

```python
@app.route("/logout")
def logout():
    session.pop("user_id", None)
    session.pop("username", None)
    return redirect(url_for("index"))
```

Then add this after `BASE_TEMPLATE` is defined and after `has_uid_flag()` and `get_db_connection()` exist:

```python
register_auth_routes(app, BASE_TEMPLATE, has_uid_flag, get_db_connection)
```

## Why the call must happen there

`register_auth_routes(...)` needs:

- `app`
- `BASE_TEMPLATE`
- `has_uid_flag`
- `get_db_connection`

So registering before those names exist will fail.

## Test checklist

After wiring:

```bash
python -m py_compile app.py craftworld_tools/routes/auth.py
```

Then smoke test:

- `/register`
- `/login`
- `/logout`
- Login redirect to `/boosts`
- Logout redirect to `/`
